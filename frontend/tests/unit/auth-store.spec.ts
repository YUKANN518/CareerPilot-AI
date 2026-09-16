import { createPinia, setActivePinia } from "pinia"
import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  getCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
} from "@/api/auth"
import { useAuthStore } from "@/stores/auth"
import type { AuthSession, User } from "@/types/auth"

vi.mock("@/api/auth", () => ({
  getCurrentUser: vi.fn(),
  loginUser: vi.fn(),
  logoutUser: vi.fn(),
  registerUser: vi.fn(),
}))

const user: User = {
  id: 1,
  email: "user@example.com",
  role: "USER",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  profile: null,
}

const session: AuthSession = {
  user,
  tokens: {
    access_token: "access-token",
    refresh_token: "refresh-token",
    token_type: "bearer",
    expires_in: 1800,
  },
}

describe("auth store", () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.mocked(getCurrentUser).mockReset()
    vi.mocked(loginUser).mockReset()
    vi.mocked(logoutUser).mockReset()
    vi.mocked(registerUser).mockReset()
  })

  it("applies a session after registration", async () => {
    vi.mocked(registerUser).mockResolvedValue(session)
    const store = useAuthStore()

    await store.register({
      email: "user@example.com",
      password: "StrongPassword123!",
      display_name: "User",
    })

    expect(store.isAuthenticated).toBe(true)
    expect(store.user?.email).toBe("user@example.com")
    expect(localStorage.getItem("careerpilot.tokens")).toContain("access-token")
  })

  it("clears local state even when remote logout fails", async () => {
    vi.mocked(loginUser).mockResolvedValue(session)
    vi.mocked(logoutUser).mockRejectedValue(new Error("network"))
    const store = useAuthStore()
    await store.login({
      email: "user@example.com",
      password: "StrongPassword123!",
    })

    await expect(store.logout()).resolves.toBeUndefined()

    expect(store.isAuthenticated).toBe(false)
    expect(localStorage.getItem("careerpilot.tokens")).toBeNull()
  })
})
