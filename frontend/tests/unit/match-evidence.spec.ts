import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"

import MatchEvidenceDrawer from "@/components/domain/MatchEvidenceDrawer.vue"
import { matchReport } from "@/../tests/unit/match-fixture"

describe("MatchEvidenceDrawer", () => {
  it("shows resume, job and rule source positions", () => {
    const evidence = matchReport().evidence_items
    const wrapper = mount(MatchEvidenceDrawer, {
      props: { open: true, title: "Python 证据", evidence },
      global: { stubs: { teleport: true } },
    })
    expect(wrapper.text()).toContain("Built a production Python API.")
    expect(wrapper.text()).toContain("第 1 页")
    expect(wrapper.text()).toContain("job_skills")
    expect(wrapper.text()).toContain("EXACT_NORMALIZED_SKILL")
  })

  it("states that no traceable evidence exists instead of generating an explanation", () => {
    const wrapper = mount(MatchEvidenceDrawer, {
      props: { open: true, title: "无证据", evidence: [] },
      global: { stubs: { teleport: true } },
    })
    expect(wrapper.get('[data-testid="no-evidence"]').text()).toContain(
      "未找到可追溯证据",
    )
  })
})
