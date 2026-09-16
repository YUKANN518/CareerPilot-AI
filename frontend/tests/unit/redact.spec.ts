import { describe, expect, it } from "vitest"

import { redactText, sanitizeLogJson } from "@/utils/redact"

describe("sync log sanitization", () => {
  it("redacts credentials and omits large response bodies", () => {
    expect(redactText("Authorization: Bearer abc.def")).not.toContain("abc.def")
    expect(
      sanitizeLogJson({
        Authorization: "Bearer secret",
        response_body: "complete upstream response",
        imported_count: 2,
      }),
    ).toEqual({
      Authorization: "[REDACTED]",
      response_body: "[OMITTED]",
      imported_count: 2,
    })
  })
})
