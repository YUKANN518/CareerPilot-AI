import "vue-router"

import type { UserRole } from "@/types/auth"

export {}

declare module "vue-router" {
  interface RouteMeta {
    requiresAuth?: boolean
    guestOnly?: boolean
    roles?: UserRole[]
  }
}
