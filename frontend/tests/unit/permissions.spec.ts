import { describe, expect, it } from "vitest"

import { hasRequiredRole } from "@/router/permissions"
import { router } from "@/router"

describe("hasRequiredRole", () => {
  it("allows routes without role restrictions", () => {
    expect(hasRequiredRole("USER", undefined)).toBe(true)
  })

  it("enforces admin-only routes", () => {
    expect(hasRequiredRole("USER", ["ADMIN"])).toBe(false)
    expect(hasRequiredRole("ADMIN", ["ADMIN"])).toBe(true)
  })

  it("marks the independent admin route as authenticated and ADMIN-only", () => {
    const adminRoute = router.resolve({ name: "admin-knowledge-documents" })

    expect(adminRoute.meta.requiresAuth).toBe(true)
    expect(adminRoute.meta.roles).toEqual(["ADMIN"])
    expect(hasRequiredRole("USER", adminRoute.meta.roles)).toBe(false)
  })
})
