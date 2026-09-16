import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"

import ResumeProfileEditor from "@/components/domain/ResumeProfileEditor.vue"
import { resumeProfile } from "./resume-fixture"

describe("resume profile editor", () => {
  it("shows low-confidence evidence and edits a structured field", async () => {
    const profile = resumeProfile()
    const wrapper = mount(ResumeProfileEditor, {
      props: { modelValue: profile },
    })

    expect(wrapper.text()).toContain("低置信度 50%")
    expect(wrapper.text()).toContain("Source evidence")

    await wrapper.get("#field-姓名").setValue("Edited Candidate")

    expect(profile.basic_info.full_name.value).toBe("Edited Candidate")
    expect(profile.basic_info.full_name.needs_confirmation).toBe(false)
  })

  it("adds and deletes missing structured entries", async () => {
    const profile = resumeProfile()
    const wrapper = mount(ResumeProfileEditor, {
      props: { modelValue: profile },
    })

    const addEducationButton = wrapper
      .findAll("button")
      .find((button) => button.text() === "增加教育经历")
    await addEducationButton?.trigger("click")

    expect(profile.education).toHaveLength(1)
    expect(wrapper.text()).toContain("教育描述")
  })
})
