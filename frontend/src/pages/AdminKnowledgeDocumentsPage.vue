<script setup lang="ts">
import {
  BookOpen,
  Database,
  FileCheck2,
  RefreshCw,
  Trash2,
  Upload,
} from "@lucide/vue"
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue"

import { getApiErrorMessage } from "@/api/errors"
import {
  deleteAdminKnowledgeDocument,
  listAdminKnowledgeDocuments,
  reindexAdminKnowledgeDocument,
  uploadAdminKnowledgeDocument,
} from "@/api/career-assistant"
import ConfirmDialog from "@/components/domain/ConfirmDialog.vue"
import EmptyState from "@/components/domain/EmptyState.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import FileDropzone from "@/components/domain/FileDropzone.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import PageSkeleton from "@/components/domain/PageSkeleton.vue"
import ToastMessage from "@/components/domain/ToastMessage.vue"
import { Button } from "@/components/ui/button"
import { FormMessage } from "@/components/ui/form-message"
import { Input } from "@/components/ui/input"
import { StatusBadge } from "@/components/ui/status-badge"
import type {
  KnowledgeDocument,
  KnowledgeDocumentStatus,
} from "@/types/career-assistant"

const MAX_SIZE_BYTES = 10 * 1024 * 1024
const ALLOWED_MIME = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
])

const documents = ref<KnowledgeDocument[]>([])
const loading = ref(true)
const acting = ref(false)
const pageError = ref<string | null>(null)
const toast = ref<string | null>(null)
const toastTone = ref<"success" | "danger">("success")
const confirmDialog = ref<InstanceType<typeof ConfirmDialog> | null>(null)
const pendingDocument = ref<KnowledgeDocument | null>(null)

const form = reactive({
  file: null as File | null,
  title: "",
  category: "guide",
})
const formError = ref<string | null>(null)
const uploadProgress = ref(0)
const activeAction = ref<string | null>(null)
const actionError = ref<Record<number, string>>({})
let statusPollTimer: ReturnType<typeof setInterval> | null = null

const statusMeta: Record<
  KnowledgeDocumentStatus,
  { label: string; tone: "neutral" | "success" | "danger" }
> = {
  PENDING: { label: "处理中", tone: "neutral" },
  PROCESSING: { label: "正在建立索引", tone: "neutral" },
  READY: { label: "已索引", tone: "success" },
  FAILED: { label: "失败", tone: "danger" },
}

const hasIndexingDocument = computed(() =>
  documents.value.some((document) =>
    ["PENDING", "PROCESSING"].includes(document.status),
  ),
)

const isFormValid = computed(
  () =>
    form.file !== null &&
    form.title.trim().length >= 1 &&
    form.title.trim().length <= 240 &&
    form.category.trim().length >= 1 &&
    form.category.trim().length <= 80,
)

function validateFile(file: File): string | null {
  const extension = file.name.split(".").pop()?.toLowerCase()
  if (extension !== "pdf" && extension !== "docx") {
    return "仅支持 PDF 或 DOCX 文件。"
  }
  if (file.size === 0) return "不能上传空文件。"
  if (file.size > MAX_SIZE_BYTES) return "文件大小不能超过 10MB。"
  if (file.type && !ALLOWED_MIME.has(file.type)) {
    return "浏览器识别的文件类型与扩展名不一致。"
  }
  return null
}

function chooseFile(file: File | null): void {
  form.file = file
  formError.value = file ? validateFile(file) : null
  if (file && !form.title) {
    const baseName = file.name.replace(/\.[^.]+$/, "")
    form.title = baseName.slice(0, 240)
  }
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}

async function load(): Promise<void> {
  loading.value = true
  pageError.value = null
  try {
    const result = await listAdminKnowledgeDocuments(0, 100)
    documents.value = result.items
  } catch (error) {
    pageError.value = getApiErrorMessage(error)
  } finally {
    loading.value = false
  }
}

async function pollStatuses(): Promise<void> {
  if (!hasIndexingDocument.value) {
    stopStatusPolling()
    return
  }
  try {
    const result = await listAdminKnowledgeDocuments(0, 100)
    documents.value = result.items
  } catch {
    // Keep the current list visible. A transient poll failure must not turn a
    // background indexing task into a false upload failure in the UI.
  }
}

function startStatusPolling(): void {
  if (statusPollTimer === null) {
    statusPollTimer = setInterval(() => {
      void pollStatuses()
    }, 1500)
  }
}

function stopStatusPolling(): void {
  if (statusPollTimer !== null) {
    clearInterval(statusPollTimer)
    statusPollTimer = null
  }
}

function processingMessage(document: KnowledgeDocument): string | null {
  if (!["PENDING", "PROCESSING"].includes(document.status)) return null
  const hasOffset = /(?:Z|[+-]\d{2}:\d{2})$/.test(document.updated_at)
  const updatedAt = new Date(hasOffset ? document.updated_at : `${document.updated_at}Z`)
  const elapsedMs = Date.now() - updatedAt.getTime()
  return elapsedMs > 120_000
    ? "处理时间较长，系统仍在后台继续建立索引。"
    : "正在解析文档、生成向量并写入本地索引。"
}

async function submitUpload(): Promise<void> {
  if (!isFormValid.value || acting.value) return
  if (!form.file) {
    formError.value = "请选择知识文档文件。"
    return
  }
  const validationError = validateFile(form.file)
  if (validationError) {
    formError.value = validationError
    return
  }
  acting.value = true
  formError.value = null
  uploadProgress.value = 0
  try {
    const created = await uploadAdminKnowledgeDocument(
      {
        file: form.file,
        title: form.title.trim(),
        category: form.category.trim(),
      },
      (percent) => {
        uploadProgress.value = percent
      },
    )
    documents.value = [created, ...documents.value]
    startStatusPolling()
    toast.value = `已上传，正在后台解析和建立索引：${created.title}`
    toastTone.value = "success"
    form.file = null
    form.title = ""
    form.category = "guide"
    uploadProgress.value = 0
  } catch (error) {
    formError.value = getApiErrorMessage(error)
  } finally {
    acting.value = false
  }
}

async function reindex(document: KnowledgeDocument): Promise<void> {
  if (acting.value || activeAction.value) return
  activeAction.value = `reindex-${document.id}`
  actionError.value[document.id] = ""
  try {
    const result = await reindexAdminKnowledgeDocument(document.id)
    const index = documents.value.findIndex((item) => item.id === document.id)
    if (index >= 0) {
      documents.value[index] = {
        ...documents.value[index],
        status: result.status,
        chunk_count: result.chunk_count,
        error_code: null,
        error_message: null,
        indexed_at: new Date().toISOString(),
      }
    }
    startStatusPolling()
    toast.value = `已开始重新索引：${document.title}`
    toastTone.value = "success"
  } catch (error) {
    actionError.value[document.id] = getApiErrorMessage(error)
    toast.value = `重新索引失败：${document.title}`
    toastTone.value = "danger"
  } finally {
    activeAction.value = null
  }
}

function askDelete(document: KnowledgeDocument): void {
  if (acting.value) return
  pendingDocument.value = document
  confirmDialog.value?.open()
}

async function confirmDelete(): Promise<void> {
  const document = pendingDocument.value
  if (!document) return
  activeAction.value = `delete-${document.id}`
  actionError.value[document.id] = ""
  try {
    await deleteAdminKnowledgeDocument(document.id)
    documents.value = documents.value.filter((item) => item.id !== document.id)
    toast.value = `已删除：${document.title}`
    toastTone.value = "success"
  } catch (error) {
    actionError.value[document.id] = getApiErrorMessage(error)
    toast.value = `删除失败：${document.title}`
    toastTone.value = "danger"
  } finally {
    activeAction.value = null
    pendingDocument.value = null
  }
}

onMounted(async () => {
  await load()
  if (hasIndexingDocument.value) startStatusPolling()
})

onBeforeUnmount(stopStatusPolling)
</script>

<template>
  <section class="space-y-6">
    <PageHeader
      eyebrow="知识库"
      title="知识库"
      description="上传 PDF/DOCX 知识文档并构建本地 FAISS 索引，供 AI 求职助手检索引用。"
    >
      <template #actions>
        <Button
          variant="outline"
          :disabled="loading"
          @click="load"
        >
          <RefreshCw class="mr-2 size-4" />
          刷新
        </Button>
      </template>
    </PageHeader>

    <PageSkeleton
      v-if="loading && documents.length === 0"
      label="正在加载知识库"
      :rows="5"
    />
    <ErrorState
      v-else-if="pageError"
      :message="pageError"
      @retry="load"
    />

    <div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <section class="space-y-4">
        <EmptyState
          v-if="documents.length === 0 && !loading"
          title="还没有知识文档"
          description="上传第一份 PDF 或 DOCX 文档即可开始构建知识库。"
          :icon="Database"
        />

        <section
          v-else
          class="rounded-lg border bg-surface p-5 shadow-sm"
        >
          <h2 class="flex items-center gap-2 text-sm font-semibold">
            <BookOpen class="size-4" />
            已索引文档（{{ documents.length }}）
          </h2>
          <ul class="mt-4 space-y-3">
            <li
              v-for="document in documents"
              :key="document.id"
              class="rounded-md border bg-background p-4"
              :data-testid="`knowledge-document-${document.id}`"
            >
              <div class="flex flex-wrap items-start justify-between gap-3">
                <div class="min-w-0">
                  <h3 class="truncate text-base font-semibold">{{ document.title }}</h3>
                  <p class="mt-1 text-xs text-muted-foreground">
                    分类：{{ document.category }} · {{ document.chunk_count }} 个分块
                  </p>
                  <p class="mt-1 text-xs text-muted-foreground">
                    上传于 {{ formatDate(document.created_at) }}
                    <span v-if="document.indexed_at">
                      · 索引于 {{ formatDate(document.indexed_at) }}
                    </span>
                  </p>
                  <p
                    v-if="document.error_message"
                    class="mt-2 text-xs text-danger"
                  >
                    {{ document.error_message }}
                  </p>
                  <p
                    v-else-if="processingMessage(document)"
                    class="mt-2 text-xs text-muted-foreground"
                  >
                    {{ processingMessage(document) }}
                  </p>
                </div>
                <div class="flex flex-col items-end gap-2">
                  <StatusBadge :tone="statusMeta[document.status].tone">
                    {{ statusMeta[document.status].label }}
                  </StatusBadge>
                  <div class="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      :disabled="['PENDING', 'PROCESSING'].includes(document.status) || activeAction === `reindex-${document.id}`"
                      :data-testid="`knowledge-document-reindex-${document.id}`"
                      @click="reindex(document)"
                    >
                      <RefreshCw
                        class="mr-1.5 size-3.5"
                        :class="activeAction === `reindex-${document.id}` ? 'animate-spin' : ''"
                      />
                      重新索引
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      :disabled="activeAction === `delete-${document.id}`"
                      :data-testid="`knowledge-document-delete-${document.id}`"
                      @click="askDelete(document)"
                    >
                      <Trash2 class="mr-1.5 size-3.5" />
                      删除
                    </Button>
                  </div>
                </div>
              </div>
              <p
                v-if="actionError[document.id]"
                class="mt-2 text-xs text-danger"
              >
                {{ actionError[document.id] }}
              </p>
            </li>
          </ul>
        </section>
      </section>

      <aside class="space-y-4">
        <section class="rounded-lg border bg-surface p-5 shadow-sm">
          <h2 class="flex items-center gap-2 text-sm font-semibold">
            <Upload class="size-4" />
            上传新文档
          </h2>
          <form
            class="mt-4 space-y-4"
            @submit.prevent="submitUpload"
          >
            <div>
              <label
                for="knowledge-title"
                class="text-xs font-semibold text-muted-foreground"
              >
                文档标题
              </label>
              <Input
                id="knowledge-title"
                v-model="form.title"
                data-testid="knowledge-title-input"
                :maxlength="240"
                :disabled="acting"
                placeholder="例如：后端工程师面试指南"
                class="mt-1.5"
              />
            </div>
            <div>
              <label
                for="knowledge-category"
                class="text-xs font-semibold text-muted-foreground"
              >
                分类
              </label>
              <Input
                id="knowledge-category"
                v-model="form.category"
                data-testid="knowledge-category-input"
                :maxlength="80"
                :disabled="acting"
                placeholder="例如：guide / interview / skill"
                class="mt-1.5"
              />
            </div>
            <div>
              <p class="text-xs font-semibold text-muted-foreground">文件</p>
              <FileDropzone
                class="mt-1.5"
                :selected-file="form.file"
                :disabled="acting"
                @select="chooseFile"
              />
            </div>

            <div
              v-if="acting || uploadProgress > 0"
              class="space-y-2 rounded-md bg-muted/70 p-3"
              role="status"
            >
              <div class="flex items-center justify-between text-xs">
                <span class="font-medium">正在上传文件</span>
                <strong class="text-primary">{{ uploadProgress }}%</strong>
              </div>
              <div class="h-2 overflow-hidden rounded-full bg-surface">
                <div
                  class="h-full rounded-full bg-primary transition-[width]"
                  :style="{ width: `${uploadProgress}%` }"
                />
              </div>
            </div>

            <FormMessage
              v-if="formError"
              :message="formError"
            />

            <Button
              type="submit"
              :disabled="acting || !isFormValid"
              class="w-full"
              data-testid="knowledge-upload-submit"
            >
              <FileCheck2 class="mr-2 size-4" />
              {{ acting ? "上传中…" : "上传并后台索引" }}
            </Button>
          </form>
        </section>

        <section class="rounded-lg border border-info/20 bg-info-soft p-5">
          <div class="flex items-start gap-3">
            <span class="grid size-9 shrink-0 place-items-center rounded-md bg-surface text-info">
              <Database class="size-5" />
            </span>
            <div>
              <h2 class="text-sm font-semibold">本地检索</h2>
              <p class="mt-2 text-xs leading-5 text-muted-foreground">
                上传后系统会提取文本分块并构建 FAISS 索引；用户问答时由后端检索 Top-K
                分块并交给 Dify 生成答案与引用，引用片段可追溯、不可伪造。
              </p>
            </div>
          </div>
        </section>
      </aside>
    </div>

    <ConfirmDialog
      ref="confirmDialog"
      title="删除知识文档"
      :description="`将删除“${pendingDocument?.title ?? ''}”及其索引，操作不可恢复。`"
      confirm-label="确认删除"
      danger
      @confirm="confirmDelete"
      @cancel="pendingDocument = null"
    />

    <ToastMessage
      :message="toast"
      :tone="toastTone"
      @dismiss="toast = null"
    />
  </section>
</template>
