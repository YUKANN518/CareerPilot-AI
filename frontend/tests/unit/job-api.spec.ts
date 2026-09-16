import { beforeEach, describe, expect, it, vi } from "vitest"

const apiClient = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
}))

vi.mock("@/api/client", () => ({ apiClient }))

import { jobApi } from "@/api/jobs"

describe("job API mappings", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("maps the real job list response and forwards supported filters", async () => {
    const payload = {
      items: [
        {
          id: 1,
          title: "Backend Engineer",
          company: "CareerPilot",
        },
      ],
      total: 1,
      offset: 0,
      limit: 20,
    }
    apiClient.get.mockResolvedValue({
      data: { success: true, data: payload, message: "ok" },
    })

    await expect(
      jobApi.listJobs({
        search: "Backend",
        source_name: "Official",
        source_id: 4,
        sort: "published_desc",
      }),
    ).resolves.toBe(payload)
    expect(apiClient.get).toHaveBeenCalledWith("/jobs", {
      params: expect.objectContaining({
        search: "Backend",
        source_name: "Official",
        source_id: 4,
        sort: "published_desc",
      }),
    })
  })

})
