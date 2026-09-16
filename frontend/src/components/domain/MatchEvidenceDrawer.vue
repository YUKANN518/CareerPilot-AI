<script setup lang="ts">
import { FileSearch, MapPin, Scale } from "@lucide/vue"

import { Drawer } from "@/components/ui/drawer"
import { StatusBadge } from "@/components/ui/status-badge"
import type { EvidenceTrace, SemanticEvidence } from "@/types/matching"

withDefaults(
  defineProps<{
    open: boolean
    title: string
    evidence: EvidenceTrace[]
    semanticEvidence?: SemanticEvidence[]
    requirement?: string | null
  }>(),
  {
    semanticEvidence: () => [],
    requirement: null,
  },
)

defineEmits<{ close: [] }>()

function sourceLabel(item: EvidenceTrace): string {
  const parts = [
    item.source_type,
    item.page_number ? `第 ${item.page_number} 页` : null,
    item.paragraph_index !== null ? `第 ${item.paragraph_index + 1} 段` : null,
    item.source_location,
  ]
  return parts.filter(Boolean).join(" · ") || "来源位置未提供"
}

function sectionLabel(section: string | null): string {
  const labels: Record<string, string> = {
    education: "Education",
    project_experience: "Project Experience",
    work_experience: "Work Experience",
    skill_section: "Skill Section",
    technical_skills: "Skill Section",
    soft_skills: "Skill Section",
    other_resume_text: "Other Resume Text",
  }
  return section ? (labels[section] ?? section) : "Source not classified"
}
</script>

<template>
  <Drawer
    :open="open"
    :title="title"
    @close="$emit('close')"
  >
    <div
      v-if="requirement"
      class="mb-5 rounded-md border border-primary/15 bg-primary-soft p-4 text-sm"
    >
      <strong>岗位要求</strong>
      <p class="mt-1 leading-6 text-muted-foreground">{{ requirement }}</p>
    </div>

    <ol
      v-if="semanticEvidence.length > 0"
      class="space-y-4"
      data-testid="semantic-evidence-drawer"
    >
      <li
        v-for="item in semanticEvidence"
        :key="`${item.rank}-${item.relation}`"
        class="rounded-lg border p-5"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <StatusBadge tone="warning">语义证据 #{{ item.rank }}</StatusBadge>
          <span class="text-xs font-semibold text-muted-foreground">
            相似度 {{ Math.round(item.similarity * 100) }}%
          </span>
        </div>
        <p class="mt-3 text-xs text-muted-foreground">
          {{ item.resume_section }} → {{ item.job_field }}
        </p>
        <section class="mt-4">
          <h3 class="flex items-center gap-2 text-sm font-semibold">
            <FileSearch class="size-4 text-primary" />
            简历原文
          </h3>
          <blockquote class="mt-2 rounded-sm bg-muted p-3 text-sm leading-6">
            {{ item.resume_text }}
          </blockquote>
          <p class="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <MapPin class="size-3.5" />
            {{
              [
                item.page_number ? `第 ${item.page_number} 页` : null,
                item.paragraph_index !== null ? `第 ${item.paragraph_index + 1} 段` : null,
              ]
                .filter(Boolean)
                .join(" · ") || "来源位置未提供"
            }}
          </p>
        </section>
        <section class="mt-5 border-t pt-5">
          <h3 class="text-sm font-semibold">岗位原文</h3>
          <p class="mt-2 text-xs text-muted-foreground">字段：{{ item.job_field }}</p>
          <blockquote class="mt-2 rounded-sm bg-muted p-3 text-sm leading-6">
            {{ item.job_text }}
          </blockquote>
        </section>
        <p class="mt-5 border-t pt-4 text-xs leading-5 text-muted-foreground">
          该结果仅表示文本相关性，不证明候选人一定具备某项技能，也不能替代资格条件判断。
        </p>
      </li>
    </ol>

    <section
      v-else-if="evidence.length === 0"
      class="rounded-lg border border-dashed p-8 text-center"
      data-testid="no-evidence"
    >
      <FileSearch class="mx-auto size-8 text-muted-foreground" />
      <h3 class="mt-3 font-semibold">未找到可追溯证据</h3>
      <p class="mt-2 text-sm text-muted-foreground">
        后端没有为此结论保存证据，页面不会生成额外解释。
      </p>
    </section>

    <ol
      v-else
      class="space-y-4"
    >
      <li
        v-for="(item, index) in evidence"
        :key="`${item.conclusion_key}-${index}`"
        class="rounded-lg border p-5"
      >
        <div class="flex flex-wrap items-center justify-between gap-2">
          <StatusBadge tone="primary">证据 {{ index + 1 }}</StatusBadge>
          <span class="text-xs font-semibold text-muted-foreground">
            置信度 {{ Math.round(item.confidence * 100) }}%
          </span>
        </div>

        <section class="mt-5">
          <h3 class="flex items-center gap-2 text-sm font-semibold">
            <FileSearch class="size-4 text-primary" />
            简历证据
          </h3>
          <dl class="mt-3 space-y-2 text-xs">
            <div class="flex justify-between gap-4">
              <dt class="text-muted-foreground">简历版本 / 技能</dt>
              <dd class="text-right font-medium">
                #{{ item.resume_version_id }} /
                {{ item.resume_skill_id ? `#${item.resume_skill_id}` : "经历记录" }}
              </dd>
            </div>
            <div class="flex justify-between gap-4">
              <dt class="text-muted-foreground">章节</dt>
              <dd class="text-right font-medium">{{ sectionLabel(item.resume_section) }}</dd>
            </div>
          </dl>
          <blockquote class="mt-3 rounded-sm bg-muted p-3 text-sm leading-6">
            {{ item.resume_evidence || "未找到可追溯证据" }}
          </blockquote>
          <p class="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <MapPin class="size-3.5" />
            {{ sourceLabel(item) }}
          </p>
        </section>

        <section class="mt-5 border-t pt-5">
          <h3 class="text-sm font-semibold">岗位证据</h3>
          <p class="mt-2 text-xs text-muted-foreground">字段：{{ item.job_field }}</p>
          <blockquote class="mt-2 rounded-sm bg-muted p-3 text-sm leading-6">
            {{ item.job_snippet || "岗位原文未提供" }}
          </blockquote>
        </section>

        <section class="mt-5 border-t pt-5">
          <h3 class="flex items-center gap-2 text-sm font-semibold">
            <Scale class="size-4 text-primary" />
            确定性规则
          </h3>
          <dl class="mt-3 grid gap-3 text-xs sm:grid-cols-2">
            <div>
              <dt class="text-muted-foreground">matching_rule</dt>
              <dd class="mt-1 break-all font-medium">{{ item.matching_rule }}</dd>
            </div>
            <div>
              <dt class="text-muted-foreground">conclusion_key</dt>
              <dd class="mt-1 break-all font-medium">{{ item.conclusion_key }}</dd>
            </div>
          </dl>
        </section>
      </li>
    </ol>
  </Drawer>
</template>
