from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import ResumeStatus


class DashboardResumeRead(BaseModel):
    id: int
    title: str
    file_type: str | None
    status: ResumeStatus
    progress: int = Field(ge=0, le=100)
    updated_at: datetime


class DashboardSkillRead(BaseModel):
    name: str
    evidence_count: int = Field(ge=1)
    percentage: int = Field(ge=0, le=100)


class DashboardResumeFunnelRead(BaseModel):
    uploaded: int = Field(ge=0)
    extracted: int = Field(ge=0)
    needs_confirmation: int = Field(ge=0)
    confirmed: int = Field(ge=0)


class DashboardApplicationFunnelRead(BaseModel):
    saved: int = Field(ge=0)
    applied: int = Field(ge=0)
    interview: int = Field(ge=0)
    offer: int = Field(ge=0)
    rejected: int = Field(ge=0)


class DashboardRecommendedJobRead(BaseModel):
    report_id: int
    job_id: int
    title: str
    company: str
    location: str | None
    final_score: float = Field(ge=0, le=100)
    recommendation: str
    scoring_version: str
    created_at: datetime


class DashboardRead(BaseModel):
    resume_completeness: int = Field(ge=0, le=100)
    confirmed_version_count: int = Field(ge=0)
    confirmed_skill_evidence_count: int = Field(ge=0)
    analyzed_job_count: int = Field(ge=0)
    average_match_score: float | None = Field(default=None, ge=0, le=100)
    recommended_job_count: int = Field(ge=0)
    pending_confirmation_count: int = Field(ge=0)
    recent_resumes: list[DashboardResumeRead]
    top_skills: list[DashboardSkillRead]
    resume_funnel: DashboardResumeFunnelRead
    application_funnel: DashboardApplicationFunnelRead
    weekly_application_count: int = Field(ge=0)
    pending_interview_count: int = Field(ge=0)
    recommended_jobs: list[DashboardRecommendedJobRead]
