<script setup lang="ts">
import {
  AlertTriangle,
  ArrowLeft,
  ClipboardCheck,
  Lightbulb,
  RefreshCw,
  ShieldCheck,
  Target,
  TrendingDown,
  TrendingUp,
} from "@lucide/vue"
import { computed, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getApiErrorInfo } from "@/api/errors"
import { getInterviewChatReport } from "@/api/interviews"
import ErrorState from "@/components/domain/ErrorState.vue"
import ForbiddenState from "@/components/domain/ForbiddenState.vue"
import LoadingState from "@/components/domain/LoadingState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import { Button } from "@/components/ui/button"
import type {
  AnswerSequenceRefRead,
  FinalDimensionScoreRead,
  FinalEvaluationDimension,
  InterviewChatReportRead,
  InterviewType,
} from "@/types/interview"

const route = useRoute()
const router = useRouter()
const report = ref<InterviewChatReportRead | null>(null)
const loading = ref(true)
const errorMessage = ref<string | null>(null)
const errorKind = ref<string | null>(null)

const interviewId = computed(() => Number(route.params.interviewId))

const finalDimensions: FinalEvaluationDimension[] = [
  "relevance",
  "completeness",
  "clarity",
  "structure",
  "technical_accuracy",
]

const finalDimensionLabels: Record<FinalEvaluationDimension, string> = {
  relevance: "相关性",
  completeness: "完整性",
  clarity: "清晰度",
  structure: "结构",
  technical_accuracy: "技术准确度",
}

function typeLabel(type: InterviewType): string {
  const labels: Record<InterviewType, string> = {
    COMPREHENSIVE: "综合面试",
    TECHNICAL: "技术面试",
    BEHAVIORAL: "行为面试",
    PROJECT: "项目深挖",
    HR: "HR 面试",
  }
  return labels[type] ?? type
}

function formatDate(value: string | null): string {
  if (!value) return "—"
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

// Defensive array accessors — every array field must default to [] so
// the template can call .length without undefined errors.
function strengths(r: InterviewChatReportRead | null): string[] {
  return r?.strengths ?? []
}
function weaknesses(r: InterviewChatReportRead | null): string[] {
  return r?.weaknesses ?? []
}
function bestAnswers(r: InterviewChatReportRead | null): AnswerSequenceRefRead[] {
  return r?.best_answers ?? []
}
function weakestAnswers(
  r: InterviewChatReportRead | null,
): AnswerSequenceRefRead[] {
  return r?.weakest_answers ?? []
}
function unsupportedClaims(r: InterviewChatReportRead | null): string[] {
  return r?.unsupported_claims ?? []
}
function missingSkillWarnings(r: InterviewChatReportRead | null): string[] {
  return r?.missing_skill_warnings ?? []
}
function improvementSuggestions(r: InterviewChatReportRead | null): string[] {
  return r?.improvement_suggestions ?? []
}
function practiceQuestions(r: InterviewChatReportRead | null): string[] {
  return r?.practice_questions ?? []
}
function usedFacts(r: InterviewChatReportRead | null): string[] {
  return r?.used_facts ?? []
}
function dimensionScores(
  r: InterviewChatReportRead | null,
): FinalDimensionScoreRead[] {
  return r?.dimension_scores ?? []
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  errorKind.value = null
  try {
    report.value = await getInterviewChatReport(interviewId.value)
  } catch (error) {
    const info = getApiErrorInfo(error)
    errorKind.value = info.kind
    errorMessage.value = info.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="space-y-6">
    <Button
      variant="ghost"
      class="px-0"
      @click="router.push({ name: 'interviews' })"
    >
      <ArrowLeft class="mr-1 h-4 w-4" />
      返回面试列表
    </Button>

    <PageHeader
      title="模拟面试评估报告"
      :description="report ? typeLabel(report.interview_type) : ''"
    />

    <div
      v-if="loading"
      class="flex items-center justify-center py-12"
    >
      <LoadingState label="正在加载评估报告..." />
    </div>

    <ForbiddenState
      v-else-if="errorKind === 'forbidden'"
      title="无权访问该面试报告"
    />

    <ErrorState
      v-else-if="errorMessage"
      :message="errorMessage"
    />

    <div
      v-else-if="report"
      data-testid="interview-chat-report"
      class="space-y-6"
    >
      <!-- Error code -->
      <div
        v-if="report.error_code"
        data-testid="chat-report-error"
        class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
      >
        <div class="flex items-center gap-2">
          <AlertTriangle class="h-4 w-4" />
          <span>错误码：{{ report.error_code }}</span>
        </div>
        <p
          v-if="report.error_message"
          class="mt-1"
        >
          {{ report.error_message }}
        </p>
      </div>

      <!-- Overall score + summary -->
      <div
        class="rounded-lg border border-slate-200 bg-white p-6"
        data-testid="chat-report-summary"
      >
        <div class="flex items-center gap-4">
          <div
            data-testid="chat-report-overall-score"
            class="flex h-20 w-20 items-center justify-center rounded-full bg-blue-600 text-xl font-bold text-white"
          >
            {{ report.overall_score ?? "—" }}
          </div>
          <div class="flex-1">
            <div class="text-sm text-slate-500">综合评分 (0-100)</div>
            <div class="mt-1 text-xs text-slate-400">
              生成时间: {{ formatDate(report.generated_at) }}
            </div>
          </div>
        </div>
        <p
          v-if="report.summary"
          data-testid="chat-report-summary-text"
          class="mt-4 text-sm leading-relaxed text-slate-700"
        >
          {{ report.summary }}
        </p>
      </div>

      <!-- Five dimension scores -->
      <div
        class="rounded-lg border border-slate-200 bg-white p-6"
        data-testid="chat-report-dimensions"
      >
        <h3 class="mb-4 text-sm font-semibold text-slate-700">五维评分</h3>
        <div class="space-y-3">
          <div
            v-for="dim in finalDimensions"
            :key="dim"
            data-testid="chat-report-dimension"
            class="flex items-center gap-3"
          >
            <span class="w-24 text-sm text-slate-600">
              {{ finalDimensionLabels[dim] }}
            </span>
            <div class="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div
                class="h-full rounded-full bg-blue-500"
                :style="{
                  width: `${dimensionScores(report).find((d) => d.dimension === dim)?.score ?? 0}%`,
                }"
              />
            </div>
            <span class="w-10 text-right text-sm font-medium text-slate-700">
              {{ dimensionScores(report).find((d) => d.dimension === dim)?.score ?? 0 }}
            </span>
          </div>
        </div>
      </div>

      <!-- Strengths and Weaknesses -->
      <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div
          class="rounded-lg border border-emerald-200 bg-emerald-50 p-6"
          data-testid="chat-report-strengths"
        >
          <div class="mb-3 flex items-center gap-2">
            <TrendingUp class="h-4 w-4 text-emerald-600" />
            <h3 class="text-sm font-semibold text-emerald-700">优势</h3>
          </div>
          <ul
            v-if="strengths(report).length > 0"
            class="list-inside list-disc space-y-1 text-sm text-slate-700"
          >
            <li
              v-for="(item, i) in strengths(report)"
              :key="i"
            >
              {{ item }}
            </li>
          </ul>
          <p
            v-else
            class="text-sm text-slate-400"
          >
            暂无数据
          </p>
        </div>

        <div
          class="rounded-lg border border-amber-200 bg-amber-50 p-6"
          data-testid="chat-report-weaknesses"
        >
          <div class="mb-3 flex items-center gap-2">
            <TrendingDown class="h-4 w-4 text-amber-600" />
            <h3 class="text-sm font-semibold text-amber-700">待改进</h3>
          </div>
          <ul
            v-if="weaknesses(report).length > 0"
            class="list-inside list-disc space-y-1 text-sm text-slate-700"
          >
            <li
              v-for="(item, i) in weaknesses(report)"
              :key="i"
            >
              {{ item }}
            </li>
          </ul>
          <p
            v-else
            class="text-sm text-slate-400"
          >
            暂无数据
          </p>
        </div>
      </div>

      <!-- Best and Weakest answers -->
      <div class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div
          class="rounded-lg border border-slate-200 bg-white p-6"
          data-testid="chat-report-best-answers"
        >
          <div class="mb-3 flex items-center gap-2">
            <Target class="h-4 w-4 text-blue-600" />
            <h3 class="text-sm font-semibold text-slate-700">最佳回答</h3>
          </div>
          <div
            v-if="bestAnswers(report).length > 0"
            class="space-y-3"
          >
            <div
              v-for="(ans, i) in bestAnswers(report)"
              :key="i"
              data-testid="chat-report-best-answer"
              class="rounded-md bg-slate-50 px-3 py-2"
            >
              <div class="text-xs text-slate-500">问题 #{{ ans.question_sequence }}</div>
              <p
                v-if="ans.excerpt"
                class="mt-1 text-sm text-slate-700"
              >
                {{ ans.excerpt }}
              </p>
              <p
                v-if="ans.reason"
                class="mt-1 text-xs text-slate-500"
              >
                {{ ans.reason }}
              </p>
            </div>
          </div>
          <p
            v-else
            class="text-sm text-slate-400"
          >
            暂无数据
          </p>
        </div>

        <div
          class="rounded-lg border border-slate-200 bg-white p-6"
          data-testid="chat-report-weakest-answers"
        >
          <div class="mb-3 flex items-center gap-2">
            <ClipboardCheck class="h-4 w-4 text-amber-600" />
            <h3 class="text-sm font-semibold text-slate-700">待加强回答</h3>
          </div>
          <div
            v-if="weakestAnswers(report).length > 0"
            class="space-y-3"
          >
            <div
              v-for="(ans, i) in weakestAnswers(report)"
              :key="i"
              data-testid="chat-report-weakest-answer"
              class="rounded-md bg-slate-50 px-3 py-2"
            >
              <div class="text-xs text-slate-500">问题 #{{ ans.question_sequence }}</div>
              <p
                v-if="ans.excerpt"
                class="mt-1 text-sm text-slate-700"
              >
                {{ ans.excerpt }}
              </p>
              <p
                v-if="ans.reason"
                class="mt-1 text-xs text-slate-500"
              >
                {{ ans.reason }}
              </p>
            </div>
          </div>
          <p
            v-else
            class="text-sm text-slate-400"
          >
            暂无数据
          </p>
        </div>
      </div>

      <!-- Improvement suggestions -->
      <div
        v-if="improvementSuggestions(report).length > 0"
        class="rounded-lg border border-slate-200 bg-white p-6"
        data-testid="chat-report-improvement"
      >
        <div class="mb-3 flex items-center gap-2">
          <Lightbulb class="h-4 w-4 text-blue-600" />
          <h3 class="text-sm font-semibold text-slate-700">改进建议</h3>
        </div>
        <ul class="list-inside list-disc space-y-1 text-sm text-slate-700">
          <li
            v-for="(item, i) in improvementSuggestions(report)"
            :key="i"
          >
            {{ item }}
          </li>
        </ul>
      </div>

      <!-- Practice questions -->
      <div
        v-if="practiceQuestions(report).length > 0"
        class="rounded-lg border border-slate-200 bg-white p-6"
        data-testid="chat-report-practice"
      >
        <h3 class="mb-3 text-sm font-semibold text-slate-700">练习题</h3>
        <ul class="list-inside list-decimal space-y-1 text-sm text-slate-700">
          <li
            v-for="(item, i) in practiceQuestions(report)"
            :key="i"
          >
            {{ item }}
          </li>
        </ul>
      </div>

      <!-- Fact-check section -->
      <div
        class="rounded-lg border border-slate-200 bg-white p-6"
        data-testid="chat-report-fact-check"
      >
        <div class="mb-3 flex items-center gap-2">
          <ShieldCheck class="h-4 w-4 text-emerald-600" />
          <h3 class="text-sm font-semibold text-slate-700">事实校验</h3>
        </div>
        <div class="space-y-4">
          <div v-if="unsupportedClaims(report).length > 0">
            <div class="text-xs font-medium text-slate-500">未支持声明</div>
            <ul class="mt-1 list-inside list-disc space-y-1 text-sm text-slate-700">
              <li
                v-for="(item, i) in unsupportedClaims(report)"
                :key="i"
              >
                {{ item }}
              </li>
            </ul>
          </div>
          <div v-if="missingSkillWarnings(report).length > 0">
            <div class="text-xs font-medium text-slate-500">缺失技能提醒</div>
            <ul class="mt-1 list-inside list-disc space-y-1 text-sm text-slate-700">
              <li
                v-for="(item, i) in missingSkillWarnings(report)"
                :key="i"
              >
                {{ item }}
              </li>
            </ul>
          </div>
          <div v-if="usedFacts(report).length > 0">
            <div class="text-xs font-medium text-slate-500">已引用事实</div>
            <ul class="mt-1 list-inside list-disc space-y-1 text-sm text-emerald-700">
              <li
                v-for="(item, i) in usedFacts(report)"
                :key="i"
              >
                {{ item }}
              </li>
            </ul>
          </div>
          <p
            v-if="
              unsupportedClaims(report).length === 0 &&
                missingSkillWarnings(report).length === 0 &&
                usedFacts(report).length === 0
            "
            class="text-sm text-slate-400"
          >
            暂无事实校验数据
          </p>
        </div>
      </div>

      <!-- Refresh button -->
      <div class="flex justify-end">
        <Button
          variant="outline"
          @click="load"
        >
          <RefreshCw class="mr-1 h-4 w-4" />
          刷新报告
        </Button>
      </div>
    </div>
  </section>
</template>
