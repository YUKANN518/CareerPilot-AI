from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.core.security import hash_password
from app.models.enums import TaskStatus, UserRole
from app.models.operations import AgentRun
from app.models.users import User, UserProfile
from app.schemas.match_runs import MatchRunCreate
from app.schemas.matching import MatchCreate
from app.semantic.embeddings import FakeEmbeddingProvider
from app.semantic.index import SemanticIndexService
from app.services.match_runs import MatchRunService
from app.services.matching import MatchService
from tests.test_matching import _create_case


def test_deterministic_graph_skips_semantic_waits_and_confirms(
    db_session: Session,
    admin_user: User,
) -> None:
    case = _create_case(db_session, admin_user, "high_match")
    service = MatchRunService(db_session)
    created = service.create(
        admin_user,
        MatchRunCreate(
            resume_version_id=case.version.id,
            job_id=case.job.id,
            scoring_version="deterministic-v1.1",
        ),
    )
    waiting = service.execute(created.run_id)
    assert waiting.status == "WAITING_REVIEW"
    assert waiting.waiting_for_user is True
    assert waiting.report_id is not None
    assert (
        next(step for step in waiting.steps if step.node_name == "semantic_retrieval").status
        == "SKIPPED"
    )
    assert [event.event for event in service.events(admin_user, created.run_id)] == [
        "run_started",
        "node_started",
        "node_completed",
        "node_started",
        "node_completed",
        "node_completed",
        "node_started",
        "node_completed",
        "node_started",
        "node_completed",
        "waiting_for_user",
    ]

    completed = service.confirm(admin_user, created.run_id)
    assert completed.status == "SUCCEEDED"
    assert completed.waiting_for_user is False
    assert completed.report_id == waiting.report_id
    assert service.events(admin_user, created.run_id)[-1].event == "run_completed"


def test_blocking_is_preserved_and_report_is_still_saved(
    db_session: Session,
    admin_user: User,
) -> None:
    case = _create_case(db_session, admin_user, "eligibility_blocked")
    service = MatchRunService(db_session)
    run = service.create(
        admin_user,
        MatchRunCreate(
            resume_version_id=case.version.id,
            job_id=case.job.id,
        ),
    )
    waiting = service.execute(run.run_id)
    assert waiting.report_id is not None
    assert waiting.blocking_risks
    report = service.confirm(admin_user, run.run_id)
    assert report.status == "SUCCEEDED"


def test_hybrid_graph_runs_semantic_node(
    db_session: Session,
    admin_user: User,
    test_settings: Settings,
    tmp_path: Path,
) -> None:
    case = _create_case(db_session, admin_user, "high_match")
    settings = test_settings.model_copy(
        update={"embedding_provider": "fake", "faiss_index_dir": str(tmp_path / "faiss")}
    )
    provider = FakeEmbeddingProvider()
    index = SemanticIndexService(settings, provider)
    service = MatchRunService(
        db_session,
        matching_service_factory=lambda session: MatchService(
            session,
            settings=settings,
            embedding_provider=provider,
            semantic_index=index,
        ),
    )
    run = service.create(
        admin_user,
        MatchRunCreate(
            resume_version_id=case.version.id,
            job_id=case.job.id,
            scoring_version="hybrid-v1",
        ),
    )
    waiting = service.execute(run.run_id)
    semantic = next(step for step in waiting.steps if step.node_name == "semantic_retrieval")
    assert semantic.status == "SUCCEEDED"
    assert waiting.semantic_score is not None
    assert waiting.hybrid_score is not None


def test_cancel_and_owner_isolation(
    db_session: Session,
    admin_user: User,
) -> None:
    case = _create_case(db_session, admin_user, "high_match")
    service = MatchRunService(db_session)
    run = service.create(
        admin_user,
        MatchRunCreate(
            resume_version_id=case.version.id,
            job_id=case.job.id,
        ),
    )
    cancelled = service.cancel(admin_user, run.run_id)
    assert cancelled.status == "CANCELLED"
    persisted = db_session.get(AgentRun, run.run_id)
    assert persisted is not None and persisted.status == TaskStatus.CANCELLED
    other = User(
        email="other-run-user@example.com",
        password_hash=hash_password("OtherPassword123!"),
        role=UserRole.USER,
        profile=UserProfile(display_name="Other"),
    )
    db_session.add(other)
    db_session.commit()
    with pytest.raises(AppError) as exc_info:
        service.get(other, run.run_id)
    assert exc_info.value.code == "MATCH_RUN_NOT_FOUND"


def test_two_runs_reuse_the_same_equivalent_report(
    db_session: Session,
    admin_user: User,
) -> None:
    case = _create_case(db_session, admin_user, "high_match")
    service = MatchRunService(db_session)
    payload = MatchRunCreate(
        resume_version_id=case.version.id,
        job_id=case.job.id,
    )
    first = service.execute(service.create(admin_user, payload).run_id)
    second = service.execute(service.create(admin_user, payload).run_id)
    assert first.report_id is not None
    assert second.report_id == first.report_id


def test_failed_node_can_retry_only_twice(
    db_session: Session,
    admin_user: User,
) -> None:
    case = _create_case(db_session, admin_user, "high_match")
    service = MatchRunService(db_session)
    run = service.create(
        admin_user,
        MatchRunCreate(
            resume_version_id=case.version.id,
            job_id=case.job.id,
        ),
    )

    class FailingMatchService(MatchService):
        def workflow_compute_deterministic(
            self,
            user: User,
            payload: MatchCreate,
        ) -> dict[str, Any]:
            raise RuntimeError("secret failure details")

    service.matching_service_factory = FailingMatchService
    failed = service.execute(run.run_id)
    assert failed.status == "FAILED"
    assert failed.error_message == "The workflow node failed"
    assert service.retry(admin_user, run.run_id).status == "FAILED"
    assert service.retry(admin_user, run.run_id).status == "FAILED"
    with pytest.raises(AppError) as retry_error:
        service.retry(admin_user, run.run_id)
    assert retry_error.value.code == "MATCH_RUN_RETRY_LIMIT"


async def test_match_run_api_sse_order(
    client: AsyncClient,
    db_session: Session,
    admin_user: User,
) -> None:
    case = _create_case(db_session, admin_user, "high_match")
    login = await client.post(
        "/api/auth/login",
        json={"email": admin_user.email, "password": "AdminPassword123!"},
    )
    headers = {"Authorization": f"Bearer {login.json()['data']['tokens']['access_token']}"}
    created = await client.post(
        "/api/match-runs",
        headers=headers,
        json={
            "resume_version_id": case.version.id,
            "job_id": case.job.id,
            "scoring_version": "deterministic-v1.1",
        },
    )
    assert created.status_code == 202
    run_id = created.json()["data"]["run_id"]
    waiting = await client.get(f"/api/match-runs/{run_id}", headers=headers)
    assert waiting.json()["data"]["status"] == "WAITING_REVIEW"
    confirmed = await client.post(f"/api/match-runs/{run_id}/confirm", headers=headers)
    assert confirmed.json()["data"]["run"]["status"] == "SUCCEEDED"
    ticket = await client.post(f"/api/match-runs/{run_id}/event-ticket", headers=headers)
    stream = await client.get(
        f"/api/match-runs/{run_id}/events",
        params={"ticket": ticket.json()["data"]["ticket"]},
    )
    assert stream.status_code == 200
    assert "event: run_started" in stream.text
    assert stream.text.index("event: run_started") < stream.text.index("event: run_completed")
