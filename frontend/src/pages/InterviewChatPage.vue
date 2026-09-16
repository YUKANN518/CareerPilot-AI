<script setup lang="ts">
import {
  AlertTriangle,
  ArrowLeft,
  Clock,
  Send,
  Square,
} from "@lucide/vue"
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getApiErrorInfo, getApiErrorMessage } from "@/api/errors"
import {
  completeInterviewChat,
  getInterview,
  getInterviewChatStatus,
  listInterviewMessages,
  sendInterviewMessage,
  startInterviewChat,
} from "@/api/interviews"
import ErrorState from "@/components/domain/ErrorState.vue"
import ForbiddenState from "@/components/domain/ForbiddenState.vue"
import LoadingState from "@/components/domain/LoadingState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import { Button } from "@/components/ui/button"
import type {
  Interview,
  InterviewMessage,
  InterviewProgress,
} from "@/types/interview"

const route = useRoute()
const router = useRouter()
const interviewId = computed(() => Number(route.params.interviewId))

const interview = ref<Interview | null>(null)
const messages = ref<InterviewMessage[]>([])
const progress = ref<InterviewProgress | null>(null)
const chatStatus = ref<string>("")
const loading = ref(true)
const errorMessage = ref<string | null>(null)
const errorKind = ref<string | null>(null)
const sending = ref(false)
const aiThinking = ref(false)
const actionError = ref<string | null>(null)
const draft = ref("")
const startedAt = ref<number | null>(null)
const elapsedSeconds = ref(0)
let timerHandle: ReturnType<typeof setInterval> | null = null

const messagesContainer = ref<HTMLElement | null>(null)

const interviewTypeLabel = computed(() => {
  const map: Record<string, string> = {
    COMPREHENSIVE: "综合面试",
    TECHNICAL: "技术面试",
    BEHAVIORAL: "行为面试",
    PROJECT: "项目面试",
    HR: "HR 面试",
  }
  return interview.value
    ? (map[interview.value.interview_type] ?? interview.value.interview_type)
    : ""
})

const isCompleted = computed(
  () => chatStatus.value === "COMPLETED" || chatStatus.value === "GENERATING_REPORT",
)
const isCancelled = computed(() => chatStatus.value === "CANCELLED")
const isActive = computed(
  () =>
    !isCompleted.value &&
    !isCancelled.value &&
    chatStatus.value !== "FAILED" &&
    chatStatus.value !== "",
)
const canSend = computed(
  () =>
    !sending.value &&
    !aiThinking.value &&
    isActive.value &&
    draft.value.trim().length > 0,
)
const canComplete = computed(
  () => !sending.value && !aiThinking.value && isActive.value,
)

function scrollToBottom(): void {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
    .toString()
    .padStart(2, "0")
  const s = (seconds % 60).toString().padStart(2, "0")
  return `${m}:${s}`
}

function startTimer(): void {
  if (timerHandle) return
  timerHandle = setInterval(() => {
    if (startedAt.value !== null) {
      elapsedSeconds.value = Math.floor((Date.now() - startedAt.value) / 1000)
    }
  }, 1000)
}

function stopTimer(): void {
  if (timerHandle) {
    clearInterval(timerHandle)
    timerHandle = null
  }
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  errorKind.value = null
  try {
    const [iv, status] = await Promise.all([
      getInterview(interviewId.value),
      getInterviewChatStatus(interviewId.value),
    ])
    interview.value = iv
    chatStatus.value = status.chat_status
    progress.value = status.progress
    // Load any existing messages (session resume).
    messages.value = await listInterviewMessages(interviewId.value)
    if (messages.value.length > 0) {
      startedAt.value = new Date(messages.value[0].created_at).getTime()
      startTimer()
    }
    // If the interview is freshly created (CREATED), start the chat.
    if (status.chat_status === "CREATED") {
      await startChat()
    } else if (status.chat_status === "COMPLETED") {
      // Interview is already complete; redirect to report after a brief delay.
      void redirectToReport()
    }
    scrollToBottom()
  } catch (error) {
    const info = getApiErrorInfo(error)
    errorKind.value = info.kind
    errorMessage.value = info.message
  } finally {
    loading.value = false
  }
}

async function startChat(): Promise<void> {
  aiThinking.value = true
  actionError.value = null
  try {
    const status = await startInterviewChat(interviewId.value)
    chatStatus.value = status.chat_status
    progress.value = status.progress
    messages.value = await listInterviewMessages(interviewId.value)
    startedAt.value = Date.now()
    startTimer()
    scrollToBottom()
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    aiThinking.value = false
  }
}

async function sendMessage(): Promise<void> {
  if (!canSend.value) return
  const content = draft.value.trim()
  if (!content) return
  sending.value = true
  aiThinking.value = true
  actionError.value = null
  try {
    const turn = await sendInterviewMessage(interviewId.value, { content })
    // Append the user message and the assistant message locally so the
    // UI updates immediately.
    messages.value.push(turn.user_message)
    messages.value.push(turn.assistant_message)
    progress.value = turn.progress
    draft.value = ""
    scrollToBottom()
    if (turn.interview_completed) {
      chatStatus.value = "COMPLETED"
      stopTimer()
      // Redirect to the report page after a brief pause so the user
      // sees the completion message.
      setTimeout(() => {
        void redirectToReport()
      }, 1200)
    }
  } catch (error) {
    // The interview final-evaluation workflow can take ~30s. If the
    // request timed out or the network dropped, the server may still
    // have completed the interview successfully. Poll the chat status
    // before surfacing an error: if the session is COMPLETED, redirect
    // to the report page; if it is still WAITING_FOR_ANSWER, show the
    // error and let the user retry.
    const info = getApiErrorInfo(error)
    const mayHaveSucceeded =
      info.kind === "timeout" || info.kind === "network"
    if (mayHaveSucceeded) {
      try {
        const status = await getInterviewChatStatus(interviewId.value)
        chatStatus.value = status.chat_status
        progress.value = status.progress
        if (
          status.chat_status === "COMPLETED" ||
          status.chat_status === "GENERATING_REPORT"
        ) {
          // The server finished (or is finishing) the report. Refresh
          // messages so the user sees the final assistant message, then
          // redirect.
          messages.value = await listInterviewMessages(interviewId.value)
          scrollToBottom()
          if (status.chat_status === "COMPLETED") {
            stopTimer()
            setTimeout(() => {
              void redirectToReport()
            }, 1200)
          }
          return
        }
      } catch {
        // Status poll failed — fall through to surface the original error.
      }
    }
    actionError.value = getApiErrorMessage(error)
  } finally {
    sending.value = false
    aiThinking.value = false
  }
}

async function completeNow(): Promise<void> {
  if (sending.value || aiThinking.value) return
  if (!confirm("确定要立即结束本次模拟面试并生成评估报告吗？")) return
  sending.value = true
  aiThinking.value = true
  actionError.value = null
  try {
    const status = await completeInterviewChat(interviewId.value)
    chatStatus.value = status.chat_status
    progress.value = status.progress
    messages.value = await listInterviewMessages(interviewId.value)
    stopTimer()
    if (status.chat_status === "COMPLETED") {
      setTimeout(() => {
        void redirectToReport()
      }, 1200)
    }
  } catch (error) {
    actionError.value = getApiErrorMessage(error)
  } finally {
    sending.value = false
    aiThinking.value = false
  }
}

async function redirectToReport(): Promise<void> {
  await router.push({
    name: "interview-chat-report",
    params: { interviewId: interviewId.value },
  })
}

onMounted(load)
onUnmounted(stopTimer)
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
      title="模拟面试进行中"
      :description="interviewTypeLabel"
    />

    <div
      v-if="loading"
      class="flex items-center justify-center py-12"
    >
      <LoadingState label="正在加载面试会话..." />
    </div>

    <ForbiddenState
      v-else-if="errorKind === 'forbidden'"
      title="无权访问该面试会话"
    />

    <ErrorState
      v-else-if="errorMessage"
      :message="errorMessage"
    />

    <div
      v-else
      data-testid="interview-chat"
      class="flex h-[70vh] flex-col rounded-lg border border-slate-200 bg-white"
    >
      <!-- Header bar: job title, interview type, progress, elapsed time -->
      <div
        class="flex items-center justify-between border-b border-slate-200 px-4 py-3"
      >
        <div class="flex items-center gap-3">
          <span class="text-sm font-medium text-slate-700">
            {{ interviewTypeLabel }}
          </span>
          <span
            v-if="progress"
            data-testid="chat-progress"
            class="text-xs text-slate-500"
          >
            进度: {{ progress.current_question }}/{{ progress.total_questions }}
            <template v-if="progress.follow_up_count > 0">
              · 追问 {{ progress.follow_up_count }}
            </template>
          </span>
        </div>
        <div class="flex items-center gap-2 text-xs text-slate-500">
          <Clock class="h-3.5 w-3.5" />
          <span data-testid="chat-elapsed">{{ formatTime(elapsedSeconds) }}</span>
        </div>
      </div>

      <!-- Messages area -->
      <div
        ref="messagesContainer"
        data-testid="chat-messages"
        class="flex-1 space-y-4 overflow-y-auto px-4 py-4"
      >
        <div
          v-for="msg in messages"
          :key="msg.id"
          :data-testid="
            msg.role === 'ASSISTANT' ? 'chat-message-assistant' : 'chat-message-user'
          "
          :class="[
            'flex',
            msg.role === 'ASSISTANT' ? 'justify-start' : 'justify-end',
          ]"
        >
          <div
            :class="[
              'max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-2 text-sm',
              msg.role === 'ASSISTANT'
                ? 'bg-slate-100 text-slate-900'
                : 'bg-blue-600 text-white',
            ]"
          >
            {{ msg.content }}
          </div>
        </div>

        <!-- AI thinking indicator -->
        <div
          v-if="aiThinking"
          data-testid="chat-thinking"
          class="flex justify-start"
        >
          <div class="rounded-lg bg-slate-100 px-4 py-2 text-sm text-slate-500">
            AI 正在思考...
          </div>
        </div>

        <!-- Completion banner -->
        <div
          v-if="isCompleted"
          data-testid="chat-completion-banner"
          class="rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700"
        >
          本次模拟面试已经结束，正在生成最终评估报告。
        </div>

        <!-- Cancelled banner -->
        <div
          v-if="isCancelled"
          data-testid="chat-cancelled-banner"
          class="rounded-lg bg-amber-50 px-4 py-3 text-sm text-amber-700"
        >
          本次模拟面试已取消。
        </div>
      </div>

      <!-- Action error -->
      <div
        v-if="actionError"
        data-testid="chat-action-error"
        class="flex items-center gap-2 border-t border-slate-200 bg-red-50 px-4 py-2 text-sm text-red-700"
      >
        <AlertTriangle class="h-4 w-4" />
        {{ actionError }}
      </div>

      <!-- Input area -->
      <div
        class="flex items-end gap-2 border-t border-slate-200 px-4 py-3"
      >
        <textarea
          v-model="draft"
          data-testid="chat-input"
          class="flex-1 resize-none rounded-md border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          rows="2"
          placeholder="请输入你的回答..."
          :disabled="!isActive"
          @keydown.enter.exact.prevent="sendMessage"
        />
        <Button
          data-testid="chat-send-button"
          :disabled="!canSend"
          @click="sendMessage"
        >
          <Send class="mr-1 h-4 w-4" />
          发送
        </Button>
        <Button
          v-if="!isCompleted && !isCancelled"
          data-testid="chat-complete-button"
          variant="outline"
          :disabled="!canComplete"
          @click="completeNow"
        >
          <Square class="mr-1 h-4 w-4" />
          结束面试
        </Button>
      </div>
    </div>
  </section>
</template>
