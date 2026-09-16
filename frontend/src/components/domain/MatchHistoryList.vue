<script setup lang="ts">
import { Clock3, Eye, RefreshCw } from "@lucide/vue"

import EmptyState from "@/components/domain/EmptyState.vue"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import type { MatchReport, RecommendationLevel } from "@/types/matching"
import { recommendationLabel } from "@/utils/matching"

withDefaults(
  defineProps<{
    reports: MatchReport[]
    jobLabels?: Record<number, string>
    resumeLabels?: Record<number, string>
    recalculatingId?: number | null
    compact?: boolean
  }>(),
  {
    jobLabels: () => ({}),
    resumeLabels: () => ({}),
    recalculatingId: null,
    compact: false,
  },
)

defineEmits<{ recalculate: [report: MatchReport] }>()

function tone(value: RecommendationLevel | null) {
  if (value === "STRONGLY_RECOMMENDED" || value === "RECOMMENDED") return "success"
  if (value === "CONSIDER") return "info"
  if (value === "HIGH_RISK") return "warning"
  return "danger"
}

function date(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value))
}
</script>

<template>
  <EmptyState
    v-if="reports.length === 0"
    compact
    title="暂无匹配历史"
    description="完成一次确定性匹配后，报告会保留在这里。"
  />
  <div
    v-else
    class="overflow-x-auto rounded-lg border"
  >
    <table class="w-full min-w-[64rem] text-left text-sm">
      <thead class="bg-muted text-xs text-muted-foreground">
        <tr>
          <th class="px-4 py-3 font-medium">匹配时间</th>
          <th class="px-4 py-3 font-medium">岗位</th>
          <th class="px-4 py-3 font-medium">简历版本</th>
          <th class="px-4 py-3 font-medium">规则 / 语义 / 混合 / 最终</th>
          <th class="px-4 py-3 font-medium">结论</th>
          <th class="px-4 py-3 font-medium">评分版本</th>
          <th class="px-4 py-3 font-medium">报告可信度</th>
          <th class="px-4 py-3 text-right font-medium">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="report in reports"
          :key="report.id"
          class="border-t"
        >
          <td class="px-4 py-3 text-xs text-muted-foreground">
            <span class="flex items-center gap-1.5">
              <Clock3 class="size-3.5" />
              {{ date(report.created_at) }}
            </span>
          </td>
          <td class="px-4 py-3 font-medium">
            {{ jobLabels[report.job_id] || `岗位 #${report.job_id}` }}
          </td>
          <td class="px-4 py-3">
            {{ resumeLabels[report.resume_version_id] || `正式版本 #${report.resume_version_id}` }}
          </td>
          <td class="px-4 py-3 font-semibold">
            {{ report.rule_score ?? "—" }} /
            {{ report.semantic_score ?? "—" }} /
            {{ report.hybrid_score ?? "—" }} /
            {{ report.final_score ?? "—" }}
          </td>
          <td class="px-4 py-3">
            <StatusBadge :tone="tone(report.recommendation)">
              {{ recommendationLabel(report.recommendation) }}
            </StatusBadge>
          </td>
          <td class="px-4 py-3 text-xs text-muted-foreground">
            <span class="flex items-center gap-2">
              {{ report.scoring_version }}
              <StatusBadge
                v-if="report.scoring_version === 'hybrid-v1'"
                tone="warning"
              >
                实验
              </StatusBadge>
            </span>
          </td>
          <td class="px-4 py-3 text-xs text-muted-foreground">
            {{ report.report_confidence || "旧报告未记录" }}
          </td>
          <td class="px-4 py-3">
            <div class="flex justify-end gap-2">
              <RouterLink :to="{ name: 'match-report', params: { matchId: report.id } }">
                <Button
                  size="sm"
                  variant="outline"
                >
                  <Eye class="mr-1.5 size-3.5" />
                  查看报告
                </Button>
              </RouterLink>
              <Button
                v-if="!compact"
                size="sm"
                variant="ghost"
                :disabled="recalculatingId === report.id"
                @click="$emit('recalculate', report)"
              >
                <RefreshCw class="mr-1.5 size-3.5" />
                重算
              </Button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
