import { apiClient } from "@/api/client"
import type { ApiResponse } from "@/api/types"
import type {
  Job,
  JobFilters,
  JobImportResult,
  JobList,
  ManualJobPreview,
  UserJobInput,
  UserJobUpdate,
} from "@/types/job"

function compactParams(filters: JobFilters): Record<string, string | number> {
  return Object.fromEntries(
    Object.entries(filters).filter(
      ([, value]) => value !== undefined && value !== null && value !== "",
    ),
  ) as Record<string, string | number>
}

export async function listJobs(filters: JobFilters = {}): Promise<JobList> {
  const response = await apiClient.get<ApiResponse<JobList>>("/jobs", {
    params: compactParams(filters),
  })
  return response.data.data
}

export async function listFavoriteJobs(
  offset = 0,
  limit = 20,
): Promise<JobList> {
  const response = await apiClient.get<ApiResponse<JobList>>("/jobs/favorites", {
    params: { offset, limit },
  })
  return response.data.data
}

export async function getJob(jobId: number): Promise<Job> {
  const response = await apiClient.get<ApiResponse<Job>>(`/jobs/${jobId}`)
  return response.data.data
}

export async function setJobFavorite(
  jobId: number,
  favorite: boolean,
): Promise<void> {
  if (favorite) {
    await apiClient.post(`/jobs/${jobId}/favorite`)
  } else {
    await apiClient.delete(`/jobs/${jobId}/favorite`)
  }
}

export async function importManualJob(
  input: UserJobInput,
): Promise<JobImportResult> {
  const response = await apiClient.post<ApiResponse<JobImportResult>>(
    "/jobs/manual",
    input,
  )
  return response.data.data
}

export async function previewManualJob(input: UserJobInput): Promise<ManualJobPreview> {
  const response = await apiClient.post<ApiResponse<ManualJobPreview>>(
    "/jobs/manual/preview",
    input,
  )
  return response.data.data
}

export async function updatePrivateJob(jobId: number, input: UserJobUpdate): Promise<Job> {
  const response = await apiClient.patch<ApiResponse<Job>>(`/jobs/${jobId}`, input)
  return response.data.data
}

export async function deletePrivateJob(jobId: number): Promise<void> {
  await apiClient.delete(`/jobs/${jobId}`)
}

export async function importJobCsv(input: {
  csv_content: string
  delimiter: string
  field_mapping: Record<string, string>
}): Promise<JobImportResult> {
  const response = await apiClient.post<ApiResponse<JobImportResult>>(
    "/jobs/import-csv",
    input,
  )
  return response.data.data
}

export interface JobApi {
  listJobs(filters?: JobFilters): Promise<JobList>
  listFavoriteJobs(offset?: number, limit?: number): Promise<JobList>
  getJob(jobId: number): Promise<Job>
  setJobFavorite(jobId: number, favorite: boolean): Promise<void>
  importManualJob(input: UserJobInput): Promise<JobImportResult>
  previewManualJob(input: UserJobInput): Promise<ManualJobPreview>
  updatePrivateJob(jobId: number, input: UserJobUpdate): Promise<Job>
  deletePrivateJob(jobId: number): Promise<void>
  importJobCsv(input: {
    csv_content: string
    delimiter: string
    field_mapping: Record<string, string>
  }): Promise<JobImportResult>
}

export const jobApi: JobApi = {
  listJobs,
  listFavoriteJobs,
  getJob,
  setJobFavorite,
  importManualJob,
  previewManualJob,
  updatePrivateJob,
  deletePrivateJob,
  importJobCsv,
}

export const jobService = jobApi
