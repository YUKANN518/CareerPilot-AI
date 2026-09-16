<script setup lang="ts">
import { MessageSquare, RefreshCw } from "@lucide/vue"
import { onMounted, ref } from "vue"
import { RouterLink } from "vue-router"

import { getApiErrorMessage } from "@/api/errors"
import { listInterviews } from "@/api/interviews"
import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import PageSkeleton from "@/components/domain/PageSkeleton.vue"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import type {
  Interview,
  InterviewStatus,
  InterviewType,
} from "@/types/interview"

const interviews = ref<Interview[]>([])
const loading = ref(true)
const errorMessage = ref<string | null>(null)

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

function statusTone(status: InterviewStatus) {
  if (status === "REPORTED" || status === "COMPLETED") return "success"
  if (status === "FAILED") return "danger"
  if (status === "PLANNED") return "neutral"
  return "warning"
}

function typeTone(type: InterviewType) {
  if (type === "TECHNICAL") return "info"
  if (type === "BEHAVIORAL") return "primary"
  if (type === "HR") return "warning"
  if (type === "PROJECT") return "success"
  return "neutral"
}

function typeLabel(type: InterviewType): string {
  const labels: Record<InterviewType, string> = {
    COMPREHENSIVE: "综合面试",
    TECHNICAL: "技术面试",
    BEHAVIORAL: "行为面试",
    PROJECT: "项目深挖",
    HR: "HR 面试",
  }
  return labels[type] ?? type
}

function preview(text: string): string {
  if (!text) return "（暂无摘要）"
  return text.length > 120 ? text.slice(0, 120) + "…" : text
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    const result = await listInterviews({ offset: 0, limit: 50 })
    interviews.value = result.items
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="space-y-6">
    <PageHeader
      eyebrow="Interview"
      title="模拟面试"
      description="基于已确认简历版本与真实岗位生成结构化面试问答，记录作答评分、事实校验与 AI 反馈。"
    >
      <template #actions>
        <Button
          variant="outline"
          @click="load"
        >
          <RefreshCw class="mr-2 size-4" />
          刷新
        </Button>
      </template>
    </PageHeader>

    <PageSkeleton
      v-if="loading"
      label="正在加载模拟面试"
      :rows="6"
    />
    <ErrorState
      v-else-if="errorMessage"
      :message="errorMessage"
      @retry="load"
    />
    <EmptyState
      v-else-if="interviews.length === 0"
      title="还没有模拟面试记录"
      description="基于匹配报告生成结构化面试问答后，记录将出现在这里。"
      :icon="MessageSquare"
    />
    <section
      v-else
      class="rounded-lg border bg-surface p-5 shadow-sm"
    >
      <div class="space-y-3">
        <RouterLink
          v-for="interview in interviews"
          :key="interview.id"
          :to="{
            name: 'interview-chat',
            params: { interviewId: interview.id },
          }"
          class="block rounded-md border bg-background p-4 transition-colors hover:border-primary/50 hover:bg-muted/40"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h2 class="truncate text-base font-semibold">
                  模拟面试 #{{ interview.id }}
                </h2>
                <StatusBadge :tone="typeTone(interview.interview_type)">
                  {{ typeLabel(interview.interview_type) }}
                </StatusBadge>
              </div>
              <p
                v-if="interview.error_message"
                class="mt-1 line-clamp-2 text-sm leading-6 text-danger"
              >
                {{ interview.error_message }}
              </p>
              <p
                v-else
                class="mt-1 line-clamp-2 text-sm leading-6 text-muted-foreground"
              >
                {{ preview(interview.summary) }}
              </p>
              <p class="mt-1 text-xs text-muted-foreground">
                简历版本 #{{ interview.resume_version_id }} · 岗位 #{{ interview.job_id }}
              </p>
            </div>
            <StatusBadge :tone="statusTone(interview.status)">
              {{ interview.status }}
            </StatusBadge>
          </div>
          <div class="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span>创建于 {{ formatDate(interview.created_at) }}</span>
            <span v-if="interview.provider">Provider: {{ interview.provider }}</span>
          </div>
        </RouterLink>
      </div>
    </section>
  </section>
</template>
