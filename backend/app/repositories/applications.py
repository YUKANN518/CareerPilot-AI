from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.interfaces import ORMOption

from app.models.applications import Application
from app.models.enums import ApplicationStatus
from app.models.jobs import Job, JobSkill


class ApplicationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _options() -> tuple[ORMOption, ...]:
        return (
            selectinload(Application.job).selectinload(Job.source),
            selectinload(Application.job).selectinload(Job.skills).selectinload(JobSkill.skill),
            selectinload(Application.status_history),
        )

    def get(self, user_id: int, application_id: int) -> Application | None:
        return self.session.scalar(
            select(Application)
            .where(Application.id == application_id, Application.user_id == user_id)
            .options(*self._options())
        )

    def get_for_job(self, user_id: int, job_id: int) -> Application | None:
        return self.session.scalar(
            select(Application)
            .where(Application.user_id == user_id, Application.job_id == job_id)
            .options(*self._options())
        )

    def list(
        self,
        user_id: int,
        status: ApplicationStatus | None = None,
    ) -> list[Application]:
        statement = select(Application).where(Application.user_id == user_id)
        if status is not None:
            statement = statement.where(Application.status == status)
        statement = statement.options(*self._options()).order_by(Application.updated_at.desc())
        return list(self.session.scalars(statement).all())

    def status_counts(self, user_id: int) -> dict[ApplicationStatus, int]:
        rows = self.session.execute(
            select(Application.status, func.count(Application.id))
            .where(Application.user_id == user_id)
            .group_by(Application.status)
        ).all()
        return {status: int(count) for status, count in rows}
