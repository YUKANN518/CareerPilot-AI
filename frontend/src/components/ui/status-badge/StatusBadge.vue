<script setup lang="ts">
import { computed } from "vue"

import { cn } from "@/utils/cn"

const props = withDefaults(
  defineProps<{
    tone?: "neutral" | "primary" | "info" | "success" | "warning" | "danger"
    dot?: boolean
  }>(),
  {
    tone: "neutral",
    dot: false,
  },
)

const toneClass = computed(
  () =>
    ({
      neutral: "bg-muted text-muted-foreground",
      primary: "bg-primary-soft text-primary",
      info: "bg-info-soft text-info",
      success: "bg-success-soft text-success",
      warning: "bg-warning-soft text-warning",
      danger: "bg-danger-soft text-danger",
    })[props.tone],
)

const dotClass = computed(
  () =>
    ({
      neutral: "bg-muted-foreground",
      primary: "bg-primary",
      info: "bg-info",
      success: "bg-success",
      warning: "bg-warning",
      danger: "bg-danger",
    })[props.tone],
)
</script>

<template>
  <span
    class="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-caption font-medium"
    :class="cn(toneClass)"
  >
    <span
      v-if="dot"
      class="size-1.5 rounded-full"
      :class="dotClass"
      aria-hidden="true"
    />
    <slot />
  </span>
</template>
