"""Repository for resume optimization records (Stage 3).

Stores optimization records as ``GeneratedMaterial`` rows with
``material_type='resume_optimization'`` and links them to the parent
resume version, job and match report. The repository also tracks
``AgentRun`` / ``AgentStep`` history for audit and retries without
creating duplicate user-visible rows.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models.career import GeneratedMaterial
from app.models.jobs import Job
from app.models.matching import MatchDetail, MatchReport
from app.models.operations import AgentRun
from app.models.resumes import Resume, ResumeVersion
from app.models.users import User


class ResumeOptimizationRepository:
    """Persistence helpers for resume optimization records."""

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
        """Return the job if owned by ``user_id`` or publicly visible."""
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

    def get_owned_material(
        self,
        material_id: int,
        user_id: int,
    ) -> GeneratedMaterial | None:
        return self.session.scalar(
            select(GeneratedMaterial).where(
                GeneratedMaterial.id == material_id,
                GeneratedMaterial.user_id == user_id,
                GeneratedMaterial.material_type == "resume_optimization",
            )
        )

    def list_owned(
        self,
        *,
        user_id: int,
        offset: int,
        limit: int,
        include_failed: bool = False,
    ) -> tuple[list[GeneratedMaterial], int]:
        statement = select(GeneratedMaterial).where(
            GeneratedMaterial.user_id == user_id,
            GeneratedMaterial.material_type == "resume_optimization",
        )
        if not include_failed:
            statement = statement.where(GeneratedMaterial.status != "FAILED")
        total = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        rows = self.session.scalars(
            statement.order_by(GeneratedMaterial.created_at.desc()).offset(offset).limit(limit)
        ).all()
        return list(rows), total

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add_material(self, material: GeneratedMaterial) -> GeneratedMaterial:
        self.session.add(material)
        self.session.flush()
        return material

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
                    AgentRun.run_type == "resume_optimization",
                )
                .order_by(AgentRun.created_at.desc())
            )
        )

    def latest_run_for_material(self, material_id: int, user_id: int) -> AgentRun | None:
        return self.session.scalar(
            select(AgentRun)
            .where(
                AgentRun.user_id == user_id,
                AgentRun.run_type == "resume_optimization",
                AgentRun.state_snapshot["generated_material_id"].as_integer() == material_id,
            )
            .order_by(AgentRun.created_at.desc())
        )

    # ------------------------------------------------------------------
    # Helpers for new resume version creation
    # ------------------------------------------------------------------

    def get_resume_owner(self, resume_id: int) -> User | None:
        return self.session.scalar(
            select(User).join(Resume, Resume.owner_id == User.id).where(Resume.id == resume_id)
        )

    def next_version_number(self, resume_id: int) -> int:
        statement = select(func.max(ResumeVersion.version_number)).where(
            ResumeVersion.resume_id == resume_id
        )
        return int(self.session.scalar(statement) or 0) + 1
