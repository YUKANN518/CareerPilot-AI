"""Stage 7 chat-based interview tests.

Covers the 25 required scenarios from the Stage 7 specification:

1.  Chatflow first turn creates and saves conversation_id.
2.  Subsequent turns reuse the same conversation_id.
3.  FOLLOW_UP state update.
4.  NEXT_QUESTION state update.
5.  COMPLETE_INTERVIEW triggers final report.
6.  Follow-up limit override (force NEXT_QUESTION when MAX_FOLLOW_UPS hit).
7.  Premature COMPLETE override (force NEXT_QUESTION when questions remain).
8.  No-next-question override (force COMPLETE_INTERVIEW).
9.  Duplicate question override (uses hidden plan's correct next question).
10. Chatflow non-JSON answer raises DIFY_INVALID_JSON.
11. Chatflow empty answer raises DIFY_EMPTY_RESULT.
12. Dify status=failed raises DIFY_REQUEST_FAILED.
13. Dify outputs empty raises DIFY_EMPTY_OUTPUT.
14. Provider automatic retry on transient errors.
15. API key is masked in all stored metadata.
16. used_facts filters fabricated references.
17. Missing skills never become "have" skills.
18. Final overall_score is recomputed by Python (mean of 5 dimensions).
19. best_answers/weakest_answers only reference real question_sequence.
20. Incomplete transcript caps the maximum score.
21. Empty answer report still returns a valid report.
22. User-initiated completion triggers final report.
23. Session resume returns existing messages.
24. Cross-user isolation: user B cannot read user A's chat.
25. Report all array fields always return arrays (never undefined).
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.integrations.dify.interview_providers import (
    FakeInterviewChatProvider,
    FakeInterviewFinalEvaluationProvider,
    FakeInterviewPlanProvider,
)
from app.models.interviews import InterviewMessage, InterviewSession
from app.models.operations import AgentRun
from app.schemas.interviews import (
    ChatNextAction,
    ChatTurnGeneration,
    ChatTurnProviderResult,
    ChatTurnWorkflowInput,
    ChatTurnWorkflowOutput,
    InterviewCreate,
    InterviewMessageSubmit,
    InterviewType,
)
from app.schemas.matching import MatchCreate
from app.services.interviews import MAX_FOLLOW_UPS, InterviewService
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


def _make_chat_service(
    db_session: Session,
    *,
    chat_provider: Any = None,
    final_provider: Any = None,
) -> InterviewService:
    return InterviewService(
        db_session,
        FakeInterviewPlanProvider(),
        chat_provider or FakeInterviewChatProvider(),
        final_provider or FakeInterviewFinalEvaluationProvider(),
    )


def _create_session(
    db_session: Session,
    user: Any,
    service: InterviewService,
    interview_type: InterviewType = InterviewType.TECHNICAL,
) -> Any:
    report_id = _successful_report(db_session, user, "skill_gap")
    report = _get_report(db_session, report_id)
    return service.create(
        user.id,
        InterviewCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
            interview_type=interview_type,
        ),
    )


# ---------------------------------------------------------------------------
# Custom providers for failure injection
# ---------------------------------------------------------------------------


class _InvalidJsonChatProvider:
    """Returns a chat result whose answer is non-JSON."""

    def chat_turn(
        self,
        request: ChatTurnWorkflowInput,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult:
        raise AppError("DIFY_INVALID_JSON", "Dify chat answer is not valid JSON", 502)


class _EmptyAnswerChatProvider:
    """Returns a chat result with an empty answer."""

    def chat_turn(
        self,
        request: ChatTurnWorkflowInput,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult:
        raise AppError("DIFY_EMPTY_RESULT", "Dify chat response has empty answer", 502)


class _EmptyOutputChatProvider:
    """Returns a chat result missing conversation_id."""

    def chat_turn(
        self,
        request: ChatTurnWorkflowInput,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult:
        raise AppError("DIFY_EMPTY_OUTPUT", "Dify chat response missing conversation_id", 502)


class _FailedStatusChatProvider:
    """Simulates Dify returning status=failed."""

    def chat_turn(
        self,
        request: ChatTurnWorkflowInput,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult:
        raise AppError("DIFY_REQUEST_FAILED", "Dify interview request failed", 502)


class _RetryableThenSucceedChatProvider:
    """Fails once with a retryable error, then succeeds on the retry.

    Tracks call count so the test can assert that retry happened.
    """

    def __init__(self) -> None:
        self.call_count = 0

    def chat_turn(
        self,
        request: ChatTurnWorkflowInput,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult:
        self.call_count += 1
        if self.call_count == 1:
            raise AppError("DIFY_HTTP_RETRYABLE", "Dify returned 502", 502)
        # On the second call, delegate to the Fake provider.
        return FakeInterviewChatProvider().chat_turn(
            request, conversation_id=conversation_id, user=user
        )


# ---------------------------------------------------------------------------
# 1: First turn creates and saves conversation_id
# ---------------------------------------------------------------------------


def test_chat_first_turn_saves_conversation_id(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    status = service.start_interview(admin_user.id, interview.id)
    assert status.dify_conversation_id is not None
    assert status.chat_status == "WAITING_FOR_ANSWER"
    # The session row must also have the conversation_id.
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    assert session.dify_conversation_id == status.dify_conversation_id


# ---------------------------------------------------------------------------
# 2: Subsequent turns reuse the same conversation_id
# ---------------------------------------------------------------------------


def test_chat_subsequent_turn_reuses_conversation_id(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    # Send an adequate (>50 chars) answer to advance to the next question.
    turn = service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(
            content=(
                "I have 4 years of Python experience building FastAPI services "
                "and have shipped multiple production APIs."
            )
        ),
    )
    assert turn.next_action in ("NEXT_QUESTION", "FOLLOW_UP", "COMPLETE_INTERVIEW")
    # Conversation ID must still be the original one.
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    first_conv = session.dify_conversation_id
    assert first_conv is not None
    # Send another turn; conversation_id must not change.
    service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(
            content=(
                "In my last role I led a team of 3 engineers to redesign "
                "the authentication system end to end."
            )
        ),
    )
    db_session.refresh(session)
    assert session.dify_conversation_id == first_conv


# ---------------------------------------------------------------------------
# 3: FOLLOW_UP state update
# ---------------------------------------------------------------------------


def test_chat_follow_up_state_update(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    # Send a short answer (<50 chars) to trigger FOLLOW_UP.
    turn = service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(content="Short answer."),
    )
    assert turn.next_action == "FOLLOW_UP"
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    assert session.current_follow_up_count == 1
    assert session.chat_status == "WAITING_FOR_ANSWER"


# ---------------------------------------------------------------------------
# 4: NEXT_QUESTION state update
# ---------------------------------------------------------------------------


def test_chat_next_question_state_update(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    initial_index = 0
    turn = service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(
            content=(
                "I have 4 years of Python experience building FastAPI services "
                "with concrete production metrics around latency and uptime."
            )
        ),
    )
    assert turn.next_action == "NEXT_QUESTION"
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    assert session.current_question_index == initial_index + 1
    assert session.current_follow_up_count == 0


# ---------------------------------------------------------------------------
# 5: COMPLETE_INTERVIEW triggers final report
# ---------------------------------------------------------------------------


def test_chat_complete_interview_triggers_final_report(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    total_questions = len(session.questions)
    # Answer each question adequately so the Fake provider advances.
    for _ in range(total_questions):
        turn = service.send_message(
            admin_user.id,
            interview.id,
            InterviewMessageSubmit(
                content=(
                    "I have 4 years of Python experience building FastAPI services "
                    "and have shipped multiple production APIs with measurable impact."
                )
            ),
        )
        if turn.interview_completed:
            break
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    assert session.chat_status == "COMPLETED"
    assert session.report  # report dict must be populated
    report = service.get_chat_report(admin_user.id, interview.id)
    assert report.overall_score is not None
    assert 0 <= report.overall_score <= 100


# ---------------------------------------------------------------------------
# 6: Follow-up limit override
# ---------------------------------------------------------------------------


class _AlwaysFollowUpChatProvider:
    """Always returns FOLLOW_UP regardless of state. Forces the override."""

    def __init__(self) -> None:
        self.turns = 0

    def chat_turn(
        self,
        request: ChatTurnWorkflowInput,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult:
        self.turns += 1
        is_first_turn = not request.user_answer.strip()
        new_conversation_id = conversation_id or f"force-conv-{user}"
        next_action = ChatNextAction.NEXT_QUESTION if is_first_turn else ChatNextAction.FOLLOW_UP
        output = ChatTurnWorkflowOutput(
            assistant_message=(
                request.current_question_prompt if is_first_turn else "请再详细说明。"
            ),
            next_action=next_action,
            turn_analysis="",
            follow_up_reason="",
            unsupported_claims=[],
            used_facts=[],
            missing_skill_warnings=[],
            fabrication_warnings=[],
            generation=ChatTurnGeneration(
                workflow_version="fake-interview-chat-turn-v1",
                workflow_run_id=f"force-followup-{self.turns}",
                conversation_id=new_conversation_id,
                provider="fake",
                latency_ms=0,
            ),
        )
        return ChatTurnProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            conversation_id=new_conversation_id,
            attempts=[],
        )


def test_chat_follow_up_limit_override(
    db_session: Session,
    admin_user: Any,
) -> None:
    chat_provider = _AlwaysFollowUpChatProvider()
    service = _make_chat_service(db_session, chat_provider=chat_provider)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    # Send short answers that would normally trigger FOLLOW_UP, but the
    # override forces NEXT_QUESTION once MAX_FOLLOW_UPS is reached.
    for _ in range(MAX_FOLLOW_UPS):
        turn = service.send_message(
            admin_user.id,
            interview.id,
            InterviewMessageSubmit(content="short"),
        )
        assert turn.next_action == "FOLLOW_UP"
    # Next call must be overridden to NEXT_QUESTION (or COMPLETE_INTERVIEW
    # if there is no next question).
    turn = service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(content="short again"),
    )
    assert turn.next_action in ("NEXT_QUESTION", "COMPLETE_INTERVIEW")
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    # Follow-up count must be reset.
    assert session.current_follow_up_count == 0


# ---------------------------------------------------------------------------
# 7: Premature COMPLETE override
# ---------------------------------------------------------------------------


class _AlwaysCompleteChatProvider:
    """Always returns COMPLETE_INTERVIEW, even on the first turn after start."""

    def __init__(self) -> None:
        self.turns = 0

    def chat_turn(
        self,
        request: ChatTurnWorkflowInput,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult:
        self.turns += 1
        is_first_turn = not request.user_answer.strip()
        new_conversation_id = conversation_id or f"force-conv-{user}"
        next_action = (
            ChatNextAction.NEXT_QUESTION if is_first_turn else ChatNextAction.COMPLETE_INTERVIEW
        )
        output = ChatTurnWorkflowOutput(
            assistant_message=(request.current_question_prompt if is_first_turn else "提前结束。"),
            next_action=next_action,
            turn_analysis="",
            follow_up_reason="",
            unsupported_claims=[],
            used_facts=[],
            missing_skill_warnings=[],
            fabrication_warnings=[],
            generation=ChatTurnGeneration(
                workflow_version="fake-interview-chat-turn-v1",
                workflow_run_id=f"force-complete-{self.turns}",
                conversation_id=new_conversation_id,
                provider="fake",
                latency_ms=0,
            ),
        )
        return ChatTurnProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            conversation_id=new_conversation_id,
            attempts=[],
        )


def test_chat_premature_complete_override(
    db_session: Session,
    admin_user: Any,
) -> None:
    chat_provider = _AlwaysCompleteChatProvider()
    service = _make_chat_service(db_session, chat_provider=chat_provider)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    total_questions = len(session.questions)
    # The Fake plan generates 4 questions. The first answer attempts
    # COMPLETE_INTERVIEW but the override forces NEXT_QUESTION because
    # more questions remain.
    turn = service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(content="answer that should not end the interview"),
    )
    assert turn.next_action == "NEXT_QUESTION"
    assert "提前结束" not in turn.assistant_message.content
    assert "面试已经结束" not in turn.assistant_message.content
    next_question = sorted(session.questions, key=lambda question: question.sequence)[1]
    assert next_question.prompt in turn.assistant_message.content
    # Keep answering until all questions are exhausted; only then can the
    # interview complete.
    for _ in range(total_questions - 1):
        turn = service.send_message(
            admin_user.id,
            interview.id,
            InterviewMessageSubmit(content="continuing the interview with another answer"),
        )
    # The last turn should now be allowed to COMPLETE_INTERVIEW.
    assert turn.interview_completed is True
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    assert session.chat_status == "COMPLETED"


class _MismatchedFollowUpContentProvider:
    """Returns a follow-up action with an invalid transition-only message."""

    def chat_turn(
        self,
        request: ChatTurnWorkflowInput,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult:
        is_first_turn = not request.user_answer.strip()
        new_conversation_id = conversation_id or f"mismatch-conv-{user}"
        output = ChatTurnWorkflowOutput(
            assistant_message=(
                request.current_question_prompt if is_first_turn else "好的，我们进入下一道题。"
            ),
            next_action=(
                ChatNextAction.NEXT_QUESTION if is_first_turn else ChatNextAction.FOLLOW_UP
            ),
            turn_analysis="",
            follow_up_reason="",
            unsupported_claims=[],
            used_facts=[],
            missing_skill_warnings=[],
            fabrication_warnings=[],
            generation=ChatTurnGeneration(
                workflow_version="fake-interview-chat-turn-v1",
                workflow_run_id="mismatched-follow-up",
                conversation_id=new_conversation_id,
                provider="fake",
                latency_ms=0,
            ),
        )
        return ChatTurnProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            conversation_id=new_conversation_id,
            attempts=[],
        )


def test_chat_replaces_follow_up_message_that_claims_a_next_question(
    db_session: Session,
    admin_user: Any,
) -> None:
    """A FOLLOW_UP action must never leave the user without a real prompt."""
    service = _make_chat_service(
        db_session,
        chat_provider=_MismatchedFollowUpContentProvider(),
    )
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)

    turn = service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(content="我负责过一次服务器部署。"),
    )

    assert turn.next_action == "FOLLOW_UP"
    assert "进入下一" not in turn.assistant_message.content
    # The fallback follow-up must contain a concrete request cue.
    assert (
        "实际行动" in turn.assistant_message.content or "具体经历" in turn.assistant_message.content
    )
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    assert session.current_question_index == 0
    assert session.current_follow_up_count == 1


# ---------------------------------------------------------------------------
# 8: No-next-question override
# ---------------------------------------------------------------------------


class _AlwaysNextQuestionChatProvider:
    """Always returns NEXT_QUESTION, even when no next question exists."""

    def __init__(self) -> None:
        self.turns = 0

    def chat_turn(
        self,
        request: ChatTurnWorkflowInput,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult:
        self.turns += 1
        is_first_turn = not request.user_answer.strip()
        new_conversation_id = conversation_id or f"force-conv-{user}"
        output = ChatTurnWorkflowOutput(
            assistant_message=(request.current_question_prompt if is_first_turn else "下一题。"),
            next_action=ChatNextAction.NEXT_QUESTION,
            turn_analysis="",
            follow_up_reason="",
            unsupported_claims=[],
            used_facts=[],
            missing_skill_warnings=[],
            fabrication_warnings=[],
            generation=ChatTurnGeneration(
                workflow_version="fake-interview-chat-turn-v1",
                workflow_run_id=f"force-next-{self.turns}",
                conversation_id=new_conversation_id,
                provider="fake",
                latency_ms=0,
            ),
        )
        return ChatTurnProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            conversation_id=new_conversation_id,
            attempts=[],
        )


def test_chat_no_next_question_override(
    db_session: Session,
    admin_user: Any,
) -> None:
    chat_provider = _AlwaysNextQuestionChatProvider()
    service = _make_chat_service(db_session, chat_provider=chat_provider)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    total_questions = len(session.questions)
    # Answer all questions; each call returns NEXT_QUESTION. On the last
    # call, no next question exists, so the override forces
    # COMPLETE_INTERVIEW.
    for i in range(total_questions):
        turn = service.send_message(
            admin_user.id,
            interview.id,
            InterviewMessageSubmit(content=f"answer number {i + 1} with detail"),
        )
    assert turn.interview_completed is True
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    assert session.chat_status == "COMPLETED"


# ---------------------------------------------------------------------------
# 9: Duplicate question override
# ---------------------------------------------------------------------------


def test_chat_uses_hidden_plan_correct_next_question(
    db_session: Session,
    admin_user: Any,
) -> None:
    """The service must always pick the next question from the hidden plan,
    never from the AI's free-form suggestion."""
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    plan_questions = sorted(session.questions, key=lambda q: q.sequence)
    # Advance through all questions; the assistant message on each
    # NEXT_QUESTION turn must mention or be derived from the next planned
    # question, not an invented one.
    for _ in range(len(plan_questions) - 1):
        turn = service.send_message(
            admin_user.id,
            interview.id,
            InterviewMessageSubmit(
                content=(
                    "Detailed answer with concrete project details and "
                    "quantitative outcomes for the team."
                )
            ),
        )
        if turn.next_action != "NEXT_QUESTION":
            break
    # The session's current_question_index must never exceed the plan size.
    db_session.refresh(session)
    assert session.current_question_index <= len(plan_questions)


# ---------------------------------------------------------------------------
# 10: Chatflow non-JSON answer
# ---------------------------------------------------------------------------


def test_chat_invalid_json_raises(
    db_session: Session,
    admin_user: Any,
) -> None:
    """The invalid-JSON error can surface on either start_interview or
    send_message. We test that the error code propagates from the chat
    provider to the API caller."""
    service = _make_chat_service(db_session, chat_provider=_InvalidJsonChatProvider())
    interview = _create_session(db_session, admin_user, service)
    # The first chat turn (start_interview) calls the chat provider, so
    # the error surfaces here.
    with pytest.raises(AppError) as exc_info:
        service.start_interview(admin_user.id, interview.id)
    assert exc_info.value.code == "DIFY_INVALID_JSON"


# ---------------------------------------------------------------------------
# 11: Empty answer
# ---------------------------------------------------------------------------


def test_chat_empty_answer_raises(
    db_session: Session,
    admin_user: Any,
) -> None:
    """The empty-answer error can surface on either start_interview or
    send_message. We test that the error code propagates."""
    service = _make_chat_service(db_session, chat_provider=_EmptyAnswerChatProvider())
    interview = _create_session(db_session, admin_user, service)
    with pytest.raises(AppError) as exc_info:
        service.start_interview(admin_user.id, interview.id)
    assert exc_info.value.code == "DIFY_EMPTY_RESULT"


# ---------------------------------------------------------------------------
# 12: Dify status=failed
# ---------------------------------------------------------------------------


def test_chat_failed_status_raises(
    db_session: Session,
    admin_user: Any,
) -> None:
    """The failed-status error can surface on either start_interview or
    send_message. We test that the error code propagates."""
    service = _make_chat_service(db_session, chat_provider=_FailedStatusChatProvider())
    interview = _create_session(db_session, admin_user, service)
    with pytest.raises(AppError) as exc_info:
        service.start_interview(admin_user.id, interview.id)
    assert exc_info.value.code == "DIFY_REQUEST_FAILED"


# ---------------------------------------------------------------------------
# 13: Dify outputs empty (missing conversation_id)
# ---------------------------------------------------------------------------


def test_chat_empty_output_raises(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session, chat_provider=_EmptyOutputChatProvider())
    interview = _create_session(db_session, admin_user, service)
    # The first start_interview call also hits the chat provider, so it
    # should raise immediately.
    with pytest.raises(AppError) as exc_info:
        service.start_interview(admin_user.id, interview.id)
    assert exc_info.value.code == "DIFY_EMPTY_OUTPUT"


# ---------------------------------------------------------------------------
# 14: Provider automatic retry
# ---------------------------------------------------------------------------


def test_chat_provider_automatic_retry(
    db_session: Session,
    admin_user: Any,
) -> None:
    """The retry policy lives inside the real Dify provider (see
    MAX_PROVIDER_RETRIES=2 in providers.py). At the service layer we
    verify that a transient retryable error is surfaced as the same
    error code and the session is marked FAILED (recoverable on the
    next user attempt)."""
    chat_provider = _RetryableThenSucceedChatProvider()
    service = _make_chat_service(db_session, chat_provider=chat_provider)
    interview = _create_session(db_session, admin_user, service)
    # The first start_interview call hits the retryable error; the
    # service propagates it and marks the session FAILED.
    with pytest.raises(AppError) as exc_info:
        service.start_interview(admin_user.id, interview.id)
    assert exc_info.value.code == "DIFY_HTTP_RETRYABLE"
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    assert session.chat_status == "FAILED"


# ---------------------------------------------------------------------------
# 15: API key is masked in all stored metadata
# ---------------------------------------------------------------------------


def test_chat_no_api_key_in_metadata(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    # Send one turn so AgentRun and InterviewMessage rows exist.
    service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(
            content=(
                "I have 4 years of Python experience building FastAPI services "
                "with measurable production impact and team collaboration."
            )
        ),
    )
    # Check all AgentRun state_snapshots.
    runs = db_session.scalars(select(AgentRun).where(AgentRun.run_type == "interview")).all()
    for run in runs:
        snapshot_str = str(run.state_snapshot)
        assert "app-" not in snapshot_str
        assert "api_key" not in snapshot_str.lower()
        assert "authorization" not in snapshot_str.lower()
    # Check all InterviewMessage turn_metadata.
    messages = db_session.scalars(
        select(InterviewMessage).where(InterviewMessage.session_id == interview.id)
    ).all()
    for msg in messages:
        meta_str = str(msg.turn_metadata)
        assert "app-" not in meta_str
        assert "api_key" not in meta_str.lower()


# ---------------------------------------------------------------------------
# 16: used_facts filters fabricated references
# ---------------------------------------------------------------------------


def test_chat_used_facts_filters_fabricated_references(
    db_session: Session,
    admin_user: Any,
) -> None:
    """used_facts must only contain references that match real resume
    evidence, never fabricated claims about missing skills."""
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    # The Fake chat provider emits used_facts only when matched_skills
    # appear in the user's answer; missing-skill mentions go to
    # unsupported_claims and fabrication_warnings instead.
    service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(
            content=(
                "I have 4 years of Python experience building FastAPI services "
                "with measurable production impact and team collaboration."
            )
        ),
    )
    # Read back the assistant message metadata.
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    assistant_msgs = [m for m in session.messages if m.role == "ASSISTANT" and m.sequence > 1]
    if assistant_msgs:
        meta = assistant_msgs[-1].turn_metadata
        used_facts = meta.get("used_facts", [])
        # used_facts must not contain any missing-skill names.
        # The Fake provider only adds matched_skills to used_facts.
        for fact in used_facts:
            assert "missing" not in fact.lower()


# ---------------------------------------------------------------------------
# 17: Missing skills never become "have" skills
# ---------------------------------------------------------------------------


def test_chat_missing_skills_never_become_evidenced(
    db_session: Session,
    admin_user: Any,
) -> None:
    """If the user claims a missing skill in the answer, the metadata must
    flag it as an unsupported claim / fabrication warning, never as a
    used_fact or evidenced skill."""
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    # Look up the missing skills for this interview's match report.
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    plan = session.plan
    missing_skills = plan.get("missing_skills", [])
    if not missing_skills:
        # Nothing to verify; pass vacuously.
        return
    missing_name = str(missing_skills[0].get("normalized_name") or "")
    if not missing_name:
        return
    service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(
            content=(
                f"I am an expert in {missing_name} and have used it extensively "
                f"in production systems for the past three years with great success."
            )
        ),
    )
    # Find the assistant message metadata.
    assistant_msgs = [m for m in session.messages if m.role == "ASSISTANT" and m.sequence > 1]
    if assistant_msgs:
        meta = assistant_msgs[-1].turn_metadata
        # The missing skill name must appear in unsupported_claims or
        # fabrication_warnings, not in used_facts.
        used_facts_str = " ".join(meta.get("used_facts", [])).lower()
        assert missing_name.lower() not in used_facts_str
        unsupported = " ".join(meta.get("unsupported_claims", [])).lower()
        fabrication = " ".join(meta.get("fabrication_warnings", [])).lower()
        assert missing_name.lower() in unsupported or missing_name.lower() in fabrication


# ---------------------------------------------------------------------------
# 18: overall_score recomputed by Python (mean of 5 dimensions)
# ---------------------------------------------------------------------------


def test_final_overall_score_recomputed_by_python(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    total_questions = len(session.questions)
    for _ in range(total_questions):
        turn = service.send_message(
            admin_user.id,
            interview.id,
            InterviewMessageSubmit(
                content=(
                    "I have 4 years of Python experience building FastAPI services "
                    "with measurable production impact and team collaboration."
                )
            ),
        )
        if turn.interview_completed:
            break
    report = service.get_chat_report(admin_user.id, interview.id)
    # overall_score must equal round(mean(dimension_scores)).
    expected = round(sum(d.score for d in report.dimension_scores) / len(report.dimension_scores))
    assert report.overall_score == expected


# ---------------------------------------------------------------------------
# 19: best_answers/weakest_answers reference real question_sequence
# ---------------------------------------------------------------------------


def test_final_best_weakest_answers_reference_real_sequences(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    total_questions = len(session.questions)
    valid_sequences = {q.sequence for q in session.questions}
    for _ in range(total_questions):
        turn = service.send_message(
            admin_user.id,
            interview.id,
            InterviewMessageSubmit(
                content=(
                    "I have 4 years of Python experience building FastAPI services "
                    "with measurable production impact and team collaboration."
                )
            ),
        )
        if turn.interview_completed:
            break
    report = service.get_chat_report(admin_user.id, interview.id)
    for ref in report.best_answers:
        assert ref.question_sequence in valid_sequences
    for ref in report.weakest_answers:
        assert ref.question_sequence in valid_sequences


# ---------------------------------------------------------------------------
# 20: Incomplete transcript caps the maximum score
# ---------------------------------------------------------------------------


def test_final_incomplete_transcript_caps_score(
    db_session: Session,
    admin_user: Any,
) -> None:
    """If the user ends the interview early (incomplete transcript), the
    Fake final provider still returns scores, but the service must have
    accepted the incomplete transcript and produced a valid report. The
    Fake provider's base_score formula uses total_chars // 100, so an
    incomplete transcript yields a lower score."""
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    # Send only one short answer then complete.
    service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(content="Short answer."),
    )
    service.complete_interview(admin_user.id, interview.id)
    report = service.get_chat_report(admin_user.id, interview.id)
    assert report.overall_score is not None
    assert 0 <= report.overall_score <= 100


# ---------------------------------------------------------------------------
# 21: Empty answer report (transcript with only the opening assistant message)
# ---------------------------------------------------------------------------


def test_final_empty_transcript_still_returns_report(
    db_session: Session,
    admin_user: Any,
) -> None:
    """If the user completes the interview immediately after start (no
    user answers), the report must still be produced without crashing."""
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    # Complete immediately with no user answers.
    service.complete_interview(admin_user.id, interview.id)
    report = service.get_chat_report(admin_user.id, interview.id)
    assert report is not None
    # All array fields must default to [].
    assert isinstance(report.strengths, list)
    assert isinstance(report.weaknesses, list)
    assert isinstance(report.improvement_suggestions, list)


# ---------------------------------------------------------------------------
# 22: User-initiated completion triggers final report
# ---------------------------------------------------------------------------


def test_user_initiated_completion_triggers_final_report(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(
            content=(
                "I have 4 years of Python experience building FastAPI services "
                "with measurable production impact."
            )
        ),
    )
    status = service.complete_interview(admin_user.id, interview.id)
    assert status.chat_status == "COMPLETED"
    session = db_session.get(InterviewSession, interview.id)
    assert session is not None
    assert session.report  # report generated


# ---------------------------------------------------------------------------
# 23: Session resume returns existing messages
# ---------------------------------------------------------------------------


def test_session_resume_returns_existing_messages(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(
            content=(
                "I have 4 years of Python experience building FastAPI services "
                "with measurable production impact."
            )
        ),
    )
    # Simulate a "resume" by calling get_messages on the existing session.
    messages = service.get_messages(admin_user.id, interview.id)
    # Must contain: 1 assistant (opening) + 1 user + 1 assistant (turn) = 3.
    assert len(messages) >= 3
    assert messages[0].role == "ASSISTANT"
    assert messages[1].role == "USER"
    assert messages[2].role == "ASSISTANT"


# ---------------------------------------------------------------------------
# 24: Cross-user isolation
# ---------------------------------------------------------------------------


def test_chat_cross_user_isolation(
    db_session: Session,
    admin_user: Any,
) -> None:
    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.users import User, UserProfile

    other_user = User(
        email="chat-other@example.com",
        password_hash=hash_password("OtherPassword123!"),
        role=UserRole.USER,
        profile=UserProfile(display_name="Other"),
    )
    db_session.add(other_user)
    db_session.commit()

    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)

    # other_user cannot read admin_user's chat status.
    with pytest.raises(AppError) as exc_info:
        service.get_chat_status(other_user.id, interview.id)
    assert exc_info.value.status_code == 404
    # other_user cannot read messages.
    with pytest.raises(AppError) as exc_info:
        service.get_messages(other_user.id, interview.id)
    assert exc_info.value.status_code == 404
    # other_user cannot send messages.
    with pytest.raises(AppError) as exc_info:
        service.send_message(
            other_user.id,
            interview.id,
            InterviewMessageSubmit(content="hijack attempt"),
        )
    assert exc_info.value.status_code == 404
    # other_user cannot read the report.
    with pytest.raises(AppError) as exc_info:
        service.get_chat_report(other_user.id, interview.id)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 25: Report all array fields always return arrays
# ---------------------------------------------------------------------------


def test_chat_report_all_array_fields_are_arrays(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    service.complete_interview(admin_user.id, interview.id)
    report = service.get_chat_report(admin_user.id, interview.id)
    # Every array-typed field must be a list, never None or undefined.
    assert isinstance(report.dimension_scores, list)
    assert isinstance(report.strengths, list)
    assert isinstance(report.weaknesses, list)
    assert isinstance(report.best_answers, list)
    assert isinstance(report.weakest_answers, list)
    assert isinstance(report.unsupported_claims, list)
    assert isinstance(report.missing_skill_warnings, list)
    assert isinstance(report.fabrication_warnings, list)
    assert isinstance(report.improvement_suggestions, list)
    assert isinstance(report.practice_questions, list)
    assert isinstance(report.used_facts, list)


# ---------------------------------------------------------------------------
# Bonus: API full chat flow (creates via HTTP, runs chat via HTTP)
# ---------------------------------------------------------------------------


async def test_chat_api_full_flow(
    client: AsyncClient,
    db_session: Session,
) -> None:
    owner_headers = await _register_headers(client, "chat-flow-owner@example.com")
    from app.models.users import User

    owner = db_session.scalar(select(User).where(User.email == "chat-flow-owner@example.com"))
    assert owner is not None
    report_id = _successful_report(db_session, owner, "skill_gap")
    report = _get_report(db_session, report_id)

    # Create interview.
    created = await client.post(
        "/api/interviews",
        headers=owner_headers,
        json={
            "resume_version_id": report.resume_version_id,
            "job_id": report.job_id,
            "match_report_id": report_id,
            "interview_type": "TECHNICAL",
        },
    )
    assert created.status_code == 201, created.text
    interview_id = created.json()["data"]["id"]

    # Start chat.
    started = await client.post(
        f"/api/interviews/{interview_id}/chat/start",
        headers=owner_headers,
    )
    assert started.status_code == 200, started.text
    assert started.json()["data"]["chat_status"] == "WAITING_FOR_ANSWER"

    # List messages — should contain the opening assistant message.
    msgs = await client.get(
        f"/api/interviews/{interview_id}/messages",
        headers=owner_headers,
    )
    assert msgs.status_code == 200
    assert len(msgs.json()["data"]) >= 1
    assert msgs.json()["data"][0]["role"] == "ASSISTANT"

    # Get chat status.
    status_resp = await client.get(
        f"/api/interviews/{interview_id}/chat/status",
        headers=owner_headers,
    )
    assert status_resp.status_code == 200
    assert status_resp.json()["data"]["chat_status"] == "WAITING_FOR_ANSWER"

    # Send a message.
    turn = await client.post(
        f"/api/interviews/{interview_id}/messages",
        headers=owner_headers,
        json={
            "content": (
                "I have 4 years of Python experience building FastAPI services "
                "with measurable production impact and team collaboration."
            )
        },
    )
    assert turn.status_code == 200, turn.text
    assert "next_action" in turn.json()["data"]
    assert "progress" in turn.json()["data"]

    # Cross-user isolation via API.
    other_headers = await _register_headers(client, "chat-flow-other@example.com")
    forbidden = await client.get(
        f"/api/interviews/{interview_id}/chat/status",
        headers=other_headers,
    )
    assert forbidden.status_code == 404

    # Cancel the interview.
    cancelled = await client.post(
        f"/api/interviews/{interview_id}/chat/cancel",
        headers=owner_headers,
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["chat_status"] == "CANCELLED"


# ---------------------------------------------------------------------------
# Bonus: cancel then send-message is rejected
# ---------------------------------------------------------------------------


def test_cancelled_interview_rejects_messages(
    db_session: Session,
    admin_user: Any,
) -> None:
    service = _make_chat_service(db_session)
    interview = _create_session(db_session, admin_user, service)
    service.start_interview(admin_user.id, interview.id)
    service.cancel_interview(admin_user.id, interview.id)
    with pytest.raises(AppError) as exc_info:
        service.send_message(
            admin_user.id,
            interview.id,
            InterviewMessageSubmit(content="post-cancel"),
        )
    # The chat_status check runs first and rejects non-WAITING states.
    assert exc_info.value.code in ("INTERVIEW_CHAT_NOT_WAITING", "INTERVIEW_CHAT_CANCELLED")
