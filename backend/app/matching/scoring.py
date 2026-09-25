from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.matching.config import DEFAULT_SCORING_CONFIG
from app.matching.normalization import SkillNormalizationService
from app.matching.policy import (
    confidence_for,
    count_unknown_requirements,
    recommendation_cap_for,
)
from app.models.resumes import ResumeSkill, ResumeVersion
from app.models.users import UserProfile
from app.schemas.matching import (
    AvailabilityStatus,
    DimensionScore,
    DimensionStatus,
    EvidenceTrace,
    JobInformationAssessment,
    JobRequirements,
    MatchComputation,
    RecommendationLevel,
    RecommendedAction,
    RiskItem,
    RiskSeverity,
    RiskType,
    ScoringConfig,
    SkillMatch,
    SkillMatchStatus,
    VerificationStatus,
)

EDUCATION_RANK = {
    "HIGH_SCHOOL": 1,
    "ASSOCIATE": 2,
    "BACHELOR": 3,
    "MASTER": 4,
    "DOCTORATE": 5,
}
SEVERITY_ORDER = {
    RiskSeverity.INFO: 0,
    RiskSeverity.LOW: 1,
    RiskSeverity.MEDIUM: 2,
    RiskSeverity.HIGH: 3,
    RiskSeverity.BLOCKING: 4,
}
RECOMMENDATION_ORDER = {
    RecommendationLevel.STRONGLY_RECOMMENDED: 0,
    RecommendationLevel.RECOMMENDED: 1,
    RecommendationLevel.CONSIDER: 2,
    RecommendationLevel.HIGH_RISK: 3,
    RecommendationLevel.NOT_RECOMMENDED: 4,
}
RECOMMENDATION_LABELS = {
    RecommendationLevel.STRONGLY_RECOMMENDED: "强烈推荐",
    RecommendationLevel.RECOMMENDED: "推荐申请",
    RecommendationLevel.CONSIDER: "可以考虑",
    RecommendationLevel.HIGH_RISK: "风险较高",
    RecommendationLevel.NOT_RECOMMENDED: "不建议申请",
}
RISK_TITLE_LABELS = {
    "EXPERIENCE_UNKNOWN": "工作经验待核验",
    "MINIMUM_EXPERIENCE_NOT_MET": "最低经验要求未满足",
    "EDUCATION_UNKNOWN": "学历信息待核验",
    "EDUCATION_REQUIREMENT_NOT_MET": "学历要求未满足",
    "LANGUAGE_CAPABILITY_UNKNOWN": "语言能力待核验",
    "LANGUAGE_REQUIREMENT_NOT_MET": "语言要求未满足",
    "LOCATION_COMPATIBILITY_UNKNOWN": "工作地点兼容性待核验",
    "LOCATION_MISMATCH": "工作地点不匹配",
    "WORK_ELIGIBILITY_UNKNOWN": "任职资格待核验",
    "WORK_ELIGIBILITY_BLOCKED": "任职资格存在阻断冲突",
    "USER_PREFERENCE_MISMATCH": "岗位与求职偏好不一致",
    "PREFERENCES_NOT_SET": "尚未设置求职偏好",
    "CERTIFICATE_REQUIREMENT_NOT_MET": "证书要求未满足",
    "CERTIFICATE_STATUS_UNKNOWN": "证书状态待核验",
    "JOB_REQUIREMENTS_INCOMPLETE": "岗位要求信息不完整",
}


def recommendation_for_score(
    score: float,
    risks: list[RiskItem],
    cap: RecommendationLevel | None = None,
) -> RecommendationLevel:
    recommendation = DeterministicMatchEngine._recommendation(score, risks)
    if cap is not None:
        return DeterministicMatchEngine._apply_recommendation_cap(recommendation, cap)
    return recommendation


class DeterministicMatchEngine:
    """Calculate a reproducible rule score and evidence-backed explanation."""

    def __init__(
        self,
        normalizer: SkillNormalizationService,
        config: ScoringConfig = DEFAULT_SCORING_CONFIG,
    ) -> None:
        self.normalizer = normalizer
        self.config = config

    def calculate(
        self,
        resume_version: ResumeVersion,
        requirements: JobRequirements,
        profile: UserProfile | None,
        job_information: JobInformationAssessment | None = None,
    ) -> MatchComputation:
        structured_data = resume_version.structured_data
        resume_skills = self._resume_skill_index(resume_version.skills)
        skill_matches, evidence_items, skill_risks = self._match_skills(
            resume_version.id,
            requirements,
            resume_skills,
        )
        hard_skill_score = self._skill_score(skill_matches)
        evidence_score = self._evidence_score(skill_matches, evidence_items)

        experience_score, experience_risks = self._experience_score(
            structured_data,
            resume_version.created_at,
            requirements,
        )
        education_score, education_risks = self._education_score(
            structured_data,
            requirements,
        )
        experience_education_score = round((experience_score + education_score) / 2, 2)

        qualification_score, qualification_risks = self._qualification_score(
            structured_data,
            requirements,
            profile,
        )
        preference_score, preference_risks = self._preference_score(requirements, profile)
        other_score, other_risks = self._other_conditions_score(
            structured_data,
            requirements,
        )
        risks = [
            *skill_risks,
            *experience_risks,
            *education_risks,
            *qualification_risks,
            *preference_risks,
            *other_risks,
        ]
        if requirements.warnings:
            risks.append(
                RiskItem(
                    code="JOB_REQUIREMENTS_INCOMPLETE",
                    severity=RiskSeverity.INFO,
                    explanation="; ".join(requirements.warnings),
                    job_requirement=None,
                    resume_evidence=None,
                    remediation="作出最终决定前，请核对原始招聘信息。",
                )
            )
        risks = [self._classify_risk(item, requirements) for item in risks]
        skill_evidence_keys = [
            item.normalized_name
            for item in skill_matches
            if item.status is SkillMatchStatus.MATCHED and item.evidence_count > 0
        ]
        skill_gap_codes = [
            item.normalized_name
            for item in skill_matches
            if item.status is not SkillMatchStatus.MATCHED
        ]
        experience_education_gaps = [
            item.code
            for item in risks
            if "EXPERIENCE" in item.code or "EDUCATION" in item.code
        ]
        qualification_gaps = [
            item.code
            for item in risks
            if any(token in item.code for token in ("LANGUAGE", "LOCATION", "ELIGIBILITY"))
        ]
        certificate_gaps = [item.code for item in risks if "CERTIFICATE" in item.code]

        dimension_scores = [
            self._dimension(
                "hard_skills",
                "硬技能",
                hard_skill_score,
                self.config.weights.hard_skills,
                "必需技能的权重是加分技能的两倍。",
                evidence_keys=skill_evidence_keys,
                gap_codes=skill_gap_codes,
            ),
            self._dimension(
                "evidence_strength",
                "证据强度",
                evidence_score,
                self.config.weights.evidence_strength,
                "只有经用户确认且带原文来源证据的简历技能才能获得满分。",
                evidence_keys=skill_evidence_keys,
                gap_codes=skill_gap_codes,
            ),
            self._dimension(
                "experience_education",
                "经验与教育背景",
                experience_education_score,
                self.config.weights.experience_education,
                "明确的最低要求会与带日期的工作经历和教育记录进行比较。",
                evidence_keys=[
                    code
                    for code, status in (
                        ("EXPERIENCE", requirements.experience_status),
                        ("EDUCATION", requirements.education_status),
                    )
                    if status is AvailabilityStatus.PROVIDED
                ],
                gap_codes=experience_education_gaps,
            ),
            self._dimension(
                "language_location_eligibility",
                "语言、地点与任职资格",
                qualification_score,
                self.config.weights.language_location_eligibility,
                "岗位未提供的条件不扣分；候选人未知信息按中性处理。",
                evidence_keys=[
                    code
                    for code, status in (
                        ("LANGUAGE", requirements.language_status),
                        ("LOCATION", requirements.location_status),
                        ("WORK_ELIGIBILITY", requirements.work_eligibility_status),
                    )
                    if status is AvailabilityStatus.PROVIDED
                ],
                gap_codes=qualification_gaps,
            ),
            self._dimension(
                "user_preferences",
                "求职偏好",
                preference_score,
                self.config.weights.user_preferences,
                "求职偏好为可选信息，未设置时不会降低评分。",
                gap_codes=[item.code for item in risks if "PREFERENCE" in item.code],
            ),
            self._dimension(
                "other_conditions",
                "其他条件",
                other_score,
                self.config.weights.other_conditions,
                "检查明确提出的证书要求及其他确定性条件。",
                evidence_keys=(
                    ["CERTIFICATE"]
                    if requirements.certificate_status is AvailabilityStatus.PROVIDED
                    else []
                ),
                gap_codes=certificate_gaps,
            ),
        ]
        rule_score = round(sum(item.weighted_score for item in dimension_scores), 2)
        recommendation = self._recommendation(rule_score, risks)
        completeness = None
        report_confidence = None
        report_confidence_score = None
        completeness_warning = None
        evaluated_count = 0
        unknown_count = 0
        not_provided_count = 0
        recommendation_cap = None
        policy = self.config.blocking_policy
        if policy is not None and job_information is not None:
            completeness = job_information.job_information_completeness
            evaluated_count = job_information.evaluated_requirement_count
            not_provided_count = job_information.not_provided_requirement_count
            unknown_count = count_unknown_requirements(
                sum(item.status is SkillMatchStatus.UNKNOWN for item in skill_matches),
                (item.code for item in risks),
                job_information,
            )
            report_confidence, report_confidence_score = confidence_for(
                completeness,
                unknown_count,
                evaluated_count,
                policy,
            )
            recommendation_cap = recommendation_cap_for(completeness, policy)
            if recommendation_cap is not None:
                recommendation = self._apply_recommendation_cap(
                    recommendation,
                    recommendation_cap,
                )
                completeness_warning = (
                    f"岗位信息完整度为 {completeness:.0%}；"
                    f"推荐结论上限为{RECOMMENDATION_LABELS[recommendation_cap]}。"
                )
        actions = self._actions(risks)
        matched_count = sum(item.status is SkillMatchStatus.MATCHED for item in skill_matches)
        required_count = sum(item.requirement_type == "REQUIRED" for item in skill_matches)
        explanation = (
            f"确定性规则评分为 {rule_score:.2f}/100，采用 {self.config.version}；"
            f"共提取 {len(skill_matches)} 项技能要求，其中 {matched_count} 项有已确认证据，"
            f"{required_count} 项为必需技能。"
        )
        return MatchComputation(
            rule_score=rule_score,
            dimension_scores=dimension_scores,
            skill_matches=skill_matches,
            risks=risks,
            evidence_items=evidence_items,
            recommendation=recommendation,
            explanation=explanation,
            recommended_actions=actions,
            job_information_completeness=completeness,
            report_confidence=report_confidence,
            report_confidence_score=report_confidence_score,
            completeness_warning=completeness_warning,
            evaluated_requirement_count=evaluated_count,
            unknown_requirement_count=unknown_count,
            not_provided_requirement_count=not_provided_count,
            recommendation_cap=recommendation_cap,
            policy_version=policy.policy_version if policy is not None else None,
            policy_config_snapshot=policy,
        )

    def _match_skills(
        self,
        resume_version_id: int,
        requirements: JobRequirements,
        resume_skills: dict[str, list[ResumeSkill]],
    ) -> tuple[list[SkillMatch], list[EvidenceTrace], list[RiskItem]]:
        matches: list[SkillMatch] = []
        evidence_items: list[EvidenceTrace] = []
        risks: list[RiskItem] = []
        for requirement in requirements.skills:
            candidates = resume_skills.get(requirement.normalized_name.casefold(), [])
            eligible_candidates = sorted(
                (
                    item
                    for item in candidates
                    if item.is_user_confirmed and item.evidence_text.strip()
                ),
                key=lambda item: (-item.confidence, item.id),
            )
            candidate = max(
                candidates,
                key=lambda item: (
                    bool(item.is_user_confirmed and item.evidence_text.strip()),
                    item.confidence,
                    -item.id,
                ),
                default=None,
            )
            requirement_type = "REQUIRED" if requirement.required else "PREFERRED"
            if eligible_candidates:
                candidate = eligible_candidates[0]
                status = SkillMatchStatus.MATCHED
                score = 1.0
                explanation = "已确认的简历技能具有可追溯的原文证据。"
            elif candidate is not None:
                status = SkillMatchStatus.PARTIAL
                score = self.config.partial_skill_credit
                explanation = "简历中存在该技能，但用户确认或来源证据不完整。"
            elif requirement.normalization_rule == "NORMALIZED_TEXT":
                status = SkillMatchStatus.UNKNOWN
                score = self.config.unknown_criterion_credit
                explanation = "该岗位术语超出当前技能词典的安全识别范围。"
            else:
                status = SkillMatchStatus.MISSING
                score = 0.0
                explanation = "未找到与岗位要求等价的简历技能。"
            trace_candidates = eligible_candidates or ([candidate] if candidate is not None else [])
            traces = [
                self._evidence_trace(
                    resume_version_id,
                    item,
                    requirement.normalized_name,
                    requirement.source_field,
                    requirement.evidence_text,
                    (
                        "CANONICAL_SKILL_WITH_CONFIRMED_EVIDENCE"
                        if status is SkillMatchStatus.MATCHED
                        else "SKILL_NAME_WITH_INCOMPLETE_EVIDENCE"
                    ),
                )
                for item in trace_candidates
            ]
            overlap = any(
                self._token_overlap(item.resume_evidence, item.job_snippet) for item in traces
            )
            source_types = sorted(
                {item.source_type for item in traces if item.source_type is not None}
            )
            match = SkillMatch(
                normalized_name=requirement.normalized_name,
                job_raw_name=requirement.raw_name,
                category=requirement.category,
                requirement_type=requirement_type,
                status=status,
                score=score,
                matching_rule=requirement.normalization_rule,
                explanation=explanation,
                resume_skill_id=candidate.id if candidate is not None else None,
                evidence_count=len(eligible_candidates),
                source_types=source_types,
                responsibility_keyword_overlap=overlap,
            )
            matches.append(match)
            if traces:
                evidence_items.extend(traces)
            else:
                evidence_items.append(
                    EvidenceTrace(
                        conclusion_key=requirement.normalized_name,
                        resume_version_id=resume_version_id,
                        resume_skill_id=None,
                        resume_evidence=None,
                        resume_section=None,
                        source_type=None,
                        page_number=None,
                        paragraph_index=None,
                        source_location=None,
                        job_field=requirement.source_field,
                        job_snippet=requirement.evidence_text,
                        matching_rule=requirement.normalization_rule,
                        confidence=requirement.confidence,
                    )
                )
            if requirement.required and status is not SkillMatchStatus.MATCHED:
                severity = {
                    SkillMatchStatus.MISSING: RiskSeverity.HIGH,
                    SkillMatchStatus.PARTIAL: RiskSeverity.MEDIUM,
                    SkillMatchStatus.UNKNOWN: RiskSeverity.INFO,
                    SkillMatchStatus.MATCHED: RiskSeverity.INFO,
                }[status]
                risks.append(
                    RiskItem(
                        code=f"REQUIRED_SKILL_{status.value}",
                        severity=severity,
                        explanation=explanation,
                        job_requirement=requirement.evidence_text,
                        resume_evidence=candidate.evidence_text if candidate else None,
                        remediation=(
                            "申请前请补充可核验的技能证据，或先提升该项必需技能。"
                        ),
                    )
                )
        return matches, evidence_items, risks

    def _resume_skill_index(
        self,
        resume_skills: Iterable[ResumeSkill],
    ) -> dict[str, list[ResumeSkill]]:
        indexed: dict[str, list[ResumeSkill]] = {}
        for skill in resume_skills:
            names = (skill.skill.name, skill.raw_name)
            for name in names:
                normalized = self.normalizer.normalize(name)
                indexed.setdefault(normalized.normalized_name.casefold(), []).append(skill)
        return indexed

    def _skill_score(self, matches: list[SkillMatch]) -> float:
        if not matches:
            return 100.0
        numerator = 0.0
        denominator = 0
        for match in matches:
            weight = (
                self.config.required_skill_weight
                if match.requirement_type == "REQUIRED"
                else self.config.preferred_skill_weight
            )
            numerator += match.score * weight
            denominator += weight
        return round(numerator / denominator * 100, 2)

    def _evidence_score(
        self,
        matches: list[SkillMatch],
        evidence_items: list[EvidenceTrace],
    ) -> float:
        if not matches:
            return 100.0
        evidence_by_conclusion: dict[str, list[EvidenceTrace]] = {}
        for item in evidence_items:
            evidence_by_conclusion.setdefault(item.conclusion_key.casefold(), []).append(item)
        section_skill_counts: dict[str, set[str]] = {}
        for item in evidence_items:
            if item.resume_section:
                section_skill_counts.setdefault(item.resume_section, set()).add(
                    item.conclusion_key.casefold()
                )
        scores: list[float] = []
        weights: list[int] = []
        for match in matches:
            weight = 2 if match.requirement_type == "REQUIRED" else 1
            evidence = evidence_by_conclusion.get(match.normalized_name.casefold(), [])
            usable_evidence = [item for item in evidence if item.resume_evidence]
            if not usable_evidence:
                strength = 0.25 if match.status is SkillMatchStatus.PARTIAL else 0.0
            else:
                strength = 0.55
                strength += min(len(usable_evidence) * 0.05, 0.15)
                if any(item.source_location for item in usable_evidence):
                    strength += 0.1
                if any(
                    item.resume_section in {"project_experience", "work_experience"}
                    for item in usable_evidence
                ):
                    strength += 0.1
                if match.responsibility_keyword_overlap:
                    strength += 0.1
                if any(
                    item.resume_section
                    and len(section_skill_counts.get(item.resume_section, set())) >= 2
                    for item in usable_evidence
                ):
                    strength += 0.05
            scores.append(min(strength, 1.0) * weight)
            weights.append(weight)
        return round(sum(scores) / sum(weights) * 100, 2)

    def _experience_score(
        self,
        structured_data: dict[str, Any],
        anchor: datetime,
        requirements: JobRequirements,
    ) -> tuple[float, list[RiskItem]]:
        minimum = requirements.minimum_experience_years
        if requirements.experience_status is AvailabilityStatus.NOT_PROVIDED:
            return 100.0, []
        actual = self._experience_years(structured_data, anchor)
        if requirements.graduate_exception:
            return 100.0, []
        if minimum is None:
            return 100.0, []
        if actual is None:
            return self.config.unknown_criterion_credit * 100, [
                RiskItem(
                    code="EXPERIENCE_UNKNOWN",
                    severity=RiskSeverity.INFO,
                    explanation="简历中缺少足够的带日期工作经历，暂时无法判断经验年限。",
                    job_requirement=f"最低 {minimum:g} 年",
                    resume_evidence=None,
                    remediation="请补充并确认工作经历的起止时间后再判断该维度。",
                )
            ]
        if actual >= minimum:
            return 100.0, []
        gap = minimum - actual
        severity = RiskSeverity.HIGH if gap >= 2 else RiskSeverity.MEDIUM
        if (
            self.config.blocking_policy is not None
            and requirements.experience_required_explicit
            and gap >= self.config.blocking_policy.blocking_experience_gap_years
        ):
            severity = RiskSeverity.BLOCKING
        return round(max(actual / max(minimum, 1), 0) * 100, 2), [
            RiskItem(
                code="MINIMUM_EXPERIENCE_NOT_MET",
                severity=severity,
                explanation=(
                    f"简历证据显示 {actual:.1f} 年经验，岗位要求至少 {minimum:g} 年。"
                ),
                job_requirement=f"最低 {minimum:g} 年",
                resume_evidence=f"根据带日期的工作经历计算为 {actual:.1f} 年",
                remediation="优先考虑经验要求更接近的岗位，或补充缺失的工作日期。",
            )
        ]

    def _education_score(
        self,
        structured_data: dict[str, Any],
        requirements: JobRequirements,
    ) -> tuple[float, list[RiskItem]]:
        required = requirements.education_level
        if requirements.education_status is AvailabilityStatus.NOT_PROVIDED or required is None:
            return 100.0, []
        actual = self._education_level(structured_data)
        if actual is None:
            return self.config.unknown_criterion_credit * 100, [
                RiskItem(
                    code="EDUCATION_UNKNOWN",
                    severity=RiskSeverity.INFO,
                    explanation="已确认的简历中未识别到可比较的学历层级。",
                    job_requirement=required,
                    resume_evidence=None,
                    remediation="请在简历资料中确认学历层级。",
                )
            ]
        if EDUCATION_RANK[actual] >= EDUCATION_RANK[required]:
            return 100.0, []
        severity = RiskSeverity.HIGH
        if (
            self.config.blocking_policy is not None
            and requirements.education_required_explicit
            and requirements.education_non_substitutable
        ):
            severity = RiskSeverity.BLOCKING
        return 30.0, [
            RiskItem(
                code="EDUCATION_REQUIREMENT_NOT_MET",
                severity=severity,
                explanation=f"简历学历层级 {actual} 低于岗位要求 {required}。",
                job_requirement=required,
                resume_evidence=actual,
                remediation="请确认岗位是否明确接受等效工作经验替代学历要求。",
            )
        ]

    def _qualification_score(
        self,
        structured_data: dict[str, Any],
        requirements: JobRequirements,
        profile: UserProfile | None,
    ) -> tuple[float, list[RiskItem]]:
        scores: list[float] = []
        risks: list[RiskItem] = []
        resume_languages = self._list_values(structured_data.get("languages"))
        if requirements.language_status is AvailabilityStatus.PROVIDED:
            if not resume_languages:
                scores.append(self.config.unknown_criterion_credit * 100)
                risks.append(
                    self._unknown_risk(
                        "LANGUAGE_CAPABILITY_UNKNOWN",
                        ", ".join(requirements.languages),
                        "请在简历中补充并确认语言能力。",
                    )
                )
            else:
                language_matches = [
                    self._contains_equivalent(resume_languages, language)
                    for language in requirements.languages
                ]
                scores.append(sum(language_matches) / len(language_matches) * 100)
                if not all(language_matches):
                    severity = RiskSeverity.HIGH
                    if self.config.blocking_policy is not None:
                        if requirements.language_required_explicit:
                            severity = RiskSeverity.BLOCKING
                        elif requirements.language_preferred:
                            severity = RiskSeverity.MEDIUM
                    risks.append(
                        RiskItem(
                            code="LANGUAGE_REQUIREMENT_NOT_MET",
                            severity=severity,
                            explanation="未在简历中找到一项或多项岗位明确要求的语言能力。",
                            job_requirement=", ".join(requirements.languages),
                            resume_evidence=", ".join(resume_languages),
                            remediation="申请前请核验实际语言水平并补充相应证据。",
                        )
                    )

        if requirements.location_status is AvailabilityStatus.PROVIDED:
            candidate_location = self._candidate_location(structured_data, profile)
            if not candidate_location:
                scores.append(self.config.unknown_criterion_credit * 100)
                risks.append(
                    self._unknown_risk(
                        "LOCATION_COMPATIBILITY_UNKNOWN",
                        requirements.location,
                        "请设置当前所在地或期望工作地点。",
                    )
                )
            else:
                compatible = self._locations_compatible(
                    candidate_location,
                    requirements.location or "",
                )
                scores.append(100.0 if compatible else 50.0)
                if not compatible:
                    risks.append(
                        RiskItem(
                            code="LOCATION_MISMATCH",
                            severity=RiskSeverity.LOW,
                            explanation="简历或个人资料中的地点与岗位地点不一致。",
                            job_requirement=requirements.location,
                            resume_evidence=candidate_location,
                            remediation="请确认岗位是否支持远程办公，或本人是否接受搬迁。",
                        )
                    )

        if requirements.work_eligibility_status is AvailabilityStatus.PROVIDED:
            eligibility = self._preference_value(profile, "work_eligibility")
            if eligibility is None:
                scores.append(self.config.unknown_criterion_credit * 100)
                risks.append(
                    self._unknown_risk(
                        "WORK_ELIGIBILITY_UNKNOWN",
                        requirements.work_eligibility,
                        "请确认自己是否具备岗位所在地要求的工作授权。",
                    )
                )
            else:
                eligible = self._truthy_eligibility(eligibility)
                scores.append(100.0 if eligible else 0.0)
                if not eligible:
                    risks.append(
                        RiskItem(
                            code="WORK_ELIGIBILITY_BLOCKED",
                            severity=RiskSeverity.BLOCKING,
                            explanation=(
                                "已知任职资格与岗位明确要求存在冲突。"
                            ),
                            job_requirement=requirements.work_eligibility,
                            resume_evidence=str(eligibility),
                            remediation="除非雇主提供担保或任职资格发生变化，否则不建议申请。",
                        )
                    )
        return (round(sum(scores) / len(scores), 2) if scores else 100.0), risks

    def _preference_score(
        self,
        requirements: JobRequirements,
        profile: UserProfile | None,
    ) -> tuple[float, list[RiskItem]]:
        if profile is None:
            return 100.0, [self._preferences_not_set()]
        preferences = profile.preferences
        configured = False
        scores: list[float] = []
        preferred_locations = self._as_string_list(
            preferences.get("preferred_locations")
            or preferences.get("locations")
            or preferences.get("location")
        )
        if preferred_locations:
            configured = True
            if requirements.location:
                scores.append(
                    100.0
                    if any(
                        self._locations_compatible(value, requirements.location)
                        for value in preferred_locations
                    )
                    else 30.0
                )
        employment_types = self._as_string_list(
            preferences.get("employment_types") or preferences.get("employment_type")
        )
        if employment_types:
            configured = True
            if requirements.employment_type:
                scores.append(
                    100.0
                    if self._contains_equivalent(
                        employment_types,
                        requirements.employment_type,
                    )
                    else 30.0
                )
        target_roles = [
            *profile.target_roles,
            *self._as_string_list(preferences.get("target_roles")),
        ]
        if target_roles:
            configured = True
            scores.append(
                100.0 if self._contains_equivalent(target_roles, requirements.job_title) else 40.0
            )
        expected_salary = self._numeric_preference(
            preferences.get("salary_min")
            or preferences.get("expected_salary_min")
            or preferences.get("salary_expectation")
        )
        if expected_salary is not None:
            configured = True
            offered_salary = requirements.salary_max or requirements.salary_min
            if offered_salary is not None:
                scores.append(100.0 if offered_salary >= expected_salary else 30.0)
        preferred_industries = self._as_string_list(
            preferences.get("industries") or preferences.get("industry")
        )
        if preferred_industries:
            configured = True
            if requirements.industry:
                scores.append(
                    100.0
                    if self._contains_equivalent(
                        preferred_industries,
                        requirements.industry,
                    )
                    else 30.0
                )
        if not configured:
            return 100.0, [self._preferences_not_set()]
        if not scores:
            return 100.0, []
        score = round(sum(scores) / len(scores), 2)
        risks = []
        if score < 100:
            risks.append(
                RiskItem(
                    code="USER_PREFERENCE_MISMATCH",
                    severity=RiskSeverity.LOW,
                    explanation="该岗位与一项或多项已设置的求职偏好不一致。",
                    job_requirement=(
                        f"{requirements.location or '地点未知'}；"
                        f"{requirements.employment_type or '工作类型未知'}"
                    ),
                    resume_evidence=str(preferences),
                    remediation="请确认相关求职偏好是否可以调整。",
                )
            )
        return score, risks

    def _other_conditions_score(
        self,
        structured_data: dict[str, Any],
        requirements: JobRequirements,
    ) -> tuple[float, list[RiskItem]]:
        if requirements.certificate_status is AvailabilityStatus.NOT_PROVIDED:
            return 100.0, []
        resume_certificates = self._list_values(structured_data.get("certificates"))
        if not resume_certificates:
            if (
                requirements.certificates_required
                or (
                    self.config.blocking_policy is not None
                    and requirements.certificate_required_explicit
                )
                or (
                    self.config.blocking_policy is not None
                    and requirements.certificate_preferred
                    and "certificates" in structured_data
                )
            ):
                severity = RiskSeverity.HIGH
                if self.config.blocking_policy is not None:
                    if requirements.certificate_required_explicit:
                        severity = RiskSeverity.BLOCKING
                    elif requirements.certificate_preferred:
                        severity = RiskSeverity.MEDIUM
                score = (
                    0.0
                    if requirements.certificates_required
                    else self.config.unknown_criterion_credit * 100
                )
                return score, [
                    RiskItem(
                        code="CERTIFICATE_REQUIREMENT_NOT_MET",
                        severity=severity,
                        explanation="未找到岗位所需证书的已确认证据。",
                        job_requirement=", ".join(requirements.certificates),
                        resume_evidence="未找到已确认的证书证据",
                        remediation="申请前请确认该证书是否为强制要求。",
                    )
                ]
            return self.config.unknown_criterion_credit * 100, [
                self._unknown_risk(
                    "CERTIFICATE_STATUS_UNKNOWN",
                    ", ".join(requirements.certificates),
                    "请确认是否持有岗位要求的证书。",
                )
            ]
        matches = [
            self._contains_equivalent(resume_certificates, certificate)
            for certificate in requirements.certificates
        ]
        if all(matches):
            return 100.0, []
        severity = RiskSeverity.HIGH
        if self.config.blocking_policy is not None:
            if requirements.certificate_required_explicit:
                severity = RiskSeverity.BLOCKING
            elif requirements.certificate_preferred:
                severity = RiskSeverity.MEDIUM
        return round(sum(matches) / len(matches) * 100, 2), [
            RiskItem(
                code="CERTIFICATE_REQUIREMENT_NOT_MET",
                severity=severity,
                explanation="简历中未找到一项或多项岗位指定的证书。",
                job_requirement=", ".join(requirements.certificates),
                resume_evidence=", ".join(resume_certificates),
                remediation="申请前请确认该证书是否为强制要求。",
            )
        ]

    def _evidence_trace(
        self,
        resume_version_id: int,
        skill: ResumeSkill,
        conclusion_key: str,
        job_field: str,
        job_snippet: str,
        matching_rule: str,
    ) -> EvidenceTrace:
        try:
            location = json.loads(skill.source_location)
        except (json.JSONDecodeError, TypeError):
            location = {}
        return EvidenceTrace(
            conclusion_key=conclusion_key,
            resume_version_id=resume_version_id,
            resume_skill_id=skill.id,
            resume_evidence=skill.evidence_text,
            resume_section=skill.evidence_section,
            source_type=self._optional_string(location.get("source_type")),
            page_number=self._optional_int(location.get("page_number")),
            paragraph_index=self._optional_int(location.get("paragraph_index")),
            source_location=skill.evidence_source_id,
            job_field=job_field,
            job_snippet=job_snippet,
            matching_rule=matching_rule,
            confidence=skill.confidence,
        )

    @staticmethod
    def _dimension(
        code: str,
        label: str,
        score: float,
        weight: int,
        explanation: str,
        *,
        evidence_keys: list[str] | None = None,
        gap_codes: list[str] | None = None,
    ) -> DimensionScore:
        status = (
            DimensionStatus.GOOD
            if score >= 80
            else DimensionStatus.PARTIAL
            if score >= 50
            else DimensionStatus.WEAK
        )
        return DimensionScore(
            code=code,
            label=label,
            score=round(score, 2),
            weight=weight,
            weighted_score=round(score * weight / 100, 2),
            explanation=explanation,
            status=status,
            evidence_keys=evidence_keys or [],
            gap_codes=gap_codes or [],
        )

    @staticmethod
    def _classify_risk(risk: RiskItem, requirements: JobRequirements) -> RiskItem:
        title = DeterministicMatchEngine._risk_title(risk.code)
        if risk.code.startswith("REQUIRED_SKILL_"):
            return risk.model_copy(
                update={
                    "title": title,
                    "risk_type": RiskType.SKILL_GAP,
                    "verification_status": VerificationStatus.UNVERIFIED,
                }
            )
        if risk.severity is RiskSeverity.BLOCKING:
            return risk.model_copy(
                update={
                    "title": title,
                    "risk_type": RiskType.BLOCKING_RISK,
                    "verification_status": VerificationStatus.CONFLICT,
                }
            )
        mandatory_unknown = {
            "EXPERIENCE_UNKNOWN": requirements.experience_required_explicit,
            "EDUCATION_UNKNOWN": requirements.education_required_explicit,
            "LANGUAGE_CAPABILITY_UNKNOWN": requirements.language_required_explicit,
            "WORK_ELIGIBILITY_UNKNOWN": (
                requirements.work_eligibility_status is AvailabilityStatus.PROVIDED
            ),
            "CERTIFICATE_STATUS_UNKNOWN": requirements.certificate_required_explicit,
        }
        if mandatory_unknown.get(risk.code, False):
            return risk.model_copy(
                update={
                    "title": title,
                    "risk_type": RiskType.BLOCKING_RISK,
                    "verification_status": VerificationStatus.UNVERIFIED,
                }
            )
        verification = (
            VerificationStatus.UNVERIFIED
            if "UNKNOWN" in risk.code
            or risk.code in {"JOB_REQUIREMENTS_INCOMPLETE", "PREFERENCES_NOT_SET"}
            else VerificationStatus.CONFLICT
        )
        return risk.model_copy(
            update={"title": title, "verification_status": verification}
        )

    @staticmethod
    def _risk_title(code: str) -> str:
        if code.startswith("REQUIRED_SKILL_"):
            status = code.removeprefix("REQUIRED_SKILL_")
            return {
                "MISSING": "必需技能缺失",
                "PARTIAL": "必需技能证据不完整",
                "UNKNOWN": "必需技能待确认",
            }.get(status, "必需技能风险")
        return RISK_TITLE_LABELS.get(code, code.replace("_", " "))

    @staticmethod
    def _recommendation(
        rule_score: float,
        risks: list[RiskItem],
    ) -> RecommendationLevel:
        max_severity = max(
            (SEVERITY_ORDER[item.severity] for item in risks),
            default=0,
        )
        if max_severity >= SEVERITY_ORDER[RiskSeverity.BLOCKING]:
            return RecommendationLevel.NOT_RECOMMENDED
        if max_severity >= SEVERITY_ORDER[RiskSeverity.HIGH]:
            return RecommendationLevel.HIGH_RISK
        if rule_score >= 85:
            return RecommendationLevel.STRONGLY_RECOMMENDED
        if rule_score >= 70:
            return RecommendationLevel.RECOMMENDED
        if rule_score >= 55:
            return RecommendationLevel.CONSIDER
        if rule_score >= 40:
            return RecommendationLevel.HIGH_RISK
        return RecommendationLevel.NOT_RECOMMENDED

    @staticmethod
    def _apply_recommendation_cap(
        recommendation: RecommendationLevel,
        cap: RecommendationLevel,
    ) -> RecommendationLevel:
        if RECOMMENDATION_ORDER[recommendation] < RECOMMENDATION_ORDER[cap]:
            return cap
        return recommendation

    @staticmethod
    def _actions(risks: list[RiskItem]) -> list[RecommendedAction]:
        actions: list[RecommendedAction] = []
        seen: set[str] = set()
        for risk in sorted(
            risks,
            key=lambda item: (-SEVERITY_ORDER[item.severity], item.code),
        ):
            if risk.severity in {RiskSeverity.INFO, RiskSeverity.LOW} or risk.code in seen:
                continue
            seen.add(risk.code)
            actions.append(
                RecommendedAction(
                    code=risk.code,
                    title=risk.title,
                    explanation=risk.remediation,
                    priority=risk.severity,
                )
            )
        return actions[:8]

    @staticmethod
    def _experience_years(
        structured_data: dict[str, Any],
        anchor: datetime,
    ) -> float | None:
        entries = structured_data.get("work_experience")
        if not isinstance(entries, list):
            return None
        intervals: list[tuple[int, int]] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            start = DeterministicMatchEngine._parse_month(
                DeterministicMatchEngine._field_value(item.get("start_date")),
                anchor,
                is_end=False,
            )
            end = DeterministicMatchEngine._parse_month(
                DeterministicMatchEngine._field_value(item.get("end_date")),
                anchor,
                is_end=True,
            )
            if start is not None and end is not None and end >= start:
                intervals.append((start, end))
        if not intervals:
            return None
        merged: list[list[int]] = []
        for start, end in sorted(intervals):
            if not merged or start > merged[-1][1] + 1:
                merged.append([start, end])
            else:
                merged[-1][1] = max(merged[-1][1], end)
        months = sum(end - start + 1 for start, end in merged)
        return round(months / 12, 2)

    @staticmethod
    def _parse_month(value: str, anchor: datetime, *, is_end: bool) -> int | None:
        normalized = value.casefold().strip()
        if is_end and normalized in {"present", "current", "now", "至今", "现在"}:
            return anchor.year * 12 + anchor.month
        match = re.search(r"((?:19|20)\d{2})(?:[-/.年](\d{1,2}))?", value)
        if not match:
            return None
        year = int(match.group(1))
        month = int(match.group(2) or (12 if is_end else 1))
        if not 1 <= month <= 12:
            return None
        return year * 12 + month

    @staticmethod
    def _education_level(structured_data: dict[str, Any]) -> str | None:
        entries = structured_data.get("education")
        if not isinstance(entries, list):
            return None
        best: str | None = None
        for item in entries:
            if not isinstance(item, dict):
                continue
            degree = DeterministicMatchEngine._field_value(item.get("degree")).casefold()
            for level, markers in (
                ("DOCTORATE", ("doctorate", "doctoral", "phd", "博士")),
                ("MASTER", ("master", "硕士", "研究生")),
                ("BACHELOR", ("bachelor", "本科", "学士")),
                ("ASSOCIATE", ("associate", "大专", "专科")),
                ("HIGH_SCHOOL", ("high school", "高中")),
            ):
                if any(marker in degree for marker in markers) and (
                    best is None or EDUCATION_RANK[level] > EDUCATION_RANK[best]
                ):
                    best = level
        return best

    @staticmethod
    def _field_value(value: Any) -> str:
        if isinstance(value, dict):
            nested = value.get("value")
            return str(nested).strip() if nested is not None else ""
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _list_values(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [
            field_value
            for item in value
            if (field_value := DeterministicMatchEngine._field_value(item))
        ]

    @staticmethod
    def _candidate_location(
        structured_data: dict[str, Any],
        profile: UserProfile | None,
    ) -> str | None:
        if profile is not None and profile.location:
            return profile.location
        basic_info = structured_data.get("basic_info")
        if isinstance(basic_info, dict):
            location = DeterministicMatchEngine._field_value(basic_info.get("location"))
            return location or None
        return None

    @staticmethod
    def _locations_compatible(candidate: str, job: str) -> bool:
        candidate_key = candidate.casefold().strip()
        job_key = job.casefold().strip()
        remote_markers = ("remote", "远程", "不限地点")
        if any(marker in job_key for marker in remote_markers):
            return True
        return candidate_key in job_key or job_key in candidate_key

    @staticmethod
    def _contains_equivalent(values: list[str], target: str) -> bool:
        target_key = target.casefold().strip()
        return any(
            target_key in value.casefold() or value.casefold() in target_key for value in values
        )

    @staticmethod
    def _as_string_list(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @staticmethod
    def _preference_value(profile: UserProfile | None, key: str) -> Any:
        return profile.preferences.get(key) if profile is not None else None

    @staticmethod
    def _numeric_preference(value: Any) -> float | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _truthy_eligibility(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).casefold().strip() in {
            "true",
            "yes",
            "eligible",
            "authorized",
            "有",
            "是",
            "已授权",
        }

    @staticmethod
    def _unknown_risk(
        code: str,
        requirement: str | None,
        remediation: str,
    ) -> RiskItem:
        return RiskItem(
            code=code,
            severity=RiskSeverity.INFO,
            explanation="候选人信息未知，当前不能据此认定为不满足要求。",
            job_requirement=requirement,
            resume_evidence=None,
            remediation=remediation,
        )

    @staticmethod
    def _preferences_not_set() -> RiskItem:
        return RiskItem(
            code="PREFERENCES_NOT_SET",
            severity=RiskSeverity.INFO,
            explanation="尚未设置匹配偏好，因此该项不扣分。",
            job_requirement=None,
            resume_evidence=None,
            remediation="可设置求职偏好，以便后续获得更贴合的比较结果。",
        )

    @staticmethod
    def _token_overlap(left: str | None, right: str | None) -> bool:
        if not left or not right:
            return False
        pattern = r"[A-Za-z0-9+#.]{2,}|[\u4e00-\u9fff]{2,}"
        left_tokens = {item.casefold() for item in re.findall(pattern, left)}
        right_tokens = {item.casefold() for item in re.findall(pattern, right)}
        return bool(left_tokens & right_tokens)

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        return str(value) if isinstance(value, str) and value else None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return value if isinstance(value, int) else None
