<script setup lang="ts">
import { Eye, EyeOff, KeyRound, Mail } from "@lucide/vue"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { z } from "zod"

import { getApiErrorMessage } from "@/api/auth"
import { Button } from "@/components/ui/button"
import { FormMessage } from "@/components/ui/form-message"
import { Input } from "@/components/ui/input"
import { useAuthStore } from "@/stores/auth"

const schema = z.object({
  email: z.string().email("请输入有效邮箱"),
  password: z.string().min(1, "请输入密码"),
})

const authStore = useAuthStore()
const router = useRouter()
const email = ref("")
const password = ref("")
const errorMessage = ref<string | null>(null)
const isSubmitting = ref(false)
const showPassword = ref(false)
const rememberEmail = ref(false)

async function submit(): Promise<void> {
  errorMessage.value = null
  const result = schema.safeParse({ email: email.value, password: password.value })
  if (!result.success) {
    errorMessage.value = result.error.issues[0]?.message ?? "请检查输入"
    return
  }

  isSubmitting.value = true
  try {
    await authStore.login(result.data)
    if (rememberEmail.value) {
      localStorage.setItem("careerpilot.remembered-email", email.value)
    } else {
      localStorage.removeItem("careerpilot.remembered-email")
    }
    await router.push({ name: "dashboard" })
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSubmitting.value = false
  }
}

onMounted(() => {
  const rememberedEmail = localStorage.getItem("careerpilot.remembered-email")
  if (rememberedEmail) {
    email.value = rememberedEmail
    rememberEmail.value = true
  }
})
</script>

<template>
  <section>
    <p class="text-xs font-semibold uppercase tracking-widest text-primary">欢迎回来</p>
    <h1 class="mt-3 text-3xl font-bold tracking-tight">登录 CareerPilot AI</h1>
    <p class="mt-3 text-sm leading-6 text-muted-foreground">
      继续管理你的简历版本、解析结果与技能证据。
    </p>

    <form
      class="mt-8 space-y-5"
      @submit.prevent="submit"
    >
      <div class="space-y-2">
        <label
          for="login-email"
          class="text-sm font-medium"
        >
          邮箱地址
        </label>
        <div class="relative">
          <Mail
            class="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id="login-email"
            v-model="email"
            type="email"
            autocomplete="email"
            class="pl-10"
            placeholder="name@example.com"
          />
        </div>
      </div>

      <div class="space-y-2">
        <label
          for="login-password"
          class="text-sm font-medium"
        >
          密码
        </label>
        <div class="relative">
          <KeyRound
            class="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            id="login-password"
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            autocomplete="current-password"
            class="px-10"
            placeholder="输入你的密码"
          />
          <button
            type="button"
            class="absolute right-1 top-1 grid size-8 place-items-center rounded-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            :aria-label="showPassword ? '隐藏输入内容' : '显示输入内容'"
            @click="showPassword = !showPassword"
          >
            <EyeOff
              v-if="showPassword"
              class="size-4"
            />
            <Eye
              v-else
              class="size-4"
            />
          </button>
        </div>
      </div>

      <div class="flex items-center justify-between gap-3">
        <label class="flex cursor-pointer items-center gap-2 text-sm text-muted-foreground">
          <input
            v-model="rememberEmail"
            type="checkbox"
            class="size-4 rounded border-border text-primary"
          >
          记住账号
        </label>
      </div>

      <FormMessage :message="errorMessage" />

      <Button
        type="submit"
        class="w-full shadow-md"
        size="lg"
        :disabled="isSubmitting"
      >
        {{ isSubmitting ? "登录中…" : "登录" }}
      </Button>
    </form>

    <p class="mt-8 text-center text-sm text-muted-foreground sm:hidden">
      还没有账号？
      <RouterLink
        :to="{ name: 'register' }"
        class="font-semibold text-primary underline-offset-4 hover:underline"
      >
        免费注册
      </RouterLink>
    </p>

    <div class="mt-10 rounded-md border bg-muted/60 p-4">
      <p class="flex items-start gap-2 text-xs leading-5 text-muted-foreground">
        <KeyRound class="mt-0.5 size-3.5 shrink-0 text-primary" />
        你的简历内容仅用于当前账户的解析与确认流程，未经确认的 AI
        结果不会成为正式职业事实。
      </p>
    </div>
  </section>
</template>
