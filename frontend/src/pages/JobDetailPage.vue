<script setup lang="ts">
import {
  ArrowLeft,
  Banknote,
  BriefcaseBusiness,
  Building2,
  ExternalLink,
  FileCheck2,
  FileText,
  Heart,
  History,
  MapPin,
  Pencil,
  Sparkles,
  Trash2,
} from "@lucide/vue"
import { computed, reactive, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getApiErrorMessage } from "@/api/auth"
import { applicationService } from "@/api/applications"
import { createResumeOptimization } from "@/api/resume-optimizations"
import { listResumes, listResumeVersions } from "@/api/resumes"
import ConfirmDialog from "@/components/domain/ConfirmDialog.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import MatchHistoryList from "@/components/domain/MatchHistoryList.vue"
import LoadingState from "@/components/domain/LoadingState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { FormField } from "@/components/ui/form-field"
import { Input } from "@/components/ui/input"
import { StatusBadge } from "@/components/ui/status-badge"
import { jobService } from "@/services/jobs"
import { matchHistoryService, matchRunService } from "@/services/matching"
import type { Job, UserJobUpdate } from "@/types/job"
import type { MatchReport } from "@/types/matching"
import type { Resume, ResumeVersion } from "@/types/resume"

const route = useRoute()
const router = useRouter()
const job = ref<Job | null>(null)
const resumeVersions = ref<Array<{ version: ResumeVersion; resume: Resume }>>([])
const selectedVersionId = ref("")
const matchHistory = ref<MatchReport[]>([])
const selectedHistoryReport = ref<MatchReport | null>(null)
const recalculatingId = ref<number | null>(null)
const recalculateDialog = ref<InstanceType<typeof ConfirmDialog> | null>(null)
const privateDeleteDialog = ref<InstanceType<typeof ConfirmDialog> | null>(null)
const loading = ref(true)
const errorMessage = ref<string | null>(null)
const favoriteBusy = ref(false)
const applicationBusy = ref(false)
const applicationError = ref<string | null>(null)
const optimizationBusy = ref(false)
const optimizationError = ref<string | null>(null)
const privateEditOpen = ref(false)
const privateEditBusy = ref(false)
const privateEditError = ref<string | null>(null)
const privateEditForm = reactive<UserJobUpdate>({
  title: "",
  company: "",
  description: "",
  requirements: "",
})
const isPrivateJob = computed(
  () => job.value?.source_id === null && job.value.source_type.startsWith("USER_"),
)
const jobLabels = computed<Record<number, string>>(() =>
  job.value ? { [job.value.id]: `${job.value.title} · ${job.value.company}` } : {},
)
const resumeLabels = computed<Record<number, string>>(() =>
  Object.fromEntries(
    resumeVersions.value.map(({ resume, version }) => [
      version.id,
      `${resume.title} · 正式版本 v${version.version_number}`,
    ]),
  ),
)

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    const jobId = Number(route.params.jobId)
    job.value = await jobService.getJob(jobId)
    const [resumes, history] = await Promise.all([
      listResumes(),
      matchHistoryService.forJob(jobId, 0, 10),
    ])
    const groups = await Promise.all(
      resumes
        .filter((resume) => resume.status === "CONFIRMED")
        .map(async (resume) => ({
          resume,
          versions: await listResumeVersions(resume.id),
        })),
    )
    resumeVersions.value = groups.flatMap(({ resume, versions }) =>
      versions
        .filter((version) => version.is_confirmed)
        .map((version) => ({ resume, version })),
    )
    selectedVersionId.value = String(resumeVersions.value[0]?.version.id ?? "")
    matchHistory.value = history.items
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

async function startMatch(): Promise<void> {
  if (!job.value || !selectedVersionId.value) return
  await router.push({
    name: "match-new",
    query: {
      jobId: String(job.value.id),
      resumeVersionId: selectedVersionId.value,
    },
  })
}

function requestRecalculate(report: MatchReport): void {
  selectedHistoryReport.value = report
  recalculateDialog.value?.open()
}

async function recalculate(): Promise<void> {
  if (!selectedHistoryReport.value || recalculatingId.value !== null) return
  recalculatingId.value = selectedHistoryReport.value.id
  try {
    const run = await matchRunService.create({
      resume_version_id: selectedHistoryReport.value.resume_version_id,
      job_id: selectedHistoryReport.value.job_id,
      scoring_version: selectedHistoryReport.value.scoring_version,
    })
    await router.push({
      name: "match-processing",
      params: { runId: run.run_id },
    })
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    recalculatingId.value = null
  }
}

async function toggleFavorite(): Promise<void> {
  if (!job.value) return
  favoriteBusy.value = true
  try {
    await jobService.setJobFavorite(job.value.id, !job.value.is_favorite)
    job.value.is_favorite = !job.value.is_favorite
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    favoriteBusy.value = false
  }
}

async function addToApplications(): Promise<void> {
  if (!job.value || applicationBusy.value) return
  applicationBusy.value = true
  applicationError.value = null
  try {
    await applicationService.create({ job_id: job.value.id, status: "SAVED" })
    await router.push({ name: "applications" })
  } catch (error) {
    applicationError.value = getApiErrorMessage(error)
  } finally {
    applicationBusy.value = false
  }
}

function openPrivateEdit(): void {
  if (!job.value || !isPrivateJob.value) return
  privateEditForm.title = job.value.title
  privateEditForm.company = job.value.company === "未提供" ? "" : job.value.company
  privateEditForm.description = job.value.description
  privateEditForm.requirements = job.value.requirements ?? ""
  privateEditError.value = null
  privateEditOpen.value = true
}

async function savePrivateEdit(): Promise<void> {
  if (!job.value || privateEditBusy.value) return
  privateEditBusy.value = true
  privateEditError.value = null
  try {
    job.value = await jobService.updatePrivateJob(job.value.id, privateEditForm)
    privateEditOpen.value = false
  } catch (error) {
    privateEditError.value = getApiErrorMessage(error)
  } finally {
    privateEditBusy.value = false
  }
}

async function deletePrivateJob(): Promise<void> {
  if (!job.value || !isPrivateJob.value) return
  try {
    await jobService.deletePrivateJob(job.value.id)
    await router.push({ name: "jobs" })
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  }
}

async function optimizeResume(): Promise<void> {
  if (!job.value || optimizationBusy.value) return
  const versionId = Number(selectedVersionId.value)
  if (!versionId) {
    optimizationError.value = "请先选择一个已确认的简历版本。"
    return
  }
  const report = matchHistory.value.find(
    (item) =>
      item.job_id === job.value!.id &&
      item.resume_version_id === versionId &&
      item.status === "SUCCESS",
  )
  if (!report) {
    optimizationError.value = "请先对该简历版本执行匹配分析，生成成功的匹配报告后再优化简历。"
    return
  }
  optimizationBusy.value = true
  optimizationError.value = null
  try {
    const optimization = await createResumeOptimization({
      resume_version_id: versionId,
      job_id: job.value.id,
      match_report_id: report.id,
    })
    await router.push({
      name: "resume-optimization-detail",
      params: { optimizationId: optimization.id },
    })
  } catch (error) {
    optimizationError.value = getApiErrorMessage(error)
  } finally {
    optimizationBusy.value = false
  }
}

function salary(value: Job): string {
  if (value.salary_summary) return value.salary_summary
  if (!value.salary_min && !value.salary_max) return "未提供"
  const range =
    value.salary_min && value.salary_max
      ? `${Number(value.salary_min).toLocaleString()}–${Number(value.salary_max).toLocaleString()}`
      : Number(value.salary_min ?? value.salary_max).toLocaleString()
  return `${range} ${value.currency ?? ""}`.trim()
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

function sourceBadgeLabel(sourceName: string): string {
  const upper = sourceName.toUpperCase()
  if (upper === "JOBSDB") return "JobsDB"
  if (upper === "OFFERTODAY") return "OfferToday"
  return sourceName
}

function date(value: string | null): string {
  return value
    ? new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "未提供"
}

watch(
  () => route.params.jobId,
  () => {
    void load()
  },
  { immediate: true },
)
</script>

<template>
  <section class="space-y-6">
    <RouterLink
      :to="{ name: 'jobs' }"
      class="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"
    >
      <ArrowLeft class="size-4" />
      返回目标岗位
    </RouterLink>

    <LoadingState
      v-if="loading"
      label="正在加载岗位详情"
      :rows="6"
    />
    <ErrorState
      v-else-if="errorMessage || !job"
      :message="errorMessage ?? '岗位不存在或无权访问。'"
      @retry="load"
    />
    <template v-else>
      <PageHeader
        eyebrow="岗位详情"
        :title="job.title"
        :description="`${job.company} · ${job.location || '地点未注明'}`"
      >
        <template #actions>
          <Button
            variant="outline"
            :disabled="applicationBusy"
            @click="addToApplications"
          >
            <BriefcaseBusiness class="mr-2 size-4" />
            {{ applicationBusy ? "加入中…" : "加入求职进度" }}
          </Button>
          <Button
            variant="outline"
            :disabled="favoriteBusy"
            @click="toggleFavorite"
          >
            <Heart
              class="mr-2 size-4"
              :class="{ 'fill-danger text-danger': job.is_favorite }"
            />
            {{ job.is_favorite ? "取消收藏" : "收藏岗位" }}
          </Button>
          <Button
            v-if="isPrivateJob"
            variant="outline"
            @click="openPrivateEdit"
          >
            <Pencil class="mr-2 size-4" />
            编辑私人岗位
          </Button>
          <Button
            v-if="isPrivateJob"
            variant="outline"
            class="text-danger"
            @click="privateDeleteDialog?.open()"
          >
            <Trash2 class="mr-2 size-4" />
            删除私人岗位
          </Button>
          <a
            v-if="isSafeExternalUrl(job.source_url)"
            :href="job.source_url ?? undefined"
            target="_blank"
            rel="noopener noreferrer"
            data-testid="job-detail-source-link"
          >
            <Button>
              <ExternalLink class="mr-2 size-4" />
              打开原始来源
            </Button>
          </a>
          <Button
            v-else
            disabled
            data-testid="job-detail-source-link-disabled"
          >
            <ExternalLink class="mr-2 size-4" />
            原岗位链接暂不可用
          </Button>
        </template>
      </PageHeader>

      <div
        v-if="job.is_summary_only"
        class="rounded-lg border border-warning/30 bg-warning-soft p-4 text-sm text-warning"
        data-testid="job-detail-summary-warning"
      >
        <p class="font-semibold">当前岗位为已合规入库的公开快照</p>
        <p class="mt-1">
          匹配结果基于有限信息，仅供初步筛选。来源可能存在登录或访问限制，请以原招聘平台的完整岗位描述为准。
        </p>
        <p class="mt-1 text-xs">
          数据完整度：{{ job.data_completeness }}% ·
          最后核验：{{ date(job.last_verified_at) }}
        </p>
      </div>

      <p
        v-if="applicationError"
        class="rounded-md border border-danger/20 bg-danger-soft p-3 text-sm text-danger"
        role="alert"
      >
        {{ applicationError }}
      </p>

      <div class="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <main class="space-y-5">
          <section
            id="job-match-entry"
            class="rounded-lg border border-primary/20 bg-surface p-6 shadow-sm"
          >
            <div class="flex items-start gap-3">
              <span class="grid size-10 shrink-0 place-items-center rounded-md bg-primary-soft text-primary">
                <Sparkles class="size-5" />
              </span>
              <div>
                <h2 class="text-lg font-semibold">确定性匹配分析</h2>
                <p class="mt-1 text-sm text-muted-foreground">
                  使用正式简历版本、岗位条件和可追溯证据生成六维报告。
                </p>
              </div>
            </div>
            <div
              v-if="resumeVersions.length === 0"
              class="mt-5 rounded-md border border-dashed p-5"
            >
              <div class="flex items-start gap-3">
                <FileCheck2 class="mt-0.5 size-5 text-warning" />
                <div>
                  <h3 class="font-semibold">还没有正式简历版本</h3>
                  <p class="mt-1 text-sm text-muted-foreground">
                    请先完成简历解析和人工确认，再返回此岗位发起匹配。
                  </p>
                  <RouterLink :to="{ name: 'resumes' }">
                    <Button
                      class="mt-4"
                      variant="outline"
                    >
                      前往简历中心
                    </Button>
                  </RouterLink>
                </div>
              </div>
            </div>
            <div
              v-else
              class="mt-5 flex flex-col gap-3 sm:flex-row sm:items-end"
            >
              <FormField
                class="min-w-0 flex-1"
                label="已确认简历版本"
                for-id="job-match-version"
              >
                <select
                  id="job-match-version"
                  v-model="selectedVersionId"
                  class="h-10 w-full rounded-sm border bg-surface px-3 text-sm"
                >
                  <option
                    v-for="item in resumeVersions"
                    :key="item.version.id"
                    :value="String(item.version.id)"
                  >
                    {{ item.resume.title }} · v{{ item.version.version_number }}
                    {{ item.version.is_current ? "（当前）" : "" }}
                  </option>
                </select>
              </FormField>
              <Button @click="startMatch">
                <Sparkles class="mr-2 size-4" />
                开始匹配分析
              </Button>
            </div>
          </section>
          <section
            v-if="resumeVersions.length > 0"
            class="rounded-lg border bg-surface p-6 shadow-sm"
          >
            <div class="flex items-start gap-3">
              <span class="grid size-10 shrink-0 place-items-center rounded-md bg-primary-soft text-primary">
                <FileText class="size-5" />
              </span>
              <div class="flex-1">
                <h2 class="text-lg font-semibold">使用正式简历优化</h2>
                <p class="mt-1 text-sm text-muted-foreground">
                  基于已确认简历版本和该岗位的匹配报告生成逐段优化建议。仅优化表达与关键词，不虚构经历。
                </p>
                <p
                  v-if="optimizationError"
                  class="mt-2 text-sm text-danger"
                >
                  {{ optimizationError }}
                </p>
                <Button
                  class="mt-4"
                  variant="outline"
                  :disabled="optimizationBusy"
                  data-testid="job-optimize-resume-button"
                  @click="optimizeResume"
                >
                  <FileText class="mr-2 size-4" />
                  {{ optimizationBusy ? "生成中" : "使用正式简历优化" }}
                </Button>
              </div>
            </div>
          </section>
          <section class="rounded-lg border bg-surface p-6 shadow-sm">
            <h2 class="text-lg font-semibold">岗位描述</h2>
            <p class="mt-4 whitespace-pre-line text-sm leading-7 text-muted-foreground">
              {{ job.description }}
            </p>
          </section>
          <section
            v-if="job.responsibilities"
            class="rounded-lg border bg-surface p-6 shadow-sm"
          >
            <h2 class="text-lg font-semibold">工作职责</h2>
            <p class="mt-4 whitespace-pre-line text-sm leading-7 text-muted-foreground">
              {{ job.responsibilities }}
            </p>
          </section>
          <section
            v-if="job.requirements"
            class="rounded-lg border bg-surface p-6 shadow-sm"
          >
            <h2 class="text-lg font-semibold">任职要求</h2>
            <p class="mt-4 whitespace-pre-line text-sm leading-7 text-muted-foreground">
              {{ job.requirements }}
            </p>
          </section>
          <section
            v-if="job.skills.length"
            class="rounded-lg border bg-surface p-6 shadow-sm"
          >
            <h2 class="text-lg font-semibold">技能标签</h2>
            <div class="mt-4 flex flex-wrap gap-2">
              <StatusBadge
                v-for="skill in job.skills"
                :key="skill"
                tone="primary"
              >
                {{ skill }}
              </StatusBadge>
            </div>
          </section>
          <section
            id="job-match-history"
            class="rounded-lg border bg-surface p-6 shadow-sm"
          >
            <h2 class="flex items-center gap-2 text-lg font-semibold">
              <History class="size-5 text-primary" />
              岗位匹配历史
            </h2>
            <div class="mt-5">
              <MatchHistoryList
                :reports="matchHistory"
                :job-labels="jobLabels"
                :resume-labels="resumeLabels"
                :recalculating-id="recalculatingId"
                @recalculate="requestRecalculate"
              />
            </div>
          </section>
        </main>

        <aside class="space-y-4 rounded-lg border bg-surface p-5 shadow-sm lg:sticky lg:top-24">
          <h2 class="font-semibold">岗位概览</h2>
          <dl class="space-y-4 text-sm">
            <div class="flex gap-3">
              <Building2 class="mt-0.5 size-4 shrink-0 text-primary" />
              <div>
                <dt class="text-xs text-muted-foreground">公司</dt>
                <dd class="mt-1 font-medium">{{ job.company }}</dd>
              </div>
            </div>
            <div class="flex gap-3">
              <MapPin class="mt-0.5 size-4 shrink-0 text-primary" />
              <div>
                <dt class="text-xs text-muted-foreground">地点</dt>
                <dd class="mt-1 font-medium">{{ job.location || "未提供" }}</dd>
              </div>
            </div>
            <div class="flex gap-3">
              <Banknote class="mt-0.5 size-4 shrink-0 text-primary" />
              <div>
                <dt class="text-xs text-muted-foreground">薪资</dt>
                <dd class="mt-1 font-medium">{{ salary(job) }}</dd>
              </div>
            </div>
            <div class="flex gap-3">
              <BriefcaseBusiness class="mt-0.5 size-4 shrink-0 text-primary" />
              <div>
                <dt class="text-xs text-muted-foreground">类型 / 经验</dt>
                <dd class="mt-1 font-medium">
                  {{ job.employment_type || "未提供" }} /
                  {{ job.experience_level || "未提供" }}
                </dd>
              </div>
            </div>
          </dl>
          <div class="border-t pt-4 text-xs leading-5 text-muted-foreground">
            <p>学历：{{ job.education_requirement || "未提供" }}</p>
            <p>语言：{{ job.language_requirements.join("、") || "未提供" }}</p>
            <p>来源：{{ sourceBadgeLabel(job.source_name) }} · {{ job.source_type }}</p>
            <p>发布：{{ date(job.published_at) }}</p>
            <p>入库：{{ date(job.created_at) }}</p>
            <p>最后核验：{{ date(job.last_verified_at) }}</p>
            <p>状态：{{ job.status }}</p>
            <p>信息完整度：{{ job.data_completeness }}%</p>
            <p v-if="job.is_summary_only">
              类型：公开快照（来源可能受限）
            </p>
          </div>
        </aside>
      </div>
      <ConfirmDialog
        ref="recalculateDialog"
        title="创建新的匹配报告？"
        description="重新计算会创建一份新的匹配报告，旧报告不会被覆盖。"
        confirm-label="确认重新计算"
        @confirm="recalculate"
      />
      <Dialog
        :open="privateEditOpen"
        title="编辑私人岗位"
        description="仅你本人可查看、编辑、删除和匹配该岗位。"
        @close="privateEditOpen = false"
      >
        <form
          class="space-y-4"
          @submit.prevent="savePrivateEdit"
        >
          <FormField
            label="职位名称"
            for-id="private-job-title"
            required
          >
            <Input
              id="private-job-title"
              v-model="privateEditForm.title"
            />
          </FormField>
          <FormField
            label="公司"
            for-id="private-job-company"
            hint="可选"
          >
            <Input
              id="private-job-company"
              v-model="privateEditForm.company"
            />
          </FormField>
          <FormField
            label="职位描述"
            for-id="private-job-description"
          >
            <textarea
              id="private-job-description"
              v-model="privateEditForm.description"
              class="min-h-28 w-full rounded-sm border bg-surface p-3 text-sm"
            />
          </FormField>
          <FormField
            label="任职要求"
            for-id="private-job-requirements"
            hint="职位描述或任职要求至少填写一项"
          >
            <textarea
              id="private-job-requirements"
              v-model="privateEditForm.requirements"
              class="min-h-28 w-full rounded-sm border bg-surface p-3 text-sm"
            />
          </FormField>
          <p
            v-if="privateEditError"
            class="text-sm text-danger"
          >
            {{ privateEditError }}
          </p>
          <div class="flex justify-end gap-2 border-t pt-4">
            <Button
              variant="outline"
              @click="privateEditOpen = false"
            >
              取消
            </Button>
            <Button
              type="submit"
              :disabled="privateEditBusy"
            >
              {{ privateEditBusy ? "保存中…" : "保存修改" }}
            </Button>
          </div>
        </form>
      </Dialog>
      <ConfirmDialog
        ref="privateDeleteDialog"
        title="删除私人岗位？"
        description="删除后无法恢复；如已有投递或匹配历史，系统会保留记录并提示不能删除。"
        confirm-label="确认删除"
        danger
        @confirm="deletePrivateJob"
      />
    </template>
  </section>
</template>
