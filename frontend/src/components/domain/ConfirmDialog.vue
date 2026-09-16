<script setup lang="ts">
import { AlertTriangle, X } from "@lucide/vue"
import { ref } from "vue"

import { Button } from "@/components/ui/button"

withDefaults(
  defineProps<{
    title: string
    description: string
    confirmLabel?: string
    cancelLabel?: string
    danger?: boolean
  }>(),
  {
    confirmLabel: "确认",
    cancelLabel: "取消",
    danger: false,
  },
)

const emit = defineEmits<{
  confirm: []
  cancel: []
}>()

const dialog = ref<HTMLDialogElement | null>(null)

function open(): void {
  dialog.value?.showModal()
}

function close(): void {
  dialog.value?.close()
}

function cancel(): void {
  close()
  emit("cancel")
}

function confirm(): void {
  close()
  emit("confirm")
}

defineExpose({ open, close })
</script>

<template>
  <dialog
    ref="dialog"
    aria-labelledby="confirm-dialog-title"
    class="w-[min(30rem,calc(100%-2rem))] rounded-lg border bg-surface p-0 text-foreground shadow-lg backdrop:bg-foreground/30"
    @cancel.prevent="cancel"
  >
    <div class="p-6">
      <div class="flex items-start gap-4">
        <span
          class="grid size-10 shrink-0 place-items-center rounded-md"
          :class="danger ? 'bg-danger-soft text-danger' : 'bg-warning-soft text-warning'"
        >
          <AlertTriangle class="size-5" />
        </span>
        <div class="min-w-0 flex-1">
          <h2
            id="confirm-dialog-title"
            class="text-lg font-semibold"
          >
            {{ title }}
          </h2>
          <p class="mt-2 text-sm leading-6 text-muted-foreground">
            {{ description }}
          </p>
        </div>
        <button
          type="button"
          class="grid size-8 place-items-center rounded-sm text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label="关闭"
          @click="cancel"
        >
          <X class="size-4" />
        </button>
      </div>
    </div>
    <div class="flex justify-end gap-2 border-t bg-muted/50 px-6 py-4">
      <Button
        variant="outline"
        @click="cancel"
      >
        {{ cancelLabel }}
      </Button>
      <Button
        :variant="danger ? 'danger' : 'default'"
        @click="confirm"
      >
        {{ confirmLabel }}
      </Button>
    </div>
  </dialog>
</template>
