<script setup lang="ts">
import { FileText, UploadCloud } from "@lucide/vue"
import { ref } from "vue"

withDefaults(
  defineProps<{
    selectedFile?: File | null
    disabled?: boolean
    accept?: string
  }>(),
  {
    selectedFile: null,
    disabled: false,
    accept:
      ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  },
)

const emit = defineEmits<{
  select: [file: File | null]
}>()

const isDragging = ref(false)

function selectFromInput(event: Event): void {
  emit("select", (event.target as HTMLInputElement).files?.[0] ?? null)
}

function handleDrop(event: DragEvent): void {
  isDragging.value = false
  emit("select", event.dataTransfer?.files[0] ?? null)
}
</script>

<template>
  <label
    for="resume-file"
    class="group flex min-h-72 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed p-8 text-center transition-colors duration-fast"
    :class="[
      isDragging ? 'border-primary bg-primary-soft' : 'border-primary/30 bg-primary-soft/60 hover:border-primary',
      disabled ? 'pointer-events-none opacity-60' : '',
    ]"
    @dragenter.prevent="isDragging = true"
    @dragover.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @drop.prevent="handleDrop"
  >
    <input
      id="resume-file"
      data-testid="resume-file"
      type="file"
      :accept="accept"
      :disabled="disabled"
      class="sr-only"
      @change="selectFromInput"
    >
    <span class="grid size-14 place-items-center rounded-lg bg-surface text-primary shadow-sm">
      <FileText
        v-if="selectedFile"
        class="size-7"
        aria-hidden="true"
      />
      <UploadCloud
        v-else
        class="size-7"
        aria-hidden="true"
      />
    </span>
    <template v-if="selectedFile">
      <p class="mt-5 max-w-full truncate text-base font-semibold">{{ selectedFile.name }}</p>
      <p class="mt-2 text-sm text-muted-foreground">
        {{ (selectedFile.size / 1024).toFixed(1) }} KB · 点击可重新选择
      </p>
    </template>
    <template v-else>
      <p class="mt-5 text-base font-semibold">拖放简历到这里</p>
      <p class="mt-2 text-sm text-muted-foreground">或点击浏览本地文件</p>
      <span class="mt-5 rounded-sm bg-primary px-4 py-2 text-sm font-semibold text-white">
        选择文件
      </span>
    </template>
  </label>
</template>
