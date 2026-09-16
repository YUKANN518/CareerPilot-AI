<script setup lang="ts">
import { computed } from "vue"

import { StatusBadge } from "@/components/ui/status-badge"
import type { ResumeStatus } from "@/types/resume"

const props = defineProps<{ status: ResumeStatus }>()

const labels: Record<ResumeStatus, string> = {
  UPLOADED: "已上传",
  EXTRACTING: "提取中",
  EXTRACTED: "已提取",
  PARSING: "解析中",
  NEEDS_CONFIRMATION: "待确认",
  CONFIRMED: "已确认",
  FAILED: "处理失败",
  ARCHIVED: "已归档",
}

const tones: Record<
  ResumeStatus,
  "neutral" | "primary" | "info" | "success" | "warning" | "danger"
> = {
  UPLOADED: "primary",
  EXTRACTING: "info",
  EXTRACTED: "info",
  PARSING: "primary",
  NEEDS_CONFIRMATION: "warning",
  CONFIRMED: "success",
  FAILED: "danger",
  ARCHIVED: "neutral",
}

const tone = computed(() => tones[props.status])
</script>

<template>
  <StatusBadge
    :tone="tone"
    dot
  >
    {{ labels[status] }}
  </StatusBadge>
</template>
