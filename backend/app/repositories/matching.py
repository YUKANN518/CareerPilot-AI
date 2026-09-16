from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import TaskStatus
from app.models.jobs import Job, JobSkill
from app.models.matching import MatchDetail, MatchReport
from app.models.resumes import Resume, ResumeSkill, ResumeVersion, Skill


class MatchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_resume_version_for_owner(
        self,
        version_id: int,
        owner_id: int,
    ) -> ResumeVersion | None:
        return self.session.scalar(
            select(ResumeVersion)
            .join(Resume)
            .where(
                ResumeVersion.id == version_id,
                Resume.owner_id == owner_id,
            )
            .options(
                selectinload(ResumeVersion.resume),
                selectinload(ResumeVersion.skills).selectinload(ResumeSkill.skill),
            )
        )

    def get_visible_job(self, job_id: int, user_id: int) -> Job | None:
        return self.session.scalar(
            select(Job)
            .where(
                Job.id == job_id,
                or_(Job.owner_id.is_(None), Job.owner_id == user_id),
            )
            .options(
                selectinload(Job.source),
                selectinload(Job.skills).selectinload(JobSkill.skill),
            )
        )

    def get_owned_report(self, report_id: int, user_id: int) -> MatchReport | None:
        return self.session.scalar(
            select(MatchReport)
            .where(MatchReport.id == report_id, MatchReport.user_id == user_id)
            .options(
                selectinload(MatchReport.details).selectinload(MatchDetail.evidence),
            )
        )

    def find_successful(
        self,
        *,
        user_id: int,
        resume_version_id: int,
        job_id: int,
        scoring_version: str,
        scoring_config_snapshot: dict[str, object],
    ) -> MatchReport | None:
        return self.session.scalar(
            select(MatchReport)
            .where(
                MatchReport.user_id == user_id,
                MatchReport.resume_version_id == resume_version_id,
                MatchReport.job_id == job_id,
                MatchReport.scoring_version == scoring_version,
                MatchReport.scoring_config_snapshot == scoring_config_snapshot,
                MatchReport.status == TaskStatus.SUCCEEDED,
            )
            .options(
                selectinload(MatchReport.details).selectinload(MatchDetail.evidence),
            )
            .order_by(MatchReport.created_at.desc())
        )

    def list_owned(
        self,
        *,
        user_id: int,
        resume_version_id: int | None = None,
        job_id: int | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[MatchReport], int]:
        statement = select(MatchReport).where(MatchReport.user_id == user_id)
        if resume_version_id is not None:
            statement = statement.where(MatchReport.resume_version_id == resume_version_id)
        if job_id is not None:
            statement = statement.where(MatchReport.job_id == job_id)
        total = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        reports = self.session.scalars(
            statement.options(
                selectinload(MatchReport.details).selectinload(MatchDetail.evidence),
            )
            .order_by(MatchReport.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()
        return list(reports), total

    def skill_dictionary(self) -> dict[str, tuple[str, str | None]]:
        skills = self.session.scalars(select(Skill).options(selectinload(Skill.aliases))).all()
        result: dict[str, tuple[str, str | None]] = {}
        for skill in skills:
            result[skill.name] = (skill.name, skill.category)
            for alias in skill.aliases:
                result[alias.alias] = (skill.name, skill.category)
        return result
