from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MatchRunStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    WAITING_REVIEW = "WAITING_REVIEW"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MatchNodeStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    WAITING_REVIEW = "WAITING_REVIEW"
    CANCELLED = "CANCELLED"


class MatchRunCreate(StrictSchema):
    resume_version_id: int = Field(ge=1)
    job_id: int = Field(ge=1)
    scoring_version: str = Field(
        default="deterministic-v1.1",
        pattern=r"^(deterministic-v1\.1|hybrid-v1)$",
    )


class MatchRunStepRead(StrictSchema):
    node_name: str
    status: MatchNodeStatus
    retry_count: int
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    summary: dict[str, JsonValue]
    error_message: str | None


class MatchRunRead(StrictSchema):
    run_id: int
    user_id: int
    resume_version_id: int
    job_id: int
    scoring_version: str
    status: MatchRunStatus
    current_node: str | None
    node_status: MatchNodeStatus
    completed_nodes: list[str]
    rule_score: float | None
    semantic_score: float | None
    hybrid_score: float | None
    blocking_risks: list[dict[str, JsonValue]]
    report_id: int | None
    error_code: str | None
    error_message: str | None
    waiting_for_user: bool
    retry_count: int
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    steps: list[MatchRunStepRead]


class MatchRunEvent(StrictSchema):
    id: int
    event: str
    run_id: int
    node: str | None = None
    status: str
    timestamp: datetime
    duration_ms: int | None = None
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    report_id: int | None = None


class MatchRunActionResult(StrictSchema):
    run: MatchRunRead


class MatchRunListRead(StrictSchema):
    items: list[MatchRunRead]
    total: int
    offset: int
    limit: int


class MatchRunEventTicket(StrictSchema):
    ticket: str
    expires_at: datetime
