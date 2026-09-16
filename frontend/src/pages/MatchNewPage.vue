<script setup lang="ts">
import { ArrowLeft, FileCheck2, Play, ShieldCheck } from "@lucide/vue"
import { computed, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getApiErrorInfo } from "@/api/errors"
import { getJob } from "@/api/jobs"
import { listResumes, listResumeVersions } from "@/api/resumes"
import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import ForbiddenState from "@/components/domain/ForbiddenState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import PageSkeleton from "@/components/domain/PageSkeleton.vue"
import { Button } from "@/components/ui/button"
import { FormField } from "@/components/ui/form-field"
import { StatusBadge } from "@/components/ui/status-badge"
import { matchRunService } from "@/services/matching"
import type { Job } from "@/types/job"
import type { ScoringVersion } from "@/types/matching"
import type { Resume, ResumeVersion } from "@/types/resume"
import { isPositiveInteger } from "@/utils/matching"

const route = useRoute()
const router = useRouter()
const job = ref<Job | null>(null)
const versions = ref<Array<{ version: ResumeVersion; resume: Resume }>>([])
const selectedVersionId = ref("")
const scoringVersion = ref<ScoringVersion>("deterministic-v1.1")
const loading = ref(true)
const creating = ref(false)
const errorMessage = ref<string | null>(null)
const errorKind = ref<string | null>(null)

const jobId = computed(() => Number(route.query.jobId))
const validJobId = computed(() => isPositiveInteger(jobId.value))
const selectedVersion = computed(() =>
  versions.value.find((item) => String(item.version.id) === selectedVersionId.value),
)

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  errorKind.value = null
  if (!validJobId.value) {
    loading.value = false
    errorKind.value = "not-found"
    errorMessage.value = "岗位参数无效，请从岗位详情重新发起匹配。"
    return
  }
  try {
    const [nextJob, resumes] = await Promise.all([getJob(jobId.value), listResumes()])
    job.value = nextJob
    const versionGroups = await Promise.all(
      resumes
        .filter((resume) => resume.status === "CONFIRMED")
        .map(async (resume) => ({
          resume,
          versions: await listResumeVersions(resume.id),
        })),
    )
    versions.value = versionGroups.flatMap(({ resume, versions: items }) =>
      items
        .filter((version) => version.is_confirmed)
        .map((version) => ({ resume, version })),
    )
    const requested = Number(route.query.resumeVersionId)
    const initial = versions.value.find((item) => item.version.id === requested)
    selectedVersionId.value = String(initial?.version.id ?? versions.value[0]?.version.id ?? "")
  } catch (error) {
    const info = getApiErrorInfo(error)
    errorKind.value = info.kind
    errorMessage.value = info.message
  } finally {
    loading.value = false
  }
}

async function createMatch(): Promise<void> {
  const resumeVersionId = Number(selectedVersionId.value)
  if (!isPositiveInteger(resumeVersionId) || !validJobId.value || creating.value) return
  creating.value = true
  errorMessage.value = null
  try {
    const run = await matchRunService.create({
      job_id: jobId.value,
      resume_version_id: resumeVersionId,
      scoring_version: scoringVersion.value,
    })
    await router.push({
      name: "match-processing",
      params: { runId: run.run_id },
    })
  } catch (error) {
    const info = getApiErrorInfo(error)
    errorKind.value = info.kind
    errorMessage.value = info.message
  } finally {
    creating.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="space-y-6">
    <PageSkeleton
      v-if="loading || creating"
      :label="creating ? '正在执行真实匹配' : '正在准备匹配'"
      :rows="creating ? 7 : 4"
    />
    <ForbiddenState
      v-else-if="errorKind === 'forbidden'"
      description="当前账号无权使用该岗位发起匹配。"
    />
    <ErrorState
      v-else-if="errorMessage && !job"
      :title="errorKind === 'not-found' ? '岗位不存在' : '无法准备匹配'"
      :message="errorMessage"
      @retry="load"
    />
    <template v-else-if="job">
      <RouterLink
        :to="{ name: 'job-detail', params: { jobId: job.id } }"
        class="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft class="size-4" />
        返回岗位详情
      </RouterLink>
      <PageHeader
        eyebrow="Evidence-grounded match"
        title="开始证据约束匹配"
        :description="`${job.title} · ${job.company}`"
      />

      <ErrorState
        v-if="errorMessage"
        compact
        title="匹配未能启动"
        :message="errorMessage"
      />

      <EmptyState
        v-if="versions.length === 0"
        :icon="FileCheck2"
        title="还没有正式简历版本"
        description="请先在简历中心完成解析、人工确认并创建正式版本，再返回岗位发起匹配。"
      >
        <RouterLink :to="{ name: 'resumes' }">
          <Button>前往简历中心</Button>
        </RouterLink>
      </EmptyState>

      <div
        v-else
        class="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]"
      >
        <form
          class="rounded-lg border bg-surface p-6 shadow-sm"
          @submit.prevent="createMatch"
        >
          <div class="flex items-start gap-3">
            <span class="grid size-10 place-items-center rounded-md bg-primary-soft text-primary">
              <ShieldCheck class="size-5" />
            </span>
            <div>
              <h2 class="font-semibold">选择已确认简历版本</h2>
              <p class="mt-1 text-sm text-muted-foreground">
                只有属于当前账号且已经人工确认（Human Verified）的正式版本可用于评分。
              </p>
            </div>
          </div>
          <FormField
            class="mt-6"
            label="正式简历版本"
            for-id="match-resume-version"
          >
            <select
              id="match-resume-version"
              v-model="selectedVersionId"
              class="h-11 w-full rounded-sm border bg-surface px-3 text-sm"
              required
            >
              <option
                v-for="item in versions"
                :key="item.version.id"
                :value="String(item.version.id)"
              >
                {{ item.resume.title }} · v{{ item.version.version_number }}
                {{ item.version.is_current ? "（当前）" : "" }}
              </option>
            </select>
          </FormField>
          <fieldset class="mt-6 space-y-3">
            <legend class="text-sm font-medium">匹配模式</legend>
            <label
              class="flex cursor-pointer gap-3 rounded-md border p-4"
              :class="{ 'border-primary bg-primary-soft': scoringVersion === 'deterministic-v1.1' }"
            >
              <input
                v-model="scoringVersion"
                type="radio"
                value="deterministic-v1.1"
                name="scoring-version"
              >
              <span>
                <strong class="block text-sm">规则匹配</strong>
                <span class="mt-1 block text-xs text-muted-foreground">
                  默认使用 deterministic-v1.1，稳定、快速并保留完整规则证据。
                </span>
              </span>
            </label>
            <label
              class="flex cursor-pointer gap-3 rounded-md border p-4"
              :class="{ 'border-primary bg-primary-soft': scoringVersion === 'hybrid-v1' }"
            >
              <input
                v-model="scoringVersion"
                type="radio"
                value="hybrid-v1"
                name="scoring-version"
              >
              <span>
                <span class="flex items-center gap-2">
                  <strong class="text-sm">混合匹配</strong>
                  <StatusBadge tone="primary">语义为辅助信号</StatusBadge>
                </span>
                <span class="mt-1 block text-xs text-muted-foreground">
                  70% 规则分 + 30% 本地多语言语义相关性；语义不能证明技能，也不能抵消资格冲突。
                </span>
              </span>
            </label>
          </fieldset>
          <div class="mt-6 rounded-md bg-muted p-4 text-xs leading-6 text-muted-foreground">
            规则模式不调用 LLM 或 Embedding；混合模式只使用本地 Embedding 和 FAISS，
            不调用云端 Embedding API。
          </div>
          <Button
            class="mt-6 w-full"
            type="submit"
            size="lg"
            :disabled="creating || !selectedVersionId"
          >
            <Play class="mr-2 size-4" />
            {{ creating ? "正在执行真实匹配…" : "开始匹配分析" }}
          </Button>
        </form>

        <aside class="rounded-lg border bg-surface p-5 shadow-sm">
          <StatusBadge tone="primary">输入快照</StatusBadge>
          <dl class="mt-4 space-y-4 text-sm">
            <div>
              <dt class="text-xs text-muted-foreground">岗位</dt>
              <dd class="mt-1 font-semibold">{{ job.title }}</dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">公司 / 地点</dt>
              <dd class="mt-1">{{ job.company }} · {{ job.location || "未提供" }}</dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">岗位数据完整度</dt>
              <dd class="mt-1 font-semibold">{{ job.data_completeness }}%</dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">简历证据状态</dt>
              <dd class="mt-1 flex items-center gap-2 font-semibold">
                <StatusBadge tone="success">Human Verified</StatusBadge>
                <span v-if="selectedVersion">v{{ selectedVersion.version.version_number }}</span>
              </dd>
            </div>
          </dl>
        </aside>
      </div>
    </template>
  </section>
</template>
