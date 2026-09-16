export type JobSourceType =
  | "MANUAL"
  | "CSV"
  | "GENERIC_HTML"
  | "REST_API"
  | "SINGLE_JOB_URL"

export type JobSort =
  | "published_desc"
  | "published_asc"
  | "salary_desc"
  | "title_asc"
  | "created_desc"

export interface Job {
  id: number
  source_id: number | null
  external_job_id: string | null
  title: string
  company: string
  location: string | null
  salary_min: string | null
  salary_max: string | null
  currency: string | null
  employment_type: string | null
  experience_level: string | null
  education_requirement: string | null
  language_requirements: string[]
  description: string
  responsibilities: string | null
  requirements: string | null
  source_url: string | null
  published_at: string | null
  status: string
  skills: string[]
  source_name: string
  source_type: string
  source_last_sync_at: string | null
  is_favorite: boolean
  data_completeness: number
  // Derived display fields
  summary: string | null
  salary_summary: string | null
  fetched_at: string | null
  is_summary_only: boolean
  original_platform_login_may_be_required: boolean
  is_public_snapshot: boolean
  last_verified_at: string | null
  source_access_limited: boolean
  created_at: string
  updated_at: string
}

export interface JobList {
  items: Job[]
  total: number
  offset: number
  limit: number
  page: number
  page_size: number
  total_pages: number
}

export interface JobFilters {
  search?: string
  location?: string
  company?: string
  employment_type?: string
  experience_level?: string
  source_id?: number
  source_name?: string
  source_type?: JobSourceType
  published_after?: string
  information_type?: "SUMMARY"
  visibility?: "ALL" | "PUBLIC" | "PRIVATE"
  sort?: JobSort
  offset?: number
  limit?: number
}

export interface UserJobInput {
  external_job_id?: string
  title: string
  company?: string
  location?: string
  salary_min?: number
  salary_max?: number
  currency?: string
  employment_type?: string
  experience_level?: string
  education_requirement?: string
  language_requirements?: string[]
  description?: string
  responsibilities?: string
  requirements?: string
  source_url?: string
  published_at?: string
  skills?: string[]
}

export type UserJobUpdate = Partial<UserJobInput>

export interface ManualJobPreview {
  title: string
  company: string
  location: string | null
  description: string
  responsibilities: string | null
  requirements: string | null
  source_url: string | null
  employment_type: string | null
  experience_level: string | null
  education_requirement: string | null
  skills: string[]
}

export interface JobImportResult {
  items: Job[]
  imported_count: number
  duplicate_count: number
  failed_count: number
  errors: string[]
}
