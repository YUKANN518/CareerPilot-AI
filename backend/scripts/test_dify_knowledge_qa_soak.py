"""Real Dify knowledge QA stability (smoke) test.

Runs the same knowledge QA request N times against a real Dify Workflow
endpoint and reports stability statistics. Mirrors ``test_dify_soak.py``
but exercises the ``DifyKnowledgeQAProvider`` through the career assistant
plan provider.

Acceptance targets:

- 10/10 or at least 9/10 final calls succeed
- no unhandled empty outputs
- each success has a workflow_run_id
- each success passes Pydantic validation
- no API key leakage in attempt metadata

Only runs when ``RUN_REAL_DIFY_TESTS=1``. The number of runs can be tuned
via ``DIFY_SOAK_RUNS`` (default 10)::

    RUN_REAL_DIFY_TESTS=1 DIFY_SOAK_RUNS=10 \
    DIFY_PROVIDER_MODE=dify \
    DIFY_BASE_URL=http://localhost/v1 \
    DIFY_KNOWLEDGE_QA_API_KEY=<your-key> \
    python scripts/test_dify_knowledge_qa_soak.py

The script never logs API keys or Authorization headers.
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

DEFAULT_SOAK_RUNS = 10
MIN_ACCEPTANCE_PASSES = 9


@dataclass
class QAOutcome:
    sequence: int
    success: bool
    error_code: str | None = None
    error_message: str | None = None
    workflow_run_id: str | None = None
    latency_ms: int = 0
    attempt_count: int = 0
    retry_count: int = 0
    citation_count: int = 0
    answer_length: int = 0


@dataclass
class QASoakReport:
    runs: list[QAOutcome] = field(default_factory=list)

    def add(self, outcome: QAOutcome) -> None:
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
    def empty_result_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "DIFY_EMPTY_RESULT")

    @property
    def invalid_json_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "DIFY_INVALID_JSON")

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
                "DIFY_EMPTY_RESULT",
                "DIFY_INVALID_JSON",
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
        return self.success_count >= MIN_ACCEPTANCE_PASSES and self.total > 0

    def failing_runs(self) -> list[QAOutcome]:
        return [run for run in self.runs if not run.success]


def _fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def _build_request():
    from app.schemas.career_assistant import (
        KnowledgeQAContextChunk,
        KnowledgeQAWorkflowInput,
        PersonalContextChunk,
    )

    # Stage 4B: include personal_context so the request uses the elevated
    # ``career-assistant-personalized-input-v1`` schema_version. This
    # verifies the Dify workflow can handle personalised QA input that
    # references the user's private data (resume, match reports, etc.).
    request = KnowledgeQAWorkflowInput(
        user_id=1,
        question="What backend engineer experience does the candidate have?",
        context_chunks=[
            KnowledgeQAContextChunk(
                document_id=1,
                title="Career Knowledge Guide",
                category="guide",
                chunk_text=(
                    "Backend engineer building reliable web services using "
                    "Python, FastAPI and SQLAlchemy."
                ),
                chunk_index=0,
                page_number=1,
                paragraph_index=0,
                score=0.85,
            ),
            KnowledgeQAContextChunk(
                document_id=1,
                title="Career Knowledge Guide",
                category="guide",
                chunk_text=(
                    "Skills: Python, FastAPI, SQLAlchemy, SQLite, Vue, TypeScript, Communication."
                ),
                chunk_index=1,
                page_number=1,
                paragraph_index=1,
                score=0.78,
            ),
        ],
        personal_context=[
            PersonalContextChunk(
                source_type="resume",
                source_id=1,
                title="My Resume",
                category="experience",
                chunk_text=(
                    "3 years of backend engineering experience building "
                    "REST APIs with Python and FastAPI."
                ),
                chunk_index=0,
            ),
            PersonalContextChunk(
                source_type="match_report",
                source_id=1,
                title="Match Report - Backend Engineer",
                category="match",
                chunk_text=(
                    "Matched at 87% - strong alignment on Python, FastAPI and SQLAlchemy skills."
                ),
                chunk_index=0,
            ),
        ],
    )
    # Mirror the service-layer elevation: when personal_context is
    # non-empty, production elevates schema_version to
    # ``career-assistant-personalized-input-v1``. This verifies the
    # Dify workflow can handle personalised QA input that references
    # the user's private data (resume, match reports, etc.).
    return request.model_copy(update={"schema_version": "career-assistant-personalized-input-v1"})


def _run_once(provider, request, sequence: int) -> QAOutcome:
    from app.core.exceptions import AppError

    started = perf_counter()
    try:
        result = provider.answer_question(request)
    except AppError as exc:
        return QAOutcome(
            sequence=sequence,
            success=False,
            error_code=exc.code,
            error_message=_truncate(exc.message, 200),
            latency_ms=_elapsed_ms(started),
        )
    except Exception as exc:  # pragma: no cover - defensive
        return QAOutcome(
            sequence=sequence,
            success=False,
            error_code="UNEXPECTED_EXCEPTION",
            error_message=_truncate(type(exc).__name__, 200),
            latency_ms=_elapsed_ms(started),
        )

    latency_ms = _elapsed_ms(started)
    workflow_run_id = result.output.generation.workflow_run_id
    if not workflow_run_id:
        return QAOutcome(
            sequence=sequence,
            success=False,
            error_code="MISSING_WORKFLOW_RUN_ID",
            error_message="Provider returned success but workflow_run_id was empty",
            latency_ms=latency_ms,
            attempt_count=len(result.attempts),
            retry_count=sum(1 for a in result.attempts if a.retried),
        )

    retry_count = sum(1 for attempt in result.attempts if attempt.retried)

    # Sanity check: no API key leakage in attempt metadata.
    for attempt in result.attempts:
        attempt_dump = json.dumps(attempt.model_dump(mode="json"), ensure_ascii=False)
        if "app-" in attempt_dump or "Bearer" in attempt_dump:
            return QAOutcome(
                sequence=sequence,
                success=False,
                error_code="ATTEMPT_METADATA_LEAK",
                error_message="Attempt metadata contained an API key or Authorization header",
                latency_ms=latency_ms,
                attempt_count=len(result.attempts),
                retry_count=retry_count,
            )

    return QAOutcome(
        sequence=sequence,
        success=True,
        workflow_run_id=workflow_run_id,
        latency_ms=latency_ms,
        attempt_count=len(result.attempts),
        retry_count=retry_count,
        citation_count=len(result.output.used_citation_keys),
        answer_length=len(result.output.answer),
    )


def _elapsed_ms(started: float) -> int:
    return max(round((perf_counter() - started) * 1000), 0)


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def main() -> None:
    if os.environ.get("RUN_REAL_DIFY_TESTS") != "1":
        print("SKIP: RUN_REAL_DIFY_TESTS is not 1")
        return

    from app.core.config import get_settings
    from app.integrations.dify.knowledge_qa_providers import (
        create_knowledge_qa_provider,
    )

    settings = get_settings()
    if settings.dify_provider_mode != "dify":
        _fail(f"DIFY_PROVIDER_MODE must be 'dify', got '{settings.dify_provider_mode}'")
    if not settings.dify_base_url:
        _fail("DIFY_BASE_URL is not set")
    if not settings.dify_knowledge_qa_api_key:
        _fail("DIFY_KNOWLEDGE_QA_API_KEY is not set")

    try:
        soak_runs = int(os.environ.get("DIFY_SOAK_RUNS", str(DEFAULT_SOAK_RUNS)))
    except ValueError:
        soak_runs = DEFAULT_SOAK_RUNS
    if soak_runs < 1:
        _fail(f"DIFY_SOAK_RUNS must be >= 1, got {soak_runs}")

    request = _build_request()
    provider = create_knowledge_qa_provider(settings)

    print(f"Running Dify knowledge QA soak test: {soak_runs} run(s)")
    print(f"  question: {request.question}")
    print(f"  context_chunks: {len(request.context_chunks)}")
    print(f"  personal_context: {len(request.personal_context)}")
    print(f"  schema_version: {request.schema_version}")

    report = QASoakReport()
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
    print("== Dify knowledge QA soak summary ==")
    print(f"  total_runs: {report.total}")
    print(f"  success: {report.success_count}")
    print(f"  empty_output (DIFY_EMPTY_OUTPUT): {report.empty_output_count}")
    print(f"  empty_result (DIFY_EMPTY_RESULT): {report.empty_result_count}")
    print(f"  invalid_json (DIFY_INVALID_JSON): {report.invalid_json_count}")
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
        print(
            f"PASS: {report.success_count}/{report.total} runs succeeded "
            f"(>= {MIN_ACCEPTANCE_PASSES} required)"
        )
        return

    print()
    _fail(
        f"ACCEPTANCE FAILED: only {report.success_count}/{report.total} runs succeeded "
        f"(>= {MIN_ACCEPTANCE_PASSES} required)"
    )


if __name__ == "__main__":
    main()
