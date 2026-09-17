<script setup lang="ts">
import {
  AlertOctagon,
  BrainCircuit,
  Check,
  ChevronRight,
  CircleDashed,
  Clock3,
  Eye,
  FileCheck2,
  FileSearch,
  FileText,
  Link2,
  LoaderCircle,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
  Square,
} from "@lucide/vue"
import axios from "axios"
import { computed, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getApiErrorMessage } from "@/api/auth"
import {
  downloadResumeFile,
  extractResume,
  getResume,
  listResumeVersions,
  parseResume,
} from "@/api/resumes"
import ConfirmDialog from "@/components/domain/ConfirmDialog.vue"
import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import LoadingState from "@/components/domain/LoadingState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import ResumeStatusBadge from "@/components/domain/ResumeStatusBadge.vue"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import type { Resume, ResumeStatus, ResumeVersion } from "@/types/resume"

type StageState = "pending" | "running" | "success" | "failed" | "unsupported"
type ActionName = "extract" | "parse"

interface ProcessStage {
  key: string
  title: string
  description: string
  state: StageState
  timing: string
  error?: string
}

const route = useRoute()
const router = useRouter()
const resumeId = computed(() => Number(route.params.resumeId))
const resume = ref<Resume | null>(null)
const versions = ref<ResumeVersion[]>([])
const isLoading = ref(true)
const activeAction = ref<ActionName | null>(null)
const requestController = ref<AbortController | null>(null)
const stopDialog = ref<InstanceType<typeof ConfirmDialog> | null>(null)
const errorMessage = ref<string | null>(null)
const actionNotice = ref<string | null>(null)
const extractionStats = ref<{ characters: number; blocks: number } | null>(null)

const progressByStatus: Record<ResumeStatus, number> = {
  UPLOADED: 16,
  EXTRACTING: 24,
  EXTRACTED: 33,
  PARSING: 48,
  NEEDS_CONFIRMATION: 83,
  CONFIRMED: 100,
  FAILED: 16,
  ARCHIVED: 100,
}

const progress = computed(() =>
  resume.value ? progressByStatus[resume.value.status] : 0,
)
const isScannedPdfUnsupported = computed(
  () =>
    resume.value?.file.file_format === "pdf" &&
    resume.value.last_error_code === "SCANNED_PDF_UNSUPPORTED",
)
const statusTitle = computed(() => {
  if (!resume.value) return "简历处理状态"
  const titles: Record<ResumeStatus, string> = {
    UPLOADED: "简历已就绪，等待开始处理",
    EXTRACTING: "正在提取简历文本",
    EXTRACTED: "文本提取完成，等待结构化解析",
    PARSING: "正在解析简历",
    NEEDS_CONFIRMATION: "解析完成，等待你的确认",
    CONFIRMED: "简历处理已完成",
    FAILED: isScannedPdfUnsupported.value
      ? "扫描版 PDF 暂不支持"
      : "简历处理遇到问题",
    ARCHIVED: "简历已归档",
  }
  return titles[resume.value.status]
})

function formatMoment(value: string | null): string {
  if (!value) return "尚未开始"
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value))
}

function formatElapsed(start: string | null, end: string | null): string {
  if (!start || !end) return "—"
  const elapsed = Math.max(0, new Date(end).getTime() - new Date(start).getTime())
  if (elapsed < 1000) return "< 1 秒"
  if (elapsed < 60_000) return `${Math.round(elapsed / 1000)} 秒`
  return `${Math.floor(elapsed / 60_000)} 分 ${Math.round((elapsed % 60_000) / 1000)} 秒`
}

const processStages = computed<ProcessStage[]>(() => {
  if (!resume.value) return []
  const item = resume.value
  const extracted = Boolean(item.extracted_at)
  const parsed = Boolean(item.parsed_at)
  const confirmed = Boolean(item.confirmed_at)
  const extractionRunning = activeAction.value === "extract" || item.status === "EXTRACTING"
  const parsingRunning = activeAction.value === "parse" || item.status === "PARSING"
  const extractionFailed = item.status === "FAILED" && !extracted
  const parsedState: StageState = parsed
    ? "success"
    : parsingRunning
      ? "running"
      : "pending"

  return [
    {
      key: "validation",
      title: "文件校验",
      description: "扩展名、MIME、文件签名与内部结构",
      state: "success",
      timing: formatMoment(item.created_at),
    },
    {
      key: "extraction",
      title: "文本提取",
      description: "保留 PDF 页码或 DOCX 段落来源",
      state: extracted
        ? "success"
        : extractionRunning
          ? "running"
          : isScannedPdfUnsupported.value
            ? "unsupported"
            : extractionFailed
              ? "failed"
              : "pending",
      timing: extracted
        ? `${formatElapsed(item.created_at, item.extracted_at)} · ${formatMoment(item.extracted_at)}`
        : extractionRunning
          ? "服务器处理中"
          : "尚未开始",
      error: extractionFailed ? item.last_error_message ?? undefined : undefined,
    },
    {
      key: "parsing",
      title: "AI 结构化解析",
      description: "提取基本信息、经历、技能与置信度",
      state: parsedState,
      timing: parsed
        ? `${formatElapsed(item.extracted_at, item.parsed_at)} · ${formatMoment(item.parsed_at)}`
        : parsingRunning
          ? `第 ${Math.max(1, item.parse_attempts)} 次尝试`
          : "尚未开始",
      error: item.last_error_code === "AI_PARSE_FAILED" ? item.last_error_message ?? undefined : undefined,
    },
    {
      key: "field-validation",
      title: "字段校验",
      description: "严格 Schema、类型与低置信度字段校验",
      state: parsedState,
      timing: parsed ? `与解析同步完成 · ${formatMoment(item.parsed_at)}` : "尚未开始",
    },
    {
      key: "evidence",
      title: "证据关联",
      description: "验证技能证据存在于原文并保留来源位置",
      state: parsedState,
      timing: parsed ? `与解析同步完成 · ${formatMoment(item.parsed_at)}` : "尚未开始",
    },
    {
      key: "confirmation",
      title: "等待确认",
      description: "人工核对后生成不可覆盖的正式版本",
      state: confirmed
        ? "success"
        : item.status === "NEEDS_CONFIRMATION"
          ? "running"
          : "pending",
      timing: confirmed
        ? `${formatElapsed(item.parsed_at, item.confirmed_at)} · ${formatMoment(item.confirmed_at)}`
        : item.status === "NEEDS_CONFIRMATION"
          ? `自 ${formatMoment(item.parsed_at)} 等待确认`
          : "尚未开始",
    },
  ]
})

const stageSummary = computed(() => ({
  success: processStages.value.filter((stage) => stage.state === "success").length,
  running: processStages.value.filter((stage) => stage.state === "running").length,
  attention: processStages.value.filter((stage) =>
    ["failed", "unsupported"].includes(stage.state),
  ).length,
}))

async function fetchResumeData(): Promise<void> {
  ;[resume.value, versions.value] = await Promise.all([
    getResume(resumeId.value),
    listResumeVersions(resumeId.value),
  ])
}

async function load(): Promise<void> {
  isLoading.value = true
  errorMessage.value = null
  try {
    await fetchResumeData()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

async function refreshAfterAction(): Promise<void> {
  try {
    await fetchResumeData()
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  }
}

async function runAction(action: ActionName): Promise<void> {
  activeAction.value = action
  errorMessage.value = null
  actionNotice.value = null
  const controller = new AbortController()
  requestController.value = controller
  try {
    if (action === "extract") {
      const result = await extractResume(resumeId.value, controller.signal)
      extractionStats.value = {
        characters: result.character_count,
        blocks: result.blocks.length,
      }
    } else {
      const result = await parseResume(resumeId.value, controller.signal)
      if (result.status === "NEEDS_CONFIRMATION") {
        await router.push({ name: "resume-confirm", params: { resumeId: resumeId.value } })
        return
      }
    }
    await refreshAfterAction()
  } catch (error) {
    if (axios.isCancel(error)) {
      actionNotice.value =
        "已停止等待本次请求。服务器可能继续处理，刷新后可查看最终状态。"
    } else {
      errorMessage.value = getApiErrorMessage(error)
    }
    await refreshAfterAction()
  } finally {
    if (requestController.value === controller) requestController.value = null
    activeAction.value = null
  }
}

function retryFailedStage(): void {
  void runAction(resume.value?.extracted_at ? "parse" : "extract")
}

function requestStop(): void {
  stopDialog.value?.open()
}

function stopCurrentRequest(): void {
  requestController.value?.abort()
}

async function previewFile(): Promise<void> {
  if (!resume.value) return
  errorMessage.value = null
  try {
    const blob = await downloadResumeFile(resume.value.id)
    const url = URL.createObjectURL(blob)
    window.open(url, "_blank", "noopener,noreferrer")
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  }
}

function formatSize(size: number): string {
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(1)} MB`
}

function stateLabel(state: StageState): string {
  return {
    pending: "待处理",
    running: "处理中",
    success: "已完成",
    failed: "失败",
    unsupported: "不支持",
  }[state]
}

onMounted(load)
</script>

<template>
  <section class="space-y-6">
    <LoadingState
      v-if="isLoading"
      label="正在读取处理状态"
      :rows="6"
    />
    <ErrorState
      v-else-if="errorMessage && !resume"
      :message="errorMessage"
      @retry="load"
    />
    <template v-else-if="resume">
      <PageHeader
        eyebrow="简历流程 · 第 2 步 / 共 3 步"
        :title="statusTitle"
        description="所有进度均来自服务器真实状态，页面不会模拟处理结果。"
      >
        <template #actions>
          <Button
            variant="outline"
            @click="previewFile"
          >
            <Eye class="mr-2 size-4" />
            预览原文件
          </Button>
          <Button
            v-if="activeAction"
            variant="danger"
            @click="requestStop"
          >
            <Square class="mr-2 size-3.5" />
            停止任务
          </Button>
        </template>
      </PageHeader>

      <ErrorState
        v-if="errorMessage"
        compact
        title="本次操作未完成"
        :message="errorMessage"
      />
      <section
        v-else-if="actionNotice"
        role="status"
        class="rounded-md border border-info/20 bg-info-soft p-4 text-sm text-info"
      >
        {{ actionNotice }}
      </section>

      <section class="rounded-lg border bg-surface p-5 shadow-sm">
        <div class="flex flex-wrap items-center gap-4">
          <span class="grid size-12 shrink-0 place-items-center rounded-md bg-primary-soft text-xs font-bold text-primary">
            {{ resume.file.file_format.toUpperCase() }}
          </span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="truncate font-semibold">{{ resume.title }}</h2>
              <ResumeStatusBadge :status="resume.status" />
            </div>
            <p class="mt-1 truncate text-xs text-muted-foreground">
              {{ resume.file.original_name }} · {{ formatSize(resume.file.size_bytes) }} ·
              SHA-256 {{ resume.file.sha256.slice(0, 12) }}…
            </p>
          </div>
          <dl class="grid grid-cols-3 gap-6 text-center text-xs">
            <div>
              <dt class="text-muted-foreground">总进度</dt>
              <dd class="mt-1 text-lg font-bold">{{ progress }}%</dd>
            </div>
            <div>
              <dt class="text-muted-foreground">解析次数</dt>
              <dd class="mt-1 text-lg font-bold">{{ resume.parse_attempts }}</dd>
            </div>
            <div>
              <dt class="text-muted-foreground">正式版本</dt>
              <dd class="mt-1 text-lg font-bold">{{ versions.length }}</dd>
            </div>
          </dl>
        </div>
      </section>

      <section
        v-if="isScannedPdfUnsupported"
        class="flex items-start gap-4 rounded-lg border border-warning/30 bg-warning-soft p-5"
      >
        <span class="grid size-10 shrink-0 place-items-center rounded-md bg-surface text-warning">
          <AlertOctagon class="size-5" />
        </span>
        <div>
          <h2 class="font-semibold text-warning">扫描版 PDF 不支持自动解析</h2>
          <p class="mt-1 text-sm leading-6 text-muted-foreground">
            {{ resume.last_error_message }}。请上传带可选择文本层的 PDF，或将内容转换为 DOCX 后重试。
          </p>
        </div>
      </section>

      <div class="grid gap-6 xl:grid-cols-3">
        <section class="rounded-lg border bg-surface p-5 shadow-sm xl:col-span-2">
          <div class="flex items-end justify-between gap-4">
            <div>
              <p class="text-sm font-medium text-muted-foreground">真实处理进度</p>
              <div class="mt-2 flex items-baseline gap-2">
                <strong class="text-4xl tracking-tight">{{ progress }}%</strong>
                <span class="text-xs text-muted-foreground">
                  更新于 {{ formatMoment(resume.updated_at) }}
                </span>
              </div>
            </div>
            <StatusBadge
              v-if="activeAction"
              tone="primary"
            >
              <LoaderCircle class="mr-1 size-3 animate-spin" />
              请求处理中
            </StatusBadge>
          </div>
          <div class="mt-4 h-2 overflow-hidden rounded-full bg-muted">
            <div
              class="h-full rounded-full bg-primary transition-[width] duration-slow"
              :style="{ width: `${progress}%` }"
            />
          </div>

          <ol class="mt-7">
            <li
              v-for="(stage, index) in processStages"
              :key="stage.key"
              class="flex gap-4"
            >
              <div class="flex w-9 shrink-0 flex-col items-center">
                <span
                  class="grid size-9 place-items-center rounded-full border text-xs font-bold"
                  :class="{
                    'border-success bg-success text-white': stage.state === 'success',
                    'border-primary bg-primary text-white': stage.state === 'running',
                    'border-danger bg-danger text-white': stage.state === 'failed',
                    'border-warning bg-warning text-white': stage.state === 'unsupported',
                    'border-border bg-surface text-muted-foreground': stage.state === 'pending',
                  }"
                >
                  <Check
                    v-if="stage.state === 'success'"
                    class="size-4"
                  />
                  <LoaderCircle
                    v-else-if="stage.state === 'running'"
                    class="size-4 animate-spin"
                  />
                  <AlertOctagon
                    v-else-if="['failed', 'unsupported'].includes(stage.state)"
                    class="size-4"
                  />
                  <span v-else>{{ index + 1 }}</span>
                </span>
                <span
                  v-if="index < processStages.length - 1"
                  class="min-h-10 w-px flex-1"
                  :class="stage.state === 'success' ? 'bg-success/30' : 'bg-border'"
                />
              </div>
              <div class="flex min-w-0 flex-1 items-start justify-between gap-4 pb-6 pt-1">
                <div>
                  <div class="flex flex-wrap items-center gap-2">
                    <p class="text-sm font-semibold">{{ stage.title }}</p>
                    <StatusBadge
                      :tone="
                        stage.state === 'success'
                          ? 'success'
                          : stage.state === 'running'
                            ? 'primary'
                            : ['failed', 'unsupported'].includes(stage.state)
                              ? 'warning'
                              : 'neutral'
                      "
                    >
                      {{ stateLabel(stage.state) }}
                    </StatusBadge>
                  </div>
                  <p class="mt-1 text-xs leading-5 text-muted-foreground">
                    {{ stage.description }}
                  </p>
                  <p
                    v-if="stage.error"
                    class="mt-2 text-xs font-medium text-danger"
                  >
                    {{ stage.error }}
                  </p>
                </div>
                <span class="shrink-0 text-right text-xs leading-5 text-muted-foreground">
                  {{ stage.timing }}
                </span>
              </div>
            </li>
          </ol>

          <div class="flex flex-wrap gap-2 border-t pt-5">
            <Button
              v-if="resume.status === 'UPLOADED'"
              :disabled="activeAction !== null"
              @click="runAction('extract')"
            >
              <ScanSearch class="mr-2 size-4" />
              提取文本
            </Button>
            <Button
              v-if="resume.status === 'EXTRACTED'"
              :disabled="activeAction !== null"
              @click="runAction('parse')"
            >
              <BrainCircuit class="mr-2 size-4" />
              执行结构化解析
            </Button>
            <Button
              v-if="resume.status === 'FAILED' && !isScannedPdfUnsupported"
              :disabled="activeAction !== null"
              @click="retryFailedStage"
            >
              <RefreshCw class="mr-2 size-4" />
              重试失败节点
            </Button>
            <RouterLink
              v-if="resume.status === 'NEEDS_CONFIRMATION'"
              :to="{ name: 'resume-confirm', params: { resumeId } }"
              class="inline-flex h-10 items-center rounded-sm bg-primary px-4 text-sm font-semibold text-white hover:bg-primary-hover"
            >
              打开解析确认页
              <ChevronRight class="ml-2 size-4" />
            </RouterLink>
            <Button
              v-if="resume.status === 'EXTRACTED'"
              variant="outline"
              :disabled="activeAction !== null"
              @click="runAction('extract')"
            >
              <RefreshCw class="mr-2 size-4" />
              重新提取
            </Button>
          </div>
        </section>

        <aside class="space-y-4">
          <section class="rounded-lg border bg-surface p-5 shadow-sm">
            <div class="flex items-center justify-between">
              <div>
                <h2 class="text-sm font-semibold">实时处理结果</h2>
                <p class="mt-1 text-xs text-muted-foreground">来自当前真实流程</p>
              </div>
              <FileSearch class="size-5 text-primary" />
            </div>
            <dl class="mt-4 grid grid-cols-3 gap-2">
              <div class="rounded-md bg-success-soft p-3 text-center">
                <dt class="text-xs text-muted-foreground">完成</dt>
                <dd class="mt-1 text-lg font-bold text-success">{{ stageSummary.success }}</dd>
              </div>
              <div class="rounded-md bg-primary-soft p-3 text-center">
                <dt class="text-xs text-muted-foreground">进行中</dt>
                <dd class="mt-1 text-lg font-bold text-primary">{{ stageSummary.running }}</dd>
              </div>
              <div class="rounded-md bg-warning-soft p-3 text-center">
                <dt class="text-xs text-muted-foreground">需处理</dt>
                <dd class="mt-1 text-lg font-bold text-warning">{{ stageSummary.attention }}</dd>
              </div>
            </dl>
            <ul class="mt-4 space-y-3 text-xs">
              <li class="flex items-center justify-between gap-3">
                <span class="flex items-center gap-2 text-muted-foreground">
                  <FileText class="size-3.5" />
                  提取字符
                </span>
                <strong>{{ extractionStats?.characters ?? "本次会话暂无" }}</strong>
              </li>
              <li class="flex items-center justify-between gap-3">
                <span class="flex items-center gap-2 text-muted-foreground">
                  <Link2 class="size-3.5" />
                  来源块
                </span>
                <strong>{{ extractionStats?.blocks ?? "本次会话暂无" }}</strong>
              </li>
              <li class="flex items-center justify-between gap-3">
                <span class="flex items-center gap-2 text-muted-foreground">
                  <Clock3 class="size-3.5" />
                  解析尝试
                </span>
                <strong>{{ resume.parse_attempts }}</strong>
              </li>
              <li class="flex items-center justify-between gap-3">
                <span class="flex items-center gap-2 text-muted-foreground">
                  <ShieldCheck class="size-3.5" />
                  所有权校验
                </span>
                <StatusBadge tone="success">已保护</StatusBadge>
              </li>
            </ul>
          </section>

          <section class="rounded-lg border bg-surface p-5 shadow-sm">
            <div class="flex items-center justify-between gap-3">
              <h2 class="text-sm font-semibold">版本历史</h2>
              <StatusBadge tone="neutral">{{ versions.length }} 个版本</StatusBadge>
            </div>
            <div
              v-if="versions.length === 0"
              class="mt-4 flex items-start gap-3 rounded-md bg-muted p-3"
            >
              <CircleDashed class="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <p class="text-xs leading-5 text-muted-foreground">
                确认解析结果后才会生成第一个不可覆盖版本。
              </p>
            </div>
            <ul
              v-else
              class="mt-3 space-y-2"
            >
              <li
                v-for="historyVersion in versions"
                :key="historyVersion.id"
              >
                <RouterLink
                  class="flex items-center gap-3 rounded-md border p-3 hover:border-primary hover:bg-primary-soft"
                  :to="{ name: 'resume-version', params: { versionId: historyVersion.id } }"
                >
                  <span class="grid size-8 place-items-center rounded-full bg-success-soft text-success">
                    <FileCheck2 class="size-4" />
                  </span>
                  <span class="min-w-0 flex-1">
                    <strong class="block text-xs">版本 {{ historyVersion.version_number }}</strong>
                    <span class="text-xs text-muted-foreground">已确认</span>
                  </span>
                  <ChevronRight class="size-4 text-muted-foreground" />
                </RouterLink>
              </li>
            </ul>
          </section>
        </aside>
      </div>

      <ConfirmDialog
        ref="stopDialog"
        title="停止当前处理任务？"
        description="确认后会中止浏览器等待；服务器可能继续完成本次提取或解析，刷新页面即可查看最终状态。"
        confirm-label="停止等待"
        danger
        @confirm="stopCurrentRequest"
      />
    </template>
    <EmptyState
      v-else
      title="未找到简历"
      description="该简历可能已删除，或当前账号没有访问权限。"
    />
  </section>
</template>
