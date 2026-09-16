"""Strict structured-output contracts for real provider validation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JobSkillExtraction(StrictSchema):
    name: str = Field(min_length=1, max_length=120)
    required: bool
    evidence_text: str = Field(min_length=1, max_length=1000)


class JobRequirementProfile(StrictSchema):
    """Provider output used by the opt-in real Job parsing path."""

    title: str = Field(default="", max_length=240)
    required_skills: list[JobSkillExtraction] = Field(default_factory=list, max_length=80)
    preferred_skills: list[JobSkillExtraction] = Field(default_factory=list, max_length=80)
    minimum_experience_years: float | None = Field(default=None, ge=0, le=50)
    experience_required: bool | None = None
    education_requirement: str | None = Field(default=None, max_length=240)
    languages: list[str] = Field(default_factory=list, max_length=20)
    work_eligibility: str | None = Field(default=None, max_length=240)
    employment_type: str | None = Field(default=None, max_length=80)
    summary: str = Field(default="", max_length=2000)

