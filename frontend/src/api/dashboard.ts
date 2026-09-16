import { apiClient } from "@/api/client"
import type { ApiResponse } from "@/api/types"

export type DashboardResumeStatus =
  | "UPLOADED"
  | "EXTRACTING"
  | "EXTRACTED"
  | "PARSING"
  | "NEEDS_CONFIRMATION"
  | "CONFIRMED"
  | "FAILED"
  | "ARCHIVED"

export interface DashboardResume {
  id: number
  title: string
  file_type: string | null
  status: DashboardResumeStatus
  progress: number
  updated_at: string
}

export interface DashboardSkill {
  name: string
  evidence_count: number
  percentage: number
}

export interface DashboardRecommendedJob {
  report_id: number
  job_id: number
  title: string
  company: string
  location: string | null
  final_score: number
  recommendation: string
  scoring_version: string
  created_at: string
}

export interface DashboardData {
  resume_completeness: number
  confirmed_version_count: number
  confirmed_skill_evidence_count: number
  analyzed_job_count: number
  average_match_score: number | null
  recommended_job_count: number
  pending_confirmation_count: number
  recent_resumes: DashboardResume[]
  top_skills: DashboardSkill[]
  resume_funnel: {
    uploaded: number
    extracted: number
    needs_confirmation: number
    confirmed: number
  }
  application_funnel: {
    saved: number
    applied: number
    interview: number
    offer: number
    rejected: number
  }
  weekly_application_count: number
  pending_interview_count: number
  recommended_jobs: DashboardRecommendedJob[]
}

export async function getDashboard(): Promise<DashboardData> {
  const response =
    await apiClient.get<ApiResponse<DashboardData>>("/dashboard")
  return response.data.data
}

export const dashboardApi = { getDashboard }
