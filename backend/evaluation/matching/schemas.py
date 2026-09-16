from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.matching import (
    RecommendationLevel,
    ReportConfidence,
    RequirementInformationStatus,
    SkillMatchStatus,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseCategory(StrEnum):
    HIGH_MATCH = "HIGH_MATCH"
    MEDIUM_MATCH = "MEDIUM_MATCH"
    SKILL_GAP = "SKILL_GAP"
    BLOCKING = "BLOCKING"
    INCOMPLETE_JOB = "INCOMPLETE_JOB"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class ResumeFixture(StrictModel):
    fixture_id: str
    skills: list[str]
    unconfirmed_skills: list[str] = Field(default_factory=list)
    duplicate_evidence: dict[str, int] = Field(default_factory=dict)
    experience_years: int | None = Field(default=4, ge=0, le=20)
    degree: str = "Bachelor"
    languages: list[str] = Field(default_factory=lambda: ["English"])
    certificates: list[str] = Field(default_factory=list)
    location: str = "Shanghai"
    preferences: dict[str, object] = Field(default_factory=dict)
    target_roles: list[str] = Field(default_factory=list)


class JobSkillFixture(StrictModel):
    name: str
    required: bool = True


class JobFixture(StrictModel):
    fixture_id: str
    title: str
    skills: list[JobSkillFixture] = Field(default_factory=list)
    requirements: str | None = None
    experience_level: str | None = None
    education_requirement: str | None = None
    languages: list[str] = Field(default_factory=list)
    location: str | None = None
    employment_type: str | None = None
    description: str = "Synthetic evaluation job."
    responsibilities: str | None = "Deliver reliable software."
    industry: str | None = "Software"


class EvaluationLabel(StrictModel):
    case_id: str
    category: CaseCategory
    resume_fixture: str
    job_fixture: str
    expected_score_min: float = Field(ge=0, le=100)
    expected_score_max: float = Field(ge=0, le=100)
    expected_recommendations: list[RecommendationLevel]
    expected_matched_skills: list[str] = Field(default_factory=list)
    expected_partial_skills: list[str] = Field(default_factory=list)
    expected_missing_skills: list[str] = Field(default_factory=list)
    expected_unknown_skills: list[str] = Field(default_factory=list)
    expected_blocking_risks: list[str] = Field(default_factory=list)
    expected_high_risks: list[str] = Field(default_factory=list)
    expected_evidence_sources: list[str] = Field(default_factory=list)
    expected_order_group: str | None = None
    expected_order_rank: int | None = Field(default=None, ge=1)
    notes: str

    @model_validator(mode="after")
    def validate_label(self) -> EvaluationLabel:
        if self.expected_score_min > self.expected_score_max:
            raise ValueError("expected_score_min must not exceed expected_score_max")
        skill_lists = (
            self.expected_matched_skills,
            self.expected_partial_skills,
            self.expected_missing_skills,
            self.expected_unknown_skills,
        )
        flattened = [item.casefold() for values in skill_lists for item in values]
        if len(flattened) != len(set(flattened)):
            raise ValueError("a skill may have only one expected status")
        if (self.expected_order_group is None) != (self.expected_order_rank is None):
            raise ValueError("order group and rank must be set together")
        return self


class EvaluationDataset(StrictModel):
    dataset_version: str
    resumes: list[ResumeFixture]
    jobs: list[JobFixture]
    labels: list[EvaluationLabel]


class CaseResult(StrictModel):
    case_id: str
    category: CaseCategory
    scoring_version: str
    rule_score: float
    recommendation: RecommendationLevel
    skill_statuses: dict[str, SkillMatchStatus]
    risks: dict[str, str]
    evidence_complete: int
    evidence_total: int
    required_skill_evidence_complete: int
    required_skill_evidence_total: int
    blocking_evidence_complete: int
    blocking_evidence_total: int
    not_provided_count: int
    unknown_count: int
    job_information_completeness: float
    report_confidence: float
    report_confidence_level: ReportConfidence
    recommendation_cap: RecommendationLevel | None = None
    policy_version: str | None = None
    information_statuses: dict[str, RequirementInformationStatus]
    duration_ms: float
    dimension_scores: dict[str, float]
    weighted_score_sum: float
    evidence_signature: list[str]
    config_snapshot: dict[str, object]
    expected_order_group: str | None = None
    expected_order_rank: int | None = None


class EvaluationMetrics(StrictModel):
    case_count: int
    recommendation_accuracy: float
    score_interval_hit_rate: float
    score_mean_absolute_error: float
    blocking_recall: float
    blocking_precision: float
    high_risk_recall: float
    skill_accuracy: dict[str, float]
    skill_macro_f1: float
    confusion_matrix: dict[str, dict[str, int]]
    evidence_trace_coverage: float
    required_skill_evidence_coverage: float
    blocking_evidence_coverage: float
    no_evidence_conclusion_count: int
    repeat_consistency_rate: float
    exact_ranking_accuracy: float
    pairwise_ranking_accuracy: float
    spearman_correlation: float
    unknown_ratio: float
    not_provided_ratio: float
    mean_duration_ms: float
    p50_duration_ms: float
    p95_duration_ms: float
