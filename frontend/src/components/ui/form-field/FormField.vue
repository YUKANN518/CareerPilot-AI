<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    forId?: string
    required?: boolean
    hint?: string
    error?: string
  }>(),
  {
    forId: undefined,
    required: false,
    hint: undefined,
    error: undefined,
  },
)
</script>

<template>
  <div class="space-y-2">
    <label
      :for="forId"
      class="block text-sm font-medium"
    >
      {{ label }}
      <span
        v-if="required"
        class="text-danger"
        aria-hidden="true"
      >*</span>
    </label>
    <slot />
    <p
      v-if="error"
      class="text-xs text-danger"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-else-if="hint"
      class="text-xs leading-5 text-muted-foreground"
    >
      {{ hint }}
    </p>
  </div>
</template>
