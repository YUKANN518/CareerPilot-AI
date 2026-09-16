"""Contract tests for the chat interview FOLLOW_UP message validation.

These tests enforce the core invariant of the chat interview state machine:

* The structured ``next_action`` field is the SOLE authority for state
  transitions. Natural-language prose never drives the state machine.
* When ``next_action == FOLLOW_UP``, the displayed message must always
  contain a real follow-up question. If Dify emits transition prose, a
  bare acknowledgement, or a message without a question under
  ``FOLLOW_UP``, the server substitutes a deterministic follow-up so
  the user always has a concrete question to answer.

Covers the user's required scenarios:

1. FOLLOW_UP + "进入下一道题" → stays FOLLOW_UP, question index unchanged,
   returns a real follow-up, DB does not store the transition prose.
2. FOLLOW_UP + zero-width-character "下一道题" → normalized detection,
   returns a real follow-up.
3. FOLLOW_UP + only "感谢你的回答" → replaced with the fallback follow-up.
4. Normal FOLLOW_UP (real question) → Dify message preserved, index
   unchanged.
5. Normal NEXT_QUESTION → index 1→2, follow-up count reset, returns the
   second question body.
6. COMPLETE_INTERVIEW → no next question fetched, final evaluation
   triggered.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.integrations.dify.interview_providers import (
    FakeInterviewFinalEvaluationProvider,
    LocalInterviewPlanProvider,
)
from app.models.interviews import InterviewSession
from app.models.matching import MatchReport
from app.schemas.interviews import (
    ChatNextAction,
    ChatTurnGeneration,
    ChatTurnProviderResult,
    ChatTurnWorkflowOutput,
    InterviewCreate,
    InterviewMessageSubmit,
    InterviewType,
)
from app.schemas.matching import MatchCreate
from app.services.interviews import InterviewService
from app.services.matching import MatchService
from tests.test_matching import _create_case

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _report_for_service(db_session: Session, user: Any, fixture_name: str = "skill_gap") -> Any:
    case = _create_case(db_session, user, fixture_name)
    result = MatchService(db_session).create(
        user,
        MatchCreate(resume_version_id=case.version.id, job_id=case.job.id),
    )
    return db_session.get(MatchReport, result.report.id)


def _make_chat_output(
    assistant_message: str,
    next_action: ChatNextAction,
    *,
    follow_up_reason: str = "",
) -> ChatTurnWorkflowOutput:
    return ChatTurnWorkflowOutput(
        assistant_message=assistant_message,
        next_action=next_action,
        follow_up_reason=follow_up_reason,
        generation=ChatTurnGeneration(
            workflow_version="interview-chat-turn-v1",
            workflow_run_id="test-run",
            conversation_id="test-conv",
            provider="fake",
            latency_ms=10,
        ),
    )


class _ScriptedChatProvider:
    """Chat provider that returns pre-scripted outputs in order.

    Each call to ``chat_turn`` pops the next output from the queue. This
    lets a test inject the exact Dify output that triggers the bug
    scenario (e.g. ``FOLLOW_UP`` with transition prose).
    """

    def __init__(self, outputs: list[ChatTurnWorkflowOutput]) -> None:
        self._outputs = list(outputs)
        self._index = 0

    def chat_turn(
        self,
        request: Any,
        *,
        conversation_id: str | None,
        user: str,
    ) -> ChatTurnProviderResult:
        output = self._outputs[self._index]
        self._index += 1
        return ChatTurnProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            conversation_id=conversation_id or "test-conv",
            attempts=[],
        )


def _make_service(
    db_session: Session,
    chat_outputs: list[ChatTurnWorkflowOutput],
) -> InterviewService:
    chat = _ScriptedChatProvider(chat_outputs)
    return InterviewService(
        db_session,
        LocalInterviewPlanProvider(),
        chat,
        FakeInterviewFinalEvaluationProvider(),
    )


def _create_interview(service: InterviewService, user: Any, report: Any) -> Any:
    return service.create(
        user.id,
        InterviewCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report.id,
            interview_type=InterviewType.TECHNICAL,
        ),
    )


def _answer(service: InterviewService, user_id: int, interview_id: int, content: str) -> Any:
    return service.send_message(
        user_id,
        interview_id,
        InterviewMessageSubmit(content=content),
    )


# ---------------------------------------------------------------------------
# 1. FOLLOW_UP + transition prose → stays FOLLOW_UP, real follow-up returned
# ---------------------------------------------------------------------------


def test_followup_with_transition_prose_stays_followup_and_returns_real_question(
    db_session: Session,
    admin_user: Any,
) -> None:
    report = _report_for_service(db_session, admin_user)
    opening = _make_chat_output(
        "你好，请简单自我介绍。",
        ChatNextAction.NEXT_QUESTION,
    )
    # The bug: FOLLOW_UP but text says "进入下一道题".
    buggy = _make_chat_output(
        "感谢你的回答。我们进入下一道题。",
        ChatNextAction.FOLLOW_UP,
        follow_up_reason="请结合一次 Linux 故障排查经历说明你的具体步骤。",
    )
    service = _make_service(db_session, [opening, buggy])
    interview = _create_interview(service, admin_user, report)
    service.start_interview(admin_user.id, interview.id)

    turn = _answer(service, admin_user.id, interview.id, "我有Linux运维经验。")

    # The structured action must stay FOLLOW_UP — prose must not drive state.
    assert turn.next_action == "FOLLOW_UP"
    # Question index must NOT advance.
    session = db_session.get(InterviewSession, interview.id)
    assert session.current_question_index == 0
    assert session.current_follow_up_count == 1
    # The assistant message must NOT be the transition prose.
    assert "进入下一道题" not in turn.assistant_message.content
    # The message must contain a real follow-up (from follow_up_reason).
    assert "Linux" in turn.assistant_message.content or "具体" in turn.assistant_message.content


# ---------------------------------------------------------------------------
# 2. FOLLOW_UP + zero-width characters → normalized detection
# ---------------------------------------------------------------------------


def test_followup_with_zero_width_transition_is_normalized(
    db_session: Session,
    admin_user: Any,
) -> None:
    report = _report_for_service(db_session, admin_user)
    opening = _make_chat_output(
        "你好，请简单自我介绍。",
        ChatNextAction.NEXT_QUESTION,
    )
    # Inject a zero-width space between "下一" and "道题".
    buggy = _make_chat_output(
        "感谢你的回答。我们进入下一\u200b道题。",
        ChatNextAction.FOLLOW_UP,
        follow_up_reason="请说明你排查服务启动失败的具体步骤。",
    )
    service = _make_service(db_session, [opening, buggy])
    interview = _create_interview(service, admin_user, report)
    service.start_interview(admin_user.id, interview.id)

    turn = _answer(service, admin_user.id, interview.id, "我有相关经验。")

    assert turn.next_action == "FOLLOW_UP"
    session = db_session.get(InterviewSession, interview.id)
    assert session.current_question_index == 0
    # The zero-width transition prose must not leak into the stored message.
    assert "道题" not in turn.assistant_message.content
    assert "排查" in turn.assistant_message.content


# ---------------------------------------------------------------------------
# 3. FOLLOW_UP + only "感谢你的回答" → fallback follow-up
# ---------------------------------------------------------------------------


def test_followup_bare_acknowledgement_uses_fallback(
    db_session: Session,
    admin_user: Any,
) -> None:
    report = _report_for_service(db_session, admin_user)
    opening = _make_chat_output(
        "你好，请简单自我介绍。",
        ChatNextAction.NEXT_QUESTION,
    )
    # Bare acknowledgement, no question, no follow_up_reason.
    bare = _make_chat_output(
        "感谢你的回答。",
        ChatNextAction.FOLLOW_UP,
        follow_up_reason="",
    )
    service = _make_service(db_session, [opening, bare])
    interview = _create_interview(service, admin_user, report)
    service.start_interview(admin_user.id, interview.id)

    turn = _answer(service, admin_user.id, interview.id, "我有一定经验。")

    assert turn.next_action == "FOLLOW_UP"
    session = db_session.get(InterviewSession, interview.id)
    assert session.current_question_index == 0
    # Must be the fallback follow-up (contains "具体经历" or "实际行动").
    content = turn.assistant_message.content
    assert "具体经历" in content or "实际行动" in content


# ---------------------------------------------------------------------------
# 4. Normal FOLLOW_UP (real question) → preserved, index unchanged
# ---------------------------------------------------------------------------


def test_normal_followup_preserves_dify_message(
    db_session: Session,
    admin_user: Any,
) -> None:
    report = _report_for_service(db_session, admin_user)
    opening = _make_chat_output(
        "你好，请简单自我介绍。",
        ChatNextAction.NEXT_QUESTION,
    )
    real_followup = _make_chat_output(
        "你提到有Linux经验，请举一个你排查服务无法启动的具体例子，说明用了哪些命令？",
        ChatNextAction.FOLLOW_UP,
        follow_up_reason="需要考察具体命令使用",
    )
    service = _make_service(db_session, [opening, real_followup])
    interview = _create_interview(service, admin_user, report)
    service.start_interview(admin_user.id, interview.id)

    turn = _answer(service, admin_user.id, interview.id, "我使用过systemctl和journalctl。")

    assert turn.next_action == "FOLLOW_UP"
    session = db_session.get(InterviewSession, interview.id)
    assert session.current_question_index == 0
    assert session.current_follow_up_count == 1
    # The valid Dify message must be preserved verbatim.
    assert turn.assistant_message.content == real_followup.assistant_message


# ---------------------------------------------------------------------------
# 5. Normal NEXT_QUESTION → index 1→2, follow-up reset, returns question 2
# ---------------------------------------------------------------------------


def test_normal_next_question_advances_index_and_returns_second_question(
    db_session: Session,
    admin_user: Any,
) -> None:
    report = _report_for_service(db_session, admin_user)
    opening = _make_chat_output(
        "你好，请简单自我介绍。",
        ChatNextAction.NEXT_QUESTION,
    )
    advance = _make_chat_output(
        "好的，我们进入下一题。",
        ChatNextAction.NEXT_QUESTION,
    )
    service = _make_service(db_session, [opening, advance])
    interview = _create_interview(service, admin_user, report)
    service.start_interview(admin_user.id, interview.id)

    session = db_session.get(InterviewSession, interview.id)
    assert session.current_question_index == 0

    turn = _answer(
        service, admin_user.id, interview.id, "我有3年Python开发经验，做过多个FastAPI服务。"
    )

    assert turn.next_action == "NEXT_QUESTION"
    session = db_session.get(InterviewSession, interview.id)
    assert session.current_question_index == 1
    assert session.current_follow_up_count == 0
    # Progress must reflect 2/total.
    assert turn.progress.current_question == 2
    # The assistant message must contain the second question's prompt.
    questions = sorted(session.questions, key=lambda q: q.sequence)
    assert questions[1].prompt in turn.assistant_message.content


# ---------------------------------------------------------------------------
# 6. COMPLETE_INTERVIEW → no next question, final evaluation triggered
# ---------------------------------------------------------------------------


def test_complete_interview_triggers_final_evaluation(
    db_session: Session,
    admin_user: Any,
) -> None:
    """User-initiated completion triggers the final evaluation and
    persists the report. The state machine only allows COMPLETE_INTERVIEW
    via Dify when no next question remains; user-initiated completion
    bypasses that check via ``complete_interview``.
    """
    report = _report_for_service(db_session, admin_user)
    opening = _make_chat_output(
        "你好，请简单自我介绍。",
        ChatNextAction.NEXT_QUESTION,
    )
    service = _make_service(db_session, [opening])
    interview = _create_interview(service, admin_user, report)
    service.start_interview(admin_user.id, interview.id)

    # User explicitly ends the interview before answering everything.
    status = service.complete_interview(admin_user.id, interview.id)

    assert status.chat_status == "COMPLETED"
    session = db_session.get(InterviewSession, interview.id)
    assert session.chat_status == "COMPLETED"
    # The report must be persisted.
    assert session.report is not None
    assert isinstance(session.report, dict)


# ---------------------------------------------------------------------------
# 7. DB does not store transition prose under FOLLOW_UP
# ---------------------------------------------------------------------------


def test_followup_transition_prose_not_persisted(
    db_session: Session,
    admin_user: Any,
) -> None:
    report = _report_for_service(db_session, admin_user)
    opening = _make_chat_output(
        "你好，请简单自我介绍。",
        ChatNextAction.NEXT_QUESTION,
    )
    buggy = _make_chat_output(
        "感谢你的回答。我们进入下一道题。",
        ChatNextAction.FOLLOW_UP,
        follow_up_reason="请结合具体经历说明你的排查步骤。",
    )
    service = _make_service(db_session, [opening, buggy])
    interview = _create_interview(service, admin_user, report)
    service.start_interview(admin_user.id, interview.id)

    service.send_message(
        admin_user.id,
        interview.id,
        InterviewMessageSubmit(content="我有经验。"),
    )

    session = db_session.get(InterviewSession, interview.id)
    # The third message (seq>=3) is the assistant reply to the user answer.
    assistant_msgs = [m for m in session.messages if m.role == "ASSISTANT" and m.sequence >= 3]
    assert len(assistant_msgs) == 1
    stored = assistant_msgs[0].content
    # The transition prose must not be in the stored content.
    assert "进入下一道题" not in stored
    assert "排查" in stored or "具体" in stored


# ---------------------------------------------------------------------------
# 8. FOLLOW_UP where assistant_message AND follow_up_reason are the same
#    evaluative sentence (e.g. "当前回答仍缺少足够的具体细节。") → must use
#    the deterministic fallback, never echo the evaluative sentence back.
# ---------------------------------------------------------------------------


def test_followup_evalutive_sentence_in_both_fields_uses_fallback(
    db_session: Session,
    admin_user: Any,
) -> None:
    """Regression: Dify sometimes fills ``assistant_message`` and
    ``follow_up_reason`` with the same evaluative sentence that contains
    no answerable question (e.g. "当前回答仍缺少足够的具体细节。").

    The server must validate ``follow_up_reason`` with the same rule and
    fall back to the deterministic follow-up question, otherwise the user
    sees a bare evaluation with nothing to answer.
    """
    report = _report_for_service(db_session, admin_user)
    opening = _make_chat_output(
        "你好，请简单自我介绍。",
        ChatNextAction.NEXT_QUESTION,
    )
    # Both fields hold the SAME evaluative sentence — no question mark, no
    # imperative cue, just a generic "needs more detail" statement.
    evaluative = "当前回答仍缺少足够的具体细节。"
    buggy = _make_chat_output(
        evaluative,
        ChatNextAction.FOLLOW_UP,
        follow_up_reason=evaluative,
    )
    service = _make_service(db_session, [opening, buggy])
    interview = _create_interview(service, admin_user, report)
    service.start_interview(admin_user.id, interview.id)

    turn = _answer(service, admin_user.id, interview.id, "我有相关经验。")

    assert turn.next_action == "FOLLOW_UP"
    session = db_session.get(InterviewSession, interview.id)
    assert session.current_question_index == 0
    content = turn.assistant_message.content
    # The evaluative sentence must NOT be echoed back to the user.
    assert "缺少足够的具体细节" not in content
    # The deterministic fallback follow-up must be used instead.
    assert "具体经历" in content or "实际行动" in content
    # The DB must also store the fallback, not the evaluative sentence.
    assistant_msgs = [
        m for m in session.messages if m.role == "ASSISTANT" and m.sequence >= 3
    ]
    assert len(assistant_msgs) == 1
    assert "缺少足够的具体细节" not in assistant_msgs[0].content
