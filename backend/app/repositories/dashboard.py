from datetime import UTC, datetime, timedelta

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.applications import Application
from app.models.enums import ApplicationStatus, ResumeStatus, TaskStatus
from app.models.jobs import Job
from app.models.matching import MatchReport
from app.models.resumes import Resume, ResumeSkill, ResumeVersion, Skill


class DashboardRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def recent_resumes(self, user_id: int, limit: int = 3) -> list[Resume]:
        return list(
            self.session.scalars(
                select(Resume)
                .where(Resume.owner_id == user_id)
                .options(selectinload(Resume.file_asset))
                .order_by(Resume.updated_at.desc())
                .limit(limit)
            ).all()
        )

    def resume_status_counts(self, user_id: int) -> dict[ResumeStatus, int]:
        rows = self.session.execute(
            select(Resume.status, func.count(Resume.id))
            .where(Resume.owner_id == user_id)
            .group_by(Resume.status)
        ).all()
        return {status: int(count) for status, count in rows}

    def current_confirmed_version(self, user_id: int) -> ResumeVersion | None:
        return self.session.scalar(
            select(ResumeVersion)
            .join(Resume)
            .where(
                Resume.owner_id == user_id,
                ResumeVersion.is_confirmed.is_(True),
                ResumeVersion.is_current.is_(True),
            )
            .order_by(ResumeVersion.created_at.desc())
        )

    def pending_parse_results(self, user_id: int) -> list[dict[str, object]]:
        values = self.session.scalars(
            select(Resume.parse_result).where(
                Resume.owner_id == user_id,
                Resume.status == ResumeStatus.NEEDS_CONFIRMATION,
                Resume.parse_result.is_not(None),
            )
        ).all()
        return [value for value in values if isinstance(value, dict)]

    def confirmed_version_count(self, user_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count(ResumeVersion.id))
                .join(Resume)
                .where(
                    Resume.owner_id == user_id,
                    ResumeVersion.is_confirmed.is_(True),
                )
            )
            or 0
        )

    def confirmed_skill_evidence_count(self, user_id: int) -> int:
        return int(
            self.session.scalar(
                select(func.count(ResumeSkill.id))
                .join(ResumeVersion)
                .join(Resume)
                .where(
                    Resume.owner_id == user_id,
                    ResumeVersion.is_confirmed.is_(True),
                    ResumeSkill.is_user_confirmed.is_(True),
                    func.length(func.trim(ResumeSkill.evidence_text)) > 0,
                )
            )
            or 0
        )

    def top_confirmed_skills(
        self,
        user_id: int,
        limit: int = 4,
    ) -> list[tuple[str, int]]:
        rows = self.session.execute(
            select(Skill.name, func.count(ResumeSkill.id).label("evidence_count"))
            .join(ResumeSkill)
            .join(ResumeVersion)
            .join(Resume)
            .where(
                Resume.owner_id == user_id,
                ResumeVersion.is_confirmed.is_(True),
                ResumeSkill.is_user_confirmed.is_(True),
                func.length(func.trim(ResumeSkill.evidence_text)) > 0,
            )
            .group_by(Skill.id, Skill.name)
            .order_by(func.count(ResumeSkill.id).desc(), Skill.name.asc())
            .limit(limit)
        ).all()
        return [(str(name), int(count)) for name, count in rows]

    def match_summary(self, user_id: int) -> tuple[int, float | None, int]:
        row = self.session.execute(
            select(
                func.count(distinct(MatchReport.job_id)),
                func.avg(MatchReport.final_score),
            ).where(
                MatchReport.user_id == user_id,
                MatchReport.status == TaskStatus.SUCCEEDED,
                MatchReport.final_score.is_not(None),
            )
        ).one()
        recommended_count = int(
            self.session.scalar(
                select(func.count(distinct(MatchReport.job_id))).where(
                    MatchReport.user_id == user_id,
                    MatchReport.status == TaskStatus.SUCCEEDED,
                    MatchReport.recommendation_level.in_(["STRONGLY_RECOMMENDED", "RECOMMENDED"]),
                )
            )
            or 0
        )
        average = float(row[1]) if row[1] is not None else None
        return int(row[0] or 0), average, recommended_count

    def recent_recommended_reports(
        self,
        user_id: int,
        limit: int = 12,
    ) -> list[tuple[MatchReport, Job]]:
        rows = self.session.execute(
            select(MatchReport, Job)
            .join(Job, Job.id == MatchReport.job_id)
            .where(
                MatchReport.user_id == user_id,
                MatchReport.status == TaskStatus.SUCCEEDED,
                MatchReport.final_score.is_not(None),
                MatchReport.recommendation_level.in_(
                    ["STRONGLY_RECOMMENDED", "RECOMMENDED", "CONSIDER"]
                ),
            )
            .order_by(MatchReport.created_at.desc())
            .limit(limit)
        ).all()
        return [(report, job) for report, job in rows]

    def application_summary(self, user_id: int) -> tuple[dict[ApplicationStatus, int], int, int]:
        rows = self.session.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.user_id == user_id)
            .group_by(Application.status)
        ).all()
        counts = {status: int(count) for status, count in rows}
        week_start = datetime.now(UTC) - timedelta(days=7)
        weekly_count = int(
            self.session.scalar(
                select(func.count(Application.id)).where(
                    Application.user_id == user_id,
                    Application.created_at >= week_start,
                )
            )
            or 0
        )
        pending_interviews = int(
            self.session.scalar(
                select(func.count(Application.id)).where(
                    Application.user_id == user_id,
                    Application.status == ApplicationStatus.INTERVIEW,
                )
            )
            or 0
        )
        return counts, weekly_count, pending_interviews
