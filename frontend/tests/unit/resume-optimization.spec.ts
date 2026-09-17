import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { ResumeOptimization } from "@/types/resume-optimization"

const listOptimizations = vi.hoisted(() => vi.fn())
const getOptimization = vi.hoisted(() => vi.fn())
const confirmOptimization = vi.hoisted(() => vi.fn())
const retryOptimization = vi.hoisted(() => vi.fn())
const createVersion = vi.hoisted(() => vi.fn())
const push = vi.hoisted(() => vi.fn())

vi.mock("@/api/resume-optimizations", () => ({
  listResumeOptimizations: listOptimizations,
  getResumeOptimization: getOptimization,
  confirmResumeOptimization: confirmOptimization,
  retryResumeOptimization: retryOptimization,
  createResumeOptimizationVersion: createVersion,
}))
vi.mock("@/api/errors", () => ({
  getApiErrorInfo: (error: unknown) => {
    const message = error instanceof Error ? error.message : "未知错误"
    const kind = message.includes("无权") ? "forbidden" : "unknown"
    return {
      kind,
      status: null,
      code: "UNKNOWN_ERROR",
      message,
      retryable: false,
      fieldErrors: {},
    }
  },
  getApiErrorMessage: (error: unknown) =>
    error instanceof Error ? error.message : "请求失败",
}))
vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { optimizationId: "101" } }),
  useRouter: () => ({ push }),
  RouterLink: {
    name: "RouterLink",
    props: ["to"],
    template: '<a><slot /></a>',
  },
}))

import ResumeOptimizationsPage from "@/pages/ResumeOptimizationsPage.vue"
import ResumeOptimizationDetailPage from "@/pages/ResumeOptimizationDetailPage.vue"

function makeOptimization(
  overrides: Partial<ResumeOptimization> = {},
): ResumeOptimization {
  return {
    id: 101,
    user_id: 1,
    resume_version_id: 12,
    job_id: 31,
    match_report_id: 41,
    status: "DRAFT",
    summary: "针对岗位调整项目顺序与关键词",
    sections: [
      {
        section: "项目经历",
        source_section_id: "project-1",
        original_text: "Built a Python service.",
        suggested_text: "Built a Python FastAPI service handling 1k QPS.",
        reason: "突出 FastAPI 关键词，匹配岗位摘要要求。",
        related_job_requirement: "FastAPI experience",
        evidence_keys: ["resume-evidence-1"],
        change_type: "REWRITE",
        accepted: false,
        edited_text: null,
      },
      {
        section: "技能总结",
        source_section_id: "skill-1",
        original_text: "Python, JavaScript",
        suggested_text: "Python, JavaScript, TypeScript",
        reason: "技能顺序按岗位优先级调整。",
        related_job_requirement: "TypeScript",
        evidence_keys: ["resume-evidence-2"],
        change_type: "REORDER",
        accepted: false,
        edited_text: null,
      },
    ],
    keyword_suggestions: [
      {
        keyword: "FastAPI",
        reason: "岗位摘要明确提及",
        evidence_keys: ["resume-evidence-1"],
      },
    ],
    missing_evidence_warnings: ["未找到量化数据证据"],
    fabrication_warnings: [],
    job_information_warning:
      "当前优化建议仅基于公开岗位摘要生成，不能覆盖原平台完整职位要求。",
    is_human_confirmed: false,
    workflow_run_id: "wf-run-abc",
    workflow_version: "resume-optimization-v1",
    provider: "dify",
    latency_ms: 7321,
    error_code: null,
    error_message: null,
    created_at: "2026-07-22T10:00:00Z",
    updated_at: "2026-07-22T10:00:05Z",
    ...overrides,
  }
}

function mountDetail() {
  return mount(ResumeOptimizationDetailPage, {
    global: {
      stubs: {
        RouterLink: { template: "<a><slot /></a>" },
        ForbiddenState: { template: '<div data-testid="forbidden-state" />' },
      },
    },
  })
}

describe("resume optimizations list page", () => {
  beforeEach(() => {
    listOptimizations.mockReset()
  })

  it("shows loading skeleton then empty state when no records exist", async () => {
    listOptimizations.mockResolvedValue({ items: [], total: 0, offset: 0, limit: 50 })
    const wrapper = mount(ResumeOptimizationsPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()
    expect(listOptimizations).toHaveBeenCalledWith({ offset: 0, limit: 50 })
    expect(wrapper.text()).toContain("还没有优化记录")
  })

  it("renders optimizations with summary, status and section count", async () => {
    const opt = makeOptimization()
    listOptimizations.mockResolvedValue({
      items: [opt],
      total: 1,
      offset: 0,
      limit: 50,
    })
    const wrapper = mount(ResumeOptimizationsPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()
    expect(wrapper.text()).toContain("针对岗位调整项目顺序与关键词")
    expect(wrapper.text()).toContain("DRAFT")
    expect(wrapper.text()).toContain("2 个章节建议")
    expect(wrapper.text()).toContain("服务提供方：dify")
  })

  it("shows error state when the API call fails", async () => {
    listOptimizations.mockRejectedValue(new Error("网络错误"))
    const wrapper = mount(ResumeOptimizationsPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()
    expect(wrapper.text()).toContain("网络错误")
  })
})

describe("resume optimization detail page", () => {
  beforeEach(() => {
    getOptimization.mockReset()
    confirmOptimization.mockReset()
    retryOptimization.mockReset()
    createVersion.mockReset()
    push.mockReset()
  })

  it("renders original vs suggested text comparison and evidence keys", async () => {
    getOptimization.mockResolvedValue(makeOptimization())
    const wrapper = mountDetail()
    await flushPromises()

    const cards = wrapper.findAll('[data-testid="optimization-section-card"]')
    expect(cards).toHaveLength(2)
    expect(wrapper.text()).toContain("Built a Python service.")
    expect(wrapper.text()).toContain("Built a Python FastAPI service handling 1k QPS.")
    expect(wrapper.text()).toContain("resume-evidence-1")
    expect(wrapper.text()).toContain("FastAPI experience")
  })

  it("displays the summary-only job information warning", async () => {
    getOptimization.mockResolvedValue(makeOptimization())
    const wrapper = mountDetail()
    await flushPromises()
    expect(
      wrapper.get('[data-testid="job-information-warning"]').text(),
    ).toContain("当前优化建议仅基于公开岗位摘要生成")
  })

  it("accepts and rejects section suggestions independently", async () => {
    getOptimization.mockResolvedValue(makeOptimization())
    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('[data-testid="accept-section-project-1"]').trigger("click")
    await wrapper.get('[data-testid="reject-section-skill-1"]').trigger("click")

    expect(wrapper.text()).toContain("接受")
    // After accepting project-1, suggested text remains visible
    expect(wrapper.text()).toContain("Built a Python FastAPI service")
  })

  it("edits a section suggestion inline and saves", async () => {
    getOptimization.mockResolvedValue(makeOptimization())
    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('[data-testid="edit-section-project-1"]').trigger("click")
    const textarea = wrapper.get('[data-testid="edit-textarea"]')
    await textarea.setValue("Built a Python FastAPI service with observability.")
    await wrapper.get('[data-testid="save-edit-button"]').trigger("click")

    expect(wrapper.text()).toContain(
      "Built a Python FastAPI service with observability.",
    )
  })

  it("cancels editing without saving changes", async () => {
    getOptimization.mockResolvedValue(makeOptimization())
    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('[data-testid="edit-section-project-1"]').trigger("click")
    await wrapper
      .get('[data-testid="edit-textarea"]')
      .setValue("Discarded content")
    await wrapper.get('[data-testid="cancel-edit-button"]').trigger("click")

    expect(wrapper.find('[data-testid="edit-textarea"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain("Discarded content")
  })

  it("confirms optimization by submitting accept/reject state", async () => {
    const original = makeOptimization()
    getOptimization.mockResolvedValue(original)
    const confirmed = makeOptimization({
      status: "CONFIRMED",
      is_human_confirmed: true,
      sections: original.sections.map((s, idx) => ({
        ...s,
        accepted: idx === 0,
        edited_text: null,
      })),
    })
    confirmOptimization.mockResolvedValue(confirmed)
    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('[data-testid="accept-section-project-1"]').trigger("click")
    await wrapper.get('[data-testid="confirm-optimization-button"]').trigger("click")
    await flushPromises()

    expect(confirmOptimization).toHaveBeenCalledWith(101, {
      sections: [
        {
          source_section_id: "project-1",
          accepted: true,
          edited_text: null,
        },
        {
          source_section_id: "skill-1",
          accepted: false,
          edited_text: null,
        },
      ],
      attest_truth: false,
    })
    expect(wrapper.text()).toContain("CONFIRMED")
  })

  it("shows a fabrication error and stays DRAFT when an edit introduces a missing skill", async () => {
    const original = makeOptimization()
    getOptimization.mockResolvedValue(original)
    confirmOptimization.mockRejectedValue(
      new Error(
        "edited_text for section '项目经历' must not introduce the missing skill 'SQL'",
      ),
    )
    const wrapper = mountDetail()
    await flushPromises()

    // Edit the section to introduce a missing skill, then confirm.
    await wrapper.get('[data-testid="edit-section-project-1"]').trigger("click")
    await wrapper
      .get('[data-testid="edit-textarea"]')
      .setValue("Built services. Now expert in SQL.")
    await wrapper.get('[data-testid="save-edit-button"]').trigger("click")
    // The attestation checkbox must be checked before the confirm button
    // is enabled (edited_text present → hasAnyEdit = true).
    await wrapper.get('[data-testid="attest-truth-checkbox"]').setValue(true)
    await wrapper.get('[data-testid="confirm-optimization-button"]').trigger("click")
    await flushPromises()

    // The confirm payload carries the edited_text the user typed.
    expect(confirmOptimization).toHaveBeenCalledWith(101, {
      sections: [
        {
          source_section_id: "project-1",
          accepted: true,
          edited_text: "Built services. Now expert in SQL.",
        },
        {
          source_section_id: "skill-1",
          accepted: false,
          edited_text: null,
        },
      ],
      attest_truth: true,
    })
    // The server-side rejection surfaces to the user and the record
    // is NOT promoted to CONFIRMED (it stays DRAFT).
    expect(wrapper.text()).toContain("must not introduce the missing skill 'SQL'")
    expect(wrapper.text()).toContain("DRAFT")
    expect(wrapper.text()).not.toContain("CONFIRMED")
  })

  it("disables confirm button when edited_text present but attestation not checked", async () => {
    getOptimization.mockResolvedValue(makeOptimization())
    const wrapper = mountDetail()
    await flushPromises()

    // Edit a section to introduce edited_text.
    await wrapper.get('[data-testid="edit-section-project-1"]').trigger("click")
    await wrapper
      .get('[data-testid="edit-textarea"]')
      .setValue("Built a Python service with extra detail.")
    await wrapper.get('[data-testid="save-edit-button"]').trigger("click")

    // The attestation section is visible but the checkbox is unchecked.
    expect(wrapper.find('[data-testid="attest-truth-section"]').exists()).toBe(true)
    const confirmButton = wrapper.get('[data-testid="confirm-optimization-button"]')
    expect((confirmButton.element as HTMLButtonElement).disabled).toBe(true)
  })

  it("enables confirm button after checking attestation checkbox with edits", async () => {
    const original = makeOptimization()
    getOptimization.mockResolvedValue(original)
    const confirmed = makeOptimization({
      status: "CONFIRMED",
      is_human_confirmed: true,
    })
    confirmOptimization.mockResolvedValue(confirmed)
    const wrapper = mountDetail()
    await flushPromises()

    // Edit a section.
    await wrapper.get('[data-testid="edit-section-project-1"]').trigger("click")
    await wrapper
      .get('[data-testid="edit-textarea"]')
      .setValue("Built a Python service with extra detail.")
    await wrapper.get('[data-testid="save-edit-button"]').trigger("click")

    // Confirm button is disabled before checking attestation.
    const confirmButton = wrapper.get('[data-testid="confirm-optimization-button"]')
    expect((confirmButton.element as HTMLButtonElement).disabled).toBe(true)

    // Check attestation → button becomes enabled.
    await wrapper.get('[data-testid="attest-truth-checkbox"]').setValue(true)
    expect((confirmButton.element as HTMLButtonElement).disabled).toBe(false)

    // Confirm sends attest_truth: true.
    await confirmButton.trigger("click")
    await flushPromises()
    expect(confirmOptimization).toHaveBeenCalledWith(
      101,
      expect.objectContaining({ attest_truth: true }),
    )
    expect(wrapper.text()).toContain("CONFIRMED")
  })

  it("does not show create-version button before confirmation", async () => {
    getOptimization.mockResolvedValue(makeOptimization({ status: "DRAFT" }))
    const wrapper = mountDetail()
    await flushPromises()
    expect(wrapper.find('[data-testid="create-version-button"]').exists()).toBe(false)
  })

  it("creates a new resume version after confirmation", async () => {
    const confirmed = makeOptimization({
      status: "CONFIRMED",
      is_human_confirmed: true,
    })
    getOptimization.mockResolvedValue(confirmed)
    createVersion.mockResolvedValue({
      resume_version: {
        id: 200,
        resume_id: 5,
        version_number: 2,
        parent_version_id: 12,
        is_current: false,
        is_confirmed: false,
      },
      applied_section_count: 1,
      parent_version_id: 12,
    })
    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('[data-testid="create-version-button"]').trigger("click")
    await flushPromises()

    expect(createVersion).toHaveBeenCalledWith(101)
    expect(push).toHaveBeenCalledWith({
      name: "resume-version",
      params: { resumeId: 5, versionId: 200 },
    })
  })

  it("retries generation when status is FAILED", async () => {
    const failed = makeOptimization({
      status: "FAILED",
      error_code: "DIFY_EMPTY_OUTPUT",
      error_message: "Dify returned empty output",
    })
    getOptimization.mockResolvedValue(failed)
    const retried = makeOptimization({ id: 102, status: "DRAFT" })
    retryOptimization.mockResolvedValue(retried)
    const wrapper = mountDetail()
    await flushPromises()

    expect(wrapper.text()).toContain("Dify returned empty output")
    await wrapper.get('[data-testid="retry-optimization-button"]').trigger("click")
    await flushPromises()

    expect(retryOptimization).toHaveBeenCalledWith(101)
    expect(push).toHaveBeenCalledWith({
      name: "resume-optimization-detail",
      params: { optimizationId: 102 },
    })
  })

  it("shows error message when retry fails", async () => {
    const failed = makeOptimization({ status: "FAILED" })
    getOptimization.mockResolvedValue(failed)
    retryOptimization.mockRejectedValue(new Error("重试失败"))
    const wrapper = mountDetail()
    await flushPromises()

    await wrapper.get('[data-testid="retry-optimization-button"]').trigger("click")
    await flushPromises()

    expect(wrapper.text()).toContain("重试失败")
  })
})
