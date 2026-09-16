import { apiClient } from "@/api/client"
import type { ApiResponse } from "@/api/types"
import type {
  Interview,
  InterviewChatReportRead,
  InterviewChatStatusRead,
  InterviewChatTurnResponse,
  InterviewCreateInput,
  InterviewList,
  InterviewMessage,
  InterviewMessageSubmit,
} from "@/types/interview"

export async function createInterview(
  input: InterviewCreateInput,
): Promise<Interview> {
  const response = await apiClient.post<ApiResponse<Interview>>(
    "/interviews",
    input,
  )
  return response.data.data
}

export async function listInterviews(params?: {
  offset?: number
  limit?: number
  include_failed?: boolean
}): Promise<InterviewList> {
  const response = await apiClient.get<ApiResponse<InterviewList>>(
    "/interviews",
    { params },
  )
  return response.data.data
}

export async function getInterview(id: number): Promise<Interview> {
  const response = await apiClient.get<ApiResponse<Interview>>(
    `/interviews/${id}`,
  )
  return response.data.data
}

export async function startInterviewChat(
  interviewId: number,
): Promise<InterviewChatStatusRead> {
  const response = await apiClient.post<
    ApiResponse<InterviewChatStatusRead>
  >(`/interviews/${interviewId}/chat/start`)
  return response.data.data
}

export async function sendInterviewMessage(
  interviewId: number,
  payload: InterviewMessageSubmit,
): Promise<InterviewChatTurnResponse> {
  // The last question's answer triggers the Dify Final Evaluation
  // Workflow, which can take ~30s. Use a per-request timeout well above
  // the global default to avoid the client aborting while the server
  // is still generating the report.
  const response = await apiClient.post<
    ApiResponse<InterviewChatTurnResponse>
  >(`/interviews/${interviewId}/messages`, payload, {
    timeout: 90_000,
  })
  return response.data.data
}

export async function listInterviewMessages(
  interviewId: number,
): Promise<InterviewMessage[]> {
  const response = await apiClient.get<ApiResponse<InterviewMessage[]>>(
    `/interviews/${interviewId}/messages`,
  )
  return response.data.data
}

export async function completeInterviewChat(
  interviewId: number,
): Promise<InterviewChatStatusRead> {
  const response = await apiClient.post<
    ApiResponse<InterviewChatStatusRead>
  >(`/interviews/${interviewId}/chat/complete`)
  return response.data.data
}

export async function cancelInterviewChat(
  interviewId: number,
): Promise<InterviewChatStatusRead> {
  const response = await apiClient.post<
    ApiResponse<InterviewChatStatusRead>
  >(`/interviews/${interviewId}/chat/cancel`)
  return response.data.data
}

export async function getInterviewChatStatus(
  interviewId: number,
): Promise<InterviewChatStatusRead> {
  const response = await apiClient.get<
    ApiResponse<InterviewChatStatusRead>
  >(`/interviews/${interviewId}/chat/status`)
  return response.data.data
}

export async function getInterviewChatReport(
  interviewId: number,
): Promise<InterviewChatReportRead> {
  const response = await apiClient.get<ApiResponse<InterviewChatReportRead>>(
    `/interviews/${interviewId}/chat/report`,
  )
  return response.data.data
}
