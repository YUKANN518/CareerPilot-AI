"""Real Dify resume optimization smoke test.

Only runs when RUN_REAL_DIFY_TESTS=1 is set in the environment. Requires:

- DIFY_BASE_URL
- DIFY_RESUME_OPTIMIZATION_API_KEY
- DIFY_PROVIDER_MODE=dify

This script never hard-codes Dify keys. It reads them from the environment
via the standard Settings loader. Run from the backend directory:

    RUN_REAL_DIFY_TESTS=1 python scripts/test_real_dify_resume_optimization.py

When DIFY_SOAK_RUNS is set (e.g. DIFY_SOAK_RUNS=10), the script runs the
request N times and reports stability statistics. Otherwise it runs once.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

DEFAULT_SOAK_RUNS = 1
MIN_ACCEPTANCE_PASSES = 9


def _fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def _elapsed_ms(started: float) -> int:
    return max(round((perf_counter() - started) * 1000), 0)


def _build_request():
    from app.schemas.resume_optimizations import (
        ResumeOptimizationJobInput,
        ResumeOptimizationMatchReportInput,
        ResumeOptimizationResumeInput,
        ResumeOptimizationWorkflowInput,
    )

    return ResumeOptimizationWorkflowInput(
        resume=ResumeOptimizationResumeInput(
            resume_version_id=1,
            summary="Backend engineer with 4 years of Python experience.",
            education=[
                {
                    "institution": {"value": "Fixture University"},
                    "degree": {"value": "Bachelor"},
                }
            ],
            experiences=[
                {
                    "company": {"value": "CareerPilot Labs"},
                    "title": {"value": "Software Engineer"},
                    "start_date": {"value": "2020-01"},
                    "end_date": {"value": "2023-12"},
                    "description": {"value": "Built Python services with FastAPI and PostgreSQL."},
                }
            ],
            projects=[],
            skills=[{"value": "Python"}, {"value": "PostgreSQL"}],
            evidence=[
                {
                    "key": "resume-evidence-1",
                    "skill": "Python",
                    "evidence_text": "Built Python services with FastAPI.",
                    "section": "work_experience",
                }
            ],
        ),
        job=ResumeOptimizationJobInput(
            job_id=1,
            title="Backend Engineer",
            company="Smoke Test Company",
            summary="Build reliable Python services using FastAPI and SQL.",
            source_name="JOBSDB",
            source_url="https://jobs.example.com/seed-job-1",
            information_completeness=0.8,
            is_summary_only=True,
        ),
        match_report=ResumeOptimizationMatchReportInput(
            report_id=1,
            final_score=72.0,
            matched_skills=[
                {"normalized_name": "Python", "status": "MATCHED"},
                {"normalized_name": "PostgreSQL", "status": "MATCHED"},
            ],
            partial_skills=[],
            missing_skills=[
                {
                    "normalized_name": "Docker",
                    "status": "MISSING",
                    "job_raw_name": "Docker",
                },
            ],
            blocking_risks=[],
            evidence=[
                {
                    "detail_code": "SKILL_MATCH",
                    "category": "TECHNICAL",
                    "resume_evidence": "Built Python services.",
                    "conclusion_key": "Python",
                    "resume_source_id": "resume_section:experience",
                    "job_evidence": "Python required",
                    "confidence": 1.0,
                    "resume_section": "work_experience",
                }
            ],
        ),
    )


@dataclass
class RunOutcome:
    sequence: int
    success: bool
    error_code: str | None = None
    error_message: str | None = None
    workflow_run_id: str | None = None
    latency_ms: int = 0
    attempt_count: int = 0
    retry_count: int = 0
    section_count: int = 0
    keyword_count: int = 0


@dataclass
class SoakReport:
    runs: list[RunOutcome] = field(default_factory=list)

    def add(self, outcome: RunOutcome) -> None:
        self.runs.append(outcome)

    @property
    def total(self) -> int:
        return len(self.runs)

    @property
    def success_count(self) -> int:
        return sum(1 for run in self.runs if run.success)

    @property
    def empty_output_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "DIFY_EMPTY_OUTPUT")

    @property
    def invalid_json_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "DIFY_OUTPUT_INVALID")

    @property
    def http_retryable_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "DIFY_HTTP_RETRYABLE")

    @property
    def timeout_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "DIFY_TIMEOUT")

    @property
    def other_failure_count(self) -> int:
        return sum(
            1
            for run in self.runs
            if not run.success
            and run.error_code
            not in {
                "DIFY_EMPTY_OUTPUT",
                "DIFY_OUTPUT_INVALID",
                "DIFY_HTTP_RETRYABLE",
                "DIFY_TIMEOUT",
            }
        )

    @property
    def total_attempts(self) -> int:
        return sum(run.attempt_count for run in self.runs)

    @property
    def total_retries(self) -> int:
        return sum(run.retry_count for run in self.runs)

    @property
    def success_latencies_ms(self) -> list[int]:
        return [run.latency_ms for run in self.runs if run.success]

    @property
    def average_latency_ms(self) -> float:
        latencies = self.success_latencies_ms
        if not latencies:
            return 0.0
        return statistics.fmean(latencies)

    @property
    def p95_latency_ms(self) -> float:
        latencies = self.success_latencies_ms
        if not latencies:
            return 0.0
        if len(latencies) == 1:
            return float(latencies[0])
        sorted_latencies = sorted(latencies)
        rank = max(1, round(0.95 * len(sorted_latencies)))
        return float(sorted_latencies[min(rank, len(sorted_latencies)) - 1])

    @property
    def acceptance_passed(self) -> bool:
        if self.total < DEFAULT_SOAK_RUNS:
            return self.success_count == self.total and self.total > 0
        return self.success_count >= MIN_ACCEPTANCE_PASSES and self.total > 0

    def failing_runs(self) -> list[RunOutcome]:
        return [run for run in self.runs if not run.success]


def _validate_output_contract(result, request) -> None:
    """Verify anti-fabrication guarantees on a successful Dify response."""
    output = result.output
    workflow_run_id = output.generation.workflow_run_id
    if not workflow_run_id:
        _fail("workflow_run_id was not recorded")
    if output.generation.provider != "dify":
        _fail(f"provider must be 'dify', got '{output.generation.provider}'")

    # Allowed evidence keys are derived from the request sent to Dify.
    allowed_evidence_keys: set[str] = set()
    for item in request.match_report.evidence:
        for field_name in ("resume_evidence", "conclusion_key", "resume_source_id"):
            value = item.get(field_name)
            if isinstance(value, str) and value:
                allowed_evidence_keys.add(value)
    for index in range(1, len(request.resume.skills) + 1):
        allowed_evidence_keys.add(f"resume-evidence-{index}")

    missing_skill_names = {
        str(item.get("normalized_name") or item.get("job_raw_name") or "").lower()
        for item in request.match_report.missing_skills
        if item.get("normalized_name") or item.get("job_raw_name")
    }

    allowed_section_ids = {"summary", "experience-1", "education-1", "skill-1", "skill-2"}

    for section in output.sections:
        if section.source_section_id not in allowed_section_ids:
            _fail(f"source_section_id '{section.source_section_id}' is not in the resume")
        for key in section.evidence_keys:
            if key not in allowed_evidence_keys:
                _fail(f"evidence_key '{key}' does not match any resume evidence")
        lowered_suggested = section.suggested_text.lower()
        lowered_original = section.original_text.lower()
        for name in missing_skill_names:
            if not name:
                continue
            if name in lowered_suggested and name not in lowered_original:
                _fail(
                    f"Missing skill '{name}' must not appear in section "
                    f"'{section.section}' suggested_text"
                )

    for kw in output.keyword_suggestions:
        for key in kw.evidence_keys:
            if key not in allowed_evidence_keys:
                _fail(f"keyword suggestion evidence_key '{key}' does not match any resume evidence")
        if kw.keyword.lower() in missing_skill_names:
            _fail(f"keyword '{kw.keyword}' is a missing skill and cannot be added")


def _run_once(provider, request, sequence: int) -> RunOutcome:
    from app.core.exceptions import AppError

    started = perf_counter()
    try:
        result = provider.generate_optimization(request)
    except AppError as exc:
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code=exc.code,
            error_message=_truncate(exc.message, 200),
            latency_ms=_elapsed_ms(started),
        )
    except Exception as exc:  # pragma: no cover - defensive
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="UNEXPECTED_EXCEPTION",
            error_message=_truncate(type(exc).__name__, 200),
            latency_ms=_elapsed_ms(started),
        )

    latency_ms = _elapsed_ms(started)

    # Sanity check: no API key leakage in attempt metadata.
    for attempt in result.attempts:
        attempt_dump = json.dumps(attempt.model_dump(mode="json"), ensure_ascii=False)
        if "app-" in attempt_dump or "Bearer" in attempt_dump:
            return RunOutcome(
                sequence=sequence,
                success=False,
                error_code="ATTEMPT_METADATA_LEAK",
                error_message="Attempt metadata contained an API key or Authorization header",
                latency_ms=latency_ms,
                attempt_count=len(result.attempts),
                retry_count=sum(1 for a in result.attempts if a.retried),
            )

    # Validate the anti-fabrication contract. Fail fast if Dify returns
    # fabricated content — this is the highest priority guarantee.
    try:
        _validate_output_contract(result, request)
    except SystemExit:
        raise

    retry_count = sum(1 for attempt in result.attempts if attempt.retried)
    return RunOutcome(
        sequence=sequence,
        success=True,
        workflow_run_id=result.output.generation.workflow_run_id,
        latency_ms=latency_ms,
        attempt_count=len(result.attempts),
        retry_count=retry_count,
        section_count=len(result.output.sections),
        keyword_count=len(result.output.keyword_suggestions),
    )


def main() -> None:
    if os.environ.get("RUN_REAL_DIFY_TESTS") != "1":
        print("SKIP: RUN_REAL_DIFY_TESTS is not 1")
        return

    from app.core.config import get_settings
    from app.integrations.dify.resume_optimization_providers import (
        create_resume_optimization_provider,
    )

    settings = get_settings()
    if settings.dify_provider_mode != "dify":
        _fail(f"DIFY_PROVIDER_MODE must be 'dify', got '{settings.dify_provider_mode}'")
    if not settings.dify_base_url:
        _fail("DIFY_BASE_URL is not set")
    if not settings.dify_resume_optimization_api_key:
        _fail("DIFY_RESUME_OPTIMIZATION_API_KEY is not set")

    try:
        soak_runs = int(os.environ.get("DIFY_SOAK_RUNS", str(DEFAULT_SOAK_RUNS)))
    except ValueError:
        soak_runs = DEFAULT_SOAK_RUNS
    if soak_runs < 1:
        _fail(f"DIFY_SOAK_RUNS must be >= 1, got {soak_runs}")

    request = _build_request()
    provider = create_resume_optimization_provider(settings)

    print(f"Running Dify resume optimization smoke test: {soak_runs} run(s)")

    report = SoakReport()
    for sequence in range(1, soak_runs + 1):
        outcome = _run_once(provider, request, sequence)
        report.add(outcome)
        status_label = "OK" if outcome.success else f"FAIL({outcome.error_code})"
        workflow_label = outcome.workflow_run_id or "-"
        print(
            f"  run {sequence:>2}/{soak_runs}: {status_label} "
            f"latency={outcome.latency_ms}ms attempts={outcome.attempt_count} "
            f"retries={outcome.retry_count} workflow_run_id={workflow_label}"
        )

    print()
    print("== Dify resume optimization summary ==")
    print(f"  total_runs: {report.total}")
    print(f"  success: {report.success_count}")
    print(f"  empty_output (DIFY_EMPTY_OUTPUT): {report.empty_output_count}")
    print(f"  invalid_json (DIFY_OUTPUT_INVALID): {report.invalid_json_count}")
    print(f"  http_retryable (429/502/503/504): {report.http_retryable_count}")
    print(f"  timeout (DIFY_TIMEOUT): {report.timeout_count}")
    print(f"  other_failures: {report.other_failure_count}")
    print(f"  total_provider_attempts: {report.total_attempts}")
    print(f"  total_auto_retries: {report.total_retries}")
    print(f"  average_latency_ms: {report.average_latency_ms:.1f}")
    print(f"  p95_latency_ms: {report.p95_latency_ms:.1f}")

    failing = report.failing_runs()
    if failing:
        print()
        print("  failing runs (workflow_run_id for Dify trace, no API key):")
        for outcome in failing:
            run_id = outcome.workflow_run_id or "<none>"
            print(
                f"    run {outcome.sequence}: error={outcome.error_code} "
                f"workflow_run_id={run_id} message={outcome.error_message}"
            )

    if report.acceptance_passed:
        print()
        if soak_runs == 1:
            print("PASS: Dify real resume optimization smoke test")
        else:
            print(
                f"PASS: {report.success_count}/{report.total} runs succeeded "
                f"(>= {MIN_ACCEPTANCE_PASSES} required)"
            )
        # Show the first successful output for inspection.
        first_success = next((run for run in report.runs if run.success), None)
        if first_success is not None and soak_runs == 1:
            print(
                f"  workflow_run_id: {first_success.workflow_run_id}  "
                f"sections: {first_success.section_count}  "
                f"keywords: {first_success.keyword_count}  "
                f"latency_ms: {first_success.latency_ms}"
            )
        return

    print()
    if soak_runs == 1:
        _fail("Dify real resume optimization smoke test failed")
    else:
        _fail(
            f"only {report.success_count}/{report.total} runs succeeded; "
            f"acceptance requires >= {MIN_ACCEPTANCE_PASSES}"
        )


if __name__ == "__main__":
    main()
