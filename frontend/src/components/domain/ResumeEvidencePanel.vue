<script setup lang="ts">
import {
  ChevronLeft,
  ChevronRight,
  FileSearch,
  FileText,
  LocateFixed,
  Search,
} from "@lucide/vue"
import { computed, ref, watch } from "vue"

import { Input } from "@/components/ui/input"
import { StatusBadge } from "@/components/ui/status-badge"
import type {
  EvidenceField,
  ResumeProfile,
  SourceLocation,
} from "@/types/resume"

interface EvidenceRecord {
  id: string
  field: EvidenceField
  sourceKey: string
}

const props = defineProps<{
  profile: ResumeProfile
  fileFormat: "pdf" | "docx"
  fileName: string
  activeEvidence: EvidenceField | null
}>()

const query = ref("")
const selectedSourceKey = ref<string | null>(null)

function sourceKey(location: SourceLocation): string {
  if (props.fileFormat === "pdf" && location.page_number) {
    return `page-${location.page_number}`
  }
  if (location.paragraph_index !== null) {
    return `paragraph-${location.paragraph_index}`
  }
  if (location.block_index !== null) {
    return `block-${location.block_index}`
  }
  return location.label
}

function sourceLabel(location: SourceLocation): string {
  if (props.fileFormat === "pdf" && location.page_number) {
    return `第 ${location.page_number} 页`
  }
  if (location.paragraph_index !== null) {
    return `第 ${location.paragraph_index + 1} 段`
  }
  if (location.table_index !== null) {
    return `表格 ${location.table_index + 1}`
  }
  if (location.block_index !== null) {
    return `来源块 ${location.block_index + 1}`
  }
  return location.label
}

function allFields(profile: ResumeProfile): EvidenceField[] {
  const fields: EvidenceField[] = [
    ...Object.values(profile.basic_info),
    profile.summary,
  ]
  for (const item of profile.education) fields.push(...Object.values(item))
  for (const item of profile.work_experience) fields.push(...Object.values(item))
  for (const item of profile.project_experience) fields.push(...Object.values(item))
  fields.push(
    ...profile.technical_skills,
    ...profile.soft_skills,
    ...profile.languages,
    ...profile.certificates,
    ...profile.awards,
  )
  return fields
}

const evidenceRecords = computed<EvidenceRecord[]>(() => {
  const seen = new Set<string>()
  return allFields(props.profile)
    .filter((field) => field.evidence_text.trim())
    .map((field, index) => ({
      id: `${field.source_location.label}-${index}`,
      field,
      sourceKey: sourceKey(field.source_location),
    }))
    .filter((record) => {
      const dedupe = `${record.sourceKey}:${record.field.evidence_text}`
      if (seen.has(dedupe)) return false
      seen.add(dedupe)
      return true
    })
})

const sources = computed(() => {
  const unique = new Map<string, SourceLocation>()
  for (const record of evidenceRecords.value) {
    unique.set(record.sourceKey, record.field.source_location)
  }
  return [...unique.entries()].map(([key, location]) => ({
    key,
    label: sourceLabel(location),
  }))
})

const selectedIndex = computed(() =>
  sources.value.findIndex((source) => source.key === selectedSourceKey.value),
)
const visibleRecords = computed(() => {
  const normalizedQuery = query.value.trim().toLocaleLowerCase()
  return evidenceRecords.value.filter((record) => {
    const matchesSource =
      selectedSourceKey.value === null || record.sourceKey === selectedSourceKey.value
    const matchesQuery =
      !normalizedQuery ||
      record.field.evidence_text.toLocaleLowerCase().includes(normalizedQuery) ||
      record.field.value.toLocaleLowerCase().includes(normalizedQuery)
    return matchesSource && matchesQuery
  })
})

function selectAdjacent(offset: number): void {
  if (sources.value.length === 0) return
  const current = selectedIndex.value < 0 ? 0 : selectedIndex.value
  const next = Math.min(sources.value.length - 1, Math.max(0, current + offset))
  selectedSourceKey.value = sources.value[next]?.key ?? null
}

function isActive(record: EvidenceRecord): boolean {
  if (!props.activeEvidence) return false
  return (
    record.field.source_location.label === props.activeEvidence.source_location.label &&
    record.field.evidence_text === props.activeEvidence.evidence_text
  )
}

watch(
  () => props.activeEvidence,
  (field) => {
    if (!field) return
    selectedSourceKey.value = sourceKey(field.source_location)
  },
)

watch(
  sources,
  (nextSources) => {
    if (
      nextSources.length > 0 &&
      !nextSources.some((source) => source.key === selectedSourceKey.value)
    ) {
      selectedSourceKey.value = nextSources[0]?.key ?? null
    }
  },
  { immediate: true },
)
</script>

<template>
  <aside class="self-start overflow-hidden rounded-lg border bg-surface shadow-sm xl:sticky xl:top-24">
    <header class="border-b p-5">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0">
          <h2 class="flex items-center gap-2 text-sm font-semibold">
            <FileText class="size-4 text-primary" />
            原文与证据
          </h2>
          <p class="mt-1 truncate text-xs text-muted-foreground">{{ fileName }}</p>
        </div>
        <StatusBadge tone="info">
          {{ fileFormat === "pdf" ? "PDF 页码" : "DOCX 段落" }}
        </StatusBadge>
      </div>

      <label class="relative mt-4 block">
        <span class="sr-only">搜索原文</span>
        <Search class="pointer-events-none absolute left-3 top-2.5 size-4 text-muted-foreground" />
        <Input
          v-model="query"
          class="pl-9"
          placeholder="搜索原文或字段值"
        />
      </label>

      <div class="mt-3 flex items-center gap-2">
        <button
          type="button"
          class="grid size-9 place-items-center rounded-sm border hover:bg-muted disabled:opacity-40"
          :disabled="selectedIndex <= 0"
          aria-label="上一页或上一段"
          @click="selectAdjacent(-1)"
        >
          <ChevronLeft class="size-4" />
        </button>
        <select
          v-model="selectedSourceKey"
          class="h-9 min-w-0 flex-1 rounded-sm border bg-surface px-3 text-sm"
          aria-label="原文位置"
        >
          <option
            v-for="source in sources"
            :key="source.key"
            :value="source.key"
          >
            {{ source.label }}
          </option>
        </select>
        <button
          type="button"
          class="grid size-9 place-items-center rounded-sm border hover:bg-muted disabled:opacity-40"
          :disabled="selectedIndex < 0 || selectedIndex >= sources.length - 1"
          aria-label="下一页或下一段"
          @click="selectAdjacent(1)"
        >
          <ChevronRight class="size-4" />
        </button>
      </div>
    </header>

    <div class="max-h-[calc(100vh-19rem)] overflow-y-auto bg-muted/40 p-5">
      <div
        v-if="activeEvidence"
        data-testid="active-evidence-source"
        class="mb-4 flex items-start gap-3 rounded-md border border-primary/20 bg-primary-soft p-3"
      >
        <LocateFixed class="mt-0.5 size-4 shrink-0 text-primary" />
        <p class="text-xs leading-5 text-primary">
          已定位到 {{ sourceLabel(activeEvidence.source_location) }}：
          {{ activeEvidence.source_location.label }}
        </p>
      </div>

      <div
        v-if="visibleRecords.length === 0"
        class="grid min-h-56 place-items-center rounded-md border border-dashed bg-surface p-6 text-center"
      >
        <div>
          <FileSearch class="mx-auto size-8 text-muted-foreground" />
          <p class="mt-3 text-sm font-semibold">没有匹配的原文证据</p>
          <p class="mt-1 text-xs leading-5 text-muted-foreground">
            尝试切换页码、段落或调整搜索词。
          </p>
        </div>
      </div>
      <div
        v-else
        class="space-y-3"
      >
        <article
          v-for="record in visibleRecords"
          :key="record.id"
          :data-testid="isActive(record) ? 'active-evidence-card' : undefined"
          class="rounded-md border bg-surface p-4 transition-colors"
          :class="
            isActive(record)
              ? 'border-primary ring-2 ring-primary/15'
              : 'hover:border-primary/30'
          "
        >
          <div class="flex items-center justify-between gap-2">
            <StatusBadge tone="neutral">
              {{ sourceLabel(record.field.source_location) }}
            </StatusBadge>
            <span class="text-xs font-medium text-muted-foreground">
              {{ Math.round(record.field.confidence * 100) }}%
            </span>
          </div>
          <p
            class="mt-3 whitespace-pre-line text-sm leading-7"
            :class="{ 'bg-warning-soft': query.trim() }"
          >
            {{ record.field.evidence_text }}
          </p>
          <p class="mt-3 border-t pt-3 text-xs text-muted-foreground">
            对应字段：{{ record.field.value || "待人工补充" }}
          </p>
        </article>
      </div>
    </div>
  </aside>
</template>
