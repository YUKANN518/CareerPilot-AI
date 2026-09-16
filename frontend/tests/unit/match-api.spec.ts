import { beforeEach, describe, expect, it, vi } from "vitest"

const apiClient = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))
vi.mock("@/api/client", () => ({ apiClient }))

import { matchApi, matchHistoryApi } from "@/api/matches"
import { matchReport } from "@/../tests/unit/match-fixture"

describe("MatchApi real contract mapping", () => {
  beforeEach(() => vi.clearAllMocks())

  it("creates a match with exact Pydantic input and maps reused result", async () => {
    const result = { report: matchReport(), reused: true }
    apiClient.post.mockResolvedValue({
      data: { success: true, data: result, message: "Existing match report reused" },
    })

    await expect(
      matchApi.create({ resume_version_id: 12, job_id: 31 }),
    ).resolves.toBe(result)
    expect(apiClient.post).toHaveBeenCalledWith("/matches", {
      resume_version_id: 12,
      job_id: 31,
    })
  })

  it("maps report, details, status, recalculate and two history endpoints", async () => {
    const report = matchReport()
    const list = { items: [report], total: 1, offset: 0, limit: 20 }
    apiClient.get.mockResolvedValue({
      data: { success: true, data: list, message: "ok" },
    })

    await matchApi.list({ job_id: 31 })
    await matchHistoryApi.forJob(31)
    await matchHistoryApi.forResumeVersion(12)

    expect(apiClient.get).toHaveBeenNthCalledWith(1, "/matches", {
      params: { job_id: 31 },
    })
    expect(apiClient.get).toHaveBeenNthCalledWith(
      2,
      "/jobs/31/match-history",
      { params: { offset: 0, limit: 20 } },
    )
    expect(apiClient.get).toHaveBeenNthCalledWith(
      3,
      "/resume-versions/12/match-history",
      { params: { offset: 0, limit: 20 } },
    )
  })
})
