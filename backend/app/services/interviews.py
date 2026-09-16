"""Service layer for the optional evidence-grounded chat interview.

The service builds planning, chat-turn, and final-evaluation inputs only from
owned database records, persists the transcript and reports, and records
auditable provider metadata. The retired one-shot answer evaluator is not part
of this flow.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.integrations.dify.interview_providers import (
    FakeInterviewChatProvider,
    FakeInterviewFinalEvaluationProvider,
    InterviewChatProvider,
    InterviewFinalEvaluationProvider,
    InterviewPlanProvider,
)
from app.job_sources.source_names import canonical_source_name, is_discovery_platform
from app.models.enums import TaskStatus
from app.models.interviews import (
    InterviewMessage,
    InterviewQuestion,
    InterviewSession,
)
from app.models.matching import MatchReport
from app.models.operations import AgentRun, AgentStep, AuditLog, ModelUsageLog
from app.models.resumes import ResumeVersion
from app.repositories.interviews import InterviewRepository
from app.schemas.interviews import (
    AnswerSequenceRefRead,
    ChatNextAction,
    ChatTurnProviderResult,
    ChatTurnWorkflowInput,
    ChatTurnWorkflowOutput,
    FinalDimensionScore,
    FinalDimensionScoreRead,
    FinalEvaluationDimension,
    FinalEvaluationWorkflowInput,
    FinalEvaluationWorkflowOutput,
    InterviewChatReportRead,
    InterviewChatStatus,
    InterviewChatStatusRead,
    InterviewChatTurnResponse,
    InterviewCreate,
    InterviewListRead,
    InterviewMessageRead,
    InterviewMessageSubmit,
    InterviewPlanProviderResult,
    InterviewPlanWorkflowInput,
    InterviewPlanWorkflowOutput,
    InterviewProgressRead,
    InterviewQuestionRead,
    InterviewQuestionType,
    InterviewRead,
    InterviewStatus,
    InterviewType,
)

RUN_TYPE_INTERVIEW = "interview"
MAX_FOLLOW_UPS = 3

logger = logging.getLogger(__name__)

# Zero-width and other invisible characters that can interfere with
# transition-claim detection. Stripped before any text matching.
_INVISIBLE_CHARS = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
_WHITESPACE_RUN = re.compile(r"\s+")


def _normalize_model_text(text: str) -> str:
    """Normalize Dify-generated text for reliable pattern matching.

    Applies Unicode NFKC (compatibility decomposition → composition),
    strips zero-width / BOM / word-joiner characters, collapses
    whitespace runs to a single space, and trims. This guarantees that
    transition-claim detection is not defeated by invisible characters
    or full-width/half-width variants.
    """
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = _INVISIBLE_CHARS.sub("", normalized)
    normalized = _WHITESPACE_RUN.sub(" ", normalized)
    return normalized.strip()


class InterviewService:
    def __init__(
        self,
        session: Session,
        plan_provider: InterviewPlanProvider,
        chat_provider: InterviewChatProvider | None = None,
        final_provider: InterviewFinalEvaluationProvider | None = None,
    ) -> None:
        self.session = session
        self.plan_provider = plan_provider
        self.chat_provider: InterviewChatProvider = (
            chat_provider if chat_provider is not None else FakeInterviewChatProvider()
        )
        self.final_provider: InterviewFinalEvaluationProvider = (
            final_provider if final_provider is not None else FakeInterviewFinalEvaluationProvider()
        )
        self.repository = InterviewRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(
        self,
        user_id: int,
        payload: InterviewCreate,
    ) -> InterviewRead:
        """Generate a new interview session with questions."""
        report = self._owned_successful_report(payload.match_report_id, user_id)
        self._validate_input_relationships(payload, report, user_id)
        version = self._owned_confirmed_version(payload.resume_version_id, user_id)
        job = self.repository.get_owned_job(payload.job_id, user_id)
        if job is None:
            raise AppError("JOB_NOT_FOUND", "The job was not found", 404)
        request = self._plan_workflow_input(version, job, report, payload.interview_type)
        run = self._start_plan_run(user_id, request)
        started = perf_counter()
        try:
            result = self.plan_provider.generate_plan(request)
            self._validate_plan_output(result.output, request)
            session = self._persist_plan_success(
                user_id,
                version,
                job,
                report,
                payload.interview_type,
                result,
                run,
                started,
            )
            self._audit(
                user_id,
                "INTERVIEW_CREATED",
                session.id,
                {
                    "resume_version_id": version.id,
                    "job_id": job.id,
                    "match_report_id": report.id,
                    "interview_type": payload.interview_type.value,
                },
            )
            self.session.commit()
            return self._read(session, run)
        except AppError as exc:
            session = self._persist_plan_failure(
                user_id,
                version,
                job,
                report,
                payload.interview_type,
                run,
                started,
                exc.code,
                exc.message,
            )
            self.session.commit()
            if exc.status_code >= 500:
                return self._read(session, run)
            raise
        except Exception:
            session = self._persist_plan_failure(
                user_id,
                version,
                job,
                report,
                payload.interview_type,
                run,
                started,
                "INTERVIEW_PLAN_FAILED",
                "The interview plan could not be generated",
            )
            self.session.commit()
            return self._read(session, run)

    def list_interviews(
        self,
        user_id: int,
        *,
        offset: int,
        limit: int,
        include_failed: bool = False,
    ) -> InterviewListRead:
        rows, total = self.repository.list_owned(
            user_id=user_id,
            offset=offset,
            limit=limit,
            include_failed=include_failed,
        )
        run_by_session = self._run_by_session(user_id)
        return InterviewListRead(
            items=[self._read(row, run_by_session.get(row.id)) for row in rows],
            total=total,
            offset=offset,
            limit=limit,
        )

    def get(self, user_id: int, session_id: int) -> InterviewRead:
        session = self._owned_session(session_id, user_id)
        run = self.repository.latest_run_for_session(session.id, user_id)
        return self._read(session, run)


    def start_interview(
        self,
        user_id: int,
        session_id: int,
    ) -> InterviewChatStatusRead:
        """Start the chat-based interview by presenting the first question.

        Calls the Chatflow with the first hidden question and an empty
        ``user_answer`` to obtain a natural opening message. Saves the
        Dify ``conversation_id`` for subsequent turns.
        """
        session = self._owned_session(session_id, user_id)
        self._validate_chat_session(session)
        if session.chat_status not in (
            InterviewChatStatus.CREATED.value,
            InterviewChatStatus.WAITING_FOR_ANSWER.value,
        ):
            raise AppError(
                "INTERVIEW_CHAT_ALREADY_STARTED",
                "The interview has already started or is completed",
                409,
            )
        questions = self._sorted_questions(session)
        if not questions:
            raise AppError(
                "INTERVIEW_NO_QUESTIONS",
                "The interview plan has no questions",
                409,
            )
        first_question = questions[0]
        session.current_question_index = 0
        session.current_follow_up_count = 0
        session.chat_status = InterviewChatStatus.PROCESSING_TURN.value
        self.session.flush()

        request = self._chat_workflow_input(session, first_question, "")
        run = self._start_chat_run(user_id, session, first_question, phase="chat_start")
        started = perf_counter()
        try:
            result = self.chat_provider.chat_turn(
                request,
                conversation_id=session.dify_conversation_id,
                user=self._dify_user(session),
            )
        except AppError as exc:
            self._persist_chat_failure(user_id, session, run, started, exc.code, exc.message)
            session.chat_status = InterviewChatStatus.FAILED.value
            self.session.commit()
            raise

        session.dify_conversation_id = session.dify_conversation_id or result.conversation_id
        assistant_message = self._save_message(
            session,
            role="ASSISTANT",
            content=result.output.assistant_message,
            metadata=self._chat_turn_metadata(result.output),
        )
        self._persist_chat_success(user_id, session, run, started, result, phase="chat_start")
        session.chat_status = InterviewChatStatus.WAITING_FOR_ANSWER.value
        self._audit(
            user_id,
            "INTERVIEW_CHAT_STARTED",
            session.id,
            {
                "conversation_id": session.dify_conversation_id,
                "first_question_sequence": first_question.sequence,
                "message_id": assistant_message.id,
            },
        )
        self.session.commit()
        return self._chat_status_read(session)

    def send_message(
        self,
        user_id: int,
        session_id: int,
        payload: InterviewMessageSubmit,
    ) -> InterviewChatTurnResponse:
        """Process one user answer in the chat flow.

        Calls the Chatflow, applies state-machine overrides, saves the
        user and assistant messages, and transitions the session state.
        If the AI decides ``COMPLETE_INTERVIEW`` (or the override forces
        it), the final evaluation is triggered automatically.
        """
        session = self._owned_session(session_id, user_id)
        self._validate_chat_session(session)
        if session.chat_status != InterviewChatStatus.WAITING_FOR_ANSWER.value:
            raise AppError(
                "INTERVIEW_CHAT_NOT_WAITING",
                "The interview is not waiting for an answer",
                409,
            )
        current_question = self._current_question(session)
        if current_question is None:
            raise AppError(
                "INTERVIEW_NO_CURRENT_QUESTION",
                "No current question is available",
                409,
            )

        # Save the user message immediately.
        user_message = self._save_message(
            session,
            role="USER",
            content=payload.content,
            metadata={},
        )
        session.chat_status = InterviewChatStatus.PROCESSING_TURN.value
        self.session.flush()

        request = self._chat_workflow_input(session, current_question, payload.content)
        run = self._start_chat_run(user_id, session, current_question, phase="chat_turn")
        started = perf_counter()
        try:
            result = self.chat_provider.chat_turn(
                request,
                conversation_id=session.dify_conversation_id,
                user=self._dify_user(session),
            )
        except AppError as exc:
            self._persist_chat_failure(user_id, session, run, started, exc.code, exc.message)
            session.chat_status = InterviewChatStatus.WAITING_FOR_ANSWER.value
            self.session.commit()
            raise

        # Apply state-machine overrides to the AI's next_action decision.
        overridden = self._apply_state_machine_overrides(session, result.output, request)
        assistant_content = self._compose_assistant_message(session, current_question, overridden)
        assistant_message = self._save_message(
            session,
            role="ASSISTANT",
            content=assistant_content,
            metadata=self._chat_turn_metadata(overridden),
        )
        self._persist_chat_success(user_id, session, run, started, result, phase="chat_turn")

        # Update session state based on the (possibly overridden) next_action.
        interview_completed = False
        report_status = "pending"
        if overridden.next_action == ChatNextAction.FOLLOW_UP:
            session.current_follow_up_count += 1
            session.chat_status = InterviewChatStatus.WAITING_FOR_ANSWER.value
        elif overridden.next_action == ChatNextAction.NEXT_QUESTION:
            session.current_follow_up_count = 0
            session.current_question_index += 1
            session.chat_status = InterviewChatStatus.WAITING_FOR_ANSWER.value
        elif overridden.next_action == ChatNextAction.COMPLETE_INTERVIEW:
            session.chat_status = InterviewChatStatus.GENERATING_REPORT.value
            self.session.flush()
            self._generate_final_report(user_id, session)
            interview_completed = True
            report_status = "ready"

        self._audit(
            user_id,
            "INTERVIEW_CHAT_TURN",
            session.id,
            {
                "next_action": overridden.next_action.value,
                "current_question_index": session.current_question_index,
                "follow_up_count": session.current_follow_up_count,
                "user_message_id": user_message.id,
                "assistant_message_id": assistant_message.id,
            },
        )
        self.session.commit()
        return InterviewChatTurnResponse(
            user_message=self._message_read(user_message),
            assistant_message=self._message_read(assistant_message),
            next_action=overridden.next_action.value,
            progress=self._progress_read(session),
            interview_completed=interview_completed,
            report_status=report_status,
        )

    def complete_interview(
        self,
        user_id: int,
        session_id: int,
    ) -> InterviewChatStatusRead:
        """User-initiated interview completion.

        Generates the final evaluation report immediately from the
        current transcript, regardless of whether all questions were
        answered.
        """
        session = self._owned_session(session_id, user_id)
        self._validate_chat_session(session)
        if session.chat_status in (
            InterviewChatStatus.COMPLETED.value,
            InterviewChatStatus.GENERATING_REPORT.value,
        ):
            raise AppError(
                "INTERVIEW_CHAT_ALREADY_COMPLETED",
                "The interview is already completed or generating a report",
                409,
            )
        if session.chat_status == InterviewChatStatus.CANCELLED.value:
            raise AppError(
                "INTERVIEW_CHAT_CANCELLED",
                "Cannot complete a cancelled interview",
                409,
            )
        session.chat_status = InterviewChatStatus.GENERATING_REPORT.value
        self.session.flush()
        self._generate_final_report(user_id, session)
        self._audit(user_id, "INTERVIEW_CHAT_COMPLETED", session.id, {})
        self.session.commit()
        return self._chat_status_read(session)

    def cancel_interview(
        self,
        user_id: int,
        session_id: int,
    ) -> InterviewChatStatusRead:
        """Cancel the interview. No further messages are accepted."""
        session = self._owned_session(session_id, user_id)
        self._validate_chat_session(session)
        if session.chat_status in (
            InterviewChatStatus.COMPLETED.value,
            InterviewChatStatus.CANCELLED.value,
        ):
            raise AppError(
                "INTERVIEW_CHAT_ALREADY_FINISHED",
                "The interview is already completed or cancelled",
                409,
            )
        session.chat_status = InterviewChatStatus.CANCELLED.value
        self._audit(user_id, "INTERVIEW_CHAT_CANCELLED", session.id, {})
        self.session.commit()
        return self._chat_status_read(session)

    def get_chat_status(
        self,
        user_id: int,
        session_id: int,
    ) -> InterviewChatStatusRead:
        """Return the current chat status and progress."""
        session = self._owned_session(session_id, user_id)
        self._validate_chat_session(session)
        return self._chat_status_read(session)

    def get_messages(
        self,
        user_id: int,
        session_id: int,
    ) -> list[InterviewMessageRead]:
        """Return all chat messages for the session, ordered by sequence."""
        session = self._owned_session(session_id, user_id)
        self._validate_chat_session(session)
        return [self._message_read(m) for m in self._sorted_messages(session)]

    def get_chat_report(
        self,
        user_id: int,
        session_id: int,
    ) -> InterviewChatReportRead:
        """Return the final chat report. Generates it if not yet done."""
        session = self._owned_session(session_id, user_id)
        self._validate_chat_session(session)
        if session.chat_status == InterviewChatStatus.CANCELLED.value:
            raise AppError(
                "INTERVIEW_CHAT_CANCELLED",
                "Cancelled interviews have no report",
                409,
            )
        if session.chat_status == InterviewChatStatus.FAILED.value:
            raise AppError(
                "INTERVIEW_FAILED",
                "Failed interviews have no report",
                409,
            )
        if session.chat_status == InterviewChatStatus.COMPLETED.value and session.report:
            return self._chat_report_read(session)
        # If the interview is in GENERATING_REPORT or WAITING_FOR_ANSWER
        # with no report, generate it on the fly.
        if not session.report:
            session.chat_status = InterviewChatStatus.GENERATING_REPORT.value
            self.session.flush()
            self._generate_final_report(user_id, session)
            self.session.commit()
        return self._chat_report_read(session)

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _owned_successful_report(self, report_id: int, user_id: int) -> MatchReport:
        report = self.repository.get_owned_match_report(report_id, user_id)
        if report is None:
            raise AppError("MATCH_NOT_FOUND", "The match report was not found", 404)
        if report.status != TaskStatus.SUCCEEDED:
            raise AppError(
                "MATCH_REPORT_NOT_READY",
                "Only successful match reports can drive interview generation",
                409,
            )
        return report

    def _owned_confirmed_version(
        self,
        version_id: int,
        user_id: int,
    ) -> ResumeVersion:
        version = self.repository.get_owned_resume_version(version_id, user_id)
        if version is None:
            raise AppError("RESUME_VERSION_NOT_FOUND", "The resume version was not found", 404)
        if not version.is_confirmed:
            raise AppError(
                "RESUME_VERSION_NOT_CONFIRMED",
                "Only confirmed resume versions can drive interview generation",
                409,
            )
        return version

    def _owned_session(self, session_id: int, user_id: int) -> InterviewSession:
        session = self.repository.get_owned_session(session_id, user_id)
        if session is None:
            raise AppError(
                "INTERVIEW_NOT_FOUND",
                "The interview session was not found",
                404,
            )
        return session

    def _validate_input_relationships(
        self,
        payload: InterviewCreate,
        report: MatchReport,
        user_id: int,
    ) -> None:
        """The resume version, job and match report must be mutually linked."""
        if report.resume_version_id != payload.resume_version_id:
            raise AppError(
                "INTERVIEW_INPUT_MISMATCH",
                "The match report does not reference the supplied resume version",
                409,
            )
        if report.job_id != payload.job_id:
            raise AppError(
                "INTERVIEW_INPUT_MISMATCH",
                "The match report does not reference the supplied job",
                409,
            )
        version = self.repository.get_owned_resume_version(payload.resume_version_id, user_id)
        if version is None:
            raise AppError("RESUME_VERSION_NOT_FOUND", "The resume version was not found", 404)

    def _validate_plan_output(
        self,
        output: InterviewPlanWorkflowOutput,
        request: InterviewPlanWorkflowInput,
    ) -> None:
        """Server-side anti-fabrication checks for the plan.

        Verifies that none of the generated questions ask the user to
        demonstrate a missing skill (a skill the match report says the
        user lacks) as if they had already mastered it. Questions may
        reference missing skills for awareness, but not for
        demonstration.
        """
        missing_skill_names = {
            str(item.get("normalized_name") or item.get("job_raw_name") or "").lower()
            for item in request.match_report.missing_skills
            if item.get("normalized_name") or item.get("job_raw_name")
        }
        for question in output.questions:
            prompt_lower = question.prompt.lower()
            for name in missing_skill_names:
                if not name:
                    continue
                # Allow the skill name to appear in a warning context
                # (e.g., "you mentioned you lack Docker"). Block it in
                # a demonstration context (e.g., "show how you use Docker").
                if name in prompt_lower and "demonstrat" in prompt_lower:
                    raise AppError(
                        "DIFY_OUTPUT_INVALID",
                        (
                            "Question must not ask the user to demonstrate "
                            f"the missing skill '{name}'"
                        ),
                        502,
                    )


    def _plan_workflow_input(
        self,
        version: ResumeVersion,
        job: Any,
        report: MatchReport,
        interview_type: InterviewType,
    ) -> InterviewPlanWorkflowInput:
        from app.schemas.interviews import (
            InterviewJobInput,
            InterviewMatchReportInput,
            InterviewResumeInput,
        )

        profile_data = version.structured_data or {}
        summary_value = profile_data.get("summary") or {}
        summary_text = (
            summary_value.get("value")
            if isinstance(summary_value, dict)
            else str(summary_value or "")
        )
        resume_input = InterviewResumeInput(
            resume_version_id=version.id,
            summary=str(summary_text or "")[:4000],
            education=list(profile_data.get("education", []) or []),
            experiences=list(profile_data.get("work_experience", []) or []),
            projects=list(profile_data.get("project_experience", []) or []),
            skills=list(profile_data.get("technical_skills", []) or []),
        )
        source_name = ""
        is_summary_only = False
        if job.source is not None:
            source_name = canonical_source_name(job.source.name) or job.source.name
            is_summary_only = is_discovery_platform(job.source.name)
        completeness = self._job_information_completeness(report)
        job_input = InterviewJobInput(
            job_id=job.id,
            title=job.title,
            company=job.company,
            summary=self._job_summary(job),
            source_name=source_name,
            source_url=job.source_url,
            information_completeness=completeness,
            is_summary_only=is_summary_only,
        )
        match_input = InterviewMatchReportInput(
            report_id=report.id,
            final_score=report.final_score,
            matched_skills=self._json_list(report.matched_skills),
            partial_skills=self._json_list(report.partial_skills),
            missing_skills=self._json_list(report.missing_skills),
            blocking_risks=self._json_list(report.hard_constraint_warnings),
        )
        return InterviewPlanWorkflowInput(
            interview_type=interview_type,
            resume=resume_input,
            job=job_input,
            match_report=match_input,
        )


    @staticmethod
    def _job_summary(job: Any) -> str:
        parts = [job.description, job.responsibilities, job.requirements]
        return "\n".join(part for part in parts if part).strip()[:8000]

    @staticmethod
    def _job_information_completeness(report: MatchReport) -> float:
        for detail in report.details:
            if detail.category == "REPORT_METADATA" and detail.code == "REPORT_TRUST":
                value = detail.data.get("job_information_completeness")
                if isinstance(value, (int, float)):
                    return float(value)
        return 0.0

    @staticmethod
    def _json_list(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(item) for item in values]

    # ------------------------------------------------------------------
    # Run / persistence helpers — plan generation
    # ------------------------------------------------------------------

    def _start_plan_run(
        self,
        user_id: int,
        request: InterviewPlanWorkflowInput,
    ) -> AgentRun:
        run = AgentRun(
            user_id=user_id,
            run_type=RUN_TYPE_INTERVIEW,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(UTC),
            state_snapshot={
                "user_id": user_id,
                "resume_version_id": request.resume.resume_version_id,
                "job_id": request.job.job_id,
                "match_report_id": request.match_report.report_id,
                "interview_type": request.interview_type.value,
                "phase": "plan_generation",
                "is_summary_only": request.job.is_summary_only,
                "information_completeness": request.job.information_completeness,
            },
        )
        self.repository.add_run(run)
        run.steps.append(
            AgentStep(
                sequence=1,
                node_name="dify_interview_plan_workflow",
                status=TaskStatus.RUNNING,
                started_at=run.started_at,
                input_summary={
                    "resume_version_id": request.resume.resume_version_id,
                    "job_id": request.job.job_id,
                    "match_report_id": request.match_report.report_id,
                    "interview_type": request.interview_type.value,
                    "matched_skill_count": len(request.match_report.matched_skills),
                    "missing_skill_count": len(request.match_report.missing_skills),
                    "blocking_risk_count": len(request.match_report.blocking_risks),
                },
            )
        )
        self.session.flush()
        return run

    def _persist_plan_success(
        self,
        user_id: int,
        version: ResumeVersion,
        job: Any,
        report: MatchReport,
        interview_type: InterviewType,
        result: InterviewPlanProviderResult,
        run: AgentRun,
        started: float,
    ) -> InterviewSession:
        latency_ms = result.output.generation.latency_ms or self._elapsed_ms(started)
        # Build the plan dict stored on the session. This includes the
        # match_report_id and resume_version_id so answer evaluation can
        # reconstruct the context without re-fetching.
        plan_dict: dict[str, Any] = {
            "match_report_id": report.id,
            "resume_version_id": version.id,
            "job_id": job.id,
            "interview_type": interview_type.value,
            "summary": result.output.summary,
            "questions": [q.model_dump(mode="json") for q in result.output.questions],
            "missing_skill_warnings": list(result.output.missing_skill_warnings),
            "fabrication_warnings": list(result.output.fabrication_warnings),
            "job_information_warning": result.output.job_information_warning,
        }
        session = InterviewSession(
            user_id=user_id,
            resume_version_id=version.id,
            job_id=job.id,
            interview_type=interview_type.value,
            status=InterviewStatus.PLANNED.value,
            plan=plan_dict,
            report={},
        )
        self.repository.add_session(session)
        # Create question rows.
        for q in result.output.questions:
            self.repository.add_question(
                InterviewQuestion(
                    session_id=session.id,
                    sequence=q.sequence,
                    question_type=q.question_type.value,
                    prompt=q.prompt,
                    parent_question_id=None,
                )
            )
        run.status = TaskStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        run.state_snapshot = {
            **run.state_snapshot,
            "interview_session_id": session.id,
            "workflow_run_id": result.output.generation.workflow_run_id,
            "workflow_version": result.output.generation.workflow_version,
            "provider": result.output.generation.provider,
            "latency_ms": latency_ms,
            "raw_output": result.raw_output,
            "attempts": [a.model_dump(mode="json") for a in result.attempts],
        }
        self._record_attempts_as_steps(run, result.attempts, latency_ms, succeeded=True)
        self.session.add(
            ModelUsageLog(
                user_id=user_id,
                agent_run_id=run.id,
                provider=result.output.generation.provider,
                model_name="dify-workflow",
                operation="interview_plan",
                latency_ms=latency_ms,
                is_success=True,
            )
        )
        return session

    def _persist_plan_failure(
        self,
        user_id: int,
        version: ResumeVersion,
        job: Any,
        report: MatchReport,
        interview_type: InterviewType,
        run: AgentRun,
        started: float,
        code: str,
        message: str,
    ) -> InterviewSession:
        session = InterviewSession(
            user_id=user_id,
            resume_version_id=version.id,
            job_id=job.id,
            interview_type=interview_type.value,
            status=InterviewStatus.FAILED.value,
            plan={
                "match_report_id": report.id,
                "resume_version_id": version.id,
                "job_id": job.id,
                "interview_type": interview_type.value,
            },
            report={},
        )
        self.repository.add_session(session)
        latency_ms = self._elapsed_ms(started)
        run.status = TaskStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.error_code = code
        run.error_message = message
        run.state_snapshot = {
            **run.state_snapshot,
            "interview_session_id": session.id,
            "latency_ms": latency_ms,
            "error_code": code,
            "error_message": message,
        }
        for step in run.steps:
            step.status = TaskStatus.FAILED
            step.finished_at = run.finished_at
            step.duration_ms = latency_ms
            step.error_message = "The interview plan workflow failed"
        self.session.add(
            ModelUsageLog(
                user_id=user_id,
                agent_run_id=run.id,
                provider="dify",
                model_name="dify-workflow",
                operation="interview_plan",
                latency_ms=latency_ms,
                is_success=False,
                error_code=code,
            )
        )
        return session

    # ------------------------------------------------------------------
    # Run / persistence helpers — answer evaluation
    # ------------------------------------------------------------------


    def _read(
        self,
        session: InterviewSession,
        run: AgentRun | None,
    ) -> InterviewRead:
        snapshot = run.state_snapshot if run is not None else {}
        plan = session.plan or {}
        questions: list[InterviewQuestionRead] = []
        plan_questions = plan.get("questions", []) if isinstance(plan, dict) else []
        plan_by_sequence = {
            int(item["sequence"]): item
            for item in plan_questions
            if isinstance(item, dict) and isinstance(item.get("sequence"), int)
        }
        for question in session.questions:
            metadata = plan_by_sequence.get(question.sequence, {})
            try:
                question_type = InterviewQuestionType(question.question_type)
            except ValueError:
                question_type = InterviewQuestionType.OPENING
            questions.append(
                InterviewQuestionRead(
                    id=question.id,
                    session_id=question.session_id,
                    sequence=question.sequence,
                    question_type=question_type,
                    prompt=question.prompt,
                    intent=str(metadata.get("intent") or ""),
                    expected_evidence_keys=[
                        str(value)
                        for value in (metadata.get("expected_evidence_keys", []) or [])
                    ],
                    created_at=question.created_at,
                )
            )
        try:
            status = InterviewStatus(session.status)
        except ValueError:
            status = InterviewStatus.PLANNED
        try:
            itype = InterviewType(session.interview_type)
        except ValueError:
            itype = InterviewType.COMPREHENSIVE
        return InterviewRead(
            id=session.id,
            user_id=session.user_id,
            resume_version_id=session.resume_version_id,
            job_id=session.job_id,
            interview_type=itype,
            status=status,
            summary=str(plan.get("summary", "")),
            missing_skill_warnings=list(plan.get("missing_skill_warnings", []) or []),
            fabrication_warnings=list(plan.get("fabrication_warnings", []) or []),
            job_information_warning=str(plan.get("job_information_warning", "")),
            workflow_run_id=self._optional_str(snapshot.get("workflow_run_id")),
            workflow_version=self._optional_str(snapshot.get("workflow_version")),
            provider=self._optional_str(snapshot.get("provider")),
            latency_ms=self._optional_int(snapshot.get("latency_ms")),
            error_code=run.error_code if run is not None else None,
            error_message=run.error_message if run is not None else None,
            questions=questions,
            report=session.report or {},
            created_at=session.created_at,
            updated_at=session.updated_at,
        )


    def _run_by_session(self, user_id: int) -> dict[int, AgentRun]:
        result: dict[int, AgentRun] = {}
        for run in self.repository.list_runs_for_user(user_id):
            session_id = self._optional_int(run.state_snapshot.get("interview_session_id"))
            if session_id is not None and session_id not in result:
                result[session_id] = run
        return result

    # ------------------------------------------------------------------
    # Chat helpers
    # ------------------------------------------------------------------

    def _validate_chat_session(self, session: InterviewSession) -> None:
        """Ensure the session is usable for chat operations."""
        if session.status == InterviewStatus.FAILED.value:
            raise AppError(
                "INTERVIEW_FAILED",
                "Failed interviews cannot be used",
                409,
            )

    def _sorted_questions(self, session: InterviewSession) -> list[InterviewQuestion]:
        return sorted(session.questions, key=lambda q: q.sequence)

    def _sorted_messages(self, session: InterviewSession) -> list[InterviewMessage]:
        return sorted(session.messages, key=lambda m: m.sequence)

    def _current_question(self, session: InterviewSession) -> InterviewQuestion | None:
        questions = self._sorted_questions(session)
        idx = session.current_question_index
        if 0 <= idx < len(questions):
            return questions[idx]
        return None

    def _dify_user(self, session: InterviewSession) -> str:
        return f"careerpilot-interview-{session.id}"

    def _next_message_sequence(self, session: InterviewSession) -> int:
        existing = self._sorted_messages(session)
        return (existing[-1].sequence + 1) if existing else 1

    def _save_message(
        self,
        session: InterviewSession,
        *,
        role: str,
        content: str,
        metadata: dict[str, Any],
    ) -> InterviewMessage:
        msg = InterviewMessage(
            session_id=session.id,
            sequence=self._next_message_sequence(session),
            role=role,
            content=content,
            turn_metadata=metadata,
        )
        self.session.add(msg)
        self.session.flush()
        # Add to the session's messages collection for in-memory consistency.
        session.messages.append(msg)
        return msg

    def _chat_workflow_input(
        self,
        session: InterviewSession,
        question: InterviewQuestion,
        user_answer: str,
    ) -> ChatTurnWorkflowInput:
        """Build the Chatflow input from real DB rows."""
        from app.schemas.interviews import (
            InterviewJobInput,
            InterviewMatchReportInput,
            InterviewResumeInput,
        )

        plan = session.plan or {}
        report_id = plan.get("match_report_id")
        version_id = plan.get("resume_version_id")
        # Lazily build the resume/job/match inputs. The schema requires
        # IDs >= 1, so we only construct them when real data is available;
        # otherwise we fall back to a minimal valid placeholder using the
        # session's own foreign keys (which are guaranteed non-zero).
        resume_input = InterviewResumeInput(
            resume_version_id=session.resume_version_id,
            summary="",
        )
        job_input = InterviewJobInput(
            job_id=session.job_id,
            title="Unknown",
            company="Unknown",
        )
        match_input = InterviewMatchReportInput(report_id=report_id or 1)
        if version_id:
            version = self.session.get(ResumeVersion, version_id)
            if version is not None:
                profile_data = version.structured_data or {}
                summary_value = profile_data.get("summary") or {}
                raw_summary = (
                    summary_value.get("value") if isinstance(summary_value, dict) else summary_value
                )
                resume_input = InterviewResumeInput(
                    resume_version_id=version.id,
                    summary=str(raw_summary or "")[:4000],
                    education=list(profile_data.get("education", []) or []),
                    experiences=list(profile_data.get("work_experience", []) or []),
                    projects=list(profile_data.get("project_experience", []) or []),
                    skills=list(profile_data.get("technical_skills", []) or []),
                )
        if report_id:
            report = self.session.get(MatchReport, report_id)
            if report is not None:
                match_input = InterviewMatchReportInput(
                    report_id=report.id,
                    final_score=report.final_score,
                    matched_skills=self._json_list(report.matched_skills),
                    partial_skills=self._json_list(report.partial_skills),
                    missing_skills=self._json_list(report.missing_skills),
                    blocking_risks=self._json_list(report.hard_constraint_warnings),
                )
                job = report.job
                if job is not None:
                    source_name = ""
                    is_summary_only = False
                    if job.source is not None:
                        source_name = canonical_source_name(job.source.name) or job.source.name
                        is_summary_only = is_discovery_platform(job.source.name)
                    job_input = InterviewJobInput(
                        job_id=job.id,
                        title=job.title,
                        company=job.company,
                        summary=self._job_summary(job),
                        source_name=source_name,
                        source_url=job.source_url,
                        information_completeness=self._job_information_completeness(report),
                        is_summary_only=is_summary_only,
                    )
        try:
            qt = InterviewQuestionType(question.question_type)
        except ValueError:
            qt = InterviewQuestionType.OPENING
        intent = ""
        plan_questions = plan.get("questions", []) if isinstance(plan, dict) else []
        for pq in plan_questions:
            if isinstance(pq, dict) and pq.get("sequence") == question.sequence:
                intent = str(pq.get("intent") or "")
                break
        try:
            itype = InterviewType(session.interview_type)
        except ValueError:
            itype = InterviewType.COMPREHENSIVE
        # Build conversation history from saved messages (excluding the
        # current turn's user answer which is passed separately).
        conversation_history: list[dict[str, Any]] = []
        for msg in self._sorted_messages(session):
            conversation_history.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                    "sequence": msg.sequence,
                }
            )
        return ChatTurnWorkflowInput(
            interview_type=itype,
            current_question_sequence=question.sequence,
            current_question_prompt=question.prompt,
            current_question_type=qt,
            current_question_intent=intent,
            user_answer=user_answer,
            follow_up_count=session.current_follow_up_count,
            total_questions=len(self._sorted_questions(session)),
            conversation_history=conversation_history,
            resume=resume_input,
            job=job_input,
            match_report=match_input,
        )

    def _apply_state_machine_overrides(
        self,
        session: InterviewSession,
        output: ChatTurnWorkflowOutput,
        request: ChatTurnWorkflowInput,
    ) -> ChatTurnWorkflowOutput:
        """Override illegal Dify decisions per the state machine rules.

        * FOLLOW_UP at or beyond the follow-up limit: force NEXT_QUESTION
          (or COMPLETE_INTERVIEW if no next question exists).
        * COMPLETE_INTERVIEW while questions remain: force NEXT_QUESTION.
        * NEXT_QUESTION while no next question exists: force
          COMPLETE_INTERVIEW.
        """
        action = output.next_action
        questions = self._sorted_questions(session)
        has_next_question = session.current_question_index + 1 < len(questions)

        if action == ChatNextAction.FOLLOW_UP and session.current_follow_up_count >= MAX_FOLLOW_UPS:
            if has_next_question:
                action = ChatNextAction.NEXT_QUESTION
            else:
                action = ChatNextAction.COMPLETE_INTERVIEW

        if action == ChatNextAction.COMPLETE_INTERVIEW and has_next_question:
            action = ChatNextAction.NEXT_QUESTION

        if action == ChatNextAction.NEXT_QUESTION and not has_next_question:
            action = ChatNextAction.COMPLETE_INTERVIEW

        if action == output.next_action:
            return output
        return output.model_copy(update={"next_action": action})

    def _compose_assistant_message(
        self,
        session: InterviewSession,
        current_question: InterviewQuestion,
        output: ChatTurnWorkflowOutput,
    ) -> str:
        """Compose a state-consistent assistant message for the user.

        The structured ``next_action`` field is the sole authority for state
        transitions. Natural-language prose never drives the state machine.
        For ``FOLLOW_UP``, the message must always contain a real follow-up
        question; if Dify emits transition prose or a bare acknowledgement
        under ``FOLLOW_UP``, the server substitutes a deterministic
        follow-up derived from ``follow_up_reason`` (or a safe fallback) so
        the user always has a concrete question to answer.
        """
        if output.next_action == ChatNextAction.COMPLETE_INTERVIEW:
            return "感谢你的回答。本次模拟面试已经结束，CareerPilot 正在生成最终评估报告。"

        if output.next_action == ChatNextAction.FOLLOW_UP:
            original = output.assistant_message
            normalized = _normalize_model_text(original)
            if self._is_follow_up_message_valid(normalized):
                return original
            # Dify returned an invalid FOLLOW_UP message (transition prose,
            # bare acknowledgement, or no actual question). The structured
            # action stays FOLLOW_UP — only the displayed text is replaced.
            # The follow_up_reason field is also validated because Dify
            # sometimes fills both fields with the same evaluative sentence
            # (e.g. "当前回答仍缺少具体细节。"), which is not an answerable
            # question either.
            reason = _normalize_model_text(output.follow_up_reason)
            reason_valid = self._is_follow_up_message_valid(reason)
            logger.info(
                "interview follow_up message replaced: session_id=%s "
                "original_len=%d normalized_len=%d reason_len=%d reason_valid=%s",
                session.id,
                len(original),
                len(normalized),
                len(reason),
                reason_valid,
            )
            if reason_valid:
                return reason
            return "请结合一个具体经历进一步说明你的处理步骤、实际行动和最终结果。"

        # NEXT_QUESTION is always rendered from the hidden, persisted plan.
        # Do not reuse model-generated transition prose: it may claim that the
        # interview ended or omit the next question entirely.
        questions = self._sorted_questions(session)
        next_idx = session.current_question_index + 1
        if next_idx < len(questions):
            next_prompt = questions[next_idx].prompt
            return f"好的，感谢你的回答。我们进入下一题。\n\n{next_prompt}"
        # This branch should only be reachable for a malformed/late provider
        # response; the state-machine override converts it to completion.
        return "感谢你的回答。本次模拟面试已经结束，CareerPilot 正在生成最终评估报告。"

    @staticmethod
    def _contains_transition_claim(content: str) -> bool:
        """Return whether a follow-up message incorrectly claims a transition.

        ``content`` is expected to be already normalized via
        ``_normalize_model_text``. Matching is performed on the
        whitespace-stripped, lower-cased form.
        """
        compact = re.sub(r"\s+", "", content).lower()
        transition_patterns = (
            "进入下一题",
            "进入下一个问题",
            "下一道题",
            "下一题",
            "面试已经结束",
            "模拟面试已经结束",
            "生成最终评估报告",
            "nextquestion",
            "nextquestionplease",
            "interviewhasended",
        )
        return any(pattern in compact for pattern in transition_patterns)

    @classmethod
    def _is_follow_up_message_valid(cls, normalized: str) -> bool:
        """Validate that a FOLLOW_UP message is a real follow-up question.

        A valid FOLLOW_UP message must:
        * not contain any transition claim (next question / interview ended);
        * be long enough to be more than a bare acknowledgement;
        * contain an actual question — a question mark OR an imperative
          request clause ("请...", "能否...", "请说明..."). Bare evaluative
          statements ("当前回答仍缺少具体细节") are NOT valid follow-ups
          because they give the user nothing concrete to answer.

        ``normalized`` must already be NFKC-normalized and stripped of
        invisible characters via ``_normalize_model_text``.
        """
        if not normalized:
            return False
        if cls._contains_transition_claim(normalized):
            return False
        # A bare acknowledgement like "感谢你的回答。" is too short to be a
        # real follow-up question.
        if len(normalized) < 12:
            return False
        # Must contain a question mark — the clearest signal of a real
        # question the user can answer.
        has_question_mark = any(ch in normalized for ch in ("？", "?"))
        if has_question_mark:
            return True
        # Otherwise require an explicit imperative request clause. Generic
        # nouns/verbs like "具体" or "说明" are too permissive — they match
        # evaluative statements ("说明得很清楚", "缺少具体细节") that are
        # not answerable questions.
        imperative_cues = ("请", "能否", "能不能", "可否", "请具体", "请说明", "请举例")
        return any(cue in normalized for cue in imperative_cues)

    def _chat_turn_metadata(self, output: ChatTurnWorkflowOutput) -> dict[str, Any]:
        """Extract hidden per-turn metadata for storage."""
        return {
            "next_action": output.next_action.value,
            "turn_analysis": output.turn_analysis,
            "follow_up_reason": output.follow_up_reason,
            "unsupported_claims": list(output.unsupported_claims),
            "used_facts": list(output.used_facts),
            "missing_skill_warnings": list(output.missing_skill_warnings),
            "fabrication_warnings": list(output.fabrication_warnings),
            "workflow_version": output.generation.workflow_version,
            "workflow_run_id": output.generation.workflow_run_id,
            "conversation_id": output.generation.conversation_id,
            "provider": output.generation.provider,
            "latency_ms": output.generation.latency_ms,
        }

    def _start_chat_run(
        self,
        user_id: int,
        session: InterviewSession,
        question: InterviewQuestion | None,
        *,
        phase: str,
    ) -> AgentRun:
        run = AgentRun(
            user_id=user_id,
            run_type=RUN_TYPE_INTERVIEW,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(UTC),
            state_snapshot={
                "user_id": user_id,
                "interview_session_id": session.id,
                "phase": phase,
                "conversation_id": session.dify_conversation_id,
                "question_sequence": question.sequence if question else None,
                "current_question_index": session.current_question_index,
                "follow_up_count": session.current_follow_up_count,
            },
        )
        self.repository.add_run(run)
        run.steps.append(
            AgentStep(
                sequence=1,
                node_name=f"dify_interview_chat_{phase}",
                status=TaskStatus.RUNNING,
                started_at=run.started_at,
                input_summary={
                    "interview_session_id": session.id,
                    "phase": phase,
                    "conversation_id": session.dify_conversation_id,
                },
            )
        )
        self.session.flush()
        return run

    def _persist_chat_success(
        self,
        user_id: int,
        session: InterviewSession,
        run: AgentRun,
        started: float,
        result: ChatTurnProviderResult,
        *,
        phase: str,
    ) -> None:
        latency_ms = result.output.generation.latency_ms or self._elapsed_ms(started)
        run.status = TaskStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        run.state_snapshot = {
            **run.state_snapshot,
            "workflow_run_id": result.output.generation.workflow_run_id,
            "workflow_version": result.output.generation.workflow_version,
            "conversation_id": result.conversation_id,
            "provider": result.output.generation.provider,
            "latency_ms": latency_ms,
            "next_action": result.output.next_action.value,
            "raw_output": result.raw_output,
            "attempts": [a.model_dump(mode="json") for a in result.attempts],
        }
        self._record_attempts_as_steps(run, result.attempts, latency_ms, succeeded=True)
        self.session.add(
            ModelUsageLog(
                user_id=user_id,
                agent_run_id=run.id,
                provider=result.output.generation.provider,
                model_name="dify-chatflow",
                operation=f"interview_chat_{phase}",
                latency_ms=latency_ms,
                is_success=True,
            )
        )

    def _persist_chat_failure(
        self,
        user_id: int,
        session: InterviewSession,
        run: AgentRun,
        started: float,
        code: str,
        message: str,
    ) -> None:
        latency_ms = self._elapsed_ms(started)
        run.status = TaskStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.error_code = code
        run.error_message = message
        run.state_snapshot = {
            **run.state_snapshot,
            "latency_ms": latency_ms,
            "error_code": code,
            "error_message": message,
        }
        for step in run.steps:
            step.status = TaskStatus.FAILED
            step.finished_at = run.finished_at
            step.duration_ms = latency_ms
            step.error_message = "The interview chat workflow failed"
        self.session.add(
            ModelUsageLog(
                user_id=user_id,
                agent_run_id=run.id,
                provider="dify",
                model_name="dify-chatflow",
                operation="interview_chat",
                latency_ms=latency_ms,
                is_success=False,
                error_code=code,
            )
        )

    def _build_transcript(self, session: InterviewSession) -> list[dict[str, Any]]:
        """Build the transcript from saved messages for final evaluation."""
        transcript: list[dict[str, Any]] = []
        current_q_seq = 0
        for msg in self._sorted_messages(session):
            if msg.role == "ASSISTANT":
                # Track which question is being discussed.
                metadata = msg.turn_metadata or {}
                action = metadata.get("next_action", "")
                if action == "NEXT_QUESTION":
                    current_q_seq += 1
                elif not transcript:
                    current_q_seq = 1
            transcript.append(
                {
                    "role": msg.role,
                    "content": msg.content,
                    "sequence": msg.sequence,
                    "question_sequence": current_q_seq if msg.role == "USER" else None,
                }
            )
        return transcript

    def _final_eval_input(
        self,
        session: InterviewSession,
    ) -> FinalEvaluationWorkflowInput:
        from app.schemas.interviews import (
            InterviewJobInput,
            InterviewMatchReportInput,
            InterviewResumeInput,
        )

        plan = session.plan or {}
        report_id = plan.get("match_report_id")
        version_id = plan.get("resume_version_id")
        # Lazily build the resume/job/match inputs. The schema requires
        # IDs >= 1, so we only construct them when real data is available;
        # otherwise we fall back to a minimal valid placeholder using the
        # session's own foreign keys (which are guaranteed non-zero).
        resume_input = InterviewResumeInput(
            resume_version_id=session.resume_version_id,
            summary="",
        )
        job_input = InterviewJobInput(
            job_id=session.job_id,
            title="Unknown",
            company="Unknown",
        )
        match_input = InterviewMatchReportInput(report_id=report_id or 1)
        if version_id:
            version = self.session.get(ResumeVersion, version_id)
            if version is not None:
                profile_data = version.structured_data or {}
                summary_value = profile_data.get("summary") or {}
                raw_summary = (
                    summary_value.get("value") if isinstance(summary_value, dict) else summary_value
                )
                resume_input = InterviewResumeInput(
                    resume_version_id=version.id,
                    summary=str(raw_summary or "")[:4000],
                    education=list(profile_data.get("education", []) or []),
                    experiences=list(profile_data.get("work_experience", []) or []),
                    projects=list(profile_data.get("project_experience", []) or []),
                    skills=list(profile_data.get("technical_skills", []) or []),
                )
        if report_id:
            report = self.session.get(MatchReport, report_id)
            if report is not None:
                match_input = InterviewMatchReportInput(
                    report_id=report.id,
                    final_score=report.final_score,
                    matched_skills=self._json_list(report.matched_skills),
                    partial_skills=self._json_list(report.partial_skills),
                    missing_skills=self._json_list(report.missing_skills),
                    blocking_risks=self._json_list(report.hard_constraint_warnings),
                )
                job = report.job
                if job is not None:
                    source_name = ""
                    is_summary_only = False
                    if job.source is not None:
                        source_name = canonical_source_name(job.source.name) or job.source.name
                        is_summary_only = is_discovery_platform(job.source.name)
                    job_input = InterviewJobInput(
                        job_id=job.id,
                        title=job.title,
                        company=job.company,
                        summary=self._job_summary(job),
                        source_name=source_name,
                        source_url=job.source_url,
                        information_completeness=self._job_information_completeness(report),
                        is_summary_only=is_summary_only,
                    )
        try:
            itype = InterviewType(session.interview_type)
        except ValueError:
            itype = InterviewType.COMPREHENSIVE
        return FinalEvaluationWorkflowInput(
            interview_type=itype,
            transcript=self._build_transcript(session),
            question_count=len(self._sorted_questions(session)),
            resume=resume_input,
            job=job_input,
            match_report=match_input,
        )

    def _generate_final_report(
        self,
        user_id: int,
        session: InterviewSession,
    ) -> None:
        """Call the final evaluation provider and save the report."""
        transcript = self._build_transcript(session)
        if not transcript:
            session.report = {
                "schema_version": "interview-final-evaluation-v1",
                "error": "No transcript available for evaluation",
            }
            session.chat_status = InterviewChatStatus.COMPLETED.value
            session.status = InterviewStatus.COMPLETED.value
            return

        request = self._final_eval_input(session)
        run = AgentRun(
            user_id=user_id,
            run_type=RUN_TYPE_INTERVIEW,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(UTC),
            state_snapshot={
                "user_id": user_id,
                "interview_session_id": session.id,
                "phase": "final_evaluation",
            },
        )
        self.repository.add_run(run)
        run.steps.append(
            AgentStep(
                sequence=1,
                node_name="dify_interview_final_evaluation",
                status=TaskStatus.RUNNING,
                started_at=run.started_at,
                input_summary={
                    "interview_session_id": session.id,
                    "transcript_length": len(transcript),
                    "question_count": request.question_count,
                },
            )
        )
        self.session.flush()
        started = perf_counter()
        try:
            result = self.final_provider.evaluate_final(request)
            self._validate_final_output(result.output, request)
            overall_score = self._recompute_overall_score(result.output.dimension_scores)
            report_data = self._build_final_report_dict(result.output, overall_score)
            session.report = report_data
            session.chat_status = InterviewChatStatus.COMPLETED.value
            session.status = InterviewStatus.COMPLETED.value
            latency_ms = result.output.generation.latency_ms or self._elapsed_ms(started)
            run.status = TaskStatus.SUCCEEDED
            run.finished_at = datetime.now(UTC)
            run.state_snapshot = {
                **run.state_snapshot,
                "workflow_run_id": result.output.generation.workflow_run_id,
                "workflow_version": result.output.generation.workflow_version,
                "provider": result.output.generation.provider,
                "latency_ms": latency_ms,
                "overall_score": overall_score,
                "raw_output": result.raw_output,
                "attempts": [a.model_dump(mode="json") for a in result.attempts],
            }
            self._record_attempts_as_steps(run, result.attempts, latency_ms, succeeded=True)
            self.session.add(
                ModelUsageLog(
                    user_id=user_id,
                    agent_run_id=run.id,
                    provider=result.output.generation.provider,
                    model_name="dify-workflow",
                    operation="interview_final_evaluation",
                    latency_ms=latency_ms,
                    is_success=True,
                )
            )
        except AppError as exc:
            latency_ms = self._elapsed_ms(started)
            run.status = TaskStatus.FAILED
            run.finished_at = datetime.now(UTC)
            run.error_code = exc.code
            run.error_message = exc.message
            run.state_snapshot = {
                **run.state_snapshot,
                "latency_ms": latency_ms,
                "error_code": exc.code,
                "error_message": exc.message,
            }
            for step in run.steps:
                step.status = TaskStatus.FAILED
                step.finished_at = run.finished_at
                step.duration_ms = latency_ms
                step.error_message = "The final evaluation workflow failed"
            self.session.add(
                ModelUsageLog(
                    user_id=user_id,
                    agent_run_id=run.id,
                    provider="dify",
                    model_name="dify-workflow",
                    operation="interview_final_evaluation",
                    latency_ms=latency_ms,
                    is_success=False,
                    error_code=exc.code,
                )
            )
            session.chat_status = InterviewChatStatus.FAILED.value
            session.report = {
                "schema_version": "interview-final-evaluation-v1",
                "error_code": exc.code,
                "error_message": exc.message,
            }
            raise

    @staticmethod
    def _recompute_overall_score(
        dimension_scores: list[FinalDimensionScore],
    ) -> int:
        """Compute the overall score as the mean of the five dimensions.

        The LLM's ``overall_score`` is never trusted. Python always
        recomputes it to ensure consistency.
        """
        if not dimension_scores:
            return 0
        return round(sum(d.score for d in dimension_scores) / len(dimension_scores))

    def _validate_final_output(
        self,
        output: FinalEvaluationWorkflowOutput,
        request: FinalEvaluationWorkflowInput,
    ) -> None:
        """Validate that best/weakest answers reference real question sequences."""
        max_seq = request.question_count
        for ref in output.best_answers:
            if ref.question_sequence < 1 or ref.question_sequence > max_seq:
                raise AppError(
                    "DIFY_OUTPUT_INVALID",
                    f"best_answers reference invalid question_sequence {ref.question_sequence}",
                    502,
                )
        for ref in output.weakest_answers:
            if ref.question_sequence < 1 or ref.question_sequence > max_seq:
                raise AppError(
                    "DIFY_OUTPUT_INVALID",
                    f"weakest_answers reference invalid question_sequence {ref.question_sequence}",
                    502,
                )

    def _build_final_report_dict(
        self,
        output: FinalEvaluationWorkflowOutput,
        overall_score: int,
    ) -> dict[str, Any]:
        return {
            "schema_version": "interview-final-evaluation-v1",
            "overall_score": overall_score,
            "dimension_scores": [d.model_dump(mode="json") for d in output.dimension_scores],
            "summary": output.summary,
            "strengths": list(output.strengths),
            "weaknesses": list(output.weaknesses),
            "best_answers": [a.model_dump(mode="json") for a in output.best_answers],
            "weakest_answers": [a.model_dump(mode="json") for a in output.weakest_answers],
            "unsupported_claims": list(output.unsupported_claims),
            "missing_skill_warnings": list(output.missing_skill_warnings),
            "fabrication_warnings": list(output.fabrication_warnings),
            "improvement_suggestions": list(output.improvement_suggestions),
            "practice_questions": list(output.practice_questions),
            "used_facts": list(output.used_facts),
            "generation": output.generation.model_dump(mode="json"),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def _progress_read(self, session: InterviewSession) -> InterviewProgressRead:
        questions = self._sorted_questions(session)
        current = min(session.current_question_index + 1, len(questions)) if questions else 0
        return InterviewProgressRead(
            current_question=current,
            total_questions=len(questions),
            follow_up_count=session.current_follow_up_count,
        )

    def _chat_status_read(self, session: InterviewSession) -> InterviewChatStatusRead:
        try:
            status = InterviewStatus(session.status)
        except ValueError:
            status = InterviewStatus.PLANNED
        try:
            chat_status = InterviewChatStatus(session.chat_status)
        except ValueError:
            chat_status = InterviewChatStatus.CREATED
        return InterviewChatStatusRead(
            id=session.id,
            chat_status=chat_status,
            status=status,
            progress=self._progress_read(session),
            dify_conversation_id=session.dify_conversation_id,
        )

    def _message_read(self, msg: InterviewMessage) -> InterviewMessageRead:
        return InterviewMessageRead(
            id=msg.id,
            session_id=msg.session_id,
            sequence=msg.sequence,
            role=msg.role,
            content=msg.content,
            created_at=msg.created_at,
        )

    def _chat_report_read(self, session: InterviewSession) -> InterviewChatReportRead:
        report = session.report or {}
        try:
            status = InterviewStatus(session.status)
        except ValueError:
            status = InterviewStatus.PLANNED
        try:
            itype = InterviewType(session.interview_type)
        except ValueError:
            itype = InterviewType.COMPREHENSIVE

        dimension_scores: list[FinalDimensionScoreRead] = []
        for item in report.get("dimension_scores", []) or []:
            try:
                dim = FinalEvaluationDimension(item["dimension"])
            except (KeyError, ValueError):
                continue
            dimension_scores.append(
                FinalDimensionScoreRead(
                    dimension=dim,
                    score=int(item.get("score", 0)),
                    rationale=str(item.get("rationale", "")),
                )
            )

        best_answers: list[AnswerSequenceRefRead] = []
        for item in report.get("best_answers", []) or []:
            best_answers.append(
                AnswerSequenceRefRead(
                    question_sequence=int(item.get("question_sequence", 0)),
                    excerpt=str(item.get("excerpt", "")),
                    reason=str(item.get("reason", "")),
                )
            )

        weakest_answers: list[AnswerSequenceRefRead] = []
        for item in report.get("weakest_answers", []) or []:
            weakest_answers.append(
                AnswerSequenceRefRead(
                    question_sequence=int(item.get("question_sequence", 0)),
                    excerpt=str(item.get("excerpt", "")),
                    reason=str(item.get("reason", "")),
                )
            )

        return InterviewChatReportRead(
            id=session.id,
            status=status,
            chat_status=str(session.chat_status),
            interview_type=itype,
            overall_score=self._optional_float(report.get("overall_score")),
            dimension_scores=dimension_scores,
            summary=str(report.get("summary", "")),
            strengths=list(report.get("strengths", []) or []),
            weaknesses=list(report.get("weaknesses", []) or []),
            best_answers=best_answers,
            weakest_answers=weakest_answers,
            unsupported_claims=list(report.get("unsupported_claims", []) or []),
            missing_skill_warnings=list(report.get("missing_skill_warnings", []) or []),
            fabrication_warnings=list(report.get("fabrication_warnings", []) or []),
            improvement_suggestions=list(report.get("improvement_suggestions", []) or []),
            practice_questions=list(report.get("practice_questions", []) or []),
            used_facts=list(report.get("used_facts", []) or []),
            question_count=int(report.get("question_count", len(self._sorted_questions(session)))),
            answered_count=int(report.get("answered_count", 0)),
            report=report,
            generated_at=self._optional_datetime(report.get("generated_at")),
            error_code=self._optional_str(report.get("error_code")),
            error_message=self._optional_str(report.get("error_message")),
        )

    def _audit(
        self,
        user_id: int,
        action: str,
        session_id: int,
        details: dict[str, Any],
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=user_id,
                action=action,
                resource_type="interview",
                resource_id=str(session_id),
                details=details,
            )
        )

    def _record_attempts_as_steps(
        self,
        run: AgentRun,
        attempts: list[Any],
        latency_ms: int,
        *,
        succeeded: bool,
    ) -> None:
        if not attempts:
            return
        next_sequence = max((step.sequence for step in run.steps), default=0) + 1
        for attempt in attempts:
            run.steps.append(
                AgentStep(
                    sequence=next_sequence,
                    node_name="dify_workflow_attempt",
                    status=TaskStatus.SUCCEEDED if succeeded else TaskStatus.FAILED,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    duration_ms=attempt.latency_ms,
                    retry_count=1 if attempt.retried else 0,
                    input_summary={
                        "sequence": attempt.sequence,
                        "retried": attempt.retried,
                    },
                    output_summary={
                        "http_status": attempt.http_status,
                        "workflow_run_id": attempt.workflow_run_id,
                        "workflow_id": getattr(attempt, "workflow_id", None),
                        "status": attempt.status,
                        "error": attempt.error,
                        "total_steps": getattr(attempt, "total_steps", None),
                        "elapsed_time": getattr(attempt, "elapsed_time", None),
                        "outputs_keys": getattr(attempt, "outputs_keys", []),
                        "error_code": getattr(attempt, "error_code", None),
                        "error_message": getattr(attempt, "error_message", None),
                        "latency_ms": attempt.latency_ms,
                    },
                )
            )
            next_sequence += 1

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(round((perf_counter() - started) * 1000), 0)

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return value if isinstance(value, int) else None

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        return value if isinstance(value, (int, float)) else None

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return None
        return None
