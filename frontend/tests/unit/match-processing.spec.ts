import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"

const get = vi.hoisted(() => vi.fn())
const connect = vi.hoisted(() => vi.fn())
const retry = vi.hoisted(() => vi.fn())
const confirm = vi.hoisted(() => vi.fn())
const push = vi.hoisted(() => vi.fn())
const replace = vi.hoisted(() => vi.fn())
const close = vi.hoisted(() => vi.fn())

vi.mock("@/services/matching", () => ({
  matchRunService: { get, connect, retry, confirm },
}))
vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { runId: "81" } }),
  useRouter: () => ({ push, replace }),
}))

import MatchProcessingPage from "@/pages/MatchProcessingPage.vue"
import type { MatchRun } from "@/types/matching"

function matchRun(overrides: Partial<MatchRun> = {}): MatchRun {
  const nodes = [
    "load_inputs",
    "deterministic_matching",
    "semantic_retrieval",
    "blocking_risk_check",
    "save_report",
    "human_review",
  ]
  return {
    run_id: 81,
    user_id: 1,
    resume_version_id: 12,
    job_id: 31,
    scoring_version: "deterministic-v1.1",
    status: "RUNNING",
    current_node: "load_inputs",
    node_status: "RUNNING",
    completed_nodes: [],
    rule_score: null,
    semantic_score: null,
    hybrid_score: null,
    blocking_risks: [],
    report_id: null,
    error_code: null,
    error_message: null,
    waiting_for_user: false,
    retry_count: 0,
    started_at: "2026-07-18T00:00:00Z",
    finished_at: null,
    duration_ms: null,
    steps: nodes.map((node_name) => ({
      node_name,
      status: "PENDING",
      retry_count: 0,
      started_at: null,
      finished_at: null,
      duration_ms: null,
      summary: {},
      error_message: null,
    })),
    ...overrides,
  }
}

describe("MatchProcessingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks()
    connect.mockResolvedValue(close)
  })

  it("connects SSE and applies node completion and human review events", async () => {
    get.mockResolvedValue(matchRun())
    const wrapper = mount(MatchProcessingPage)
    await flushPromises()
    const options = connect.mock.calls[0][1]
    options.onEvent({
      event: "node_completed",
      node: "load_inputs",
      status: "SUCCEEDED",
      duration_ms: 12,
      summary: { inputs_valid: true },
    })
    options.onEvent({
      event: "waiting_for_user",
      node: "human_review",
      status: "WAITING_REVIEW",
    })
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-testid="node-load_inputs"]').text()).toContain("12 ms")
    expect(wrapper.text()).toContain("确认并打开报告")
    wrapper.unmount()
    expect(close).toHaveBeenCalled()
  })

  it("retries a failed node and confirms a waiting run", async () => {
    get.mockResolvedValue(matchRun({ status: "FAILED" }))
    retry.mockResolvedValue(matchRun())
    const wrapper = mount(MatchProcessingPage)
    await flushPromises()
    await wrapper.get("button").trigger("click")
    expect(retry).toHaveBeenCalledWith(81)

    get.mockResolvedValue(matchRun({ status: "WAITING_REVIEW", waiting_for_user: true }))
    confirm.mockResolvedValue(matchRun({ status: "SUCCEEDED", report_id: 41 }))
    wrapper.unmount()
    const waitingWrapper = mount(MatchProcessingPage)
    await flushPromises()
    await waitingWrapper.get("button").trigger("click")
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith(81)
    expect(push).toHaveBeenCalledWith({
      name: "match-report",
      params: { matchId: 41 },
    })
  })

  it("shows reconnect exhaustion without fake timers", async () => {
    get.mockResolvedValue(matchRun())
    const wrapper = mount(MatchProcessingPage)
    await flushPromises()
    connect.mock.calls[0][1].onDisconnected(3)
    connect.mock.calls[0][1].onExhausted()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain("第 3 次自动重连")
    expect(wrapper.text()).toContain("连续中断 3 次")
  })
})
