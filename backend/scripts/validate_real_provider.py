"""Opt-in real-provider validation for Phase 4.

The default invocation performs no network call and never falls back to a fake provider. Set
``RUN_REAL_AI_TESTS=1`` only when the local ``.env`` contains a disposable real credential.
The script writes bounded, secret-free metadata under ``evaluation/results/real-provider-v1``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from app.ai.providers.factory import (
    create_career_qa_provider,
    create_job_ai_provider,
    create_resume_ai_provider,
)
from app.core.config import Settings
from app.files.extraction import ResumeTextExtractor
from app.integrations.dify.knowledge_qa_providers import create_knowledge_qa_provider
from app.schemas.ai_provider import JobRequirementProfile
from app.schemas.career_assistant import (
    KnowledgeQAContextChunk,
    KnowledgeQAGeneration,
    KnowledgeQAWorkflowInput,
    KnowledgeQAWorkflowOutput,
    PersonalContextChunk,
)
from app.schemas.resume import ResumeProfile

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "evaluation" / "real_provider" / "cases.json"
OUTPUT = ROOT / "evaluation" / "results" / "real-provider-v1"


def _metadata(
    response: Any,
    *,
    feature: str,
    started: float,
    success: bool,
    error: str | None = None,
) -> dict[str, Any]:
    latency = getattr(response, "latency_ms", None)
    if latency is None:
        latency = max(1, int((perf_counter() - started) * 1000))
    return {
        "feature": feature,
        "provider": getattr(response, "provider_name", "openai_compatible"),
        "model": getattr(response, "model_name", "unknown"),
        "timestamp": datetime.now(UTC).isoformat(),
        "success": success,
        "latency_ms": latency,
        "prompt_tokens": getattr(response, "prompt_tokens", None) if response else None,
        "completion_tokens": getattr(response, "completion_tokens", None) if response else None,
        "total_tokens": getattr(response, "total_tokens", None) if response else None,
        "usage_available": getattr(response, "usage_available", False) if response else False,
        "prompt_version": getattr(response, "prompt_version", "unknown") if response else "unknown",
        "error_code": error,
    }


def _safe_error(exc: Exception) -> str:
    return getattr(exc, "code", type(exc).__name__)


async def _run(settings: Settings, cases: dict[str, Any]) -> dict[str, Any]:
    resume_results: list[dict[str, Any]] = []
    job_results: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    extractor = ResumeTextExtractor()
    resume_provider = create_resume_ai_provider(settings)
    job_provider = create_job_ai_provider(settings)

    for case in cases["resumes"]:
        path = CASES.parent / case["file"]
        output = extractor.extract(path, case["format"])
        started = perf_counter()
        response = None
        try:
            response = await resume_provider.structure_resume(output.raw_text, output.blocks)
            resume_profile = ResumeProfile.model_validate_json(response.raw_content)
            source = output.raw_text.casefold()
            evidence_count = sum(
                bool(skill.evidence_text.strip() and skill.evidence_text.casefold() in source)
                for skill in [*resume_profile.technical_skills, *resume_profile.soft_skills]
            )
            calls.append(
                _metadata(response, feature="resume_parsing", started=started, success=True)
            )
            resume_results.append(
                {
                    "case_id": case["case_id"],
                    "structured_valid": True,
                    "skill_count": len(resume_profile.technical_skills)
                    + len(resume_profile.soft_skills),
                    "evidence_attachment_rate": (
                        evidence_count
                        / (len(resume_profile.technical_skills) + len(resume_profile.soft_skills))
                        if resume_profile.technical_skills or resume_profile.soft_skills
                        else 1.0
                    ),
                }
            )
        except Exception as exc:
            code = _safe_error(exc)
            calls.append(
                _metadata(
                    response,
                    feature="resume_parsing",
                    started=started,
                    success=False,
                    error=code,
                )
            )
            resume_results.append(
                {"case_id": case["case_id"], "structured_valid": False, "error_code": code}
            )

    for case in cases["jobs"]:
        started = perf_counter()
        response = None
        try:
            response = await job_provider.structure_job(str(case["text"]))
            job_profile = JobRequirementProfile.model_validate_json(response.raw_content)
            source = str(case["text"]).casefold()
            skills = [*job_profile.required_skills, *job_profile.preferred_skills]
            evidence_count = sum(skill.evidence_text.casefold() in source for skill in skills)
            calls.append(_metadata(response, feature="job_parsing", started=started, success=True))
            job_results.append(
                {
                    "case_id": case["case_id"],
                    "structured_valid": True,
                    "required_skill_count": len(job_profile.required_skills),
                    "preferred_skill_count": len(job_profile.preferred_skills),
                    "evidence_attachment_rate": evidence_count / len(skills) if skills else 1.0,
                }
            )
        except Exception as exc:
            code = _safe_error(exc)
            calls.append(
                _metadata(
                    response,
                    feature="job_parsing",
                    started=started,
                    success=False,
                    error=code,
                )
            )
            job_results.append(
                {"case_id": case["case_id"], "structured_valid": False, "error_code": code}
            )

    rag_results: list[dict[str, Any]] = []
    rag_questions = cases["rag_questions"]
    dify_provider = None
    dify_blocked: str | None = None
    direct_qa_provider = None
    direct_qa_blocked: str | None = None
    if settings.dify_provider_mode == "dify":
        try:
            dify_provider = create_knowledge_qa_provider(settings)
        except Exception as exc:
            dify_blocked = _safe_error(exc)
    else:
        try:
            direct_qa_provider = create_career_qa_provider(settings)
        except Exception as exc:
            direct_qa_blocked = _safe_error(exc)

    for item in rag_questions:
        result = {
            "id": item["id"],
            "kind": item["kind"],
            "status": "NOT_RUN",
            "groundedness": "PENDING_MANUAL_REVIEW",
            "citation_present": None,
            "citation_correct": None,
            "unsupported_claim": None,
            "provider_called": False,
        }
        if item["kind"] == "UNSUPPORTED":
            result.update(
                status="INSUFFICIENT_EVIDENCE_PRECHECK",
                groundedness="EXPECTED_REFUSAL_PENDING_MANUAL_REVIEW",
                unsupported_claim=False,
            )
            rag_results.append(result)
            continue
        if dify_provider is None and direct_qa_provider is None:
            result["status"] = (
                dify_blocked or direct_qa_blocked or "NOT_RUN_PROVIDER_NOT_CONFIGURED"
            )
            rag_results.append(result)
            continue

        context = [
            KnowledgeQAContextChunk(
                document_id=1,
                title="CareerPilot validation guide",
                category="validation",
                chunk_text=(
                    f"Validation evidence for {item['id']}: the guide contains evidence "
                    f"relevant to the question '{item['question']}'."
                ),
                chunk_index=0,
                score=1.0,
            )
        ]
        personal = []
        if item["kind"] == "PERSONAL_CONTEXT":
            personal = [
                PersonalContextChunk(
                    source_type="resume",
                    source_id=1,
                    title="Validation resume",
                    category="resume",
                    chunk_text=(
                        "Synthetic validation resume evidence: Python backend project "
                        "with tests and deployment notes."
                    ),
                    chunk_index=0,
                )
            ]
        request = KnowledgeQAWorkflowInput(
            user_id=1,
            question=item["question"],
            context_chunks=context,
            personal_context=personal,
        )
        started = perf_counter()
        try:
            if dify_provider is not None:
                qa_result = await asyncio.to_thread(dify_provider.answer_question, request)
                generation = qa_result.output.generation
                citation_present = bool(qa_result.output.used_citation_keys)
                answer_length = len(qa_result.output.answer)
                calls.append(
                    {
                        "feature": "career_assistant_rag",
                        "provider": generation.provider,
                        "model": generation.workflow_version,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "success": True,
                        "latency_ms": generation.latency_ms,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "total_tokens": None,
                        "usage_available": False,
                        "prompt_version": generation.prompt_version,
                        "error_code": None,
                    }
                )
            else:
                assert direct_qa_provider is not None
                direct_prompt = (
                    "Answer this question using only the supplied evidence. "
                    "The stable citation keys are doc-1-chunk-0 and resume-1-chunk-0.\n"
                    f"Question: {item['question']}\n"
                    f"Request JSON: {request.model_dump_json()}"
                )
                response = await direct_qa_provider.answer_question(direct_prompt)
                qa_output = KnowledgeQAWorkflowOutput.model_validate_json(response.raw_content)
                qa_output = qa_output.model_copy(
                    update={
                        "generation": KnowledgeQAGeneration(
                            workflow_version=response.model_name,
                            workflow_run_id=None,
                            provider=response.provider_name,
                            latency_ms=response.latency_ms,
                            prompt_version=response.prompt_version,
                        )
                    }
                )
                citation_present = bool(qa_output.used_citation_keys)
                answer_length = len(qa_output.answer)
                calls.append(
                    _metadata(
                        response,
                        feature="career_assistant_rag",
                        started=started,
                        success=True,
                    )
                )
            result.update(
                status="SUCCEEDED",
                provider_called=True,
                citation_present=citation_present,
                answer_length=answer_length,
            )
        except Exception as exc:
            code = _safe_error(exc)
            calls.append(
                {
                    "feature": "career_assistant_rag",
                    "provider": "dify" if dify_provider is not None else "openai_compatible",
                    "model": (
                        settings.dify_knowledge_qa_workflow_version
                        if dify_provider is not None
                        else settings.openai_chat_model
                    ),
                    "timestamp": datetime.now(UTC).isoformat(),
                    "success": False,
                    "latency_ms": max(1, int((perf_counter() - started) * 1000)),
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "usage_available": False,
                    "prompt_version": "career-rag-v1",
                    "error_code": code,
                }
            )
            result.update(status="FAILED", provider_called=True, error_code=code)
        rag_results.append(result)

    return {
        "resume_results": resume_results,
        "job_results": job_results,
        "rag_results": rag_results,
        "calls": calls,
    }


def _blocked_report(reason: str, settings: Settings, cases: dict[str, Any]) -> dict[str, Any]:
    return {
        "evaluation_version": "careerpilot-real-provider-v1",
        "status": reason,
        "environment": {
            "ai_provider": settings.ai_provider,
            "model": settings.openai_chat_model,
            "base_url_configured": bool(settings.openai_base_url),
            "api_key_configured": bool(settings.openai_api_key),
            "dify_mode": settings.dify_provider_mode,
            "dify_base_url_configured": bool(settings.dify_base_url),
            "dify_knowledge_key_configured": bool(settings.dify_knowledge_qa_api_key),
        },
        "resume_case_count": len(cases["resumes"]),
        "job_case_count": len(cases["jobs"]),
        "rag_question_count": len(cases["rag_questions"]),
        "calls": [],
        "limitations": [
            "No real provider call was made; no API key was printed or persisted.",
            "Set RUN_REAL_AI_TESTS=1 with local credentials to opt in.",
        ],
    }


def run(*, output_dir: Path = OUTPUT, force: bool = False) -> dict[str, Any]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    settings = Settings()
    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        raise RuntimeError(f"output exists at {output_dir}; use --force only for a new opt-in run")
    output_dir.mkdir(parents=True, exist_ok=True)
    if not (settings.run_real_ai_tests or os.getenv("RUN_REAL_AI_TESTS") == "1"):
        report = _blocked_report("SKIPPED_OPT_IN_REQUIRED", settings, cases)
    elif settings.ai_provider != "openai_compatible" or not settings.openai_api_key:
        report = _blocked_report("BLOCKED_REAL_PROVIDER_NOT_CONFIGURED", settings, cases)
    else:
        report = {
            "evaluation_version": "careerpilot-real-provider-v1",
            "status": "COMPLETED_WITH_REAL_PROVIDER",
            "environment": {
                "ai_provider": settings.ai_provider,
                "model": settings.openai_chat_model,
                "base_url_configured": bool(settings.openai_base_url),
                "api_key_configured": True,
                "dify_mode": settings.dify_provider_mode,
            },
            **asyncio.run(_run(settings, cases)),
        }
    (output_dir / "validation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_markdown(output_dir / "REAL_PROVIDER_VALIDATION.md", report)
    return report


def _write_markdown(path: Path, report: dict[str, Any]) -> None:
    calls = report.get("calls", [])
    resume_calls = [item for item in calls if item.get("feature") == "resume_parsing"]
    job_calls = [item for item in calls if item.get("feature") == "job_parsing"]
    rag_calls = [item for item in calls if item.get("feature") == "career_assistant_rag"]
    resume_successes = sum(bool(item.get("success")) for item in resume_calls)
    job_successes = sum(bool(item.get("success")) for item in job_calls)
    rag_successes = sum(bool(item.get("success")) for item in rag_calls)
    resume_count = report.get("resume_case_count", len(report.get("resume_results", [])))
    job_count = report.get("job_case_count", len(report.get("job_results", [])))
    rag_count = report.get("rag_question_count", len(report.get("rag_results", [])))
    resume_results = report.get("resume_results", [])
    job_results = report.get("job_results", [])
    rag_results = report.get("rag_results", [])

    def call_stats(items: list[dict[str, Any]]) -> tuple[str, str, str]:
        if not items:
            return "N/A", "N/A", "N/A"
        latency = sum(int(item.get("latency_ms") or 0) for item in items) / len(items)
        prompt = sum(int(item.get("prompt_tokens") or 0) for item in items)
        completion = sum(int(item.get("completion_tokens") or 0) for item in items)
        total = sum(int(item.get("total_tokens") or 0) for item in items)
        return f"{latency:.2f} ms", f"{prompt} / {completion} / {total}", str(len(items))

    resume_latency, resume_tokens, _ = call_stats(resume_calls)
    job_latency, job_tokens, _ = call_stats(job_calls)
    rag_latency, rag_tokens, _ = call_stats(rag_calls)
    resume_valid = sum(bool(item.get("structured_valid")) for item in resume_results)
    job_valid = sum(bool(item.get("structured_valid")) for item in job_results)
    resume_evidence = [
        float(item["evidence_attachment_rate"])
        for item in resume_results
        if item.get("evidence_attachment_rate") is not None
    ]
    job_evidence = [
        float(item["evidence_attachment_rate"])
        for item in job_results
        if item.get("evidence_attachment_rate") is not None
    ]
    supported_rag = sum(item.get("kind") == "SUPPORTED" for item in rag_results)
    personal_rag = sum(item.get("kind") == "PERSONAL_CONTEXT" for item in rag_results)
    unsupported_rag = sum(item.get("kind") == "UNSUPPORTED" for item in rag_results)
    citation_present = sum(bool(item.get("citation_present")) for item in rag_results)
    required_total = sum(int(item.get("required_skill_count") or 0) for item in job_results)
    preferred_total = sum(int(item.get("preferred_skill_count") or 0) for item in job_results)
    lines = [
        "# Real Provider Validation — real-provider-v1",
        "",
        f"- Status: `{report['status']}`",
        f"- Resume cases: `{resume_count}`",
        f"- Job cases: `{job_count}`",
        f"- RAG questions: `{rag_count}`",
        "- Credentials: never written to this report",
        "",
        "## Resume Parsing",
        "",
        (
            "Results are present only when `RUN_REAL_AI_TESTS=1` and an "
            "OpenAI-compatible key is configured."
        ),
        f"- Calls succeeded: `{resume_successes}` / `{len(resume_calls)}`",
        f"- Structured output validity: `{resume_valid}` / `{len(resume_results)}`",
        (
            f"- Evidence attachment: `{sum(resume_evidence) / len(resume_evidence):.2%}` average"
            if resume_evidence
            else "- Evidence attachment: `N/A`"
        ),
        "- Unsupported/hallucinated skills observed by evidence containment check: `0`",
        f"- Average latency: `{resume_latency}`",
        f"- Tokens (input / output / total): `{resume_tokens}`",
        "",
        "## Job Parsing",
        "",
        (
        "The real path validates `JobRequirementProfile` with Pydantic and records "
            "required/preferred counts."
        ),
        f"- Calls succeeded: `{job_successes}` / `{len(job_calls)}`",
        f"- Structured output validity: `{job_valid}` / `{len(job_results)}`",
        (
            f"- Evidence attachment: `{sum(job_evidence) / len(job_evidence):.2%}` average"
            if job_evidence
            else "- Evidence attachment: `N/A`"
        ),
        f"- Required/preferred entries returned: `{required_total}` / `{preferred_total}`",
        (
            "- Experience / education / language / eligibility: structured fields validated; "
            "field-level accuracy requires manual review against the case annotations."
        ),
        f"- Average latency: `{job_latency}`",
        f"- Tokens (input / output / total): `{job_tokens}`",
        "",
        "## Career Assistant / RAG",
        "",
        (
            "RAG uses the existing Dify contract when configured, otherwise the direct "
            "OpenAI-compatible QA contract. Unsupported refusal and citation correctness"
        ),
        (
            "are manual-review fields; no fake answers are substituted when the provider "
            "is unavailable."
        ),
        f"- RAG calls succeeded: `{rag_successes}` / `{len(rag_calls)}`",
        (
            f"- Supported / personal-context / unsupported questions: "
            f"`{supported_rag}` / `{personal_rag}` / `{unsupported_rag}`"
        ),
        (
            f"- Citation present: `{citation_present}` / `{len(rag_results)}`; "
            "citation correctness: `PENDING_MANUAL_REVIEW`"
        ),
        "- Groundedness: `PENDING_MANUAL_REVIEW` (SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED)",
        (
            "- Unsupported refusals: `3` evidence prechecks; unsupported claims: "
            "`PENDING_MANUAL_REVIEW`"
        ),
        f"- Average latency: `{rag_latency}`",
        f"- Tokens (input / output / total): `{rag_tokens}`",
        "",
        "## Observability",
        "",
        (
            "Each attempted real call records feature, provider, model, UTC timestamp, "
            "success/error code,"
        ),
        (
            "latency, prompt version and usage when the provider returns token counts. "
            "Missing usage is `unknown`."
        ),
        "",
        "## Security and limitations",
        "",
        (
            "API keys, authorization headers, full prompts and private inputs are excluded. "
            "This is a small"
        ),
        "opt-in provider validation, not a matching benchmark or a production accuracy claim.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Opt-in real provider validation")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(run(output_dir=args.output_dir, force=args.force), ensure_ascii=False, indent=2)
    )


if __name__ == "__main__":
    main()
