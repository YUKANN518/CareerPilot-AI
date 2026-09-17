<script setup lang="ts">
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BriefcaseBusiness,
  CheckCircle2,
  FileText,
  GraduationCap,
  Save,
  Sparkles,
  UserRound,
} from "@lucide/vue"
import { computed, onMounted, onUnmounted, ref } from "vue"
import { onBeforeRouteLeave, useRoute, useRouter } from "vue-router"

import { getApiErrorMessage } from "@/api/auth"
import {
  confirmResume,
  getParseResult,
  getResume,
  updateParseResult,
} from "@/api/resumes"
import ConfirmDialog from "@/components/domain/ConfirmDialog.vue"
import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import LoadingState from "@/components/domain/LoadingState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import ResumeEvidencePanel from "@/components/domain/ResumeEvidencePanel.vue"
import ResumeProfileEditor from "@/components/domain/ResumeProfileEditor.vue"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import type { EvidenceField, Resume, ResumeProfile } from "@/types/resume"

const route = useRoute()
const router = useRouter()
const resumeId = computed(() => Number(route.params.resumeId))
const resume = ref<Resume | null>(null)
const profile = ref<ResumeProfile | null>(null)
const activeEvidence = ref<EvidenceField | null>(null)
const lowConfidenceCount = ref(0)
const parseWarning = ref<string | null>(null)
const errorMessage = ref<string | null>(null)
const successMessage = ref<string | null>(null)
const isLoading = ref(true)
const isSaving = ref(false)
const isDirty = ref(false)
const isLeavingAfterConfirm = ref(false)
const confirmDialog = ref<InstanceType<typeof ConfirmDialog> | null>(null)

const completion = computed(() => {
  if (!profile.value) return 0
  const coreFields = [
    profile.value.basic_info.full_name,
    profile.value.basic_info.email,
    profile.value.basic_info.phone,
    profile.value.basic_info.location,
    profile.value.summary,
  ]
  const completed = coreFields.filter((field) => field.value.trim()).length
  return Math.round((completed / coreFields.length) * 100)
})

async function load(): Promise<void> {
  isLoading.value = true
  errorMessage.value = null
  try {
    const [parseResult, resumeResult] = await Promise.all([
      getParseResult(resumeId.value),
      getResume(resumeId.value),
    ])
    profile.value = parseResult.result
    lowConfidenceCount.value = parseResult.low_confidence_count
    parseWarning.value = parseResult.error_message
    resume.value = resumeResult
    activeEvidence.value = parseResult.result?.basic_info.full_name ?? null
    isDirty.value = false
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isLoading.value = false
  }
}

function markModified(): void {
  isDirty.value = true
  successMessage.value = null
}

function focusEvidence(field: EvidenceField): void {
  activeEvidence.value = field
}

async function saveDraft(): Promise<void> {
  if (!profile.value) return
  isSaving.value = true
  errorMessage.value = null
  successMessage.value = null
  try {
    const result = await updateParseResult(resumeId.value, profile.value)
    profile.value = result.result
    lowConfidenceCount.value = result.low_confidence_count
    activeEvidence.value = result.result?.basic_info.full_name ?? activeEvidence.value
    isDirty.value = false
    successMessage.value = "草稿已保存，尚未生成正式版本。"
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSaving.value = false
  }
}

function requestConfirmation(): void {
  confirmDialog.value?.open()
}

async function createConfirmedVersion(): Promise<void> {
  if (!profile.value) return
  isSaving.value = true
  errorMessage.value = null
  successMessage.value = null
  try {
    await updateParseResult(resumeId.value, profile.value)
    const version = await confirmResume(resumeId.value)
    isDirty.value = false
    isLeavingAfterConfirm.value = true
    await router.push({ name: "resume-version", params: { versionId: version.id } })
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isSaving.value = false
  }
}

function handleBeforeUnload(event: BeforeUnloadEvent): void {
  if (!isDirty.value || isLeavingAfterConfirm.value) return
  event.preventDefault()
  event.returnValue = ""
}

onBeforeRouteLeave(() => {
  if (!isDirty.value || isLeavingAfterConfirm.value) return true
  return window.confirm("存在未保存修改，确定离开解析确认页吗？")
})

onMounted(() => {
  window.addEventListener("beforeunload", handleBeforeUnload)
  void load()
})
onUnmounted(() => window.removeEventListener("beforeunload", handleBeforeUnload))
</script>

<template>
  <section class="space-y-6">
    <LoadingState
      v-if="isLoading"
      label="正在加载解析结果"
      :rows="6"
    />
    <ErrorState
      v-else-if="errorMessage && !profile"
      :message="errorMessage"
      @retry="load"
    />
    <template v-else-if="profile && resume">
      <PageHeader
        eyebrow="简历流程 · 第 3 步 / 共 3 步"
        title="确认解析结果"
        description="左侧查看真实证据片段，右侧逐项核对字段；只有二次确认后才会生成不可覆盖版本。"
      >
        <template #actions>
          <StatusBadge
            v-if="isDirty"
            tone="warning"
          >
            <AlertTriangle class="mr-1 size-3.5" />
            有未保存修改
          </StatusBadge>
          <StatusBadge
            v-else-if="lowConfidenceCount > 0"
            tone="warning"
          >
            <AlertTriangle class="mr-1 size-3.5" />
            {{ lowConfidenceCount }} 个字段需要核对
          </StatusBadge>
          <StatusBadge
            v-else
            tone="success"
          >
            <CheckCircle2 class="mr-1 size-3.5" />
            草稿已校验
          </StatusBadge>
        </template>
      </PageHeader>

      <div class="flex flex-wrap items-center gap-2 text-xs">
        <StatusBadge tone="success">高置信度</StatusBadge>
        <StatusBadge tone="warning">低置信度</StatusBadge>
        <StatusBadge tone="danger">无证据</StatusBadge>
        <StatusBadge tone="info">用户已修改</StatusBadge>
        <span class="ml-auto text-muted-foreground">
          核心资料完成度 {{ completion }}%
        </span>
      </div>

      <ErrorState
        v-if="errorMessage"
        compact
        title="修改未保存"
        :message="errorMessage"
      />
      <section
        v-else-if="successMessage"
        role="status"
        class="flex items-center gap-3 rounded-md border border-success/20 bg-success-soft p-4 text-sm text-success"
      >
        <CheckCircle2 class="size-5 shrink-0" />
        {{ successMessage }}
      </section>
      <section
        v-else-if="parseWarning"
        class="flex items-start gap-3 rounded-md border border-warning/20 bg-warning-soft p-4 text-sm text-warning"
      >
        <AlertTriangle class="mt-0.5 size-5 shrink-0" />
        {{ parseWarning }}
      </section>

      <div class="grid gap-6 xl:grid-cols-resume-review">
        <ResumeEvidencePanel
          :profile="profile"
          :file-format="resume.file.file_format"
          :file-name="resume.file.original_name"
          :active-evidence="activeEvidence"
        />

        <section class="rounded-lg border bg-surface p-5 shadow-sm">
          <div class="flex items-center justify-between gap-4 border-b pb-4">
            <div>
              <h2 class="font-semibold">结构化字段</h2>
              <p class="mt-1 text-xs text-muted-foreground">
                点击或聚焦字段时，左侧会定位到对应页码、段落和证据。
              </p>
            </div>
            <Sparkles class="size-5 text-primary" />
          </div>

          <div class="mt-5 grid grid-cols-3 gap-2 text-xs">
            <div class="flex items-center gap-2 rounded-md bg-primary-soft p-3 text-primary">
              <UserRound class="size-4" />
              基础信息
            </div>
            <div class="flex items-center gap-2 rounded-md bg-muted p-3 text-muted-foreground">
              <BriefcaseBusiness class="size-4" />
              工作与项目
            </div>
            <div class="flex items-center gap-2 rounded-md bg-muted p-3 text-muted-foreground">
              <GraduationCap class="size-4" />
              教育与技能
            </div>
          </div>

          <ResumeProfileEditor
            v-model="profile"
            class="mt-6"
            @focus-evidence="focusEvidence"
            @modified="markModified"
          />
        </section>
      </div>

      <div class="sticky bottom-0 z-20 flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-surface/95 p-4 shadow-lg backdrop-blur">
        <div class="flex min-w-0 items-center gap-3">
          <RouterLink
            :to="{ name: 'resume-status', params: { resumeId } }"
            class="inline-flex h-10 shrink-0 items-center rounded-sm border bg-surface px-4 text-sm font-semibold hover:bg-muted"
          >
            <ArrowLeft class="mr-2 size-4" />
            返回处理状态
          </RouterLink>
          <p
            v-if="isDirty"
            class="truncate text-xs font-medium text-warning"
          >
            修改尚未保存，离开页面前会再次提醒。
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button
            variant="outline"
            :disabled="isSaving || !isDirty"
            @click="saveDraft"
          >
            <Save class="mr-2 size-4" />
            {{ isSaving ? "保存中…" : "保存草稿" }}
          </Button>
          <Button
            :disabled="isSaving"
            @click="requestConfirmation"
          >
            <FileText class="mr-2 size-4" />
            确认简历
            <ArrowRight class="ml-2 size-4" />
          </Button>
        </div>
      </div>

      <ConfirmDialog
        ref="confirmDialog"
        title="确认并生成正式简历版本？"
        description="系统会先保存当前字段，再创建新的不可覆盖正式版本。历史版本不会被覆盖，此操作完成后可继续基于该结果创建下一版本。"
        confirm-label="确认简历"
        @confirm="createConfirmedVersion"
      />
    </template>
    <EmptyState
      v-else
      title="没有可确认的解析结果"
      description="请先完成文本提取和结构化解析，再进入人工确认。"
    />
  </section>
</template>
