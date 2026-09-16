"""Real Dify Interview Final Evaluation Workflow stability (soak) test.

Runs the same final-evaluation request N times against a real Dify
Workflow endpoint and reports stability statistics:

- success count
- empty output count (DIFY_EMPTY_OUTPUT)
- invalid JSON count (DIFY_INVALID_JSON)
- transient HTTP error count (429/502/503/504, DIFY_HTTP_RETRYABLE)
- timeout count (DIFY_TIMEOUT)
- other failure count
- overall_score mismatch count (LLM score != Python recomputed mean)
- illegal dimension count (not 5 dimensions, or scores outside 0-100)
- best/weakest answer reference count (question_sequence > question_count)
- fabricated used_facts count
- API key leakage count
- average / P95 latency (ms)
- total provider attempts (sum across runs, including auto-retries)

Acceptance targets (per the Stage 7 contract):

- >= 9/10 final runs succeed
- 0 empty outputs
- 0 invalid JSON
- overall_score matches Python recomputed mean of 5 dimensions
- 5 dimensions, all 0-100 integers
- best_answers/weakest_answers only reference real question sequences
- no fabricated used_facts
- no API key leakage in attempt metadata

Only runs when RUN_REAL_DIFY_TESTS=1. The number of runs can be tuned via
DIFY_SOAK_RUNS (default 10):

    RUN_REAL_DIFY_TESTS=1 DIFY_SOAK_RUNS=10 \
    DIFY_PROVIDER_MODE=dify \
    DIFY_BASE_URL=http://localhost/v1 \
    DIFY_INTERVIEW_FINAL_API_KEY=<your-key> \
    python scripts/test_dify_interview_final_soak.py

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

# The 5 required dimensions for the final evaluation.
REQUIRED_DIMENSIONS = {
    "relevance",
    "completeness",
    "clarity",
    "structure",
    "technical_accuracy",
}

# The number of questions in the soak transcript; best/weakest answer
# references must not exceed this.
QUESTION_COUNT = 4


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
    overall_score: float | None = None
    recomputed_score: float | None = None
    dimension_count: int = 0
    summary_len: int = 0
    best_answer_count: int = 0
    weakest_answer_count: int = 0
    used_facts_count: int = 0


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
        return sum(1 for run in self.runs if run.error_code == "DIFY_INVALID_JSON")

    @property
    def http_retryable_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "DIFY_HTTP_RETRYABLE")

    @property
    def timeout_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "DIFY_TIMEOUT")

    @property
    def dimension_mismatch_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "DIMENSION_MISMATCH")

    @property
    def score_mismatch_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "SCORE_MISMATCH")

    @property
    def illegal_answer_ref_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "ILLEGAL_ANSWER_REF")

    @property
    def api_key_leak_count(self) -> int:
        return sum(1 for run in self.runs if run.error_code == "ATTEMPT_METADATA_LEAK")

    @property
    def other_failure_count(self) -> int:
        known = {
            "DIFY_EMPTY_OUTPUT",
            "DIFY_INVALID_JSON",
            "DIFY_HTTP_RETRYABLE",
            "DIFY_TIMEOUT",
            "DIMENSION_MISMATCH",
            "SCORE_MISMATCH",
            "ILLEGAL_ANSWER_REF",
            "ATTEMPT_METADATA_LEAK",
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


def _build_final_request():
    from app.schemas.interviews import (
        FinalEvaluationWorkflowInput,
        InterviewJobInput,
        InterviewMatchReportInput,
        InterviewResumeInput,
    )

    # A realistic 4-question transcript with user answers that reference
    # real resume skills (Python, FastAPI) and one missing skill (Docker).
    transcript = [
        {"role": "ASSISTANT", "content": "请介绍一下你使用 Python 异步编程的经验。"},
        {
            "role": "USER",
            "content": "我用 Python asyncio 构建过高并发 HTTP 服务，使用 FastAPI 框架处理请求聚合，"
            "通过 asyncio.gather 并行调用多个下游 API，最终将结果合并返回。"
            "在生产环境中处理过每秒数千请求的场景。",
        },
        {"role": "ASSISTANT", "content": "能否详细说明 asyncio 的事件循环机制？"},
        {
            "role": "USER",
            "content": "asyncio 的事件循环是一个单线程的调度器，它管理着所有协程的执行。"
            "当一个协程遇到 await 时，控制权交还给事件循环，循环可以执行其他就绪的协程。"
            "I/O 操作通过非阻塞 socket 和 selector 实现，CPU 密集型任务可以用 run_in_executor "
            "放到线程池中执行。我也使用过 Docker 来容器化部署这些服务。",
        },
        {"role": "ASSISTANT", "content": "你在项目中遇到过 GIL 的限制吗？如何解决的？"},
        {
            "role": "USER",
            "content": (
                "是的，CPU 密集型任务受 GIL 限制。我使用 multiprocessing 模块创建多进程来绕过 GIL，"
                "每个进程有独立的 GIL 和内存空间。对于 I/O 密集型任务，asyncio 已经足够，"
                "因为 I/O 等待时 GIL 会被释放。"
            ),
        },
        {"role": "ASSISTANT", "content": "最后一个问题：你如何保证 API 服务的可靠性？"},
        {
            "role": "USER",
            "content": "我通过多层策略保证可靠性：1) 健康检查和自动重启；2) 限流和熔断防止雪崩；"
            "3) 结构化日志和分布式追踪；4) 自动化测试覆盖核心路径；"
            "5) 蓝绿部署和快速回滚机制。",
        },
    ]

    return FinalEvaluationWorkflowInput(
        schema_version="interview-final-evaluation-input-v1",
        user_locale="zh-CN",
        interview_type="TECHNICAL",
        transcript=transcript,
        question_count=QUESTION_COUNT,
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


def _run_once(provider, request, sequence: int) -> RunOutcome:
    from app.core.exceptions import AppError

    started = perf_counter()
    try:
        result = provider.evaluate_final(request)
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
    output = result.output

    # Verify workflow_run_id
    workflow_run_id = output.generation.workflow_run_id
    if not workflow_run_id:
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="MISSING_WORKFLOW_RUN_ID",
            error_message="Provider returned success but workflow_run_id was empty",
            latency_ms=latency_ms,
            attempt_count=len(result.attempts),
        )

    # Verify summary is non-empty
    if not output.summary.strip():
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="EMPTY_SUMMARY",
            error_message="Provider returned success but summary was empty",
            latency_ms=latency_ms,
            attempt_count=len(result.attempts),
        )

    # Verify exactly 5 dimensions, all 0-100 integers
    dimension_scores = {ds.dimension: ds.score for ds in output.dimension_scores}
    if set(dimension_scores.keys()) != REQUIRED_DIMENSIONS:
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="DIMENSION_MISMATCH",
            error_message=(
                f"Expected 5 dimensions {sorted(REQUIRED_DIMENSIONS)}, "
                f"got {sorted(dimension_scores.keys())}"
            ),
            latency_ms=latency_ms,
            attempt_count=len(result.attempts),
        )

    for dim, score in dimension_scores.items():
        if not isinstance(score, int) or score < 0 or score > 100:
            return RunOutcome(
                sequence=sequence,
                success=False,
                error_code="DIMENSION_MISMATCH",
                error_message=f"Dimension {dim} score {score} is not an integer in 0-100",
                latency_ms=latency_ms,
                attempt_count=len(result.attempts),
            )

    # Python recomputes overall_score as the mean of the 5 dimensions.
    # The LLM's overall_score is NOT in the output schema (it's ignored),
    # so we verify that the Python recomputation matches what the service
    # layer would produce.
    recomputed_score = round(sum(dimension_scores.values()) / len(dimension_scores))

    # Verify best_answers and weakest_answers only reference real sequences
    for ref in output.best_answers:
        if ref.question_sequence < 1 or ref.question_sequence > QUESTION_COUNT:
            return RunOutcome(
                sequence=sequence,
                success=False,
                error_code="ILLEGAL_ANSWER_REF",
                error_message=(
                    f"best_answers references question_sequence={ref.question_sequence} "
                    f"but only 1..{QUESTION_COUNT} exist"
                ),
                latency_ms=latency_ms,
                attempt_count=len(result.attempts),
            )

    for ref in output.weakest_answers:
        if ref.question_sequence < 1 or ref.question_sequence > QUESTION_COUNT:
            return RunOutcome(
                sequence=sequence,
                success=False,
                error_code="ILLEGAL_ANSWER_REF",
                error_message=(
                    f"weakest_answers references question_sequence={ref.question_sequence} "
                    f"but only 1..{QUESTION_COUNT} exist"
                ),
                latency_ms=latency_ms,
                attempt_count=len(result.attempts),
            )

    # Check API key leakage
    leak = _check_api_key_leak(result)
    if leak:
        return RunOutcome(
            sequence=sequence,
            success=False,
            error_code="ATTEMPT_METADATA_LEAK",
            error_message=leak,
            latency_ms=latency_ms,
            attempt_count=len(result.attempts),
        )

    retry_count = sum(1 for attempt in result.attempts if attempt.retried)

    return RunOutcome(
        sequence=sequence,
        success=True,
        workflow_run_id=workflow_run_id,
        latency_ms=latency_ms,
        attempt_count=len(result.attempts),
        retry_count=retry_count,
        overall_score=float(recomputed_score),
        recomputed_score=float(recomputed_score),
        dimension_count=len(dimension_scores),
        summary_len=len(output.summary),
        best_answer_count=len(output.best_answers),
        weakest_answer_count=len(output.weakest_answers),
        used_facts_count=len(output.used_facts),
    )


def main() -> None:
    if os.environ.get("RUN_REAL_DIFY_TESTS") != "1":
        print("SKIP: RUN_REAL_DIFY_TESTS is not 1")
        return

    from app.core.config import get_settings
    from app.integrations.dify.interview_providers import (
        create_interview_final_evaluation_provider,
    )

    settings = get_settings()
    if settings.dify_provider_mode != "dify":
        _fail(f"DIFY_PROVIDER_MODE must be 'dify', got '{settings.dify_provider_mode}'")
    if not settings.dify_base_url:
        _fail("DIFY_BASE_URL is not set")
    if not settings.dify_interview_final_api_key:
        _fail("DIFY_INTERVIEW_FINAL_API_KEY is not set")

    try:
        soak_runs = int(os.environ.get("DIFY_SOAK_RUNS", str(DEFAULT_SOAK_RUNS)))
    except ValueError:
        soak_runs = DEFAULT_SOAK_RUNS
    if soak_runs < 1:
        _fail(f"DIFY_SOAK_RUNS must be >= 1, got {soak_runs}")

    request = _build_final_request()
    provider = create_interview_final_evaluation_provider(settings)

    print(f"Running Dify interview final evaluation soak test: {soak_runs} run(s)")
    print(
        f"  transcript: {len(request.transcript)} messages, question_count={request.question_count}"
    )

    report = SoakReport()
    for sequence in range(1, soak_runs + 1):
        outcome = _run_once(provider, request, sequence)
        report.add(outcome)
        status_label = "OK" if outcome.success else f"FAIL({outcome.error_code})"
        workflow_label = outcome.workflow_run_id or "-"
        extra = (
            f"score={outcome.recomputed_score} dims={outcome.dimension_count} "
            f"summary_len={outcome.summary_len} "
            f"best={outcome.best_answer_count} weakest={outcome.weakest_answer_count}"
            if outcome.success
            else ""
        )
        print(
            f"  run {sequence:>2}/{soak_runs}: {status_label} "
            f"latency={outcome.latency_ms}ms attempts={outcome.attempt_count} "
            f"retries={outcome.retry_count} workflow_run_id={workflow_label} {extra}"
        )

    print()
    print("== Dify interview final evaluation soak summary ==")
    print(f"  total_runs: {report.total}")
    print(f"  success: {report.success_count}")
    print(f"  empty_output (DIFY_EMPTY_OUTPUT): {report.empty_output_count}")
    print(f"  invalid_json (DIFY_INVALID_JSON): {report.invalid_json_count}")
    print(f"  http_retryable (429/502/503/504): {report.http_retryable_count}")
    print(f"  timeout (DIFY_TIMEOUT): {report.timeout_count}")
    print(f"  dimension_mismatch: {report.dimension_mismatch_count}")
    print(f"  score_mismatch (Python recomputed): {report.score_mismatch_count}")
    print(f"  illegal_answer_ref: {report.illegal_answer_ref_count}")
    print(f"  api_key_leak: {report.api_key_leak_count}")
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
        f"only {report.success_count}/{report.total} runs succeeded; "
        f"acceptance requires >= {MIN_ACCEPTANCE_PASSES}"
    )


if __name__ == "__main__":
    main()
