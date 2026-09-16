<script setup lang="ts">
import { X } from "@lucide/vue"

withDefaults(
  defineProps<{
    open: boolean
    title: string
    description?: string
    size?: "md" | "lg" | "xl"
  }>(),
  {
    description: undefined,
    size: "lg",
  },
)

defineEmits<{
  close: []
}>()
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-50 grid place-items-center bg-foreground/30 p-4"
      role="presentation"
      @mousedown.self="$emit('close')"
    >
      <section
        role="dialog"
        aria-modal="true"
        :aria-label="title"
        class="max-h-[90vh] w-full overflow-hidden rounded-lg border bg-surface shadow-lg"
        :class="{
          'max-w-xl': size === 'md',
          'max-w-3xl': size === 'lg',
          'max-w-5xl': size === 'xl',
        }"
      >
        <header class="flex items-start justify-between gap-4 border-b px-6 py-5">
          <div>
            <h2 class="text-lg font-semibold">{{ title }}</h2>
            <p
              v-if="description"
              class="mt-1 text-sm text-muted-foreground"
            >
              {{ description }}
            </p>
          </div>
          <button
            type="button"
            class="grid size-8 place-items-center rounded-sm text-muted-foreground hover:bg-muted"
            aria-label="关闭"
            @click="$emit('close')"
          >
            <X class="size-4" />
          </button>
        </header>
        <div class="max-h-[calc(90vh-9rem)] overflow-y-auto p-6">
          <slot />
        </div>
        <footer
          v-if="$slots.footer"
          class="flex justify-end gap-2 border-t bg-muted/40 px-6 py-4"
        >
          <slot name="footer" />
        </footer>
      </section>
    </div>
  </Teleport>
</template>
