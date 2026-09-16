import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"

import MatchHistoryList from "@/components/domain/MatchHistoryList.vue"
import { matchReport } from "@/../tests/unit/match-fixture"

describe("MatchHistoryList", () => {
  it("distinguishes legacy and hybrid reports while tolerating empty legacy fields", () => {
    const legacy = matchReport()
    const hybrid = { ...matchReport({ hybrid: true }), id: 42 }
    const wrapper = mount(MatchHistoryList, {
      props: {
        reports: [legacy, hybrid],
        compact: true,
      },
      global: {
        stubs: { RouterLink: { template: "<a><slot /></a>" } },
      },
    })

    expect(wrapper.text()).toContain("deterministic-v1")
    expect(wrapper.text()).toContain("hybrid-v1")
    expect(wrapper.text()).toContain("实验")
    expect(wrapper.text()).toContain("旧报告未记录")
    expect(wrapper.text()).toContain("87.25 / — / — / 87.25")
    expect(wrapper.text()).toContain("87.25 / 82 / 85.68 / 85.68")
  })
})
