import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"

const getJob = vi.hoisted(() => vi.fn())
const listResumes = vi.hoisted(() => vi.fn())
const listResumeVersions = vi.hoisted(() => vi.fn())
const create = vi.hoisted(() => vi.fn())
const push = vi.hoisted(() => vi.fn())

vi.mock("@/api/jobs", () => ({ getJob }))
vi.mock("@/api/resumes", () => ({ listResumes, listResumeVersions }))
vi.mock("@/services/matching", () => ({ matchRunService: { create } }))
vi.mock("vue-router", () => ({
  useRoute: () => ({ query: { jobId: "31", resumeVersionId: "12" } }),
  useRouter: () => ({ push }),
}))

import MatchNewPage from "@/pages/MatchNewPage.vue"
import { resumeProfile } from "@/../tests/unit/resume-fixture"

const job = {
  id: 31,
  title: "Backend Engineer",
  company: "CareerPilot",
  location: "Shanghai",
  data_completeness: 90,
  summary: null,
  salary_summary: null,
  fetched_at: "2026-07-17T00:00:00Z",
  is_summary_only: false,
  original_platform_login_may_be_required: false,
}
const resume = {
  id: 3,
  title: "Confirmed Resume",
  status: "CONFIRMED",
}
const version = {
  id: 12,
  resume_id: 3,
  version_number: 2,
  structured_data: resumeProfile(),
  is_current: true,
  is_confirmed: true,
  created_at: "2026-07-17T00:00:00Z",
}

describe("MatchNewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getJob.mockResolvedValue(job)
    listResumes.mockResolvedValue([resume])
    listResumeVersions.mockResolvedValue([version])
  })

  it("selects a confirmed version and sends the real create request", async () => {
    create.mockResolvedValue({ run_id: 81 })
    const wrapper = mount(MatchNewPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    expect(wrapper.get("#match-resume-version").element).toHaveProperty("value", "12")
    await wrapper.get("form").trigger("submit")
    await flushPromises()
    expect(create).toHaveBeenCalledWith({
      job_id: 31,
      resume_version_id: 12,
      scoring_version: "deterministic-v1.1",
    })
    expect(push).toHaveBeenCalledWith({
      name: "match-processing",
      params: { runId: 81 },
    })
  })

  it("allows selecting hybrid mode as a supporting semantic signal", async () => {
    create.mockResolvedValue({ run_id: 82 })
    const wrapper = mount(MatchNewPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    await wrapper.get('input[value="hybrid-v1"]').setValue()
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    expect(create).toHaveBeenCalledWith({
      job_id: 31,
      resume_version_id: 12,
      scoring_version: "hybrid-v1",
    })
    expect(wrapper.text()).toContain("语义为辅助信号")
    expect(wrapper.text()).toContain("语义不能证明技能")
  })

  it("shows a resume-center call to action instead of an empty selector", async () => {
    listResumes.mockResolvedValue([])
    const wrapper = mount(MatchNewPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain("还没有正式简历版本")
    expect(wrapper.find("#match-resume-version").exists()).toBe(false)
    expect(wrapper.text()).toContain("前往简历中心")
  })
})
