export type MatchStatus = "PENDING" | "RUNNING" | "SUCCESS" | "FAILED" | "CANCELLED"

export type MatchPhase =
  | "VALIDATING_INPUT"
  | "EXTRACTING_REQUIREMENTS"
  | "NORMALIZING_SKILLS"
  | "MATCHING_RULES"
  | "MATCHING_SEMANTIC"
  | "VERIFYING_EVIDENCE"
  | "CALCULATING_SCORE"
  | "SAVING_REPORT"
  | "COMPLETED"

export type SkillMatchStatus = "MATCHED" | "PARTIAL" | "MISSING" | "UNKNOWN"
export type AvailabilityStatus = "PROVIDED" | "UNKNOWN" | "NOT_PROVIDED"
export type RiskSeverity = "INFO" | "LOW" | "MEDIUM" | "HIGH" | "BLOCKING"
export type RiskType = "SKILL_GAP" | "BLOCKING_RISK" | "GENERAL_RISK"
export type VerificationStatus = "CONFIRMED" | "UNVERIFIED" | "CONFLICT"
export type DimensionStatus = "GOOD" | "PARTIAL" | "WEAK" | "UNKNOWN"
export type RecommendationLevel =
  | "STRONGLY_RECOMMENDED"
  | "RECOMMENDED"
  | "CONSIDER"
  | "HIGH_RISK"
  | "NOT_RECOMMENDED"
export type ReportConfidence = "HIGH" | "MEDIUM" | "LOW" | "VERY_LOW"
export type ScoringVersion = "deterministic-v1" | "deterministic-v1.1" | "hybrid-v1"

export interface ScoreWeights {
  hard_skills: number
  evidence_strength: number
  experience_education: number
  language_location_eligibility: number
  user_preferences: number
  other_conditions: number
}

export interface ScoringConfig {
  version: string
  skill_dictionary_version: string
  job_requirement_extractor_version: string
  weights: ScoreWeights
  partial_skill_credit: number
  unknown_criterion_credit: number
  required_skill_weight: number
  preferred_skill_weight: number
  base_rule_version?: string | null
  semantic?: SemanticScoringConfig | null
  hybrid_weights?: HybridWeights | null
  embedding_config?: EmbeddingConfigSnapshot | null
}

export interface SemanticScoringConfig {
  version: string
  top_k: number
  similarity_threshold: number
  similarity_ceiling: number
  empty_score: number
}

export interface HybridWeights {
  deterministic: number
  semantic: number
}

export interface EmbeddingConfigSnapshot {
  provider: string
  model: string
  device: string
  normalize_embeddings: boolean
}

export interface SemanticEvidence {
  rank: number
  relation: string
  similarity: number
  score: number
  resume_text: string
  job_text: string
  resume_section: string
  job_field: string
  page_number: number | null
  paragraph_index: number | null
  resume_metadata: Record<string, string | number | boolean | null>
  job_metadata: Record<string, string | number | boolean | null>
}

export interface SemanticSummary {
  evidence_count: number
  evaluated_resume_chunks: number
  top_similarity: number | null
  relation_counts: Record<string, number>
}

export interface DimensionScore {
  code: string
  label: string
  score: number
  weight: number
  weighted_score: number
  explanation: string
  status: DimensionStatus
  evidence_keys: string[]
  gap_codes: string[]
}

export interface EvidenceTrace {
  conclusion_key: string
  resume_version_id: number
  resume_skill_id: number | null
  resume_evidence: string | null
  resume_section: string | null
  source_type: string | null
  page_number: number | null
  paragraph_index: number | null
  source_location: string | null
  job_field: string
  job_snippet: string
  matching_rule: string
  confidence: number
}

export interface SkillMatch {
  normalized_name: string
  job_raw_name: string
  category: string | null
  requirement_type: string
  status: SkillMatchStatus
  score: number
  matching_rule: string
  explanation: string
  resume_skill_id: number | null
  evidence_count: number
  source_types: string[]
  responsibility_keyword_overlap: boolean
}

export interface RiskItem {
  code: string
  title: string
  severity: RiskSeverity
  explanation: string
  job_requirement: string | null
  resume_evidence: string | null
  remediation: string
  risk_type: RiskType
  verification_status: VerificationStatus
}

export interface RecommendedAction {
  code: string
  title: string
  explanation: string
  priority: RiskSeverity
}

export interface JobSkillRequirement {
  raw_name: string
  normalized_name: string
  category: string | null
  required: boolean
  weight: number
  evidence_text: string
  source_field: string
  normalization_rule: string
  confidence: number
}

export interface JobRequirements {
  job_title: string
  industry: string | null
  salary_min: number | null
  salary_max: number | null
  skills: JobSkillRequirement[]
  minimum_experience_years: number | null
  experience_status: AvailabilityStatus
  graduate_exception: boolean
  education_level: string | null
  education_status: AvailabilityStatus
  languages: string[]
  language_status: AvailabilityStatus
  location: string | null
  location_status: AvailabilityStatus
  employment_type: string | null
  employment_status: AvailabilityStatus
  certificates: string[]
  certificates_required: boolean
  certificate_status: AvailabilityStatus
  work_eligibility: string | null
  work_eligibility_status: AvailabilityStatus
  experience_required_explicit: boolean
  education_required_explicit: boolean
  education_non_substitutable: boolean
  language_required_explicit: boolean
  language_preferred: boolean
  certificate_required_explicit: boolean
  certificate_preferred: boolean
  warnings: string[]
  extractor_version: string
}

export interface EvidenceCoverage {
  total_requirements: number
  verified: number
  partially_supported: number
  missing: number
  unknown: number
  coverage_percent: number
}

export interface MatchInputSnapshot {
  resume: {
    resume_id: number
    version_id: number
    version_number: number
    is_confirmed: boolean
    created_at: string
  }
  job: {
    job_id: number
    title: string
    company: string
    location: string | null
    content_hash: string
    import_method: string | null
    description: string
    requirements: string | null
    responsibilities: string | null
  }
}

export interface MatchReport {
  id: number
  user_id: number
  resume_version_id: number
  job_id: number
  status: MatchStatus
  current_phase: MatchPhase
  rule_score: number | null
  semantic_score: number | null
  hybrid_score: number | null
  final_score: number | null
  scoring_version: ScoringVersion
  scoring_config_snapshot: ScoringConfig
  dimension_scores: DimensionScore[]
  matched_skills: SkillMatch[]
  partial_skills: SkillMatch[]
  missing_skills: SkillMatch[]
  hard_requirement_risks: RiskItem[]
  evidence_items: EvidenceTrace[]
  recommendation: RecommendationLevel | null
  explanation: string | null
  recommended_actions: RecommendedAction[]
  job_requirements: JobRequirements | null
  phase_timings_ms: Record<string, number>
  duration_ms: number | null
  error_code: string | null
  error_message: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
  job_information_completeness?: number | null
  report_confidence?: ReportConfidence | null
  report_confidence_score?: number | null
  completeness_warning?: string | null
  evaluated_requirement_count?: number
  unknown_requirement_count?: number
  not_provided_requirement_count?: number
  recommendation_cap?: RecommendationLevel | null
  policy_version?: string | null
  policy_config_snapshot?: Record<string, unknown> | null
  embedding_model?: string | null
  embedding_config_snapshot?: EmbeddingConfigSnapshot | null
  semantic_config_snapshot?: SemanticScoringConfig | null
  semantic_evidence?: SemanticEvidence[]
  semantic_summary?: SemanticSummary | null
  evidence_coverage: EvidenceCoverage
  input_snapshot?: MatchInputSnapshot | null
}

export interface MatchCreateInput {
  resume_version_id: number
  job_id: number
  scoring_version?: ScoringVersion
}

export interface MatchCreateResult {
  report: MatchReport
  reused: boolean
}

export interface MatchList {
  items: MatchReport[]
  total: number
  offset: number
  limit: number
}

export interface MatchStatusResult {
  id: number
  status: MatchStatus
  current_phase: MatchPhase
  phase_timings_ms: Record<string, number>
  duration_ms: number | null
  error_code: string | null
  error_message: string | null
}

export type MatchRunStatus =
  | "PENDING"
  | "RUNNING"
  | "WAITING_REVIEW"
  | "SUCCEEDED"
  | "FAILED"
  | "CANCELLED"
export type MatchNodeStatus =
  | "PENDING"
  | "RUNNING"
  | "SUCCEEDED"
  | "FAILED"
  | "SKIPPED"
  | "WAITING_REVIEW"
  | "CANCELLED"

export interface MatchRunStep {
  node_name: string
  status: MatchNodeStatus
  retry_count: number
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  summary: Record<string, unknown>
  error_message: string | null
}

export interface MatchRun {
  run_id: number
  user_id: number
  resume_version_id: number
  job_id: number
  scoring_version: ScoringVersion
  status: MatchRunStatus
  current_node: string | null
  node_status: MatchNodeStatus
  completed_nodes: string[]
  rule_score: number | null
  semantic_score: number | null
  hybrid_score: number | null
  blocking_risks: Array<Record<string, unknown>>
  report_id: number | null
  error_code: string | null
  error_message: string | null
  waiting_for_user: boolean
  retry_count: number
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  steps: MatchRunStep[]
}

export interface MatchRunEvent {
  id: number
  event:
    | "run_started"
    | "node_started"
    | "node_completed"
    | "node_failed"
    | "waiting_for_user"
    | "run_completed"
    | "run_failed"
    | "run_cancelled"
  run_id: number
  node: string | null
  status: string
  timestamp: string
  duration_ms: number | null
  summary: Record<string, unknown>
  error_code: string | null
  error_message: string | null
  report_id: number | null
}

export interface MatchEvidenceRead extends EvidenceTrace {
  id: number
  detail_id: number
}

export interface MatchDetail {
  id: number
  report_id: number
  category: string
  requirement: string
  status: string
  score: number | null
  sort_order: number
  code: string | null
  severity: string | null
  explanation: string | null
  remediation: string | null
  matching_rule: string | null
  data: Record<string, unknown>
  evidence: MatchEvidenceRead[]
}
