<script setup lang="ts">
import { ChevronDown, LogOut, Moon, Sun } from "@lucide/vue"
import { computed, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { useAuthStore } from "@/stores/auth"

const routeLabels: Record<string, string> = {
  dashboard: "工作台",
  resumes: "简历",
  "resume-upload": "上传简历",
  "resume-status": "简历处理",
  "resume-confirm": "解析确认",
  "resume-version": "版本详情",
  jobs: "岗位",
  "job-detail": "目标岗位详情",
  "job-favorites": "我的收藏",
  applications: "求职进度",
  matches: "岗位匹配",
  "match-new": "发起匹配",
  "match-processing": "匹配流程",
  "match-report": "匹配报告",
  "career-assistant": "可选 AI 求职助手",
  "resume-optimizations": "简历优化",
  "resume-optimization-detail": "简历优化详情",
  interviews: "模拟面试",
  "interview-detail": "模拟面试",
  "interview-chat": "模拟面试",
  "interview-chat-report": "面试报告",
  "admin-home": "知识库",
  "admin-knowledge-documents": "知识库",
}

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const isDark = ref(false)
const menuOpen = ref(false)

const pageLabel = computed(() => routeLabels[String(route.name ?? "")] ?? "CareerPilot AI")
const displayName = computed(
  () =>
    authStore.user?.profile?.display_name?.trim() ||
    authStore.user?.email.split("@")[0] ||
    "CareerPilot 用户",
)
const initials = computed(() => displayName.value.slice(0, 2).toUpperCase())

function applyTheme(value: boolean): void {
  isDark.value = value
  document.documentElement.classList.toggle("dark", value)
  localStorage.setItem("careerpilot.theme", value ? "dark" : "light")
}

function toggleTheme(): void {
  applyTheme(!isDark.value)
}

async function handleLogout(): Promise<void> {
  menuOpen.value = false
  await authStore.logout()
  await router.push({ name: "login" })
}

onMounted(() => {
  applyTheme(localStorage.getItem("careerpilot.theme") === "dark")
})
</script>

<template>
  <header class="sticky top-0 z-30 flex h-20 items-center border-b bg-surface/95 px-4 backdrop-blur md:px-6">
    <RouterLink
      :to="{ name: 'dashboard' }"
      class="mr-4 flex items-center gap-2 lg:hidden"
      aria-label="CareerPilot AI 工作台"
    >
      <span class="grid size-8 place-items-center rounded-sm bg-primary text-xs font-bold text-white">
        CP
      </span>
    </RouterLink>

    <div class="hidden min-w-0 flex-1 items-center gap-2 sm:flex">
      <span class="text-sm text-muted-foreground">工作区</span>
      <span class="text-muted-foreground/40">/</span>
      <span class="truncate text-sm font-semibold">{{ pageLabel }}</span>
    </div>

    <div class="ml-auto flex items-center gap-2 md:ml-6">
      <button
        type="button"
        class="grid size-9 place-items-center rounded-sm border bg-surface text-muted-foreground hover:bg-muted hover:text-foreground"
        :aria-label="isDark ? '切换浅色模式' : '切换深色模式'"
        @click="toggleTheme"
      >
        <Sun
          v-if="isDark"
          class="size-4"
        />
        <Moon
          v-else
          class="size-4"
        />
      </button>
      <button
        type="button"
        class="grid size-9 place-items-center rounded-sm border bg-surface text-muted-foreground hover:bg-danger-soft hover:text-danger"
        aria-label="退出登录"
        title="退出登录"
        @click="handleLogout"
      >
        <LogOut class="size-4" />
      </button>
      <div class="relative">
        <button
          type="button"
          class="flex h-10 items-center gap-2 rounded-sm pl-1 pr-2 hover:bg-muted"
          aria-label="用户菜单"
          :aria-expanded="menuOpen"
          @click="menuOpen = !menuOpen"
        >
          <span class="grid size-8 place-items-center rounded-full bg-primary text-xs font-bold text-white">
            {{ initials }}
          </span>
          <span class="hidden max-w-28 truncate text-sm font-semibold xl:block">{{ displayName }}</span>
          <ChevronDown class="hidden size-4 text-muted-foreground xl:block" />
        </button>
        <div
          v-if="menuOpen"
          class="absolute right-0 top-12 w-56 rounded-md border bg-surface p-2 shadow-lg"
        >
          <div class="border-b px-3 py-2">
            <p class="truncate text-sm font-semibold">{{ displayName }}</p>
            <p class="truncate text-xs text-muted-foreground">{{ authStore.user?.email }}</p>
          </div>
          <button
            type="button"
            class="mt-1 flex w-full items-center gap-2 rounded-sm px-3 py-2 text-sm text-danger hover:bg-danger-soft"
            aria-label="从用户菜单退出登录"
            @click="handleLogout"
          >
            <LogOut class="size-4" />
            退出登录
          </button>
        </div>
      </div>
    </div>
  </header>
</template>
