<script setup lang="ts">
import { Inbox } from "@lucide/vue"
import type { Component } from "vue"

withDefaults(
  defineProps<{
    title: string
    description: string
    icon?: Component
    compact?: boolean
  }>(),
  {
    icon: () => Inbox,
    compact: false,
  },
)
</script>

<template>
  <section
    class="grid place-items-center rounded-lg border border-dashed bg-surface text-center"
    :class="compact ? 'p-6' : 'min-h-64 p-10'"
  >
    <div class="max-w-md">
      <span class="mx-auto grid size-12 place-items-center rounded-lg bg-primary-soft text-primary">
        <component
          :is="icon"
          class="size-5"
          aria-hidden="true"
        />
      </span>
      <h2 class="mt-4 text-base font-semibold">{{ title }}</h2>
      <p class="mt-2 text-sm leading-6 text-muted-foreground">{{ description }}</p>
      <div
        v-if="$slots.default"
        class="mt-5"
      >
        <slot />
      </div>
    </div>
  </section>
</template>
