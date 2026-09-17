<script setup lang="ts">
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  CheckCircle2,
  CircleAlert,
  Clock,
  FilePlus,
  Pencil,
  RefreshCw,
  RotateCcw,
  Tag,
  X,
} from "@lucide/vue"
import { computed, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getApiErrorInfo, getApiErrorMessage } from "@/api/errors"
import {
  confirmResumeOptimization,
  createResumeOptimizationVersion,
  getResumeOptimization,
  retryResumeOptimization,
} from "@/api/resume-optimizations"
import ErrorState from "@/components/domain/ErrorState.vue"
import ForbiddenState from "@/components/domain/ForbiddenState.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import PageSkeleton from "@/components/domain/PageSkeleton.vue"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import type {
  ResumeOptimization,
  ResumeOptimizationSection,
  ResumeOptimizationSectionConfirm,
  SectionChangeType,
} from "@/types/resume-optimization"

const route = useRoute()
const router = useRouter()
const optimization = ref<ResumeOptimization | null>(null)
const loading = ref(true)
const saving = ref(false)
const errorMessage = ref<string | null>(null)
const errorKind = ref<string | null>(null)

const editingSectionId = ref<string | null>(null)
const editBuffer = ref<string>("")
const sectionAccepted = ref<Record<string, boolean>>({})
const sectionEditedText = ref<Record<string, string | null>>({})
const attestTruth = ref(false)

const optimizationId = computed(() => Number(route.params.optimizationId))

const hasAnyEdit = computed(() => {
  if (!optimization.value) return false
  return optimization.value.sections.some((s) => {
    const edited = sectionEditedText.value[s.source_section_id]
    return edited != null && edited.trim() !== ""
  })
})

const canConfirm = computed(() => {
  if (!optimization.value || optimization.value.status !== "DRAFT") return false
  if (optimization.value.sections.length === 0) return false
  if (hasAnyEdit.value && !attestTruth.value) return false
  return true
})

const canCreateVersion = computed(() => {
  if (!optimization.value) return false
  return optimization.value.status === "CONFIRMED"
})

function normalizeOptimization(
  opt: ResumeOptimization,
): ResumeOptimization {
  return {
    ...opt,
    sections: (opt.sections ?? []).map((s) => ({
      ...s,
      evidence_keys: s.evidence_keys ?? [],
    })),
    keyword_suggestions: opt.keyword_suggestions ?? [],
    missing_evidence_warnings: opt.missing_evidence_warnings ?? [],
    fabrication_warnings: opt.fabrication_warnings ?? [],
  }
}

function syncSectionState(opt: ResumeOptimization): void {
  const accepted: Record<string, boolean> = {}
  const edited: Record<string, string | null> = {}
  for (const section of opt.sections) {
    accepted[section.source_section_id] = section.accepted
    edited[section.source_section_id] = section.edited_text
  }
  sectionAccepted.value = accepted
  sectionEditedText.value = edited
}

function statusTone(status: ResumeOptimization["status"]) {
  if (status === "CONFIRMED") return "success"
  if (status === "FAILED") return "danger"
  if (status === "ARCHIVED") return "neutral"
  return "warning"
}

function changeTypeLabel(type: SectionChangeType): string {
  const labels: Record<SectionChangeType, string> = {
    REWRITE: "重写",
    REORDER: "重排",
    SHORTEN: "精简",
    EMPHASIZE: "强调",
    NO_CHANGE: "保持原样",
  }
  return labels[type] ?? type
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = null
  errorKind.value = null
  try {
    const opt = normalizeOptimization(await getResumeOptimization(optimizationId.value))
    optimization.value = opt
    syncSectionState(opt)
  } catch (error) {
    const info = getApiErrorInfo(error)
    errorKind.value = info.kind
    errorMessage.value = info.message
  } finally {
    loading.value = false
  }
}

function acceptSection(section: ResumeOptimizationSection): void {
  sectionAccepted.value[section.source_section_id] = true
  editingSectionId.value = null
}

function rejectSection(section: ResumeOptimizationSection): void {
  sectionAccepted.value[section.source_section_id] = false
  sectionEditedText.value[section.source_section_id] = null
  editingSectionId.value = null
}

function startEditing(section: ResumeOptimizationSection): void {
  editingSectionId.value = section.source_section_id
  const existing = sectionEditedText.value[section.source_section_id]
  editBuffer.value =
    existing ?? section.suggested_text ?? section.original_text
}

function saveEdit(section: ResumeOptimizationSection): void {
  const trimmed = editBuffer.value.trim()
  if (!trimmed) return
  sectionEditedText.value[section.source_section_id] = trimmed
  sectionAccepted.value[section.source_section_id] = true
  editingSectionId.value = null
}

function cancelEdit(): void {
  editingSectionId.value = null
}

async function confirmOptimization(): Promise<void> {
  if (!optimization.value || saving.value) return
  saving.value = true
  try {
    const sections: ResumeOptimizationSectionConfirm[] =
      optimization.value.sections.map((s) => ({
        source_section_id: s.source_section_id,
        accepted: sectionAccepted.value[s.source_section_id] ?? false,
        edited_text: sectionEditedText.value[s.source_section_id] ?? null,
      }))
    const opt = normalizeOptimization(
      await confirmResumeOptimization(optimization.value.id, {
        sections,
        attest_truth: attestTruth.value,
      }),
    )
    optimization.value = opt
    syncSectionState(opt)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    saving.value = false
  }
}

async function retryOptimization(): Promise<void> {
  if (!optimization.value || saving.value) return
  saving.value = true
  try {
    const next = await retryResumeOptimization(optimization.value.id)
    await router.push({
      name: "resume-optimization-detail",
      params: { optimizationId: next.id },
    })
    const opt = normalizeOptimization(next)
    optimization.value = opt
    syncSectionState(opt)
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    saving.value = false
  }
}

async function createVersion(): Promise<void> {
  if (!optimization.value || saving.value) return
  saving.value = true
  try {
    const result = await createResumeOptimizationVersion(optimization.value.id)
    await router.push({
      name: "resume-version",
      params: {
        resumeId: result.resume_version.resume_id,
        versionId: result.resume_version.id,
      },
    })
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="space-y-6">
    <Button
      variant="ghost"
      class="px-0"
      @click="router.push({ name: 'resume-optimizations' })"
    >
      <ArrowLeft class="mr-2 size-4" />
      返回优化列表
    </Button>

    <PageSkeleton
      v-if="loading"
      label="正在加载优化建议"
      :rows="6"
    />
    <ForbiddenState
      v-else-if="errorKind === 'forbidden'"
      title="无权访问优化记录"
      description="你只能查看自己生成的简历优化记录。"
    />
    <ErrorState
      v-else-if="errorMessage && !optimization"
      :message="errorMessage"
      @retry="load"
    />
    <template v-else-if="optimization">
      <PageHeader
        eyebrow="简历优化（实验功能）"
        :title="optimization.summary || '简历优化建议'"
        :description="`简历版本 #${optimization.resume_version_id} · 岗位 #${optimization.job_id} · 匹配报告 #${optimization.match_report_id}`"
      >
        <template #actions>
          <StatusBadge :tone="statusTone(optimization.status)">
            {{ optimization.status }}
          </StatusBadge>
          <Button
            v-if="optimization.status === 'DRAFT'"
            :disabled="saving || !canConfirm"
            data-testid="confirm-optimization-button"
            @click="confirmOptimization"
          >
            <CheckCircle2 class="mr-2 size-4" />
            确认建议
          </Button>
          <Button
            v-if="optimization.status === 'FAILED'"
            variant="outline"
            :disabled="saving"
            data-testid="retry-optimization-button"
            @click="retryOptimization"
          >
            <RotateCcw class="mr-2 size-4" />
            重试生成
          </Button>
          <Button
            v-if="canCreateVersion"
            :disabled="saving"
            data-testid="create-version-button"
            @click="createVersion"
          >
            <FilePlus class="mr-2 size-4" />
            创建优化后简历版本
          </Button>
          <Button
            variant="outline"
            @click="load"
          >
            <RefreshCw class="mr-2 size-4" />
            刷新
          </Button>
        </template>
      </PageHeader>

      <ErrorState
        v-if="errorMessage"
        :message="errorMessage"
        compact
        @retry="load"
      />

      <section
        v-if="optimization.error_message"
        class="rounded-lg border border-danger/30 bg-danger-soft p-5"
      >
        <div class="flex items-start gap-3">
          <AlertTriangle class="mt-0.5 size-5 shrink-0 text-danger" />
          <div>
            <h2 class="font-semibold text-danger">生成失败</h2>
            <p class="mt-1 text-sm leading-6 text-danger/85">
              {{ optimization.error_message }}
            </p>
            <p
              v-if="optimization.error_code"
              class="mt-1 text-xs text-danger/70"
            >
              错误码：{{ optimization.error_code }}
            </p>
          </div>
        </div>
      </section>

      <section
        v-if="optimization.job_information_warning"
        class="rounded-lg border border-warning/30 bg-warning-soft p-4 text-sm leading-6 text-warning"
        data-testid="job-information-warning"
      >
        <div class="flex items-start gap-2">
          <CircleAlert class="mt-0.5 size-4 shrink-0" />
          <span>{{ optimization.job_information_warning }}</span>
        </div>
      </section>

      <section
        v-if="optimization.missing_evidence_warnings.length"
        class="rounded-lg border border-info/30 bg-info-soft p-4 text-sm leading-6 text-info"
      >
        <p class="font-semibold">缺少证据提示</p>
        <ul class="mt-2 list-disc space-y-1 pl-5">
          <li
            v-for="warning in optimization.missing_evidence_warnings"
            :key="warning"
          >
            {{ warning }}
          </li>
        </ul>
      </section>

      <section
        v-if="optimization.sections.length"
        class="rounded-lg border bg-surface p-5 shadow-sm"
      >
        <h2 class="text-section-title font-semibold">逐段优化建议</h2>
        <div class="mt-4 space-y-4">
          <article
            v-for="section in optimization.sections"
            :key="section.source_section_id"
            class="rounded-md border bg-background p-4"
            data-testid="optimization-section-card"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <h3 class="font-semibold">{{ section.section }}</h3>
                  <StatusBadge tone="neutral">
                    {{ changeTypeLabel(section.change_type) }}
                  </StatusBadge>
                  <code class="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                    {{ section.source_section_id }}
                  </code>
                </div>
                <p
                  v-if="section.related_job_requirement"
                  class="mt-1 text-sm leading-6 text-muted-foreground"
                >
                  对应岗位要求：{{ section.related_job_requirement }}
                </p>
              </div>
              <div class="flex items-center gap-2">
                <Button
                  v-if="optimization.status === 'DRAFT' && editingSectionId !== section.source_section_id"
                  size="sm"
                  :variant="sectionAccepted[section.source_section_id] ? 'default' : 'outline'"
                  :disabled="saving"
                  :data-testid="`accept-section-${section.source_section_id}`"
                  @click="acceptSection(section)"
                >
                  <Check class="mr-1 size-3" />
                  接受
                </Button>
                <Button
                  v-if="optimization.status === 'DRAFT' && editingSectionId !== section.source_section_id"
                  size="sm"
                  variant="ghost"
                  :disabled="saving"
                  :data-testid="`reject-section-${section.source_section_id}`"
                  @click="rejectSection(section)"
                >
                  <X class="mr-1 size-3" />
                  保留原文
                </Button>
                <Button
                  v-if="optimization.status === 'DRAFT' && editingSectionId !== section.source_section_id"
                  size="sm"
                  variant="ghost"
                  :disabled="saving"
                  :data-testid="`edit-section-${section.source_section_id}`"
                  @click="startEditing(section)"
                >
                  <Pencil class="mr-1 size-3" />
                  编辑
                </Button>
              </div>
            </div>

            <div class="mt-3 grid gap-3 md:grid-cols-2">
              <div>
                <p class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  原文
                </p>
                <p class="mt-1 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
                  {{ section.original_text || "（空）" }}
                </p>
              </div>
              <div>
                <p class="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                  建议内容
                </p>
                <p
                  v-if="editingSectionId !== section.source_section_id"
                  class="mt-1 whitespace-pre-wrap text-sm leading-6 text-foreground"
                  data-testid="suggested-text"
                >
                  {{
                    sectionEditedText[section.source_section_id] ??
                      section.suggested_text ??
                      "（空）"
                  }}
                </p>
                <div
                  v-else
                  class="mt-1 space-y-2"
                >
                  <textarea
                    v-model="editBuffer"
                    class="w-full rounded-md border bg-background p-3 text-sm leading-6 text-foreground focus:border-primary focus:outline-none"
                    rows="5"
                    data-testid="edit-textarea"
                  />
                  <div class="flex gap-2">
                    <Button
                      size="sm"
                      :disabled="!editBuffer.trim()"
                      data-testid="save-edit-button"
                      @click="saveEdit(section)"
                    >
                      保存编辑
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      data-testid="cancel-edit-button"
                      @click="cancelEdit"
                    >
                      取消
                    </Button>
                  </div>
                </div>
              </div>
            </div>

            <p
              v-if="section.reason"
              class="mt-3 text-sm leading-6 text-muted-foreground"
            >
              <span class="font-semibold">修改原因：</span>{{ section.reason }}
            </p>

            <div
              v-if="section.evidence_keys.length"
              class="mt-3 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"
            >
              <Tag class="size-3" />
              <span>证据来源：</span>
              <code
                v-for="key in section.evidence_keys"
                :key="key"
                class="rounded bg-muted px-1.5 py-0.5"
              >{{ key }}</code>
            </div>
          </article>
        </div>
      </section>

      <section
        v-if="optimization.status === 'DRAFT' && hasAnyEdit"
        class="rounded-lg border border-warning/30 bg-warning-soft p-4"
        data-testid="attest-truth-section"
      >
        <label class="flex items-start gap-3 text-sm leading-6 text-warning">
          <input
            v-model="attestTruth"
            type="checkbox"
            class="mt-0.5 size-4 shrink-0 cursor-pointer"
            data-testid="attest-truth-checkbox"
          >
          <span>我确认手动编辑的内容真实准确，并可在需要时提供证明。</span>
        </label>
        <p
          v-if="!attestTruth"
          class="mt-2 text-xs text-warning/70"
        >
          勾选后才能确认包含手动编辑的建议。
        </p>
      </section>

      <section
        v-if="optimization.keyword_suggestions.length"
        class="rounded-lg border bg-surface p-5 shadow-sm"
      >
        <h2 class="text-section-title font-semibold">关键词建议</h2>
        <div class="mt-4 flex flex-wrap gap-2">
          <div
            v-for="kw in optimization.keyword_suggestions"
            :key="kw.keyword"
            class="rounded-md border bg-background px-3 py-2"
          >
            <p class="text-sm font-semibold">{{ kw.keyword }}</p>
            <p class="mt-1 text-xs text-muted-foreground">{{ kw.reason }}</p>
          </div>
        </div>
      </section>

      <section class="grid gap-4 md:grid-cols-3">
        <div class="rounded-lg border bg-surface p-4">
          <p class="text-xs text-muted-foreground">流程</p>
          <p class="mt-1 text-sm font-semibold">
            {{ optimization.workflow_version || "未记录" }}
          </p>
        </div>
        <div class="rounded-lg border bg-surface p-4">
          <p class="text-xs text-muted-foreground">运行编号</p>
          <p class="mt-1 break-all text-sm font-semibold">
            {{ optimization.workflow_run_id || "未记录" }}
          </p>
        </div>
        <div class="rounded-lg border bg-surface p-4">
          <p class="text-xs text-muted-foreground">Provider / 耗时</p>
          <p class="mt-1 flex items-center gap-1 text-sm font-semibold">
            <Clock class="size-3" />
            {{ optimization.provider || "unknown" }} ·
            {{ optimization.latency_ms ?? 0 }}ms
          </p>
        </div>
      </section>
    </template>
  </section>
</template>
