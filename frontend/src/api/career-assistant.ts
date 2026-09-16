import type { AxiosProgressEvent } from "axios"

import { apiClient } from "@/api/client"
import type { ApiResponse } from "@/api/types"
import type {
  CareerAssistantQA,
  CareerAssistantQAEventTicket,
  CareerAssistantQAList,
  CareerAssistantQACreateInput,
  KnowledgeDocument,
  KnowledgeDocumentList,
  KnowledgeDocumentReindexResult,
  KnowledgeDocumentUploadInput,
} from "@/types/career-assistant"

export async function createCareerAssistantQA(
  input: CareerAssistantQACreateInput,
): Promise<CareerAssistantQA> {
  const response = await apiClient.post<ApiResponse<CareerAssistantQA>>(
    "/career-assistant/qa",
    input,
  )
  return response.data.data
}

export async function getCareerAssistantQA(runId: number): Promise<CareerAssistantQA> {
  const response = await apiClient.get<ApiResponse<CareerAssistantQA>>(
    `/career-assistant/qa/${runId}`,
  )
  return response.data.data
}

export async function listCareerAssistantQA(
  offset = 0,
  limit = 20,
): Promise<CareerAssistantQAList> {
  const response = await apiClient.get<ApiResponse<CareerAssistantQAList>>(
    "/career-assistant/qa",
    { params: { offset, limit } },
  )
  return response.data.data
}

export async function createCareerAssistantEventTicket(
  runId: number,
): Promise<CareerAssistantQAEventTicket> {
  const response = await apiClient.post<
    ApiResponse<CareerAssistantQAEventTicket>
  >(`/career-assistant/qa/${runId}/event-ticket`)
  return response.data.data
}

export async function careerAssistantEventUrl(runId: number): Promise<string> {
  const ticket = await createCareerAssistantEventTicket(runId)
  const baseUrl = String(apiClient.defaults.baseURL ?? "/api").replace(/\/$/, "")
  return `${baseUrl}/career-assistant/qa/${runId}/events?ticket=${encodeURIComponent(ticket.ticket)}`
}

export async function listAdminKnowledgeDocuments(
  offset = 0,
  limit = 20,
): Promise<KnowledgeDocumentList> {
  const response = await apiClient.get<ApiResponse<KnowledgeDocumentList>>(
    "/admin/knowledge-documents",
    { params: { offset, limit } },
  )
  return response.data.data
}

export async function getAdminKnowledgeDocument(
  documentId: number,
): Promise<KnowledgeDocument> {
  const response = await apiClient.get<ApiResponse<KnowledgeDocument>>(
    `/admin/knowledge-documents/${documentId}`,
  )
  return response.data.data
}

export async function uploadAdminKnowledgeDocument(
  input: KnowledgeDocumentUploadInput,
  onProgress?: (percent: number) => void,
): Promise<KnowledgeDocument> {
  const body = new FormData()
  body.append("file", input.file)
  body.append("title", input.title)
  body.append("category", input.category)
  const response = await apiClient.post<ApiResponse<KnowledgeDocument>>(
    "/admin/knowledge-documents",
    body,
    {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (event: AxiosProgressEvent) => {
        if (event.total && onProgress) {
          onProgress(
            Math.min(100, Math.round((event.loaded / event.total) * 100)),
          )
        }
      },
    },
  )
  return response.data.data
}

export async function deleteAdminKnowledgeDocument(
  documentId: number,
): Promise<void> {
  await apiClient.delete(`/admin/knowledge-documents/${documentId}`)
}

export async function reindexAdminKnowledgeDocument(
  documentId: number,
): Promise<KnowledgeDocumentReindexResult> {
  const response = await apiClient.post<
    ApiResponse<KnowledgeDocumentReindexResult>
  >(`/admin/knowledge-documents/${documentId}/reindex`)
  return response.data.data
}
