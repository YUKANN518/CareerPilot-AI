"""Schemas for the resume optimization feature (Stage 3).

The contracts here govern the data sent to and received from the Dify
"CareerPilot 简历定向优化" workflow. They are intentionally strict
(``extra="forbid"``) so fabrication attempts from the LLM surface as
Pydantic validation errors instead of silently producing fake resume
content.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResumeOptimizationStatus(StrEnum):
    DRAFT = "DRAFT"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


class SectionChangeType(StrEnum):
    REWRITE = "REWRITE"
    REORDER = "REORDER"
    SHORTEN = "SHORTEN"
    EMPHASIZE = "EMPHASIZE"
    NO_CHANGE = "NO_CHANGE"


# ---------------------------------------------------------------------------
# Workflow input contract
# ---------------------------------------------------------------------------


class ResumeOptimizationResumeInput(StrictSchema):
    resume_version_id: int = Field(ge=1)
    summary: str = Field(default="", max_length=4000)
    education: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=20)
    experiences: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=40)
    projects: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=40)
    skills: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=80)
    evidence: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=120)


class ResumeOptimizationJobInput(StrictSchema):
    job_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    company: str = Field(min_length=1, max_length=240)
    summary: str = Field(default="", max_length=8000)
    source_name: str = Field(default="", max_length=120)
    source_url: str | None = Field(default=None, max_length=1000)
    information_completeness: float = Field(default=0.0, ge=0, le=1)
    is_summary_only: bool = False


class ResumeOptimizationMatchReportInput(StrictSchema):
    report_id: int = Field(ge=1)
    final_score: float | None = Field(default=None, ge=0, le=100)
    matched_skills: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=80)
    partial_skills: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=80)
    missing_skills: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=80)
    blocking_risks: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=40)
    evidence: list[dict[str, JsonValue]] = Field(default_factory=list, max_length=120)


class ResumeOptimizationWorkflowInput(StrictSchema):
    """Payload sent to the Dify resume optimization workflow."""

    schema_version: str = "resume-optimization-input-v1"
    user_locale: str = "zh-CN"
    resume: ResumeOptimizationResumeInput
    job: ResumeOptimizationJobInput
    match_report: ResumeOptimizationMatchReportInput

    @model_validator(mode="after")
    def validate_schema_version(self) -> ResumeOptimizationWorkflowInput:
        if self.schema_version != "resume-optimization-input-v1":
            raise ValueError("schema_version must be resume-optimization-input-v1")
        return self


# ---------------------------------------------------------------------------
# Workflow output contract
# ---------------------------------------------------------------------------


class ResumeOptimizationSectionOutput(StrictSchema):
    section: str = Field(min_length=1, max_length=120)
    source_section_id: str = Field(min_length=1, max_length=160)
    original_text: str = Field(default="", max_length=8000)
    suggested_text: str = Field(default="", max_length=8000)
    reason: str = Field(default="", max_length=2000)
    related_job_requirement: str = Field(default="", max_length=2000)
    evidence_keys: list[str] = Field(default_factory=list, max_length=40)
    change_type: SectionChangeType = SectionChangeType.NO_CHANGE

    @model_validator(mode="after")
    def validate_evidence_keys(self) -> ResumeOptimizationSectionOutput:
        for key in self.evidence_keys:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("evidence_keys items must be non-empty strings")
        return self


class ResumeOptimizationKeywordSuggestion(StrictSchema):
    keyword: str = Field(min_length=1, max_length=120)
    reason: str = Field(default="", max_length=2000)
    evidence_keys: list[str] = Field(default_factory=list, max_length=40)


class ResumeOptimizationGeneration(StrictSchema):
    workflow_version: str = Field(min_length=1, max_length=120)
    workflow_run_id: str | None = Field(default=None, max_length=160)
    provider: str = Field(default="dify", max_length=80)
    latency_ms: int | None = Field(default=None, ge=0)


class ResumeOptimizationWorkflowOutput(StrictSchema):
    """Strict output contract returned by the Dify workflow."""

    schema_version: str = "resume-optimization-v1"
    summary: str = Field(default="", max_length=4000)
    sections: list[ResumeOptimizationSectionOutput] = Field(default_factory=list, max_length=60)
    keyword_suggestions: list[ResumeOptimizationKeywordSuggestion] = Field(
        default_factory=list, max_length=60
    )
    missing_evidence_warnings: list[str] = Field(default_factory=list, max_length=40)
    fabrication_warnings: list[str] = Field(default_factory=list, max_length=40)
    job_information_warning: str = Field(default="", max_length=2000)
    generation: ResumeOptimizationGeneration

    @model_validator(mode="after")
    def validate_schema_version(self) -> ResumeOptimizationWorkflowOutput:
        if self.schema_version != "resume-optimization-v1":
            raise ValueError("schema_version must be resume-optimization-v1")
        return self


# ---------------------------------------------------------------------------
# Provider result
# ---------------------------------------------------------------------------


class ResumeOptimizationProviderAttempt(StrictSchema):
    """Masked metadata for one Dify workflow attempt inside the provider."""

    sequence: int = Field(ge=1)
    http_status: int | None = Field(default=None)
    workflow_run_id: str | None = Field(default=None, max_length=160)
    workflow_id: str | None = Field(default=None, max_length=160)
    status: str | None = Field(default=None, max_length=40)
    error: str | None = Field(default=None, max_length=240)
    total_steps: int | None = Field(default=None, ge=0)
    elapsed_time: float | None = Field(default=None, ge=0)
    outputs_keys: list[str] = Field(default_factory=list)
    error_code: str | None = Field(default=None, max_length=80)
    error_message: str | None = Field(default=None, max_length=240)
    latency_ms: int = Field(default=0, ge=0)
    retried: bool = False


class ResumeOptimizationProviderResult(StrictSchema):
    output: ResumeOptimizationWorkflowOutput
    raw_output: dict[str, JsonValue] = Field(default_factory=dict)
    attempts: list[ResumeOptimizationProviderAttempt] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# API schemas
# ---------------------------------------------------------------------------


class ResumeOptimizationCreate(StrictSchema):
    resume_version_id: int = Field(ge=1)
    job_id: int = Field(ge=1)
    match_report_id: int = Field(ge=1)


class ResumeOptimizationSectionRead(StrictSchema):
    section: str
    source_section_id: str
    original_text: str
    suggested_text: str
    reason: str
    related_job_requirement: str
    evidence_keys: list[str] = Field(default_factory=list)
    change_type: SectionChangeType
    # User-side state for accept / reject / edit
    accepted: bool = False
    edited_text: str | None = None


class ResumeOptimizationKeywordSuggestionRead(StrictSchema):
    keyword: str
    reason: str
    evidence_keys: list[str] = Field(default_factory=list)


class ResumeOptimizationRead(StrictSchema):
    id: int
    user_id: int
    resume_version_id: int
    job_id: int
    match_report_id: int
    status: ResumeOptimizationStatus
    summary: str
    sections: list[ResumeOptimizationSectionRead]
    keyword_suggestions: list[ResumeOptimizationKeywordSuggestionRead]
    missing_evidence_warnings: list[str] = Field(default_factory=list)
    fabrication_warnings: list[str] = Field(default_factory=list)
    job_information_warning: str = ""
    is_human_confirmed: bool
    workflow_run_id: str | None = None
    workflow_version: str | None = None
    provider: str | None = None
    latency_ms: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ResumeOptimizationListRead(StrictSchema):
    items: list[ResumeOptimizationRead]
    total: int
    offset: int
    limit: int


class ResumeOptimizationConfirmPayload(StrictSchema):
    """User-side confirmation of which section suggestions to accept."""

    sections: list[ResumeOptimizationSectionConfirm] = Field(default_factory=list)
    # 真实性声明:当用户提交任何 ``edited_text`` 时，必须显式勾选确认
    # 手动编辑内容真实准确、可在需要时提供证明。服务端在任何章节携带
    # ``edited_text`` 但本字段为 ``False`` 时拒绝确认。本字段不替代
    # missing-skill、数字事实或 evidence-key 服务端校验，仅覆盖确定性
    # 代码无法完整识别的自由文本事实(公司、项目、证书等)。
    attest_truth: bool = False


class ResumeOptimizationSectionConfirm(StrictSchema):
    source_section_id: str
    accepted: bool = False
    edited_text: str | None = None


class ResumeOptimizationCreateVersionResult(StrictSchema):
    """Result of creating a new resume version from confirmed suggestions."""

    resume_version: dict[str, Any]
    applied_section_count: int
    parent_version_id: int
