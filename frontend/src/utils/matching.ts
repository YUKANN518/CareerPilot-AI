import type {
  AvailabilityStatus,
  DimensionScore,
  EvidenceTrace,
  MatchPhase,
  MatchReport,
  RecommendationLevel,
  RiskSeverity,
  SkillMatch,
  SkillMatchStatus,
} from "@/types/matching"

export const MATCH_PHASES: MatchPhase[] = [
  "VALIDATING_INPUT",
  "EXTRACTING_REQUIREMENTS",
  "NORMALIZING_SKILLS",
  "MATCHING_RULES",
  "MATCHING_SEMANTIC",
  "VERIFYING_EVIDENCE",
  "CALCULATING_SCORE",
  "SAVING_REPORT",
]

export const phaseLabels: Record<MatchPhase, string> = {
  VALIDATING_INPUT: "校验输入",
  EXTRACTING_REQUIREMENTS: "提取岗位要求",
  NORMALIZING_SKILLS: "标准化技能",
  MATCHING_RULES: "执行确定性规则",
  MATCHING_SEMANTIC: "检索本地语义证据",
  VERIFYING_EVIDENCE: "验证证据",
  CALCULATING_SCORE: "计算评分",
  SAVING_REPORT: "保存报告",
  COMPLETED: "已完成",
}

export const recommendationLabels: Record<RecommendationLevel, string> = {
  STRONGLY_RECOMMENDED: "强烈推荐",
  RECOMMENDED: "推荐申请",
  CONSIDER: "可以考虑",
  HIGH_RISK: "风险较高",
  NOT_RECOMMENDED: "不建议申请",
}

export const skillStatusLabels: Record<SkillMatchStatus, string> = {
  MATCHED: "已匹配",
  PARTIAL: "部分匹配",
  MISSING: "缺失",
  UNKNOWN: "无法判断",
}

export const riskLabels: Record<RiskSeverity, string> = {
  INFO: "信息",
  LOW: "低",
  MEDIUM: "中",
  HIGH: "高",
  BLOCKING: "阻断",
}

export function recommendationLabel(value: RecommendationLevel | null): string {
  return value ? recommendationLabels[value] : "尚无结论"
}

export function allSkillMatches(report: MatchReport): SkillMatch[] {
  return [...report.matched_skills, ...report.partial_skills, ...report.missing_skills]
}

export function groupSkillMatches(
  report: MatchReport,
): Record<SkillMatchStatus, SkillMatch[]> {
  const grouped: Record<SkillMatchStatus, SkillMatch[]> = {
    MATCHED: [],
    PARTIAL: [],
    MISSING: [],
    UNKNOWN: [],
  }
  for (const item of allSkillMatches(report)) grouped[item.status].push(item)
  return grouped
}

export function evidenceFor(
  report: MatchReport,
  conclusionKey: string,
): EvidenceTrace[] {
  const key = conclusionKey.toLocaleLowerCase()
  return report.evidence_items.filter(
    (item) => item.conclusion_key.toLocaleLowerCase() === key,
  )
}

export function riskCountForDimension(
  report: MatchReport,
  dimension: DimensionScore,
): number {
  const code = dimension.code.toLocaleLowerCase()
  const mappings: Record<string, string[]> = {
    hard_skills: ["skill", "required"],
    evidence_strength: ["evidence"],
    experience_education: ["experience", "education"],
    language_location_eligibility: ["language", "location", "eligibility"],
    user_preferences: ["preference"],
    other_conditions: ["certificate", "condition"],
  }
  const tokens = mappings[code] ?? [code]
  return report.hard_requirement_risks.filter((risk) =>
    tokens.some((token) => risk.code.toLocaleLowerCase().includes(token)),
  ).length
}

export interface RequirementCompleteness {
  provided: number
  notProvided: number
  unknown: number
  incomplete: boolean
  statuses: Array<{ label: string; status: AvailabilityStatus }>
}

export function requirementCompleteness(report: MatchReport): RequirementCompleteness {
  const requirements = report.job_requirements
  if (!requirements) {
    return { provided: 0, notProvided: 0, unknown: 0, incomplete: true, statuses: [] }
  }
  const statuses = [
    { label: "经验", status: requirements.experience_status },
    { label: "学历", status: requirements.education_status },
    { label: "语言", status: requirements.language_status },
    { label: "地点", status: requirements.location_status },
    { label: "工作类型", status: requirements.employment_status },
    { label: "证书", status: requirements.certificate_status },
    { label: "工作资格", status: requirements.work_eligibility_status },
  ]
  const count = (status: AvailabilityStatus) =>
    statuses.filter((item) => item.status === status).length
  const notProvided = count("NOT_PROVIDED")
  const unknown =
    count("UNKNOWN") +
    allSkillMatches(report).filter((item) => item.status === "UNKNOWN").length
  return {
    provided: count("PROVIDED") + requirements.skills.length,
    notProvided,
    unknown,
    incomplete: notProvided > 0 || unknown > 0 || requirements.warnings.length > 0,
    statuses,
  }
}

export function isPositiveInteger(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) > 0
}
