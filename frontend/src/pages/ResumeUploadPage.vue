<script setup lang="ts">
import {
  ArrowRight,
  CheckCircle2,
  FileCheck2,
  FileText,
  Info,
  LockKeyhole,
  ScanSearch,
  ShieldCheck,
} from "@lucide/vue"
import { ref } from "vue"
import { useRouter } from "vue-router"

import { getApiErrorMessage } from "@/api/auth"
import { uploadResume } from "@/api/resumes"
import FileDropzone from "@/components/domain/FileDropzone.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import { Button } from "@/components/ui/button"
import { FormMessage } from "@/components/ui/form-message"
import { StatusBadge } from "@/components/ui/status-badge"

const MAX_SIZE_BYTES = 10 * 1024 * 1024
const ALLOWED_MIME = new Set([
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
])

const router = useRouter()
const selectedFile = ref<File | null>(null)
const progress = ref(0)
const isUploading = ref(false)
const errorMessage = ref<string | null>(null)

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
  selectedFile.value = file
  errorMessage.value = file ? validateFile(file) : null
  progress.value = 0
}

async function submit(): Promise<void> {
  if (!selectedFile.value) {
    errorMessage.value = "请选择一个简历文件。"
    return
  }
  const validationError = validateFile(selectedFile.value)
  if (validationError) {
    errorMessage.value = validationError
    return
  }
  isUploading.value = true
  errorMessage.value = null
  try {
    const result = await uploadResume(selectedFile.value, (value) => {
      progress.value = value
    })
    await router.push({
      name: "resume-status",
      params: { resumeId: result.resume.id },
    })
  } catch (error) {
    errorMessage.value = getApiErrorMessage(error)
  } finally {
    isUploading.value = false
  }
}
</script>

<template>
  <section class="space-y-6">
    <PageHeader
      eyebrow="Resume workflow"
      title="上传简历"
      description="AI 将读取简历内容并生成结构化草稿，所有解析结果都需要你人工确认。"
    >
      <template #actions>
        <RouterLink
          :to="{ name: 'resumes' }"
          class="inline-flex h-10 items-center rounded-sm border bg-surface px-4 text-sm font-semibold hover:bg-muted"
        >
          返回简历列表
        </RouterLink>
      </template>
    </PageHeader>

    <ol class="grid grid-cols-3 rounded-lg border bg-surface p-2 shadow-sm">
      <li
        v-for="(step, index) in ['上传文件', 'AI 解析', '确认结果']"
        :key="step"
        class="flex items-center justify-center gap-2 rounded-md px-3 py-2.5 text-sm"
        :class="index === 0 ? 'bg-primary-soft font-semibold text-primary' : 'text-muted-foreground'"
      >
        <span
          class="grid size-6 place-items-center rounded-full text-xs font-bold"
          :class="index === 0 ? 'bg-primary text-white' : 'bg-muted'"
        >
          {{ index + 1 }}
        </span>
        {{ step }}
      </li>
    </ol>

    <form
      class="space-y-6"
      @submit.prevent="submit"
    >
      <div class="grid gap-6 xl:grid-cols-3">
        <section class="rounded-lg border bg-surface p-6 shadow-sm xl:col-span-2">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 class="font-semibold">选择简历文件</h2>
              <p class="mt-1 text-sm text-muted-foreground">
                请上传包含真实经历的 PDF 或 DOCX 文件。
              </p>
            </div>
            <StatusBadge tone="info">最大 10MB</StatusBadge>
          </div>

          <FileDropzone
            class="mt-5"
            :selected-file="selectedFile"
            :disabled="isUploading"
            @select="chooseFile"
          />

          <div class="mt-5 grid gap-3 text-xs text-muted-foreground sm:grid-cols-2">
            <div class="flex items-start gap-2">
              <FileText class="mt-0.5 size-4 shrink-0 text-primary" />
              <p>
                <strong class="block text-foreground">支持格式</strong>
                PDF、DOCX
              </p>
            </div>
            <div class="flex items-start gap-2">
              <ShieldCheck class="mt-0.5 size-4 shrink-0 text-success" />
              <p>
                <strong class="block text-foreground">安全校验</strong>
                MIME、文件签名与内部结构
              </p>
            </div>
            <div class="flex items-start gap-2">
              <LockKeyhole class="mt-0.5 size-4 shrink-0 text-primary" />
              <p>
                <strong class="block text-foreground">私有存储</strong>
                文件仅对当前账号可见
              </p>
            </div>
            <div class="flex items-start gap-2">
              <ScanSearch class="mt-0.5 size-4 shrink-0 text-info" />
              <p>
                <strong class="block text-foreground">来源定位</strong>
                保留页码、段落与证据文本
              </p>
            </div>
          </div>

          <div
            v-if="isUploading || progress > 0"
            class="mt-5 space-y-2 rounded-md bg-muted/70 p-4"
            role="status"
          >
            <div class="flex items-center justify-between text-xs">
              <span class="font-medium">正在安全上传</span>
              <strong class="text-primary">{{ progress }}%</strong>
            </div>
            <div class="h-2 overflow-hidden rounded-full bg-surface">
              <div
                class="h-full rounded-full bg-primary transition-[width]"
                :style="{ width: `${progress}%` }"
              />
            </div>
            <p class="text-xs text-muted-foreground">上传进度：{{ progress }}%</p>
          </div>

          <FormMessage
            class="mt-4"
            :message="errorMessage"
          />
        </section>

        <aside class="space-y-4">
          <section class="rounded-lg border border-info/20 bg-info-soft p-5">
            <div class="flex items-start gap-3">
              <span class="grid size-9 shrink-0 place-items-center rounded-md bg-surface text-info">
                <Info class="size-5" />
              </span>
              <div>
                <h2 class="text-sm font-semibold">你的数据将如何处理</h2>
                <p class="mt-2 text-xs leading-5 text-muted-foreground">
                  系统先安全保存文件，再提取文本与来源，结构化结果不会在人工确认前成为正式事实。
                </p>
              </div>
            </div>
          </section>

          <section class="rounded-lg border bg-surface p-5 shadow-sm">
            <h2 class="text-sm font-semibold">获得更好的解析结果</h2>
            <ul class="mt-4 space-y-3 text-xs leading-5 text-muted-foreground">
              <li class="flex gap-2">
                <CheckCircle2 class="mt-0.5 size-4 shrink-0 text-success" />
                使用清晰、可选择文字的文档
              </li>
              <li class="flex gap-2">
                <CheckCircle2 class="mt-0.5 size-4 shrink-0 text-success" />
                保留明确的时间、公司与项目名称
              </li>
              <li class="flex gap-2">
                <CheckCircle2 class="mt-0.5 size-4 shrink-0 text-success" />
                避免扫描件、复杂多栏和图片文字
              </li>
            </ul>
          </section>

          <section class="rounded-lg border bg-surface p-5 shadow-sm">
            <div class="flex items-center justify-between">
              <h2 class="text-sm font-semibold">文件状态</h2>
              <span class="text-xs text-muted-foreground">Upload</span>
            </div>
            <div
              v-if="selectedFile && !errorMessage"
              class="mt-4 flex items-center gap-3 rounded-md bg-success-soft p-3"
            >
              <FileCheck2 class="size-5 shrink-0 text-success" />
              <div class="min-w-0">
                <p class="truncate text-xs font-semibold">Ready</p>
                <p class="truncate text-xs text-muted-foreground">{{ selectedFile.name }}</p>
              </div>
            </div>
            <p
              v-else
              class="mt-4 text-xs leading-5 text-muted-foreground"
            >
              选择文件后会在这里显示本地校验状态。
            </p>
          </section>
        </aside>
      </div>

      <div class="flex justify-end gap-3 border-t pt-5">
        <RouterLink
          :to="{ name: 'resumes' }"
          class="inline-flex h-10 items-center rounded-sm border bg-surface px-4 text-sm font-semibold hover:bg-muted"
        >
          取消
        </RouterLink>
        <Button
          type="submit"
          :disabled="isUploading"
        >
          {{ isUploading ? "上传中…" : "上传并继续" }}
          <ArrowRight class="ml-2 size-4" />
        </Button>
      </div>
    </form>
  </section>
</template>
