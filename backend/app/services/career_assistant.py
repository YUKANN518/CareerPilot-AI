"""Career Assistant knowledge QA service (Stage 4A + 4B).

An independent LangGraph orchestration that reuses the existing
``AgentRun`` / ``AgentStep`` audit tables (with ``run_type =
CAREER_ASSISTANT_QA``) instead of introducing a new table. The graph has
five linear nodes:

    load_question -> retrieve_knowledge -> retrieve_personal_context
                 -> generate_answer -> save_run

Retrieval is backend-controlled:
- Knowledge base: FAISS via ``KnowledgeIndexService`` (shared docs).
- Personal context: SQL queries via ``PersonalContextService`` (the
  user's own resume, match reports and applications).

Generation is delegated to the ``KnowledgeQAProvider`` (Fake or Dify).
When both retrieval sources yield nothing the graph short-circuits
generation and returns a graceful "insufficient evidence" answer with
no citations, so the provider is never called without context.

The ``scope`` field on ``CareerAssistantQACreate`` (Stage 4B) controls
which retrieval sources run: ``auto`` (both), ``knowledge`` (KB only)
or ``personal`` (user data only).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.ai.prompts import CAREER_RAG_PROMPT_VERSION
from app.core.config import Settings
from app.core.exceptions import AppError
from app.integrations.dify.knowledge_qa_providers import (
    KnowledgeQAProvider,
    create_knowledge_qa_provider,
)
from app.models.enums import TaskStatus
from app.models.operations import AgentRun, AgentStep, ModelUsageLog
from app.models.users import User
from app.schemas.career_assistant import (
    CareerAssistantQACitationRead,
    CareerAssistantQACreate,
    CareerAssistantQAEvent,
    CareerAssistantQAListItemRead,
    CareerAssistantQAListRead,
    CareerAssistantQARead,
    KnowledgeQAContextChunk,
    KnowledgeQAWorkflowInput,
    PersonalContextChunk,
)
from app.semantic.embeddings import embedding_provider_from_settings
from app.semantic.knowledge_index import KnowledgeIndexService
from app.services.personal_context import PersonalContextService

RUN_TYPE = "CAREER_ASSISTANT_QA"
NODE_ORDER = (
    "load_question",
    "retrieve_knowledge",
    "retrieve_personal_context",
    "generate_answer",
    "save_run",
)
TERMINAL_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}
INSUFFICIENT_EVIDENCE_MESSAGE_EN = (
    "No relevant knowledge base content was found for this question. "
    "Please try rephrasing your question or ask an administrator to upload "
    "additional reference materials."
)
INSUFFICIENT_EVIDENCE_MESSAGE_ZH = "当前知识库中没有足够依据回答该问题。"
SCOPE_KNOWLEDGE = "knowledge"
SCOPE_PERSONAL = "personal"
SCOPE_AUTO = "auto"


@dataclass(frozen=True)
class _QueryEntity:
    """A deterministic entity recognised in multi-topic knowledge queries."""

    name: str
    aliases: tuple[str, ...]
    focused_query: str
    title_keywords: tuple[str, ...]


# This deliberately small dictionary maps only known knowledge-base themes.
# It never invents comparison dimensions or additional entities.
QUERY_ENTITIES: tuple[_QueryEntity, ...] = (
    _QueryEntity(
        "软件开发",
        ("软件开发", "软件工程", "software development"),
        "软件开发岗位 适合用什么项目证明能力",
        ("软件开发",),
    ),
    _QueryEntity(
        "数据分析",
        ("数据分析", "data analysis", "data analyst"),
        "数据分析岗位 适合用什么项目证明能力",
        ("数据分析",),
    ),
    _QueryEntity(
        "QA",
        ("软件测试", "qa", "quality assurance"),
        "软件测试 QA 岗位 适合用什么项目证明能力",
        ("软件测试", "qa"),
    ),
    _QueryEntity(
        "IT Support",
        ("it support", "技术支持"),
        "IT Support 技术支持岗位 职责 能力 项目证据",
        ("it support", "技术支持"),
    ),
    _QueryEntity(
        "Business Analyst",
        ("business analyst", "业务分析"),
        "Business Analyst 业务分析岗位 职责 能力 项目证据",
        ("business analyst", "业务分析"),
    ),
    _QueryEntity("IANG", ("iang",), "IANG 非本地毕业生 求职提示", ("iang",)),
    _QueryEntity("简历", ("简历", "resume"), "简历 求职建议", ("简历",)),
    _QueryEntity("面试", ("面试", "interview"), "面试 求职建议", ("面试",)),
)


class CareerAssistantQAState(TypedDict, total=False):
    run_id: int
    user_id: int
    question: str
    scope: str
    current_node: str | None
    node_status: str
    completed_nodes: list[str]
    context_chunks: list[dict[str, Any]]
    requested_entities: list[str]
    retrieved_entities: list[str]
    missing_entities: list[str]
    retrieval_queries: dict[str, str]
    personal_context: list[dict[str, Any]]
    answer: str | None
    citations: list[dict[str, Any]]
    generation: dict[str, Any] | None
    provider_attempts: list[dict[str, Any]]
    error_code: str | None
    error_message: str | None
    insufficient_evidence: bool
    events: list[dict[str, Any]]


class _RunCancelled(Exception):
    pass


class CareerAssistantQAService:
    """Durable LangGraph orchestration for knowledge QA runs."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        session_factory: Callable[[], Session] | None = None,
        index_service_factory: Callable[[Session], KnowledgeIndexService] | None = None,
        provider_factory: Callable[[], KnowledgeQAProvider] | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.session_factory = session_factory or sessionmaker(
            bind=session.get_bind(),
            autoflush=False,
            expire_on_commit=False,
        )
        self._index_service_factory = index_service_factory
        self._provider_factory = provider_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self, user: User, payload: CareerAssistantQACreate) -> CareerAssistantQARead:
        question = payload.question.strip()
        scope = payload.scope
        now = datetime.now(UTC)
        snapshot: CareerAssistantQAState = {
            "user_id": user.id,
            "question": question,
            "scope": scope,
            "current_node": None,
            "node_status": "PENDING",
            "completed_nodes": [],
            "context_chunks": [],
            "requested_entities": [],
            "retrieved_entities": [],
            "missing_entities": [],
            "retrieval_queries": {},
            "personal_context": [],
            "answer": None,
            "citations": [],
            "generation": None,
            "provider_attempts": [],
            "error_code": None,
            "error_message": None,
            "insufficient_evidence": False,
            "events": [],
        }
        run = AgentRun(
            user_id=user.id,
            run_type=RUN_TYPE,
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
            CareerAssistantQAService(
                session,
                self.settings,
                session_factory=self.session_factory,
                index_service_factory=self._index_service_factory,
                provider_factory=self._provider_factory,
            ).execute(run_id)

    def execute(self, run_id: int) -> CareerAssistantQARead:
        run = self._run(run_id)
        if run.status == TaskStatus.CANCELLED:
            return self._read(run)
        snapshot = self._snapshot(run)
        run.status = TaskStatus.RUNNING
        run.state_snapshot = dict(snapshot)
        self.session.commit()
        try:
            self._graph().invoke(snapshot)
        except _RunCancelled:
            pass
        except Exception as exc:
            self.session.rollback()
            run = self._run(run_id)
            if run.status != TaskStatus.CANCELLED:
                snapshot = self._snapshot(run)
                snapshot["node_status"] = "FAILED"
                snapshot["error_code"] = self._error_code(exc)
                snapshot["error_message"] = self._safe_error(exc)
                run.status = TaskStatus.FAILED
                run.finished_at = datetime.now(UTC)
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

    def get(self, user: User, run_id: int) -> CareerAssistantQARead:
        return self._read(self._owned(run_id, user.id))

    def get_by_id(self, run_id: int) -> CareerAssistantQARead:
        return self._read(self._run(run_id))

    def list_user(
        self,
        user: User,
        *,
        offset: int,
        limit: int,
    ) -> CareerAssistantQAListRead:
        statement = select(AgentRun).where(
            AgentRun.user_id == user.id,
            AgentRun.run_type == RUN_TYPE,
        )
        total = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        runs = self.session.scalars(
            statement.order_by(AgentRun.created_at.desc()).offset(offset).limit(limit)
        ).all()
        return CareerAssistantQAListRead(
            items=[self._list_item(run) for run in runs],
            total=total,
            offset=offset,
            limit=limit,
        )

    def events(self, user: User, run_id: int, after_id: int = 0) -> list[CareerAssistantQAEvent]:
        run = self._owned(run_id, user.id)
        return [
            CareerAssistantQAEvent.model_validate(item)
            for item in self._snapshot(run).get("events", [])
            if int(item["id"]) > after_id
        ]

    # ------------------------------------------------------------------
    # LangGraph definition
    # ------------------------------------------------------------------

    def _graph(self) -> Any:
        builder = StateGraph(CareerAssistantQAState)
        builder.add_node("load_question", self._load_question_node)
        builder.add_node("retrieve_knowledge", self._retrieve_knowledge_node)
        builder.add_node("retrieve_personal_context", self._retrieve_personal_context_node)
        builder.add_node("generate_answer", self._generate_answer_node)
        builder.add_node("save_run", self._save_run_node)
        builder.add_edge(START, "load_question")
        builder.add_edge("load_question", "retrieve_knowledge")
        builder.add_edge("retrieve_knowledge", "retrieve_personal_context")
        builder.add_edge("retrieve_personal_context", "generate_answer")
        builder.add_edge("generate_answer", "save_run")
        builder.add_edge("save_run", END)
        return builder.compile()

    def _load_question_node(self, state: CareerAssistantQAState) -> CareerAssistantQAState:
        def action() -> dict[str, Any]:
            question = str(state["question"]).strip()
            if not question:
                raise AppError(
                    "CAREER_QA_QUESTION_EMPTY",
                    "The question must not be empty",
                    422,
                )
            return {"summary": {"question_length": len(question)}}

        return self._run_node(state, "load_question", action)

    def _retrieve_knowledge_node(self, state: CareerAssistantQAState) -> CareerAssistantQAState:
        scope = str(state.get("scope", SCOPE_AUTO))
        if scope == SCOPE_PERSONAL:
            return self._skip_node(
                state,
                "retrieve_knowledge",
                "scope=personal; skipped knowledge retrieval",
                extra_changes={
                    "context_chunks": [],
                    "requested_entities": [],
                    "retrieved_entities": [],
                    "missing_entities": [],
                    "retrieval_queries": {},
                    "insufficient_evidence": True,
                },
            )

        def action() -> dict[str, Any]:
            index_service = self._index_service()
            chunks, coverage = self._retrieve_knowledge_with_coverage(
                index_service,
                str(state["question"]),
            )
            context_chunks = [
                KnowledgeQAContextChunk(
                    document_id=chunk.document_id,
                    title=chunk.title,
                    category=chunk.category,
                    chunk_text=chunk.chunk_text,
                    chunk_index=chunk.chunk_index,
                    page_number=chunk.page_number,
                    paragraph_index=chunk.paragraph_index,
                    score=chunk.score,
                )
                for chunk in chunks
            ]
            return {
                "context_chunks": [item.model_dump(mode="json") for item in context_chunks],
                "requested_entities": coverage["requested_entities"],
                "retrieved_entities": coverage["retrieved_entities"],
                "missing_entities": coverage["missing_entities"],
                "retrieval_queries": coverage["retrieval_queries"],
                "summary": {
                    "retrieved_chunks": len(context_chunks),
                    "requested_entities": coverage["requested_entities"],
                    "retrieved_entities": coverage["retrieved_entities"],
                    "missing_entities": coverage["missing_entities"],
                },
            }

        return self._run_node(state, "retrieve_knowledge", action)

    def _retrieve_personal_context_node(
        self, state: CareerAssistantQAState
    ) -> CareerAssistantQAState:
        scope = str(state.get("scope", SCOPE_AUTO))
        if scope == SCOPE_KNOWLEDGE:
            return self._skip_node(
                state,
                "retrieve_personal_context",
                "scope=knowledge; skipped personal retrieval",
                extra_changes={"personal_context": []},
            )

        def action() -> dict[str, Any]:
            service = PersonalContextService(self.session)
            chunks = service.retrieve(
                int(state["user_id"]),
                str(state["question"]),
            )
            return {
                "personal_context": [item.model_dump(mode="json") for item in chunks],
                "summary": {
                    "personal_chunks": len(chunks),
                },
            }

        return self._run_node(state, "retrieve_personal_context", action)

    def _generate_answer_node(self, state: CareerAssistantQAState) -> CareerAssistantQAState:
        context_chunks_data = state.get("context_chunks", [])
        personal_context_data = state.get("personal_context", [])
        has_any_context = bool(context_chunks_data) or bool(personal_context_data)
        if not has_any_context:
            return self._skip_node(
                state,
                "generate_answer",
                "insufficient evidence; skipped provider call",
                extra_changes={
                    "answer": self._insufficient_evidence_message(str(state["question"])),
                    "citations": [],
                    "generation": None,
                    "provider_attempts": [],
                },
            )

        def action() -> dict[str, Any]:
            context_chunks = [
                KnowledgeQAContextChunk.model_validate(item) for item in context_chunks_data
            ]
            personal_chunks = [
                PersonalContextChunk.model_validate(item) for item in personal_context_data
            ]
            # When only personal context is available, we still need at least
            # one knowledge chunk to satisfy the workflow input contract
            # (context_chunks min_length=1). Use a synthetic placeholder.
            workflow_context_chunks = context_chunks[: self.settings.knowledge_qa_context_chunks]
            if not workflow_context_chunks and personal_chunks:
                workflow_context_chunks = [
                    KnowledgeQAContextChunk(
                        document_id=0,
                        title="User personal data",
                        category="personal",
                        chunk_text="See personal_context for user-specific data.",
                        chunk_index=0,
                        score=1.0,
                    )
                ]

            schema_version = (
                "career-assistant-personalized-input-v1"
                if personal_chunks
                else "career-assistant-knowledge-input-v1"
            )
            request = KnowledgeQAWorkflowInput(
                user_id=int(state["user_id"]),
                question=str(state["question"]),
                context_chunks=workflow_context_chunks,
                personal_context=personal_chunks,
                requested_entities=list(state.get("requested_entities", [])),
                retrieved_entities=list(state.get("retrieved_entities", [])),
                missing_entities=list(state.get("missing_entities", [])),
            )
            request = request.model_copy(update={"schema_version": schema_version})
            provider = self._provider()
            result = provider.answer_question(request)
            output = result.output
            self.session.add(
                ModelUsageLog(
                    user_id=int(state["user_id"]),
                    agent_run_id=int(state["run_id"]),
                    provider=output.generation.provider,
                    model_name=output.generation.workflow_version,
                    operation="career_assistant_qa",
                    prompt_version=output.generation.prompt_version,
                    prompt_tokens=0,
                    completion_tokens=0,
                    latency_ms=output.generation.latency_ms,
                    estimated_cost=None,
                    is_success=True,
                    error_code=None,
                )
            )
            if output.insufficient_evidence:
                return {
                    "answer": self._insufficient_evidence_message(str(state["question"])),
                    "citations": [],
                    "generation": output.generation.model_dump(mode="json"),
                    "provider_attempts": [item.model_dump(mode="json") for item in result.attempts],
                    "provider_request": result.request_summary,
                    "summary": {
                        "citation_count": 0,
                        "provider": output.generation.provider,
                        "attempts": len(result.attempts),
                        "insufficient_evidence": True,
                    },
                }
            citations = self._enrich_citations(
                output.used_citation_keys,
                context_chunks,
                personal_chunks,
            )
            return {
                "answer": output.answer,
                "citations": [item.model_dump(mode="json") for item in citations],
                "generation": output.generation.model_dump(mode="json"),
                "provider_attempts": [item.model_dump(mode="json") for item in result.attempts],
                "provider_request": result.request_summary,
                "summary": {
                    "citation_count": len(citations),
                    "provider": output.generation.provider,
                    "attempts": len(result.attempts),
                },
            }

        return self._run_node(state, "generate_answer", action)

    def _save_run_node(self, state: CareerAssistantQAState) -> CareerAssistantQAState:
        def action() -> dict[str, Any]:
            return {"summary": {"persisted": True}}

        result = self._run_node(state, "save_run", action)
        run = self._run(int(state["run_id"]))
        run.status = TaskStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        snapshot = self._snapshot(run)
        snapshot["current_node"] = "save_run"
        snapshot["node_status"] = "SUCCEEDED"
        run.state_snapshot = dict(snapshot)
        self._append_event(
            run,
            "run_completed",
            status=TaskStatus.SUCCEEDED.value,
            answer=snapshot.get("answer"),
            citations=snapshot.get("citations", []),
        )
        self.session.commit()
        return result

    # ------------------------------------------------------------------
    # Node execution machinery (mirrors MatchRunService._run_node)
    # ------------------------------------------------------------------

    def _run_node(
        self,
        state: CareerAssistantQAState,
        node_name: str,
        action: Callable[[], dict[str, Any]],
    ) -> CareerAssistantQAState:
        run = self._run(int(state["run_id"]))
        if run.status == TaskStatus.CANCELLED:
            raise _RunCancelled
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
        snapshot["node_status"] = "RUNNING"
        run.status = TaskStatus.RUNNING
        run.state_snapshot = dict(snapshot)
        self._append_event(run, "node_started", node=node_name, status="RUNNING")
        self.session.commit()
        try:
            changes = action()
        except Exception as exc:
            self.session.rollback()
            if node_name == "generate_answer":
                self.session.add(
                    ModelUsageLog(
                        user_id=int(state["user_id"]),
                        agent_run_id=int(state["run_id"]),
                        provider=self.settings.dify_provider_mode,
                        model_name=self.settings.dify_knowledge_qa_workflow_version,
                        operation="career_assistant_qa",
                        prompt_version=CAREER_RAG_PROMPT_VERSION,
                        prompt_tokens=0,
                        completion_tokens=0,
                        latency_ms=max(0, int((perf_counter() - started_clock) * 1000)),
                        estimated_cost=None,
                        is_success=False,
                        error_code=self._error_code(exc),
                    )
                )
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
            snapshot["node_status"] = "FAILED"
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
        snapshot["node_status"] = "SUCCEEDED"
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
        )
        self.session.commit()
        return snapshot

    def _skip_node(
        self,
        state: CareerAssistantQAState,
        node_name: str,
        reason: str,
        *,
        extra_changes: dict[str, Any] | None = None,
    ) -> CareerAssistantQAState:
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
        if extra_changes:
            for key, value in extra_changes.items():
                snapshot[key] = value  # type: ignore[literal-required]
        completed = list(snapshot.get("completed_nodes", []))
        completed.append(node_name)
        snapshot["completed_nodes"] = list(dict.fromkeys(completed))
        snapshot["current_node"] = node_name
        snapshot["node_status"] = "SKIPPED"
        run.state_snapshot = dict(snapshot)
        self._append_event(
            run,
            "node_completed",
            node=node_name,
            status="SKIPPED",
            duration_ms=0,
            summary={"skipped": True, "reason": reason},
            answer=snapshot.get("answer"),
            citations=snapshot.get("citations", []),
        )
        self.session.commit()
        return snapshot

    # ------------------------------------------------------------------
    # Read models
    # ------------------------------------------------------------------

    def _read(self, run: AgentRun) -> CareerAssistantQARead:
        snapshot = self._snapshot(run)
        citations = [
            CareerAssistantQACitationRead.model_validate(item)
            for item in snapshot.get("citations", [])
        ]
        return CareerAssistantQARead(
            id=run.id,
            user_id=run.user_id,
            question=str(snapshot["question"]),
            answer=snapshot.get("answer"),
            status=run.status.value,
            citations=citations,
            error_code=run.error_code,
            error_message=run.error_message,
            created_at=run.created_at,
            finished_at=run.finished_at,
        )

    def _list_item(self, run: AgentRun) -> CareerAssistantQAListItemRead:
        snapshot = self._snapshot(run)
        return CareerAssistantQAListItemRead(
            id=run.id,
            question=str(snapshot["question"]),
            status=run.status.value,
            answer=snapshot.get("answer"),
            created_at=run.created_at,
            finished_at=run.finished_at,
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
        answer: str | None = None,
        citations: list[dict[str, Any]] | None = None,
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
                "answer": answer,
                "citations": citations or [],
            }
        )
        snapshot["events"] = events
        run.state_snapshot = dict(snapshot)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _retrieve_knowledge_with_coverage(
        self,
        index_service: KnowledgeIndexService,
        question: str,
    ) -> tuple[list[Any], dict[str, Any]]:
        """Retrieve the original question and deterministic entity subqueries.

        Single-topic questions retain the original search path. For questions
        naming at least two known entities, one highest-ranked matching chunk
        is reserved per entity before original-question results fill remaining
        context capacity. This increases coverage without changing the global
        similarity threshold or embedding model.
        """
        top_k = self.settings.knowledge_qa_top_k
        threshold = self.settings.knowledge_qa_similarity_threshold
        original_chunks = index_service.search(
            question,
            top_k=top_k,
            similarity_threshold=threshold,
        )
        entities = self._detect_query_entities(question)
        coverage: dict[str, Any] = {
            "requested_entities": [entity.name for entity in entities],
            "retrieved_entities": [],
            "missing_entities": [],
            "retrieval_queries": {},
        }
        if len(entities) < 2:
            return original_chunks, coverage

        per_entity_chunks: list[Any] = []
        # Search a broader candidate set per focused query so a multi-role
        # question about project evidence can select the relevant evidence
        # chunk rather than only a document's introductory chunk. This does
        # not relax score filtering; the final merged context remains bounded
        # by top_k.
        # The current knowledge base contains short, per-topic documents.
        # Thirty candidates covers their evidence sections without changing
        # the global threshold or the final five-chunk prompt budget.
        per_query_top_k = max(30, top_k)
        for entity in entities:
            subquery = f"{entity.focused_query}。原问题：{question}"
            coverage["retrieval_queries"][entity.name] = subquery
            candidates = index_service.search(
                subquery,
                top_k=per_query_top_k,
                similarity_threshold=threshold,
            )
            chunk = self._select_entity_chunk(candidates, entity, question)
            if chunk is None:
                coverage["missing_entities"].append(entity.name)
                continue
            per_entity_chunks.append(chunk)
            coverage["retrieved_entities"].append(entity.name)

        return self._merge_knowledge_chunks(
            per_entity_chunks, original_chunks, limit=top_k
        ), coverage

    @staticmethod
    def _detect_query_entities(question: str) -> list[_QueryEntity]:
        normalized = question.casefold()
        matched: list[tuple[int, _QueryEntity]] = []
        for entity in QUERY_ENTITIES:
            positions = [normalized.find(alias.casefold()) for alias in entity.aliases]
            positions = [position for position in positions if position >= 0]
            if positions:
                matched.append((min(positions), entity))
        return [entity for _, entity in sorted(matched, key=lambda item: item[0])]

    @staticmethod
    def _chunk_matches_entity(chunk: Any, entity: _QueryEntity) -> bool:
        title = str(getattr(chunk, "title", "")).casefold()
        return any(keyword.casefold() in title for keyword in entity.title_keywords)

    @classmethod
    def _select_entity_chunk(
        cls,
        candidates: list[Any],
        entity: _QueryEntity,
        question: str,
    ) -> Any | None:
        """Choose a directly relevant chunk for one known entity.

        For project-evidence questions, document introductions often describe
        the role but not the concrete project evidence that the user asked
        about. Prefer a title-matched chunk that explicitly discusses project
        evidence, while retaining the search score ordering for all other
        questions.
        """
        matching = [item for item in candidates if cls._chunk_matches_entity(item, entity)]
        if not matching:
            return None
        if not cls._question_requests_project_evidence(question):
            return matching[0]

        evidence_markers = ("项目", "作品", "案例", "证据", "展示")
        detailed_markers = ("例如", "示例", "可用于", "可以用", "准备")

        def evidence_rank(item: Any) -> tuple[int, float]:
            content = str(getattr(item, "chunk_text", ""))
            marker_hits = sum(marker in content for marker in evidence_markers)
            detail_hits = sum(marker in content for marker in detailed_markers)
            return (marker_hits * 2 + detail_hits, float(getattr(item, "score", 0.0)))

        return max(matching, key=evidence_rank)

    @staticmethod
    def _question_requests_project_evidence(question: str) -> bool:
        normalized = question.casefold()
        return any(
            marker in normalized
            for marker in ("项目", "作品", "案例", "证明能力", "能力证据", "portfolio")
        )

    @staticmethod
    def _merge_knowledge_chunks(
        entity_chunks: list[Any],
        original_chunks: list[Any],
        *,
        limit: int,
    ) -> list[Any]:
        """Merge by stable citation identity and avoid one document dominating."""
        merged: list[Any] = []
        seen_keys: set[tuple[int, int]] = set()
        document_counts: dict[int, int] = {}

        def add(chunk: Any, *, allow_second_chunk: bool) -> bool:
            key = (int(chunk.document_id), int(chunk.chunk_index))
            if key in seen_keys:
                return False
            count = document_counts.get(int(chunk.document_id), 0)
            if count and not allow_second_chunk:
                return False
            seen_keys.add(key)
            document_counts[int(chunk.document_id)] = count + 1
            merged.append(chunk)
            return True

        for chunk in entity_chunks:
            if len(merged) >= limit:
                return merged
            add(chunk, allow_second_chunk=True)
        for chunk in original_chunks:
            if len(merged) >= limit:
                break
            add(chunk, allow_second_chunk=False)
        # If the bounded result still has space, permit an adjacent chunk only
        # after every distinct-document candidate has been considered.
        for chunk in original_chunks:
            if len(merged) >= limit:
                break
            add(chunk, allow_second_chunk=True)
        return merged

    @staticmethod
    def _insufficient_evidence_message(question: str) -> str:
        return (
            INSUFFICIENT_EVIDENCE_MESSAGE_ZH
            if any("\u4e00" <= character <= "\u9fff" for character in question)
            else INSUFFICIENT_EVIDENCE_MESSAGE_EN
        )

    def _index_service(self) -> KnowledgeIndexService:
        if self._index_service_factory is not None:
            return self._index_service_factory(self.session)
        return KnowledgeIndexService(
            self.settings,
            embedding_provider_from_settings(self.settings),
            self.session,
        )

    def _provider(self) -> KnowledgeQAProvider:
        if self._provider_factory is not None:
            return self._provider_factory()
        return create_knowledge_qa_provider(self.settings)

    def _owned(self, run_id: int, user_id: int) -> AgentRun:
        run = self.session.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.user_id == user_id,
                AgentRun.run_type == RUN_TYPE,
            )
        )
        if run is None:
            raise AppError("CAREER_QA_RUN_NOT_FOUND", "The QA run was not found", 404)
        return run

    def _run(self, run_id: int) -> AgentRun:
        run = self.session.scalar(
            select(AgentRun).where(
                AgentRun.id == run_id,
                AgentRun.run_type == RUN_TYPE,
            )
        )
        if run is None:
            raise AppError("CAREER_QA_RUN_NOT_FOUND", "The QA run was not found", 404)
        return run

    @staticmethod
    def _enrich_citations(
        citation_keys: list[str],
        context_chunks: list[KnowledgeQAContextChunk],
        personal_chunks: list[PersonalContextChunk] | None = None,
    ) -> list[CareerAssistantQACitationRead]:
        """Merge provider citation keys with full chunk provenance.

        Citation keys are strings returned by the Dify workflow:
        - Knowledge chunks: ``"doc-<id>-chunk-<index>"``
        - Personal chunks (Stage 4B): ``"<source_type>-<source_id>-chunk-<index>"``
          e.g. ``"resume-12-chunk-0"``, ``"match_report-5-chunk-1"``.

        Each key is matched against the retrieval chunks to build a
        ``CareerAssistantQACitationRead`` with full provenance. Unknown
        keys are silently dropped.
        """
        knowledge_lookup: dict[str, KnowledgeQAContextChunk] = {
            f"doc-{chunk.document_id}-chunk-{chunk.chunk_index}": chunk for chunk in context_chunks
        }
        personal_lookup: dict[str, PersonalContextChunk] = {}
        for chunk in personal_chunks or []:
            key = f"{chunk.source_type}-{chunk.source_id}-chunk-{chunk.chunk_index}"
            personal_lookup[key] = chunk

        enriched: list[CareerAssistantQACitationRead] = []
        for key in citation_keys:
            k_chunk = knowledge_lookup.get(key)
            if k_chunk is not None:
                # Skip the synthetic placeholder chunk (document_id=0); it
                # exists only to satisfy the workflow input contract when
                # only personal context is available, not as a real citation.
                if k_chunk.document_id == 0:
                    continue
                enriched.append(
                    CareerAssistantQACitationRead(
                        source_type="knowledge",
                        source_id=k_chunk.document_id,
                        document_id=k_chunk.document_id,
                        title=k_chunk.title,
                        category=k_chunk.category,
                        chunk_index=k_chunk.chunk_index,
                        chunk_text=k_chunk.chunk_text,
                        quote="",
                        page_number=k_chunk.page_number,
                        paragraph_index=k_chunk.paragraph_index,
                        score=k_chunk.score,
                    )
                )
                continue
            p_chunk = personal_lookup.get(key)
            if p_chunk is not None:
                enriched.append(
                    CareerAssistantQACitationRead(
                        source_type=p_chunk.source_type,
                        source_id=p_chunk.source_id,
                        document_id=0,
                        title=p_chunk.title,
                        category=p_chunk.category,
                        chunk_index=p_chunk.chunk_index,
                        chunk_text=p_chunk.chunk_text,
                        quote="",
                        page_number=None,
                        paragraph_index=None,
                        score=p_chunk.score,
                    )
                )
        return enriched

    @staticmethod
    def _step(run: AgentRun, node_name: str) -> AgentStep:
        step = next((item for item in run.steps if item.node_name == node_name), None)
        if step is None:
            raise AppError("CAREER_QA_STEP_NOT_FOUND", "The workflow node was not found", 500)
        return step

    @staticmethod
    def _snapshot(run: AgentRun) -> CareerAssistantQAState:
        return dict(run.state_snapshot)  # type: ignore[return-value]

    @staticmethod
    def _error_code(exc: Exception) -> str:
        return exc.code if isinstance(exc, AppError) else "CAREER_QA_NODE_FAILED"

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        return exc.message if isinstance(exc, AppError) else "The workflow node failed"

    @staticmethod
    def _merge_state(
        target: CareerAssistantQAState,
        source: CareerAssistantQAState,
    ) -> None:
        for key, value in source.items():
            if key != "events":
                target[key] = value  # type: ignore[literal-required]
