<script setup lang="ts">
import {
  FileCheck2,
  FileClock,
  FileText,
  MoreHorizontal,
  Plus,
  Search,
  Trash2,
} from "@lucide/vue"
import { computed, onMounted, ref } from "vue"

import { getApiErrorMessage } from "@/api/auth"
import { deleteResume, listResumes } from "@/api/resumes"
import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import LoadingState from "@/components/domain/LoadingState.vue"
import MetricCard from "@/components/domain/MetricCard.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import ResumeStatusBadge from "@/components/domain/ResumeStatusBadge.vue"
import { Button } from "@/components/ui/button"
import type { Resume } from "@/types/resume"

const resumes = ref<Resume[]>([])
const isLoading = ref(true)
const errorMessage = ref<string | null>(null)
const query = ref("")
const statusFilter = ref<"ALL" | Resume["status"]>("ALL")

const filteredResumes = computed(() => {
  const search = query.value.trim().toLowerCase()
  return resumes.value.filter((resume) => {
    const matchesSearch =
      !search ||
      resume.title.toLowerCase().includes(search) ||
      resume.file.original_name.toLowerCase().includes(search)
    const matchesStatus =
      statusFilter.value === "ALL" || resume.status === statusFilter.value
    return matchesSearch && matchesStatus
  })
})

const reviewCount = computed(
  () => resumes.value.filter((resume) => resume.status === "NEEDS_CONFIRMATION").length,
)
const versionCount = computed(() =>
  resumes.value.reduce((total, resume) => total + resume.version_count, 0),
)

async function load(): Promise<void> {
  isLoading.value = true
  errorMessage.value = null
  try {
    resumes.value = await listResumes()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

async function remove(resume: Resume): Promise<void> {
  if (!window.confirm(`确认删除“${resume.title}”及其历史版本吗？`)) return
  try {
    await deleteResume(resume.id)
    resumes.value = resumes.value.filter((item) => item.id !== resume.id)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  }
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value))
}

function formatSize(size: number): string {
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

onMounted(load)
</script>

<template>
  <section class="space-y-6">
    <PageHeader
      title="简历"
      description="管理不同方向的简历版本，并跟踪每一份简历的真实处理状态。"
    >
      <template #actions>
        <RouterLink :to="{ name: 'resume-upload' }">
          <Button>
            <Plus class="mr-2 size-4" />
            上传简历
          </Button>
        </RouterLink>
      </template>
    </PageHeader>

    <LoadingState
      v-if="isLoading"
      label="正在加载简历"
      :rows="4"
    />
    <ErrorState
      v-else-if="errorMessage"
      :message="errorMessage"
      @retry="load"
    />
    <template v-else-if="resumes.length > 0">
      <div class="grid gap-4 sm:grid-cols-3">
        <MetricCard
          label="简历文件"
          :value="resumes.length"
          helper="当前账户"
          tone="primary"
          :icon="FileText"
        />
        <MetricCard
          label="已确认版本"
          :value="versionCount"
          helper="不可覆盖，可追溯"
          tone="success"
          :icon="FileCheck2"
        />
        <MetricCard
          label="待人工确认"
          :value="reviewCount"
          helper="需要核对解析字段"
          tone="warning"
          :icon="FileClock"
        />
      </div>

      <section class="overflow-hidden rounded-lg border bg-surface shadow-sm">
        <div class="flex flex-wrap items-center justify-between gap-3 border-b p-4">
          <label class="flex h-10 min-w-64 flex-1 items-center gap-2 rounded-sm border bg-background px-3 sm:max-w-sm">
            <Search class="size-4 text-muted-foreground" />
            <span class="sr-only">搜索简历</span>
            <input
              v-model="query"
              type="search"
              class="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
              placeholder="搜索简历名称或文件名"
            >
          </label>
          <div class="flex items-center gap-3">
            <label class="text-sm text-muted-foreground">
              <span class="sr-only">状态筛选</span>
              <select
                v-model="statusFilter"
                class="h-10 rounded-sm border bg-surface px-3 text-sm text-foreground"
              >
                <option value="ALL">全部状态</option>
                <option value="UPLOADED">已上传</option>
                <option value="EXTRACTED">已提取</option>
                <option value="NEEDS_CONFIRMATION">待确认</option>
                <option value="CONFIRMED">已确认</option>
                <option value="FAILED">处理失败</option>
              </select>
            </label>
            <span class="text-xs text-muted-foreground">
              共 {{ filteredResumes.length }} 份
            </span>
          </div>
        </div>

        <div
          v-if="filteredResumes.length > 0"
          class="overflow-x-auto"
        >
          <table class="w-full min-w-table border-collapse text-left text-sm">
            <thead class="bg-muted/70 text-xs text-muted-foreground">
              <tr>
                <th class="px-5 py-3 font-medium">简历</th>
                <th class="px-4 py-3 font-medium">当前状态</th>
                <th class="px-4 py-3 font-medium">版本</th>
                <th class="px-4 py-3 font-medium">更新时间</th>
                <th class="px-4 py-3 text-right font-medium">操作</th>
              </tr>
            </thead>
            <tbody class="divide-y">
              <tr
                v-for="resume in filteredResumes"
                :key="resume.id"
                class="group hover:bg-muted/35"
              >
                <td class="px-5 py-4">
                  <div class="flex min-w-72 items-center gap-3">
                    <span
                      class="grid size-11 shrink-0 place-items-center rounded-md text-xs font-bold"
                      :class="
                        resume.file.file_format === 'pdf'
                          ? 'bg-primary-soft text-primary'
                          : 'bg-info-soft text-info'
                      "
                    >
                      {{ resume.file.file_format.toUpperCase() }}
                    </span>
                    <div class="min-w-0">
                      <RouterLink
                        :to="{ name: 'resume-status', params: { resumeId: resume.id } }"
                        class="block truncate font-semibold hover:text-primary hover:underline"
                      >
                        {{ resume.title }}
                      </RouterLink>
                      <p class="mt-1 truncate text-xs text-muted-foreground">
                        {{ resume.file.original_name }} · {{ formatSize(resume.file.size_bytes) }}
                      </p>
                    </div>
                  </div>
                </td>
                <td class="px-4 py-4">
                  <ResumeStatusBadge :status="resume.status" />
                  <p
                    v-if="resume.last_error_message"
                    class="mt-1 max-w-56 truncate text-xs text-danger"
                  >
                    {{ resume.last_error_message }}
                  </p>
                </td>
                <td class="px-4 py-4">
                  <p class="font-medium">
                    {{ resume.version_count > 0 ? `v${resume.version_count}` : "未成版" }}
                  </p>
                  <p class="mt-1 text-xs text-muted-foreground">
                    {{ resume.version_count }} 个正式版本
                  </p>
                </td>
                <td class="px-4 py-4 text-muted-foreground">
                  {{ formatDate(resume.updated_at) }}
                </td>
                <td class="px-4 py-4">
                  <div class="flex justify-end gap-2">
                    <RouterLink
                      :to="{ name: 'resume-status', params: { resumeId: resume.id } }"
                      class="inline-flex h-9 items-center rounded-sm border bg-surface px-3 text-xs font-semibold hover:bg-muted"
                    >
                      查看详情
                    </RouterLink>
                    <Button
                      variant="ghost"
                      size="sm"
                      :aria-label="`删除 ${resume.title}`"
                      @click="remove(resume)"
                    >
                      <Trash2 class="size-4 text-danger" />
                    </Button>
                    <span
                      class="grid size-9 place-items-center text-muted-foreground"
                      aria-hidden="true"
                    >
                      <MoreHorizontal class="size-4" />
                    </span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <EmptyState
          v-else
          compact
          title="没有匹配的简历"
          description="调整搜索关键词或状态筛选后再试。"
        />
      </section>
    </template>
    <EmptyState
      v-else
      title="还没有简历"
      description="上传 PDF 或 DOCX，开始安全提取、结构化解析与人工确认。"
    >
      <RouterLink :to="{ name: 'resume-upload' }">
        <Button>上传第一份简历</Button>
      </RouterLink>
    </EmptyState>
  </section>
</template>
