import { apiClient } from "@/api/client"
import type { ApiResponse } from "@/api/types"

export interface RuntimeMode {
  status: "ok"
  ai_mode: "demo" | "mixed" | "real"
  ai_provider: "mock" | "openai_compatible"
  dify_provider_mode: "fake" | "dify"
}

export async function getRuntimeMode(): Promise<RuntimeMode> {
  const response = await apiClient.get<ApiResponse<RuntimeMode>>("/health")
  return response.data.data
}
