<script setup lang="ts">
import type { Component } from "vue"

withDefaults(
  defineProps<{
    label: string
    value: string | number
    helper?: string
    trend?: string
    tone?: "primary" | "info" | "success" | "warning"
    icon: Component
  }>(),
  {
    helper: undefined,
    trend: undefined,
    tone: "primary",
  },
)

const toneClasses = {
  primary: "bg-primary-soft text-primary",
  info: "bg-info-soft text-info",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
}
</script>

<template>
  <article class="rounded-lg border bg-surface p-5 shadow-sm">
    <div class="flex items-start justify-between gap-4">
      <div>
        <p class="text-sm font-medium text-muted-foreground">{{ label }}</p>
        <p class="mt-3 text-3xl font-bold tracking-tight">{{ value }}</p>
      </div>
      <span
        class="grid size-10 place-items-center rounded-md"
        :class="toneClasses[tone]"
      >
        <component
          :is="icon"
          class="size-5"
          aria-hidden="true"
        />
      </span>
    </div>
    <div class="mt-3 flex items-center justify-between gap-2 text-xs">
      <span class="text-muted-foreground">{{ helper }}</span>
      <span
        v-if="trend"
        class="font-semibold text-success"
      >
        {{ trend }}
      </span>
    </div>
  </article>
</template>
