"""Resume optimization Dify providers.

This module uses a separate
Dify App Key (``DIFY_RESUME_OPTIMIZATION_API_KEY``) and a separate workflow
version. It reuses the shared HTTP helpers from
``app.integrations.dify.workflow_helpers`` (URL construction, retry policy,
masked metadata, JSON parsing) so the resume optimization provider does
not duplicate the stabilized Dify HTTP client logic.
"""

from __future__ import annotations

import json
import time
from time import perf_counter
from typing import Any, Protocol

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import AppError
from app.integrations.dify.workflow_helpers import (
    MAX_PROVIDER_RETRIES,
    RETRY_BACKOFF_SECONDS,
    _build_workflow_url,
    _elapsed_ms,
    _extract_masked_metadata,
    _extract_output,
    _is_retryable_error,
    _json_object,
    _string_path,
    _truncate,
)
from app.schemas.resume_optimizations import (
    ResumeOptimizationGeneration,
    ResumeOptimizationKeywordSuggestion,
    ResumeOptimizationProviderAttempt,
    ResumeOptimizationProviderResult,
    ResumeOptimizationSectionOutput,
    ResumeOptimizationWorkflowInput,
    ResumeOptimizationWorkflowOutput,
    SectionChangeType,
)


class ResumeOptimizationProvider(Protocol):
    def generate_optimization(
        self,
        request: ResumeOptimizationWorkflowInput,
    ) -> ResumeOptimizationProviderResult: ...


class FakeResumeOptimizationProvider:
    """Deterministic fake provider for tests and offline development.

    Produces a suggestion that rewrites the first resume experience to
    emphasize matched skills, plus a keyword suggestion derived from
    matched skills. It never invents new skills or companies.
    """

    def generate_optimization(
        self,
        request: ResumeOptimizationWorkflowInput,
    ) -> ResumeOptimizationProviderResult:
        matched_names = [
            str(item.get("normalized_name") or item.get("job_raw_name") or "")
            for item in request.match_report.matched_skills
            if item.get("normalized_name") or item.get("job_raw_name")
        ]
        missing_names = [
            str(item.get("normalized_name") or item.get("job_raw_name") or "")
            for item in request.match_report.missing_skills
            if item.get("normalized_name") or item.get("job_raw_name")
        ]
        missing_lower = {name.lower() for name in missing_names if name}
        experiences = request.resume.experiences
        # Use conclusion_key or resume_source_id as evidence keys (not
        # resume_evidence which is free-text evidence, not a key).
        evidence_keys = [
            str(item.get("conclusion_key") or item.get("resume_source_id") or "")
            for item in request.match_report.evidence
            if item.get("conclusion_key") or item.get("resume_source_id")
        ][:5]
        sections: list[ResumeOptimizationSectionOutput] = []
        if experiences:
            first = experiences[0]
            # The description is an EvidenceField dict with a "value" key.
            desc_field = first.get("description")
            if isinstance(desc_field, dict):
                description = str(desc_field.get("value") or "")
            else:
                description = str(desc_field or "")
            # Never suggest text that mentions a missing skill — that would
            # fail server-side anti-fabrication validation. If the original
            # description mentions missing skills, produce a NO_CHANGE
            # suggestion instead.
            description_lower = description.lower()
            mentions_missing = any(name in description_lower for name in missing_lower if name)
            if mentions_missing or not matched_names:
                suggested = description
                change_type = SectionChangeType.NO_CHANGE
                reason = "No rewrites proposed; original content preserved."
            else:
                keyword_text = ", ".join(matched_names[:3])
                suggested = (
                    f"{description} Emphasize hands-on work with {keyword_text}."
                    if description
                    else f"Hands-on work with {keyword_text}."
                ).strip()
                change_type = SectionChangeType.EMPHASIZE
                reason = (
                    "Reorder and emphasize matched skills so the recruiter sees "
                    "them in the first bullet."
                )
            sections.append(
                ResumeOptimizationSectionOutput(
                    section="工作经历",
                    source_section_id="experience-1",
                    original_text=description,
                    suggested_text=suggested,
                    reason=reason,
                    related_job_requirement=(
                        ", ".join(matched_names[:3]) if matched_names else "岗位摘要匹配项"
                    ),
                    evidence_keys=evidence_keys,
                    change_type=change_type,
                )
            )
        keyword_suggestions: list[ResumeOptimizationKeywordSuggestion] = []
        for name in matched_names[:3]:
            keyword_suggestions.append(
                ResumeOptimizationKeywordSuggestion(
                    keyword=name,
                    reason="岗位摘要明确提及",
                    evidence_keys=evidence_keys,
                )
            )
        missing_evidence_warnings: list[str] = []
        if missing_names:
            missing_evidence_warnings.append(
                "缺失技能不得写入简历: " + ", ".join(missing_names[:5]) + ". 请在真实学习后再补充."
            )
        fabrication_warnings: list[str] = []
        job_warning = ""
        if request.job.is_summary_only:
            job_warning = "当前优化建议仅基于公开岗位摘要生成，不能覆盖原平台完整职位要求。"
        output = ResumeOptimizationWorkflowOutput(
            summary=(
                f"针对 {request.job.title} 岗位优化简历表达与关键词，"
                "仅基于已有经历与证据，不虚构内容。"
            ),
            sections=sections,
            keyword_suggestions=keyword_suggestions,
            missing_evidence_warnings=missing_evidence_warnings,
            fabrication_warnings=fabrication_warnings,
            job_information_warning=job_warning,
            generation=ResumeOptimizationGeneration(
                workflow_version="fake-resume-optimization-v1",
                workflow_run_id=f"fake-{request.match_report.report_id}",
                provider="fake",
                latency_ms=0,
            ),
        )
        return ResumeOptimizationProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            attempts=[
                ResumeOptimizationProviderAttempt(
                    sequence=1,
                    http_status=200,
                    status="succeeded",
                    latency_ms=0,
                    retried=False,
                )
            ],
        )


class DifyResumeOptimizationProvider:
    """Real Dify provider for the resume optimization workflow.

    Reuses the shared HTTP helpers from the workflow helper module
    so URL construction, retry policy, masked metadata, and JSON parsing
    stay consistent. Only the API key and workflow version differ.
    """

    def __init__(self, settings: Settings) -> None:
        if not settings.dify_base_url or not settings.dify_resume_optimization_api_key:
            raise AppError(
                "DIFY_NOT_CONFIGURED",
                "Dify resume optimization provider is not configured",
                503,
            )
        self.base_url = settings.dify_base_url.rstrip("/")
        self.api_key = settings.dify_resume_optimization_api_key
        self.timeout_seconds = settings.dify_timeout_seconds
        self.workflow_version = settings.dify_resume_optimization_workflow_version
        self.workflow_url = _build_workflow_url(self.base_url)

    def generate_optimization(
        self,
        request: ResumeOptimizationWorkflowInput,
    ) -> ResumeOptimizationProviderResult:
        started = perf_counter()
        payload = {
            "inputs": {
                "data": json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
            },
            "response_mode": "blocking",
            "user": f"careerpilot-user-{request.resume.resume_version_id}",
        }
        attempts: list[ResumeOptimizationProviderAttempt] = []
        last_error: AppError | None = None
        for attempt_index in range(MAX_PROVIDER_RETRIES + 1):
            attempt_started = perf_counter()
            retried = attempt_index > 0
            if retried:
                backoff = RETRY_BACKOFF_SECONDS[attempt_index - 1]
                time.sleep(backoff)
            try:
                raw, http_status = self._post_payload(payload)
            except AppError as exc:
                attempt_latency = _elapsed_ms(attempt_started)
                attempts.append(
                    ResumeOptimizationProviderAttempt(
                        sequence=attempt_index + 1,
                        http_status=None,
                        latency_ms=attempt_latency,
                        retried=retried,
                        error_code=exc.code,
                        error_message=_truncate(exc.message, 240),
                    )
                )
                last_error = exc
                if not _is_retryable_error(exc):
                    break
                continue

            attempt_metadata = _extract_masked_metadata(raw, http_status)
            attempt_latency = _elapsed_ms(attempt_started)
            try:
                output_payload = _extract_output(raw)
                output = ResumeOptimizationWorkflowOutput.model_validate(output_payload)
            except AppError as exc:
                attempts.append(
                    ResumeOptimizationProviderAttempt(
                        sequence=attempt_index + 1,
                        latency_ms=attempt_latency,
                        retried=retried,
                        error_code=exc.code,
                        error_message=_truncate(exc.message, 240),
                        **attempt_metadata,
                    )
                )
                last_error = exc
                if not _is_retryable_error(exc):
                    break
                continue
            except ValidationError:
                attempts.append(
                    ResumeOptimizationProviderAttempt(
                        sequence=attempt_index + 1,
                        latency_ms=attempt_latency,
                        retried=retried,
                        error_code="DIFY_OUTPUT_INVALID",
                        error_message=_truncate("Dify output failed Pydantic validation", 240),
                        **attempt_metadata,
                    )
                )
                last_error = AppError(
                    "DIFY_OUTPUT_INVALID",
                    "Dify output failed Pydantic validation",
                    502,
                )
                break

            workflow_run_id = _string_path(raw, ("workflow_run_id",)) or _string_path(
                raw, ("data", "workflow_run_id")
            )
            latency_ms = max(_elapsed_ms(started), 0)
            output = output.model_copy(
                update={
                    "generation": output.generation.model_copy(
                        update={
                            "workflow_run_id": output.generation.workflow_run_id or workflow_run_id,
                            "workflow_version": output.generation.workflow_version
                            or self.workflow_version,
                            "provider": "dify",
                            "latency_ms": output.generation.latency_ms or latency_ms,
                        }
                    )
                }
            )
            attempts.append(
                ResumeOptimizationProviderAttempt(
                    sequence=attempt_index + 1,
                    latency_ms=attempt_latency,
                    retried=retried,
                    **attempt_metadata,
                )
            )
            return ResumeOptimizationProviderResult(
                output=output,
                raw_output=_json_object(raw),
                attempts=attempts,
            )

        assert last_error is not None
        raise last_error

    def _post_payload(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        try:
            with httpx.Client(
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=False,
                trust_env=False,
            ) as client:
                response = client.post(
                    self.workflow_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            raise AppError(
                "DIFY_TIMEOUT", "Dify resume optimization request timed out", 504
            ) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                "DIFY_UNAVAILABLE",
                "Dify resume optimization provider is unavailable",
                503,
            ) from exc

        from app.integrations.dify.workflow_helpers import RETRYABLE_HTTP_STATUS

        if response.status_code in RETRYABLE_HTTP_STATUS:
            raise AppError(
                "DIFY_HTTP_RETRYABLE",
                f"Dify returned retryable HTTP status {response.status_code}",
                502,
            )
        if response.status_code >= 400:
            raise AppError(
                "DIFY_REQUEST_FAILED",
                "Dify resume optimization request failed",
                502,
            )
        try:
            raw = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise AppError(
                "DIFY_OUTPUT_INVALID",
                "Dify returned a non-JSON response",
                502,
            ) from exc
        return raw, response.status_code


def create_resume_optimization_provider(
    settings: Settings,
) -> ResumeOptimizationProvider:
    if settings.dify_provider_mode == "dify":
        return DifyResumeOptimizationProvider(settings)
    return FakeResumeOptimizationProvider()
