<script setup lang="ts">
import { X } from "@lucide/vue"

defineProps<{
  open: boolean
  title: string
}>()

defineEmits<{
  close: []
}>()
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 bg-foreground/30"
      @mousedown.self="$emit('close')"
    >
      <aside
        class="ml-auto flex h-full w-full max-w-2xl flex-col border-l bg-surface shadow-lg"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
      >
        <header class="flex items-center justify-between border-b px-6 py-5">
          <h2 class="text-lg font-semibold">{{ title }}</h2>
          <button
            type="button"
            class="grid size-8 place-items-center rounded-sm text-muted-foreground hover:bg-muted"
            aria-label="关闭"
            @click="$emit('close')"
          >
            <X class="size-4" />
          </button>
        </header>
        <div class="min-h-0 flex-1 overflow-y-auto p-6">
          <slot />
        </div>
      </aside>
    </div>
  </Teleport>
</template>
