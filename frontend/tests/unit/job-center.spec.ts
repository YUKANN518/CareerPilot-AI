import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"

import JobsPage from "@/pages/JobsPage.vue"
import type { Job } from "@/types/job"

const service = vi.hoisted(() => ({
  listJobs: vi.fn(),
  listFavoriteJobs: vi.fn(),
  getJob: vi.fn(),
  setJobFavorite: vi.fn(),
  previewManualJob: vi.fn(),
  importManualJob: vi.fn(),
  importJobCsv: vi.fn(),
}))
const routerPush = vi.hoisted(() => vi.fn())

vi.mock("@/services/jobs", () => ({ jobService: service }))
vi.mock("@/api/auth", () => ({
  getApiErrorMessage: () => "岗位请求失败",
}))
vi.mock("vue-router", () => ({
  useRouter: () => ({ push: routerPush }),
  RouterLink: { template: "<a><slot /></a>" },
}))

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: 31,
    source_id: 4,
    external_job_id: "job-31",
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
    description: "Build reliable APIs",
    responsibilities: null,
    requirements: "Python",
    source_url: "https://jobs.example.com/31",
    published_at: "2026-07-17T00:00:00Z",
    status: "ACTIVE",
    skills: ["Python"],
    source_name: "Official careers",
    source_type: "REST_API",
    source_last_sync_at: "2026-07-17T00:00:00Z",
    is_favorite: false,
    data_completeness: 92,
    summary: null,
    salary_summary: null,
    fetched_at: null,
    is_summary_only: false,
    original_platform_login_may_be_required: false,
    is_public_snapshot: false,
    last_verified_at: null,
    source_access_limited: false,
    created_at: "2026-07-17T00:00:00Z",
    updated_at: "2026-07-17T00:00:00Z",
    ...overrides,
  }
}

function mountPage() {
  return mount(JobsPage, {
    global: {
      stubs: {
        RouterLink: { template: "<a><slot /></a>" },
        Teleport: true,
      },
    },
  })
}

describe("target job page", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    service.listJobs.mockResolvedValue({
      items: [job()],
      total: 1,
      offset: 0,
      limit: 20,
      page: 1,
      page_size: 20,
      total_pages: 1,
    })
    service.setJobFavorite.mockResolvedValue(undefined)
  })

  it("sends search and filters to the API service", async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('input[placeholder="搜索职位、公司或岗位描述"]').setValue("Backend")
    await wrapper.get("#job-location").setValue("Shanghai")
    await wrapper.get("#employment-type").setValue("FULL_TIME")
    await wrapper.get("#experience-level").setValue("MID")
    await wrapper.get('button[type="submit"]').trigger("submit")
    await flushPromises()

    expect(service.listJobs).toHaveBeenLastCalledWith(
      expect.objectContaining({
        search: "Backend",
        location: "Shanghai",
        employment_type: "FULL_TIME",
        experience_level: "MID",
        visibility: "ALL",
      }),
    )
    expect(wrapper.text()).toContain("Backend Engineer")
  })

  it("favorites through the API and updates the accessible state", async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('button[aria-label="收藏岗位"]').trigger("click")
    await flushPromises()

    expect(service.setJobFavorite).toHaveBeenCalledWith(31, true)
    expect(wrapper.find('button[aria-label="取消收藏"]').exists()).toBe(true)
  })

  it("keeps loading, empty, and error results mutually exclusive", async () => {
    service.listJobs.mockResolvedValueOnce({
      items: [],
      total: 0,
      offset: 0,
      limit: 20,
      page: 1,
      page_size: 20,
      total_pages: 0,
    })
    const emptyWrapper = mountPage()
    await flushPromises()
    expect(emptyWrapper.text()).toContain("没有符合条件的目标岗位")
    expect(emptyWrapper.text()).not.toContain("岗位请求失败")

    service.listJobs.mockRejectedValueOnce(new Error("network"))
    const errorWrapper = mountPage()
    await flushPromises()
    expect(errorWrapper.text()).toContain("岗位请求失败")
    expect(errorWrapper.text()).not.toContain("没有符合条件的目标岗位")
  })

  it("focuses the page on saved target jobs and supported imports", async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(service.listJobs).toHaveBeenCalledWith(expect.objectContaining({ visibility: "ALL" }))
    expect(wrapper.get("h1").text()).toBe("目标岗位")
    expect(wrapper.text()).toContain("输入岗位详情并匹配")
    expect(wrapper.text()).toContain("导入 CSV")
    expect(wrapper.text()).not.toContain("我的收藏")

  })

  it("requires a normalized preview before saving a private job", async () => {
    service.previewManualJob.mockResolvedValue({
      title: "Backend Engineer",
      company: "未提供",
      location: null,
      description: "Build APIs",
      responsibilities: null,
      requirements: "Python",
      source_url: null,
      employment_type: null,
      experience_level: null,
      education_requirement: null,
      skills: [],
    })
    service.importManualJob.mockResolvedValue({
      items: [job({ source_id: null, source_type: "USER_MANUAL" })],
      imported_count: 1,
      duplicate_count: 0,
      failed_count: 0,
      errors: [],
    })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.findAll("button").find((button) => button.text().includes("输入岗位详情"))?.trigger("click")
    await wrapper.get("#manual-title").setValue("Backend Engineer")
    await wrapper.get("#manual-requirements").setValue("Python")
    await wrapper.findAll("form").at(-1)?.trigger("submit")
    await flushPromises()

    expect(service.previewManualJob).toHaveBeenCalled()
    expect(wrapper.find('[data-testid="manual-job-preview"]').exists()).toBe(true)
    expect(service.importManualJob).not.toHaveBeenCalled()
  })
})
