import axios from "axios"

import type { ApiErrorBody, ApiValidationDetail } from "@/api/types"

export type ApiErrorKind =
  | "bad-request"
  | "unauthorized"
  | "forbidden"
  | "not-found"
  | "conflict"
  | "validation"
  | "rate-limit"
  | "server"
  | "timeout"
  | "network"
  | "unknown"

export interface ApiErrorInfo {
  kind: ApiErrorKind
  status: number | null
  code: string
  message: string
  retryable: boolean
  fieldErrors: Record<string, string>
}

const statusMessages: Record<number, string> = {
  400: "请求内容无效，请检查后重试。",
  401: "登录状态已失效，请重新登录。",
  403: "当前账号没有执行此操作的权限。",
  404: "请求的资源不存在或已被删除。",
  409: "当前状态不允许此操作，请刷新后重试。",
  422: "提交内容未通过校验，请检查标记字段。",
  429: "请求过于频繁，请稍后重试。",
  500: "服务暂时不可用，请稍后重试。",
}

function kindFromStatus(status: number | null): ApiErrorKind {
  if (status === 400) return "bad-request"
  if (status === 401) return "unauthorized"
  if (status === 403) return "forbidden"
  if (status === 404) return "not-found"
  if (status === 409) return "conflict"
  if (status === 422) return "validation"
  if (status === 429) return "rate-limit"
  if (status !== null && status >= 500) return "server"
  return "unknown"
}

function isValidationDetails(value: unknown): value is ApiValidationDetail[] {
  return (
    Array.isArray(value) &&
    value.every(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        "field" in item &&
        typeof item.field === "string" &&
        "message" in item &&
        typeof item.message === "string",
    )
  )
}

function normalizeFieldPath(path: string): string {
  return path
    .replace(/^body\./, "")
    .replace(/^query\./, "")
    .replace(/^path\./, "")
}

export function mapPydanticFieldErrors(error: unknown): Record<string, string> {
  if (!axios.isAxiosError<ApiErrorBody>(error)) return {}
  const details = error.response?.data.error.details
  if (!isValidationDetails(details)) return {}
  return Object.fromEntries(
    details.map((detail) => [normalizeFieldPath(detail.field), detail.message]),
  )
}

export function getApiErrorInfo(error: unknown): ApiErrorInfo {
  if (axios.isAxiosError<ApiErrorBody>(error)) {
    if (error.code === "ECONNABORTED") {
      return {
        kind: "timeout",
        status: null,
        code: "NETWORK_TIMEOUT",
        message: "请求超时，请检查网络后重试。",
        retryable: true,
        fieldErrors: {},
      }
    }

    const status = error.response?.status ?? null
    if (status === null) {
      return {
        kind: "network",
        status,
        code: "NETWORK_ERROR",
        message: "无法连接服务，请检查网络或稍后重试。",
        retryable: true,
        fieldErrors: {},
      }
    }

    const body = error.response?.data
    return {
      kind: kindFromStatus(status),
      status,
      code: body?.error.code ?? `HTTP_${status}`,
      message: body?.error.message || statusMessages[status] || "请求失败，请稍后重试。",
      retryable: status === 429 || status >= 500,
      fieldErrors: mapPydanticFieldErrors(error),
    }
  }

  return {
    kind: "unknown",
    status: null,
    code: "UNKNOWN_ERROR",
    message: error instanceof Error ? error.message : "发生未知错误，请稍后重试。",
    retryable: false,
    fieldErrors: {},
  }
}

export function getApiErrorMessage(error: unknown): string {
  return getApiErrorInfo(error).message
}
