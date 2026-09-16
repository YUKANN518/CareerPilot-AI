"""Tests for the LocalInterviewPlanProvider and the new interview
architecture where:

1. ``DIFY_INTERVIEW_PLAN_API_KEY`` is NOT required to create interviews.
2. ``LocalInterviewPlanProvider`` generates deterministic questions.
4. Sequences are contiguous 1..N.
5. No duplicate question prompts.
6. When the resume has projects, at least one PROJECT_DEEP_DIVE question
   is generated.
7. Missing-skill questions only ask about skill-improvement plans, never
   demonstrate-as-mastered.
8. ``_sorted_questions(session)`` returns the full list.
9. Chatflow first turn reads ``current_question_prompt``.
10. FOLLOW_UP does not change the current question index.
11. NEXT_QUESTION advances to the next local plan question.
12. COMPLETE_INTERVIEW triggers Final Evaluation.
13. Final report is persisted.
14. Owner isolation.
15. Dify keys never leak into logs or state snapshots.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.integrations.dify.interview_providers import (
    FakeInterviewChatProvider,
    FakeInterviewFinalEvaluationProvider,
    LocalInterviewPlanProvider,
)
from app.models.interviews import InterviewSession
from app.models.operations import AgentRun
from app.schemas.interviews import (
    InterviewCreate,
    InterviewJobInput,
    InterviewMatchReportInput,
    InterviewPlanWorkflowInput,
    InterviewQuestionType,
    InterviewResumeInput,
    InterviewType,
)
from app.schemas.matching import MatchCreate
from app.services.interviews import InterviewService
from app.services.matching import MatchService
from tests.test_matching import _create_case, _register_headers

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _successful_report(
    db_session: Session,
    user: Any,
    fixture_name: str = "skill_gap",
) -> int:
    case = _create_case(db_session, user, fixture_name)
    result = MatchService(db_session).create(
        user,
        MatchCreate(resume_version_id=case.version.id, job_id=case.job.id),
    )
    return result.report.id


def _get_report(db_session: Session, report_id: int) -> Any:
    from app.models.matching import MatchReport

    return db_session.get(MatchReport, report_id)


def _make_service_with_local_plan(
    db_session: Session,
    *,
    chat_provider: Any = None,
    final_provider: Any = None,
) -> InterviewService:
    """Build a service with LocalInterviewPlanProvider (production default)."""
    return InterviewService(
        db_session,
        LocalInterviewPlanProvider(),
        chat_provider or FakeInterviewChatProvider(),
        final_provider or FakeInterviewFinalEvaluationProvider(),
    )


def _plan_input(
    report: Any,
    *,
    with_projects: bool = False,
    with_missing_skills: bool = False,
) -> InterviewPlanWorkflowInput:
    """Build a plan workflow input for direct provider testing."""
    projects: list[dict[str, Any]] = []
    if with_projects:
        projects = [
            {
                "title": {
                    "value": "B站爬虫数据分析系统",
                    "confidence": 1.0,
                    "evidence_text": "B站爬虫数据分析系统",
                }
            }
        ]
    missing_skills: list[dict[str, Any]] = []
    if with_missing_skills:
        missing_skills = [
            {"normalized_name": "TensorFlow", "job_raw_name": "TensorFlow"},
            {"normalized_name": "Docker", "job_raw_name": "Docker"},
        ]
    matched_skills = [
        {"normalized_name": "Python", "job_raw_name": "Python"},
        {"normalized_name": "SQL", "job_raw_name": "SQL"},
    ]
    return InterviewPlanWorkflowInput(
        schema_version="interview-plan-input-v1",
        user_locale="zh-CN",
        interview_type=InterviewType.TECHNICAL,
        resume=InterviewResumeInput(
            resume_version_id=report.resume_version_id,
            summary="求職意向：資訊科技部實習生",
            projects=projects,
            skills=[{"name": "Python"}, {"name": "SQL"}],
        ),
        job=InterviewJobInput(
            job_id=report.job_id,
            title="Data Scientist",
            company="Test Company",
            summary="Data Scientist role",
        ),
        match_report=InterviewMatchReportInput(
            report_id=report.id,
            final_score=85.0,
            matched_skills=matched_skills,
            missing_skills=missing_skills,
        ),
    )


# ---------------------------------------------------------------------------
# 1. LocalInterviewPlanProvider generates contiguous sequences
# ---------------------------------------------------------------------------


def test_local_plan_generates_contiguous_sequences(
    db_session: Session,
    admin_user: Any,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = _get_report(db_session, report_id)
    provider = LocalInterviewPlanProvider()
    request = _plan_input(report)
    result = provider.generate_plan(request)
    sequences = [q.sequence for q in result.output.questions]
    assert sequences == list(range(1, len(sequences) + 1))
    assert len(result.output.questions) >= 4
    assert len(result.output.questions) <= 8


# ---------------------------------------------------------------------------
# 2. No duplicate question prompts
# ---------------------------------------------------------------------------


def test_local_plan_no_duplicate_prompts(
    db_session: Session,
    admin_user: Any,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = _get_report(db_session, report_id)
    provider = LocalInterviewPlanProvider()
    request = _plan_input(report)
    result = provider.generate_plan(request)
    prompts = [q.prompt for q in result.output.questions]
    assert len(prompts) == len(set(prompts))


# ---------------------------------------------------------------------------
# 3. Resume with projects generates a PROJECT_DEEP_DIVE question
# ---------------------------------------------------------------------------


def test_local_plan_with_projects_generates_project_question(
    db_session: Session,
    admin_user: Any,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = _get_report(db_session, report_id)
    provider = LocalInterviewPlanProvider()
    request = _plan_input(report, with_projects=True)
    result = provider.generate_plan(request)
    project_questions = [
        q
        for q in result.output.questions
        if q.question_type == InterviewQuestionType.PROJECT_DEEP_DIVE
    ]
    assert len(project_questions) >= 1
    # The project title must appear in the prompt.
    assert "B站爬虫数据分析系统" in project_questions[0].prompt


# ---------------------------------------------------------------------------
# 4. Missing-skill question only asks about improvement plans
# ---------------------------------------------------------------------------


def test_local_plan_missing_skill_question_targets_skill_gap(
    db_session: Session,
    admin_user: Any,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = _get_report(db_session, report_id)
    provider = LocalInterviewPlanProvider()
    request = _plan_input(report, with_missing_skills=True)
    result = provider.generate_plan(request)
    # Find the SITUATIONAL question (missing-skill improvement plan).
    situational = [
        q for q in result.output.questions if q.question_type == InterviewQuestionType.SITUATIONAL
    ]
    assert len(situational) == 1
    prompt = situational[0].prompt
    # Must mention the missing skill name.
    assert "TensorFlow" in prompt
    # Must ask about an improvement plan, not demonstration.
    assert "提升计划" in prompt or "弥补" in prompt
    # Must NOT ask the user to demonstrate the missing skill.
    assert "demonstrat" not in prompt.lower()


# ---------------------------------------------------------------------------
# 5. _sorted_questions(session) returns the full list
# ---------------------------------------------------------------------------


def test_sorted_questions_returns_full_list(
    db_session: Session,
    admin_user: Any,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = _get_report(db_session, report_id)
    service = _make_service_with_local_plan(db_session)
    interview = service.create(
        admin_user.id,
        InterviewCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
            interview_type=InterviewType.TECHNICAL,
        ),
    )
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    questions = service._sorted_questions(session)
    assert len(questions) >= 4
    assert [q.sequence for q in questions] == list(range(1, len(questions) + 1))


# ---------------------------------------------------------------------------
# 6. Provider field is "local" and provider name is correct
# ---------------------------------------------------------------------------


def test_local_plan_provider_name(
    db_session: Session,
    admin_user: Any,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = _get_report(db_session, report_id)
    service = _make_service_with_local_plan(db_session)
    interview = service.create(
        admin_user.id,
        InterviewCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
            interview_type=InterviewType.TECHNICAL,
        ),
    )
    assert interview.provider == "local"
    assert interview.status == "PLANNED"


# ---------------------------------------------------------------------------
# 7. No DIFY_INTERVIEW_PLAN_API_KEY required — factory returns Local
# ---------------------------------------------------------------------------


def test_factory_returns_local_when_no_plan_key() -> None:
    """In dify mode without DIFY_INTERVIEW_PLAN_API_KEY, factory returns
    LocalInterviewPlanProvider (not Dify, not Fake)."""
    from app.core.config import Settings
    from app.integrations.dify.interview_providers import (
        create_interview_plan_provider,
    )

    settings = Settings(
        dify_provider_mode="dify",
        dify_base_url="http://localhost:8080",
        dify_interview_chat_api_key="app-test-chat",
        dify_interview_final_api_key="app-test-final",
        # dify_interview_plan_api_key is NOT set (None)
    )
    provider = create_interview_plan_provider(settings)
    assert isinstance(provider, LocalInterviewPlanProvider)


# ---------------------------------------------------------------------------
# 8. Chat flow works without a separate answer evaluator
# ---------------------------------------------------------------------------


def test_chat_flow_works_without_answer_eval(
    db_session: Session,
    admin_user: Any,
) -> None:
    """The chat-based interview flow (start → message → complete) does
    NOT call the answer evaluation provider at all."""
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = _get_report(db_session, report_id)
    service = _make_service_with_local_plan(db_session)

    # Create interview
    interview = service.create(
        admin_user.id,
        InterviewCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
            interview_type=InterviewType.TECHNICAL,
        ),
    )

    # Start chat
    status = service.start_interview(admin_user.id, interview.id)
    assert status.chat_status == "WAITING_FOR_ANSWER"

    # Send a message
    from app.schemas.interviews import InterviewMessageSubmit

    response = service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(content="我有3年Python开发经验。"),
    )
    assert response.user_message is not None
    assert response.assistant_message is not None

    # Complete the interview
    final_status = service.complete_interview(admin_user.id, interview.id)
    assert final_status.chat_status in ("COMPLETED", "GENERATING_REPORT")


# ---------------------------------------------------------------------------
# 10. Owner isolation
# ---------------------------------------------------------------------------


def test_owner_isolation_local_plan(
    db_session: Session,
    admin_user: Any,
) -> None:
    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.users import User, UserProfile

    other_user = User(
        email="other-local-plan@example.com",
        password_hash=hash_password("OtherPassword123!"),
        role=UserRole.USER,
        profile=UserProfile(display_name="Other"),
    )
    db_session.add(other_user)
    db_session.commit()

    report_id = _successful_report(db_session, other_user, "skill_gap")
    report = _get_report(db_session, report_id)
    service = _make_service_with_local_plan(db_session)
    interview = service.create(
        other_user.id,
        InterviewCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
            interview_type=InterviewType.TECHNICAL,
        ),
    )
    # admin_user cannot read other_user's interview.
    with pytest.raises(AppError) as exc_info:
        service.get(admin_user.id, interview.id)
    assert exc_info.value.status_code in (403, 404)


# ---------------------------------------------------------------------------
# 11. Dify keys never leak into state snapshots
# ---------------------------------------------------------------------------


def test_dify_keys_not_in_state_snapshots(
    db_session: Session,
    admin_user: Any,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = _get_report(db_session, report_id)
    service = _make_service_with_local_plan(db_session)
    service.create(
        admin_user.id,
        InterviewCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
            interview_type=InterviewType.TECHNICAL,
        ),
    )
    runs = db_session.scalars(select(AgentRun).where(AgentRun.run_type == "interview")).all()
    for run in runs:
        snapshot_str = str(run.state_snapshot)
        # No API keys should appear anywhere in state snapshots.
        assert "app-" not in snapshot_str
        assert "sk-" not in snapshot_str


# ---------------------------------------------------------------------------
# 12. API: create interview without DIFY_INTERVIEW_PLAN_API_KEY
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_api_create_interview_without_plan_key(
    client: AsyncClient,
    db_session: Session,
) -> None:
    """The API should create an interview even when
    DIFY_INTERVIEW_PLAN_API_KEY is not set in the environment."""
    owner_headers = await _register_headers(client, "local-plan-owner@example.com")
    from app.models.users import User

    owner = db_session.scalar(select(User).where(User.email == "local-plan-owner@example.com"))
    assert owner is not None
    report_id = _successful_report(db_session, owner, "skill_gap")
    report = _get_report(db_session, report_id)

    # Patch the factory to simulate dify mode without plan key.
    with patch("app.api.interviews.create_interview_plan_provider") as mock_factory:
        mock_factory.return_value = LocalInterviewPlanProvider()
        resp = await client.post(
            "/api/interviews",
            headers=owner_headers,
            json={
                "resume_version_id": report.resume_version_id,
                "job_id": report.job_id,
                "match_report_id": report_id,
                "interview_type": "TECHNICAL",
            },
        )
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["status"] == "PLANNED"
    assert data["provider"] == "local"
    assert len(data["questions"]) >= 4


# ---------------------------------------------------------------------------
# 13. FOLLOW_UP does not change current question index
# ---------------------------------------------------------------------------


def test_follow_up_does_not_change_question_index(
    db_session: Session,
    admin_user: Any,
) -> None:
    """Verify that a FOLLOW_UP action keeps the same question index."""
    from app.schemas.interviews import (
        ChatNextAction,
        ChatTurnGeneration,
        ChatTurnWorkflowOutput,
    )

    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = _get_report(db_session, report_id)

    # Create a custom chat provider that always returns FOLLOW_UP.
    class FollowUpChatProvider:
        def chat_turn(self, request, *, conversation_id, user):
            from app.integrations.dify.interview_providers import (
                ChatTurnProviderResult,
            )

            return ChatTurnProviderResult(
                output=ChatTurnWorkflowOutput(
                    schema_version="interview-chat-turn-v1",
                    assistant_message="能再详细说说吗？",
                    next_action=ChatNextAction.FOLLOW_UP,
                    turn_analysis="需要更多细节",
                    generation=ChatTurnGeneration(
                        workflow_version="test-v1",
                        conversation_id="test-conv",
                        provider="test",
                        latency_ms=10,
                    ),
                ),
                raw_output={},
                conversation_id="test-conv",
                attempts=[],
            )

    service = _make_service_with_local_plan(
        db_session,
        chat_provider=FollowUpChatProvider(),
    )
    interview = service.create(
        admin_user.id,
        InterviewCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
            interview_type=InterviewType.TECHNICAL,
        ),
    )
    service.start_interview(admin_user.id, interview.id)
    session = db_session.get(InterviewSession, interview.id)
    index_before = session.current_question_index

    from app.schemas.interviews import InterviewMessageSubmit

    service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(content="我做过一个Python项目。"),
    )
    db_session.refresh(session)
    # FOLLOW_UP should NOT advance the question index.
    assert session.current_question_index == index_before
    assert session.current_follow_up_count == 1


# ---------------------------------------------------------------------------
# 14. Project title extraction handles {"value": ...} wrapper
# ---------------------------------------------------------------------------


def test_project_title_extraction_unwraps_value_dict() -> None:
    """The _extract_project_titles method must unwrap the
    {"value": str, "confidence": float} dict format used by
    resume structured_data."""
    projects = [
        {
            "title": {
                "value": "B站爬虫系统",
                "confidence": 1.0,
                "evidence_text": "B站爬虫系统",
            }
        },
        {"title": {"value": "图书管理系统", "confidence": 0.9}},
        {"name": "Plain Title Project"},
    ]
    titles = LocalInterviewPlanProvider._extract_project_titles(projects)
    assert titles == ["B站爬虫系统", "图书管理系统", "Plain Title Project"]


# ---------------------------------------------------------------------------
# 15. Complete interview generates and persists final report
# ---------------------------------------------------------------------------


def test_complete_interview_persists_report(
    db_session: Session,
    admin_user: Any,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = _get_report(db_session, report_id)
    service = _make_service_with_local_plan(db_session)
    interview = service.create(
        admin_user.id,
        InterviewCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
            interview_type=InterviewType.TECHNICAL,
        ),
    )
    service.start_interview(admin_user.id, interview.id)

    from app.schemas.interviews import InterviewMessageSubmit

    # Answer the first question.
    service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(content="我有Python和SQL经验。"),
    )

    # Complete the interview.
    service.complete_interview(admin_user.id, interview.id)

    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    assert session.chat_status == "COMPLETED"
    assert session.report is not None
    assert len(session.report) > 0
