from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MatchStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MatchPhase(StrEnum):
    VALIDATING_INPUT = "VALIDATING_INPUT"
    EXTRACTING_REQUIREMENTS = "EXTRACTING_REQUIREMENTS"
    NORMALIZING_SKILLS = "NORMALIZING_SKILLS"
    MATCHING_RULES = "MATCHING_RULES"
    MATCHING_SEMANTIC = "MATCHING_SEMANTIC"
    VERIFYING_EVIDENCE = "VERIFYING_EVIDENCE"
    CALCULATING_SCORE = "CALCULATING_SCORE"
    SAVING_REPORT = "SAVING_REPORT"
    COMPLETED = "COMPLETED"


class SkillMatchStatus(StrEnum):
    MATCHED = "MATCHED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class AvailabilityStatus(StrEnum):
    PROVIDED = "PROVIDED"
    UNKNOWN = "UNKNOWN"
    NOT_PROVIDED = "NOT_PROVIDED"


class RequirementInformationStatus(StrEnum):
    PROVIDED = "PROVIDED"
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_PROVIDED = "NOT_PROVIDED"
    UNPARSEABLE = "UNPARSEABLE"


class RiskSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    BLOCKING = "BLOCKING"


class RiskType(StrEnum):
    SKILL_GAP = "SKILL_GAP"
    BLOCKING_RISK = "BLOCKING_RISK"
    GENERAL_RISK = "GENERAL_RISK"


class VerificationStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    UNVERIFIED = "UNVERIFIED"
    CONFLICT = "CONFLICT"


class DimensionStatus(StrEnum):
    GOOD = "GOOD"
    PARTIAL = "PARTIAL"
    WEAK = "WEAK"
    UNKNOWN = "UNKNOWN"


class RecommendationLevel(StrEnum):
    STRONGLY_RECOMMENDED = "STRONGLY_RECOMMENDED"
    RECOMMENDED = "RECOMMENDED"
    CONSIDER = "CONSIDER"
    HIGH_RISK = "HIGH_RISK"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"


class ReportConfidence(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    VERY_LOW = "VERY_LOW"


class ConfidenceThresholds(StrictSchema):
    high_min: float = Field(default=0.8, ge=0, le=1)
    medium_min: float = Field(default=0.6, ge=0, le=1)
    low_min: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode="after")
    def validate_order(self) -> ConfidenceThresholds:
        if not self.high_min > self.medium_min > self.low_min:
            raise ValueError("confidence thresholds must descend from high to low")
        return self


class CompletenessThresholds(StrictSchema):
    unrestricted_min: float = Field(default=0.8, ge=0, le=1)
    recommended_cap_min: float = Field(default=0.6, ge=0, le=1)
    consider_cap_min: float = Field(default=0.5, ge=0, le=1)

    @model_validator(mode="after")
    def validate_order(self) -> CompletenessThresholds:
        if not self.unrestricted_min > self.recommended_cap_min > self.consider_cap_min:
            raise ValueError("completeness thresholds must descend from unrestricted")
        return self


class BlockingPolicyConfig(StrictSchema):
    policy_version: str = "blocking-policy-v1"
    work_eligibility_rule: str = "explicit_requirement_and_confirmed_conflict"
    mandatory_certificate_rule: str = "explicit_mandatory_and_confirmed_absence"
    mandatory_language_rule: str = "explicit_mandatory_and_confirmed_mismatch"
    experience_gap_rule: str = "explicit_minimum_and_gap_threshold"
    education_rule: str = "explicit_non_substitutable_minimum"
    explicit_requirement_markers: list[str] = Field(
        default_factory=lambda: [
            "must",
            "required",
            "mandatory",
            "must have",
            "minimum",
            "at least",
            "必须",
            "必需",
            "持有",
            "最低",
            "至少",
            "硬性要求",
            "不可替代",
        ]
    )
    preferred_requirement_markers: list[str] = Field(
        default_factory=lambda: [
            "preferred",
            "nice to have",
            "plus",
            "bonus",
            "优先",
            "加分",
            "更佳",
        ]
    )
    blocking_experience_gap_years: float = Field(default=3, gt=0, le=20)
    confidence_thresholds: ConfidenceThresholds = Field(default_factory=ConfidenceThresholds)
    completeness_thresholds: CompletenessThresholds = Field(default_factory=CompletenessThresholds)


class SemanticScoringConfig(StrictSchema):
    version: str = "semantic-v1"
    top_k: int = Field(default=5, ge=1, le=20)
    similarity_threshold: float = Field(default=0.25, ge=-1, le=1)
    similarity_ceiling: float = Field(default=1, gt=0, le=1)
    empty_score: float = Field(default=0, ge=0, le=100)


class HybridWeights(StrictSchema):
    deterministic: float = Field(default=0.7, ge=0, le=1)
    semantic: float = Field(default=0.3, ge=0, le=1)

    @model_validator(mode="after")
    def validate_total(self) -> HybridWeights:
        if abs(self.deterministic + self.semantic - 1) > 0.000001:
            raise ValueError("hybrid weights must total 1")
        return self


class ScoreWeights(StrictSchema):
    hard_skills: int = Field(default=35, ge=0, le=100)
    evidence_strength: int = Field(default=20, ge=0, le=100)
    experience_education: int = Field(default=15, ge=0, le=100)
    language_location_eligibility: int = Field(default=10, ge=0, le=100)
    user_preferences: int = Field(default=10, ge=0, le=100)
    other_conditions: int = Field(default=10, ge=0, le=100)

    @model_validator(mode="after")
    def validate_total(self) -> ScoreWeights:
        if sum(self.model_dump().values()) != 100:
            raise ValueError("matching dimension weights must total 100")
        return self


class EmbeddingConfigSnapshot(StrictSchema):
    provider: str
    model: str
    device: str
    normalize_embeddings: bool = True


class ScoringConfig(StrictSchema):
    version: str = "deterministic-v1"
    skill_dictionary_version: str = "skill-dictionary-v1"
    job_requirement_extractor_version: str = "job-requirements-v1"
    weights: ScoreWeights = Field(default_factory=ScoreWeights)
    partial_skill_credit: float = Field(default=0.5, ge=0, le=1)
    unknown_criterion_credit: float = Field(default=0.7, ge=0, le=1)
    required_skill_weight: int = Field(default=2, ge=1)
    preferred_skill_weight: int = Field(default=1, ge=1)
    blocking_policy: BlockingPolicyConfig | None = None
    base_rule_version: str | None = None
    semantic: SemanticScoringConfig | None = None
    hybrid_weights: HybridWeights | None = None
    embedding_config: EmbeddingConfigSnapshot | None = None


class SemanticEvidence(StrictSchema):
    rank: int = Field(ge=1)
    relation: str
    similarity: float = Field(ge=-1, le=1)
    score: float = Field(ge=0, le=100)
    resume_text: str
    job_text: str
    resume_section: str
    job_field: str
    page_number: int | None = Field(default=None, ge=1)
    paragraph_index: int | None = Field(default=None, ge=0)
    resume_metadata: dict[str, JsonValue]
    job_metadata: dict[str, JsonValue]


class SemanticSummary(StrictSchema):
    evidence_count: int = Field(ge=0)
    evaluated_resume_chunks: int = Field(ge=0)
    top_similarity: float | None = Field(default=None, ge=-1, le=1)
    relation_counts: dict[str, int] = Field(default_factory=dict)


class NormalizedSkill(StrictSchema):
    raw_name: str
    normalized_name: str
    category: str | None
    normalization_rule: str
    confidence: float = Field(ge=0, le=1)
    dictionary_version: str


class JobSkillRequirement(StrictSchema):
    raw_name: str
    normalized_name: str
    category: str | None
    required: bool
    weight: int = Field(ge=1)
    evidence_text: str
    source_field: str
    normalization_rule: str
    confidence: float = Field(ge=0, le=1)


class JobRequirements(StrictSchema):
    job_title: str
    industry: str | None = None
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    skills: list[JobSkillRequirement]
    minimum_experience_years: float | None = Field(default=None, ge=0)
    experience_status: AvailabilityStatus
    graduate_exception: bool = False
    education_level: str | None = None
    education_status: AvailabilityStatus
    languages: list[str]
    language_status: AvailabilityStatus
    location: str | None = None
    location_status: AvailabilityStatus
    employment_type: str | None = None
    employment_status: AvailabilityStatus
    certificates: list[str]
    certificates_required: bool
    certificate_status: AvailabilityStatus
    work_eligibility: str | None = None
    work_eligibility_status: AvailabilityStatus
    experience_required_explicit: bool = False
    education_required_explicit: bool = False
    education_non_substitutable: bool = False
    language_required_explicit: bool = False
    language_preferred: bool = False
    certificate_required_explicit: bool = False
    certificate_preferred: bool = False
    warnings: list[str]
    extractor_version: str


class JobInformationAssessment(StrictSchema):
    statuses: dict[str, RequirementInformationStatus]
    job_information_completeness: float = Field(ge=0, le=1)
    evaluated_requirement_count: int = Field(ge=0)
    not_provided_requirement_count: int = Field(ge=0)
    unparseable_requirement_count: int = Field(ge=0)


class DimensionScore(StrictSchema):
    code: str
    label: str
    score: float = Field(ge=0, le=100)
    weight: int = Field(ge=0, le=100)
    weighted_score: float = Field(ge=0, le=100)
    explanation: str
    status: DimensionStatus = DimensionStatus.UNKNOWN
    evidence_keys: list[str] = Field(default_factory=list)
    gap_codes: list[str] = Field(default_factory=list)


class EvidenceTrace(StrictSchema):
    conclusion_key: str
    resume_version_id: int
    resume_skill_id: int | None
    resume_evidence: str | None
    resume_section: str | None
    source_type: str | None
    page_number: int | None = Field(default=None, ge=1)
    paragraph_index: int | None = Field(default=None, ge=0)
    source_location: str | None
    job_field: str
    job_snippet: str
    matching_rule: str
    confidence: float = Field(ge=0, le=1)


class SkillMatch(StrictSchema):
    normalized_name: str
    job_raw_name: str
    category: str | None
    requirement_type: str
    status: SkillMatchStatus
    score: float = Field(ge=0, le=1)
    matching_rule: str
    explanation: str
    resume_skill_id: int | None
    evidence_count: int = Field(ge=0)
    source_types: list[str]
    responsibility_keyword_overlap: bool


class RiskItem(StrictSchema):
    code: str
    title: str = ""
    severity: RiskSeverity
    explanation: str
    job_requirement: str | None
    resume_evidence: str | None
    remediation: str
    risk_type: RiskType = RiskType.GENERAL_RISK
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED

    @model_validator(mode="after")
    def populate_title(self) -> RiskItem:
        if not self.title:
            self.title = self.code.replace("_", " ").title()
        return self


class RecommendedAction(StrictSchema):
    code: str
    title: str
    explanation: str
    priority: RiskSeverity


class EvidenceCoverage(StrictSchema):
    total_requirements: int = Field(ge=0)
    verified: int = Field(ge=0)
    partially_supported: int = Field(ge=0)
    missing: int = Field(ge=0)
    unknown: int = Field(ge=0)
    coverage_percent: float = Field(ge=0, le=100)


class ResumeInputSnapshot(StrictSchema):
    resume_id: int
    version_id: int
    version_number: int
    is_confirmed: bool
    created_at: datetime


class JobInputSnapshot(StrictSchema):
    job_id: int
    title: str
    company: str
    location: str | None = None
    content_hash: str
    import_method: str | None = None
    description: str
    requirements: str | None = None
    responsibilities: str | None = None


class MatchInputSnapshot(StrictSchema):
    resume: ResumeInputSnapshot
    job: JobInputSnapshot


class MatchComputation(StrictSchema):
    rule_score: float = Field(ge=0, le=100)
    dimension_scores: list[DimensionScore]
    skill_matches: list[SkillMatch]
    risks: list[RiskItem]
    evidence_items: list[EvidenceTrace]
    recommendation: RecommendationLevel
    explanation: str
    recommended_actions: list[RecommendedAction]
    job_information_completeness: float | None = Field(default=None, ge=0, le=1)
    report_confidence: ReportConfidence | None = None
    report_confidence_score: float | None = Field(default=None, ge=0, le=1)
    completeness_warning: str | None = None
    evaluated_requirement_count: int = Field(default=0, ge=0)
    unknown_requirement_count: int = Field(default=0, ge=0)
    not_provided_requirement_count: int = Field(default=0, ge=0)
    recommendation_cap: RecommendationLevel | None = None
    policy_version: str | None = None
    policy_config_snapshot: BlockingPolicyConfig | None = None


class MatchCreate(StrictSchema):
    resume_version_id: int = Field(ge=1)
    job_id: int = Field(ge=1)
    scoring_version: str | None = Field(
        default=None,
        pattern=r"^(deterministic-v1(\.1)?|hybrid-v1)$",
    )


class MatchEvidenceRead(EvidenceTrace):
    id: int
    detail_id: int


class MatchDetailRead(StrictSchema):
    id: int
    report_id: int
    category: str
    requirement: str
    status: str
    score: float | None
    sort_order: int
    code: str | None
    severity: str | None
    explanation: str | None
    remediation: str | None
    matching_rule: str | None
    data: dict[str, JsonValue]
    evidence: list[MatchEvidenceRead]


class MatchReportRead(StrictSchema):
    id: int
    user_id: int
    resume_version_id: int
    job_id: int
    status: MatchStatus
    current_phase: MatchPhase
    rule_score: float | None
    semantic_score: float | None
    hybrid_score: float | None
    final_score: float | None
    scoring_version: str
    scoring_config_snapshot: ScoringConfig
    dimension_scores: list[DimensionScore]
    matched_skills: list[SkillMatch]
    partial_skills: list[SkillMatch]
    missing_skills: list[SkillMatch]
    hard_requirement_risks: list[RiskItem]
    evidence_items: list[EvidenceTrace]
    recommendation: RecommendationLevel | None
    explanation: str | None
    recommended_actions: list[RecommendedAction]
    job_requirements: JobRequirements | None
    phase_timings_ms: dict[str, int]
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    job_information_completeness: float | None = Field(default=None, ge=0, le=1)
    report_confidence: ReportConfidence | None = None
    report_confidence_score: float | None = Field(default=None, ge=0, le=1)
    completeness_warning: str | None = None
    evaluated_requirement_count: int = Field(default=0, ge=0)
    unknown_requirement_count: int = Field(default=0, ge=0)
    not_provided_requirement_count: int = Field(default=0, ge=0)
    recommendation_cap: RecommendationLevel | None = None
    policy_version: str | None = None
    policy_config_snapshot: BlockingPolicyConfig | None = None
    embedding_model: str | None = None
    embedding_config_snapshot: EmbeddingConfigSnapshot | None = None
    semantic_config_snapshot: SemanticScoringConfig | None = None
    semantic_evidence: list[SemanticEvidence] = Field(default_factory=list)
    semantic_summary: SemanticSummary | None = None
    evidence_coverage: EvidenceCoverage
    input_snapshot: MatchInputSnapshot | None = None


class MatchCreateResult(StrictSchema):
    report: MatchReportRead
    reused: bool


class MatchListRead(StrictSchema):
    items: list[MatchReportRead]
    total: int
    offset: int
    limit: int


class MatchStatusRead(StrictSchema):
    id: int
    status: MatchStatus
    current_phase: MatchPhase
    phase_timings_ms: dict[str, int]
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
