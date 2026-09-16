import { beforeEach, describe, expect, it, vi } from "vitest"

const apiClient = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock("@/api/client", () => ({ apiClient }))

import { dashboardApi } from "@/api/dashboard"
import { toDashboardSnapshot } from "@/services/dashboard"

const payload = {
  resume_completeness: 86,
  confirmed_version_count: 2,
  confirmed_skill_evidence_count: 7,
  analyzed_job_count: 4,
  average_match_score: 78.5,
  recommended_job_count: 2,
  pending_confirmation_count: 1,
  recent_resumes: [
    {
      id: 3,
      title: "匿名候选人简历",
      file_type: "PDF",
      status: "NEEDS_CONFIRMATION" as const,
      progress: 85,
      updated_at: "2026-07-19T08:00:00Z",
    },
  ],
  top_skills: [{ name: "Python", evidence_count: 3, percentage: 100 }],
  resume_funnel: {
    uploaded: 3,
    extracted: 3,
    needs_confirmation: 1,
    confirmed: 2,
  },
  application_funnel: {
    saved: 1,
    applied: 3,
    interview: 1,
    offer: 0,
    rejected: 1,
  },
  weekly_application_count: 3,
  pending_interview_count: 2,
  recommended_jobs: [
    {
      report_id: 9,
      job_id: 5,
      title: "后端工程师",
      company: "示例科技",
      location: "上海",
      final_score: 88,
      recommendation: "RECOMMENDED",
      scoring_version: "deterministic-v1.1",
      created_at: "2026-07-19T08:00:00Z",
    },
  ],
}

describe("dashboard real API mapping", () => {
  beforeEach(() => vi.clearAllMocks())

  it("loads the authenticated aggregate endpoint", async () => {
    apiClient.get.mockResolvedValue({
      data: { success: true, data: payload, message: "ok" },
    })
    await expect(dashboardApi.getDashboard()).resolves.toEqual(payload)
    expect(apiClient.get).toHaveBeenCalledWith("/dashboard")
  })

  it("maps backend values without fixed business data", () => {
    const snapshot = toDashboardSnapshot(payload)
    expect(snapshot.completeness).toBe(86)
    expect(snapshot.pendingConfirmationCount).toBe(1)
    expect(snapshot.metrics.find((item) => item.id === "matches")).toMatchObject({
      value: 4,
      helper: "平均匹配分 78.5",
    })
    expect(snapshot.metrics.find((item) => item.id === "applications-week")).toMatchObject({
      value: 3,
      helper: "待推进面试 2 个",
    })
    expect(snapshot.workflows[0]?.status).toBe("review")
    expect(snapshot.skillEvidence[0]).toMatchObject({
      name: "Python",
      count: 3,
    })
    expect(snapshot.recommendedJobs[0]).toMatchObject({
      reportId: 9,
      score: 88,
    })
  })

  it("handles accounts without reports", () => {
    const snapshot = toDashboardSnapshot({
      ...payload,
      analyzed_job_count: 0,
      average_match_score: null,
      recommended_jobs: [],
    })
    expect(snapshot.metrics.find((item) => item.id === "matches")?.helper).toBe(
      "尚无匹配报告",
    )
    expect(snapshot.recommendedJobs).toEqual([])
  })
})
