import { describe, expect, it } from "vitest"

import { matchReport } from "@/../tests/unit/match-fixture"
import {
  groupSkillMatches,
  recommendationLabel,
  requirementCompleteness,
} from "@/utils/matching"

describe("matching presenters", () => {
  it("maps backend recommendation levels without score recalculation", () => {
    expect(recommendationLabel("STRONGLY_RECOMMENDED")).toBe("强烈推荐")
    expect(recommendationLabel("RECOMMENDED")).toBe("推荐申请")
    expect(recommendationLabel("CONSIDER")).toBe("可以考虑")
    expect(recommendationLabel("HIGH_RISK")).toBe("风险较高")
    expect(recommendationLabel("NOT_RECOMMENDED")).toBe("不建议申请")
  })

  it("keeps MATCHED, PARTIAL, MISSING and UNKNOWN separate", () => {
    const groups = groupSkillMatches(matchReport())
    expect(groups.MATCHED.map((item) => item.normalized_name)).toEqual(["Python"])
    expect(groups.PARTIAL.map((item) => item.normalized_name)).toEqual(["SQL"])
    expect(groups.MISSING.map((item) => item.normalized_name)).toEqual(["Kubernetes"])
    expect(groups.UNKNOWN.map((item) => item.normalized_name)).toEqual(["NovelDB"])
  })

  it("counts requirement snapshot states and flags incomplete jobs", () => {
    const completeness = requirementCompleteness(matchReport({ incomplete: true }))
    expect(completeness.incomplete).toBe(true)
    expect(completeness.notProvided).toBe(2)
    expect(completeness.unknown).toBe(2)
  })
})
