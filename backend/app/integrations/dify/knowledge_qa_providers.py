"""Knowledge QA provider contract for the Stage 4A Career Assistant.

Uses a Protocol, a Fake provider
for offline tests, and a Dify provider that calls a Dify workflow with
the same transient-retry and masking discipline.
"""

from __future__ import annotations

import json
import time
from time import perf_counter
from typing import Any, Protocol

import httpx
from pydantic import JsonValue, ValidationError

from app.ai.prompts import CAREER_RAG_PROMPT_VERSION
from app.core.config import Settings
from app.core.exceptions import AppError
from app.schemas.career_assistant import (
    KnowledgeQAGeneration,
    KnowledgeQAProviderAttempt,
    KnowledgeQAProviderResult,
    KnowledgeQAWorkflowInput,
    KnowledgeQAWorkflowOutput,
)

# Maximum automatic retries inside the provider for transient errors.
# Total attempts = 1 initial + MAX_PROVIDER_RETRIES.
MAX_PROVIDER_RETRIES = 2
# Exponential backoff base in seconds: 1s, 2s for the two retries.
RETRY_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0)
# HTTP status codes that are considered transient and retryable.
RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({429, 502, 503, 504})


class KnowledgeQAProvider(Protocol):
    def answer_question(
        self,
        request: KnowledgeQAWorkflowInput,
    ) -> KnowledgeQAProviderResult: ...


class FakeKnowledgeQAProvider:
    """Deterministic offline provider used by tests and default mode."""

    def answer_question(
        self,
        request: KnowledgeQAWorkflowInput,
    ) -> KnowledgeQAProviderResult:
        chunks = request.context_chunks
        used_citation_keys = [
            f"doc-{chunk.document_id}-chunk-{chunk.chunk_index}" for chunk in chunks
        ]
        # Stage 4B: also cite personal context chunks so the enrichment
        # logic can be exercised end-to-end in offline tests.
        for p_chunk in request.personal_context:
            used_citation_keys.append(
                f"{p_chunk.source_type}-{p_chunk.source_id}-chunk-{p_chunk.chunk_index}"
            )
        first_title = chunks[0].title if chunks else "the knowledge base"
        personal_note = (
            f" with {len(request.personal_context)} personal context snippet(s)"
            if request.personal_context
            else ""
        )
        answer = (
            f"Based on '{first_title}', the answer to "
            f"'{request.question[:80]}' synthesises {len(chunks)} retrieved "
            f"snippet(s){personal_note}."
        )
        output = KnowledgeQAWorkflowOutput(
            answer=answer,
            used_citation_keys=used_citation_keys,
            insufficient_evidence=False,
            generation=KnowledgeQAGeneration(
                workflow_version="fake-knowledge-qa-v1",
                workflow_run_id=f"fake-qa-{request.user_id}-{int(time.time())}",
                provider="fake",
                latency_ms=0,
                prompt_version=CAREER_RAG_PROMPT_VERSION,
            ),
        )
        return KnowledgeQAProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            attempts=[
                KnowledgeQAProviderAttempt(
                    sequence=1,
                    http_status=200,
                    status="succeeded",
                    latency_ms=0,
                    retried=False,
                )
            ],
        )


class DifyKnowledgeQAProvider:
    """Calls the Dify knowledge QA workflow with transient retries."""

    def __init__(self, settings: Settings) -> None:
        if not settings.dify_base_url or not settings.dify_knowledge_qa_api_key:
            raise AppError(
                "DIFY_NOT_CONFIGURED",
                "Dify knowledge QA provider is not configured",
                503,
            )
        self.base_url = settings.dify_base_url.rstrip("/")
        self.api_key = settings.dify_knowledge_qa_api_key
        self.timeout_seconds = settings.dify_timeout_seconds
        self.workflow_url = _build_workflow_url(self.base_url)

    def answer_question(
        self,
        request: KnowledgeQAWorkflowInput,
    ) -> KnowledgeQAProviderResult:
        started = perf_counter()
        workflow_input = _build_dify_workflow_input(request)
        request_summary = _masked_request_summary(workflow_input)
        payload = {
            "inputs": {
                "data": json.dumps(workflow_input, ensure_ascii=False),
            },
            "response_mode": "blocking",
            "user": f"careerpilot-user-{request.user_id}",
        }
        attempts: list[KnowledgeQAProviderAttempt] = []
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
                    KnowledgeQAProviderAttempt(
                        sequence=attempt_index + 1,
                        http_status=None,
                        status="failed",
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
                output = KnowledgeQAWorkflowOutput.model_validate(output_payload)
            except AppError as exc:
                attempts.append(
                    KnowledgeQAProviderAttempt(
                        sequence=attempt_index + 1,
                        status="failed",
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
                    KnowledgeQAProviderAttempt(
                        sequence=attempt_index + 1,
                        status="failed",
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
                raw,
                ("data", "workflow_run_id"),
            )
            latency_ms = max(_elapsed_ms(started), 0)
            output = output.model_copy(
                update={
                    "generation": output.generation.model_copy(
                        update={
                            "workflow_run_id": output.generation.workflow_run_id or workflow_run_id,
                            "provider": "dify",
                            "latency_ms": output.generation.latency_ms or latency_ms,
                            "prompt_version": CAREER_RAG_PROMPT_VERSION,
                        }
                    )
                }
            )
            attempts.append(
                KnowledgeQAProviderAttempt(
                    sequence=attempt_index + 1,
                    latency_ms=attempt_latency,
                    retried=retried,
                    status="succeeded",
                    **attempt_metadata,
                )
            )
            return KnowledgeQAProviderResult(
                output=output,
                raw_output=_json_object(raw),
                attempts=attempts,
                request_summary=request_summary,
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
            raise AppError("DIFY_TIMEOUT", "Dify knowledge QA request timed out", 504) from exc
        except httpx.HTTPError as exc:
            raise AppError(
                "DIFY_UNAVAILABLE",
                "Dify knowledge QA provider is unavailable",
                503,
            ) from exc

        if response.status_code in RETRYABLE_HTTP_STATUS:
            raise AppError(
                "DIFY_HTTP_RETRYABLE",
                f"Dify returned retryable HTTP status {response.status_code}",
                502,
            )
        if response.status_code >= 400:
            raise AppError(
                "DIFY_REQUEST_FAILED",
                "Dify knowledge QA request failed",
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


def create_knowledge_qa_provider(settings: Settings) -> KnowledgeQAProvider:
    if settings.dify_provider_mode == "dify":
        return DifyKnowledgeQAProvider(settings)
    return FakeKnowledgeQAProvider()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_retryable_error(exc: AppError) -> bool:
    return exc.code in {
        "DIFY_TIMEOUT",
        "DIFY_UNAVAILABLE",
        "DIFY_HTTP_RETRYABLE",
        "DIFY_EMPTY_OUTPUT",
        "DIFY_EMPTY_RESULT",
        "DIFY_INVALID_JSON",
    }


def _build_dify_workflow_input(request: KnowledgeQAWorkflowInput) -> dict[str, JsonValue]:
    """Build the published Dify workflow's evidence shape.

    The Career Assistant retrieval contract uses ``context_chunks`` as its
    canonical Python field.  The currently published Dify workflow's Code
    node validates a legacy-compatible ``context`` collection instead, where
    each item must expose ``citation_key`` and ``content``.  Send both shapes
    from the same retrieved chunks so the workflow receives no invented
    evidence and the backend can still enrich citations by stable provenance
    keys.
    """

    workflow_input = request.model_dump(mode="json")
    context: list[dict[str, JsonValue]] = []
    for knowledge_chunk in request.context_chunks:
        context.append(
            {
                "citation_key": (
                    f"doc-{knowledge_chunk.document_id}-chunk-{knowledge_chunk.chunk_index}"
                ),
                "content": knowledge_chunk.chunk_text,
                "document_id": knowledge_chunk.document_id,
                "title": knowledge_chunk.title,
                "category": knowledge_chunk.category,
                "chunk_index": knowledge_chunk.chunk_index,
                "page_number": knowledge_chunk.page_number,
                "paragraph_index": knowledge_chunk.paragraph_index,
                "score": knowledge_chunk.score,
            }
        )
    workflow_input["context"] = context

    # The same Code node validates personal evidence with citation_key and
    # content.  Preserve the original fields, adding only deterministic keys
    # derived from the existing owner-scoped chunks.
    personal_context: list[dict[str, JsonValue]] = []
    for personal_chunk in request.personal_context:
        personal_context.append(
            {
                "citation_key": (
                    f"{personal_chunk.source_type}-{personal_chunk.source_id}"
                    f"-chunk-{personal_chunk.chunk_index}"
                ),
                "content": personal_chunk.chunk_text,
                **personal_chunk.model_dump(mode="json"),
            }
        )
    workflow_input["personal_context"] = personal_context
    return workflow_input


def _masked_request_summary(workflow_input: dict[str, JsonValue]) -> dict[str, JsonValue]:
    """Keep bounded, credential-free Dify input diagnostics in the QA run."""

    context = workflow_input.get("context")
    context_items = context if isinstance(context, list) else []
    personal = workflow_input.get("personal_context")
    personal_items = personal if isinstance(personal, list) else []

    def evidence_summary(item: JsonValue) -> dict[str, JsonValue]:
        source = item if isinstance(item, dict) else {}
        content = source.get("content")
        text = content if isinstance(content, str) else ""
        return {
            "citation_key": source.get("citation_key"),
            "document_id": source.get("document_id"),
            "source_type": source.get("source_type"),
            "source_id": source.get("source_id"),
            "title": source.get("title"),
            "category": source.get("category"),
            "chunk_index": source.get("chunk_index"),
            "score": source.get("score"),
            "content_preview": _truncate(text, 800),
            "content_length": len(text),
        }

    return {
        "input_variable": "data",
        "data_is_json_string": True,
        "schema_version": workflow_input.get("schema_version"),
        "question": workflow_input.get("question"),
        "requested_entities": workflow_input.get("requested_entities", []),
        "retrieved_entities": workflow_input.get("retrieved_entities", []),
        "missing_entities": workflow_input.get("missing_entities", []),
        "retrieved_context": [evidence_summary(item) for item in context_items],
        "personal_context": [evidence_summary(item) for item in personal_items],
    }


def _build_workflow_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return f"{normalized}/workflows/run"
    return f"{normalized}/v1/workflows/run"


def _extract_masked_metadata(raw: dict[str, Any], http_status: int) -> dict[str, Any]:
    """Build a masked metadata dict for diagnostics without exposing sensitive data.

    Note: ``status`` is intentionally omitted here -- it is the provider's own
    semantic attempt status ("succeeded"/"failed"), set explicitly on each
    attempt. The Dify-side workflow ``status`` is not stored separately to
    avoid confusing it with the attempt status; the Dify ``error`` field and
    ``raw_output`` capture enough diagnostic context.
    """
    raw_data = raw.get("data")
    data: dict[str, Any] = raw_data if isinstance(raw_data, dict) else {}
    raw_outputs = data.get("outputs")
    outputs: dict[str, Any] = raw_outputs if isinstance(raw_outputs, dict) else {}
    workflow_run_id = _string_path(raw, ("workflow_run_id",)) or _string_path(
        raw, ("data", "workflow_run_id")
    )
    return {
        "http_status": http_status,
        "workflow_run_id": _truncate_str(workflow_run_id),
        "workflow_id": _truncate_str(_string_path(data, ("workflow_id",))),
        "error": _truncate_str(_string_path(data, ("error",))),
        "total_steps": _optional_int(data.get("total_steps")),
        "elapsed_time": _optional_float(data.get("elapsed_time")),
        "outputs_keys": sorted(outputs.keys()),
    }


def _extract_output(raw: dict[str, Any]) -> dict[str, Any]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else None
    outputs = data.get("outputs") if isinstance(data, dict) else None
    candidate: Any = outputs if outputs is not None else raw.get("outputs", raw)

    if isinstance(outputs, dict) and not outputs:
        status = _string_path(raw, ("data", "status")) or _string_path(raw, ("status",))
        raise AppError(
            "DIFY_EMPTY_OUTPUT",
            (
                "Dify returned an empty outputs object"
                + (f" with status={status}" if status else "")
            ),
            502,
        )

    if isinstance(candidate, dict):
        if not candidate:
            raise AppError(
                "DIFY_EMPTY_OUTPUT",
                "Dify returned an empty output object",
                502,
            )
        for key in ("result", "output", "text", "json"):
            value = candidate.get(key)
            if isinstance(value, str):
                if not value.strip():
                    raise AppError(
                        "DIFY_EMPTY_RESULT",
                        f"Dify returned an empty string for output key '{key}'",
                        502,
                    )
                return _parse_json(value)
            if isinstance(value, dict):
                return value
        return candidate
    if isinstance(candidate, str):
        if not candidate.strip():
            raise AppError(
                "DIFY_EMPTY_RESULT",
                "Dify returned an empty output string",
                502,
            )
        return _parse_json(candidate)
    raise AppError("DIFY_OUTPUT_INVALID", "Dify returned an unsupported output shape", 502)


def _parse_json(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise AppError("DIFY_INVALID_JSON", "Dify returned invalid JSON", 502) from exc
    if not isinstance(parsed, dict):
        raise AppError("DIFY_OUTPUT_INVALID", "Dify returned a non-object JSON output", 502)
    return parsed


def _string_path(raw: dict[str, Any], path: tuple[str, ...]) -> str | None:
    current: Any = raw
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, str) else None


def _optional_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) else None


def _truncate_str(value: str | None, max_length: int = 160) -> str | None:
    if value is None:
        return None
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def _elapsed_ms(started: float) -> int:
    return max(round((perf_counter() - started) * 1000), 0)


def _json_object(raw: dict[str, Any]) -> dict[str, JsonValue]:
    parsed = json.loads(json.dumps(raw, ensure_ascii=False, default=str))
    if not isinstance(parsed, dict):
        raise AppError("DIFY_OUTPUT_INVALID", "Dify returned a non-object response", 502)
    return parsed
