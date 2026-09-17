<script setup lang="ts">
import { History, RefreshCw } from "@lucide/vue"
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"

import { getApiErrorMessage } from "@/api/errors"
import { getJob } from "@/api/jobs"
import { getResumeVersion } from "@/api/resumes"
import ConfirmDialog from "@/components/domain/ConfirmDialog.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import MatchHistoryList from "@/components/domain/MatchHistoryList.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import PageSkeleton from "@/components/domain/PageSkeleton.vue"
import { Button } from "@/components/ui/button"
import { matchHistoryService, matchRunService } from "@/services/matching"
import type { MatchReport } from "@/types/matching"

const router = useRouter()
const reports = ref<MatchReport[]>([])
const jobLabels = ref<Record<number, string>>({})
const resumeLabels = ref<Record<number, string>>({})
const loading = ref(true)
const errorMessage = ref<string | null>(null)
const selectedReport = ref<MatchReport | null>(null)
const recalculatingId = ref<number | null>(null)
const confirmDialog = ref<InstanceType<typeof ConfirmDialog> | null>(null)

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    const result = await matchHistoryService.listAll(0, 100)
    reports.value = result.items
    const jobs = [...new Set(result.items.map((item) => item.job_id))]
    const versions = [...new Set(result.items.map((item) => item.resume_version_id))]
    const [jobResults, versionResults] = await Promise.all([
      Promise.all(jobs.map(async (id) => [id, await getJob(id)] as const)),
      Promise.all(versions.map(async (id) => [id, await getResumeVersion(id)] as const)),
    ])
    jobLabels.value = Object.fromEntries(
      jobResults.map(([id, job]) => [id, `${job.title} · ${job.company}`]),
    )
    resumeLabels.value = Object.fromEntries(
      versionResults.map(([id, version]) => [id, `正式版本 v${version.version_number}`]),
    )
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

function requestRecalculate(report: MatchReport): void {
  selectedReport.value = report
  confirmDialog.value?.open()
}

async function recalculate(): Promise<void> {
  if (!selectedReport.value || recalculatingId.value !== null) return
  recalculatingId.value = selectedReport.value.id
  try {
    const run = await matchRunService.create({
      resume_version_id: selectedReport.value.resume_version_id,
      job_id: selectedReport.value.job_id,
      scoring_version: selectedReport.value.scoring_version,
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

onMounted(load)
</script>

<template>
  <section class="space-y-6">
    <PageHeader
      eyebrow="匹配历史"
      title="匹配任务与历史报告"
      description="每次显式重算都会创建新报告，旧评分版本和证据快照保持可访问。"
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
      label="正在加载匹配历史"
      :rows="6"
    />
    <ErrorState
      v-else-if="errorMessage"
      :message="errorMessage"
      @retry="load"
    />
    <section
      v-else
      class="rounded-lg border bg-surface p-5 shadow-sm"
    >
      <h2 class="flex items-center gap-2 font-semibold">
        <History class="size-4 text-primary" />
        全部报告
      </h2>
      <div class="mt-5">
        <MatchHistoryList
          :reports="reports"
          :job-labels="jobLabels"
          :resume-labels="resumeLabels"
          :recalculating-id="recalculatingId"
          @recalculate="requestRecalculate"
        />
      </div>
    </section>
    <ConfirmDialog
      ref="confirmDialog"
      title="创建新的匹配报告？"
      description="重新计算会创建一份新的匹配报告，旧报告不会被覆盖。"
      confirm-label="确认重新计算"
      @confirm="recalculate"
    />
  </section>
</template>
