import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"

const errorKind = vi.hoisted(() => ({ value: "forbidden" }))
const get = vi.hoisted(() => vi.fn())

vi.mock("@/services/matching", () => ({
  matchService: {
    get,
    details: vi.fn(),
    recalculate: vi.fn(),
  },
}))
vi.mock("@/api/errors", () => ({
  getApiErrorInfo: () => ({
    kind: errorKind.value,
    message:
      errorKind.value === "forbidden"
        ? "You do not have access to this report."
        : "The report does not exist.",
    code: errorKind.value === "forbidden" ? "FORBIDDEN" : "NOT_FOUND",
  }),
}))
vi.mock("@/api/jobs", () => ({ getJob: vi.fn() }))
vi.mock("@/api/resumes", () => ({
  getResumeVersion: vi.fn(),
  listResumeVersionSkills: vi.fn(),
}))
vi.mock("@/components/domain/MatchDimensionChart.vue", () => ({
  default: { template: '<div data-testid="dimension-chart" />' },
}))
vi.mock("vue-router", () => ({
  useRoute: () => ({ params: { matchId: "404" } }),
  useRouter: () => ({ push: vi.fn() }),
}))

import MatchReportPage from "@/pages/MatchReportPage.vue"

describe("match report error states", () => {
  beforeEach(() => {
    get.mockReset()
    get.mockRejectedValue(new Error("request failed"))
  })

  it("renders a dedicated forbidden state for a 403 response", async () => {
    errorKind.value = "forbidden"
    const wrapper = mount(MatchReportPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="forbidden-state"]').text()).toContain(
      "当前账号无权查看其他用户的匹配报告。",
    )
  })

  it("renders a dedicated not-found state for a 404 response", async () => {
    errorKind.value = "not-found"
    const wrapper = mount(MatchReportPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="not-found-state"]').text()).toContain(
      "The report does not exist.",
    )
  })
})
