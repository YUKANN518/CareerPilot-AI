import { apiClient } from "@/api/client"
import type { ApiResponse } from "@/api/types"
import type {
  Application,
  ApplicationBoard,
  ApplicationCreateInput,
  ApplicationStatusInput,
  ApplicationUpdateInput,
} from "@/types/application"

export async function createApplication(input: ApplicationCreateInput): Promise<Application> {
  const response = await apiClient.post<ApiResponse<Application>>("/applications", input)
  return response.data.data
}

export async function getApplicationBoard(): Promise<ApplicationBoard> {
  const response = await apiClient.get<ApiResponse<ApplicationBoard>>("/applications/board")
  return response.data.data
}

export async function updateApplication(
  applicationId: number,
  input: ApplicationUpdateInput,
): Promise<Application> {
  const response = await apiClient.patch<ApiResponse<Application>>(
    `/applications/${applicationId}`,
    input,
  )
  return response.data.data
}

export async function updateApplicationStatus(
  applicationId: number,
  input: ApplicationStatusInput,
): Promise<Application> {
  const response = await apiClient.post<ApiResponse<Application>>(
    `/applications/${applicationId}/status`,
    input,
  )
  return response.data.data
}

export async function deleteApplication(applicationId: number): Promise<void> {
  await apiClient.delete(`/applications/${applicationId}`)
}

export const applicationService = {
  create: createApplication,
  board: getApplicationBoard,
  update: updateApplication,
  updateStatus: updateApplicationStatus,
  delete: deleteApplication,
}
