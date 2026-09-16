<script setup lang="ts">
import { Skeleton } from "@/components/ui/skeleton"

withDefaults(
  defineProps<{
    rows?: number
    label?: string
  }>(),
  {
    rows: 5,
    label: "正在加载页面",
  },
)
</script>

<template>
  <section
    class="space-y-4"
    role="status"
    :aria-label="label"
  >
    <span class="sr-only">{{ label }}</span>
    <Skeleton class-name="h-8 w-56" />
    <Skeleton class-name="h-4 w-96 max-w-full" />
    <div class="rounded-lg border bg-surface p-5 shadow-sm">
      <Skeleton class-name="h-10 w-full" />
      <Skeleton
        v-for="index in rows"
        :key="index"
        class-name="mt-4 h-14 w-full"
      />
    </div>
  </section>
</template>
