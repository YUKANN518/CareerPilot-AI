<script setup lang="ts">
import { computed, useAttrs } from "vue"

import { cn } from "@/utils/cn"

defineOptions({ inheritAttrs: false })

withDefaults(
  defineProps<{
    modelValue?: string
    type?: string
    disabled?: boolean
  }>(),
  {
    modelValue: "",
    type: "text",
    disabled: false,
  },
)

const emit = defineEmits<{
  "update:modelValue": [value: string]
}>()

const attrs = useAttrs()
const classes = computed(() =>
  cn(
    "flex h-10 w-full rounded-sm border bg-surface px-3 py-2 text-sm",
    "placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50",
    attrs.class as string,
  ),
)

function updateValue(event: Event): void {
  emit("update:modelValue", (event.target as HTMLInputElement).value)
}
</script>

<template>
  <input
    v-bind="attrs"
    :class="classes"
    :type="type"
    :value="modelValue"
    :disabled="disabled"
    @input="updateValue"
  >
</template>
