<script setup lang="ts">
import { FileText, RefreshCw } from "@lucide/vue"
import { onMounted, ref } from "vue"
import { RouterLink } from "vue-router"

import { getApiErrorMessage } from "@/api/errors"
import { listResumeOptimizations } from "@/api/resume-optimizations"
import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import PageSkeleton from "@/components/domain/PageSkeleton.vue"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import type { ResumeOptimization } from "@/types/resume-optimization"

const optimizations = ref<ResumeOptimization[]>([])
const loading = ref(true)
const errorMessage = ref<string | null>(null)

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

function tone(status: ResumeOptimization["status"]) {
  if (status === "CONFIRMED") return "success"
  if (status === "FAILED") return "danger"
  if (status === "ARCHIVED") return "neutral"
  return "warning"
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    const result = await listResumeOptimizations({ offset: 0, limit: 50 })
    optimizations.value = result.items
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
      eyebrow="Resume optimization"
      title="简历定向优化"
      description="基于已确认简历版本、真实岗位摘要和匹配报告，生成逐段优化建议。仅优化表达与关键词，不虚构经历。"
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
      label="正在加载优化记录"
      :rows="6"
    />
    <ErrorState
      v-else-if="errorMessage"
      :message="errorMessage"
      @retry="load"
    />
    <EmptyState
      v-else-if="optimizations.length === 0"
      title="还没有优化记录"
      description="打开一份匹配报告，点击“针对此岗位优化简历”即可生成逐段优化建议。"
      :icon="FileText"
    />
    <section
      v-else
      class="rounded-lg border bg-surface p-5 shadow-sm"
    >
      <div class="space-y-3">
        <RouterLink
          v-for="opt in optimizations"
          :key="opt.id"
          :to="{
            name: 'resume-optimization-detail',
            params: { optimizationId: opt.id },
          }"
          class="block rounded-md border bg-background p-4 transition-colors hover:border-primary/50 hover:bg-muted/40"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <h2 class="truncate text-base font-semibold">
                {{ opt.summary || "优化建议" }}
              </h2>
              <p
                v-if="opt.error_message"
                class="mt-1 line-clamp-2 text-sm leading-6 text-danger"
              >
                {{ opt.error_message }}
              </p>
              <p
                v-else
                class="mt-1 line-clamp-2 text-sm leading-6 text-muted-foreground"
              >
                简历版本 #{{ opt.resume_version_id }} · 岗位 #{{ opt.job_id }} ·
                匹配报告 #{{ opt.match_report_id }}
              </p>
            </div>
            <StatusBadge :tone="tone(opt.status)">
              {{ opt.status }}
            </StatusBadge>
          </div>
          <div class="mt-3 flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span>{{ opt.sections.length }} 个章节建议</span>
            <span>创建于 {{ formatDate(opt.created_at) }}</span>
            <span v-if="opt.provider">Provider: {{ opt.provider }}</span>
          </div>
        </RouterLink>
      </div>
    </section>
  </section>
</template>
