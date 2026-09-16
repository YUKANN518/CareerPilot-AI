<script setup lang="ts">
import { CheckCircle2, FileSearch, ShieldCheck, Sparkles } from "@lucide/vue"
import { computed } from "vue"
import { useRoute } from "vue-router"

const route = useRoute()
const isLogin = computed(() => route.name === "login")

const highlights = [
  { icon: FileSearch, title: "简历解析", description: "保留原文证据与来源定位" },
  { icon: Sparkles, title: "结构化提取", description: "低置信度字段清晰可见" },
  { icon: ShieldCheck, title: "人工确认", description: "确认后才生成正式版本" },
]
</script>

<template>
  <main class="grid min-h-screen bg-surface lg:grid-cols-auth">
    <section class="hidden flex-col justify-between bg-primary p-12 text-white lg:flex xl:p-16">
      <RouterLink
        :to="{ name: 'login' }"
        class="flex items-center gap-3 text-sm font-bold"
      >
        <span class="grid size-9 place-items-center rounded-sm bg-white text-xs font-bold text-primary">
          CP
        </span>
        CareerPilot AI
      </RouterLink>

      <div class="max-w-xl">
        <p class="text-xs font-semibold uppercase tracking-widest text-white/65">
          AI Career Copilot · 可信赖的求职助手
        </p>
        <h1 class="mt-6 text-balance text-4xl font-bold leading-tight xl:text-5xl">
          让每一次求职决策
          <br>
          都有证据与方向
        </h1>
        <p class="mt-6 max-w-lg text-base leading-8 text-white/72">
          从简历解析、人工确认到版本沉淀，CareerPilot AI
          以真实证据为基础，帮助你建立清晰、可执行的职业行动。
        </p>

        <div class="mt-12 grid grid-cols-3 gap-3">
          <article
            v-for="(item, index) in highlights"
            :key="item.title"
            class="rounded-md bg-white/10 p-4"
          >
            <div class="flex items-center justify-between">
              <component
                :is="item.icon"
                class="size-5 text-white"
                aria-hidden="true"
              />
              <span class="text-xs font-semibold text-white/45">0{{ index + 1 }}</span>
            </div>
            <p class="mt-6 text-sm font-semibold">{{ item.title }}</p>
            <p class="mt-1 text-xs leading-5 text-white/60">{{ item.description }}</p>
          </article>
        </div>
      </div>

      <footer class="flex items-center gap-6 text-xs text-white/50">
        <span class="flex items-center gap-1.5">
          <CheckCircle2 class="size-3.5" />
          本地安全处理
        </span>
        <span class="flex items-center gap-1.5">
          <CheckCircle2 class="size-3.5" />
          可追溯证据
        </span>
        <span>© 2026 CareerPilot AI</span>
      </footer>
    </section>

    <section class="relative flex min-h-screen items-center justify-center p-6 sm:p-10 lg:p-16">
      <div class="absolute right-8 top-8 hidden items-center gap-2 text-sm text-muted-foreground sm:flex">
        <span>{{ isLogin ? "还没有账号？" : "已有账号？" }}</span>
        <RouterLink
          :to="{ name: isLogin ? 'register' : 'login' }"
          class="font-semibold text-primary hover:underline"
        >
          {{ isLogin ? "免费注册" : "立即登录" }}
        </RouterLink>
      </div>

      <div class="w-full max-w-auth">
        <RouterLink
          :to="{ name: 'login' }"
          class="mb-10 flex items-center gap-2 text-sm font-bold lg:hidden"
        >
          <span class="grid size-8 place-items-center rounded-sm bg-primary text-xs text-white">CP</span>
          CareerPilot AI
        </RouterLink>
        <RouterView />
      </div>
    </section>
  </main>
</template>
