import type {
  DimensionScore,
  EvidenceTrace,
  MatchReport,
  RiskItem,
  SkillMatch,
  SkillMatchStatus,
} from "@/types/matching"

const dimensions: DimensionScore[] = [
  ["hard_skills", "硬技能匹配", 90, 35, 31.5],
  ["evidence_strength", "项目与经历证据", 80, 20, 16],
  ["experience_education", "工作经验与教育", 85, 15, 12.75],
  ["language_location_eligibility", "语言、地点和资格", 70, 10, 7],
  ["user_preferences", "用户求职偏好", 100, 10, 10],
  ["other_conditions", "其他确定性岗位条件", 100, 10, 10],
].map(([code, label, score, weight, weighted_score]) => ({
  code: String(code),
  label: String(label),
  score: Number(score),
  weight: Number(weight),
  weighted_score: Number(weighted_score),
  explanation: `${label}的后端结论`,
  status: Number(score) >= 80 ? "GOOD" : Number(score) >= 50 ? "PARTIAL" : "WEAK",
  evidence_keys: ["hard_skills", "evidence_strength"].includes(String(code))
    ? ["Python"]
    : [],
  gap_codes: ["hard_skills", "evidence_strength"].includes(String(code))
    ? ["Kubernetes"]
    : [],
}))

function skill(status: SkillMatchStatus, name: string): SkillMatch {
  return {
    normalized_name: name,
    job_raw_name: `${name} raw`,
    category: "TECHNICAL",
    requirement_type: "REQUIRED",
    status,
    score: status === "MATCHED" ? 1 : status === "PARTIAL" ? 0.5 : 0,
    matching_rule: "deterministic-v1",
    explanation: `${name} ${status}`,
    resume_skill_id: status === "MATCHED" || status === "PARTIAL" ? 8 : null,
    evidence_count: status === "MATCHED" ? 1 : 0,
    source_types: status === "MATCHED" ? ["page"] : [],
    responsibility_keyword_overlap: status === "MATCHED",
  }
}

const evidence: EvidenceTrace = {
  conclusion_key: "Python",
  resume_version_id: 12,
  resume_skill_id: 8,
  resume_evidence: "Built a production Python API.",
  resume_section: "work_experience",
  source_type: "page",
  page_number: 1,
  paragraph_index: null,
  source_location: "page-1",
  job_field: "job_skills",
  job_snippet: "Python is required.",
  matching_rule: "EXACT_NORMALIZED_SKILL",
  confidence: 0.95,
}

export function matchReport(
  options: { blocking?: boolean; incomplete?: boolean; hybrid?: boolean } = {},
): MatchReport {
  const risks: RiskItem[] = options.blocking
    ? [
        {
          code: "WORK_ELIGIBILITY_BLOCKED",
          title: "Work Eligibility Blocked",
          severity: "BLOCKING",
          explanation: "Known eligibility conflict.",
          job_requirement: "Authorized to work in China",
          resume_evidence: "Not authorized",
          remediation: "Confirm sponsorship before applying.",
          risk_type: "BLOCKING_RISK",
          verification_status: "CONFLICT",
        },
      ]
    : []
  return {
    id: 41,
    user_id: 7,
    resume_version_id: 12,
    job_id: 31,
    status: "SUCCESS",
    current_phase: "COMPLETED",
    rule_score: options.blocking ? 93.67 : 87.25,
    semantic_score: options.hybrid ? 82 : null,
    hybrid_score: options.hybrid ? (options.blocking ? 90.17 : 85.68) : null,
    final_score: options.hybrid
      ? options.blocking
        ? 90.17
        : 85.68
      : options.blocking
        ? 93.67
        : 87.25,
    scoring_version: options.hybrid ? "hybrid-v1" : "deterministic-v1",
    scoring_config_snapshot: {
      version: "deterministic-v1",
      skill_dictionary_version: "skill-dictionary-v1",
      job_requirement_extractor_version: "job-requirements-v1",
      weights: {
        hard_skills: 35,
        evidence_strength: 20,
        experience_education: 15,
        language_location_eligibility: 10,
        user_preferences: 10,
        other_conditions: 10,
      },
      partial_skill_credit: 0.5,
      unknown_criterion_credit: 0.7,
      required_skill_weight: 2,
      preferred_skill_weight: 1,
    },
    dimension_scores: dimensions,
    matched_skills: [skill("MATCHED", "Python")],
    partial_skills: [skill("PARTIAL", "SQL"), skill("UNKNOWN", "NovelDB")],
    missing_skills: [skill("MISSING", "Kubernetes")],
    hard_requirement_risks: risks,
    evidence_items: [
      evidence,
      ...(options.blocking
        ? [
            {
              ...evidence,
              conclusion_key: "WORK_ELIGIBILITY_BLOCKED",
              resume_skill_id: null,
              resume_evidence: "Not authorized",
              job_field: "work_eligibility",
              job_snippet: "Authorized to work in China",
            },
          ]
        : []),
    ],
    recommendation: options.blocking ? "NOT_RECOMMENDED" : "STRONGLY_RECOMMENDED",
    explanation: "Deterministic evidence-backed result.",
    recommended_actions: [],
    job_requirements: {
      job_title: "Backend Engineer",
      industry: "Software",
      salary_min: null,
      salary_max: null,
      skills: [],
      minimum_experience_years: 2,
      experience_status: "PROVIDED",
      graduate_exception: false,
      education_level: null,
      education_status: options.incomplete ? "NOT_PROVIDED" : "PROVIDED",
      languages: ["English"],
      language_status: "PROVIDED",
      location: "Shanghai",
      location_status: "PROVIDED",
      employment_type: "FULL_TIME",
      employment_status: "PROVIDED",
      certificates: [],
      certificates_required: false,
      certificate_status: options.incomplete ? "NOT_PROVIDED" : "PROVIDED",
      work_eligibility: null,
      work_eligibility_status: options.incomplete ? "UNKNOWN" : "PROVIDED",
      experience_required_explicit: true,
      education_required_explicit: false,
      education_non_substitutable: false,
      language_required_explicit: true,
      language_preferred: false,
      certificate_required_explicit: false,
      certificate_preferred: false,
      warnings: options.incomplete ? ["Job requirements are incomplete"] : [],
      extractor_version: "job-requirements-v1",
    },
    phase_timings_ms: {
      VALIDATING_INPUT: 0,
      EXTRACTING_REQUIREMENTS: 2,
      NORMALIZING_SKILLS: 1,
      MATCHING_RULES: 4,
      VERIFYING_EVIDENCE: 2,
      CALCULATING_SCORE: 1,
      SAVING_REPORT: 1,
      COMPLETED: 0,
    },
    duration_ms: 11,
    error_code: null,
    error_message: null,
    started_at: "2026-07-17T01:00:00Z",
    completed_at: "2026-07-17T01:00:00.011Z",
    created_at: "2026-07-17T01:00:00Z",
    updated_at: "2026-07-17T01:00:00.011Z",
    job_information_completeness: options.hybrid ? (options.incomplete ? 0.45 : 0.92) : null,
    report_confidence: options.hybrid ? (options.incomplete ? "VERY_LOW" : "HIGH") : null,
    report_confidence_score: options.hybrid ? (options.incomplete ? 0.45 : 0.92) : null,
    recommendation_cap: options.hybrid && options.incomplete ? "CONSIDER" : null,
    policy_version: options.hybrid ? "blocking-policy-v1" : null,
    embedding_model: options.hybrid ? "fake-deterministic-v1" : null,
    semantic_config_snapshot: options.hybrid
      ? {
          version: "semantic-v1",
          top_k: 5,
          similarity_threshold: 0.25,
          similarity_ceiling: 1,
          empty_score: 0,
        }
      : null,
    semantic_summary: options.hybrid
      ? {
          evidence_count: 1,
          evaluated_resume_chunks: 4,
          top_similarity: 0.86,
          relation_counts: { project_experience_to_responsibilities: 1 },
        }
      : null,
    semantic_evidence: options.hybrid
      ? [
          {
            rank: 1,
            relation: "project_experience_to_responsibilities",
            similarity: 0.86,
            score: 81.33,
            resume_text: "Built a multilingual recommendation API.",
            job_text: "Build recommendation services for international users.",
            resume_section: "project_experience",
            job_field: "responsibilities",
            page_number: 2,
            paragraph_index: 3,
            resume_metadata: { content_hash: "resume-hash" },
            job_metadata: { content_hash: "job-hash" },
          },
        ]
      : [],
    evidence_coverage: {
      total_requirements: 4,
      verified: 1,
      partially_supported: 1,
      missing: 1,
      unknown: 1,
      coverage_percent: 25,
    },
    input_snapshot: {
      resume: {
        resume_id: 5,
        version_id: 12,
        version_number: 1,
        is_confirmed: true,
        created_at: "2026-07-17T00:00:00Z",
      },
      job: {
        job_id: 31,
        title: "Backend Engineer",
        company: "Fixture Company",
        location: "Shanghai",
        content_hash: "fixture-hash",
        import_method: "MANUAL",
        description: "Build APIs.",
        requirements: "Python required.",
        responsibilities: "Build reliable services.",
      },
    },
  }
}
