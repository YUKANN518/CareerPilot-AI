<script setup lang="ts">
import {
  BookOpen,
  CheckCircle2,
  CircleAlert,
  LoaderCircle,
  MessageSquareQuote,
  RefreshCw,
  Send,
} from "@lucide/vue"
import { computed, onBeforeUnmount, onMounted, ref } from "vue"

import { getApiErrorMessage } from "@/api/errors"
import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import PageSkeleton from "@/components/domain/PageSkeleton.vue"
import { Button } from "@/components/ui/button"
import { FormMessage } from "@/components/ui/form-message"
import { StatusBadge } from "@/components/ui/status-badge"
import { careerAssistantService } from "@/services/career-assistant"
import type {
  CareerAssistantQA,
  CareerAssistantQAEvent,
  CareerAssistantQACitation,
  CareerAssistantQAScope,
  CareerAssistantRunStatus,
} from "@/types/career-assistant"

const QUESTION_MAX = 2000
const QUESTION_MIN = 1

const SCOPE_OPTIONS: { value: CareerAssistantQAScope; label: string; hint: string }[] = [
  { value: "auto", label: "智能匹配", hint: "同时检索知识库与个人数据" },
  { value: "knowledge", label: "仅知识库", hint: "只检索共享知识文档" },
  { value: "personal", label: "仅个人数据", hint: "只检索简历、匹配报告等" },
]

const runs = ref<CareerAssistantQA[]>([])
const loading = ref(true)
const acting = ref(false)
const errorMessage = ref<string | null>(null)
const questionInput = ref("")
const scopeInput = ref<CareerAssistantQAScope>("auto")

const activeRun = ref<CareerAssistantQA | null>(null)
const reconnectAttempt = ref(0)
let disconnect: (() => void) | null = null

const isQuestionValid = computed(
  () =>
    questionInput.value.trim().length >= QUESTION_MIN &&
    questionInput.value.trim().length <= QUESTION_MAX,
)

const isTerminal = (status: CareerAssistantRunStatus): boolean =>
  status === "SUCCEEDED" || status === "FAILED" || status === "CANCELLED"

function statusTone(
  status: CareerAssistantRunStatus,
): "success" | "danger" | "primary" | "neutral" | "warning" {
  if (status === "SUCCEEDED") return "success"
  if (status === "FAILED") return "danger"
  if (status === "RUNNING" || status === "PENDING") return "primary"
  if (status === "CANCELLED") return "neutral"
  return "warning"
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

function applyEvent(event: CareerAssistantQAEvent): void {
  if (!activeRun.value || event.run_id !== activeRun.value.id) return
  if (event.event === "run_started") {
    activeRun.value.status = "RUNNING"
    return
  }
  if (event.event === "run_failed") {
    activeRun.value.status = "FAILED"
    activeRun.value.error_code = event.error_code
    activeRun.value.error_message = event.error_message
    return
  }
  if (event.event === "run_cancelled") {
    activeRun.value.status = "CANCELLED"
    return
  }
  if (event.event === "run_completed") {
    activeRun.value.status = "SUCCEEDED"
    activeRun.value.answer = event.answer
    activeRun.value.citations = (event.citations as unknown as CareerAssistantQACitation[]) ?? []
    activeRun.value.finished_at = event.timestamp
    disconnect?.()
    refreshHistory()
    return
  }
}

async function connect(runId: number): Promise<void> {
  disconnect?.()
  disconnect = await careerAssistantService.connect(runId, {
    onEvent: applyEvent,
    onDisconnected: (attempt) => {
      reconnectAttempt.value = attempt
    },
    onExhausted: () => {
      errorMessage.value = "实时连接连续中断 3 次，请刷新状态后重试。"
    },
  })
}

async function loadHistory(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  try {
    const result = await careerAssistantService.list(0, 50)
    runs.value = result.items
      .map((item) => ({
        id: item.id,
        user_id: 0,
        question: item.question,
        answer: item.answer,
        status: item.status,
        citations: [],
        error_code: null,
        error_message: null,
        created_at: item.created_at,
        finished_at: item.finished_at,
      }))
      .reverse()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

async function refreshHistory(): Promise<void> {
  try {
    const result = await careerAssistantService.list(0, 50)
    runs.value = result.items
      .map((item) => ({
        id: item.id,
        user_id: 0,
        question: item.question,
        answer: item.answer,
        status: item.status,
        citations: [],
        error_code: null,
        error_message: null,
        created_at: item.created_at,
        finished_at: item.finished_at,
      }))
      .reverse()
  } catch {
    // Silent refresh; the active run state remains from SSE.
  }
}

async function askQuestion(): Promise<void> {
  if (!isQuestionValid.value || acting.value) return
  acting.value = true
  errorMessage.value = null
  reconnectAttempt.value = 0
  try {
    const created = await careerAssistantService.create({
      question: questionInput.value.trim(),
      scope: scopeInput.value,
    })
    activeRun.value = created
    questionInput.value = ""
    if (!isTerminal(created.status)) await connect(created.id)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    acting.value = false
  }
}

async function openHistory(runId: number): Promise<void> {
  if (acting.value) return
  errorMessage.value = null
  try {
    const run = await careerAssistantService.get(runId)
    activeRun.value = run
    reconnectAttempt.value = 0
    if (!isTerminal(run.status)) await connect(run.id)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  }
}

onMounted(loadHistory)
onBeforeUnmount(() => disconnect?.())
</script>

<template>
  <section class="space-y-6">
    <PageHeader
      eyebrow="Career assistant"
      title="AI 职业助手"
      description="Demo / Optional Dify Integration · 基于本地知识库检索与 Dify 生成的问答，引用片段可追溯、不可伪造。"
    >
      <template #actions>
        <Button
          variant="outline"
          :disabled="loading"
          @click="loadHistory"
        >
          <RefreshCw class="mr-2 size-4" />
          刷新
        </Button>
      </template>
    </PageHeader>

    <PageSkeleton
      v-if="loading && runs.length === 0"
      label="正在加载问答历史"
      :rows="4"
    />
    <ErrorState
      v-else-if="errorMessage && !activeRun"
      :message="errorMessage"
      @retry="loadHistory"
    />

    <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <section class="space-y-5">
        <form
          class="rounded-lg border bg-surface p-5 shadow-sm"
          @submit.prevent="askQuestion"
        >
          <div class="flex items-start gap-3">
            <span class="grid size-10 shrink-0 place-items-center rounded-md bg-primary-soft text-primary">
              <MessageSquareQuote class="size-5" />
            </span>
            <div class="min-w-0 flex-1">
              <label
                for="career-question"
                class="text-sm font-semibold"
              >
                提一个职业问题
              </label>
              <p class="mt-1 text-xs text-muted-foreground">
                例如：如何写好简历中的项目经历？后端工程师需要哪些必备技能？
              </p>
              <textarea
                id="career-question"
                v-model="questionInput"
                data-testid="career-question-input"
                rows="3"
                maxlength="2000"
                :disabled="acting"
                class="mt-3 w-full resize-y rounded-md border bg-background px-3 py-2 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-60"
                placeholder="输入你的问题（不超过 2000 字符）"
              />
              <div class="mt-2 flex items-center gap-2">
                <label
                  for="career-scope"
                  class="text-xs text-muted-foreground"
                >
                  数据来源
                </label>
                <select
                  id="career-scope"
                  v-model="scopeInput"
                  data-testid="career-scope-select"
                  :disabled="acting"
                  class="rounded-md border bg-background px-2 py-1 text-xs shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <option
                    v-for="option in SCOPE_OPTIONS"
                    :key="option.value"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </option>
                </select>
                <span class="text-xs text-muted-foreground">
                  {{ SCOPE_OPTIONS.find((o) => o.value === scopeInput)?.hint }}
                </span>
              </div>
              <div class="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                <span>{{ questionInput.length }} / 2000</span>
                <Button
                  type="submit"
                  size="sm"
                  :disabled="acting || !isQuestionValid"
                >
                  <Send class="mr-1.5 size-3.5" />
                  {{ acting ? "提交中…" : "提问" }}
                </Button>
              </div>
            </div>
          </div>
          <FormMessage
            v-if="errorMessage && acting === false"
            class="mt-3"
            :message="errorMessage"
          />
        </form>

        <div
          v-if="activeRun"
          class="rounded-lg border bg-surface p-6 shadow-sm"
          data-testid="career-qa-active-run"
        >
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <p class="text-xs font-semibold uppercase tracking-widest text-primary">
                Question
              </p>
              <h2 class="mt-1 text-base font-semibold">{{ activeRun.question }}</h2>
            </div>
            <StatusBadge :tone="statusTone(activeRun.status)">
              {{ activeRun.status }}
            </StatusBadge>
          </div>

          <div
            v-if="reconnectAttempt"
            class="mt-3 rounded-md border border-warning/30 bg-warning-soft p-3 text-sm"
            role="status"
          >
            SSE 已断开，正在进行第 {{ reconnectAttempt }} 次自动重连。
          </div>

          <div
            v-if="activeRun.error_message"
            class="mt-3 rounded-md border border-danger/30 bg-danger-soft p-3 text-sm text-danger"
          >
            <CircleAlert class="mr-1.5 inline size-4" />
            {{ activeRun.error_message }}
          </div>

          <div
            v-if="activeRun.status === 'PENDING' || activeRun.status === 'RUNNING'"
            class="mt-5 flex items-center gap-2 text-sm text-muted-foreground"
          >
            <LoaderCircle class="size-4 animate-spin text-primary" />
            正在检索知识库并生成答案…
          </div>

          <div
            v-if="activeRun.answer"
            class="mt-5 space-y-4"
          >
            <div class="rounded-md bg-muted/60 p-4 text-sm leading-7">
              <p class="whitespace-pre-wrap">{{ activeRun.answer }}</p>
            </div>
          </div>
        </div>
      </section>

      <aside class="rounded-lg border bg-surface p-5 shadow-sm">
        <div class="flex items-center justify-between">
          <h2 class="flex items-center gap-2 text-sm font-semibold">
            <BookOpen class="size-4" />
            问答历史
          </h2>
          <span class="text-xs text-muted-foreground">{{ runs.length }} 条</span>
        </div>

        <EmptyState
          v-if="runs.length === 0"
          compact
          title="还没有问答记录"
          description="提出第一个问题即可开始。"
          :icon="MessageSquareQuote"
        />

        <ul
          v-else
          class="mt-4 space-y-2"
        >
          <li
            v-for="run in runs"
            :key="run.id"
          >
            <button
              type="button"
              class="block w-full rounded-md border bg-background p-3 text-left transition-colors hover:border-primary/50 hover:bg-muted/40"
              :class="
                activeRun?.id === run.id ? 'border-primary bg-primary-soft/40' : ''
              "
              :data-testid="`career-qa-history-${run.id}`"
              @click="openHistory(run.id)"
            >
              <div class="flex items-start justify-between gap-2">
                <p class="line-clamp-2 text-sm font-medium">{{ run.question }}</p>
                <span
                  v-if="run.status === 'SUCCEEDED'"
                  class="grid size-5 shrink-0 place-items-center rounded-full bg-success-soft text-success"
                >
                  <CheckCircle2 class="size-3.5" />
                </span>
                <span
                  v-else-if="run.status === 'FAILED'"
                  class="grid size-5 shrink-0 place-items-center rounded-full bg-danger-soft text-danger"
                >
                  <CircleAlert class="size-3.5" />
                </span>
              </div>
              <p class="mt-1 text-xs text-muted-foreground">
                {{ formatDate(run.created_at) }}
              </p>
            </button>
          </li>
        </ul>
      </aside>
    </div>
  </section>
</template>
