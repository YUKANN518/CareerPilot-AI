<script setup lang="ts">
import {
  CheckCircle2,
  Circle,
  CircleAlert,
  Clock3,
  LoaderCircle,
  RotateCcw,
  ShieldCheck,
} from "@lucide/vue"
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getApiErrorInfo } from "@/api/errors"
import ErrorState from "@/components/domain/ErrorState.vue"
import ForbiddenState from "@/components/domain/ForbiddenState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import PageSkeleton from "@/components/domain/PageSkeleton.vue"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import { matchRunService } from "@/services/matching"
import type { MatchNodeStatus, MatchRun, MatchRunEvent } from "@/types/matching"
import { isPositiveInteger } from "@/utils/matching"

const route = useRoute()
const router = useRouter()
const run = ref<MatchRun | null>(null)
const loading = ref(true)
const acting = ref(false)
const reconnectAttempt = ref(0)
const errorMessage = ref<string | null>(null)
const errorKind = ref<string | null>(null)
const runId = computed(() => Number(route.params.runId))
let disconnect: (() => void) | null = null

const nodeLabels: Record<string, string> = {
  load_inputs: "读取并验证输入",
  deterministic_matching: "确定性规则匹配",
  semantic_retrieval: "本地语义检索",
  blocking_risk_check: "阻断风险检查",
  save_report: "保存不可覆盖报告",
  human_review: "人工确认",
}

function stepTone(status: MatchNodeStatus): "success" | "danger" | "primary" | "neutral" {
  if (status === "SUCCEEDED" || status === "SKIPPED") return "success"
  if (status === "FAILED") return "danger"
  if (status === "RUNNING" || status === "WAITING_REVIEW") return "primary"
  return "neutral"
}

function applyEvent(event: MatchRunEvent): void {
  if (!run.value) return
  const step = event.node
    ? run.value.steps.find((item) => item.node_name === event.node)
    : undefined
  if (step) {
    if (event.event === "node_started") step.status = "RUNNING"
    if (event.event === "node_completed") {
      step.status = event.status === "SKIPPED" ? "SKIPPED" : "SUCCEEDED"
      step.duration_ms = event.duration_ms
      step.summary = event.summary
    }
    if (event.event === "node_failed") {
      step.status = "FAILED"
      step.duration_ms = event.duration_ms
      step.error_message = event.error_message
    }
  }
  if (event.event === "waiting_for_user") {
    run.value.status = "WAITING_REVIEW"
    run.value.waiting_for_user = true
  }
  if (event.event === "run_failed") {
    run.value.status = "FAILED"
    run.value.error_code = event.error_code
    run.value.error_message = event.error_message
  }
  if (event.event === "run_cancelled") run.value.status = "CANCELLED"
  if (event.event === "run_completed") {
    run.value.status = "SUCCEEDED"
    run.value.report_id = event.report_id
    disconnect?.()
    if (event.report_id) {
      void router.push({ name: "match-report", params: { matchId: event.report_id } })
    }
  }
}

async function connect(): Promise<void> {
  disconnect?.()
  disconnect = await matchRunService.connect(runId.value, {
    onEvent: applyEvent,
    onDisconnected: (attempt) => {
      reconnectAttempt.value = attempt
    },
    onExhausted: () => {
      errorMessage.value = "实时连接连续中断 3 次，请刷新状态后重试。"
    },
  })
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  if (!isPositiveInteger(runId.value)) {
    errorKind.value = "not-found"
    errorMessage.value = "匹配运行参数无效。"
    loading.value = false
    return
  }
  try {
    run.value = await matchRunService.get(runId.value)
    if (run.value.status === "SUCCEEDED" && run.value.report_id) {
      await router.replace({
        name: "match-report",
        params: { matchId: run.value.report_id },
      })
      return
    }
    if (!["FAILED", "CANCELLED"].includes(run.value.status)) await connect()
  } catch (error) {
    const info = getApiErrorInfo(error)
    errorKind.value = info.kind
    errorMessage.value = info.message
  } finally {
    loading.value = false
  }
}

async function retry(): Promise<void> {
  if (!run.value || acting.value) return
  acting.value = true
  try {
    run.value = await matchRunService.retry(run.value.run_id)
    await connect()
  } catch (error) {
    errorMessage.value = getApiErrorInfo(error).message
  } finally {
    acting.value = false
  }
}

async function confirm(): Promise<void> {
  if (!run.value || acting.value) return
  acting.value = true
  try {
    run.value = await matchRunService.confirm(run.value.run_id)
    if (run.value.report_id) {
      await router.push({
        name: "match-report",
        params: { matchId: run.value.report_id },
      })
    }
  } catch (error) {
    errorMessage.value = getApiErrorInfo(error).message
  } finally {
    acting.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => disconnect?.())
</script>

<template>
  <section class="space-y-6">
    <PageSkeleton
      v-if="loading"
      label="正在读取匹配工作流"
      :rows="6"
    />
    <ForbiddenState
      v-else-if="errorKind === 'forbidden'"
      description="当前账号无权查看这次匹配运行。"
    />
    <template v-else-if="run">
      <PageHeader
        eyebrow="LangGraph 匹配流程"
        title="实时匹配流程"
        description="节点状态、耗时与摘要来自后端 SSE，不使用伪造进度。"
      >
        <template #actions>
          <Button
            v-if="run.status === 'FAILED'"
            :disabled="acting || run.retry_count >= 2"
            @click="retry"
          >
            <RotateCcw class="mr-2 size-4" />
            重试失败节点
          </Button>
          <Button
            v-if="run.waiting_for_user"
            :disabled="acting"
            @click="confirm"
          >
            <ShieldCheck class="mr-2 size-4" />
            确认并打开报告
          </Button>
        </template>
      </PageHeader>

      <div
        v-if="reconnectAttempt"
        class="rounded-md border border-warning/30 bg-warning-soft p-3 text-sm"
        role="status"
      >
        SSE 已断开，正在进行第 {{ reconnectAttempt }} 次自动重连。
      </div>
      <ErrorState
        v-if="errorMessage"
        :message="errorMessage"
        @retry="load"
      />

      <div class="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_19rem]">
        <section class="rounded-lg border bg-surface p-6 shadow-sm">
          <ol class="space-y-3">
            <li
              v-for="step in run.steps"
              :key="step.node_name"
              class="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-3"
              :data-testid="`node-${step.node_name}`"
            >
              <span class="grid size-10 place-items-center rounded-full border">
                <CheckCircle2
                  v-if="step.status === 'SUCCEEDED' || step.status === 'SKIPPED'"
                  class="size-5 text-success"
                />
                <LoaderCircle
                  v-else-if="step.status === 'RUNNING'"
                  class="size-5 animate-spin text-primary"
                />
                <CircleAlert
                  v-else-if="step.status === 'FAILED'"
                  class="size-5 text-danger"
                />
                <Circle
                  v-else
                  class="size-4 text-muted-foreground"
                />
              </span>
              <div class="rounded-md border p-4">
                <div class="flex items-center justify-between gap-3">
                  <h2 class="font-semibold">{{ nodeLabels[step.node_name] }}</h2>
                  <StatusBadge :tone="stepTone(step.status)">{{ step.status }}</StatusBadge>
                </div>
                <p class="mt-2 text-sm text-muted-foreground">
                  {{ step.summary.reason ?? step.summary }}
                </p>
                <p class="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                  <Clock3 class="size-3.5" />
                  {{ step.duration_ms ?? "—" }} ms · 重试 {{ step.retry_count }}/2
                </p>
                <p
                  v-if="step.error_message"
                  class="mt-2 text-sm text-danger"
                >
                  {{ step.error_message }}
                </p>
              </div>
            </li>
          </ol>
        </section>

        <aside class="rounded-lg border bg-surface p-5 shadow-sm">
          <h2 class="font-semibold">运行摘要</h2>
          <dl class="mt-4 space-y-3 text-sm">
            <div class="flex justify-between"><dt>运行编号</dt><dd>#{{ run.run_id }}</dd></div>
            <div class="flex justify-between"><dt>状态</dt><dd>{{ run.status }}</dd></div>
            <div class="flex justify-between"><dt>评分版本</dt><dd>{{ run.scoring_version }}</dd></div>
            <div class="flex justify-between"><dt>规则分</dt><dd>{{ run.rule_score ?? "—" }}</dd></div>
            <div class="flex justify-between"><dt>语义分</dt><dd>{{ run.semantic_score ?? "—" }}</dd></div>
            <div class="flex justify-between"><dt>混合分</dt><dd>{{ run.hybrid_score ?? "—" }}</dd></div>
          </dl>
        </aside>
      </div>
    </template>
  </section>
</template>
