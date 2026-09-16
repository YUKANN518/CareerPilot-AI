<script setup lang="ts">
import { computed, ref } from "vue"

import { Input } from "@/components/ui/input"
import { StatusBadge } from "@/components/ui/status-badge"
import type { EvidenceField } from "@/types/resume"

const props = withDefaults(
  defineProps<{
    label: string
    modelValue: EvidenceField
    multiline?: boolean
    readonly?: boolean
  }>(),
  {
    multiline: false,
    readonly: false,
  },
)

const emit = defineEmits<{
  "update:modelValue": [field: EvidenceField]
  "focus-evidence": [field: EvidenceField]
  modified: []
}>()

const isModified = ref(false)
const lowConfidence = computed(
  () => props.modelValue.confidence < 0.7 || props.modelValue.needs_confirmation,
)

function updateValue(value: string): void {
  isModified.value = true
  emit("update:modelValue", {
    ...props.modelValue,
    value,
    needs_confirmation: false,
  })
  emit("modified")
}

function locateEvidence(): void {
  emit("focus-evidence", props.modelValue)
}
</script>

<template>
  <div
    class="space-y-2 rounded-md border bg-surface p-3"
    :class="{ 'border-warning/35 bg-warning-soft/50': lowConfidence }"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <label
        :for="`field-${label}`"
        class="text-sm font-medium"
      >
        {{ label }}
      </label>
      <span class="flex flex-wrap items-center gap-1.5">
        <StatusBadge
          v-if="isModified"
          tone="info"
        >
          用户已修改
        </StatusBadge>
        <StatusBadge
          v-if="lowConfidence"
          tone="warning"
        >
          低置信度 {{ Math.round(modelValue.confidence * 100) }}%
        </StatusBadge>
      </span>
    </div>

    <textarea
      v-if="multiline"
      :id="`field-${label}`"
      :value="modelValue.value"
      :readonly="readonly"
      class="min-h-24 w-full resize-y rounded-sm border bg-surface px-3 py-2 text-sm leading-6"
      @focus="locateEvidence"
      @input="updateValue(($event.target as HTMLTextAreaElement).value)"
    />
    <Input
      v-else
      :id="`field-${label}`"
      :model-value="modelValue.value"
      :disabled="readonly"
      @focus="locateEvidence"
      @update:model-value="updateValue"
    />

    <details v-if="modelValue.evidence_text">
      <summary
        class="cursor-pointer text-xs font-medium text-primary"
        @click="locateEvidence"
      >
        查看原文证据
      </summary>
      <blockquote class="mt-2 rounded-sm bg-muted p-3 text-xs leading-5">
        {{ modelValue.evidence_text }}
      </blockquote>
      <p class="mt-1 text-xs text-muted-foreground">
        来源：{{ modelValue.source_location.label }}
      </p>
    </details>
    <p
      v-else
      class="text-xs text-warning"
    >
      当前字段没有可引用的原文证据，请人工核对。
    </p>
  </div>
</template>
