import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios"

import { clearTokens, readTokens, writeTokens } from "@/api/token-storage"
import type { ApiResponse } from "@/api/types"
import type { TokenPair } from "@/types/auth"

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api"

export const apiClient = axios.create({
  baseURL,
  // Default timeout covers most API calls. Long-running AI workflows
  // (e.g. interview final evaluation) override this per-request via the
  // `timeout` config option in their API wrapper.
  timeout: 60_000,
  headers: {
    "Content-Type": "application/json",
  },
})

const refreshClient = axios.create({ baseURL, timeout: 10_000 })
let refreshRequest: Promise<TokenPair> | null = null

apiClient.interceptors.request.use((config) => {
  const accessToken = readTokens()?.access_token
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`
  }
  return config
})

type RetryableRequest = InternalAxiosRequestConfig & { _retry?: boolean }

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const request = error.config as RetryableRequest | undefined
    const tokens = readTokens()
    const isRefreshRequest = request?.url?.includes("/auth/refresh") ?? false
    if (
      error.response?.status !== 401 ||
      request === undefined ||
      request._retry ||
      isRefreshRequest ||
      tokens === null
    ) {
      return Promise.reject(error)
    }

    request._retry = true
    refreshRequest ??= refreshClient
      .post<ApiResponse<TokenPair>>("/auth/refresh", {
        refresh_token: tokens.refresh_token,
      })
      .then((response) => {
        writeTokens(response.data.data)
        return response.data.data
      })
      .catch((refreshError: unknown) => {
        clearTokens()
        throw refreshError
      })
      .finally(() => {
        refreshRequest = null
      })

    const refreshed = await refreshRequest
    request.headers.Authorization = `Bearer ${refreshed.access_token}`
    return apiClient(request)
  },
)
