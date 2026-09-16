import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  confirmResume,
  getParseResult,
  getResume,
  updateParseResult,
} from "@/api/resumes"
import ResumeConfirmPage from "@/pages/ResumeConfirmPage.vue"
import { resumeProfile } from "./resume-fixture"

const push = vi.fn()

vi.mock("vue-router", () => ({
  onBeforeRouteLeave: vi.fn(),
  useRoute: () => ({ params: { resumeId: "9" } }),
  useRouter: () => ({ push }),
}))
vi.mock("@/api/resumes", () => ({
  getParseResult: vi.fn(),
  getResume: vi.fn(),
  updateParseResult: vi.fn(),
  confirmResume: vi.fn(),
}))
vi.mock("@/api/auth", () => ({
  getApiErrorMessage: () => "请求失败",
}))

describe("resume confirmation page", () => {
  beforeEach(() => {
    push.mockReset()
    vi.mocked(getParseResult).mockResolvedValue({
      resume_id: 9,
      status: "NEEDS_CONFIRMATION",
      result: resumeProfile(),
      parse_attempts: 1,
      low_confidence_count: 1,
      error_code: null,
      error_message: null,
    })
    vi.mocked(getResume).mockResolvedValue({
      id: 9,
      title: "Sample Resume",
      status: "NEEDS_CONFIRMATION",
      file: {
        id: 1,
        original_name: "sample.pdf",
        mime_type: "application/pdf",
        size_bytes: 128,
        sha256: "a".repeat(64),
        file_format: "pdf",
      },
      parse_attempts: 1,
      extracted_at: "2026-01-01T00:00:00Z",
      parsed_at: "2026-01-01T00:00:00Z",
      confirmed_at: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
      version_count: 0,
      last_error_code: null,
      last_error_message: null,
    })
    vi.mocked(updateParseResult).mockImplementation(async (_resumeId, profile) => ({
      resume_id: 9,
      status: "NEEDS_CONFIRMATION",
      result: profile,
      parse_attempts: 1,
      low_confidence_count: 0,
      error_code: null,
      error_message: null,
    }))
    vi.mocked(confirmResume).mockResolvedValue({
      id: 77,
      resume_id: 9,
      version_number: 1,
      structured_data: resumeProfile(),
      is_current: true,
      is_confirmed: true,
      created_at: "2026-01-01T00:00:00Z",
    })
  })

  it("displays parsed fields and confirms an immutable version", async () => {
    const wrapper = mount(ResumeConfirmPage, {
      global: { stubs: { RouterLink: true } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain("1 个字段需要核对")
    expect(wrapper.get("#field-姓名").element).toHaveProperty(
      "value",
      "Sample Candidate",
    )

    await wrapper.get("#field-姓名").setValue("Confirmed Candidate")
    const requestConfirmButton = wrapper
      .findAll("button")
      .find((button) => button.text().trim() === "确认简历" && !button.element.closest("dialog"))
    await requestConfirmButton?.trigger("click")
    expect(wrapper.get("dialog").attributes("open")).toBeDefined()
    const dialogConfirmButton = wrapper
      .get("dialog")
      .findAll("button")
      .find((button) => button.text().trim() === "确认简历")
    await dialogConfirmButton?.trigger("click")
    await flushPromises()

    expect(updateParseResult).toHaveBeenCalledWith(
      9,
      expect.objectContaining({
        basic_info: expect.objectContaining({
          full_name: expect.objectContaining({ value: "Confirmed Candidate" }),
        }),
      }),
    )
    expect(confirmResume).toHaveBeenCalledWith(9)
    expect(push).toHaveBeenCalledWith({
      name: "resume-version",
      params: { versionId: 77 },
    })
  })
})
