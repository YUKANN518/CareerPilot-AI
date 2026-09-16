import { flushPromises, mount } from "@vue/test-utils"
import { describe, expect, it, vi } from "vitest"

const board = vi.hoisted(() => vi.fn())
const updateStatus = vi.hoisted(() => vi.fn())

vi.mock("@/api/applications", () => ({
  applicationService: {
    board,
    updateStatus,
    update: vi.fn(),
    delete: vi.fn(),
  },
}))

import ApplicationsPage from "@/pages/ApplicationsPage.vue"

const emptyColumns = {
  SAVED: [],
  APPLIED: [],
  INTERVIEW: [],
  OFFER: [],
  REJECTED: [],
}

describe("applications board", () => {
  it("renders real application cards and persists a drag status move", async () => {
    board
      .mockResolvedValueOnce({
        columns: {
          ...emptyColumns,
          APPLIED: [
            {
              id: 12,
              user_id: 1,
              job_id: 30,
              status: "APPLIED",
              notes: null,
              next_action_at: null,
              job: {
                id: 30,
                title: "Backend Engineer",
                company: "CareerPilot",
                location: "Hong Kong",
                source_url: null,
                employment_type: "FULL_TIME",
                source_name: "Official",
                is_favorite: false,
              },
              status_history: [],
              created_at: "2026-07-20T00:00:00Z",
              updated_at: "2026-07-20T00:00:00Z",
            },
          ],
        },
        counts: { ...Object.fromEntries(Object.keys(emptyColumns).map((key) => [key, 0])), APPLIED: 1 },
      })
      .mockResolvedValueOnce({ columns: emptyColumns, counts: Object.fromEntries(Object.keys(emptyColumns).map((key) => [key, 0])) })
    updateStatus.mockResolvedValue({})

    const wrapper = mount(ApplicationsPage, {
      global: { stubs: { RouterLink: { template: "<a><slot /></a>" } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain("Backend Engineer")
    await wrapper.get('[draggable="true"]').trigger("dragstart")
    await wrapper.get('[data-testid="application-column-INTERVIEW"]').trigger("drop")
    await flushPromises()

    expect(updateStatus).toHaveBeenCalledWith(12, { status: "INTERVIEW" })
  })
})
