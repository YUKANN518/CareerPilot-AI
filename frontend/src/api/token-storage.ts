import type { TokenPair } from "@/types/auth"

const TOKEN_STORAGE_KEY = "careerpilot.tokens"

export function readTokens(): TokenPair | null {
  if (typeof localStorage === "undefined") {
    return null
  }
  const value = localStorage.getItem(TOKEN_STORAGE_KEY)
  if (!value) {
    return null
  }
  try {
    return JSON.parse(value) as TokenPair
  } catch {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    return null
  }
}

export function writeTokens(tokens: TokenPair): void {
  if (typeof localStorage !== "undefined") {
    localStorage.setItem(TOKEN_STORAGE_KEY, JSON.stringify(tokens))
  }
}

export function clearTokens(): void {
  if (typeof localStorage !== "undefined") {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
  }
}
