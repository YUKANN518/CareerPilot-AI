<script setup lang="ts">
import {
  ArrowLeft,
  ArrowLeftRight,
  BadgeCheck,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  Download,
  FileCheck2,
  History,
  Layers3,
  Plus,
  ScanSearch,
  Sparkles,
  Target,
} from "@lucide/vue"
import { computed, onMounted, ref } from "vue"
import { useRoute } from "vue-router"

import { getApiErrorMessage } from "@/api/auth"
import { getJob } from "@/api/jobs"
import {
  downloadResumeFile,
  getResume,
  getResumeVersion,
  listResumeVersions,
  listResumeVersionSkills,
} from "@/api/resumes"
import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import LoadingState from "@/components/domain/LoadingState.vue"
import MatchHistoryList from "@/components/domain/MatchHistoryList.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import { matchHistoryService } from "@/services/matching"
import type { MatchReport } from "@/types/matching"
import type { Resume, ResumeSkill, ResumeVersion } from "@/types/resume"

const route = useRoute()
const versionId = computed(() => Number(route.params.versionId))
const version = ref<ResumeVersion | null>(null)
const resume = ref<Resume | null>(null)
const versions = ref<ResumeVersion[]>([])
const skills = ref<ResumeSkill[]>([])
const matchHistory = ref<MatchReport[]>([])
const jobLabels = ref<Record<number, string>>({})
const isLoading = ref(true)
const isDownloading = ref(false)
const errorMessage = ref<string | null>(null)

const positionTitle = computed(
  () =>
    version.value?.structured_data.work_experience[0]?.title.value ||
    version.value?.structured_data.project_experience[0]?.role.value ||
    "职业方向待补充",
)
const evidenceCoverage = computed(() => {
  if (skills.value.length === 0) return 0
  const evidenced = skills.value.filter((skill) => skill.evidence_text.trim()).length
  return Math.round((evidenced / skills.value.length) * 100)
})
const averageConfidence = computed(() => {
  if (skills.value.length === 0) return 0
  const total = skills.value.reduce((sum, skill) => sum + skill.confidence, 0)
  return Math.round((total / skills.value.length) * 100)
})
const previousVersion = computed(
  () =>
    versions.value.find(
      (item) => item.version_number === (version.value?.version_number ?? 0) - 1,
    ) ?? null,
)
const resumeLabels = computed<Record<number, string>>(() =>
  version.value
    ? {
        [version.value.id]: `${resume.value?.title ?? "简历"} · 正式版本 v${version.value.version_number}`,
      }
    : {},
)
const versionDifferences = computed(() => {
  if (!version.value || !previousVersion.value) return []
  const current = version.value.structured_data
  const previous = previousVersion.value.structured_data
  const comparisons = [
    {
      label: "姓名",
      previous: previous.basic_info.full_name.value,
      current: current.basic_info.full_name.value,
    },
    {
      label: "联系邮箱",
      previous: previous.basic_info.email.value,
      current: current.basic_info.email.value,
    },
    {
      label: "所在地",
      previous: previous.basic_info.location.value,
      current: current.basic_info.location.value,
    },
    {
      label: "个人摘要",
      previous: previous.summary.value,
      current: current.summary.value,
    },
    {
      label: "教育经历",
      previous: `${previous.education.length} 项`,
      current: `${current.education.length} 项`,
    },
    {
      label: "工作经历",
      previous: `${previous.work_experience.length} 项`,
      current: `${current.work_experience.length} 项`,
    },
    {
      label: "项目经历",
      previous: `${previous.project_experience.length} 项`,
      current: `${current.project_experience.length} 项`,
    },
    {
      label: "技术技能",
      previous: previous.technical_skills.map((skill) => skill.value).join("、"),
      current: current.technical_skills.map((skill) => skill.value).join("、"),
    },
  ]
  return comparisons.filter((item) => item.previous !== item.current)
})

async function load(): Promise<void> {
  isLoading.value = true
  errorMessage.value = null
  try {
    const nextVersion = await getResumeVersion(versionId.value)
    version.value = nextVersion
    const [nextSkills, nextResume, nextVersions, nextHistory] = await Promise.all([
      listResumeVersionSkills(versionId.value),
      getResume(nextVersion.resume_id),
      listResumeVersions(nextVersion.resume_id),
      matchHistoryService
        .forResumeVersion(versionId.value, 0, 20)
        .then((result) => result.items),
    ])
    skills.value = nextSkills
    resume.value = nextResume
    versions.value = nextVersions
    matchHistory.value = nextHistory
    const jobResults = await Promise.allSettled(
      [...new Set(nextHistory.map((report) => report.job_id))].map(async (jobId) => {
        const job = await getJob(jobId)
        return [jobId, `${job.title} · ${job.company}`] as const
      }),
    )
    const nextJobLabels: Record<number, string> = {}
    for (const result of jobResults) {
      if (result.status === "fulfilled") {
        nextJobLabels[result.value[0]] = result.value[1]
      }
    }
    jobLabels.value = nextJobLabels
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

async function downloadFile(): Promise<void> {
  if (!version.value) return
  isDownloading.value = true
  errorMessage.value = null
  try {
    const blob = await downloadResumeFile(version.value.resume_id)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = resume.value?.file.original_name ?? `resume-v${version.value.version_number}`
    anchor.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isDownloading.value = false
  }
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value))
}

onMounted(load)
</script>

<template>
  <section class="space-y-6">
    <LoadingState
      v-if="isLoading"
      label="正在加载版本"
      :rows="6"
    />
    <ErrorState
      v-else-if="errorMessage && !version"
      :message="errorMessage"
      @retry="load"
    />
    <template v-else-if="version">
      <PageHeader
        eyebrow="Resume version · 版本详情"
        :title="`简历版本 ${version.version_number}`"
        description="已确认的历史版本不可覆盖，所有技能判断都可以回溯到简历原文。"
      >
        <template #actions>
          <a
            v-if="previousVersion"
            href="#version-difference"
            class="inline-flex h-10 items-center rounded-sm border bg-surface px-4 text-sm font-semibold hover:bg-muted"
          >
            <ArrowLeftRight class="mr-2 size-4" />
            与上一版本比较
          </a>
          <Button
            variant="outline"
            :disabled="isDownloading"
            @click="downloadFile"
          >
            <Download class="mr-2 size-4" />
            {{ isDownloading ? "下载中…" : "下载原文件" }}
          </Button>
          <RouterLink
            :to="{ name: 'resume-confirm', params: { resumeId: version.resume_id } }"
            class="inline-flex h-10 items-center rounded-sm bg-primary px-4 text-sm font-semibold text-white hover:bg-primary-hover"
          >
            <Plus class="mr-2 size-4" />
            创建新版本
          </RouterLink>
        </template>
      </PageHeader>

      <ErrorState
        v-if="errorMessage"
        compact
        title="操作未完成"
        :message="errorMessage"
      />

      <section class="rounded-lg border bg-surface p-5 shadow-sm">
        <div class="flex flex-wrap items-center gap-5">
          <span class="grid size-12 shrink-0 place-items-center rounded-md bg-primary text-sm font-bold text-white">
            v{{ version.version_number }}
          </span>
          <div class="min-w-48 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="font-semibold">{{ resume?.title ?? `简历 ${version.resume_id}` }}</h2>
              <StatusBadge tone="success">
                <CheckCircle2 class="mr-1 size-3.5" />
                {{ version.is_current ? "当前正式版本" : "历史正式版本" }}
              </StatusBadge>
            </div>
            <p class="mt-1 text-xs text-muted-foreground">
              基于 {{ resume?.file.original_name ?? "原始简历" }} 创建
            </p>
          </div>
          <dl class="grid grid-cols-2 gap-x-8 gap-y-3 text-xs sm:grid-cols-4">
            <div>
              <dt class="text-muted-foreground">创建日期</dt>
              <dd class="mt-1 font-semibold">{{ formatDate(version.created_at) }}</dd>
            </div>
            <div>
              <dt class="text-muted-foreground">职业方向</dt>
              <dd class="mt-1 max-w-36 truncate font-semibold">{{ positionTitle }}</dd>
            </div>
            <div>
              <dt class="text-muted-foreground">技能证据</dt>
              <dd class="mt-1 font-semibold text-success">{{ skills.length }} 项</dd>
            </div>
            <div>
              <dt class="text-muted-foreground">证据覆盖</dt>
              <dd class="mt-1 font-semibold text-success">{{ evidenceCoverage }}%</dd>
            </div>
          </dl>
        </div>
      </section>

      <nav class="flex gap-1 rounded-lg border bg-surface p-1.5 shadow-sm">
        <a
          href="#version-overview"
          class="rounded-md bg-primary-soft px-4 py-2 text-sm font-semibold text-primary"
        >
          版本概览
        </a>
        <a
          href="#skills-evidence"
          class="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          技能与证据
        </a>
        <a
          href="#version-history"
          class="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          版本历史
        </a>
        <a
          v-if="previousVersion"
          href="#version-difference"
          class="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          版本差异
        </a>
      </nav>

      <section
        id="version-overview"
        class="rounded-lg border bg-surface p-5 shadow-sm"
      >
        <div class="flex items-center justify-between gap-3">
          <div>
            <h2 class="font-semibold">核心信息与可信度</h2>
            <p class="mt-1 text-xs text-muted-foreground">
              已确认画像的关键信息摘要
            </p>
          </div>
          <Sparkles class="size-5 text-primary" />
        </div>
        <div class="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <article class="rounded-md border p-4">
            <p class="text-xs text-muted-foreground">姓名</p>
            <p class="mt-2 truncate text-sm font-semibold">
              {{ version.structured_data.basic_info.full_name.value || "未填写" }}
            </p>
            <StatusBadge
              class="mt-3"
              tone="success"
            >
              已确认
            </StatusBadge>
          </article>
          <article class="rounded-md border p-4">
            <p class="text-xs text-muted-foreground">联系邮箱</p>
            <p class="mt-2 truncate text-sm font-semibold">
              {{ version.structured_data.basic_info.email.value || "未填写" }}
            </p>
            <StatusBadge
              class="mt-3"
              tone="success"
            >
              已确认
            </StatusBadge>
          </article>
          <article class="rounded-md border p-4">
            <p class="text-xs text-muted-foreground">技能数量</p>
            <p class="mt-2 text-sm font-semibold">{{ skills.length }} 项</p>
            <StatusBadge
              class="mt-3"
              tone="info"
            >
              原文可追溯
            </StatusBadge>
          </article>
          <article class="rounded-md border p-4">
            <p class="text-xs text-muted-foreground">平均置信度</p>
            <p class="mt-2 text-sm font-semibold">{{ averageConfidence }}%</p>
            <StatusBadge
              class="mt-3"
              tone="primary"
            >
              用户已确认
            </StatusBadge>
          </article>
        </div>
        <div class="mt-4 rounded-md bg-muted/60 p-4">
          <p class="text-xs font-semibold text-muted-foreground">个人摘要</p>
          <p class="mt-2 max-h-28 overflow-hidden whitespace-pre-line text-sm leading-6">
            {{ version.structured_data.summary.value || "暂无摘要" }}
          </p>
        </div>
      </section>

      <section
        id="resume-match-history"
        class="rounded-lg border bg-surface p-5 shadow-sm"
      >
        <div class="flex items-center justify-between gap-3">
          <div>
            <h2 class="font-semibold">该版本的匹配历史</h2>
            <p class="mt-1 text-xs text-muted-foreground">
              历史报告不会因后续重算而被覆盖
            </p>
          </div>
          <Target class="size-5 text-primary" />
        </div>
        <div class="mt-5">
          <MatchHistoryList
            :reports="matchHistory"
            :job-labels="jobLabels"
            :resume-labels="resumeLabels"
            compact
          />
        </div>
      </section>

      <section
        v-if="previousVersion"
        id="version-difference"
        class="rounded-lg border bg-surface p-5 shadow-sm"
      >
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 class="font-semibold">与上一版本比较</h2>
            <p class="mt-1 text-xs text-muted-foreground">
              v{{ previousVersion.version_number }} → v{{ version.version_number }}，仅展示结构化字段变化
            </p>
          </div>
          <RouterLink
            :to="{ name: 'resume-version', params: { versionId: previousVersion.id } }"
            class="inline-flex items-center text-xs font-semibold text-primary hover:underline"
          >
            查看 v{{ previousVersion.version_number }}
            <ChevronRight class="ml-1 size-3.5" />
          </RouterLink>
        </div>

        <div
          v-if="versionDifferences.length === 0"
          class="mt-5 rounded-md border border-dashed bg-muted/50 p-5 text-sm text-muted-foreground"
        >
          两个版本的核心结构化字段没有变化。
        </div>
        <div
          v-else
          class="mt-5 overflow-hidden rounded-md border"
        >
          <div class="grid grid-cols-[8rem_minmax(0,1fr)_minmax(0,1fr)] bg-muted px-4 py-3 text-xs font-semibold text-muted-foreground">
            <span>字段</span>
            <span>v{{ previousVersion.version_number }}</span>
            <span>v{{ version.version_number }}</span>
          </div>
          <div
            v-for="difference in versionDifferences"
            :key="difference.label"
            class="grid grid-cols-[8rem_minmax(0,1fr)_minmax(0,1fr)] border-t px-4 py-3 text-sm"
          >
            <strong class="text-xs">{{ difference.label }}</strong>
            <p class="line-clamp-3 border-l pl-4 text-xs leading-5 text-danger">
              {{ difference.previous || "未填写" }}
            </p>
            <p class="line-clamp-3 border-l pl-4 text-xs leading-5 text-success">
              {{ difference.current || "未填写" }}
            </p>
          </div>
        </div>
      </section>

      <div class="grid gap-6 xl:grid-cols-3">
        <section
          id="skills-evidence"
          class="rounded-lg border bg-surface p-5 shadow-sm xl:col-span-2"
        >
          <div class="flex items-center justify-between gap-3">
            <div>
              <h2 class="font-semibold">技能与证据</h2>
              <p class="mt-1 text-xs text-muted-foreground">
                每一项能力都保留原始名称、来源定位和证据文本
              </p>
            </div>
            <ScanSearch class="size-5 text-primary" />
          </div>

          <EmptyState
            v-if="skills.length === 0"
            class="mt-5"
            compact
            title="没有技能证据"
            description="该版本没有带原文证据的已确认技能。"
          />
          <ul
            v-else
            class="mt-5 grid gap-3 sm:grid-cols-2"
          >
            <li
              v-for="skill in skills"
              :key="skill.id"
              class="rounded-md border p-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <strong class="text-sm">{{ skill.normalized_name }}</strong>
                    <StatusBadge
                      v-if="skill.category"
                      tone="neutral"
                    >
                      {{ skill.category }}
                    </StatusBadge>
                  </div>
                  <p class="mt-1 text-xs text-muted-foreground">
                    原始名称：{{ skill.raw_name }}
                  </p>
                </div>
                <span
                  class="shrink-0 rounded-full px-2 py-1 text-xs font-semibold"
                  :class="
                    skill.confidence >= 0.8
                      ? 'bg-success-soft text-success'
                      : 'bg-warning-soft text-warning'
                  "
                >
                  {{ Math.round(skill.confidence * 100) }}%
                </span>
              </div>
              <blockquote class="mt-3 rounded-sm bg-muted p-3 text-xs leading-5">
                {{ skill.evidence_text }}
              </blockquote>
              <p class="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
                <BadgeCheck class="size-3.5 text-success" />
                来源：{{ skill.source_location.label }}
              </p>
            </li>
          </ul>
        </section>

        <aside
          id="version-history"
          class="space-y-4"
        >
          <section class="rounded-lg border bg-surface p-5 shadow-sm">
            <div class="flex items-center justify-between gap-3">
              <div>
                <h2 class="font-semibold">版本历史</h2>
                <p class="mt-1 text-xs text-muted-foreground">
                  共 {{ versions.length }} 个不可覆盖版本
                </p>
              </div>
              <History class="size-5 text-primary" />
            </div>
            <ol class="mt-5 space-y-4">
              <li
                v-for="historyVersion in versions"
                :key="historyVersion.id"
                class="flex gap-3"
              >
                <span
                  class="grid size-8 shrink-0 place-items-center rounded-full"
                  :class="
                    historyVersion.id === version.id
                      ? 'bg-primary text-white'
                      : 'bg-muted text-muted-foreground'
                  "
                >
                  <FileCheck2 class="size-4" />
                </span>
                <div class="min-w-0 flex-1">
                  <div class="flex items-center justify-between gap-2">
                    <strong class="text-xs">v{{ historyVersion.version_number }}</strong>
                    <StatusBadge
                      v-if="historyVersion.id === version.id"
                      tone="success"
                    >
                      当前
                    </StatusBadge>
                  </div>
                  <p class="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
                    <CalendarDays class="size-3" />
                    {{ formatDate(historyVersion.created_at) }}
                  </p>
                  <RouterLink
                    v-if="historyVersion.id !== version.id"
                    :to="{ name: 'resume-version', params: { versionId: historyVersion.id } }"
                    class="mt-2 flex items-center gap-1 text-xs font-semibold text-primary hover:underline"
                  >
                    查看版本
                    <ChevronRight class="size-3" />
                  </RouterLink>
                </div>
              </li>
            </ol>
          </section>

          <section class="rounded-lg border border-primary/15 bg-primary-soft p-4">
            <div class="flex items-start gap-3">
              <Layers3 class="mt-0.5 size-5 shrink-0 text-primary" />
              <p class="text-xs leading-5 text-muted-foreground">
                创建新版本不会覆盖当前版本。每次确认都会保留独立的结构化数据和技能证据。
              </p>
            </div>
          </section>
        </aside>
      </div>

      <RouterLink
        :to="{ name: 'resume-status', params: { resumeId: version.resume_id } }"
        class="inline-flex items-center text-sm font-semibold text-primary hover:underline"
      >
        <ArrowLeft class="mr-2 size-4" />
        返回简历处理状态
      </RouterLink>
    </template>
    <EmptyState
      v-else
      title="未找到简历版本"
      description="该版本可能已删除，或当前账号没有访问权限。"
    />
  </section>
</template>
