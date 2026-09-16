<script setup lang="ts">
withDefaults(
  defineProps<{
    label?: string
  }>(),
  {
    label: "数据表格",
  },
)
</script>

<template>
  <div class="overflow-x-auto rounded-lg border bg-surface shadow-sm">
    <table
      class="w-full min-w-[48rem] border-collapse text-left text-sm"
      :aria-label="label"
    >
      <slot />
    </table>
  </div>
</template>
