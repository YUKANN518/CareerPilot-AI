<script setup lang="ts">
import {
  ArrowRight,
  BadgeCheck,
  BriefcaseBusiness,
  FileCheck2,
  FileText,
  ScanSearch,
  Sparkles,
} from "@lucide/vue"
import { computed, onMounted, ref, type Component } from "vue"

import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import LoadingState from "@/components/domain/LoadingState.vue"
import MetricCard from "@/components/domain/MetricCard.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import {
  dashboardService,
  type DashboardIconName,
  type DashboardSnapshot,
  type DashboardWorkflowStatus,
} from "@/services/dashboard"
import { useAuthStore } from "@/stores/auth"

const iconMap: Record<DashboardIconName, Component> = {
  resume: FileText,
  version: FileCheck2,
  evidence: BadgeCheck,
  match: BriefcaseBusiness,
}

const skillToneClasses = {
  primary: "bg-primary",
  info: "bg-info",
  success: "bg-success",
  warning: "bg-warning",
}

const workflowLabels: Record<
  DashboardWorkflowStatus,
  { label: string; tone: "neutral" | "info" | "success" | "warning" | "danger" }
> = {
  uploaded: { label: "已上传", tone: "neutral" },
  processing: { label: "处理中", tone: "info" },
  extracted: { label: "已提取", tone: "info" },
  review: { label: "待确认", tone: "warning" },
  confirmed: { label: "已确认", tone: "success" },
  failed: { label: "处理失败", tone: "danger" },
}

const authStore = useAuthStore()
const snapshot = ref<DashboardSnapshot | null>(null)
const isLoading = ref(true)
const errorMessage = ref<string | null>(null)
const displayName = computed(
  () =>
    authStore.user?.profile?.display_name?.trim() ||
    authStore.user?.email.split("@")[0] ||
    "同学",
)

async function load(): Promise<void> {
  isLoading.value = true
  errorMessage.value = null
  try {
    snapshot.value = await dashboardService.getSnapshot()
  } catch {
    errorMessage.value = "工作台概览暂时不可用，请稍后重试。"
  } finally {
    isLoading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="space-y-6">
    <PageHeader
      title="用户工作台"
      :description="`早上好，${displayName}。从一份可信的简历版本开始今天的求职准备。`"
    >
      <template #actions>
        <StatusBadge tone="success">实时数据</StatusBadge>
        <RouterLink :to="{ name: 'resume-upload' }">
          <Button>
            <Sparkles class="mr-2 size-4" />
            上传新简历
          </Button>
        </RouterLink>
      </template>
    </PageHeader>

    <LoadingState
      v-if="isLoading"
      label="正在加载工作台"
      :rows="5"
    />
    <ErrorState
      v-else-if="errorMessage"
      :message="errorMessage"
      @retry="load"
    />
    <template v-else-if="snapshot">
      <section class="overflow-hidden rounded-lg bg-primary p-6 text-white shadow-md">
        <div class="flex flex-wrap items-end justify-between gap-5">
          <div>
            <p class="text-sm font-medium text-white/75">简历健康度</p>
            <h2 class="mt-2 text-2xl font-bold">
              你的核心简历已完成 {{ snapshot.completeness }}%
            </h2>
            <p class="mt-2 text-sm text-white/70">
              <template v-if="snapshot.pendingConfirmationCount > 0">
                还有 {{ snapshot.pendingConfirmationCount }} 个字段需要人工核对。
              </template>
              <template v-else>
                当前没有待确认字段，可以继续匹配合适岗位。
              </template>
            </p>
          </div>
          <div class="min-w-64">
            <div class="mb-2 flex items-center justify-between text-xs text-white/75">
              <span>{{ snapshot.completenessLabel }}</span>
              <strong class="text-white">{{ snapshot.completeness }}%</strong>
            </div>
            <div class="h-2 overflow-hidden rounded-full bg-white/20">
              <div
                class="h-full rounded-full bg-white"
                :style="{ width: `${snapshot.completeness}%` }"
              />
            </div>
          </div>
        </div>
      </section>

      <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          v-for="metric in snapshot.metrics"
          :key="metric.id"
          :label="metric.label"
          :value="`${metric.value}${metric.suffix ?? ''}`"
          :helper="metric.helper"
          :tone="metric.tone"
          :icon="iconMap[metric.icon]"
        />
      </div>

      <div class="grid gap-6 xl:grid-cols-3">
        <section class="rounded-lg border bg-surface p-5 shadow-sm xl:col-span-2">
          <div class="flex items-center justify-between gap-4">
            <div>
              <h2 class="text-section font-semibold">最近简历</h2>
              <p class="mt-1 text-support text-muted-foreground">
                最近处理的简历与当前进度
              </p>
            </div>
            <RouterLink
              :to="{ name: 'resumes' }"
              class="flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
            >
              查看全部
              <ArrowRight class="size-4" />
            </RouterLink>
          </div>
          <ul
            v-if="snapshot.workflows.length > 0"
            class="mt-5 divide-y"
          >
            <li
              v-for="workflow in snapshot.workflows"
              :key="workflow.id"
              class="grid gap-3 py-4 sm:grid-cols-[minmax(0,1fr)_8rem_auto] sm:items-center"
            >
              <div class="flex min-w-0 items-center gap-3">
                <span class="grid size-10 shrink-0 place-items-center rounded-md bg-primary-soft text-xs font-bold text-primary">
                  {{ workflow.fileType }}
                </span>
                <div class="min-w-0">
                  <p class="truncate text-sm font-semibold">{{ workflow.title }}</p>
                  <p class="mt-1 text-support text-muted-foreground">{{ workflow.updatedAt }}</p>
                </div>
              </div>
              <div>
                <div class="h-1.5 overflow-hidden rounded-full bg-muted">
                  <div
                    class="h-full rounded-full bg-primary"
                    :style="{ width: `${workflow.progress}%` }"
                  />
                </div>
                <p class="mt-1 text-right text-xs text-muted-foreground">
                  {{ workflow.progress }}%
                </p>
              </div>
              <StatusBadge :tone="workflowLabels[workflow.status].tone">
                {{ workflowLabels[workflow.status].label }}
              </StatusBadge>
            </li>
          </ul>
          <p
            v-else
            class="mt-5 rounded-md bg-muted/60 p-5 text-sm text-muted-foreground"
          >
            暂无简历，上传后即可查看处理进度。
          </p>
        </section>

        <section class="rounded-lg border bg-surface p-5 shadow-sm">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h2 class="text-section font-semibold">技能证据 Top 4</h2>
              <p class="mt-1 text-support text-muted-foreground">
                按已确认原文证据数量
              </p>
            </div>
            <ScanSearch class="size-5 text-primary" />
          </div>
          <ul
            v-if="snapshot.skillEvidence.length > 0"
            class="mt-5 space-y-5"
          >
            <li
              v-for="skill in snapshot.skillEvidence"
              :key="skill.name"
            >
              <div class="mb-2 flex items-center justify-between text-sm">
                <span class="font-medium">{{ skill.name }}</span>
                <span class="text-support text-muted-foreground">{{ skill.count }} 条</span>
              </div>
              <div class="h-1.5 overflow-hidden rounded-full bg-muted">
                <div
                  class="h-full rounded-full"
                  :class="skillToneClasses[skill.tone]"
                  :style="{ width: `${skill.percentage}%` }"
                />
              </div>
            </li>
          </ul>
          <p
            v-else
            class="mt-5 text-sm text-muted-foreground"
          >
            确认简历解析结果后，这里会显示可追溯的技能证据。
          </p>
          <div class="mt-6 rounded-md bg-primary-soft p-3 text-support leading-5 text-primary">
            技能只在存在可追溯原文时计入画像，AI 推测不会自动标记为已掌握。
          </div>
        </section>
      </div>

      <section class="rounded-lg border bg-surface p-5 shadow-sm">
        <div class="flex items-center justify-between gap-4">
          <div>
            <h2 class="text-section font-semibold">推荐岗位</h2>
            <p class="mt-1 text-support text-muted-foreground">
              来自你已完成的真实匹配报告
            </p>
          </div>
          <RouterLink
            :to="{ name: 'matches' }"
            class="flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
          >
            匹配历史
            <ArrowRight class="size-4" />
          </RouterLink>
        </div>
        <div
          v-if="snapshot.recommendedJobs.length > 0"
          class="mt-5 grid gap-3 lg:grid-cols-3"
        >
          <article
            v-for="job in snapshot.recommendedJobs"
            :key="job.reportId"
            class="rounded-md border p-4"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <RouterLink
                  :to="{ name: 'job-detail', params: { jobId: job.jobId } }"
                  class="font-semibold hover:text-primary"
                >
                  {{ job.title }}
                </RouterLink>
                <p class="mt-1 text-support text-muted-foreground">
                  {{ job.company }} · {{ job.location }}
                </p>
              </div>
              <strong class="text-xl text-primary">{{ job.score }}</strong>
            </div>
            <div class="mt-4 flex items-center justify-between gap-2">
              <span class="text-xs text-muted-foreground">{{ job.scoringVersion }}</span>
              <RouterLink
                :to="{ name: 'match-report', params: { matchId: job.reportId } }"
                class="text-sm font-semibold text-primary hover:underline"
              >
                查看报告
              </RouterLink>
            </div>
          </article>
        </div>
        <p
          v-else
          class="mt-5 rounded-md bg-muted/60 p-5 text-sm text-muted-foreground"
        >
          暂无推荐岗位。选择正式简历版本和岗位创建匹配报告后会显示在这里。
        </p>
      </section>

      <section class="rounded-lg border bg-surface p-5 shadow-sm">
        <div>
          <h2 class="text-section font-semibold">简历处理漏斗</h2>
          <p class="mt-1 text-support text-muted-foreground">
            从安全上传到不可覆盖版本
          </p>
        </div>
        <ol class="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <li
            v-for="(step, index) in snapshot.funnel"
            :key="step.label"
            class="rounded-md bg-muted/70 p-4"
          >
            <div class="flex items-center justify-between">
              <span class="grid size-7 place-items-center rounded-full bg-surface text-xs font-bold text-primary">
                {{ index + 1 }}
              </span>
              <strong class="text-xl">{{ step.value }}</strong>
            </div>
            <p class="mt-3 text-sm font-semibold">{{ step.label }}</p>
            <p class="mt-1 text-support text-muted-foreground">{{ step.description }}</p>
          </li>
        </ol>
      </section>

      <section class="rounded-lg border bg-surface p-5 shadow-sm">
        <div class="flex items-center justify-between gap-4">
          <div>
            <h2 class="text-section font-semibold">投递状态漏斗</h2>
            <p class="mt-1 text-support text-muted-foreground">
              从收藏岗位到 Offer 的真实投递进度
            </p>
          </div>
          <RouterLink
            :to="{ name: 'applications' }"
            class="flex items-center gap-1 text-sm font-semibold text-primary hover:underline"
          >
            打开求职进度
            <ArrowRight class="size-4" />
          </RouterLink>
        </div>
        <ol class="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          <li
            v-for="(step, index) in snapshot.applicationFunnel"
            :key="step.label"
            class="rounded-md bg-muted/70 p-4"
          >
            <div class="flex items-center justify-between">
              <span class="grid size-7 place-items-center rounded-full bg-surface text-xs font-bold text-primary">
                {{ index + 1 }}
              </span>
              <strong class="text-xl">{{ step.value }}</strong>
            </div>
            <p class="mt-3 text-sm font-semibold">{{ step.label }}</p>
            <p class="mt-1 text-support text-muted-foreground">{{ step.description }}</p>
          </li>
        </ol>
      </section>
    </template>
    <EmptyState
      v-else
      title="暂无工作台数据"
      description="上传第一份简历后，这里会汇总处理进度和技能证据。"
    />
  </section>
</template>
