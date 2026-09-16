from datetime import datetime

from pydantic import ConfigDict, Field

from app.models.enums import ApplicationStatus
from app.schemas.matching import StrictSchema


class ApplicationCreate(StrictSchema):
    job_id: int = Field(ge=1)
    status: ApplicationStatus = ApplicationStatus.SAVED
    notes: str | None = Field(default=None, max_length=10_000)
    next_action_at: datetime | None = None


class ApplicationUpdate(StrictSchema):
    notes: str | None = Field(default=None, max_length=10_000)
    next_action_at: datetime | None = None


class ApplicationStatusUpdate(StrictSchema):
    status: ApplicationStatus
    note: str | None = Field(default=None, max_length=500)
    next_action_at: datetime | None = None


class ApplicationJobRead(StrictSchema):
    id: int
    title: str
    company: str
    location: str | None
    source_url: str | None
    employment_type: str | None
    source_name: str
    is_favorite: bool


class ApplicationStatusHistoryRead(StrictSchema):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: int
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    note: str | None
    created_at: datetime


class ApplicationRead(StrictSchema):
    id: int
    user_id: int
    job_id: int
    status: ApplicationStatus
    notes: str | None
    next_action_at: datetime | None
    job: ApplicationJobRead
    status_history: list[ApplicationStatusHistoryRead]
    created_at: datetime
    updated_at: datetime


class ApplicationBoardRead(StrictSchema):
    columns: dict[ApplicationStatus, list[ApplicationRead]]
    counts: dict[ApplicationStatus, int]
