<script setup lang="ts">
defineProps<{
  title: string
  description: string
}>()
</script>

<template>
  <section
    class="rounded-md border border-dashed bg-surface p-8"
    aria-labelledby="placeholder-title"
  >
    <h1
      id="placeholder-title"
      class="text-xl font-semibold"
    >
      {{ title }}
    </h1>
    <p class="mt-2 max-w-2xl text-sm text-muted-foreground">
      {{ description }}
    </p>
  </section>
</template>
