<script setup lang="ts">
import {
  AlertOctagon,
  ArrowLeft,
  CircleAlert,
  Info,
  RefreshCw,
  Scale,
  ShieldAlert,
  Target,
} from "@lucide/vue"
import { computed, onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"

import { getApiErrorInfo } from "@/api/errors"
import { getJob } from "@/api/jobs"
import { getResumeVersion, listResumeVersionSkills } from "@/api/resumes"
import ConfirmDialog from "@/components/domain/ConfirmDialog.vue"
import ErrorState from "@/components/domain/ErrorState.vue"
import ForbiddenState from "@/components/domain/ForbiddenState.vue"
import MatchDimensionChart from "@/components/domain/MatchDimensionChart.vue"
import MatchEvidenceDrawer from "@/components/domain/MatchEvidenceDrawer.vue"
import PageHeader from "@/components/domain/PageHeader.vue"
import PageSkeleton from "@/components/domain/PageSkeleton.vue"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import { matchRunService, matchService } from "@/services/matching"
import type { Job } from "@/types/job"
import type {
  DimensionScore,
  EvidenceTrace,
  MatchDetail,
  MatchReport,
  RecommendationLevel,
  RiskItem,
  SemanticEvidence,
  SkillMatch,
  SkillMatchStatus,
} from "@/types/matching"
import type { ResumeVersion } from "@/types/resume"
import type { ResumeSkill } from "@/types/resume"
import {
  evidenceFor,
  groupSkillMatches,
  isPositiveInteger,
  recommendationLabel,
  requirementCompleteness,
  riskCountForDimension,
  riskLabels,
  skillStatusLabels,
} from "@/utils/matching"

const route = useRoute()
const router = useRouter()
const report = ref<MatchReport | null>(null)
const details = ref<MatchDetail[]>([])
const job = ref<Job | null>(null)
const version = ref<ResumeVersion | null>(null)
const resumeSkills = ref<ResumeSkill[]>([])
const loading = ref(true)
const errorMessage = ref<string | null>(null)
const errorKind = ref<string | null>(null)
const recalculating = ref(false)
const recalculateDialog = ref<InstanceType<typeof ConfirmDialog> | null>(null)
const drawerOpen = ref(false)
const drawerTitle = ref("匹配证据")
const drawerRequirement = ref<string | null>(null)
const drawerEvidence = ref<EvidenceTrace[]>([])
const drawerSemanticEvidence = ref<SemanticEvidence[]>([])

const matchId = computed(() => Number(route.params.matchId))
const blockingConflicts = computed(
  () => report.value?.hard_requirement_risks.filter((risk) => risk.severity === "BLOCKING") ?? [],
)
const blockingRisks = computed(
  () =>
    report.value?.hard_requirement_risks.filter(
      (risk) => risk.risk_type === "BLOCKING_RISK" || risk.severity === "BLOCKING",
    ) ?? [],
)
const generalRisks = computed(
  () =>
    report.value?.hard_requirement_risks.filter(
      (risk) =>
        risk.risk_type !== "BLOCKING_RISK" &&
        risk.risk_type !== "SKILL_GAP" &&
        risk.severity !== "BLOCKING" &&
        !risk.code.startsWith("REQUIRED_SKILL_"),
    ) ?? [],
)
const completeness = computed(() =>
  report.value
    ? requirementCompleteness(report.value)
    : { provided: 0, notProvided: 0, unknown: 0, incomplete: false, statuses: [] },
)
const skillGroups = computed(() =>
  report.value
    ? groupSkillMatches(report.value)
    : { MATCHED: [], PARTIAL: [], MISSING: [], UNKNOWN: [] },
)
const snapshotJob = computed(() => report.value?.input_snapshot?.job ?? null)
const snapshotResume = computed(() => report.value?.input_snapshot?.resume ?? null)
const scoreBand = computed(() => {
  const score = report.value?.final_score
  if (score === null || score === undefined) return "Pending"
  if (score >= 85) return "High Match"
  if (score >= 55) return "Moderate Match"
  return "Low Match"
})

function recommendationTone(value: RecommendationLevel | null) {
  if (value === "STRONGLY_RECOMMENDED" || value === "RECOMMENDED") return "success"
  if (value === "CONSIDER") return "info"
  if (value === "HIGH_RISK") return "warning"
  return "danger"
}

function severityTone(value: string) {
  if (value === "BLOCKING" || value === "HIGH") return "danger"
  if (value === "MEDIUM") return "warning"
  if (value === "LOW") return "info"
  return "neutral"
}

function skillTone(status: SkillMatchStatus) {
  if (status === "MATCHED") return "success"
  if (status === "PARTIAL") return "warning"
  if (status === "MISSING") return "danger"
  return "info"
}

function verificationTone(status: string) {
  if (status === "CONFIRMED") return "success"
  if (status === "CONFLICT") return "danger"
  return "warning"
}

function dimensionTone(status: string) {
  if (status === "GOOD") return "success"
  if (status === "PARTIAL") return "warning"
  if (status === "WEAK") return "danger"
  return "neutral"
}

function evidenceSourceLabel(section: string | null): string {
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

function firstSkillEvidence(skill: SkillMatch): EvidenceTrace | null {
  if (!report.value) return null
  return evidenceFor(report.value, skill.normalized_name).find(
    (item) => Boolean(item.resume_evidence),
  ) ?? null
}

function dimensionEvidence(dimension: DimensionScore): EvidenceTrace[] {
  if (!report.value) return []
  const seen = new Set<string>()
  return dimension.evidence_keys.flatMap((key) => evidenceFor(report.value!, key)).filter((item) => {
    const identity = `${item.conclusion_key}:${item.resume_skill_id}:${item.source_location}`
    if (seen.has(identity)) return false
    seen.add(identity)
    return true
  })
}

function formatDate(value: string | null): string {
  return value
    ? new Intl.DateTimeFormat("zh-CN", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(new Date(value))
    : "未完成"
}

function formatPercentage(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "旧报告未记录"
    : `${Math.round(value * 100)}%`
}

function openEvidence(
  title: string,
  evidence: EvidenceTrace[],
  requirement?: string | null,
): void {
  drawerTitle.value = title
  drawerEvidence.value = evidence
  drawerSemanticEvidence.value = []
  drawerRequirement.value = requirement ?? null
  drawerOpen.value = true
}

function openSemanticEvidence(item: SemanticEvidence): void {
  drawerTitle.value = `语义证据 #${item.rank}`
  drawerEvidence.value = []
  drawerSemanticEvidence.value = [item]
  drawerRequirement.value = item.job_text
  drawerOpen.value = true
}

function openSkillEvidence(skill: SkillMatch): void {
  if (!report.value) return
  openEvidence(
    `${skill.normalized_name} · 技能证据`,
    evidenceFor(report.value, skill.normalized_name),
    skill.job_raw_name,
  )
}

function openRiskEvidence(risk: RiskItem): void {
  if (!report.value) return
  openEvidence(
    `${risk.title} · 风险证据`,
    evidenceFor(report.value, risk.code),
    risk.job_requirement,
  )
}

function dimensionDetail(dimension: DimensionScore): MatchDetail | undefined {
  return details.value.find(
    (item) => item.category === "DIMENSION" && item.code === dimension.code,
  )
}

function openDimensionEvidence(dimension: DimensionScore): void {
  if (!report.value) return
  const detail = dimensionDetail(dimension)
  openEvidence(
    `${dimension.label} · 结论证据`,
    dimensionEvidence(dimension).length > 0
      ? dimensionEvidence(dimension)
      : detail?.evidence ?? [],
    dimension.explanation,
  )
}

function resumeSkillFor(skill: SkillMatch): ResumeSkill | null {
  if (!skill.resume_skill_id) return null
  return resumeSkills.value.find((item) => item.id === skill.resume_skill_id) ?? null
}

function snapshotWeight(dimension: DimensionScore): number {
  const weights = report.value?.scoring_config_snapshot.weights
  if (!weights || !(dimension.code in weights)) return dimension.weight
  return weights[dimension.code as keyof typeof weights]
}

async function load(): Promise<void> {
  loading.value = true
  errorKind.value = null
  errorMessage.value = null
  if (!isPositiveInteger(matchId.value)) {
    loading.value = false
    errorKind.value = "not-found"
    errorMessage.value = "匹配报告参数无效。"
    return
  }
  try {
    const nextReport = await matchService.get(matchId.value)
    report.value = nextReport
    ;[job.value, version.value, details.value, resumeSkills.value] = await Promise.all([
      getJob(nextReport.job_id),
      getResumeVersion(nextReport.resume_version_id),
      matchService.details(nextReport.id),
      listResumeVersionSkills(nextReport.resume_version_id),
    ])
  } catch (error) {
    const info = getApiErrorInfo(error)
    errorKind.value = info.kind
    errorMessage.value = info.message
  } finally {
    loading.value = false
  }
}

async function recalculate(): Promise<void> {
  if (!report.value || recalculating.value) return
  recalculating.value = true
  errorMessage.value = null
  try {
    const run = await matchRunService.create({
      resume_version_id: report.value.resume_version_id,
      job_id: report.value.job_id,
      scoring_version: report.value.scoring_version,
    })
    await router.push({
      name: "match-processing",
      params: { runId: run.run_id },
    })
  } catch (error) {
    const info = getApiErrorInfo(error)
    errorKind.value = info.kind
    errorMessage.value = info.message
  } finally {
    recalculating.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="space-y-6">
    <PageSkeleton
      v-if="loading"
      label="正在加载匹配报告"
      :rows="8"
    />
    <ForbiddenState
      v-else-if="errorKind === 'forbidden'"
      data-testid="forbidden-state"
      description="当前账号无权查看其他用户的匹配报告。"
    />
    <ErrorState
      v-else-if="errorKind === 'not-found' || (!report && errorMessage)"
      data-testid="not-found-state"
      :title="errorKind === 'not-found' ? '匹配报告不存在' : '无法加载匹配报告'"
      :message="errorMessage ?? '报告不存在或已删除。'"
      @retry="load"
    />
    <template v-else-if="report">
      <RouterLink
        :to="{ name: 'matches' }"
        class="inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft class="size-4" />
        返回匹配历史
      </RouterLink>
      <PageHeader
        eyebrow="Match report"
        :title="`${snapshotJob?.title ?? job?.title ?? `岗位 #${report.job_id}`} · 人岗匹配报告`"
        :description="`${snapshotJob?.company ?? job?.company ?? '岗位公司'} · 正式简历版本 v${snapshotResume?.version_number ?? version?.version_number ?? report.resume_version_id}`"
      >
        <template #actions>
          <Button
            :disabled="recalculating"
            @click="recalculateDialog?.open()"
          >
            <RefreshCw class="mr-2 size-4" />
            {{ recalculating ? "重新计算中…" : "重新计算" }}
          </Button>
        </template>
      </PageHeader>

      <ErrorState
        v-if="errorMessage"
        compact
        title="操作未完成"
        :message="errorMessage"
      />

      <section
        v-if="blockingConflicts.length"
        class="rounded-lg border border-danger/30 bg-danger-soft p-5"
        role="alert"
        data-testid="blocking-warning"
      >
        <div class="flex items-start gap-3">
          <AlertOctagon class="mt-0.5 size-6 shrink-0 text-danger" />
          <div>
            <h2 class="font-semibold text-danger">存在阻断性资格冲突</h2>
            <p class="mt-1 text-sm leading-6 text-danger/85">
              高分不能抵消资格冲突。后端推荐结论为
              <strong>{{ recommendationLabel(report.recommendation) }}</strong>，
              请先确认工作资格或其他硬性条件。
            </p>
          </div>
        </div>
      </section>

      <section
        v-if="completeness.incomplete"
        class="rounded-lg border border-warning/25 bg-warning-soft p-5"
        data-testid="incomplete-job-warning"
      >
        <div class="flex items-start gap-3">
          <Info class="mt-0.5 size-5 shrink-0 text-warning" />
          <div>
            <h2 class="font-semibold text-warning">岗位信息完整度有限</h2>
            <p class="mt-1 text-sm leading-6 text-warning/85">
              该岗位信息不完整，当前得分仅基于已有条件计算，推荐结论可信度有限。
            </p>
            <p class="mt-2 text-xs text-muted-foreground">
              已参与计算 {{ completeness.provided }} 项 · 未提供
              {{ completeness.notProvided }} 项 · UNKNOWN
              {{ completeness.unknown }} 项 · NOT_PROVIDED
              {{ completeness.notProvided }} 项
            </p>
          </div>
        </div>
      </section>

      <section class="grid gap-4 lg:grid-cols-[17rem_minmax(0,1fr)]">
        <article class="rounded-lg border bg-surface p-6 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-widest text-primary">Overall match</p>
          <div class="mt-4 flex items-end gap-1">
            <strong class="text-5xl font-bold tracking-tight">{{ report.final_score ?? "—" }}</strong>
            <span class="mb-1 text-sm text-muted-foreground">/100</span>
          </div>
          <StatusBadge
            class="mt-4"
            :tone="recommendationTone(report.recommendation)"
            data-testid="recommendation"
          >
            {{ recommendationLabel(report.recommendation) }}
          </StatusBadge>
          <p
            class="mt-3 text-sm font-semibold"
            data-testid="match-band"
          >
            {{ scoreBand }}
          </p>
          <div class="mt-3 flex flex-wrap gap-2">
            <StatusBadge tone="success">Human Verified Resume</StatusBadge>
            <StatusBadge
              tone="neutral"
              data-testid="scoring-version"
            >
              {{ report.scoring_version }}
            </StatusBadge>
          </div>
          <p class="mt-4 text-sm leading-6 text-muted-foreground">
            {{ report.explanation || "后端未提供结论说明。" }}
          </p>
        </article>
        <article class="rounded-lg border bg-surface p-6 shadow-sm">
          <h2 class="font-semibold">报告快照</h2>
          <dl class="mt-4 grid gap-4 text-sm sm:grid-cols-2 xl:grid-cols-3">
            <div>
              <dt class="text-xs text-muted-foreground">规则分 / 最终分</dt>
              <dd class="mt-1 font-semibold">{{ report.rule_score ?? "—" }} / {{ report.final_score ?? "—" }}</dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">语义评分</dt>
              <dd class="mt-1 font-semibold">
                {{ report.semantic_score ?? "尚未启用语义评分" }}
              </dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">混合评分</dt>
              <dd class="mt-1 font-semibold">
                {{ report.hybrid_score ?? "尚未启用语义评分" }}
              </dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">评分版本</dt>
              <dd class="mt-1 flex items-center gap-2 font-semibold">
                {{ report.scoring_version }}
              </dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">Embedding 模型</dt>
              <dd class="mt-1 break-all font-semibold">
                {{ report.embedding_model || "不适用" }}
              </dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">岗位信息完整度</dt>
              <dd class="mt-1 font-semibold">
                {{ formatPercentage(report.job_information_completeness) }}
              </dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">报告可信度</dt>
              <dd class="mt-1 font-semibold">
                {{ report.report_confidence || "旧报告未记录" }}
              </dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">推荐上限</dt>
              <dd class="mt-1 font-semibold">
                {{ report.recommendation_cap || "无限制 / 旧报告未记录" }}
              </dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">Blocking 政策</dt>
              <dd class="mt-1 font-semibold">
                {{ report.policy_version || "deterministic-v1 历史规则" }}
              </dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">创建 / 完成</dt>
              <dd class="mt-1 text-xs">{{ formatDate(report.created_at) }}<br>{{ formatDate(report.completed_at) }}</dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">耗时</dt>
              <dd class="mt-1 font-semibold">{{ report.duration_ms ?? "—" }} ms</dd>
            </div>
            <div>
              <dt class="text-xs text-muted-foreground">输入快照</dt>
              <dd class="mt-1 font-semibold">
                {{ report.input_snapshot ? "已保存" : "旧报告未记录" }}
              </dd>
            </div>
          </dl>
          <details class="mt-5 rounded-md bg-muted p-4 text-xs">
            <summary class="cursor-pointer font-semibold">评分配置快照</summary>
            <dl class="mt-3 grid gap-2 sm:grid-cols-2">
              <div
                v-for="(weight, code) in report.scoring_config_snapshot.weights"
                :key="code"
                class="flex justify-between gap-3"
              >
                <dt class="text-muted-foreground">{{ code }}</dt>
                <dd class="font-semibold">{{ weight }}%</dd>
              </div>
            </dl>
          </details>
          <details
            class="mt-3 rounded-md border border-primary/15 bg-primary-soft p-4 text-xs"
            data-testid="matching-methodology"
          >
            <summary class="cursor-pointer font-semibold">How this score was calculated</summary>
            <div class="mt-3 space-y-2 leading-5 text-muted-foreground">
              <p>
                CareerPilot 使用确定性规则评估已确认的简历证据、技能、经验、学历与资格条件。
                六维权重来自本报告保存的评分配置快照。
              </p>
              <p v-if="report.scoring_version === 'hybrid-v1'">
                最终分 = 规则分 {{ Math.round((report.scoring_config_snapshot.hybrid_weights?.deterministic ?? 0.7) * 100) }}%
                + Semantic Relevance {{ Math.round((report.scoring_config_snapshot.hybrid_weights?.semantic ?? 0.3) * 100) }}%。
              </p>
              <p v-else>最终分等于确定性规则分；当前报告未加入语义相关性信号。</p>
              <p>
                Semantic Relevance 只表示文本相关程度，不证明候选人掌握技能，也不能覆盖 Blocking Risk。
              </p>
            </div>
          </details>
        </article>
      </section>

      <section
        class="grid gap-4 md:grid-cols-[16rem_minmax(0,1fr)]"
        data-testid="evidence-coverage"
      >
        <article class="rounded-lg border bg-surface p-6 shadow-sm">
          <p class="text-xs font-semibold uppercase tracking-widest text-primary">Evidence Coverage</p>
          <p class="mt-3 text-4xl font-bold">{{ Math.round(report.evidence_coverage.coverage_percent) }}%</p>
          <p class="mt-2 text-xs leading-5 text-muted-foreground">
            仅统计岗位技能要求中具有人工确认简历证据的比例，不额外加入总分。
          </p>
        </article>
        <article class="rounded-lg border bg-surface p-6 shadow-sm">
          <h2 class="font-semibold">技能证据覆盖明细</h2>
          <dl class="mt-4 grid gap-3 text-sm sm:grid-cols-5">
            <div><dt class="text-xs text-muted-foreground">相关要求</dt><dd class="mt-1 font-bold">{{ report.evidence_coverage.total_requirements }}</dd></div>
            <div><dt class="text-xs text-muted-foreground">已验证</dt><dd class="mt-1 font-bold text-success">{{ report.evidence_coverage.verified }}</dd></div>
            <div><dt class="text-xs text-muted-foreground">部分支持</dt><dd class="mt-1 font-bold text-warning">{{ report.evidence_coverage.partially_supported }}</dd></div>
            <div><dt class="text-xs text-muted-foreground">缺失</dt><dd class="mt-1 font-bold text-danger">{{ report.evidence_coverage.missing }}</dd></div>
            <div><dt class="text-xs text-muted-foreground">无法判断</dt><dd class="mt-1 font-bold">{{ report.evidence_coverage.unknown }}</dd></div>
          </dl>
        </article>
      </section>

      <section
        v-if="report.scoring_version === 'hybrid-v1'"
        class="rounded-lg border bg-surface p-6 shadow-sm"
        data-testid="semantic-evidence-section"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div class="flex items-center gap-2">
              <h2 class="text-lg font-semibold">Semantic Relevance</h2>
              <StatusBadge tone="info">Supporting signal</StatusBadge>
            </div>
            <p class="mt-1 text-sm text-muted-foreground">
              本地 FAISS 返回的项目、工作经历和技能证据相关性；规则证据仍在各规则结论中独立展示。
            </p>
          </div>
          <div class="text-right text-xs text-muted-foreground">
            <p>Top K：{{ report.semantic_config_snapshot?.top_k ?? "—" }}</p>
            <p>证据数：{{ report.semantic_summary?.evidence_count ?? 0 }}</p>
          </div>
        </div>
        <div
          v-if="!report.semantic_evidence?.length"
          class="mt-5 rounded-md border border-dashed p-6 text-center text-sm text-muted-foreground"
          data-testid="semantic-evidence-empty"
        >
          未找到超过相似度阈值的语义证据，semantic_score 保持边界值。
        </div>
        <ol
          v-else
          class="mt-5 grid gap-3 lg:grid-cols-2"
        >
          <li
            v-for="item in report.semantic_evidence"
            :key="`${item.rank}-${item.relation}`"
          >
            <button
              type="button"
              class="w-full rounded-md border p-4 text-left hover:border-primary/40"
              :data-testid="`semantic-evidence-${item.rank}`"
              @click="openSemanticEvidence(item)"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <strong class="text-sm">{{ item.resume_section }} → {{ item.job_field }}</strong>
                <StatusBadge tone="primary">
                  相似度 {{ Math.round(item.similarity * 100) }}%
                </StatusBadge>
              </div>
              <p class="mt-3 line-clamp-2 text-xs leading-5">
                {{ item.resume_text }}
              </p>
              <p class="mt-2 text-xs text-muted-foreground">
                {{
                  item.page_number
                    ? `第 ${item.page_number} 页`
                    : item.paragraph_index !== null
                      ? `第 ${item.paragraph_index + 1} 段`
                      : "来源位置未提供"
                }}
                · 查看原文
              </p>
            </button>
          </li>
        </ol>
        <p
          v-if="blockingRisks.length"
          class="mt-5 rounded-md bg-danger-soft p-4 text-sm text-danger"
        >
          语义相关性不能抵消资格冲突；Blocking 案例仍为不建议申请。
        </p>
      </section>

      <section
        v-if="report.job_requirements"
        class="rounded-lg border bg-surface p-6 shadow-sm"
        data-testid="structured-job-requirements"
      >
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold">结构化岗位要求</h2>
            <p class="mt-1 text-sm text-muted-foreground">
              Required、Preferred 与资格条件由确定性解析器从岗位 JD 提取。
            </p>
          </div>
          <StatusBadge tone="primary">
            Parsed from JD · {{ report.job_requirements.extractor_version }}
          </StatusBadge>
        </div>
        <div class="mt-5 grid gap-4 lg:grid-cols-3">
          <article class="rounded-md border p-4">
            <h3 class="font-semibold">Required Skills</h3>
            <ul class="mt-3 space-y-2 text-sm">
              <li
                v-for="skill in report.job_requirements.skills.filter((item) => item.required)"
                :key="`required-${skill.normalized_name}`"
                class="rounded-sm bg-muted p-3"
              >
                <strong>{{ skill.normalized_name }}</strong>
                <p class="mt-1 text-xs text-muted-foreground">{{ skill.evidence_text }}</p>
              </li>
              <li
                v-if="!report.job_requirements.skills.some((item) => item.required)"
                class="text-sm text-muted-foreground"
              >
                JD 未提供明确的必需技能。
              </li>
            </ul>
          </article>
          <article class="rounded-md border p-4">
            <h3 class="font-semibold">Preferred Skills</h3>
            <ul class="mt-3 space-y-2 text-sm">
              <li
                v-for="skill in report.job_requirements.skills.filter((item) => !item.required)"
                :key="`preferred-${skill.normalized_name}`"
                class="rounded-sm bg-muted p-3"
              >
                <strong>{{ skill.normalized_name }}</strong>
                <p class="mt-1 text-xs text-muted-foreground">{{ skill.evidence_text }}</p>
              </li>
              <li
                v-if="!report.job_requirements.skills.some((item) => !item.required)"
                class="text-sm text-muted-foreground"
              >
                JD 未提供明确的优先技能。
              </li>
            </ul>
          </article>
          <article class="rounded-md border p-4">
            <h3 class="font-semibold">Qualifications</h3>
            <dl class="mt-3 space-y-3 text-sm">
              <div>
                <dt class="text-xs text-muted-foreground">Experience · {{ report.job_requirements.experience_required_explicit ? "Required" : "Optional / unspecified" }}</dt>
                <dd class="mt-1">{{ report.job_requirements.minimum_experience_years !== null ? `${report.job_requirements.minimum_experience_years} 年` : "未提供" }}</dd>
              </div>
              <div>
                <dt class="text-xs text-muted-foreground">Education · {{ report.job_requirements.education_required_explicit ? "Required" : "Optional / unspecified" }}</dt>
                <dd class="mt-1">{{ report.job_requirements.education_level || "未提供" }}</dd>
              </div>
              <div>
                <dt class="text-xs text-muted-foreground">Language · {{ report.job_requirements.language_required_explicit ? "Required" : report.job_requirements.language_preferred ? "Preferred" : "Optional / unspecified" }}</dt>
                <dd class="mt-1">{{ report.job_requirements.languages.join("、") || "未提供" }}</dd>
              </div>
              <div>
                <dt class="text-xs text-muted-foreground">Work Authorization · Other Hard Requirement</dt>
                <dd class="mt-1">{{ report.job_requirements.work_eligibility || "未提供" }}</dd>
              </div>
            </dl>
          </article>
        </div>
      </section>

      <section
        id="dimension-scores"
        class="rounded-lg border bg-surface p-6 shadow-sm"
      >
        <div class="flex items-center justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold">六维评分</h2>
            <p class="mt-1 text-sm text-muted-foreground">
              原始分、权重与加权贡献均直接展示后端快照。
            </p>
          </div>
          <Target class="size-5 text-primary" />
        </div>
        <div class="mt-5 grid gap-6 xl:grid-cols-[minmax(20rem,0.9fr)_minmax(0,1.1fr)]">
          <MatchDimensionChart :dimensions="report.dimension_scores" />
          <div class="grid gap-3 sm:grid-cols-2">
            <button
              v-for="dimension in report.dimension_scores"
              :key="dimension.code"
              type="button"
              class="rounded-md border p-4 text-left hover:border-primary/40"
              :data-testid="`dimension-${dimension.code}`"
              @click="openDimensionEvidence(dimension)"
            >
              <div class="flex items-center justify-between gap-3">
                <div>
                  <strong class="text-sm">{{ dimension.label }}</strong>
                  <StatusBadge
                    class="mt-2"
                    :tone="dimensionTone(dimension.status)"
                  >
                    {{ dimension.status }}
                  </StatusBadge>
                </div>
                <span class="text-xl font-bold">{{ dimension.score }}</span>
              </div>
              <p class="mt-2 text-xs text-muted-foreground">
                权重 {{ snapshotWeight(dimension) }}% · 加权贡献 {{ dimension.weighted_score }}
                · 数据状态 {{ dimensionDetail(dimension)?.status ?? "后端未提供" }}
                · 风险 {{ riskCountForDimension(report, dimension) }}
              </p>
              <p
                class="mt-3 text-xs leading-5"
                :data-testid="`dimension-explanation-${dimension.code}`"
              >
                {{ dimension.explanation }}
              </p>
              <p class="mt-2 text-xs text-muted-foreground">
                可追溯证据 {{ dimension.evidence_keys.length }} 项 · 差距
                {{ dimension.gap_codes.length }} 项
              </p>
            </button>
          </div>
        </div>
      </section>

      <section class="rounded-lg border bg-surface p-6 shadow-sm">
        <div>
          <h2 class="text-lg font-semibold">Matched Skills 与 Skill Gaps</h2>
          <p class="mt-1 text-sm text-muted-foreground">
            Matched 只接受人工确认的简历原文证据；PARTIAL、MISSING、UNKNOWN 是技能差距，
            不等同于 Blocking Risk。
          </p>
        </div>
        <div class="mt-5 grid gap-5 xl:grid-cols-2">
          <section
            v-for="status in (['MATCHED', 'PARTIAL', 'MISSING', 'UNKNOWN'] as SkillMatchStatus[])"
            :key="status"
            class="rounded-md border p-4"
            :data-testid="`skills-${status}`"
          >
            <div class="flex items-center justify-between gap-3">
              <h3 class="font-semibold">{{ skillStatusLabels[status] }}</h3>
              <StatusBadge :tone="skillTone(status)">{{ skillGroups[status].length }}</StatusBadge>
            </div>
            <p
              v-if="skillGroups[status].length === 0"
              class="mt-4 text-sm text-muted-foreground"
            >
              此分类没有项目。
            </p>
            <ul
              v-else
              class="mt-4 space-y-3"
            >
              <li
                v-for="skill in skillGroups[status]"
                :key="`${status}-${skill.job_raw_name}`"
              >
                <button
                  type="button"
                  class="w-full rounded-sm bg-muted p-3 text-left hover:bg-primary-soft"
                  @click="openSkillEvidence(skill)"
                >
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <strong class="text-sm">{{ skill.job_raw_name }} → {{ skill.normalized_name }}</strong>
                    <StatusBadge :tone="skillTone(skill.status)">{{ skill.requirement_type }}</StatusBadge>
                  </div>
                  <p class="mt-2 text-xs text-muted-foreground">
                    简历技能 {{ resumeSkillFor(skill)?.normalized_name || "未关联" }}
                    · 用户确认 {{ resumeSkillFor(skill)?.is_user_confirmed ? "是" : "否" }}
                    · 证据 {{ skill.evidence_count ? `${skill.evidence_count} 条` : "无" }}
                  </p>
                  <p class="mt-1 text-xs text-muted-foreground">
                    规则 {{ skill.matching_rule }} · 评分影响 {{ Math.round(skill.score * 100) }}%
                  </p>
                  <div
                    v-if="skill.status === 'MATCHED' && firstSkillEvidence(skill)"
                    class="mt-3 rounded-sm border border-success/20 bg-surface p-3"
                    :data-testid="`skill-evidence-${skill.normalized_name}`"
                  >
                    <p class="text-xs font-semibold text-success">
                      Verified · {{ evidenceSourceLabel(firstSkillEvidence(skill)?.resume_section ?? null) }}
                    </p>
                    <blockquote class="mt-2 text-xs leading-5 text-muted-foreground">
                      “{{ firstSkillEvidence(skill)?.resume_evidence }}”
                    </blockquote>
                  </div>
                  <dl
                    v-else-if="skill.status !== 'MATCHED'"
                    class="mt-3 grid gap-2 rounded-sm border border-warning/20 bg-surface p-3 text-xs"
                  >
                    <div>
                      <dt class="text-muted-foreground">Job Requirement</dt>
                      <dd class="mt-1">{{ evidenceFor(report, skill.normalized_name)[0]?.job_snippet || skill.job_raw_name }}</dd>
                    </div>
                    <div>
                      <dt class="text-muted-foreground">Candidate Evidence</dt>
                      <dd class="mt-1">
                        {{ firstSkillEvidence(skill)?.resume_evidence || "No verified evidence found" }}
                      </dd>
                    </div>
                    <div>
                      <dt class="text-muted-foreground">Reason</dt>
                      <dd class="mt-1">{{ skill.explanation }}</dd>
                    </div>
                  </dl>
                </button>
              </li>
            </ul>
          </section>
        </div>
      </section>

      <section
        id="match-risks"
        class="rounded-lg border bg-surface p-6 shadow-sm"
        data-testid="blocking-risk-section"
      >
        <div class="flex items-center justify-between gap-3">
          <div>
            <h2 class="text-lg font-semibold">Blocking Risk</h2>
            <p class="mt-1 text-sm text-muted-foreground">
              资格类风险与 Skill Gap 独立。UNVERIFIED 表示尚无证据，CONFLICT 表示已知冲突。
            </p>
          </div>
          <ShieldAlert class="size-5 text-danger" />
        </div>
        <p
          v-if="blockingRisks.length === 0"
          class="mt-5 rounded-md bg-success-soft p-4 text-sm text-success"
        >
          未发现已确认或待核验的阻断性资格风险。
        </p>
        <ul
          v-else
          class="mt-5 space-y-3"
        >
          <li
            v-for="risk in blockingRisks"
            :key="risk.code"
          >
            <button
              type="button"
              class="w-full rounded-md border p-4 text-left hover:border-primary/35"
              :class="{ 'border-danger/40 bg-danger-soft': risk.severity === 'BLOCKING' || risk.severity === 'HIGH' }"
              @click="openRiskEvidence(risk)"
            >
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div class="flex items-center gap-2">
                  <CircleAlert class="size-4" />
                  <strong class="text-sm">{{ risk.title }}</strong>
                </div>
                <StatusBadge :tone="verificationTone(risk.verification_status)">
                  {{ risk.verification_status }}
                </StatusBadge>
              </div>
              <p class="mt-3 text-sm leading-6">{{ risk.explanation }}</p>
              <dl class="mt-3 grid gap-3 text-xs sm:grid-cols-3">
                <div><dt class="text-muted-foreground">岗位要求</dt><dd class="mt-1">{{ risk.job_requirement || "未提供" }}</dd></div>
                <div><dt class="text-muted-foreground">Resume Evidence</dt><dd class="mt-1">{{ risk.resume_evidence || "No verified evidence found" }}</dd></div>
                <div><dt class="text-muted-foreground">补救建议</dt><dd class="mt-1">{{ risk.remediation }}</dd></div>
              </dl>
            </button>
          </li>
        </ul>
      </section>

      <section
        v-if="generalRisks.length"
        class="rounded-lg border bg-surface p-6 shadow-sm"
        data-testid="general-risk-section"
      >
        <h2 class="text-lg font-semibold">其他确定性风险</h2>
        <p class="mt-1 text-sm text-muted-foreground">
          以下项目会影响判断或数据可信度，但不属于技能差距或阻断资格冲突。
        </p>
        <ul class="mt-5 space-y-3">
          <li
            v-for="risk in generalRisks"
            :key="risk.code"
            class="rounded-md border p-4"
          >
            <div class="flex flex-wrap items-center justify-between gap-2">
              <strong class="text-sm">{{ risk.title }}</strong>
              <StatusBadge :tone="severityTone(risk.severity)">
                {{ riskLabels[risk.severity] }} · {{ risk.verification_status }}
              </StatusBadge>
            </div>
            <p class="mt-2 text-sm leading-6">{{ risk.explanation }}</p>
          </li>
        </ul>
      </section>

      <section
        v-if="report.recommended_actions.length"
        class="rounded-lg border bg-surface p-6 shadow-sm"
      >
        <h2 class="flex items-center gap-2 text-lg font-semibold">
          <Scale class="size-5 text-primary" />
          建议行动
        </h2>
        <ol class="mt-4 grid gap-3 sm:grid-cols-2">
          <li
            v-for="action in report.recommended_actions"
            :key="action.code"
            class="rounded-md bg-muted p-4"
          >
            <strong class="text-sm">{{ action.title }}</strong>
            <p class="mt-2 text-xs leading-5 text-muted-foreground">{{ action.explanation }}</p>
          </li>
        </ol>
      </section>

      <MatchEvidenceDrawer
        :open="drawerOpen"
        :title="drawerTitle"
        :evidence="drawerEvidence"
        :semantic-evidence="drawerSemanticEvidence"
        :requirement="drawerRequirement"
        @close="drawerOpen = false"
      />
      <ConfirmDialog
        ref="recalculateDialog"
        title="创建新的匹配报告？"
        description="重新计算会创建一份新的匹配报告，旧报告不会被覆盖。"
        confirm-label="确认重新计算"
        @confirm="recalculate"
      />
    </template>
  </section>
</template>
