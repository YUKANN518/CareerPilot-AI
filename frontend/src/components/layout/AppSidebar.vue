<script setup lang="ts">
import {
  Bot,
  BriefcaseBusiness,
  ClipboardList,
  Database,
  FileText,
  LayoutDashboard,
  PanelLeftClose,
  PanelLeftOpen,
  Target,
} from "@lucide/vue"
import { computed, type Component } from "vue"
import { useRoute } from "vue-router"

import { useAuthStore } from "@/stores/auth"
import { cn } from "@/utils/cn"

defineProps<{
  collapsed: boolean
}>()

defineEmits<{
  "update:collapsed": [value: boolean]
}>()

interface NavigationItem {
  label: string
  icon: Component
  routeName?: string
  routePrefix?: string
}

const workspaceItems: NavigationItem[] = [
  { label: "工作台", icon: LayoutDashboard, routeName: "dashboard" },
  {
    label: "我的简历",
    icon: FileText,
    routeName: "resumes",
    routePrefix: "resume",
  },
  { label: "目标岗位", icon: BriefcaseBusiness, routeName: "jobs" },
  {
    label: "匹配任务",
    icon: Target,
    routeName: "matches",
    routePrefix: "match",
  },
  { label: "AI 职业助手", icon: Bot, routeName: "career-assistant" },
  { label: "投递管理", icon: ClipboardList, routeName: "applications", routePrefix: "application" },
]

const route = useRoute()
const authStore = useAuthStore()
const accountItems = computed<NavigationItem[]>(() => [
  ...(authStore.user?.role === "ADMIN"
    ? [{ label: "知识库管理", icon: Database, routeName: "admin-knowledge-documents" }]
    : []),
])
const displayName = computed(
  () =>
    authStore.user?.profile?.display_name?.trim() ||
    authStore.user?.email.split("@")[0] ||
    "CareerPilot 用户",
)
const initials = computed(() => displayName.value.slice(0, 2).toUpperCase())

function isActive(item: NavigationItem): boolean {
  const currentName = String(route.name ?? "")
  if (item.routeName === currentName) return true
  return Boolean(item.routePrefix && currentName.startsWith(item.routePrefix))
}
</script>

<template>
  <aside
    class="hidden min-h-screen shrink-0 flex-col border-r bg-surface transition-[width] duration-normal lg:flex"
    :class="collapsed ? 'w-20' : 'w-sidebar'"
  >
    <div
      class="flex h-20 items-center border-b px-5"
      :class="collapsed ? 'justify-center' : 'justify-between'"
    >
      <RouterLink
        :to="{ name: 'dashboard' }"
        class="flex min-w-0 items-center gap-2.5"
        aria-label="CareerPilot AI 工作台"
      >
        <span class="grid size-8 shrink-0 place-items-center rounded-sm bg-primary text-xs font-bold text-white">
          CP
        </span>
        <span
          v-if="!collapsed"
          class="truncate text-sm font-bold tracking-tight"
        >
          CareerPilot AI
        </span>
      </RouterLink>
      <button
        v-if="!collapsed"
        type="button"
        class="grid size-8 place-items-center rounded-sm text-muted-foreground hover:bg-muted hover:text-foreground"
        aria-label="折叠侧栏"
        @click="$emit('update:collapsed', true)"
      >
        <PanelLeftClose class="size-4" />
      </button>
    </div>

    <nav
      class="flex-1 overflow-y-auto px-3 py-6"
      aria-label="主导航"
    >
      <p
        v-if="!collapsed"
        class="px-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground/70"
      >
        Workspace
      </p>
      <ul class="mt-3 space-y-1">
        <li
          v-for="item in workspaceItems"
          :key="item.label"
        >
          <RouterLink
            v-if="item.routeName"
            :to="{ name: item.routeName }"
            :title="collapsed ? item.label : undefined"
            :aria-label="item.routeName === 'resumes' ? '简历' : undefined"
            :class="
              cn(
                'flex h-11 items-center rounded-sm text-base font-medium transition-colors duration-fast',
                collapsed ? 'justify-center px-2' : 'gap-3 px-3',
                isActive(item)
                  ? 'bg-primary-soft text-primary'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )
            "
          >
            <component
              :is="item.icon"
              class="size-4.5 shrink-0"
              aria-hidden="true"
            />
            <span v-if="!collapsed">{{ item.label }}</span>
          </RouterLink>
        </li>
      </ul>

      <template v-if="!collapsed && accountItems.length > 0">
        <p class="mt-8 px-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground/70">
          Account
        </p>
      </template>
      <ul class="mt-3 space-y-1">
        <li
          v-for="item in accountItems"
          :key="item.label"
        >
          <RouterLink
            v-if="item.routeName"
            :to="{ name: item.routeName }"
            :title="collapsed ? item.label : undefined"
            :class="
              cn(
                'flex h-11 items-center rounded-sm text-base font-medium transition-colors duration-fast',
                collapsed ? 'justify-center px-2' : 'gap-3 px-3',
                isActive(item)
                  ? 'bg-primary-soft text-primary'
                  : 'text-muted-foreground hover:bg-muted hover:text-foreground',
              )
            "
          >
            <component
              :is="item.icon"
              class="size-4.5 shrink-0"
              aria-hidden="true"
            />
            <span v-if="!collapsed">{{ item.label }}</span>
          </RouterLink>
        </li>
      </ul>
    </nav>

    <div class="space-y-3 border-t p-3">
      <div
        class="flex items-center rounded-md p-2"
        :class="collapsed ? 'justify-center' : 'gap-3'"
      >
        <span class="grid size-9 shrink-0 place-items-center rounded-full bg-primary text-xs font-bold text-white">
          {{ initials }}
        </span>
        <div
          v-if="!collapsed"
          class="min-w-0"
        >
          <p class="truncate text-sm font-semibold">{{ displayName }}</p>
          <p class="truncate text-xs text-muted-foreground">{{ authStore.user?.email }}</p>
        </div>
      </div>
      <button
        v-if="collapsed"
        type="button"
        class="grid h-9 w-full place-items-center rounded-sm text-muted-foreground hover:bg-muted hover:text-foreground"
        aria-label="展开侧栏"
        @click="$emit('update:collapsed', false)"
      >
        <PanelLeftOpen class="size-4" />
      </button>
    </div>
  </aside>
</template>
