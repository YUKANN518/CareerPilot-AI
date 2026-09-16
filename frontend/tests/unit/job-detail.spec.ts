import { flushPromises, mount } from "@vue/test-utils"
import { describe, expect, it, vi } from "vitest"

const getJob = vi.hoisted(() => vi.fn())
const forJob = vi.hoisted(() => vi.fn())
vi.mock("@/services/jobs", () => ({
  jobService: {
    getJob,
    setJobFavorite: vi.fn(),
  },
}))
vi.mock("@/services/matching", () => ({
  matchHistoryService: { forJob },
  matchService: { recalculate: vi.fn() },
}))
vi.mock("@/api/resumes", () => ({
  listResumes: vi.fn().mockResolvedValue([]),
  listResumeVersions: vi.fn().mockResolvedValue([]),
}))
vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { jobId: "31" } }),
  useRouter: () => ({ push: vi.fn() }),
}))

import JobDetailPage from "@/pages/JobDetailPage.vue"

describe("real job detail page", () => {
  it("renders backend fields as text and protects the original link", async () => {
    forJob.mockResolvedValue({ items: [], total: 0, offset: 0, limit: 10 })
    getJob.mockResolvedValue({
      id: 31,
      source_id: 4,
      external_job_id: "31",
      title: "Backend Engineer",
      company: "CareerPilot",
      location: "Shanghai",
      salary_min: "25000",
      salary_max: "35000",
      currency: "CNY",
      employment_type: "FULL_TIME",
      experience_level: "MID",
      education_requirement: "BACHELOR",
      language_requirements: ["zh-CN"],
      description: "<script>alert('unsafe')</script> Build APIs",
      responsibilities: "Own platform reliability",
      requirements: "Python",
      source_url: "https://jobs.example.com/31",
      published_at: "2026-07-17T00:00:00Z",
      status: "ACTIVE",
      skills: ["Python"],
      source_name: "Official",
      source_type: "REST_API",
      source_last_sync_at: "2026-07-17T00:00:00Z",
      is_favorite: false,
      data_completeness: 90,
      summary: null,
      salary_summary: null,
      fetched_at: "2026-07-17T00:00:00Z",
      is_summary_only: false,
      original_platform_login_may_be_required: false,
      created_at: "2026-07-17T01:00:00Z",
      updated_at: "2026-07-17T01:00:00Z",
    })
    const wrapper = mount(JobDetailPage, {
      global: {
        stubs: {
          RouterLink: { template: "<a><slot /></a>" },
        },
      },
    })
    await flushPromises()

    expect(wrapper.text()).toContain("Backend Engineer")
    expect(wrapper.text()).toContain("<script>alert('unsafe')</script>")
    expect(wrapper.find("script").exists()).toBe(false)
    const link = wrapper.get('a[href="https://jobs.example.com/31"]')
    expect(link.attributes("target")).toBe("_blank")
    expect(link.attributes("rel")).toContain("noopener")
    expect(link.attributes("rel")).toContain("noreferrer")
    expect(wrapper.text()).toContain("入库：")
  })
})
