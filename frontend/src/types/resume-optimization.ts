export type ResumeOptimizationStatus = "DRAFT" | "CONFIRMED" | "FAILED" | "ARCHIVED"

export type SectionChangeType =
  | "REWRITE"
  | "REORDER"
  | "SHORTEN"
  | "EMPHASIZE"
  | "NO_CHANGE"

export interface ResumeOptimizationSection {
  section: string
  source_section_id: string
  original_text: string
  suggested_text: string
  reason: string
  related_job_requirement: string
  evidence_keys: string[]
  change_type: SectionChangeType
  accepted: boolean
  edited_text: string | null
}

export interface ResumeOptimizationKeywordSuggestion {
  keyword: string
  reason: string
  evidence_keys: string[]
}

export interface ResumeOptimization {
  id: number
  user_id: number
  resume_version_id: number
  job_id: number
  match_report_id: number
  status: ResumeOptimizationStatus
  summary: string
  sections: ResumeOptimizationSection[]
  keyword_suggestions: ResumeOptimizationKeywordSuggestion[]
  missing_evidence_warnings: string[]
  fabrication_warnings: string[]
  job_information_warning: string
  is_human_confirmed: boolean
  workflow_run_id: string | null
  workflow_version: string | null
  provider: string | null
  latency_ms: number | null
  error_code: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface ResumeOptimizationList {
  items: ResumeOptimization[]
  total: number
  offset: number
  limit: number
}

export interface ResumeOptimizationCreateInput {
  resume_version_id: number
  job_id: number
  match_report_id: number
}

export interface ResumeOptimizationSectionConfirm {
  source_section_id: string
  accepted: boolean
  edited_text?: string | null
}

export interface ResumeOptimizationConfirmPayload {
  sections: ResumeOptimizationSectionConfirm[]
  attest_truth: boolean
}

export interface ResumeOptimizationCreateVersionResult {
  resume_version: {
    id: number
    resume_id: number
    version_number: number
    parent_version_id: number | null
    is_current: boolean
    is_confirmed: boolean
  }
  applied_section_count: number
  parent_version_id: number
}
