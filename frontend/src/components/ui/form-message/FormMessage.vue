<script setup lang="ts">
defineProps<{
  message?: string | null
  tone?: "error" | "success"
}>()
</script>

<template>
  <p
    v-if="message"
    role="status"
    :class="tone === 'success' ? 'text-success' : 'text-danger'"
    class="text-sm"
  >
    {{ message }}
  </p>
</template>
