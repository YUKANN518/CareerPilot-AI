import type { AxiosProgressEvent } from "axios"

import { apiClient } from "@/api/client"
import type { ApiResponse } from "@/api/types"
import type {
  ExtractionResult,
  ParseResult,
  Resume,
  ResumeProfile,
  ResumeSkill,
  ResumeUploadResult,
  ResumeVersion,
} from "@/types/resume"

export async function listResumes(): Promise<Resume[]> {
  const response = await apiClient.get<ApiResponse<Resume[]>>("/resumes")
  return response.data.data
}

export async function getResume(resumeId: number): Promise<Resume> {
  const response = await apiClient.get<ApiResponse<Resume>>(`/resumes/${resumeId}`)
  return response.data.data
}

export async function uploadResume(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<ResumeUploadResult> {
  const body = new FormData()
  body.append("file", file)
  const response = await apiClient.post<ApiResponse<ResumeUploadResult>>(
    "/resumes/upload",
    body,
    {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress: (event: AxiosProgressEvent) => {
        if (event.total && onProgress) {
          onProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)))
        }
      },
    },
  )
  return response.data.data
}

export async function deleteResume(resumeId: number): Promise<void> {
  await apiClient.delete(`/resumes/${resumeId}`)
}

export async function downloadResumeFile(resumeId: number): Promise<Blob> {
  const response = await apiClient.get<Blob>(`/resumes/${resumeId}/file`, {
    responseType: "blob",
  })
  return response.data
}

export async function extractResume(
  resumeId: number,
  signal?: AbortSignal,
): Promise<ExtractionResult> {
  const response = await apiClient.post<ApiResponse<ExtractionResult>>(
    `/resumes/${resumeId}/extract`,
    undefined,
    { signal },
  )
  return response.data.data
}

export async function parseResume(
  resumeId: number,
  signal?: AbortSignal,
): Promise<ParseResult> {
  const response = await apiClient.post<ApiResponse<ParseResult>>(
    `/resumes/${resumeId}/parse`,
    undefined,
    { signal },
  )
  return response.data.data
}

export async function getParseResult(resumeId: number): Promise<ParseResult> {
  const response = await apiClient.get<ApiResponse<ParseResult>>(
    `/resumes/${resumeId}/parse-result`,
  )
  return response.data.data
}

export async function updateParseResult(
  resumeId: number,
  profile: ResumeProfile,
): Promise<ParseResult> {
  const response = await apiClient.patch<ApiResponse<ParseResult>>(
    `/resumes/${resumeId}/parse-result`,
    profile,
  )
  return response.data.data
}

export async function confirmResume(resumeId: number): Promise<ResumeVersion> {
  const response = await apiClient.post<ApiResponse<ResumeVersion>>(
    `/resumes/${resumeId}/confirm`,
  )
  return response.data.data
}

export async function listResumeVersions(resumeId: number): Promise<ResumeVersion[]> {
  const response = await apiClient.get<ApiResponse<ResumeVersion[]>>(
    `/resumes/${resumeId}/versions`,
  )
  return response.data.data
}

export async function getResumeVersion(versionId: number): Promise<ResumeVersion> {
  const response = await apiClient.get<ApiResponse<ResumeVersion>>(
    `/resume-versions/${versionId}`,
  )
  return response.data.data
}

export async function listResumeVersionSkills(
  versionId: number,
): Promise<ResumeSkill[]> {
  const response = await apiClient.get<ApiResponse<ResumeSkill[]>>(
    `/resume-versions/${versionId}/skills`,
  )
  return response.data.data
}
