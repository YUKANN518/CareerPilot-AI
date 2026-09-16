<script setup lang="ts">
import { ShieldX } from "@lucide/vue"

import { Button } from "@/components/ui/button"

withDefaults(
  defineProps<{
    title?: string
    description?: string
  }>(),
  {
    title: "没有访问权限",
    description: "当前账号无权查看此页面。如需访问，请联系管理员调整角色权限。",
  },
)
</script>

<template>
  <section class="grid min-h-[28rem] place-items-center rounded-lg border bg-surface p-8 text-center shadow-sm">
    <div class="max-w-md">
      <span class="mx-auto grid size-14 place-items-center rounded-lg bg-danger-soft text-danger">
        <ShieldX class="size-7" />
      </span>
      <h1 class="mt-5 text-2xl font-bold">{{ title }}</h1>
      <p class="mt-3 text-sm leading-6 text-muted-foreground">{{ description }}</p>
      <RouterLink :to="{ name: 'dashboard' }">
        <Button class="mt-6">返回工作台</Button>
      </RouterLink>
    </div>
  </section>
</template>
