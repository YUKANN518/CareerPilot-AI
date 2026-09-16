<script setup lang="ts">
withDefaults(
  defineProps<{
    label?: string
    rows?: number
  }>(),
  {
    label: "正在加载…",
    rows: 3,
  },
)
</script>

<template>
  <section
    class="space-y-3 rounded-lg border bg-surface p-5 shadow-sm"
    role="status"
    :aria-label="label"
  >
    <span class="sr-only">{{ label }}</span>
    <div class="h-4 w-1/4 animate-pulse rounded-full bg-muted" />
    <div
      v-for="index in rows"
      :key="index"
      class="h-16 animate-pulse rounded-md bg-muted"
    />
  </section>
</template>
