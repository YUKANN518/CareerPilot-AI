from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
STANDARD_JOB_FIELDS = frozenset(
    {
        "external_job_id",
        "title",
        "company",
        "location",
        "salary_min",
        "salary_max",
        "currency",
        "employment_type",
        "experience_level",
        "education_requirement",
        "language_requirements",
        "description",
        "responsibilities",
        "requirements",
        "source_url",
        "published_at",
        "status",
    }
)


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _validate_mapping(mapping: dict[str, str], required: set[str]) -> dict[str, str]:
    unsupported = set(mapping) - STANDARD_JOB_FIELDS
    if unsupported:
        raise ValueError(f"unsupported job fields: {', '.join(sorted(unsupported))}")
    missing = required - set(mapping)
    if missing:
        raise ValueError(f"missing required field mappings: {', '.join(sorted(missing))}")
    return mapping




class ManualJobInput(StrictSchema):
    external_job_id: str | None = None
    title: NonEmptyString
    company: NonEmptyString
    location: str | None = None
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    employment_type: str | None = None
    experience_level: str | None = None
    education_requirement: str | None = None
    language_requirements: list[str] = Field(default_factory=list)
    description: NonEmptyString
    responsibilities: str | None = None
    requirements: str | None = None
    source_url: str | None = None
    published_at: datetime | None = None
    status: str = "ACTIVE"



class CsvSourceConfig(StrictSchema):
    csv_content: str = Field(min_length=1, max_length=2_000_000)
    delimiter: str = Field(default=",", min_length=1, max_length=1)
    field_mapping: dict[str, str]

    @field_validator("field_mapping")
    @classmethod
    def validate_field_mapping(cls, value: dict[str, str]) -> dict[str, str]:
        return _validate_mapping(value, {"title", "company", "description"})



class NormalizedJob(StrictSchema):
    source_id: int | None
    external_job_id: str | None = None
    title: NonEmptyString
    company: NonEmptyString
    location: str | None = None
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    employment_type: str | None = None
    experience_level: str | None = None
    education_requirement: str | None = None
    language_requirements: list[str] = Field(default_factory=list)
    description: NonEmptyString
    responsibilities: str | None = None
    requirements: str | None = None
    source_url: str | None = None
    normalized_source_url: str | None = None
    published_at: datetime | None = None
    content_hash: str = Field(min_length=64, max_length=64)
    raw_data: dict[str, JsonValue] = Field(default_factory=dict)
    status: str = "ACTIVE"

    @field_validator("salary_max")
    @classmethod
    def validate_salary_range(cls, value: Decimal | None, info: object) -> Decimal | None:
        data = getattr(info, "data", {})
        salary_min = data.get("salary_min")
        if value is not None and salary_min is not None and value < salary_min:
            raise ValueError("salary_max must be greater than or equal to salary_min")
        return value



class JobRead(StrictSchema):
    id: int
    source_id: int | None
    external_job_id: str | None
    title: str
    company: str
    location: str | None
    salary_min: Decimal | None
    salary_max: Decimal | None
    currency: str | None
    employment_type: str | None
    experience_level: str | None
    education_requirement: str | None
    language_requirements: list[str]
    description: str
    responsibilities: str | None
    requirements: str | None
    source_url: str | None
    published_at: datetime | None
    status: str
    skills: list[str]
    source_name: str
    source_type: str
    source_last_sync_at: datetime | None
    is_favorite: bool
    data_completeness: int = Field(ge=0, le=100)
    # Derived display fields. ``summary`` is a short public abstract derived
    # from ``description``; ``salary_summary`` is a human-readable salary range
    # string; ``fetched_at`` mirrors ``source_last_sync_at`` for display.
    # ``is_summary_only`` is True for JobsDB/OfferToday discovery jobs whose
    # raw JD may sit behind a platform login.
    summary: str | None = None
    salary_summary: str | None = None
    fetched_at: datetime | None = None
    is_summary_only: bool = False
    original_platform_login_may_be_required: bool = False
    # A public snapshot is a compliant, manually verified record.  It is not
    # a claim that the upstream site is being fetched in real time.
    is_public_snapshot: bool = False
    last_verified_at: datetime | None = None
    source_access_limited: bool = False
    created_at: datetime
    updated_at: datetime


class JobListRead(StrictSchema):
    items: list[JobRead]
    total: int
    offset: int
    limit: int
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)


class UserJobInput(StrictSchema):
    external_job_id: str | None = None
    title: NonEmptyString
    company: str | None = None
    location: str | None = None
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    employment_type: str | None = None
    experience_level: str | None = None
    education_requirement: str | None = None
    language_requirements: list[str] = Field(default_factory=list)
    description: str | None = None
    responsibilities: str | None = None
    requirements: str | None = None
    source_url: str | None = None
    published_at: datetime | None = None
    skills: list[NonEmptyString] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def require_description_or_requirements(self) -> "UserJobInput":
        if not ((self.description or "").strip() or (self.requirements or "").strip()):
            raise ValueError("description or requirements is required")
        return self


class UserJobUpdate(StrictSchema):
    """Partial owner-only update for a private job.

    The merged record is normalized and validated by the service, so an
    update cannot leave a private job without its required title and content.
    """

    title: NonEmptyString | None = None
    company: str | None = None
    location: str | None = None
    salary_min: Decimal | None = Field(default=None, ge=0)
    salary_max: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    employment_type: str | None = None
    experience_level: str | None = None
    education_requirement: str | None = None
    language_requirements: list[str] | None = None
    description: str | None = None
    responsibilities: str | None = None
    requirements: str | None = None
    source_url: str | None = None
    published_at: datetime | None = None
    skills: list[NonEmptyString] | None = Field(default=None, max_length=40)


class ManualJobPreview(StrictSchema):
    """Normalized, non-persistent result shown before a user saves a job."""

    title: str
    company: str
    location: str | None
    description: str
    responsibilities: str | None
    requirements: str | None
    source_url: str | None
    employment_type: str | None
    experience_level: str | None
    education_requirement: str | None
    skills: list[str]



class UserJobCsvImport(CsvSourceConfig):
    pass


class JobImportResult(StrictSchema):
    items: list[JobRead]
    imported_count: int
    duplicate_count: int
    failed_count: int
    errors: list[str]


class FavoriteState(StrictSchema):
    job_id: int
    is_favorite: bool
