export type UserRole = "USER" | "ADMIN"

export interface UserProfile {
  display_name: string | null
  location: string | null
  headline: string | null
  bio: string | null
  target_roles: string[]
  preferences: Record<string, unknown>
}

export interface User {
  id: number
  email: string
  role: UserRole
  is_active: boolean
  created_at: string
  profile: UserProfile | null
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: "bearer"
  expires_in: number
}

export interface AuthSession {
  user: User
  tokens: TokenPair
}

export interface LoginInput {
  email: string
  password: string
}

export interface RegisterInput extends LoginInput {
  display_name?: string
}
