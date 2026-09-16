import { apiClient } from "@/api/client"
import type { ApiResponse } from "@/api/types"
import type {
  ResumeOptimization,
  ResumeOptimizationConfirmPayload,
  ResumeOptimizationCreateInput,
  ResumeOptimizationCreateVersionResult,
  ResumeOptimizationList,
} from "@/types/resume-optimization"

export async function createResumeOptimization(
  input: ResumeOptimizationCreateInput,
): Promise<ResumeOptimization> {
  const response = await apiClient.post<ApiResponse<ResumeOptimization>>(
    "/resume-optimizations",
    input,
  )
  return response.data.data
}

export async function listResumeOptimizations(params?: {
  offset?: number
  limit?: number
  include_failed?: boolean
}): Promise<ResumeOptimizationList> {
  const response = await apiClient.get<ApiResponse<ResumeOptimizationList>>(
    "/resume-optimizations",
    { params },
  )
  return response.data.data
}

export async function getResumeOptimization(
  id: number,
): Promise<ResumeOptimization> {
  const response = await apiClient.get<ApiResponse<ResumeOptimization>>(
    `/resume-optimizations/${id}`,
  )
  return response.data.data
}

export async function confirmResumeOptimization(
  id: number,
  payload: ResumeOptimizationConfirmPayload,
): Promise<ResumeOptimization> {
  const response = await apiClient.post<ApiResponse<ResumeOptimization>>(
    `/resume-optimizations/${id}/confirm`,
    payload,
  )
  return response.data.data
}

export async function retryResumeOptimization(
  id: number,
): Promise<ResumeOptimization> {
  const response = await apiClient.post<ApiResponse<ResumeOptimization>>(
    `/resume-optimizations/${id}/retry`,
  )
  return response.data.data
}

export async function createResumeOptimizationVersion(
  id: number,
): Promise<ResumeOptimizationCreateVersionResult> {
  const response = await apiClient.post<
    ApiResponse<ResumeOptimizationCreateVersionResult>
  >(`/resume-optimizations/${id}/create-version`)
  return response.data.data
}
