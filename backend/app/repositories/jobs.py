from datetime import datetime
from typing import Any, cast

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.interfaces import ORMOption
from sqlalchemy.sql.elements import ColumnElement

from app.models.enums import JobSourceType
from app.models.jobs import Job, JobFavorite, JobSkill, JobSource
from app.schemas.jobs import NormalizedJob


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    @staticmethod
    def _visible_filter(user_id: int) -> ColumnElement[bool]:
        return or_(Job.owner_id.is_(None), Job.owner_id == user_id)

    @staticmethod
    def _visibility_filter(user_id: int, visibility: str) -> ColumnElement[bool]:
        if visibility == "PUBLIC":
            return Job.owner_id.is_(None)
        if visibility == "PRIVATE":
            return Job.owner_id == user_id
        return JobRepository._visible_filter(user_id)

    @staticmethod
    def _read_options() -> tuple[ORMOption, ...]:
        return (
            selectinload(Job.source),
            selectinload(Job.skills).selectinload(JobSkill.skill),
        )

    def find_duplicate(self, candidate: NormalizedJob) -> tuple[Job | None, str | None]:
        public_job = Job.owner_id.is_(None)
        if candidate.source_id is not None and candidate.external_job_id:
            job = self.session.scalar(
                select(Job).where(
                    public_job,
                    Job.source_id == candidate.source_id,
                    Job.external_job_id == candidate.external_job_id,
                )
            )
            if job is not None:
                return job, "SOURCE_EXTERNAL_ID"

        if candidate.normalized_source_url:
            job = self.session.scalar(
                select(Job).where(
                    public_job,
                    Job.normalized_source_url == candidate.normalized_source_url,
                )
            )
            if job is not None:
                return job, "SOURCE_URL"

        job = self.session.scalar(
            select(Job).where(public_job, Job.content_hash == candidate.content_hash)
        )
        if job is not None:
            return job, "CONTENT_HASH"

        job = self.session.scalar(
            select(Job).where(
                public_job,
                func.lower(Job.title) == candidate.title.casefold(),
                func.lower(Job.company) == candidate.company.casefold(),
                func.lower(func.coalesce(Job.location, ""))
                == (candidate.location or "").casefold(),
            )
        )
        if job is not None:
            return job, "TITLE_COMPANY_LOCATION"
        return None, None

    def find_import_duplicate(
        self,
        candidate: NormalizedJob,
        user_id: int,
    ) -> Job | None:
        visibility = self._visible_filter(user_id)
        if candidate.normalized_source_url:
            job = self.session.scalar(
                select(Job)
                .where(
                    visibility,
                    Job.normalized_source_url == candidate.normalized_source_url,
                )
                .options(*self._read_options())
            )
            if job is not None:
                return job
        job = self.session.scalar(
            select(Job)
            .where(visibility, Job.content_hash == candidate.content_hash)
            .options(*self._read_options())
        )
        if job is not None:
            return job
        return self.session.scalar(
            select(Job)
            .where(
                visibility,
                func.lower(Job.title) == candidate.title.casefold(),
                func.lower(Job.company) == candidate.company.casefold(),
                func.lower(func.coalesce(Job.location, ""))
                == (candidate.location or "").casefold(),
            )
            .options(*self._read_options())
        )

    def _filtered_statement(
        self,
        *,
        user_id: int,
        search: str | None,
        location: str | None,
        company: str | None,
        employment_type: str | None,
        experience_level: str | None,
        source_id: int | None,
        source_name: str | None,
        source_type: JobSourceType | None,
        published_after: datetime | None,
        status: str,
        visibility: str,
        information_type: str | None = None,
    ) -> Select[tuple[Job]]:
        statement = (
            select(Job)
            .outerjoin(Job.source)
            .where(
                self._visibility_filter(user_id, visibility),
                Job.status == status,
            )
        )
        if search:
            pattern = f"%{search.strip()}%"
            statement = statement.where(
                or_(
                    Job.title.ilike(pattern),
                    Job.company.ilike(pattern),
                    Job.description.ilike(pattern),
                )
            )
        if location:
            statement = statement.where(Job.location.ilike(f"%{location.strip()}%"))
        if company:
            statement = statement.where(Job.company.ilike(f"%{company.strip()}%"))
        if employment_type:
            statement = statement.where(Job.employment_type == employment_type)
        if experience_level:
            statement = statement.where(Job.experience_level == experience_level)
        if source_id is not None:
            statement = statement.where(Job.source_id == source_id)
        if source_name:
            statement = statement.where(JobSource.name.ilike(f"%{source_name.strip()}%"))
        if source_type is not None:
            statement = statement.where(JobSource.source_type == source_type)
        if published_after is not None:
            statement = statement.where(Job.published_at >= published_after)
        if information_type == "SUMMARY":
            statement = statement.where(
                or_(
                    JobSource.name.ilike("%jobsdb%"),
                    JobSource.name.ilike("%offertoday%"),
                )
            )
        return statement

    def list_jobs(
        self,
        *,
        user_id: int,
        search: str | None,
        location: str | None,
        company: str | None,
        employment_type: str | None,
        experience_level: str | None,
        source_id: int | None,
        source_name: str | None,
        source_type: JobSourceType | None,
        published_after: datetime | None,
        status: str,
        sort: str,
        offset: int,
        limit: int,
        visibility: str,
        information_type: str | None = None,
    ) -> tuple[list[Job], int]:
        statement = self._filtered_statement(
            user_id=user_id,
            search=search,
            location=location,
            company=company,
            employment_type=employment_type,
            experience_level=experience_level,
            source_id=source_id,
            source_name=source_name,
            source_type=source_type,
            published_after=published_after,
            status=status,
            visibility=visibility,
            information_type=information_type,
        )
        total = int(
            self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        )
        order_by = cast(
            tuple[ColumnElement[Any], ...],
            {
                "published_asc": (
                    Job.published_at.asc().nullslast(),
                    Job.created_at.asc(),
                ),
                "salary_desc": (
                    func.coalesce(Job.salary_max, Job.salary_min, 0).desc(),
                    Job.created_at.desc(),
                ),
                "title_asc": (Job.title.asc(), Job.company.asc()),
                "created_desc": (Job.created_at.desc(),),
            }.get(
                sort,
                (Job.published_at.desc().nullslast(), Job.created_at.desc()),
            ),
        )
        statement = (
            statement.options(*self._read_options()).order_by(*order_by).offset(offset).limit(limit)
        )
        return list(self.session.scalars(statement).all()), total

    def list_favorites(
        self,
        *,
        user_id: int,
        offset: int,
        limit: int,
    ) -> tuple[list[Job], int]:
        visibility = self._visible_filter(user_id)
        base = (
            select(Job)
            .join(JobFavorite)
            .where(JobFavorite.user_id == user_id, visibility, Job.status == "ACTIVE")
        )
        total = int(self.session.scalar(select(func.count()).select_from(base.subquery())) or 0)
        statement = (
            base.options(*self._read_options())
            .order_by(JobFavorite.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(self.session.scalars(statement).all()), total

    def get_visible_job(self, job_id: int, user_id: int) -> Job | None:
        return self.session.scalar(
            select(Job)
            .where(Job.id == job_id, self._visible_filter(user_id))
            .options(*self._read_options())
        )

    def favorite_ids(self, user_id: int, job_ids: list[int]) -> set[int]:
        if not job_ids:
            return set()
        return set(
            self.session.scalars(
                select(JobFavorite.job_id).where(
                    JobFavorite.user_id == user_id,
                    JobFavorite.job_id.in_(job_ids),
                )
            ).all()
        )

    def get_favorite(self, user_id: int, job_id: int) -> JobFavorite | None:
        return self.session.scalar(
            select(JobFavorite).where(
                JobFavorite.user_id == user_id,
                JobFavorite.job_id == job_id,
            )
        )
