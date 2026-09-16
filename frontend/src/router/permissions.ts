import type { UserRole } from "@/types/auth"

export function hasRequiredRole(
  userRole: UserRole | undefined,
  allowedRoles: UserRole[] | undefined,
): boolean {
  return allowedRoles === undefined || (userRole !== undefined && allowedRoles.includes(userRole))
}
