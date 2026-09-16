from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.models.applications import Application, ApplicationStatusHistory
from app.models.enums import ApplicationStatus
from app.models.operations import AuditLog
from app.models.users import User
from app.repositories.applications import ApplicationRepository
from app.repositories.jobs import JobRepository
from app.schemas.applications import (
    ApplicationBoardRead,
    ApplicationCreate,
    ApplicationJobRead,
    ApplicationRead,
    ApplicationStatusHistoryRead,
    ApplicationStatusUpdate,
    ApplicationUpdate,
)

APPLICATION_COLUMNS = (
    ApplicationStatus.SAVED,
    ApplicationStatus.APPLIED,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.OFFER,
    ApplicationStatus.REJECTED,
)

ALLOWED_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.SAVED: frozenset({ApplicationStatus.APPLIED, ApplicationStatus.REJECTED}),
    ApplicationStatus.APPLIED: frozenset(
        {
            ApplicationStatus.SAVED,
            ApplicationStatus.INTERVIEW,
            ApplicationStatus.OFFER,
            ApplicationStatus.REJECTED,
        }
    ),
    ApplicationStatus.INTERVIEW: frozenset(
        {
            ApplicationStatus.APPLIED,
            ApplicationStatus.OFFER,
            ApplicationStatus.REJECTED,
        }
    ),
    ApplicationStatus.OFFER: frozenset({ApplicationStatus.INTERVIEW, ApplicationStatus.REJECTED}),
    ApplicationStatus.REJECTED: frozenset({ApplicationStatus.SAVED, ApplicationStatus.APPLIED}),
}


class ApplicationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.applications = ApplicationRepository(session)
        self.jobs = JobRepository(session)

    def create(self, actor: User, payload: ApplicationCreate) -> ApplicationRead:
        job = self.jobs.get_visible_job(payload.job_id, actor.id)
        if job is None:
            raise AppError("JOB_NOT_FOUND", "岗位不存在或无权访问", 404)
        existing = self.applications.get_for_job(actor.id, job.id)
        if existing is not None:
            raise AppError("APPLICATION_EXISTS", "该岗位已加入投递管理", 409)
        if payload.status != ApplicationStatus.SAVED:
            raise AppError(
                "APPLICATION_INITIAL_STATUS_INVALID",
                "新投递记录必须从收藏开始",
                422,
            )

        application = Application(
            user_id=actor.id,
            job_id=job.id,
            status=payload.status,
            notes=payload.notes,
            next_action_at=payload.next_action_at,
        )
        application.status_history.append(
            ApplicationStatusHistory(
                from_status=None,
                to_status=payload.status,
                note="加入投递管理",
            )
        )
        self.session.add(application)
        self.session.flush()
        self._audit(actor, "APPLICATION_CREATED", application, {"status": payload.status.value})
        self.session.commit()
        created = self.applications.get(actor.id, application.id)
        assert created is not None
        return self._read(created, actor.id)

    def list(self, actor: User, status: ApplicationStatus | None = None) -> list[ApplicationRead]:
        return [self._read(item, actor.id) for item in self.applications.list(actor.id, status)]

    def get(self, actor: User, application_id: int) -> ApplicationRead:
        return self._read(self._get(actor, application_id), actor.id)

    def board(self, actor: User) -> ApplicationBoardRead:
        grouped: dict[ApplicationStatus, list[ApplicationRead]] = {
            status: [] for status in APPLICATION_COLUMNS
        }
        for item in self.applications.list(actor.id):
            grouped[item.status].append(self._read(item, actor.id))
        counts = {status: len(grouped[status]) for status in APPLICATION_COLUMNS}
        return ApplicationBoardRead(columns=grouped, counts=counts)

    def update(
        self,
        actor: User,
        application_id: int,
        payload: ApplicationUpdate,
    ) -> ApplicationRead:
        application = self._get(actor, application_id)
        if "notes" in payload.model_fields_set:
            application.notes = payload.notes
        if "next_action_at" in payload.model_fields_set:
            application.next_action_at = payload.next_action_at
        self._audit(actor, "APPLICATION_UPDATED", application, {})
        self.session.commit()
        refreshed = self._get(actor, application_id)
        return self._read(refreshed, actor.id)

    def change_status(
        self,
        actor: User,
        application_id: int,
        payload: ApplicationStatusUpdate,
    ) -> ApplicationRead:
        application = self._get(actor, application_id)
        current = application.status
        if payload.status == current:
            raise AppError("APPLICATION_STATUS_UNCHANGED", "投递状态未发生变化", 409)
        if payload.status not in ALLOWED_TRANSITIONS[current]:
            raise AppError("APPLICATION_STATUS_TRANSITION_INVALID", "不允许执行该投递状态转换", 409)

        application.status = payload.status
        if payload.next_action_at is not None:
            application.next_action_at = payload.next_action_at
        application.status_history.append(
            ApplicationStatusHistory(
                from_status=current,
                to_status=payload.status,
                note=payload.note,
            )
        )
        self._audit(
            actor,
            "APPLICATION_STATUS_CHANGED",
            application,
            {"from": current.value, "to": payload.status.value},
        )
        self.session.commit()
        refreshed = self._get(actor, application_id)
        return self._read(refreshed, actor.id)

    def delete(self, actor: User, application_id: int) -> None:
        application = self._get(actor, application_id)
        self._audit(actor, "APPLICATION_DELETED", application, {})
        self.session.delete(application)
        self.session.commit()

    def _get(self, actor: User, application_id: int) -> Application:
        application = self.applications.get(actor.id, application_id)
        if application is None:
            raise AppError("APPLICATION_NOT_FOUND", "投递记录不存在或无权访问", 404)
        return application

    def _audit(
        self,
        actor: User,
        action: str,
        application: Application,
        details: dict[str, str],
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=actor.id,
                action=action,
                resource_type="application",
                resource_id=str(application.id) if application.id is not None else None,
                details={"job_id": application.job_id, **details},
            )
        )

    @staticmethod
    def _read(application: Application, user_id: int) -> ApplicationRead:
        job = application.job
        source = job.source
        return ApplicationRead(
            id=application.id,
            user_id=application.user_id,
            job_id=application.job_id,
            status=application.status,
            notes=application.notes,
            next_action_at=application.next_action_at,
            job=ApplicationJobRead(
                id=job.id,
                title=job.title,
                company=job.company,
                location=job.location,
                source_url=job.source_url,
                employment_type=job.employment_type,
                source_name=source.name if source is not None else "用户导入",
                is_favorite=False,
            ),
            status_history=[
                ApplicationStatusHistoryRead.model_validate(item)
                for item in application.status_history
            ],
            created_at=application.created_at,
            updated_at=application.updated_at,
        )
