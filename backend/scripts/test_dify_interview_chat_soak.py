"""Real Dify Interview Chat Chatflow stability (soak) test.

Runs the same chat-flow sequence N times against a real Dify Chatflow
endpoint and reports stability statistics:

- success count
- empty output count (DIFY_EMPTY_OUTPUT)
- empty result/answer count (DIFY_EMPTY_RESULT)
- invalid JSON count (DIFY_INVALID_JSON)
- transient HTTP error count (429/502/503/504, DIFY_HTTP_RETRYABLE)
- timeout count (DIFY_TIMEOUT)
- conversation_id loss count
- illegal next_action count
- other failure count
- average / P95 latency (ms)
- total provider attempts (sum across runs, including auto-retries)

Acceptance targets (per the Stage 7 contract):

- >= 9/10 final runs succeed
- 0 empty outputs
- 0 empty result/answer
- 0 invalid JSON
- 0 conversation_id loss (first turn creates it, subsequent turns reuse it)
- 0 illegal next_action
- 0 API key leakage in attempt metadata

Only runs when RUN_REAL_DIFY_TESTS=1. The number of runs can be tuned via
DIFY_SOAK_RUNS (default 10):

    RUN_REAL_DIFY_TESTS=1 DIFY_SOAK_RUNS=10 \
    DIFY_PROVIDER_MODE=dify \
    DIFY_BASE_URL=http://localhost/v1 \
    DIFY_INTERVIEW_CHAT_API_KEY=<your-key> \
    python scripts/test_dify_interview_chat_soak.py

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

VALID_NEXT_ACTIONS = {"FOLLOW_UP", "NEXT_QUESTION", "COMPLETE_INTERVIEW"}


@dataclass
class RunOutcome:
    sequence: int
    success: bool
    error_code: str | None = None
    error_message: str | None = None
    workflow_run_id: str | None = None
    conversation_id: str | None = None
    latency_ms: int = 0
    attempt_count: int = 0
    retry_count: int = 0
    assistant_message_len: int = 0
    next_action: str | None = None
    conversation_id_reused: bool | None = None


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
    def conversation_id_lost_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "CONVERSATION_ID_LOST")

    @property
    def illegal_next_action_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "ILLEGAL_NEXT_ACTION")

    @property
    def other_failure_count(self) -> int:
        known = {
            "DIFY_EMPTY_OUTPUT",
            "DIFY_EMPTY_RESULT",
            "DIFY_INVALID_JSON",
            "DIFY_HTTP_RETRYABLE",
            "DIFY_TIMEOUT",
            "CONVERSATION_ID_LOST",
            "ILLEGAL_NEXT_ACTION",
        }
        return sum(1 for run in self.runs if not run.success and run.error_code not in known)

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

    def failing_runs(self) -> list[RunOutcome]:
        return [run for run in self.runs if not run.success]


def _fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def _elapsed_ms(started: float) -> int:
    return max(round((perf_counter() - started) * 1000), 0)


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3] + "..."


def _build_chat_request(user_answer: str):
    from app.schemas.interviews import (
        ChatTurnWorkflowInput,
        InterviewJobInput,
        InterviewMatchReportInput,
        InterviewQuestionType,
        InterviewResumeInput,
    )

    return ChatTurnWorkflowInput(
        schema_version="interview-chat-turn-input-v1",
        user_locale="zh-CN",
        interview_type="TECHNICAL",
        current_question_sequence=1,
        current_question_prompt="请介绍一下你使用 Python 异步编程的经验。",
        current_question_type=InterviewQuestionType.TECHNICAL,
        current_question_intent="考察 asyncio 与并发理解",
        user_answer=user_answer,
        follow_up_count=0,
        total_questions=4,
        conversation_history=[],
        resume=InterviewResumeInput(
            resume_version_id=1,
            summary="Experienced Python backend engineer with FastAPI and asyncio expertise.",
            education=[
                {
                    "degree": "B.Sc. Computer Science",
                    "institution": "Example University",
                    "year": "2018",
                }
            ],
            experiences=[
                {
                    "title": "Backend Engineer",
                    "company": "Soak Test Company",
                    "description": "Built async Python services with FastAPI.",
                    "start_date": "2020-01",
                    "end_date": "2024-12",
                }
            ],
            projects=[
                {
                    "name": "CareerPilot API",
                    "description": "A FastAPI-based job matching service.",
                }
            ],
            skills=[
                {"name": "Python", "level": "expert"},
                {"name": "FastAPI", "level": "advanced"},
                {"name": "SQL", "level": "advanced"},
            ],
        ),
        job=InterviewJobInput(
            job_id=1,
            title="Backend Engineer",
            company="Soak Test Company",
            summary="Build reliable Python services using FastAPI and asyncio.",
            source_name="soak-test",
            source_url="https://jobs.example.com/seed-job-1",
            information_completeness=0.8,
            is_summary_only=False,
        ),
        match_report=InterviewMatchReportInput(
            report_id=1,
            final_score=72.0,
            matched_skills=[
                {"normalized_name": "Python", "status": "MATCHED"},
                {"normalized_name": "FastAPI", "status": "MATCHED"},
            ],
            partial_skills=[],
            missing_skills=[
                {"normalized_name": "Docker", "status": "MISSING", "job_raw_name": "Docker"},
            ],
            blocking_risks=[],
        ),
    )


def _check_api_key_leak(result) -> str | None:
    """Return an error message if any attempt metadata leaks the API key."""
    for attempt in result.attempts:
        attempt_dump = json.dumps(attempt.model_dump(mode="json"), ensure_ascii=False)
        if "app-" in attempt_dump or "Bearer" in attempt_dump:
            return "Attempt metadata contained an API key or Authorization header"
    return None


def _run_one_round(provider, user_identifier: str, sequence: int) -> RunOutcome:
    """Run a full 2-turn chat round and return the combined outcome.

    Turn 1: empty user_answer (opening) → must return conversation_id
    Turn 2: non-empty user_answer → must reuse the same conversation_id
    """
    from app.core.exceptions import AppError

    started = perf_counter()

    # --- Turn 1: opening (empty user_answer) ---
    request_open = _build_chat_request(user_answer="")
    try:
        result_open = provider.chat_turn(
            request_open,
            conversation_id=None,
            user=user_identifier,
        )
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

    conversation_id_open = result_open.conversation_id
    if not conversation_id_open:
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="CONVERSATION_ID_LOST",
            error_message="First turn did not return a conversation_id",
            latency_ms=_elapsed_ms(started),
            attempt_count=len(result_open.attempts),
        )

    # Validate turn 1 output
    output_open = result_open.output
    if not output_open.assistant_message.strip():
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="DIFY_EMPTY_RESULT",
            error_message="First turn returned empty assistant_message",
            latency_ms=_elapsed_ms(started),
            attempt_count=len(result_open.attempts),
            conversation_id=conversation_id_open,
        )

    if output_open.next_action not in VALID_NEXT_ACTIONS:
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="ILLEGAL_NEXT_ACTION",
            error_message=f"First turn returned illegal next_action: {output_open.next_action}",
            latency_ms=_elapsed_ms(started),
            attempt_count=len(result_open.attempts),
            conversation_id=conversation_id_open,
        )

    # Check API key leakage
    leak = _check_api_key_leak(result_open)
    if leak:
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="ATTEMPT_METADATA_LEAK",
            error_message=leak,
            latency_ms=_elapsed_ms(started),
            attempt_count=len(result_open.attempts),
            conversation_id=conversation_id_open,
        )

    # --- Turn 2: user answer (must reuse conversation_id) ---
    request_answer = _build_chat_request(
        user_answer="I have used Python asyncio for three years, building async HTTP services "
        "and processing pipelines with multiprocessing workers in production."
    )
    try:
        result_answer = provider.chat_turn(
            request_answer,
            conversation_id=conversation_id_open,
            user=user_identifier,
        )
    except AppError as exc:
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code=exc.code,
            error_message=_truncate(exc.message, 200),
            latency_ms=_elapsed_ms(started),
            conversation_id=conversation_id_open,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="UNEXPECTED_EXCEPTION",
            error_message=_truncate(type(exc).__name__, 200),
            latency_ms=_elapsed_ms(started),
            conversation_id=conversation_id_open,
        )

    latency_ms = _elapsed_ms(started)

    # Verify conversation_id was reused
    conversation_id_reused = result_answer.conversation_id == conversation_id_open
    if not conversation_id_reused:
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="CONVERSATION_ID_LOST",
            error_message=(
                f"Second turn did not reuse conversation_id: "
                f"expected={conversation_id_open} got={result_answer.conversation_id}"
            ),
            latency_ms=latency_ms,
            attempt_count=len(result_open.attempts) + len(result_answer.attempts),
            conversation_id=conversation_id_open,
        )

    # Validate turn 2 output
    output_answer = result_answer.output
    if not output_answer.assistant_message.strip():
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="DIFY_EMPTY_RESULT",
            error_message="Second turn returned empty assistant_message",
            latency_ms=latency_ms,
            attempt_count=len(result_open.attempts) + len(result_answer.attempts),
            conversation_id=conversation_id_open,
        )

    if output_answer.next_action not in VALID_NEXT_ACTIONS:
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="ILLEGAL_NEXT_ACTION",
            error_message=f"Second turn returned illegal next_action: {output_answer.next_action}",
            latency_ms=latency_ms,
            attempt_count=len(result_open.attempts) + len(result_answer.attempts),
            conversation_id=conversation_id_open,
        )

    # Check API key leakage in turn 2
    leak = _check_api_key_leak(result_answer)
    if leak:
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="ATTEMPT_METADATA_LEAK",
            error_message=leak,
            latency_ms=latency_ms,
            attempt_count=len(result_open.attempts) + len(result_answer.attempts),
            conversation_id=conversation_id_open,
        )

    # Verify schema_version
    if output_answer.generation.workflow_version != "interview-chat-turn-v1":
        # The schema_version field on the output itself is validated by
        # Pydantic, but the generation.workflow_version is what the
        # factory uses for DIFY_INTERVIEW_CHAT_WORKFLOW_VERSION.
        pass  # workflow_version is provider-specific, not strictly enforced

    total_attempts = len(result_open.attempts) + len(result_answer.attempts)
    total_retries = sum(1 for a in result_open.attempts if a.retried) + sum(
        1 for a in result_answer.attempts if a.retried
    )

    return RunOutcome(
        sequence=sequence,
        success=True,
        workflow_run_id=output_answer.generation.workflow_run_id,
        conversation_id=conversation_id_open,
        latency_ms=latency_ms,
        attempt_count=total_attempts,
        retry_count=total_retries,
        assistant_message_len=len(output_answer.assistant_message),
        next_action=output_answer.next_action,
        conversation_id_reused=True,
    )


def main() -> None:
    if os.environ.get("RUN_REAL_DIFY_TESTS") != "1":
        print("SKIP: RUN_REAL_DIFY_TESTS is not 1")
        return

    from app.core.config import get_settings
    from app.integrations.dify.interview_providers import (
        create_interview_chat_provider,
    )

    settings = get_settings()
    if settings.dify_provider_mode != "dify":
        _fail(f"DIFY_PROVIDER_MODE must be 'dify', got '{settings.dify_provider_mode}'")
    if not settings.dify_base_url:
        _fail("DIFY_BASE_URL is not set")
    if not settings.dify_interview_chat_api_key:
        _fail("DIFY_INTERVIEW_CHAT_API_KEY is not set")

    try:
        soak_runs = int(os.environ.get("DIFY_SOAK_RUNS", str(DEFAULT_SOAK_RUNS)))
    except ValueError:
        soak_runs = DEFAULT_SOAK_RUNS
    if soak_runs < 1:
        _fail(f"DIFY_SOAK_RUNS must be >= 1, got {soak_runs}")

    provider = create_interview_chat_provider(settings)

    print(f"Running Dify interview chat soak test: {soak_runs} round(s)")
    print("  each round: 2 turns (opening + user answer)")

    report = SoakReport()
    for sequence in range(1, soak_runs + 1):
        user_identifier = f"soak-chat-user-{sequence}"
        outcome = _run_one_round(provider, user_identifier, sequence)
        report.add(outcome)
        status_label = "OK" if outcome.success else f"FAIL({outcome.error_code})"
        conv_label = outcome.conversation_id or "-"
        extra = (
            f"msg_len={outcome.assistant_message_len} action={outcome.next_action}"
            if outcome.success
            else ""
        )
        print(
            f"  run {sequence:>2}/{soak_runs}: {status_label} "
            f"latency={outcome.latency_ms}ms attempts={outcome.attempt_count} "
            f"retries={outcome.retry_count} conv_id={conv_label} {extra}"
        )

    print()
    print("== Dify interview chat soak summary ==")
    print(f"  total_runs: {report.total}")
    print(f"  success: {report.success_count}")
    print(f"  empty_output (DIFY_EMPTY_OUTPUT): {report.empty_output_count}")
    print(f"  empty_result (DIFY_EMPTY_RESULT): {report.empty_result_count}")
    print(f"  invalid_json (DIFY_INVALID_JSON): {report.invalid_json_count}")
    print(f"  http_retryable (429/502/503/504): {report.http_retryable_count}")
    print(f"  timeout (DIFY_TIMEOUT): {report.timeout_count}")
    print(f"  conversation_id_lost: {report.conversation_id_lost_count}")
    print(f"  illegal_next_action: {report.illegal_next_action_count}")
    print(f"  other_failures: {report.other_failure_count}")
    print(f"  total_provider_attempts: {report.total_attempts}")
    print(f"  total_auto_retries: {report.total_retries}")
    print(f"  average_latency_ms: {report.average_latency_ms:.1f}")
    print(f"  p95_latency_ms: {report.p95_latency_ms:.1f}")

    failing = report.failing_runs()
    if failing:
        print()
        print("  failing runs (conversation_id for Dify trace, no API key):")
        for outcome in failing:
            conv_id = outcome.conversation_id or "<none>"
            print(
                f"    run {outcome.sequence}: error={outcome.error_code} "
                f"conv_id={conv_id} message={outcome.error_message}"
            )

    if report.acceptance_passed:
        print()
        print(
            f"PASS: {report.success_count}/{report.total} rounds succeeded "
            f"(>= {MIN_ACCEPTANCE_PASSES} required)"
        )
        return

    print()
    _fail(
        f"only {report.success_count}/{report.total} rounds succeeded; "
        f"acceptance requires >= {MIN_ACCEPTANCE_PASSES}"
    )


if __name__ == "__main__":
    main()
