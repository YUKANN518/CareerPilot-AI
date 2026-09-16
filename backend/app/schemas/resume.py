from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ResumeStatus


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceLocation(StrictSchema):
    source_type: Literal["page", "paragraph", "table", "unknown"]
    page_number: int | None = Field(default=None, ge=1)
    block_index: int | None = Field(default=None, ge=0)
    paragraph_index: int | None = Field(default=None, ge=0)
    table_index: int | None = Field(default=None, ge=0)
    row_index: int | None = Field(default=None, ge=0)
    label: str = Field(min_length=1, max_length=120)


class EvidenceField(StrictSchema):
    value: str = Field(default="", max_length=10_000)
    confidence: float = Field(ge=0, le=1)
    evidence_text: str = Field(default="", max_length=4_000)
    source_location: SourceLocation
    needs_confirmation: bool


class StructuredSkill(EvidenceField):
    value: str = Field(min_length=1, max_length=120)
    evidence_text: str = Field(min_length=1, max_length=4_000)
    category: str | None = Field(default=None, max_length=80)
    level: str | None = Field(default=None, max_length=40)


class BasicInfo(StrictSchema):
    full_name: EvidenceField
    email: EvidenceField
    phone: EvidenceField
    location: EvidenceField


class EducationItem(StrictSchema):
    institution: EvidenceField
    degree: EvidenceField
    field_of_study: EvidenceField
    start_date: EvidenceField
    end_date: EvidenceField
    description: EvidenceField


class WorkExperienceItem(StrictSchema):
    company: EvidenceField
    title: EvidenceField
    start_date: EvidenceField
    end_date: EvidenceField
    description: EvidenceField


class ProjectExperienceItem(StrictSchema):
    name: EvidenceField
    role: EvidenceField
    start_date: EvidenceField
    end_date: EvidenceField
    description: EvidenceField


class ResumeProfile(StrictSchema):
    basic_info: BasicInfo
    education: list[EducationItem]
    work_experience: list[WorkExperienceItem]
    project_experience: list[ProjectExperienceItem]
    technical_skills: list[StructuredSkill]
    soft_skills: list[StructuredSkill]
    languages: list[EvidenceField]
    certificates: list[EvidenceField]
    awards: list[EvidenceField]
    summary: EvidenceField

    @model_validator(mode="after")
    def ensure_skill_evidence(self) -> ResumeProfile:
        for skill in [*self.technical_skills, *self.soft_skills]:
            if not skill.evidence_text.strip():
                raise ValueError(f"技能 {skill.value} 缺少原文证据")
        return self


class TextBlock(StrictSchema):
    source_type: Literal["page", "paragraph", "table"]
    text: str = Field(min_length=1)
    page_number: int | None = Field(default=None, ge=1)
    block_index: int | None = Field(default=None, ge=0)
    paragraph_index: int | None = Field(default=None, ge=0)
    table_index: int | None = Field(default=None, ge=0)
    row_index: int | None = Field(default=None, ge=0)


class FileAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    original_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    file_format: str


class ResumeRead(BaseModel):
    id: int
    title: str
    status: ResumeStatus
    file: FileAssetRead
    parse_attempts: int
    extracted_at: datetime | None
    parsed_at: datetime | None
    confirmed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version_count: int
    last_error_code: str | None
    last_error_message: str | None


class ResumeUploadResult(BaseModel):
    resume: ResumeRead
    duplicate: bool


class ExtractionResult(BaseModel):
    resume_id: int
    status: ResumeStatus
    character_count: int
    blocks: list[TextBlock]


class ParseResultRead(BaseModel):
    resume_id: int
    status: ResumeStatus
    result: ResumeProfile | None
    parse_attempts: int
    low_confidence_count: int
    error_code: str | None
    error_message: str | None


class ResumeVersionRead(BaseModel):
    id: int
    resume_id: int
    version_number: int
    structured_data: ResumeProfile
    is_current: bool
    is_confirmed: bool
    parent_version_id: int | None = None
    created_at: datetime


class ResumeSkillRead(BaseModel):
    id: int
    normalized_name: str
    raw_name: str
    category: str | None
    level: str | None
    confidence: float
    evidence_text: str
    evidence_section: str
    source_location: SourceLocation
    resume_version_id: int
    is_user_confirmed: bool


def count_low_confidence_fields(profile: ResumeProfile, threshold: float) -> int:
    def count_value(value: Any) -> int:
        if isinstance(value, EvidenceField):
            return int(value.confidence < threshold or value.needs_confirmation)
        if isinstance(value, BaseModel):
            return sum(count_value(item) for item in value.__dict__.values())
        if isinstance(value, list):
            return sum(count_value(item) for item in value)
        return 0

    return count_value(profile)
