<script setup lang="ts">
import {
  ArrowLeft,
  BookOpen,
  ShieldCheck,
} from "@lucide/vue"
import type { Component } from "vue"
import { useRoute } from "vue-router"

const route = useRoute()

interface AdminNavigationItem {
  label: string
  icon: Component
  routeName?: string
  routeNames?: string[]
}

const items: AdminNavigationItem[] = [
  {
    label: "知识库",
    routeName: "admin-knowledge-documents",
    routeNames: ["admin-knowledge-documents"],
    icon: BookOpen,
  },
]

function isActive(item: AdminNavigationItem): boolean {
  const current = String(route.name ?? "")
  return item.routeNames?.includes(current) ?? current === item.routeName
}
</script>

<template>
  <aside class="hidden min-h-screen w-64 shrink-0 flex-col border-r bg-surface lg:flex">
    <div class="flex h-20 items-center gap-3 border-b px-5">
      <span class="grid size-10 place-items-center rounded-md bg-primary text-white">
        <ShieldCheck class="size-5" />
      </span>
      <div class="min-w-0">
        <p class="truncate text-sm font-bold">CareerPilot 管理后台</p>
        <p class="text-xs text-muted-foreground">RAG 知识库</p>
      </div>
    </div>
    <nav
      class="flex-1 overflow-y-auto px-3 py-6"
      aria-label="管理员导航"
    >
      <p class="px-3 text-xs font-semibold uppercase tracking-widest text-muted-foreground/70">
        Administration
      </p>
      <ul class="mt-3 space-y-1">
        <li
          v-for="item in items"
          :key="item.label"
        >
          <RouterLink
            :to="{ name: item.routeName }"
            class="flex h-11 items-center gap-3 rounded-sm px-3 text-base font-medium"
            :class="
              isActive(item)
                ? 'bg-primary-soft text-primary'
                : 'text-muted-foreground hover:bg-muted hover:text-foreground'
            "
          >
            <component
              :is="item.icon"
              class="size-4.5"
            />
            {{ item.label }}
          </RouterLink>
        </li>
      </ul>
    </nav>
    <div class="border-t p-3">
      <RouterLink
        :to="{ name: 'jobs' }"
        class="flex h-11 items-center gap-3 rounded-sm px-3 text-base font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
      >
        <ArrowLeft class="size-4.5" />
        用户端入口
      </RouterLink>
    </div>
  </aside>
</template>
