from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import AppError
from app.models.enums import TaskStatus
from app.models.operations import AgentRun, AgentStep
from app.models.users import User
from app.schemas.match_runs import (
    MatchNodeStatus,
    MatchRunCreate,
    MatchRunEvent,
    MatchRunListRead,
    MatchRunRead,
    MatchRunStatus,
    MatchRunStepRead,
)
from app.schemas.matching import MatchCreate
from app.services.matching import MatchService

NODE_ORDER = (
    "load_inputs",
    "deterministic_matching",
    "semantic_retrieval",
    "blocking_risk_check",
    "save_report",
    "human_review",
)
TERMINAL_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}
MAX_NODE_RETRIES = 2


class WorkflowState(TypedDict, total=False):
    run_id: int
    user_id: int
    resume_version_id: int
    job_id: int
    scoring_version: str
    current_node: str | None
    node_status: str
    completed_nodes: list[str]
    rule_score: float | None
    semantic_score: float | None
    hybrid_score: float | None
    blocking_risks: list[dict[str, Any]]
    report_id: int | None
    error_code: str | None
    error_message: str | None
    waiting_for_user: bool
    human_confirmed: bool
    artifacts: dict[str, Any]
    events: list[dict[str, Any]]


class RunCancelled(Exception):
    pass


class MatchRunService:
    """Durable LangGraph orchestration backed by the existing agent run tables."""

    def __init__(
        self,
        session: Session,
        *,
        session_factory: Callable[[], Session] | None = None,
        matching_service_factory: Callable[[Session], MatchService] | None = None,
    ) -> None:
        self.session = session
        self.session_factory = session_factory or sessionmaker(
            bind=session.get_bind(),
            autoflush=False,
            expire_on_commit=False,
        )
        self.matching_service_factory = matching_service_factory or MatchService

    def create(self, user: User, payload: MatchRunCreate) -> MatchRunRead:
        match_payload = self._match_payload(payload)
        self._matching().workflow_validate_inputs(user, match_payload)
        now = datetime.now(UTC)
        snapshot: WorkflowState = {
            "user_id": user.id,
            "resume_version_id": payload.resume_version_id,
            "job_id": payload.job_id,
            "scoring_version": payload.scoring_version,
            "current_node": None,
            "node_status": MatchNodeStatus.PENDING.value,
            "completed_nodes": [],
            "rule_score": None,
            "semantic_score": None,
            "hybrid_score": None,
            "blocking_risks": [],
            "report_id": None,
            "error_code": None,
            "error_message": None,
            "waiting_for_user": False,
            "human_confirmed": False,
            "artifacts": {},
            "events": [],
        }
        run = AgentRun(
            user_id=user.id,
            run_type="MATCHING_LANGGRAPH",
            status=TaskStatus.PENDING,
            state_snapshot=dict(snapshot),
            started_at=now,
        )
        self.session.add(run)
        self.session.flush()
        snapshot["run_id"] = run.id
        run.state_snapshot = dict(snapshot)
        for sequence, node_name in enumerate(NODE_ORDER, 1):
            run.steps.append(
                AgentStep(
                    sequence=sequence,
                    node_name=node_name,
                    status=TaskStatus.PENDING,
                )
            )
        self._append_event(run, "run_started", status=TaskStatus.PENDING.value)
        self.session.commit()
        self.session.refresh(run)
        return self._read(run)

    def execute_in_background(self, run_id: int) -> None:
        with self.session_factory() as session:
            MatchRunService(
                session,
                session_factory=self.session_factory,
                matching_service_factory=self.matching_service_factory,
            ).execute(run_id)

    def execute(self, run_id: int, *, confirmed: bool = False) -> MatchRunRead:
        run = self._run(run_id)
        if run.status == TaskStatus.CANCELLED:
            return self._read(run)
        snapshot = self._snapshot(run)
        snapshot["human_confirmed"] = confirmed or bool(snapshot.get("human_confirmed"))
        run.status = TaskStatus.RUNNING
        snapshot["waiting_for_user"] = False
        run.state_snapshot = dict(snapshot)
        self.session.commit()
        try:
            self._graph().invoke(snapshot)
        except RunCancelled:
            pass
        except Exception as exc:
            self.session.rollback()
            run = self._run(run_id)
            if run.status != TaskStatus.CANCELLED:
                run.status = TaskStatus.FAILED
                run.finished_at = datetime.now(UTC)
                snapshot = self._snapshot(run)
                snapshot["node_status"] = MatchNodeStatus.FAILED.value
                snapshot["error_code"] = self._error_code(exc)
                snapshot["error_message"] = self._safe_error(exc)
                run.error_code = str(snapshot["error_code"])
                run.error_message = str(snapshot["error_message"])
                run.state_snapshot = dict(snapshot)
                self._append_event(
                    run,
                    "run_failed",
                    status=TaskStatus.FAILED.value,
                    error_code=run.error_code,
                    error_message=run.error_message,
                )
                self.session.commit()
        return self.get_by_id(run_id)

    def get(self, user: User, run_id: int) -> MatchRunRead:
        return self._read(self._owned(run_id, user.id))

    def get_by_id(self, run_id: int) -> MatchRunRead:
        return self._read(self._run(run_id))

    def retry(self, user: User, run_id: int) -> MatchRunRead:
        run = self._owned(run_id, user.id)
        if run.status != TaskStatus.FAILED:
            raise AppError("MATCH_RUN_NOT_FAILED", "Only a failed run can be retried", 409)
        failed = next((step for step in run.steps if step.status == TaskStatus.FAILED), None)
        if failed is None:
            raise AppError("MATCH_RUN_RETRY_UNAVAILABLE", "No failed node was found", 409)
        if failed.retry_count >= MAX_NODE_RETRIES:
            raise AppError("MATCH_RUN_RETRY_LIMIT", "The node retry limit was reached", 409)
        failed.retry_count += 1
        failed.status = TaskStatus.PENDING
        failed.started_at = None
        failed.finished_at = None
        failed.duration_ms = None
        failed.error_message = None
        snapshot = self._snapshot(run)
        snapshot["error_code"] = None
        snapshot["error_message"] = None
        snapshot["node_status"] = MatchNodeStatus.PENDING.value
        run.error_code = None
        run.error_message = None
        run.status = TaskStatus.PENDING
        run.finished_at = None
        run.state_snapshot = dict(snapshot)
        self.session.commit()
        return self.execute(run.id)

    def confirm(self, user: User, run_id: int) -> MatchRunRead:
        run = self._owned(run_id, user.id)
        if run.status != TaskStatus.WAITING_REVIEW:
            raise AppError(
                "MATCH_RUN_NOT_WAITING",
                "The run is not waiting for human confirmation",
                409,
            )
        snapshot = self._snapshot(run)
        snapshot["human_confirmed"] = True
        run.state_snapshot = dict(snapshot)
        self.session.commit()
        return self.execute(run.id, confirmed=True)

    def cancel(self, user: User, run_id: int) -> MatchRunRead:
        run = self._owned(run_id, user.id)
        if run.status in TERMINAL_STATUSES:
            raise AppError("MATCH_RUN_TERMINAL", "The run is already terminal", 409)
        run.status = TaskStatus.CANCELLED
        run.finished_at = datetime.now(UTC)
        snapshot = self._snapshot(run)
        snapshot["node_status"] = MatchNodeStatus.CANCELLED.value
        snapshot["waiting_for_user"] = False
        run.state_snapshot = dict(snapshot)
        self._append_event(run, "run_cancelled", status=TaskStatus.CANCELLED.value)
        self.session.commit()
        return self._read(run)

    def events(self, user: User, run_id: int, after_id: int = 0) -> list[MatchRunEvent]:
        run = self._owned(run_id, user.id)
        return [
            MatchRunEvent.model_validate(item)
            for item in self._snapshot(run).get("events", [])
            if int(item["id"]) > after_id
        ]

    def list_admin(self, *, offset: int, limit: int) -> MatchRunListRead:
        statement = select(AgentRun).where(AgentRun.run_type == "MATCHING_LANGGRAPH")
        total = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        runs = self.session.scalars(
            statement.order_by(AgentRun.created_at.desc()).offset(offset).limit(limit)
        ).all()
        return MatchRunListRead(
            items=[self._read(run, redact=True) for run in runs],
            total=total,
            offset=offset,
            limit=limit,
        )

    def get_admin(self, run_id: int) -> MatchRunRead:
        return self._read(self._run(run_id), redact=True)

    def _graph(self) -> Any:
        builder = StateGraph(WorkflowState)
        builder.add_node("load_inputs", self._load_inputs_node)
        builder.add_node("deterministic_matching", self._deterministic_node)
        builder.add_node("semantic_retrieval", self._semantic_node)
        builder.add_node("blocking_risk_check", self._blocking_node)
        builder.add_node("save_report", self._save_node)
        builder.add_node("human_review", self._human_review_node)
        builder.add_edge(START, "load_inputs")
        builder.add_edge("load_inputs", "deterministic_matching")
        builder.add_edge("deterministic_matching", "semantic_retrieval")
        builder.add_edge("semantic_retrieval", "blocking_risk_check")
        builder.add_edge("blocking_risk_check", "save_report")
        builder.add_edge("save_report", "human_review")
        builder.add_edge("human_review", END)
        return builder.compile()

    def _load_inputs_node(self, state: WorkflowState) -> WorkflowState:
        def action() -> dict[str, Any]:
            user = self._user(int(state["user_id"]))
            self._matching().workflow_validate_inputs(user, self._payload(state))
            return {"summary": {"inputs_valid": True}}

        return self._run_node(state, "load_inputs", action)

    def _deterministic_node(self, state: WorkflowState) -> WorkflowState:
        def action() -> dict[str, Any]:
            user = self._user(int(state["user_id"]))
            artifacts = self._matching().workflow_compute_deterministic(
                user,
                self._payload(state),
            )
            computation = artifacts["computation"]
            return {
                "artifacts": artifacts,
                "rule_score": float(computation["rule_score"]),
                "summary": {"rule_score": float(computation["rule_score"])},
            }

        return self._run_node(state, "deterministic_matching", action)

    def _semantic_node(self, state: WorkflowState) -> WorkflowState:
        if "semantic_retrieval" in state.get("completed_nodes", []):
            return state
        if state["scoring_version"] != "hybrid-v1":
            return self._skip_node(state, "semantic_retrieval", "rule-only scoring version")

        def action() -> dict[str, Any]:
            user = self._user(int(state["user_id"]))
            semantic = self._matching().workflow_compute_semantic(
                user,
                self._payload(state),
            )
            artifacts = dict(state.get("artifacts", {}))
            artifacts["semantic"] = semantic
            return {
                "artifacts": artifacts,
                "semantic_score": float(semantic["score"]),
                "summary": {
                    "semantic_score": float(semantic["score"]),
                    "evidence_count": len(semantic["evidence"]),
                },
            }

        return self._run_node(state, "semantic_retrieval", action)

    def _blocking_node(self, state: WorkflowState) -> WorkflowState:
        def action() -> dict[str, Any]:
            computation = dict(state["artifacts"]["computation"])
            risks = [
                risk for risk in computation.get("risks", []) if risk.get("severity") == "BLOCKING"
            ]
            semantic_score = state.get("semantic_score")
            rule_score = float(computation["rule_score"])
            hybrid_score: float | None = None
            if semantic_score is not None:
                weights = state["artifacts"]["scoring_config"]["hybrid_weights"]
                hybrid_score = round(
                    rule_score * float(weights["deterministic"])
                    + float(semantic_score) * float(weights["semantic"]),
                    2,
                )
            return {
                "blocking_risks": risks,
                "hybrid_score": hybrid_score,
                "summary": {
                    "blocking_risk_count": len(risks),
                    "blocking_preserved": bool(risks),
                },
            }

        return self._run_node(state, "blocking_risk_check", action)

    def _save_node(self, state: WorkflowState) -> WorkflowState:
        def action() -> dict[str, Any]:
            user = self._user(int(state["user_id"]))
            result = self._matching().create_from_workflow(
                user,
                self._payload(state),
                dict(state["artifacts"]),
            )
            return {
                "report_id": result.report.id,
                "summary": {"report_id": result.report.id, "reused": result.reused},
            }

        return self._run_node(state, "save_report", action)

    def _human_review_node(self, state: WorkflowState) -> WorkflowState:
        if not state.get("human_confirmed"):
            run = self._run(int(state["run_id"]))
            step = self._step(run, "human_review")
            now = datetime.now(UTC)
            step.status = TaskStatus.WAITING_REVIEW
            step.started_at = step.started_at or now
            snapshot = self._snapshot(run)
            self._merge_state(snapshot, state)
            snapshot["current_node"] = "human_review"
            snapshot["node_status"] = MatchNodeStatus.PENDING.value
            snapshot["waiting_for_user"] = True
            run.status = TaskStatus.WAITING_REVIEW
            run.state_snapshot = dict(snapshot)
            self._append_event(
                run,
                "waiting_for_user",
                node="human_review",
                status=TaskStatus.WAITING_REVIEW.value,
                report_id=self._optional_int(snapshot.get("report_id")),
            )
            self.session.commit()
            return snapshot

        result = self._run_node(
            state,
            "human_review",
            lambda: {"summary": {"confirmed": True}},
        )
        run = self._run(int(state["run_id"]))
        run.status = TaskStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        snapshot = self._snapshot(run)
        snapshot["waiting_for_user"] = False
        snapshot["current_node"] = "human_review"
        snapshot["node_status"] = MatchNodeStatus.SUCCEEDED.value
        run.state_snapshot = dict(snapshot)
        self._append_event(
            run,
            "run_completed",
            status=TaskStatus.SUCCEEDED.value,
            report_id=self._optional_int(snapshot.get("report_id")),
        )
        self.session.commit()
        return result

    def _run_node(
        self,
        state: WorkflowState,
        node_name: str,
        action: Callable[[], dict[str, Any]],
    ) -> WorkflowState:
        run = self._run(int(state["run_id"]))
        if run.status == TaskStatus.CANCELLED:
            raise RunCancelled
        snapshot = self._snapshot(run)
        completed = list(snapshot.get("completed_nodes", []))
        if node_name in completed:
            return snapshot
        step = self._step(run, node_name)
        started_at = datetime.now(UTC)
        started_clock = perf_counter()
        step.status = TaskStatus.RUNNING
        step.started_at = started_at
        step.finished_at = None
        self._merge_state(snapshot, state)
        snapshot["current_node"] = node_name
        snapshot["node_status"] = MatchNodeStatus.RUNNING.value
        run.status = TaskStatus.RUNNING
        run.state_snapshot = dict(snapshot)
        self._append_event(run, "node_started", node=node_name, status="RUNNING")
        self.session.commit()
        try:
            changes = action()
        except Exception as exc:
            self.session.rollback()
            run = self._run(int(state["run_id"]))
            step = self._step(run, node_name)
            finished_at = datetime.now(UTC)
            step.status = TaskStatus.FAILED
            step.finished_at = finished_at
            step.duration_ms = max(0, int((perf_counter() - started_clock) * 1000))
            step.error_message = self._safe_error(exc)
            snapshot = self._snapshot(run)
            self._merge_state(snapshot, state)
            snapshot["current_node"] = node_name
            snapshot["node_status"] = MatchNodeStatus.FAILED.value
            snapshot["error_code"] = self._error_code(exc)
            snapshot["error_message"] = self._safe_error(exc)
            run.status = TaskStatus.FAILED
            run.error_code = str(snapshot["error_code"])
            run.error_message = str(snapshot["error_message"])
            run.finished_at = finished_at
            run.state_snapshot = dict(snapshot)
            self._append_event(
                run,
                "node_failed",
                node=node_name,
                status="FAILED",
                duration_ms=step.duration_ms,
                error_code=run.error_code,
                error_message=run.error_message,
            )
            self.session.commit()
            raise
        finished_at = datetime.now(UTC)
        duration_ms = max(0, int((perf_counter() - started_clock) * 1000))
        step.status = TaskStatus.SUCCEEDED
        step.finished_at = finished_at
        step.duration_ms = duration_ms
        summary = dict(changes.pop("summary", {}))
        step.output_summary = summary
        snapshot = self._snapshot(run)
        self._merge_state(snapshot, state)
        for key, value in changes.items():
            snapshot[key] = value  # type: ignore[literal-required]
        completed = list(snapshot.get("completed_nodes", []))
        completed.append(node_name)
        snapshot["completed_nodes"] = list(dict.fromkeys(completed))
        snapshot["current_node"] = node_name
        snapshot["node_status"] = MatchNodeStatus.SUCCEEDED.value
        snapshot["error_code"] = None
        snapshot["error_message"] = None
        run.state_snapshot = dict(snapshot)
        self._append_event(
            run,
            "node_completed",
            node=node_name,
            status="SUCCEEDED",
            duration_ms=duration_ms,
            summary=summary,
            report_id=self._optional_int(snapshot.get("report_id")),
        )
        self.session.commit()
        return snapshot

    def _skip_node(self, state: WorkflowState, node_name: str, reason: str) -> WorkflowState:
        run = self._run(int(state["run_id"]))
        step = self._step(run, node_name)
        step.status = TaskStatus.SUCCEEDED
        step.output_summary = {"skipped": True, "reason": reason}
        step.duration_ms = 0
        now = datetime.now(UTC)
        step.started_at = now
        step.finished_at = now
        snapshot = self._snapshot(run)
        self._merge_state(snapshot, state)
        completed = list(snapshot.get("completed_nodes", []))
        completed.append(node_name)
        snapshot["completed_nodes"] = list(dict.fromkeys(completed))
        snapshot["current_node"] = node_name
        snapshot["node_status"] = MatchNodeStatus.SKIPPED.value
        run.state_snapshot = dict(snapshot)
        self._append_event(
            run,
            "node_completed",
            node=node_name,
            status=MatchNodeStatus.SKIPPED.value,
            duration_ms=0,
            summary={"skipped": True, "reason": reason},
        )
        self.session.commit()
        return snapshot

    def _read(self, run: AgentRun, *, redact: bool = False) -> MatchRunRead:
        snapshot = self._snapshot(run)
        started = run.started_at
        finished = run.finished_at
        duration = (
            max(
                0,
                int((self._as_utc(finished) - self._as_utc(started)).total_seconds() * 1000),
            )
            if started is not None and finished is not None
            else None
        )
        error_message = self._redact(run.error_message) if redact else run.error_message
        return MatchRunRead(
            run_id=run.id,
            user_id=run.user_id,
            resume_version_id=int(snapshot["resume_version_id"]),
            job_id=int(snapshot["job_id"]),
            scoring_version=str(snapshot["scoring_version"]),
            status=MatchRunStatus(run.status.value),
            current_node=self._optional_str(snapshot.get("current_node")),
            node_status=MatchNodeStatus(str(snapshot.get("node_status", "PENDING"))),
            completed_nodes=[str(item) for item in snapshot.get("completed_nodes", [])],
            rule_score=self._optional_float(snapshot.get("rule_score")),
            semantic_score=self._optional_float(snapshot.get("semantic_score")),
            hybrid_score=self._optional_float(snapshot.get("hybrid_score")),
            blocking_risks=list(snapshot.get("blocking_risks", [])),
            report_id=self._optional_int(snapshot.get("report_id")),
            error_code=run.error_code,
            error_message=error_message,
            waiting_for_user=bool(snapshot.get("waiting_for_user")),
            retry_count=sum(step.retry_count for step in run.steps),
            started_at=started,
            finished_at=finished,
            duration_ms=duration,
            steps=[
                MatchRunStepRead(
                    node_name=step.node_name,
                    status=(
                        MatchNodeStatus.SKIPPED
                        if step.output_summary.get("skipped")
                        else MatchNodeStatus(step.status.value)
                    ),
                    retry_count=step.retry_count,
                    started_at=step.started_at,
                    finished_at=step.finished_at,
                    duration_ms=step.duration_ms,
                    summary=step.output_summary,
                    error_message=(
                        self._redact(step.error_message) if redact else step.error_message
                    ),
                )
                for step in run.steps
            ],
        )

    def _append_event(
        self,
        run: AgentRun,
        event: str,
        *,
        status: str,
        node: str | None = None,
        duration_ms: int | None = None,
        summary: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        report_id: int | None = None,
    ) -> None:
        snapshot = self._snapshot(run)
        events = list(snapshot.get("events", []))
        events.append(
            {
                "id": len(events) + 1,
                "event": event,
                "run_id": run.id,
                "node": node,
                "status": status,
                "timestamp": datetime.now(UTC).isoformat(),
                "duration_ms": duration_ms,
                "summary": summary or {},
                "error_code": error_code,
                "error_message": error_message,
                "report_id": report_id,
            }
        )
        snapshot["events"] = events
        run.state_snapshot = dict(snapshot)

    def _owned(self, run_id: int, user_id: int) -> AgentRun:
        run = self.session.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.user_id == user_id,
                AgentRun.run_type == "MATCHING_LANGGRAPH",
            )
        )
        if run is None:
            raise AppError("MATCH_RUN_NOT_FOUND", "The matching run was not found", 404)
        return run

    def _run(self, run_id: int) -> AgentRun:
        run = self.session.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.run_type == "MATCHING_LANGGRAPH",
            )
        )
        if run is None:
            raise AppError("MATCH_RUN_NOT_FOUND", "The matching run was not found", 404)
        return run

    def _user(self, user_id: int) -> User:
        user = self.session.get(User, user_id)
        if user is None or not user.is_active:
            raise AppError("USER_NOT_FOUND", "The matching run user was not found", 404)
        return user

    def _matching(self) -> MatchService:
        return self.matching_service_factory(self.session)

    @staticmethod
    def _step(run: AgentRun, node_name: str) -> AgentStep:
        step = next((item for item in run.steps if item.node_name == node_name), None)
        if step is None:
            raise AppError("MATCH_RUN_STEP_NOT_FOUND", "The workflow node was not found", 500)
        return step

    @staticmethod
    def _snapshot(run: AgentRun) -> WorkflowState:
        return dict(run.state_snapshot)  # type: ignore[return-value]

    @staticmethod
    def _match_payload(payload: MatchRunCreate) -> MatchCreate:
        return MatchCreate(
            resume_version_id=payload.resume_version_id,
            job_id=payload.job_id,
            scoring_version=payload.scoring_version,
        )

    @staticmethod
    def _payload(state: WorkflowState) -> MatchCreate:
        return MatchCreate(
            resume_version_id=int(state["resume_version_id"]),
            job_id=int(state["job_id"]),
            scoring_version=str(state["scoring_version"]),
        )

    @staticmethod
    def _error_code(exc: Exception) -> str:
        return exc.code if isinstance(exc, AppError) else "MATCH_RUN_NODE_FAILED"

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return exc.message if isinstance(exc, AppError) else "The workflow node failed"

    @staticmethod
    def _redact(message: str | None) -> str | None:
        return "Workflow node failed; inspect server diagnostics." if message else None

    @staticmethod
    def _optional_int(value: object) -> int | None:
        return int(value) if isinstance(value, int | float | str) and str(value).isdigit() else None

    @staticmethod
    def _optional_float(value: object) -> float | None:
        return float(value) if isinstance(value, int | float) else None

    @staticmethod
    def _optional_str(value: object) -> str | None:
        return str(value) if value is not None else None

    @staticmethod
    def _merge_state(target: WorkflowState, source: WorkflowState) -> None:
        for key, value in source.items():
            if key != "events":
                target[key] = value  # type: ignore[literal-required]

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
