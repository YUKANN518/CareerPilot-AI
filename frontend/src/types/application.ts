export type ApplicationStatus =
  | "SAVED"
  | "APPLIED"
  | "INTERVIEW"
  | "OFFER"
  | "REJECTED"

export interface ApplicationJob {
  id: number
  title: string
  company: string
  location: string | null
  source_url: string | null
  employment_type: string | null
  source_name: string
  is_favorite: boolean
}

export interface ApplicationStatusHistory {
  id: number
  from_status: ApplicationStatus | null
  to_status: ApplicationStatus
  note: string | null
  created_at: string
}

export interface Application {
  id: number
  user_id: number
  job_id: number
  status: ApplicationStatus
  notes: string | null
  next_action_at: string | null
  job: ApplicationJob
  status_history: ApplicationStatusHistory[]
  created_at: string
  updated_at: string
}

export interface ApplicationBoard {
  columns: Record<ApplicationStatus, Application[]>
  counts: Record<ApplicationStatus, number>
}

export interface ApplicationCreateInput {
  job_id: number
  status?: "SAVED"
  notes?: string | null
  next_action_at?: string | null
}

export interface ApplicationUpdateInput {
  notes?: string | null
  next_action_at?: string | null
}

export interface ApplicationStatusInput {
  status: ApplicationStatus
  note?: string | null
  next_action_at?: string | null
}
