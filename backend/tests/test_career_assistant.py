"""Tests for Stage 4A Career Assistant knowledge QA.

Covers:
- KnowledgeIndexService (index, search, reuse, delete)
- FakeKnowledgeQAProvider (answer + citations)
- CareerAssistantQAService LangGraph (full run, insufficient-evidence
  short-circuit, ownership isolation, list, events)
- Career Assistant QA API (create, get, list, SSE stream, ownership 404)
- Admin knowledge document API (upload, list, get, delete, reindex,
  non-admin forbidden)
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from time import perf_counter, sleep
from typing import cast

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.integrations.dify.knowledge_qa_providers import (
    FakeKnowledgeQAProvider,
    _build_dify_workflow_input,
)
from app.models.enums import UserRole
from app.models.operations import AgentRun, KnowledgeDocument
from app.models.resumes import FileAsset
from app.models.users import User, UserProfile
from app.schemas.career_assistant import (
    CareerAssistantQACreate,
    KnowledgeQAContextChunk,
    KnowledgeQAWorkflowInput,
    PersonalContextChunk,
)
from app.semantic.embeddings import FakeEmbeddingProvider
from app.semantic.knowledge_index import KnowledgeChunk, KnowledgeIndexService
from app.services.career_assistant import CareerAssistantQAService

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _sample_pdf() -> bytes:
    return (FIXTURES / "sample_resume.pdf").read_bytes()


def _settings_with_faiss(test_settings: Settings, tmp_path: Path) -> Settings:
    return test_settings.model_copy(
        update={
            "embedding_provider": "fake",
            "faiss_index_dir": str(tmp_path / "faiss"),
            "knowledge_qa_similarity_threshold": -1.0,
            "knowledge_qa_top_k": 5,
        }
    )


def _create_file_asset(session: Session, owner_id: int, content: bytes) -> FileAsset:
    asset = FileAsset(
        owner_id=owner_id,
        storage_key=f"{owner_id}/test-knowledge.pdf",
        original_name="test-knowledge.pdf",
        mime_type="application/pdf",
        size_bytes=len(content),
        sha256="0" * 64,
        file_format="pdf",
    )
    session.add(asset)
    session.flush()
    return asset


def _create_document(
    session: Session,
    admin_id: int,
    file_asset_id: int,
    *,
    title: str = "Career Guide",
    category: str = "guide",
) -> KnowledgeDocument:
    document = KnowledgeDocument(
        uploaded_by_id=admin_id,
        file_asset_id=file_asset_id,
        title=title,
        category=category,
        status="PENDING",
        chunk_count=0,
        metadata_json={},
    )
    session.add(document)
    session.flush()
    return document


class _StubIndexService:
    """Deterministic index service for LangGraph/API tests.

    Returns predetermined chunks so tests do not depend on FAISS
    similarity scores with fake embeddings.
    """

    def __init__(
        self,
        chunks: list[KnowledgeChunk],
        *,
        query_chunks: dict[str, list[KnowledgeChunk]] | None = None,
    ) -> None:
        self._chunks = chunks
        self.query_chunks = query_chunks or {}
        self.queries: list[str] = []

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        similarity_threshold: float = 0.25,
        document_ids: list[int] | None = None,
    ) -> list[KnowledgeChunk]:
        self.queries.append(query)
        for prefix, chunks in self.query_chunks.items():
            if query.startswith(prefix):
                return chunks[:top_k]
        return self._chunks[:top_k]

    def delete_index(self, document_id: int) -> None:  # pragma: no cover
        pass


def _make_chunk(
    document_id: int = 1,
    *,
    title: str = "Career Guide",
    category: str = "guide",
    chunk_text: str = "Python is a versatile programming language for backend development.",
    chunk_index: int = 0,
    score: float = 0.9,
) -> KnowledgeChunk:
    return KnowledgeChunk(
        document_id=document_id,
        title=title,
        category=category,
        chunk_text=chunk_text,
        chunk_index=chunk_index,
        page_number=None,
        paragraph_index=None,
        score=score,
    )


def _regular_user(db_session: Session) -> User:
    user = User(
        email="user@example.com",
        password_hash=hash_password("UserPassword123!"),
        role=UserRole.USER,
        profile=UserProfile(display_name="User"),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


async def _wait_for_knowledge_document(
    client: AsyncClient,
    headers: dict[str, str],
    document_id: int,
) -> dict[str, object]:
    """Poll the public status API instead of assuming synchronous indexing."""
    for _ in range(80):
        response = await client.get(
            f"/api/admin/knowledge-documents/{document_id}",
            headers=headers,
        )
        assert response.status_code == 200
        document = response.json()["data"]
        if document["status"] in {"READY", "FAILED"}:
            return cast(dict[str, object], document)
        await asyncio.sleep(0.05)
    pytest.fail("Knowledge document did not reach a terminal state")


# ---------------------------------------------------------------------------
# KnowledgeIndexService tests
# ---------------------------------------------------------------------------


def test_knowledge_index_service_indexes_and_searches_document(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    settings = _settings_with_faiss(test_settings, tmp_path)
    storage_root = Path(settings.upload_directory)
    storage_root.mkdir(parents=True, exist_ok=True)
    content = _sample_pdf()
    (storage_root / f"{admin_user.id}").mkdir(parents=True, exist_ok=True)
    (storage_root / f"{admin_user.id}" / "test-knowledge.pdf").write_bytes(content)

    asset = _create_file_asset(db_session, admin_user.id, content)
    document = _create_document(db_session, admin_user.id, asset.id)
    provider = FakeEmbeddingProvider()
    service = KnowledgeIndexService(settings, provider, db_session)
    result = service.index_document(document)

    assert result.chunk_count > 0
    assert document.status == "READY"
    assert document.content_hash is not None
    assert document.index_path is not None
    assert document.indexed_at is not None

    chunks = service.search("Python backend development", top_k=5, similarity_threshold=-1.0)
    assert len(chunks) > 0
    assert all(chunk.document_id == document.id for chunk in chunks)


def test_knowledge_index_service_reuses_unchanged_document(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    settings = _settings_with_faiss(test_settings, tmp_path)
    storage_root = Path(settings.upload_directory)
    storage_root.mkdir(parents=True, exist_ok=True)
    content = _sample_pdf()
    (storage_root / f"{admin_user.id}").mkdir(parents=True, exist_ok=True)
    (storage_root / f"{admin_user.id}" / "test-knowledge.pdf").write_bytes(content)

    asset = _create_file_asset(db_session, admin_user.id, content)
    document = _create_document(db_session, admin_user.id, asset.id)
    service = KnowledgeIndexService(settings, FakeEmbeddingProvider(), db_session)

    first = service.index_document(document)
    assert first.reused is False

    second = service.index_document(document)
    assert second.reused is True
    assert second.chunk_count == first.chunk_count


def test_knowledge_index_service_deletes_index(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    settings = _settings_with_faiss(test_settings, tmp_path)
    storage_root = Path(settings.upload_directory)
    storage_root.mkdir(parents=True, exist_ok=True)
    content = _sample_pdf()
    (storage_root / f"{admin_user.id}").mkdir(parents=True, exist_ok=True)
    (storage_root / f"{admin_user.id}" / "test-knowledge.pdf").write_bytes(content)

    asset = _create_file_asset(db_session, admin_user.id, content)
    document = _create_document(db_session, admin_user.id, asset.id)
    service = KnowledgeIndexService(settings, FakeEmbeddingProvider(), db_session)
    service.index_document(document)

    service.delete_index(document.id)
    chunks = service.search("Python", top_k=5, similarity_threshold=-1.0)
    assert chunks == []


# ---------------------------------------------------------------------------
# FakeKnowledgeQAProvider tests
# ---------------------------------------------------------------------------


def test_fake_knowledge_qa_provider_returns_answer_and_citations() -> None:
    provider = FakeKnowledgeQAProvider()
    request = KnowledgeQAWorkflowInput(
        user_id=1,
        question="What is Python?",
        context_chunks=[
            KnowledgeQAContextChunk(
                document_id=1,
                title="Career Guide",
                category="guide",
                chunk_text="Python is a versatile programming language.",
                chunk_index=0,
                score=0.9,
            )
        ],
    )
    result = provider.answer_question(request)
    assert result.output.answer
    assert len(result.output.used_citation_keys) == 1
    assert result.output.used_citation_keys[0] == "doc-1-chunk-0"
    assert result.output.insufficient_evidence is False
    assert result.output.generation.provider == "fake"
    assert len(result.attempts) == 1
    assert result.attempts[0].status == "succeeded"


def test_dify_knowledge_qa_provider_projects_context_with_real_citation_keys() -> None:
    request = KnowledgeQAWorkflowInput(
        user_id=1,
        question="What is the acceptance code?",
        context_chunks=[
            KnowledgeQAContextChunk(
                document_id=7,
                title="Acceptance note",
                category="test",
                chunk_text="The acceptance code is CP-RAG-724.",
                chunk_index=2,
                score=0.91,
            )
        ],
        personal_context=[
            PersonalContextChunk(
                source_type="resume",
                source_id=4,
                title="Resume",
                category="summary",
                chunk_text="Candidate has Python experience.",
                chunk_index=0,
            )
        ],
    )

    # Exercise the same private adapter used by answer_question without making
    # a network call.  The Dify Code node consumes `context`, while the
    # backend still retains `context_chunks` as the canonical retrieval field.
    payload = _build_dify_workflow_input(request)
    assert payload["context"][0]["citation_key"] == "doc-7-chunk-2"
    assert payload["context"][0]["content"] == "The acceptance code is CP-RAG-724."
    assert payload["personal_context"][0]["citation_key"] == "resume-4-chunk-0"
    assert payload["personal_context"][0]["content"] == "Candidate has Python experience."


# ---------------------------------------------------------------------------
# CareerAssistantQAService LangGraph tests
# ---------------------------------------------------------------------------


def _service_with_stubs(
    session: Session,
    settings: Settings,
    *,
    chunks: list[KnowledgeChunk],
    query_chunks: dict[str, list[KnowledgeChunk]] | None = None,
) -> CareerAssistantQAService:
    stub = _StubIndexService(chunks, query_chunks=query_chunks)
    return CareerAssistantQAService(
        session,
        settings,
        index_service_factory=lambda _: cast(KnowledgeIndexService, stub),
        provider_factory=FakeKnowledgeQAProvider,
    )


def test_qa_full_run_with_chunks(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    chunks = [
        _make_chunk(),
        _make_chunk(chunk_index=1, chunk_text="FastAPI is a modern web framework."),
    ]
    service = _service_with_stubs(db_session, test_settings, chunks=chunks)
    created = service.create(admin_user, CareerAssistantQACreate(question="What is Python?"))
    result = service.execute(created.id)

    assert result.status == "SUCCEEDED"
    assert result.answer is not None
    assert len(result.citations) >= 1
    assert result.citations[0].document_id == 1
    assert result.error_code is None

    events = service.events(admin_user, created.id)
    event_names = [event.event for event in events]
    assert "run_started" in event_names
    assert "run_completed" in event_names


def test_qa_short_circuits_on_insufficient_evidence(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    service = _service_with_stubs(db_session, test_settings, chunks=[])
    created = service.create(admin_user, CareerAssistantQACreate(question="Obscure question"))
    result = service.execute(created.id)

    assert result.status == "SUCCEEDED"
    assert result.answer is not None
    assert "No relevant knowledge base content" in result.answer
    assert result.citations == []

    events = service.events(admin_user, created.id)
    generate_event = next(event for event in events if event.node == "generate_answer")
    assert generate_event.status == "SKIPPED"


def test_single_entity_question_uses_original_retrieval_only(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    """A single known entity must preserve the original one-query path."""
    stub = _StubIndexService([_make_chunk(title="软件开发岗位介绍与准备")])
    service = CareerAssistantQAService(
        db_session,
        test_settings,
        index_service_factory=lambda _: cast(KnowledgeIndexService, stub),
        provider_factory=FakeKnowledgeQAProvider,
    )
    created = service.create(
        admin_user,
        CareerAssistantQACreate(question="软件开发岗位如何准备？", scope="knowledge"),
    )
    service.execute(created.id)

    run = db_session.get(AgentRun, created.id)
    assert run is not None
    assert stub.queries == ["软件开发岗位如何准备？"]
    assert run.state_snapshot["requested_entities"] == ["软件开发"]
    assert run.state_snapshot["retrieved_entities"] == []


def test_three_entity_question_decomposes_and_merges_distinct_documents(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    """Each requested role receives a focused search and stable coverage."""
    dev = _make_chunk(17, title="软件开发岗位介绍与准备", chunk_index=0)
    data = _make_chunk(18, title="数据分析岗位介绍与准备", chunk_index=0)
    qa = _make_chunk(19, title="软件测试与 QA 岗位介绍", chunk_index=0)
    question = "软件开发、数据分析和 QA 分别适合用什么项目证明能力？"
    stub = _StubIndexService(
        [qa],
        query_chunks={
            "软件开发岗位": [dev],
            "数据分析岗位": [data],
            "软件测试 QA 岗位": [qa],
        },
    )
    service = CareerAssistantQAService(
        db_session,
        test_settings,
        index_service_factory=lambda _: cast(KnowledgeIndexService, stub),
        provider_factory=FakeKnowledgeQAProvider,
    )
    created = service.create(
        admin_user, CareerAssistantQACreate(question=question, scope="knowledge")
    )
    result = service.execute(created.id)

    run = db_session.get(AgentRun, created.id)
    assert run is not None
    assert run.state_snapshot["requested_entities"] == ["软件开发", "数据分析", "QA"]
    assert run.state_snapshot["retrieved_entities"] == ["软件开发", "数据分析", "QA"]
    assert run.state_snapshot["missing_entities"] == []
    assert [citation.document_id for citation in result.citations] == [17, 18, 19]
    assert len(stub.queries) == 4


def test_three_role_comparison_retrieves_each_role_document(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    support = _make_chunk(20, title="IT Support 岗位介绍", chunk_index=0)
    qa = _make_chunk(19, title="软件测试与 QA 岗位介绍", chunk_index=0)
    analyst = _make_chunk(21, title="Business Analyst 岗位介绍", chunk_index=0)
    stub = _StubIndexService(
        [],
        query_chunks={
            "IT Support 技术支持岗位": [support],
            "软件测试 QA 岗位": [qa],
            "Business Analyst 业务分析岗位": [analyst],
        },
    )
    service = CareerAssistantQAService(
        db_session,
        test_settings,
        index_service_factory=lambda _: cast(KnowledgeIndexService, stub),
        provider_factory=FakeKnowledgeQAProvider,
    )
    created = service.create(
        admin_user,
        CareerAssistantQACreate(
            question="IT Support、QA 和 Business Analyst 如何比较？",
            scope="knowledge",
        ),
    )
    result = service.execute(created.id)

    assert [citation.document_id for citation in result.citations] == [20, 19, 21]


def test_multi_entity_merge_deduplicates_citation_keys() -> None:
    chunk = _make_chunk(17, chunk_index=0)
    other = _make_chunk(18, chunk_index=0)
    merged = CareerAssistantQAService._merge_knowledge_chunks(
        [chunk, chunk],
        [chunk, other],
        limit=5,
    )
    assert [(item.document_id, item.chunk_index) for item in merged] == [(17, 0), (18, 0)]


def test_project_evidence_question_prefers_project_evidence_chunk() -> None:
    """Role introductions must not displace concrete project evidence."""
    introductory = _make_chunk(
        17,
        title="软件开发岗位介绍与准备",
        chunk_text="软件开发岗位的主要职责包括理解需求和交付可维护功能。",
        chunk_index=0,
        score=0.9,
    )
    project_evidence = _make_chunk(
        17,
        title="软件开发岗位介绍与准备",
        chunk_text="可用一个带 README、测试和部署说明的项目展示开发能力。",
        chunk_index=1,
        score=0.6,
    )
    selected = CareerAssistantQAService._select_entity_chunk(
        [introductory, project_evidence],
        CareerAssistantQAService._detect_query_entities("软件开发岗位")[0],
        "软件开发适合用什么项目证明能力？",
    )
    assert selected == project_evidence


def test_partial_entity_coverage_is_forwarded_to_dify_contract() -> None:
    request = KnowledgeQAWorkflowInput(
        user_id=1,
        question="IT Support、QA 和 Business Analyst 如何比较？",
        context_chunks=[
            KnowledgeQAContextChunk(
                document_id=20,
                title="IT Support 岗位介绍",
                category="it_roles",
                chunk_text="IT Support evidence.",
                chunk_index=0,
                score=0.9,
            )
        ],
        requested_entities=["IT Support", "QA", "Business Analyst"],
        retrieved_entities=["IT Support", "QA"],
        missing_entities=["Business Analyst"],
    )
    payload = _build_dify_workflow_input(request)
    assert payload["requested_entities"] == ["IT Support", "QA", "Business Analyst"]
    assert payload["retrieved_entities"] == ["IT Support", "QA"]
    assert payload["missing_entities"] == ["Business Analyst"]


def test_chinese_question_without_evidence_uses_chinese_fallback(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    service = _service_with_stubs(db_session, test_settings, chunks=[])
    created = service.create(
        admin_user,
        CareerAssistantQACreate(question="哪个岗位薪资最高？", scope="knowledge"),
    )
    result = service.execute(created.id)
    assert result.answer == "当前知识库中没有足够依据回答该问题。"


def test_qa_ownership_isolation(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    other = _regular_user(db_session)
    service = _service_with_stubs(db_session, test_settings, chunks=[_make_chunk()])
    created = service.create(admin_user, CareerAssistantQACreate(question="test"))

    with pytest.raises(AppError) as exc_info:
        service.get(other, created.id)
    assert exc_info.value.code == "CAREER_QA_RUN_NOT_FOUND"

    with pytest.raises(AppError) as exc_info:
        service.events(other, created.id)
    assert exc_info.value.code == "CAREER_QA_RUN_NOT_FOUND"


def test_qa_list_runs(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    service = _service_with_stubs(db_session, test_settings, chunks=[_make_chunk()])
    for index in range(3):
        created = service.create(
            admin_user,
            CareerAssistantQACreate(question=f"Question {index}"),
        )
        service.execute(created.id)

    result = service.list_user(admin_user, offset=0, limit=10)
    assert result.total == 3
    assert len(result.items) == 3
    assert result.items[0].question in {"Question 0", "Question 1", "Question 2"}


# ---------------------------------------------------------------------------
# Career Assistant QA API tests
# ---------------------------------------------------------------------------


async def test_qa_api_create_get_list(
    client: AsyncClient,
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    chunks = [_make_chunk()]
    stub = _StubIndexService(chunks)
    from app.core.config import get_settings
    from app.main import app

    original_override = app.dependency_overrides.get(get_settings)
    app.dependency_overrides[get_settings] = lambda: test_settings

    # Patch the service factories via a module-level monkey approach: we
    # cannot easily inject the stub through the API, so we verify the API
    # contract with the real (fake) pipeline. The test_settings already
    # forces dify_provider_mode=fake and embedding_provider=fake.
    login = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "AdminPassword123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['tokens']['access_token']}"}

    created = await client.post(
        "/api/career-assistant/qa",
        headers=headers,
        json={"question": "What is Python?"},
    )
    assert created.status_code == 202
    run_id = created.json()["data"]["id"]
    assert created.json()["data"]["status"] == "PENDING"

    # Execute synchronously via the service (background task won't run in tests)
    from app.db.session import get_db_session
    from app.services.career_assistant import CareerAssistantQAService as _Svc

    session_gen = app.dependency_overrides[get_db_session]()
    session = next(session_gen)
    svc = _Svc(
        session,
        test_settings,
        index_service_factory=lambda _: cast(KnowledgeIndexService, stub),
        provider_factory=FakeKnowledgeQAProvider,
    )
    svc.execute(run_id)

    fetched = await client.get(f"/api/career-assistant/qa/{run_id}", headers=headers)
    assert fetched.status_code == 200
    assert fetched.json()["data"]["status"] == "SUCCEEDED"
    assert fetched.json()["data"]["answer"] is not None

    listed = await client.get("/api/career-assistant/qa", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] >= 1

    if original_override is not None:
        app.dependency_overrides[get_settings] = original_override
    else:
        app.dependency_overrides.pop(get_settings, None)


async def test_qa_api_ownership_404(
    client: AsyncClient,
    db_session: Session,
    admin_user: User,
) -> None:
    other = _regular_user(db_session)
    admin_login = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "AdminPassword123!"},
    )
    admin_token = admin_login.json()["data"]["tokens"]["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    created = await client.post(
        "/api/career-assistant/qa",
        headers=admin_headers,
        json={"question": "Admin question"},
    )
    run_id = created.json()["data"]["id"]

    user_login = await client.post(
        "/api/auth/login",
        json={"email": other.email, "password": "UserPassword123!"},
    )
    user_token = user_login.json()["data"]["tokens"]["access_token"]
    user_headers = {"Authorization": f"Bearer {user_token}"}
    forbidden = await client.get(
        f"/api/career-assistant/qa/{run_id}",
        headers=user_headers,
    )
    assert forbidden.status_code == 404


async def test_qa_api_sse_stream(
    client: AsyncClient,
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    chunks = [_make_chunk()]
    stub = _StubIndexService(chunks)
    from app.core.config import get_settings
    from app.db.session import get_db_session
    from app.main import app
    from app.services.career_assistant import CareerAssistantQAService as _Svc

    original_override = app.dependency_overrides.get(get_settings)
    app.dependency_overrides[get_settings] = lambda: test_settings

    login = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "AdminPassword123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['tokens']['access_token']}"}
    created = await client.post(
        "/api/career-assistant/qa",
        headers=headers,
        json={"question": "What is Python?"},
    )
    run_id = created.json()["data"]["id"]

    session_gen = app.dependency_overrides[get_db_session]()
    session = next(session_gen)
    svc = _Svc(
        session,
        test_settings,
        index_service_factory=lambda _: cast(KnowledgeIndexService, stub),
        provider_factory=FakeKnowledgeQAProvider,
    )
    svc.execute(run_id)

    ticket = await client.post(
        f"/api/career-assistant/qa/{run_id}/event-ticket",
        headers=headers,
    )
    assert ticket.status_code == 200
    ticket_value = ticket.json()["data"]["ticket"]

    stream = await client.get(
        f"/api/career-assistant/qa/{run_id}/events",
        params={"ticket": ticket_value},
    )
    assert stream.status_code == 200
    assert "event: run_started" in stream.text
    assert "event: run_completed" in stream.text

    if original_override is not None:
        app.dependency_overrides[get_settings] = original_override
    else:
        app.dependency_overrides.pop(get_settings, None)


# ---------------------------------------------------------------------------
# Stage 4B: Personal context retrieval + personalised QA tests
# ---------------------------------------------------------------------------

import secrets  # noqa: E402

from app.models.applications import Application  # noqa: E402
from app.models.enums import ApplicationStatus  # noqa: E402
from app.models.jobs import Job  # noqa: E402
from app.models.matching import MatchReport  # noqa: E402
from app.models.resumes import Resume, ResumeVersion  # noqa: E402
from app.services.personal_context import PersonalContextService  # noqa: E402


def _create_job(
    session: Session,
    *,
    owner_id: int | None = None,
    title: str = "Backend Engineer",
    company: str = "Acme Corp",
) -> Job:
    """Create a minimal Job row to satisfy FK constraints."""
    job = Job(
        owner_id=owner_id,
        title=title,
        company=company,
        description="A test job posting.",
        content_hash=secrets.token_hex(32),
        raw_data={},
        status="ACTIVE",
    )
    session.add(job)
    session.commit()
    session.refresh(job)
    return job


def _create_resume_with_version(
    session: Session,
    user_id: int,
    *,
    title: str = "My Resume",
    full_name: str = "Test Candidate",
    summary: str = "Backend engineer with Python experience.",
    skills: list[str] | None = None,
) -> ResumeVersion:
    resume = Resume(owner_id=user_id, title=title)
    session.add(resume)
    session.flush()
    skills = skills or ["Python", "FastAPI"]
    structured = {
        "basic_info": {
            "full_name": {"value": full_name},
            "summary": {"value": summary},
        },
        "technical_skills": [{"name": {"value": s}} for s in skills],
        "work_experience": [
            {
                "company": {"value": "Acme Corp"},
                "title": {"value": "Engineer"},
                "description": {"value": "Built Python services."},
            }
        ],
        "education": [],
    }
    version = ResumeVersion(
        resume_id=resume.id,
        version_number=1,
        structured_data=structured,
        is_current=True,
        is_confirmed=True,
    )
    session.add(version)
    session.commit()
    session.refresh(version)
    return version


def _create_match_report(
    session: Session,
    user_id: int,
    resume_version_id: int,
    *,
    final_score: float = 0.85,
) -> MatchReport:
    job = _create_job(session)
    report = MatchReport(
        user_id=user_id,
        resume_version_id=resume_version_id,
        job_id=job.id,
        status="SUCCEEDED",
        final_score=final_score,
        scoring_version="deterministic-v1.1",
        matched_skills=[{"name": "Python"}, {"name": "FastAPI"}],
        partial_skills=[{"name": "SQL"}],
        missing_skills=[{"name": "Rust"}],
        recommendation_level="RECOMMENDED",
        explanation="Strong Python backend match.",
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    return report


def _create_application(
    session: Session,
    user_id: int,
    *,
    status: ApplicationStatus = ApplicationStatus.SAVED,
) -> Application:
    job = _create_job(session, owner_id=user_id)
    app = Application(
        user_id=user_id,
        job_id=job.id,
        status=status,
        notes="Excited about this role.",
    )
    session.add(app)
    session.commit()
    session.refresh(app)
    return app


def test_personal_context_service_retrieves_resume(
    db_session: Session,
    admin_user: User,
) -> None:
    _create_resume_with_version(db_session, admin_user.id, skills=["Python", "Go"])
    service = PersonalContextService(db_session)
    chunks = service.retrieve(admin_user.id, "What are my skills?")
    resume_chunks = [c for c in chunks if c.source_type == "resume"]
    assert len(resume_chunks) == 1
    assert "Python" in resume_chunks[0].chunk_text
    assert "Go" in resume_chunks[0].chunk_text


def test_personal_context_service_retrieves_match_report(
    db_session: Session,
    admin_user: User,
) -> None:
    version = _create_resume_with_version(db_session, admin_user.id)
    _create_match_report(db_session, admin_user.id, version.id)
    service = PersonalContextService(db_session)
    chunks = service.retrieve(admin_user.id, "How did I match?")
    match_chunks = [c for c in chunks if c.source_type == "match_report"]
    assert len(match_chunks) == 1
    assert "Python" in match_chunks[0].chunk_text
    assert "Rust" in match_chunks[0].chunk_text


def test_personal_context_service_retrieves_application(
    db_session: Session,
    admin_user: User,
) -> None:
    _create_application(db_session, admin_user.id)
    service = PersonalContextService(db_session)
    chunks = service.retrieve(admin_user.id, "What jobs did I apply to?")
    app_chunks = [c for c in chunks if c.source_type == "application"]
    assert len(app_chunks) == 1
    assert "Application" in app_chunks[0].chunk_text


def test_personal_context_service_owner_isolation(
    db_session: Session,
    admin_user: User,
) -> None:
    """Personal context must only return data owned by the given user."""
    other = _regular_user(db_session)
    _create_resume_with_version(db_session, admin_user.id, full_name="Admin User")
    _create_resume_with_version(db_session, other.id, full_name="Other User", title="Other Resume")
    service = PersonalContextService(db_session)
    chunks = service.retrieve(admin_user.id, "What is my name?")
    assert all("Other User" not in c.chunk_text for c in chunks)
    assert any("Admin User" in c.chunk_text for c in chunks)


def test_personal_context_service_returns_at_most_10(
    db_session: Session,
    admin_user: User,
) -> None:
    for _i in range(15):
        _create_application(db_session, admin_user.id)
    service = PersonalContextService(db_session)
    chunks = service.retrieve(admin_user.id, "applications?")
    assert len(chunks) <= 10


def test_qa_scope_personal_skips_knowledge_retrieval(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    """scope=personal must skip knowledge retrieval and still answer."""
    _create_resume_with_version(db_session, admin_user.id)
    service = _service_with_stubs(db_session, test_settings, chunks=[])
    created = service.create(
        admin_user,
        CareerAssistantQACreate(question="What are my skills?", scope="personal"),
    )
    result = service.execute(created.id)

    assert result.status == "SUCCEEDED"
    assert result.answer is not None
    events = service.events(admin_user, created.id)
    knowledge_event = next(e for e in events if e.node == "retrieve_knowledge")
    assert knowledge_event.status == "SKIPPED"
    # retrieve_personal_context runs (not skipped), so it has both
    # node_started and node_completed events; pick the completed one.
    personal_events = [e for e in events if e.node == "retrieve_personal_context"]
    personal_completed = next(e for e in personal_events if e.event == "node_completed")
    assert personal_completed.status == "SUCCEEDED"


def test_qa_scope_knowledge_skips_personal_retrieval(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    """scope=knowledge must skip personal retrieval."""
    _create_resume_with_version(db_session, admin_user.id)
    service = _service_with_stubs(db_session, test_settings, chunks=[_make_chunk()])
    created = service.create(
        admin_user,
        CareerAssistantQACreate(question="What is Python?", scope="knowledge"),
    )
    result = service.execute(created.id)

    assert result.status == "SUCCEEDED"
    events = service.events(admin_user, created.id)
    personal_event = next(e for e in events if e.node == "retrieve_personal_context")
    assert personal_event.status == "SKIPPED"


def test_qa_scope_auto_uses_both_sources(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    """scope=auto must run both retrieval sources and cite both."""
    _create_resume_with_version(db_session, admin_user.id, skills=["Python"])
    service = _service_with_stubs(db_session, test_settings, chunks=[_make_chunk()])
    created = service.create(
        admin_user,
        CareerAssistantQACreate(question="What is Python?", scope="auto"),
    )
    result = service.execute(created.id)

    assert result.status == "SUCCEEDED"
    citation_types = {c.source_type for c in result.citations}
    assert "knowledge" in citation_types
    assert "resume" in citation_types


def test_qa_personal_citation_has_correct_provenance(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    """Personal citations must carry source_type, source_id, document_id=0."""
    version = _create_resume_with_version(db_session, admin_user.id)
    service = _service_with_stubs(db_session, test_settings, chunks=[_make_chunk()])
    created = service.create(
        admin_user,
        CareerAssistantQACreate(question="My resume?", scope="auto"),
    )
    result = service.execute(created.id)

    resume_citations = [c for c in result.citations if c.source_type == "resume"]
    assert len(resume_citations) == 1
    assert resume_citations[0].source_id == version.id
    assert resume_citations[0].document_id == 0
    assert resume_citations[0].title == "My Resume"


def test_enrich_citations_handles_mixed_keys() -> None:
    """_enrich_citations must resolve both knowledge and personal keys."""
    k_chunk = KnowledgeQAContextChunk(
        document_id=5,
        title="KB Doc",
        category="guide",
        chunk_text="Knowledge text.",
        chunk_index=0,
        score=0.9,
    )
    p_chunk = PersonalContextChunk(
        source_type="resume",
        source_id=12,
        title="My Resume",
        category="resume",
        chunk_text="Resume text.",
        chunk_index=0,
    )
    keys = ["doc-5-chunk-0", "resume-12-chunk-0", "unknown-key"]
    result = CareerAssistantQAService._enrich_citations(keys, [k_chunk], [p_chunk])
    assert len(result) == 2
    assert result[0].source_type == "knowledge"
    assert result[0].document_id == 5
    assert result[1].source_type == "resume"
    assert result[1].source_id == 12


def test_qa_scope_personal_with_no_personal_data_short_circuits(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    """scope=personal with no user data must short-circuit to insufficient evidence."""
    service = _service_with_stubs(db_session, test_settings, chunks=[])
    created = service.create(
        admin_user,
        CareerAssistantQACreate(question="My skills?", scope="personal"),
    )
    result = service.execute(created.id)

    assert result.status == "SUCCEEDED"
    assert "No relevant knowledge base content" in (result.answer or "")
    assert result.citations == []


async def test_qa_api_accepts_scope_field(
    client: AsyncClient,
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
) -> None:
    """POST /qa must accept the optional scope field without error."""
    _create_resume_with_version(db_session, admin_user.id)
    from app.core.config import get_settings
    from app.main import app

    original_override = app.dependency_overrides.get(get_settings)
    app.dependency_overrides[get_settings] = lambda: test_settings

    login = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "AdminPassword123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['tokens']['access_token']}"}

    response = await client.post(
        "/api/career-assistant/qa",
        json={"question": "What are my skills?", "scope": "personal"},
        headers=headers,
    )
    assert response.status_code == 202
    run_id = response.json()["data"]["id"]

    import asyncio as _asyncio

    get_resp = None
    for _ in range(40):
        get_resp = await client.get(
            f"/api/career-assistant/qa/{run_id}",
            headers=headers,
        )
        status = get_resp.json()["data"]["status"]
        if status in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            break
        await _asyncio.sleep(0.25)

    assert get_resp is not None
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["status"] == "SUCCEEDED"

    if original_override is not None:
        app.dependency_overrides[get_settings] = original_override
    else:
        app.dependency_overrides.pop(get_settings, None)


# ---------------------------------------------------------------------------
# Admin knowledge document API tests
# ---------------------------------------------------------------------------


async def test_admin_knowledge_documents_upload_list_get_delete(
    client: AsyncClient,
    db_session: Session,
    admin_user: User,
) -> None:
    login = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "AdminPassword123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['tokens']['access_token']}"}
    content = _sample_pdf()

    started = perf_counter()
    uploaded = await client.post(
        "/api/admin/knowledge-documents",
        headers=headers,
        files={"file": ("guide.pdf", content, "application/pdf")},
        data={"title": "Career Guide", "category": "guide"},
    )
    assert uploaded.status_code == 202
    assert perf_counter() - started < 1.0
    doc = uploaded.json()["data"]
    assert doc["title"] == "Career Guide"
    assert doc["category"] == "guide"
    assert doc["status"] == "PENDING"
    assert doc["chunk_count"] == 0
    document_id = doc["id"]

    completed = await _wait_for_knowledge_document(client, headers, document_id)
    assert completed["status"] == "READY"
    assert int(cast(int, completed["chunk_count"])) > 0

    listed = await client.get("/api/admin/knowledge-documents", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] >= 1

    fetched = await client.get(
        f"/api/admin/knowledge-documents/{document_id}",
        headers=headers,
    )
    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == document_id

    deleted = await client.delete(
        f"/api/admin/knowledge-documents/{document_id}",
        headers=headers,
    )
    assert deleted.status_code == 204

    missing = await client.get(
        f"/api/admin/knowledge-documents/{document_id}",
        headers=headers,
    )
    assert missing.status_code == 404


async def test_admin_knowledge_documents_reindex(
    client: AsyncClient,
    db_session: Session,
    admin_user: User,
) -> None:
    login = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "AdminPassword123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['tokens']['access_token']}"}
    content = _sample_pdf()
    uploaded = await client.post(
        "/api/admin/knowledge-documents",
        headers=headers,
        files={"file": ("guide.pdf", content, "application/pdf")},
        data={"title": "Career Guide", "category": "guide"},
    )
    assert uploaded.status_code == 202
    document_id = uploaded.json()["data"]["id"]
    first = await _wait_for_knowledge_document(client, headers, document_id)
    first_chunk_count = int(cast(int, first["chunk_count"]))

    reindexed = await client.post(
        f"/api/admin/knowledge-documents/{document_id}/reindex",
        headers=headers,
    )
    assert reindexed.status_code == 202
    assert reindexed.json()["data"]["status"] == "PENDING"
    completed = await _wait_for_knowledge_document(client, headers, document_id)
    assert completed["status"] == "READY"
    assert int(cast(int, completed["chunk_count"])) == first_chunk_count


async def test_knowledge_document_index_failure_is_safe_and_retryable(
    client: AsyncClient,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Background failures are persisted without exposing internal details."""
    login = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "AdminPassword123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['tokens']['access_token']}"}

    def fail_index(*_args: object, **_kwargs: object) -> object:
        raise AppError("EMBEDDING_FAILED", "secret-token /absolute/private/path", 503)

    monkeypatch.setattr(KnowledgeIndexService, "index_document", fail_index)
    uploaded = await client.post(
        "/api/admin/knowledge-documents",
        headers=headers,
        files={"file": ("guide.pdf", _sample_pdf(), "application/pdf")},
        data={"title": "Failure Guide", "category": "guide"},
    )
    assert uploaded.status_code == 202
    document_id = uploaded.json()["data"]["id"]

    failed = await _wait_for_knowledge_document(client, headers, document_id)
    assert failed["status"] == "FAILED"
    assert failed["error_code"] == "EMBEDDING_FAILED"
    assert failed["error_message"] == "The knowledge document index could not be built"
    assert "secret-token" not in str(failed["error_message"])
    assert "private/path" not in str(failed["error_message"])


async def test_knowledge_index_does_not_block_other_api_requests(
    client: AsyncClient,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A slow index worker must not hold up status requests on the API."""
    original = KnowledgeIndexService.index_document

    def slow_index(*args: object, **kwargs: object) -> object:
        sleep(0.35)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(KnowledgeIndexService, "index_document", slow_index)
    login = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "AdminPassword123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['tokens']['access_token']}"}
    uploaded = await client.post(
        "/api/admin/knowledge-documents",
        headers=headers,
        files={"file": ("guide.pdf", _sample_pdf(), "application/pdf")},
        data={"title": "Slow Guide", "category": "guide"},
    )
    assert uploaded.status_code == 202
    document_id = uploaded.json()["data"]["id"]

    started = perf_counter()
    listed = await client.get("/api/admin/knowledge-documents", headers=headers)
    assert perf_counter() - started < 0.25
    assert listed.status_code == 200
    assert any(item["id"] == document_id for item in listed.json()["data"]["items"])
    completed = await _wait_for_knowledge_document(client, headers, document_id)
    assert completed["status"] == "READY"


async def test_knowledge_document_reindex_rejects_duplicate_queueing(
    client: AsyncClient,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = KnowledgeIndexService.index_document

    def slow_index(*args: object, **kwargs: object) -> object:
        sleep(0.2)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(KnowledgeIndexService, "index_document", slow_index)
    login = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "AdminPassword123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['tokens']['access_token']}"}
    uploaded = await client.post(
        "/api/admin/knowledge-documents",
        headers=headers,
        files={"file": ("guide.pdf", _sample_pdf(), "application/pdf")},
        data={"title": "Retry Guide", "category": "guide"},
    )
    document_id = uploaded.json()["data"]["id"]
    await _wait_for_knowledge_document(client, headers, document_id)

    first = await client.post(
        f"/api/admin/knowledge-documents/{document_id}/reindex", headers=headers
    )
    second = await client.post(
        f"/api/admin/knowledge-documents/{document_id}/reindex", headers=headers
    )
    assert first.status_code == 202
    assert second.status_code == 409
    completed = await _wait_for_knowledge_document(client, headers, document_id)
    assert completed["status"] == "READY"


async def test_admin_knowledge_documents_non_admin_forbidden(
    client: AsyncClient,
    db_session: Session,
) -> None:
    other = _regular_user(db_session)
    login = await client.post(
        "/api/auth/login",
        json={"email": other.email, "password": "UserPassword123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['tokens']['access_token']}"}
    content = _sample_pdf()
    response = await client.post(
        "/api/admin/knowledge-documents",
        headers=headers,
        files={"file": ("guide.pdf", content, "application/pdf")},
        data={"title": "Career Guide", "category": "guide"},
    )
    assert response.status_code == 403
