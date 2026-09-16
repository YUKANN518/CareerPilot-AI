"""Repository for optional chat interview records.

Stores interviews as ``InterviewSession`` rows with linked
``InterviewQuestion`` rows. The repository also
tracks ``AgentRun`` / ``AgentStep`` history for audit and retries
without creating duplicate user-visible rows.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.interviews import InterviewQuestion, InterviewSession
from app.models.jobs import Job
from app.models.matching import MatchDetail, MatchReport
from app.models.operations import AgentRun
from app.models.resumes import Resume, ResumeVersion


class InterviewRepository:
    """Persistence helpers for interview records."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Ownership-bound lookups
    # ------------------------------------------------------------------

    def get_owned_resume_version(
        self,
        version_id: int,
        user_id: int,
    ) -> ResumeVersion | None:
        """Return the resume version if it belongs to ``user_id``."""
        return self.session.scalar(
            select(ResumeVersion)
            .join(Resume, ResumeVersion.resume_id == Resume.id)
            .where(ResumeVersion.id == version_id, Resume.owner_id == user_id)
            .options(selectinload(ResumeVersion.skills))
        )

    def get_owned_job(self, job_id: int, user_id: int) -> Job | None:
        """Return the job. Jobs are shared resources; ownership is not
        enforced here but the service verifies the match report linkage
        before using the job."""
        return self.session.scalar(
            select(Job).where(Job.id == job_id).options(selectinload(Job.source))
        )

    def get_owned_match_report(
        self,
        report_id: int,
        user_id: int,
    ) -> MatchReport | None:
        """Return the match report if it belongs to ``user_id``."""
        return self.session.scalar(
            select(MatchReport)
            .where(MatchReport.id == report_id, MatchReport.user_id == user_id)
            .options(
                selectinload(MatchReport.job).selectinload(Job.source),
                selectinload(MatchReport.resume_version),
                selectinload(MatchReport.details).selectinload(MatchDetail.evidence),
            )
        )

    def get_owned_session(
        self,
        session_id: int,
        user_id: int,
    ) -> InterviewSession | None:
        """Return the interview session with questions eagerly
        loaded, if it belongs to ``user_id``."""
        return self.session.scalar(
            select(InterviewSession)
            .where(
                InterviewSession.id == session_id,
                InterviewSession.user_id == user_id,
            )
            .options(selectinload(InterviewSession.questions))
        )

    def list_owned(
        self,
        *,
        user_id: int,
        offset: int,
        limit: int,
        include_failed: bool = False,
    ) -> tuple[list[InterviewSession], int]:
        statement = select(InterviewSession).where(
            InterviewSession.user_id == user_id,
        )
        if not include_failed:
            statement = statement.where(InterviewSession.status != "FAILED")
        total = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        rows = self.session.scalars(
            statement.order_by(InterviewSession.created_at.desc()).offset(offset).limit(limit)
        ).all()
        return list(rows), total

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add_session(self, session: InterviewSession) -> InterviewSession:
        self.session.add(session)
        self.session.flush()
        return session

    def add_question(self, question: InterviewQuestion) -> InterviewQuestion:
        self.session.add(question)
        self.session.flush()
        return question

    def add_run(self, run: AgentRun) -> AgentRun:
        self.session.add(run)
        self.session.flush()
        return run

    # ------------------------------------------------------------------
    # AgentRun tracking
    # ------------------------------------------------------------------

    def list_runs_for_user(self, user_id: int) -> list[AgentRun]:
        return list(
            self.session.scalars(
                select(AgentRun)
                .where(
                    AgentRun.user_id == user_id,
                    AgentRun.run_type == "interview",
                )
                .order_by(AgentRun.created_at.desc())
            )
        )

    def latest_run_for_session(self, session_id: int, user_id: int) -> AgentRun | None:
        return self.session.scalar(
            select(AgentRun)
            .where(
                AgentRun.user_id == user_id,
                AgentRun.run_type == "interview",
                AgentRun.state_snapshot["interview_session_id"].as_integer() == session_id,
            )
            .order_by(AgentRun.created_at.desc())
        )
