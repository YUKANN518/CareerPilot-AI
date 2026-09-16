import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { uploadResume } from "@/api/resumes"
import ResumeUploadPage from "@/pages/ResumeUploadPage.vue"

const push = vi.fn()

vi.mock("vue-router", () => ({
  useRouter: () => ({ push }),
}))
vi.mock("@/api/resumes", () => ({
  uploadResume: vi.fn(),
}))
vi.mock("@/api/auth", () => ({
  getApiErrorMessage: () => "上传失败",
}))

describe("resume upload page", () => {
  beforeEach(() => {
    push.mockReset()
    vi.mocked(uploadResume).mockReset()
  })

  it("rejects unsupported files before making a request", async () => {
    const wrapper = mount(ResumeUploadPage, {
      global: { stubs: { RouterLink: true } },
    })
    const input = wrapper.get('[data-testid="resume-file"]')
    Object.defineProperty(input.element, "files", {
      value: [new File(["text"], "resume.txt", { type: "text/plain" })],
      configurable: true,
    })

    await input.trigger("change")
    await wrapper.get("form").trigger("submit")

    expect(wrapper.text()).toContain("仅支持 PDF 或 DOCX")
    expect(uploadResume).not.toHaveBeenCalled()
  })

  it("shows upload progress and routes to the real resume status", async () => {
    vi.mocked(uploadResume).mockImplementation(async (_file, onProgress) => {
      onProgress?.(62)
      return {
        duplicate: false,
        resume: {
          id: 42,
          title: "sample",
          status: "UPLOADED",
          file: {
            id: 1,
            original_name: "sample.pdf",
            mime_type: "application/pdf",
            size_bytes: 12,
            sha256: "a".repeat(64),
            file_format: "pdf",
          },
          parse_attempts: 0,
          extracted_at: null,
          parsed_at: null,
          confirmed_at: null,
          created_at: "2026-01-01T00:00:00Z",
          updated_at: "2026-01-01T00:00:00Z",
          version_count: 0,
          last_error_code: null,
          last_error_message: null,
        },
      }
    })
    const wrapper = mount(ResumeUploadPage, {
      global: { stubs: { RouterLink: true } },
    })
    const input = wrapper.get('[data-testid="resume-file"]')
    const pdf = new File(["%PDF-sample"], "sample.pdf", { type: "application/pdf" })
    Object.defineProperty(input.element, "files", {
      value: [pdf],
      configurable: true,
    })

    await input.trigger("change")
    await wrapper.get("form").trigger("submit")
    await flushPromises()

    expect(wrapper.text()).toContain("上传进度：62%")
    expect(push).toHaveBeenCalledWith({
      name: "resume-status",
      params: { resumeId: 42 },
    })
  })
})
