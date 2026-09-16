import { describe, expect, it } from "vitest"

import {
  getApiErrorInfo,
  mapPydanticFieldErrors,
} from "@/api/errors"

function axiosError(status: number, details?: unknown): unknown {
  return {
    isAxiosError: true,
    response: {
      status,
      data: {
        success: false,
        error: {
          code: status === 422 ? "VALIDATION_ERROR" : "TEST_ERROR",
          message: "请求参数校验失败",
          details,
        },
      },
    },
  }
}

describe("API error mapping", () => {
  it("maps Pydantic detail paths to form fields", () => {
    const error = axiosError(422, [
      {
        field: "body.name",
        message: "Field required",
        type: "missing",
      },
      {
        field: "body.config.endpoint",
        message: "URL invalid",
        type: "value_error",
      },
    ])
    expect(mapPydanticFieldErrors(error)).toEqual({
      name: "Field required",
      "config.endpoint": "URL invalid",
    })
    expect(getApiErrorInfo(error).kind).toBe("validation")
  })

  it.each([
    [400, "bad-request"],
    [401, "unauthorized"],
    [403, "forbidden"],
    [404, "not-found"],
    [409, "conflict"],
    [429, "rate-limit"],
    [500, "server"],
  ] as const)("classifies HTTP %s", (status, kind) => {
    expect(getApiErrorInfo(axiosError(status)).kind).toBe(kind)
  })

  it("classifies timeout and network failures", () => {
    expect(
      getApiErrorInfo({ isAxiosError: true, code: "ECONNABORTED" }).kind,
    ).toBe("timeout")
    expect(getApiErrorInfo({ isAxiosError: true }).kind).toBe("network")
  })
})
