import {
  dashboardApi,
  type DashboardData,
  type DashboardResumeStatus,
} from "@/api/dashboard"

export type DashboardMetricTone = "primary" | "info" | "success" | "warning"
export type DashboardIconName = "resume" | "version" | "evidence" | "match"
export type DashboardWorkflowStatus =
  | "uploaded"
  | "processing"
  | "extracted"
  | "review"
  | "confirmed"
  | "failed"

export interface DashboardMetric {
  id: string
  label: string
  value: number
  suffix?: string
  helper: string
  tone: DashboardMetricTone
  icon: DashboardIconName
}

export interface DashboardWorkflow {
  id: number
  title: string
  fileType: string
  updatedAt: string
  status: DashboardWorkflowStatus
  progress: number
}

export interface DashboardSkillEvidence {
  name: string
  count: number
  percentage: number
  tone: DashboardMetricTone
}

export interface DashboardFunnelStep {
  label: string
  value: number
  description: string
}

export interface DashboardApplicationFunnelStep {
  label: string
  value: number
  description: string
}

export interface DashboardRecommendedJob {
  reportId: number
  jobId: number
  title: string
  company: string
  location: string
  score: number
  recommendation: string
  scoringVersion: string
}

export interface DashboardSnapshot {
  completeness: number
  completenessLabel: string
  pendingConfirmationCount: number
  recommendedJobCount: number
  metrics: DashboardMetric[]
  workflows: DashboardWorkflow[]
  skillEvidence: DashboardSkillEvidence[]
  funnel: DashboardFunnelStep[]
  applicationFunnel: DashboardApplicationFunnelStep[]
  recommendedJobs: DashboardRecommendedJob[]
}

const tones: DashboardMetricTone[] = ["primary", "info", "warning", "success"]

function workflowStatus(status: DashboardResumeStatus): DashboardWorkflowStatus {
  const mapping: Record<DashboardResumeStatus, DashboardWorkflowStatus> = {
    UPLOADED: "uploaded",
    EXTRACTING: "processing",
    EXTRACTED: "extracted",
    PARSING: "processing",
    NEEDS_CONFIRMATION: "review",
    CONFIRMED: "confirmed",
    FAILED: "failed",
    ARCHIVED: "confirmed",
  }
  return mapping[status]
}

function formatDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date)
}

export function toDashboardSnapshot(data: DashboardData): DashboardSnapshot {
  const average = data.average_match_score ?? 0
  return {
    completeness: data.resume_completeness,
    completenessLabel: "当前主简历",
    pendingConfirmationCount: data.pending_confirmation_count,
    recommendedJobCount: data.recommended_job_count,
    metrics: [
      {
        id: "completeness",
        label: "简历完整度",
        value: data.resume_completeness,
        suffix: "%",
        helper: "基于当前已确认版本",
        tone: "primary",
        icon: "resume",
      },
      {
        id: "versions",
        label: "已确认版本",
        value: data.confirmed_version_count,
        helper: "历史版本不可覆盖",
        tone: "success",
        icon: "version",
      },
      {
        id: "evidence",
        label: "技能证据",
        value: data.confirmed_skill_evidence_count,
        helper: "用户确认且可追溯",
        tone: "info",
        icon: "evidence",
      },
      {
        id: "matches",
        label: "已分析岗位",
        value: data.analyzed_job_count,
        helper:
          data.average_match_score === null
            ? "尚无匹配报告"
            : `平均匹配分 ${average.toFixed(1)}`,
        tone: "warning",
        icon: "match",
      },
      {
        id: "applications-week",
        label: "近 7 天投递",
        value: data.weekly_application_count,
        helper: `待推进面试 ${data.pending_interview_count} 个`,
        tone: "primary",
        icon: "match",
      },
    ],
    workflows: data.recent_resumes.map((resume) => ({
      id: resume.id,
      title: resume.title,
      fileType: resume.file_type ?? "FILE",
      updatedAt: formatDate(resume.updated_at),
      status: workflowStatus(resume.status),
      progress: resume.progress,
    })),
    skillEvidence: data.top_skills.map((skill, index) => ({
      name: skill.name,
      count: skill.evidence_count,
      percentage: skill.percentage,
      tone: tones[index % tones.length] ?? "primary",
    })),
    funnel: [
      {
        label: "已上传",
        value: data.resume_funnel.uploaded,
        description: "原始文件已安全保存",
      },
      {
        label: "已提取",
        value: data.resume_funnel.extracted,
        description: "文本与来源已定位",
      },
      {
        label: "待确认",
        value: data.resume_funnel.needs_confirmation,
        description: "需要人工核对",
      },
      {
        label: "已成版",
        value: data.resume_funnel.confirmed,
        description: "不可覆盖的正式版本",
      },
    ],
    applicationFunnel: [
      {
        label: "收藏",
        value: data.application_funnel.saved,
        description: "待投递的岗位",
      },
      {
        label: "已投递",
        value: data.application_funnel.applied,
        description: "等待招聘方反馈",
      },
      {
        label: "面试",
        value: data.application_funnel.interview,
        description: "需要继续推进",
      },
      {
        label: "Offer",
        value: data.application_funnel.offer,
        description: "等待决策",
      },
      {
        label: "拒绝",
        value: data.application_funnel.rejected,
        description: "已结束的机会",
      },
    ],
    recommendedJobs: data.recommended_jobs.map((job) => ({
      reportId: job.report_id,
      jobId: job.job_id,
      title: job.title,
      company: job.company,
      location: job.location ?? "地点未提供",
      score: job.final_score,
      recommendation: job.recommendation,
      scoringVersion: job.scoring_version,
    })),
  }
}

export interface DashboardService {
  getSnapshot(): Promise<DashboardSnapshot>
}

class RealDashboardService implements DashboardService {
  async getSnapshot(): Promise<DashboardSnapshot> {
    return toDashboardSnapshot(await dashboardApi.getDashboard())
  }
}

export const dashboardService: DashboardService = new RealDashboardService()
