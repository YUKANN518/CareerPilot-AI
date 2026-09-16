import { apiClient } from "@/api/client"
import { getApiErrorMessage } from "@/api/errors"
import type { ApiResponse } from "@/api/types"
import type {
  AuthSession,
  LoginInput,
  RegisterInput,
  TokenPair,
  User,
} from "@/types/auth"

export async function registerUser(input: RegisterInput): Promise<AuthSession> {
  const response = await apiClient.post<ApiResponse<AuthSession>>("/auth/register", input)
  return response.data.data
}

export async function loginUser(input: LoginInput): Promise<AuthSession> {
  const response = await apiClient.post<ApiResponse<AuthSession>>("/auth/login", input)
  return response.data.data
}

export async function logoutUser(refreshToken: string): Promise<void> {
  await apiClient.post("/auth/logout", { refresh_token: refreshToken })
}

export async function getCurrentUser(): Promise<User> {
  const response = await apiClient.get<ApiResponse<User>>("/users/me")
  return response.data.data
}

export { getApiErrorMessage }
export type { TokenPair }
