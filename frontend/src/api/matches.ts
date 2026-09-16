import { apiClient } from "@/api/client"
import type { ApiResponse } from "@/api/types"
import type {
  MatchCreateInput,
  MatchCreateResult,
  MatchDetail,
  MatchList,
  MatchReport,
  MatchStatusResult,
  MatchRun,
} from "@/types/matching"

export interface MatchListQuery {
  resume_version_id?: number
  job_id?: number
  offset?: number
  limit?: number
}

export interface MatchRunApi {
  create(input: MatchCreateInput): Promise<MatchRun>
  get(runId: number): Promise<MatchRun>
  retry(runId: number): Promise<MatchRun>
  confirm(runId: number): Promise<MatchRun>
  cancel(runId: number): Promise<MatchRun>
  eventUrl(runId: number): Promise<string>
}

export const matchRunApi: MatchRunApi = {
  async create(input) {
    const response = await apiClient.post<ApiResponse<MatchRun>>("/match-runs", input)
    return response.data.data
  },
  async get(runId) {
    const response = await apiClient.get<ApiResponse<MatchRun>>(`/match-runs/${runId}`)
    return response.data.data
  },
  async retry(runId) {
    const response = await apiClient.post<ApiResponse<{ run: MatchRun }>>(
      `/match-runs/${runId}/retry`,
    )
    return response.data.data.run
  },
  async confirm(runId) {
    const response = await apiClient.post<ApiResponse<{ run: MatchRun }>>(
      `/match-runs/${runId}/confirm`,
    )
    return response.data.data.run
  },
  async cancel(runId) {
    const response = await apiClient.post<ApiResponse<{ run: MatchRun }>>(
      `/match-runs/${runId}/cancel`,
    )
    return response.data.data.run
  },
  async eventUrl(runId) {
    const response = await apiClient.post<
      ApiResponse<{ ticket: string; expires_at: string }>
    >(`/match-runs/${runId}/event-ticket`)
    const baseUrl = String(apiClient.defaults.baseURL ?? "/api").replace(/\/$/, "")
    return `${baseUrl}/match-runs/${runId}/events?ticket=${encodeURIComponent(response.data.data.ticket)}`
  },
}

export interface MatchApi {
  create(input: MatchCreateInput): Promise<MatchCreateResult>
  list(query?: MatchListQuery): Promise<MatchList>
  get(matchId: number): Promise<MatchReport>
  details(matchId: number): Promise<MatchDetail[]>
  status(matchId: number): Promise<MatchStatusResult>
  recalculate(matchId: number): Promise<MatchCreateResult>
}

export const matchApi: MatchApi = {
  async create(input) {
    const response = await apiClient.post<ApiResponse<MatchCreateResult>>("/matches", input)
    return response.data.data
  },
  async list(query = {}) {
    const response = await apiClient.get<ApiResponse<MatchList>>("/matches", {
      params: query,
    })
    return response.data.data
  },
  async get(matchId) {
    const response = await apiClient.get<ApiResponse<MatchReport>>(`/matches/${matchId}`)
    return response.data.data
  },
  async details(matchId) {
    const response = await apiClient.get<ApiResponse<MatchDetail[]>>(
      `/matches/${matchId}/details`,
    )
    return response.data.data
  },
  async status(matchId) {
    const response = await apiClient.get<ApiResponse<MatchStatusResult>>(
      `/matches/${matchId}/status`,
    )
    return response.data.data
  },
  async recalculate(matchId) {
    const response = await apiClient.post<ApiResponse<MatchCreateResult>>(
      `/matches/${matchId}/recalculate`,
    )
    return response.data.data
  },
}

export interface MatchHistoryApi {
  forJob(jobId: number, offset?: number, limit?: number): Promise<MatchList>
  forResumeVersion(
    versionId: number,
    offset?: number,
    limit?: number,
  ): Promise<MatchList>
}

export const matchHistoryApi: MatchHistoryApi = {
  async forJob(jobId, offset = 0, limit = 20) {
    const response = await apiClient.get<ApiResponse<MatchList>>(
      `/jobs/${jobId}/match-history`,
      { params: { offset, limit } },
    )
    return response.data.data
  },
  async forResumeVersion(versionId, offset = 0, limit = 20) {
    const response = await apiClient.get<ApiResponse<MatchList>>(
      `/resume-versions/${versionId}/match-history`,
      { params: { offset, limit } },
    )
    return response.data.data
  },
}
