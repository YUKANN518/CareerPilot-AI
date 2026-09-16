<script setup lang="ts">
import {
  Banknote,
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  ExternalLink,
  FileSpreadsheet,
  Heart,
  MapPin,
  Plus,
  Search,
  Sparkles,
  SlidersHorizontal,
} from "@lucide/vue"
import { computed, onMounted, reactive, ref } from "vue"
import { useRouter } from "vue-router"

import { getApiErrorMessage } from "@/api/auth"
import { applicationService } from "@/api/applications"
import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import LoadingState from "@/components/domain/LoadingState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import Pagination from "@/components/domain/Pagination.vue"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { FormField } from "@/components/ui/form-field"
import { Input } from "@/components/ui/input"
import { StatusBadge } from "@/components/ui/status-badge"
import { jobService } from "@/services/jobs"
import type {
  Job,
  JobFilters,
  JobSort,
  ManualJobPreview,
  UserJobInput,
} from "@/types/job"

const router = useRouter()
const jobs = ref<Job[]>([])
const total = ref(0)
const loading = ref(true)
const errorMessage = ref<string | null>(null)
const actionError = ref<string | null>(null)
const actionMessage = ref<string | null>(null)
const changingFavorite = ref<number | null>(null)
const applicationBusy = ref<number | null>(null)
const importOpen = ref(false)
const importMode = ref<"manual" | "csv">("manual")
const importing = ref(false)
const manualPreview = ref<ManualJobPreview | null>(null)

const filters = reactive({
  search: "",
  location: "",
  company: "",
  employmentType: "",
  experienceLevel: "",
  publishedWithinDays: "",
  sort: "published_desc" as JobSort,
  offset: 0,
  limit: 20,
})

const manualForm = reactive<UserJobInput>({
  title: "",
  company: "",
  location: "",
  description: "",
  employment_type: "",
  experience_level: "",
  education_requirement: "",
  source_url: "",
  skills: [],
})
const manualSkills = ref("")
const csvContent = ref("title,company,description\n")

const activeFilterCount = computed(
  () =>
    [
      filters.search,
      filters.location,
      filters.company,
      filters.employmentType,
      filters.experienceLevel,
      filters.publishedWithinDays,
    ].filter(Boolean).length,
)

function publishedAfter(): string | undefined {
  const days = Number(filters.publishedWithinDays)
  if (!days) return undefined
  const value = new Date()
  value.setDate(value.getDate() - days)
  return value.toISOString()
}

function query(): JobFilters {
  const base: JobFilters = {
    search: filters.search.trim() || undefined,
    location: filters.location.trim() || undefined,
    company: filters.company.trim() || undefined,
    employment_type: filters.employmentType || undefined,
    experience_level: filters.experienceLevel || undefined,
    published_after: publishedAfter(),
    sort: filters.sort,
    offset: filters.offset,
    limit: filters.limit,
    visibility: "ALL",
  }
  return base
}

async function load(resetPage = false): Promise<void> {
  if (resetPage) filters.offset = 0
  loading.value = true
  errorMessage.value = null
  try {
    const result = await jobService.listJobs(query())
    jobs.value = result.items
    total.value = result.total
  } catch (error) {
    jobs.value = []
    total.value = 0
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

function resetFilters(): void {
  filters.search = ""
  filters.location = ""
  filters.company = ""
  filters.employmentType = ""
  filters.experienceLevel = ""
  filters.publishedWithinDays = ""
  filters.sort = "published_desc"
  void load(true)
}

async function toggleFavorite(job: Job): Promise<void> {
  changingFavorite.value = job.id
  actionError.value = null
  try {
    await jobService.setJobFavorite(job.id, !job.is_favorite)
    job.is_favorite = !job.is_favorite
    actionMessage.value = job.is_favorite ? "岗位已收藏。" : "已取消收藏。"
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    changingFavorite.value = null
  }
}

async function addToApplications(job: Job): Promise<void> {
  if (applicationBusy.value !== null) return
  applicationBusy.value = job.id
  actionError.value = null
  try {
    await applicationService.create({ job_id: job.id, status: "SAVED" })
    actionMessage.value = `已加入投递管理：${job.title}`
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    applicationBusy.value = null
  }
}

function isSafeExternalUrl(url: string | null | undefined): boolean {
  if (!url) return false
  try {
    const parsed = new URL(url)
    return parsed.protocol === "http:" || parsed.protocol === "https:"
  } catch {
    return false
  }
}

function sourceBadgeTone(sourceName: string): "primary" | "info" | "neutral" {
  const upper = sourceName.toUpperCase()
  if (upper === "JOBSDB") return "primary"
  if (upper === "OFFERTODAY") return "info"
  return "neutral"
}

function sourceBadgeLabel(sourceName: string): string {
  const upper = sourceName.toUpperCase()
  if (upper === "JOBSDB") return "JobsDB"
  if (upper === "OFFERTODAY") return "OfferToday"
  return sourceName
}

function openImport(mode: "manual" | "csv"): void {
  importMode.value = mode
  manualPreview.value = null
  importOpen.value = true
  actionError.value = null
}

async function submitImport(): Promise<void> {
  importing.value = true
  actionError.value = null
  try {
    let result
    if (importMode.value === "manual") {
      const input: UserJobInput = {
        ...manualForm,
        skills: manualSkills.value
          .split(/[,，]/)
          .map((value) => value.trim())
          .filter(Boolean),
      }
      if (!manualPreview.value) {
        manualPreview.value = await jobService.previewManualJob(input)
        return
      }
      result = await jobService.importManualJob(input)
    } else if (importMode.value === "csv") {
      result = await jobService.importJobCsv({
        csv_content: csvContent.value,
        delimiter: ",",
        field_mapping: {
          title: "title",
          company: "company",
          description: "description",
        },
      })
    }
    if (!result) return
    actionMessage.value = `导入完成：新增 ${result.imported_count} 条，重复 ${result.duplicate_count} 条，失败 ${result.failed_count} 条。`
    importOpen.value = false
    const imported = result.items[0]
    if (importMode.value === "manual" && imported) {
      await router.push({ name: "job-detail", params: { jobId: imported.id } })
    } else {
      await load(true)
    }
  } catch (error) {
    actionError.value =
      error instanceof Error && !("response" in error)
        ? error.message
        : getApiErrorMessage(error)
  } finally {
    importing.value = false
  }
}

function formatSalary(job: Job): string {
  if (job.salary_summary) return job.salary_summary
  if (!job.salary_min && !job.salary_max) return "未提供"
  const range =
    job.salary_min && job.salary_max
      ? `${Number(job.salary_min).toLocaleString()}–${Number(job.salary_max).toLocaleString()}`
      : Number(job.salary_min ?? job.salary_max).toLocaleString()
  return `${range} ${job.currency ?? ""}`.trim()
}

function formatDate(value: string | null): string {
  return value
    ? new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium" }).format(new Date(value))
    : "发布时间未知"
}

function startMatch(job: Job): void {
  void router.push({ name: "match-new", query: { jobId: String(job.id) } })
}

onMounted(() => load())
</script>

<template>
  <section class="space-y-6">
    <PageHeader
      eyebrow="Target job analysis"
      title="目标岗位"
      description="粘贴职位描述或批量导入 CSV，确认岗位要求后选择简历生成人岗匹配报告。"
    >
      <template #actions>
        <Button @click="openImport('manual')">
          <Plus class="mr-2 size-4" />
          输入岗位详情并匹配
        </Button>
        <Button
          variant="outline"
          @click="openImport('csv')"
        >
          <FileSpreadsheet class="mr-2 size-4" />
          导入 CSV
        </Button>
      </template>
    </PageHeader>

    <p
      v-if="actionMessage"
      class="rounded-md border border-success/20 bg-success-soft p-3 text-sm text-success"
      role="status"
    >
      {{ actionMessage }}
    </p>
    <ErrorState
      v-if="actionError"
      compact
      title="操作未完成"
      :message="actionError"
    />

    <section class="rounded-lg border bg-surface p-4 shadow-sm">
      <form
        class="flex flex-col gap-3 lg:flex-row"
        @submit.prevent="load(true)"
      >
        <label class="relative min-w-0 flex-1">
          <span class="sr-only">搜索目标岗位</span>
          <Search class="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
          <Input
            v-model="filters.search"
            class="pl-9"
            placeholder="搜索职位、公司或岗位描述"
          />
        </label>
        <Button type="submit">搜索目标岗位</Button>
      </form>
    </section>

    <div class="grid items-start gap-6 xl:grid-cols-[17rem_minmax(0,1fr)]">
      <aside class="rounded-lg border bg-surface p-5 shadow-sm xl:sticky xl:top-24">
        <div class="flex items-center justify-between gap-3">
          <h2 class="flex items-center gap-2 text-sm font-semibold">
            <SlidersHorizontal class="size-4 text-primary" />
            筛选条件
          </h2>
          <button
            v-if="activeFilterCount"
            type="button"
            class="text-xs font-semibold text-primary hover:underline"
            @click="resetFilters"
          >
            清空 {{ activeFilterCount }} 项
          </button>
        </div>
        <div class="mt-5 space-y-4">
          <FormField
            label="地点"
            for-id="job-location"
          >
            <Input
              id="job-location"
              v-model="filters.location"
              placeholder="例如：上海"
            />
          </FormField>
          <FormField
            label="公司"
            for-id="job-company"
          >
            <Input
              id="job-company"
              v-model="filters.company"
              placeholder="公司名称"
            />
          </FormField>
          <FormField
            label="工作类型"
            for-id="employment-type"
          >
            <select
              id="employment-type"
              v-model="filters.employmentType"
              class="h-10 w-full rounded-sm border bg-surface px-3 text-sm"
            >
              <option value="">全部</option>
              <option value="FULL_TIME">全职</option>
              <option value="PART_TIME">兼职</option>
              <option value="CONTRACT">合同</option>
              <option value="INTERNSHIP">实习</option>
              <option value="REMOTE">远程</option>
            </select>
          </FormField>
          <FormField
            label="经验要求"
            for-id="experience-level"
          >
            <select
              id="experience-level"
              v-model="filters.experienceLevel"
              class="h-10 w-full rounded-sm border bg-surface px-3 text-sm"
            >
              <option value="">全部</option>
              <option value="ENTRY">初级</option>
              <option value="MID">中级</option>
              <option value="SENIOR">高级</option>
              <option value="LEAD">专家 / 负责人</option>
            </select>
          </FormField>
          <FormField
            label="发布时间"
            for-id="published-within"
          >
            <select
              id="published-within"
              v-model="filters.publishedWithinDays"
              class="h-10 w-full rounded-sm border bg-surface px-3 text-sm"
            >
              <option value="">不限</option>
              <option value="1">最近 24 小时</option>
              <option value="7">最近 7 天</option>
              <option value="30">最近 30 天</option>
            </select>
          </FormField>
          <Button
            class="w-full"
            @click="load(true)"
          >
            应用筛选
          </Button>
        </div>
      </aside>

      <main class="min-w-0">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
          <p class="text-sm text-muted-foreground">
            共 <strong class="text-foreground">{{ total }}</strong> 个目标岗位
          </p>
          <label class="flex items-center gap-2 text-xs font-medium">
            排序
            <select
              v-model="filters.sort"
              class="h-9 rounded-sm border bg-surface px-3 text-sm"
              @change="load(true)"
            >
              <option value="published_desc">最新发布</option>
              <option value="published_asc">最早发布</option>
              <option value="salary_desc">薪资从高到低</option>
              <option value="title_asc">职位名称</option>
              <option value="created_desc">最近入库</option>
            </select>
          </label>
          <label class="flex items-center gap-2 text-xs font-medium">
            每页
            <select
              v-model.number="filters.limit"
              class="h-9 rounded-sm border bg-surface px-3 text-sm"
              @change="load(true)"
            >
              <option :value="20">20</option>
              <option :value="50">50</option>
            </select>
          </label>
        </div>

        <LoadingState
          v-if="loading"
          label="正在加载目标岗位"
          :rows="5"
        />
        <ErrorState
          v-else-if="errorMessage"
          :message="errorMessage"
          @retry="load()"
        />
        <EmptyState
          v-else-if="jobs.length === 0"
          title="没有符合条件的目标岗位"
          description="你还没有保存目标岗位。输入职位详情或导入 CSV 后即可选择简历并匹配。"
        >
          <Button
            variant="outline"
            @click="resetFilters"
          >
            清空筛选
          </Button>
        </EmptyState>
        <template v-else>
          <ul class="space-y-3">
            <li
              v-for="job in jobs"
              :key="job.id"
              class="rounded-lg border bg-surface p-5 shadow-sm transition-colors hover:border-primary/35"
              data-testid="job-card"
            >
              <div class="flex gap-4">
                <span class="grid size-11 shrink-0 place-items-center rounded-md bg-primary-soft text-primary">
                  <BriefcaseBusiness class="size-5" />
                </span>
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <RouterLink
                        :to="{ name: 'job-detail', params: { jobId: job.id } }"
                        class="font-semibold hover:text-primary"
                      >
                        {{ job.title }}
                      </RouterLink>
                      <p class="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Building2 class="size-3.5" />
                        {{ job.company }}
                      </p>
                    </div>
                    <div class="flex items-center gap-2">
                      <StatusBadge
                        v-if="job.is_summary_only"
                        :tone="sourceBadgeTone(job.source_name)"
                        data-testid="job-source-badge"
                      >
                        {{ sourceBadgeLabel(job.source_name) }}
                      </StatusBadge>
                      <StatusBadge
                        v-if="job.is_summary_only"
                        tone="warning"
                        data-testid="job-summary-badge"
                      >
                        公开快照
                      </StatusBadge>
                      <button
                        type="button"
                        class="grid size-9 place-items-center rounded-sm border text-muted-foreground hover:bg-muted hover:text-danger disabled:opacity-50"
                        :disabled="changingFavorite === job.id"
                        :aria-label="job.is_favorite ? '取消收藏' : '收藏岗位'"
                        @click="toggleFavorite(job)"
                      >
                        <Heart
                          class="size-4"
                          :class="{ 'fill-danger text-danger': job.is_favorite }"
                        />
                      </button>
                    </div>
                  </div>

                  <div class="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs text-muted-foreground">
                    <span class="flex items-center gap-1.5">
                      <MapPin class="size-3.5" />
                      {{ job.location || "未提供" }}
                    </span>
                    <span class="flex items-center gap-1.5">
                      <Banknote class="size-3.5" />
                      {{ formatSalary(job) }}
                    </span>
                    <span class="flex items-center gap-1.5">
                      <BriefcaseBusiness class="size-3.5" />
                      {{ job.employment_type || "未提供" }} ·
                      {{ job.experience_level || "未提供" }}
                    </span>
                    <span class="flex items-center gap-1.5">
                      <CalendarDays class="size-3.5" />
                      {{ formatDate(job.published_at) }}
                    </span>
                  </div>

                  <p
                    class="mt-4 line-clamp-2 text-sm leading-6 text-muted-foreground"
                    data-testid="job-summary-text"
                  >
                    {{ job.summary || job.description }}
                  </p>
                  <div
                    v-if="job.skills.length"
                    class="mt-3 flex flex-wrap gap-1.5"
                  >
                    <StatusBadge
                      v-for="skill in job.skills"
                      :key="skill"
                      tone="primary"
                    >
                      {{ skill }}
                    </StatusBadge>
                  </div>
                  <div class="mt-3 flex flex-wrap gap-1.5">
                    <StatusBadge tone="neutral">
                      学历：{{ job.education_requirement || "未提供" }}
                    </StatusBadge>
                    <StatusBadge tone="neutral">
                      语言：{{ job.language_requirements.join("、") || "未提供" }}
                    </StatusBadge>
                    <StatusBadge
                      v-if="job.is_summary_only"
                      tone="neutral"
                      data-testid="job-completeness-badge"
                    >
                      完整度 {{ job.data_completeness }}%
                    </StatusBadge>
                    <StatusBadge :tone="job.status === 'ACTIVE' ? 'success' : 'neutral'">
                      {{ job.status }}
                    </StatusBadge>
                  </div>

                  <p
                    v-if="job.is_summary_only"
                    class="mt-3 rounded-md border border-warning/20 bg-warning-soft p-2.5 text-xs text-warning"
                    data-testid="job-login-hint"
                  >
                    来源可能存在登录或访问限制，请以原页面显示的完整职位信息为准。
                  </p>

                  <div class="mt-4 flex flex-wrap items-center justify-between gap-3 border-t pt-4">
                    <div class="text-xs text-muted-foreground">
                      <p>
                        来源：<strong class="text-foreground">{{ sourceBadgeLabel(job.source_name) }}</strong>
                        · {{ job.source_type }}
                      </p>
                      <p class="mt-1">
                        <template v-if="job.is_public_snapshot">
                          公开快照 · 最后核验 {{ formatDate(job.last_verified_at) }} ·
                        </template>
                        <template v-else>
                          我的私人岗位 · 保存于 {{ formatDate(job.created_at) }} ·
                        </template>
                        信息完整度 {{ job.data_completeness }}%
                      </p>
                    </div>
                    <div class="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        :disabled="applicationBusy === job.id"
                        data-testid="job-add-application"
                        @click="addToApplications(job)"
                      >
                        <BriefcaseBusiness class="mr-2 size-3.5" />
                        {{ applicationBusy === job.id ? "加入中…" : "加入投递" }}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        data-testid="job-match-button"
                        @click="startMatch(job)"
                      >
                        <Sparkles class="mr-2 size-3.5" />
                        与我的简历匹配
                      </Button>
                      <a
                        v-if="isSafeExternalUrl(job.source_url)"
                        :href="job.source_url ?? undefined"
                        target="_blank"
                        rel="noopener noreferrer"
                        data-testid="job-source-link"
                      >
                        <Button
                          size="sm"
                          variant="outline"
                        >
                          <ExternalLink class="mr-2 size-3.5" />
                          查看原岗位
                        </Button>
                      </a>
                      <Button
                        v-else
                        size="sm"
                        variant="outline"
                        disabled
                        data-testid="job-source-link-disabled"
                      >
                        <ExternalLink class="mr-2 size-3.5" />
                        原岗位链接暂不可用
                      </Button>
                      <RouterLink
                        :to="{ name: 'job-detail', params: { jobId: job.id } }"
                      >
                        <Button size="sm">查看详情</Button>
                      </RouterLink>
                    </div>
                  </div>
                </div>
              </div>
            </li>
          </ul>
          <Pagination
            class="mt-5"
            :offset="filters.offset"
            :limit="filters.limit"
            :total="total"
            label="岗位分页"
            @change="
              filters.offset = $event;
              load()
            "
          />
        </template>
      </main>
    </div>

    <Dialog
      :open="importOpen"
      :title="
        importMode === 'manual'
          ? manualPreview
            ? '确认目标岗位信息'
            : '输入目标岗位详情'
          : '导入目标岗位 CSV'
      "
      description="保存后的目标岗位仅自己可见；系统只规范化你提供的信息，不会补全缺失的事实。"
      size="lg"
      @close="importOpen = false"
    >
      <form
        class="space-y-5"
        @submit.prevent="submitImport"
      >
        <div
          v-if="importMode === 'manual' && !manualPreview"
          class="grid gap-4 md:grid-cols-2"
        >
          <FormField
            label="岗位标题"
            for-id="manual-title"
            required
          >
            <Input
              id="manual-title"
              v-model="manualForm.title"
            />
          </FormField>
          <FormField
            label="公司"
            for-id="manual-company"
            hint="可选"
          >
            <Input
              id="manual-company"
              v-model="manualForm.company"
            />
          </FormField>
          <FormField
            label="地点"
            for-id="manual-location"
          >
            <Input
              id="manual-location"
              v-model="manualForm.location"
            />
          </FormField>
          <FormField
            label="来源链接"
            for-id="manual-source-url"
          >
            <Input
              id="manual-source-url"
              v-model="manualForm.source_url"
              type="url"
            />
          </FormField>
          <FormField
            label="技能（逗号分隔）"
            for-id="manual-skills"
          >
            <Input
              id="manual-skills"
              v-model="manualSkills"
              placeholder="Python, SQL"
            />
          </FormField>
          <FormField
            class="md:col-span-2"
            label="职位描述"
            for-id="manual-description"
          >
            <textarea
              id="manual-description"
              v-model="manualForm.description"
              class="min-h-28 w-full rounded-sm border bg-surface p-3 text-sm"
            />
          </FormField>
          <FormField
            class="md:col-span-2"
            label="任职要求"
            for-id="manual-requirements"
            hint="职位描述或任职要求至少填写一项"
          >
            <textarea
              id="manual-requirements"
              v-model="manualForm.requirements"
              class="min-h-28 w-full rounded-sm border bg-surface p-3 text-sm"
            />
          </FormField>
        </div>
        <section
          v-else-if="importMode === 'manual' && manualPreview"
          class="space-y-4 rounded-lg border bg-muted/30 p-4 text-sm"
          data-testid="manual-job-preview"
        >
          <div class="flex items-start gap-3">
            <Sparkles class="mt-0.5 size-5 text-primary" />
            <div>
              <h3 class="font-semibold">已完成字段规范化</h3>
              <p class="mt-1 text-muted-foreground">
                请确认以下内容。未提供的公司、薪资、地点等信息不会被系统编造。
              </p>
            </div>
          </div>
          <dl class="grid gap-3 sm:grid-cols-2">
            <div><dt class="text-xs text-muted-foreground">职位名称</dt><dd class="mt-1 font-medium">{{ manualPreview.title }}</dd></div>
            <div><dt class="text-xs text-muted-foreground">公司</dt><dd class="mt-1 font-medium">{{ manualPreview.company }}</dd></div>
            <div><dt class="text-xs text-muted-foreground">地点</dt><dd class="mt-1 font-medium">{{ manualPreview.location || '未提供' }}</dd></div>
            <div><dt class="text-xs text-muted-foreground">工作类型</dt><dd class="mt-1 font-medium">{{ manualPreview.employment_type || '未提供' }}</dd></div>
          </dl>
          <div>
            <p class="text-xs text-muted-foreground">职位描述</p>
            <p class="mt-1 whitespace-pre-line leading-6">{{ manualPreview.description }}</p>
          </div>
          <div v-if="manualPreview.requirements">
            <p class="text-xs text-muted-foreground">任职要求</p>
            <p class="mt-1 whitespace-pre-line leading-6">{{ manualPreview.requirements }}</p>
          </div>
        </section>
        <FormField
          v-else-if="importMode === 'csv'"
          label="CSV 内容"
          for-id="job-csv"
          required
          hint="表头至少包含 title、company、description；每行保存为一个目标岗位。"
        >
          <textarea
            id="job-csv"
            v-model="csvContent"
            class="min-h-48 w-full rounded-sm border bg-surface p-3 font-mono text-sm"
            placeholder="title,company,description"
          />
        </FormField>
        <div class="flex justify-end gap-2 border-t pt-5">
          <Button
            variant="outline"
            @click="manualPreview ? (manualPreview = null) : (importOpen = false)"
          >
            {{ manualPreview ? "返回修改" : "取消" }}
          </Button>
          <Button
            type="submit"
            :disabled="importing"
          >
            {{
              importing
                ? "处理中…"
                : importMode === "manual"
                  ? manualPreview
                    ? "确认保存并选择简历"
                    : "解析并检查"
                  : "导入 CSV"
            }}
          </Button>
        </div>
      </form>
    </Dialog>
  </section>
</template>
