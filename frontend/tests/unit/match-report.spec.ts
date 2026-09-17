import { flushPromises, mount } from "@vue/test-utils"
import { describe, expect, it, vi } from "vitest"

const get = vi.hoisted(() => vi.fn())
const details = vi.hoisted(() => vi.fn())
const recalculate = vi.hoisted(() => vi.fn())
const getJob = vi.hoisted(() => vi.fn())
const getResumeVersion = vi.hoisted(() => vi.fn())
const listResumeVersionSkills = vi.hoisted(() => vi.fn())
const push = vi.hoisted(() => vi.fn())

vi.mock("@/services/matching", () => ({
  matchService: { get, details, recalculate },
}))
vi.mock("@/api/jobs", () => ({ getJob }))
vi.mock("@/api/resumes", () => ({ getResumeVersion, listResumeVersionSkills }))
vi.mock("@/components/domain/MatchDimensionChart.vue", () => ({
  default: { template: '<div data-testid="dimension-chart" />' },
}))
vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { matchId: "41" } }),
  useRouter: () => ({ push }),
}))

import MatchReportPage from "@/pages/MatchReportPage.vue"
import MatchEvidenceDrawer from "@/components/domain/MatchEvidenceDrawer.vue"
import { matchReport } from "@/../tests/unit/match-fixture"
import { resumeProfile } from "@/../tests/unit/resume-fixture"

function prepare(report = matchReport()) {
  get.mockResolvedValue(report)
  details.mockResolvedValue([])
  getJob.mockResolvedValue({
    id: 31,
    title: "Backend Engineer",
    company: "CareerPilot",
    location: "Shanghai",
  })
  getResumeVersion.mockResolvedValue({
    id: 12,
    resume_id: 3,
    version_number: 2,
    structured_data: resumeProfile(),
    is_current: true,
    is_confirmed: true,
    created_at: "2026-07-17T00:00:00Z",
  })
  listResumeVersionSkills.mockResolvedValue([
    {
      id: 8,
      normalized_name: "Python",
      raw_name: "Python",
      category: "TECHNICAL",
      level: null,
      confidence: 0.95,
      evidence_text: "Built Python.",
      evidence_section: "work_experience",
      source_location: {
        source_type: "page",
        page_number: 1,
        block_index: 0,
        paragraph_index: null,
        table_index: null,
        row_index: null,
        label: "page-1",
      },
      resume_version_id: 12,
      is_user_confirmed: true,
    },
  ])
}

describe("match report page", () => {
  it("renders six backend dimensions and scoring snapshot weights", async () => {
    prepare()
    const wrapper = mount(MatchReportPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    expect(
      wrapper.findAll('button[data-testid^="dimension-"]'),
    ).toHaveLength(6)
    expect(wrapper.text()).toContain("hard_skills")
    expect(wrapper.text()).toContain("35%")
    expect(wrapper.text()).toContain("尚未启用语义评分")
    expect(wrapper.text()).toContain("数据状态 后端未提供")
    expect(wrapper.get('[data-testid="recommendation"]').text()).toContain("强烈推荐")
    expect(wrapper.get('[data-testid="dimension-explanation-hard_skills"]').text()).toContain(
      "后端结论",
    )
    expect(wrapper.get('[data-testid="matching-methodology"]').text()).toContain(
      "语义相关性只表示文本相关程度",
    )
  })

  it("shows NOT_RECOMMENDED and blocking warning even for a high score", async () => {
    prepare(matchReport({ blocking: true }))
    const wrapper = mount(MatchReportPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="blocking-warning"]').text()).toContain(
      "高分不能抵消资格冲突",
    )
    expect(wrapper.get('[data-testid="recommendation"]').text()).toContain("不建议申请")
    expect(wrapper.text()).toContain("93.67")
  })

  it("shows incomplete-job warning and four independent skill categories", async () => {
    prepare(matchReport({ incomplete: true }))
    const wrapper = mount(MatchReportPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="incomplete-job-warning"]').text()).toContain(
      "推荐结论可信度有限",
    )
    for (const status of ["MATCHED", "PARTIAL", "MISSING", "UNKNOWN"]) {
      expect(wrapper.find(`[data-testid="skills-${status}"]`).exists()).toBe(true)
    }
    expect(wrapper.get('[data-testid="skills-MISSING"]').text()).toContain(
      "未找到已确认的证据",
    )
  })

  it("shows hybrid scores and semantic relevance separately", async () => {
    prepare(matchReport({ hybrid: true }))
    const wrapper = mount(MatchReportPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="semantic-evidence-section"]').text()).toContain(
      "语义相关性",
    )
    expect(wrapper.text()).toContain("82")
    expect(wrapper.text()).toContain("85.68")
    expect(wrapper.text()).toContain("fake-deterministic-v1")
    expect(wrapper.text()).toContain("辅助信号")

    await wrapper.get('[data-testid="semantic-evidence-1"]').trigger("click")
    const drawer = wrapper.findComponent(MatchEvidenceDrawer)
    expect(drawer.props("open")).toBe(true)
    expect(drawer.props("semanticEvidence")).toHaveLength(1)
    expect(drawer.props("semanticEvidence")).toEqual([
      expect.objectContaining({
        resume_text: expect.stringContaining("multilingual recommendation"),
      }),
    ])
  })

  it("renders matched skill evidence with a human-readable source", async () => {
    prepare()
    const wrapper = mount(MatchReportPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    const evidence = wrapper.get('[data-testid="skill-evidence-Python"]')
    expect(evidence.text()).toContain("Verified · 工作经历")
    expect(evidence.text()).toContain("Built a production Python API")
    expect(wrapper.get('[data-testid="evidence-coverage"]').text()).toContain("25%")
  })

  it("renders explicit empty states when no skill conclusions are available", async () => {
    const empty = matchReport()
    empty.matched_skills = []
    empty.partial_skills = []
    empty.missing_skills = []
    empty.evidence_items = []
    empty.evidence_coverage = {
      total_requirements: 0,
      verified: 0,
      partially_supported: 0,
      missing: 0,
      unknown: 0,
      coverage_percent: 0,
    }
    prepare(empty)
    const wrapper = mount(MatchReportPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    expect(wrapper.text().match(/此分类没有项目。/g)).toHaveLength(4)
    expect(wrapper.get('[data-testid="evidence-coverage"]').text()).toContain("0%")
  })

  it("states that semantic relevance cannot cancel a blocking conflict", async () => {
    prepare(matchReport({ blocking: true, hybrid: true }))
    const wrapper = mount(MatchReportPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="semantic-evidence-section"]').text()).toContain(
      "语义相关性不能抵消资格冲突",
    )
    expect(wrapper.get('[data-testid="recommendation"]').text()).toContain("不建议申请")
  })
})
