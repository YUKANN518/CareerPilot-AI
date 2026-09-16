from __future__ import annotations

from collections.abc import Iterable

from app.models.jobs import Job
from app.schemas.matching import (
    BlockingPolicyConfig,
    JobInformationAssessment,
    JobRequirements,
    RecommendationLevel,
    ReportConfidence,
    RequirementInformationStatus,
)

REQUIREMENT_KEYS = (
    "required_skills",
    "preferred_skills",
    "experience_requirement",
    "education_requirement",
    "language_requirements",
    "location_requirement",
    "work_eligibility",
    "certificates",
    "responsibilities",
    "employment_type",
)
UNKNOWN_RISK_CRITERIA = {
    "EXPERIENCE_UNKNOWN": "experience_requirement",
    "EDUCATION_UNKNOWN": "education_requirement",
    "LANGUAGE_CAPABILITY_UNKNOWN": "language_requirements",
    "LOCATION_COMPATIBILITY_UNKNOWN": "location_requirement",
    "WORK_ELIGIBILITY_UNKNOWN": "work_eligibility",
    "CERTIFICATE_STATUS_UNKNOWN": "certificates",
}

NO_REQUIREMENT_MARKERS = {
    "required_skills": (
        "no technical skills required",
        "no specific skills required",
        "无需特定技能",
    ),
    "experience_requirement": (
        "no experience required",
        "experience not required",
        "经验不限",
        "无需经验",
    ),
    "education_requirement": (
        "no degree required",
        "degree not required",
        "学历不限",
        "不限学历",
    ),
    "language_requirements": (
        "no language requirement",
        "language not required",
        "语言不限",
    ),
    "location_requirement": (
        "location flexible",
        "no location requirement",
        "地点不限",
    ),
    "work_eligibility": (
        "no work authorization required",
        "sponsorship available",
        "提供签证担保",
        "无需工作许可",
    ),
    "certificates": (
        "no certification required",
        "certificate not required",
        "无需证书",
        "证书不限",
    ),
    "responsibilities": (
        "no defined responsibilities",
        "职责不限",
    ),
    "employment_type": (
        "employment type flexible",
        "用工形式不限",
    ),
    "preferred_skills": (
        "no preferred skills",
        "无优先技能",
    ),
}


class JobInformationAssessor:
    """Classify ten job criteria without equating absence with failure."""

    @staticmethod
    def assess(job: Job, requirements: JobRequirements) -> JobInformationAssessment:
        text = "\n".join(
            value for value in (job.requirements, job.description, job.responsibilities) if value
        ).casefold()
        required_skills = [item for item in requirements.skills if item.required]
        preferred_skills = [item for item in requirements.skills if not item.required]
        statuses = {
            "required_skills": JobInformationAssessor._value_status(
                bool(required_skills),
                text,
                "required_skills",
            ),
            "preferred_skills": JobInformationAssessor._value_status(
                bool(preferred_skills),
                text,
                "preferred_skills",
            ),
            "experience_requirement": JobInformationAssessor._parsed_status(
                requirements.minimum_experience_years is not None,
                bool(job.experience_level),
                text,
                "experience_requirement",
            ),
            "education_requirement": JobInformationAssessor._parsed_status(
                requirements.education_level is not None,
                bool(job.education_requirement),
                text,
                "education_requirement",
            ),
            "language_requirements": JobInformationAssessor._value_status(
                bool(requirements.languages),
                text,
                "language_requirements",
            ),
            "location_requirement": JobInformationAssessor._value_status(
                bool(requirements.location),
                text,
                "location_requirement",
            ),
            "work_eligibility": JobInformationAssessor._value_status(
                bool(requirements.work_eligibility),
                text,
                "work_eligibility",
            ),
            "certificates": JobInformationAssessor._value_status(
                bool(requirements.certificates),
                text,
                "certificates",
            ),
            "responsibilities": JobInformationAssessor._value_status(
                bool(job.responsibilities and job.responsibilities.strip()),
                text,
                "responsibilities",
            ),
            "employment_type": JobInformationAssessor._value_status(
                bool(requirements.employment_type),
                text,
                "employment_type",
            ),
        }
        provided = {
            RequirementInformationStatus.PROVIDED,
            RequirementInformationStatus.NOT_REQUIRED,
        }
        score = sum(
            1
            if status in provided
            else 0.25
            if status is RequirementInformationStatus.UNPARSEABLE
            else 0
            for status in statuses.values()
        )
        return JobInformationAssessment(
            statuses=statuses,
            job_information_completeness=round(score / len(REQUIREMENT_KEYS), 4),
            evaluated_requirement_count=sum(status in provided for status in statuses.values()),
            not_provided_requirement_count=sum(
                status is RequirementInformationStatus.NOT_PROVIDED for status in statuses.values()
            ),
            unparseable_requirement_count=sum(
                status is RequirementInformationStatus.UNPARSEABLE for status in statuses.values()
            ),
        )

    @staticmethod
    def _value_status(
        has_value: bool,
        text: str,
        criterion: str,
    ) -> RequirementInformationStatus:
        if any(marker in text for marker in NO_REQUIREMENT_MARKERS.get(criterion, ())):
            return RequirementInformationStatus.NOT_REQUIRED
        if has_value:
            return RequirementInformationStatus.PROVIDED
        return RequirementInformationStatus.NOT_PROVIDED

    @staticmethod
    def _parsed_status(
        parsed: bool,
        configured: bool,
        text: str,
        criterion: str,
    ) -> RequirementInformationStatus:
        if any(marker in text for marker in NO_REQUIREMENT_MARKERS.get(criterion, ())):
            return RequirementInformationStatus.NOT_REQUIRED
        if parsed:
            return RequirementInformationStatus.PROVIDED
        if configured:
            return RequirementInformationStatus.UNPARSEABLE
        return RequirementInformationStatus.NOT_PROVIDED


def confidence_for(
    completeness: float,
    unknown_count: int,
    evaluated_count: int,
    policy: BlockingPolicyConfig,
) -> tuple[ReportConfidence, float]:
    unknown_ratio = unknown_count / evaluated_count if evaluated_count else 0
    score = round(completeness * (1 - min(unknown_ratio, 1) * 0.25), 4)
    thresholds = policy.confidence_thresholds
    if completeness < policy.completeness_thresholds.consider_cap_min:
        return ReportConfidence.VERY_LOW, score
    if score >= thresholds.high_min:
        return ReportConfidence.HIGH, score
    if score >= thresholds.medium_min:
        return ReportConfidence.MEDIUM, score
    if score >= thresholds.low_min:
        return ReportConfidence.LOW, score
    return ReportConfidence.VERY_LOW, score


def recommendation_cap_for(
    completeness: float,
    policy: BlockingPolicyConfig,
) -> RecommendationLevel | None:
    thresholds = policy.completeness_thresholds
    if completeness >= thresholds.unrestricted_min:
        return None
    if completeness >= thresholds.recommended_cap_min:
        return RecommendationLevel.RECOMMENDED
    return RecommendationLevel.CONSIDER


def count_unknown_requirements(
    skill_unknown_count: int,
    risk_codes: Iterable[str],
    assessment: JobInformationAssessment,
) -> int:
    count = skill_unknown_count
    for code in risk_codes:
        criterion = UNKNOWN_RISK_CRITERIA.get(code)
        if criterion is None:
            continue
        if assessment.statuses.get(criterion) is RequirementInformationStatus.PROVIDED:
            count += 1
    return count
