<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    description?: string
    eyebrow?: string
  }>(),
  {
    description: undefined,
    eyebrow: undefined,
  },
)
</script>

<template>
  <header class="flex flex-wrap items-start justify-between gap-4">
    <div class="min-w-0">
      <p
        v-if="eyebrow"
        class="mb-2 text-xs font-semibold uppercase tracking-widest text-primary"
      >
        {{ eyebrow }}
      </p>
      <h1 class="text-balance text-2xl font-bold tracking-tight text-foreground">
        {{ title }}
      </h1>
      <p
        v-if="description"
        class="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground"
      >
        {{ description }}
      </p>
    </div>
    <div
      v-if="$slots.actions"
      class="flex flex-wrap items-center gap-2"
    >
      <slot name="actions" />
    </div>
  </header>
</template>
