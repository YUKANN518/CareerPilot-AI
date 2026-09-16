<script setup lang="ts">
import { CheckCircle2, CircleAlert, X } from "@lucide/vue"
import { onBeforeUnmount, watch } from "vue"

const props = withDefaults(
  defineProps<{
    message: string | null
    tone?: "success" | "danger"
  }>(),
  {
    tone: "success",
  },
)

const emit = defineEmits<{
  dismiss: []
}>()

let timer: ReturnType<typeof setTimeout> | null = null

watch(
  () => props.message,
  (message) => {
    if (timer) clearTimeout(timer)
    if (message) timer = setTimeout(() => emit("dismiss"), 5000)
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (timer) clearTimeout(timer)
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="message"
      class="fixed right-5 top-5 z-[70] flex max-w-md items-start gap-3 rounded-lg border bg-surface p-4 shadow-lg"
      :class="tone === 'success' ? 'border-success/25' : 'border-danger/25'"
      :role="tone === 'danger' ? 'alert' : 'status'"
    >
      <CheckCircle2
        v-if="tone === 'success'"
        class="mt-0.5 size-5 shrink-0 text-success"
      />
      <CircleAlert
        v-else
        class="mt-0.5 size-5 shrink-0 text-danger"
      />
      <p class="text-sm leading-6">{{ message }}</p>
      <button
        type="button"
        class="grid size-7 shrink-0 place-items-center rounded-sm text-muted-foreground hover:bg-muted"
        aria-label="关闭提示"
        @click="emit('dismiss')"
      >
        <X class="size-4" />
      </button>
    </div>
  </Teleport>
</template>
