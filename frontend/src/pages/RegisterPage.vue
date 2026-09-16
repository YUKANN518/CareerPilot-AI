<script setup lang="ts">
import { ref } from "vue"
import { useRouter } from "vue-router"
import { z } from "zod"

import { getApiErrorMessage } from "@/api/auth"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { FormMessage } from "@/components/ui/form-message"
import { Input } from "@/components/ui/input"
import { useAuthStore } from "@/stores/auth"

const schema = z.object({
  display_name: z.string().trim().min(1, "请输入姓名").max(100),
  email: z.string().email("请输入有效邮箱"),
  password: z.string().min(10, "密码至少需要 10 个字符").max(128),
})

const authStore = useAuthStore()
const router = useRouter()
const displayName = ref("")
const email = ref("")
const password = ref("")
const errorMessage = ref<string | null>(null)
const isSubmitting = ref(false)

async function submit(): Promise<void> {
  errorMessage.value = null
  const result = schema.safeParse({
    display_name: displayName.value,
    email: email.value,
    password: password.value,
  })
  if (!result.success) {
    errorMessage.value = result.error.issues[0]?.message ?? "请检查输入"
    return
  }

  isSubmitting.value = true
  try {
    await authStore.register(result.data)
    await router.push({ name: "dashboard" })
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <Card>
    <h1 class="text-xl font-semibold">注册</h1>
    <p class="mt-1 text-sm text-muted-foreground">创建普通用户账号。</p>

    <form
      class="mt-6 space-y-4"
      @submit.prevent="submit"
    >
      <div class="space-y-2">
        <label
          for="register-name"
          class="text-sm font-medium"
        >
          姓名
        </label>
        <Input
          id="register-name"
          v-model="displayName"
          autocomplete="name"
        />
      </div>

      <div class="space-y-2">
        <label
          for="register-email"
          class="text-sm font-medium"
        >
          邮箱
        </label>
        <Input
          id="register-email"
          v-model="email"
          type="email"
          autocomplete="email"
        />
      </div>

      <div class="space-y-2">
        <label
          for="register-password"
          class="text-sm font-medium"
        >
          密码
        </label>
        <Input
          id="register-password"
          v-model="password"
          type="password"
          autocomplete="new-password"
        />
      </div>

      <FormMessage :message="errorMessage" />

      <Button
        type="submit"
        class="w-full"
        :disabled="isSubmitting"
      >
        {{ isSubmitting ? "注册中…" : "注册" }}
      </Button>
    </form>

    <p class="mt-4 text-sm text-muted-foreground">
      已有账号？
      <RouterLink
        :to="{ name: 'login' }"
        class="text-primary underline-offset-4 hover:underline"
      >
        登录
      </RouterLink>
    </p>
  </Card>
</template>
