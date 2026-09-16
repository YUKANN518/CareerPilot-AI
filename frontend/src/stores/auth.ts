import { defineStore } from "pinia"
import { computed, ref } from "vue"

import {
  getCurrentUser,
  loginUser,
  logoutUser,
  registerUser,
} from "@/api/auth"
import { clearTokens, readTokens, writeTokens } from "@/api/token-storage"
import type { LoginInput, RegisterInput, TokenPair, User } from "@/types/auth"

export const useAuthStore = defineStore("auth", () => {
  const user = ref<User | null>(null)
  const tokens = ref<TokenPair | null>(readTokens())
  const initialized = ref(false)
  const isAuthenticated = computed(() => user.value !== null && tokens.value !== null)

  function applySession(nextUser: User, nextTokens: TokenPair): void {
    user.value = nextUser
    tokens.value = nextTokens
    writeTokens(nextTokens)
  }

  function clearSession(): void {
    user.value = null
    tokens.value = null
    clearTokens()
  }

  async function initialize(): Promise<void> {
    if (initialized.value) {
      return
    }
    const storedTokens = readTokens()
    if (storedTokens !== null) {
      tokens.value = storedTokens
      try {
        user.value = await getCurrentUser()
        tokens.value = readTokens()
      } catch {
        clearSession()
      }
    }
    initialized.value = true
  }

  async function register(input: RegisterInput): Promise<void> {
    const session = await registerUser(input)
    applySession(session.user, session.tokens)
  }

  async function login(input: LoginInput): Promise<void> {
    const session = await loginUser(input)
    applySession(session.user, session.tokens)
  }

  async function logout(): Promise<void> {
    const refreshToken = tokens.value?.refresh_token
    try {
      if (refreshToken) {
        await logoutUser(refreshToken)
      }
    } catch {
      // Local session cleanup must still complete if the network is unavailable.
    } finally {
      clearSession()
    }
  }

  return {
    user,
    tokens,
    initialized,
    isAuthenticated,
    initialize,
    register,
    login,
    logout,
    clearSession,
  }
})
