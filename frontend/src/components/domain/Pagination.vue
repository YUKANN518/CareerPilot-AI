<script setup lang="ts">
import { computed } from "vue"

import { Button } from "@/components/ui/button"

const props = withDefaults(
  defineProps<{
    offset: number
    limit: number
    total: number
    label?: string
  }>(),
  {
    label: "分页",
  },
)

const emit = defineEmits<{
  change: [offset: number]
}>()

const currentPage = computed(() => Math.floor(props.offset / props.limit) + 1)
const pageCount = computed(() => Math.max(1, Math.ceil(props.total / props.limit)))
</script>

<template>
  <nav
    class="flex items-center justify-between rounded-lg border bg-surface p-3 shadow-sm"
    :aria-label="label"
  >
    <Button
      size="sm"
      variant="outline"
      :disabled="currentPage <= 1"
      @click="emit('change', Math.max(0, offset - limit))"
    >
      上一页
    </Button>
    <span class="text-sm text-muted-foreground">
      第 {{ currentPage }} / {{ pageCount }} 页 · 共 {{ total }} 条
    </span>
    <Button
      size="sm"
      variant="outline"
      :disabled="currentPage >= pageCount"
      @click="emit('change', offset + limit)"
    >
      下一页
    </Button>
  </nav>
</template>
