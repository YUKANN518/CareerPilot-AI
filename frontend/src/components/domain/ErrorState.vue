<script setup lang="ts">
import { AlertTriangle } from "@lucide/vue"

withDefaults(
  defineProps<{
    title?: string
    message: string
    compact?: boolean
  }>(),
  {
    title: "暂时无法加载",
    compact: false,
  },
)

defineEmits<{
  retry: []
}>()
</script>

<template>
  <section
    role="alert"
    class="rounded-lg border border-danger/20 bg-danger-soft"
    :class="compact ? 'p-4' : 'p-8'"
  >
    <div class="flex items-start gap-3">
      <span class="grid size-9 shrink-0 place-items-center rounded-md bg-surface text-danger">
        <AlertTriangle
          class="size-5"
          aria-hidden="true"
        />
      </span>
      <div class="min-w-0">
        <h2 class="font-semibold text-danger">{{ title }}</h2>
        <p class="mt-1 text-sm leading-6 text-danger/80">{{ message }}</p>
        <button
          v-if="!compact"
          type="button"
          class="mt-3 text-sm font-semibold text-danger underline-offset-4 hover:underline"
          @click="$emit('retry')"
        >
          重新加载
        </button>
      </div>
    </div>
  </section>
</template>
