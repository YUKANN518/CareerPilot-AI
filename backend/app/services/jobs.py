import csv
from datetime import datetime
from io import StringIO
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AppError
from app.job_sources.normalization import normalize_job_record
from app.job_sources.source_names import (
    canonical_source_name,
    is_discovery_platform,
)
from app.job_sources.types import SourceAdapterError
from app.models.enums import JobSourceType
from app.models.jobs import Job, JobFavorite, JobSkill
from app.models.resumes import Skill
from app.models.users import User
from app.repositories.jobs import JobRepository
from app.schemas.jobs import (
    JobImportResult,
    JobListRead,
    JobRead,
    ManualJobPreview,
    NormalizedJob,
    UserJobCsvImport,
    UserJobInput,
    UserJobUpdate,
)
from app.semantic.embeddings import embedding_provider_from_settings
from app.semantic.index import SemanticIndexService


class JobService:
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        semantic_index: SemanticIndexService | None = None,
    ) -> None:
        self.session = session
        self.repository = JobRepository(session)
        self.settings = settings
        self.semantic_index = semantic_index

    def list_jobs(
        self,
        *,
        user: User,
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
        information_type: str | None = None,
        visibility: str = "ALL",
    ) -> JobListRead:
        jobs, total = self.repository.list_jobs(
            user_id=user.id,
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
            sort=sort,
            offset=offset,
            limit=limit,
            information_type=information_type,
            visibility=visibility,
        )
        favorite_ids = self.repository.favorite_ids(user.id, [job.id for job in jobs])
        return JobListRead(
            items=[self._job_read(job, is_favorite=job.id in favorite_ids) for job in jobs],
            total=total,
            offset=offset,
            limit=limit,
            page=(offset // limit) + 1,
            page_size=limit,
            total_pages=(total + limit - 1) // limit,
        )

    def list_favorites(self, user: User, offset: int, limit: int) -> JobListRead:
        jobs, total = self.repository.list_favorites(
            user_id=user.id,
            offset=offset,
            limit=limit,
        )
        return JobListRead(
            items=[self._job_read(job, is_favorite=True) for job in jobs],
            total=total,
            offset=offset,
            limit=limit,
            page=(offset // limit) + 1,
            page_size=limit,
            total_pages=(total + limit - 1) // limit,
        )

    def get_job(self, user: User, job_id: int) -> JobRead:
        job = self._get_visible_job(user, job_id)
        favorite = self.repository.get_favorite(user.id, job.id) is not None
        return self._job_read(job, is_favorite=favorite)

    def favorite(self, user: User, job_id: int) -> None:
        job = self._get_visible_job(user, job_id)
        if self.repository.get_favorite(user.id, job.id) is None:
            self.session.add(JobFavorite(user_id=user.id, job_id=job.id))
            self.session.commit()

    def unfavorite(self, user: User, job_id: int) -> None:
        self._get_visible_job(user, job_id)
        favorite = self.repository.get_favorite(user.id, job_id)
        if favorite is not None:
            self.session.delete(favorite)
            self.session.commit()

    def delete_private_job(self, user: User, job_id: int) -> None:
        job = self._get_visible_job(user, job_id)
        if job.owner_id != user.id:
            raise AppError(
                "PRIVATE_JOB_DELETE_FORBIDDEN",
                "Only the owner can delete a privately imported job",
                403,
            )
        try:
            self.session.delete(job)
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise AppError(
                "JOB_HAS_HISTORY",
                "A job with matching or application history cannot be deleted",
                409,
            ) from exc
        index = self.semantic_index
        if (
            index is None
            and self.settings is not None
            and Path(self.settings.faiss_index_dir).exists()
        ):
            index = SemanticIndexService(
                self.settings,
                embedding_provider_from_settings(self.settings),
            )
        if index is not None:
            index.delete_job_index(job)

    def preview_manual(self, user: User, payload: UserJobInput) -> ManualJobPreview:
        """Normalize user-provided text without persisting or inventing fields."""
        candidate = self._normalize_user_job(payload)
        return ManualJobPreview(
            title=candidate.title,
            company=candidate.company,
            location=candidate.location,
            description=candidate.description,
            responsibilities=candidate.responsibilities,
            requirements=candidate.requirements,
            source_url=candidate.source_url,
            employment_type=candidate.employment_type,
            experience_level=candidate.experience_level,
            education_requirement=candidate.education_requirement,
            skills=payload.skills,
        )

    def import_manual(self, user: User, payload: UserJobInput) -> JobImportResult:
        candidate = self._normalize_user_job(payload)
        job, duplicate = self._import_candidate(
            user,
            candidate,
            "USER_MANUAL",
            payload.skills,
        )
        self.session.commit()
        return JobImportResult(
            items=[self._job_read(job, is_favorite=False)],
            imported_count=0 if duplicate else 1,
            duplicate_count=1 if duplicate else 0,
            failed_count=0,
            errors=[],
        )

    def update_private_job(
        self,
        user: User,
        job_id: int,
        payload: UserJobUpdate,
    ) -> JobRead:
        job = self._get_visible_job(user, job_id)
        if job.owner_id != user.id:
            raise AppError(
                "PRIVATE_JOB_UPDATE_FORBIDDEN",
                "Only the owner can update a privately imported job",
                403,
            )
        changes = payload.model_dump(exclude_unset=True, mode="python")
        raw: dict[str, object] = {
            "external_job_id": job.external_job_id,
            "title": job.title,
            "company": None if job.company == "未提供" else job.company,
            "location": job.location,
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "currency": job.currency,
            "employment_type": job.employment_type,
            "experience_level": job.experience_level,
            "education_requirement": job.education_requirement,
            "language_requirements": job.language_requirements,
            "description": job.description,
            "responsibilities": job.responsibilities,
            "requirements": job.requirements,
            "source_url": job.source_url,
            "published_at": job.published_at,
            "status": job.status,
        }
        skills = changes.pop("skills", None)
        raw.update(changes)
        try:
            candidate = normalize_job_record(
                None,
                self._user_job_raw(raw),
            )
        except (SourceAdapterError, ValidationError, ValueError) as exc:
            raise AppError(
                "JOB_IMPORT_INVALID",
                "A private job needs a title and either a description or requirements",
                422,
            ) from exc
        self._update_private_job_fields(job, candidate)
        if skills is not None:
            job.skills.clear()
            self._attach_skills(job, skills)
        self.session.commit()
        is_favorite = self.repository.get_favorite(user.id, job.id) is not None
        return self._job_read(job, is_favorite=is_favorite)

    def _normalize_user_job(self, payload: UserJobInput) -> NormalizedJob:
        raw = payload.model_dump(
            mode="python",
            exclude_none=True,
            exclude={"skills"},
        )
        try:
            return normalize_job_record(None, self._user_job_raw(raw))
        except (SourceAdapterError, ValidationError, ValueError) as exc:
            raise AppError(
                "JOB_IMPORT_INVALID",
                "A private job needs a title and either a description or requirements",
                422,
            ) from exc

    @staticmethod
    def _user_job_raw(raw: dict[str, object]) -> dict[str, object]:
        """Adapt optional user fields to the existing normalized-job contract.

        The placeholder is a display value only; it deliberately makes no
        assertion about an employer when the user did not provide one.
        """
        company = str(raw.get("company") or "").strip() or "未提供"
        description = str(raw.get("description") or "").strip()
        requirements = str(raw.get("requirements") or "").strip()
        if not description:
            description = requirements
        normalized_raw = dict(raw)
        normalized_raw["company"] = company
        normalized_raw["description"] = description
        normalized_raw["requirements"] = requirements or None
        return normalized_raw

    def import_csv(self, user: User, payload: UserJobCsvImport) -> JobImportResult:
        reader = csv.DictReader(StringIO(payload.csv_content), delimiter=payload.delimiter)
        headers = set(reader.fieldnames or [])
        missing = set(payload.field_mapping.values()) - headers
        if missing:
            raise AppError(
                "CSV_COLUMNS_MISSING",
                f"CSV columns are missing: {', '.join(sorted(missing))}",
                422,
            )

        jobs: list[Job] = []
        imported_count = 0
        duplicate_count = 0
        errors: list[str] = []
        for index, row in enumerate(reader):
            if index >= 500:
                errors.append("Only the first 500 CSV rows were processed")
                break
            raw = {target: row.get(column) for target, column in payload.field_mapping.items()}
            try:
                candidate = normalize_job_record(None, raw)
                job, duplicate = self._import_candidate(
                    user,
                    candidate,
                    "USER_CSV",
                    [],
                )
            except (SourceAdapterError, ValidationError, ValueError) as exc:
                errors.append(f"row {index + 2}: {type(exc).__name__}")
                continue
            jobs.append(job)
            if duplicate:
                duplicate_count += 1
            else:
                imported_count += 1
        self.session.commit()
        return JobImportResult(
            items=[self._job_read(job, is_favorite=False) for job in jobs],
            imported_count=imported_count,
            duplicate_count=duplicate_count,
            failed_count=len(errors),
            errors=errors,
        )


    def _import_candidate(
        self,
        user: User,
        candidate: NormalizedJob,
        import_method: str,
        skills: list[str],
    ) -> tuple[Job, bool]:
        duplicate = self.repository.find_import_duplicate(candidate, user.id)
        if duplicate is not None:
            return duplicate, True
        job = Job(
            **candidate.model_dump(mode="python"),
            owner_id=user.id,
            import_method=import_method,
        )
        self._attach_skills(job, skills)
        self.session.add(job)
        self.session.flush()
        return job, False

    def _attach_skills(self, job: Job, skills: list[str]) -> None:
        for skill_name in dict.fromkeys(name.strip() for name in skills if name.strip()):
            skill = self.session.scalar(
                select(Skill).where(func.lower(Skill.name) == skill_name.casefold())
            )
            if skill is None:
                skill = Skill(name=skill_name, category="JOB")
            job.skills.append(
                JobSkill(
                    skill=skill,
                    is_required=False,
                    weight=1,
                    evidence_text=None,
                )
            )

    @staticmethod
    def _update_private_job_fields(job: Job, candidate: NormalizedJob) -> None:
        for field_name, value in candidate.model_dump(
            mode="python",
            exclude={"source_id"},
        ).items():
            setattr(job, field_name, value)

    def _get_visible_job(self, user: User, job_id: int) -> Job:
        job = self.repository.get_visible_job(job_id, user.id)
        if job is None:
            raise AppError("JOB_NOT_FOUND", "Job was not found", 404)
        return job

    def _job_read(self, job: Job, *, is_favorite: bool) -> JobRead:
        if job.source is not None:
            source_name = job.source.name
            source_type = job.source.source_type.value
        elif job.owner_id is not None:
            source_name = "我的导入"
            source_type = job.import_method or "USER_IMPORT"
        else:
            source_name = "已删除的数据源"
            source_type = "SOURCE_DELETED"
        source_last_sync_at = (
            job.source.last_sync_at
            if job.source is not None and job.source.last_sync_at is not None
            else job.updated_at
        )
        completeness_values = (
            job.title,
            job.company,
            job.location,
            job.description,
            job.requirements,
            job.responsibilities,
            job.employment_type,
            job.experience_level,
            job.education_requirement,
            job.published_at,
            job.source_url,
            job.salary_min or job.salary_max,
        )
        present = sum(
            value is not None and value != "" and value != [] for value in completeness_values
        )
        canonical_name = canonical_source_name(source_name) or source_name
        is_summary_only = is_discovery_platform(source_name)
        last_verified_at = job.source.last_sync_at if job.source is not None else None
        return JobRead(
            id=job.id,
            source_id=job.source_id,
            external_job_id=job.external_job_id,
            title=job.title,
            company=job.company,
            location=job.location,
            salary_min=job.salary_min,
            salary_max=job.salary_max,
            currency=job.currency,
            employment_type=job.employment_type,
            experience_level=job.experience_level,
            education_requirement=job.education_requirement,
            language_requirements=job.language_requirements,
            description=job.description,
            responsibilities=job.responsibilities,
            requirements=job.requirements,
            source_url=job.source_url,
            published_at=job.published_at,
            status=job.status,
            skills=sorted({item.skill.name for item in job.skills}),
            source_name=canonical_name,
            source_type=source_type,
            source_last_sync_at=source_last_sync_at,
            is_favorite=is_favorite,
            data_completeness=round(present / len(completeness_values) * 100),
            summary=_build_summary(job.description),
            salary_summary=_build_salary_summary(job),
            fetched_at=source_last_sync_at,
            is_summary_only=is_summary_only,
            original_platform_login_may_be_required=is_summary_only,
            is_public_snapshot=is_summary_only and job.owner_id is None,
            last_verified_at=last_verified_at,
            source_access_limited=is_summary_only,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


def _build_summary(description: str, *, limit: int = 220) -> str:
    """Return a compact, whitespace-normalized job description preview."""
    normalized = " ".join(description.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def _build_salary_summary(job: Job) -> str | None:
    """Format the stored salary range without inventing missing values."""
    if job.salary_min is None and job.salary_max is None:
        return None
    currency = f" {job.currency}" if job.currency else ""
    if job.salary_min is not None and job.salary_max is not None:
        return f"{job.salary_min:,.0f}-{job.salary_max:,.0f}{currency}"
    value = job.salary_min if job.salary_min is not None else job.salary_max
    return f"{value:,.0f}{currency}" if value is not None else None
