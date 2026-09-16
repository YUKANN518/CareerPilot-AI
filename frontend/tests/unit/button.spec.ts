import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"

import { Button } from "@/components/ui/button"

describe("Button", () => {
  it("renders content and forwards native state", () => {
    const wrapper = mount(Button, {
      props: { disabled: true },
      slots: { default: "保存" },
    })

    expect(wrapper.text()).toBe("保存")
    expect(wrapper.get("button").attributes("disabled")).toBeDefined()
  })
})
