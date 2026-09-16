from __future__ import annotations

import json
from datetime import UTC, datetime
from time import perf_counter

from app.matching.config import CANDIDATE_SCORING_CONFIG, DEFAULT_SCORING_CONFIG
from app.matching.normalization import SkillNormalizationService
from app.matching.policy import (
    JobInformationAssessor,
    confidence_for,
    count_unknown_requirements,
)
from app.matching.requirements import JobRequirementExtractor
from app.matching.scoring import DeterministicMatchEngine
from app.models.jobs import Job, JobSkill
from app.models.resumes import ResumeSkill, ResumeVersion, Skill
from app.models.users import UserProfile
from app.schemas.matching import (
    RiskSeverity,
    SkillMatchStatus,
)
from evaluation.matching.schemas import (
    CaseResult,
    EvaluationLabel,
    JobFixture,
    ResumeFixture,
)

ANCHOR = datetime(2026, 1, 1, tzinfo=UTC)


class EvaluationExecutor:
    """Build synthetic ORM inputs and invoke the released deterministic services."""

    def __init__(self, resumes: list[ResumeFixture], jobs: list[JobFixture]) -> None:
        self.resumes = {item.fixture_id: item for item in resumes}
        self.jobs = {item.fixture_id: item for item in jobs}

    def run_case(
        self,
        label: EvaluationLabel,
        *,
        scoring_version: str = "deterministic-v1",
    ) -> CaseResult:
        if scoring_version not in {"deterministic-v1", "deterministic-v1.1"}:
            raise ValueError(f"unsupported scoring version: {scoring_version}")
        resume, profile = self._resume(self.resumes[label.resume_fixture], label.case_id)
        job = self._job(self.jobs[label.job_fixture], label.case_id)
        normalizer = SkillNormalizationService()
        config = (
            DEFAULT_SCORING_CONFIG
            if scoring_version == "deterministic-v1"
            else CANDIDATE_SCORING_CONFIG
        )
        started = perf_counter()
        requirements = JobRequirementExtractor(
            normalizer,
            config.blocking_policy,
        ).extract(job)
        assessment = JobInformationAssessor.assess(job, requirements)
        computation = DeterministicMatchEngine(normalizer, config).calculate(
            resume,
            requirements,
            profile,
            assessment if config.blocking_policy is not None else None,
        )
        duration_ms = (perf_counter() - started) * 1000

        unknown_count = count_unknown_requirements(
            sum(item.status is SkillMatchStatus.UNKNOWN for item in computation.skill_matches),
            (item.code for item in computation.risks),
            assessment,
        )
        evidence_complete = sum(self._trace_complete(item) for item in computation.evidence_items)
        required = [
            item
            for item in computation.skill_matches
            if item.requirement_type == "REQUIRED" and item.status is SkillMatchStatus.MATCHED
        ]
        required_complete = sum(
            any(
                trace.conclusion_key.casefold() == item.normalized_name.casefold()
                and self._trace_complete(trace)
                for trace in computation.evidence_items
            )
            for item in required
        )
        blocking = [item for item in computation.risks if item.severity is RiskSeverity.BLOCKING]
        blocking_complete = sum(
            bool(item.job_requirement and item.resume_evidence) for item in blocking
        )
        policy = CANDIDATE_SCORING_CONFIG.blocking_policy
        assert policy is not None
        confidence_level, confidence_score = confidence_for(
            assessment.job_information_completeness,
            unknown_count,
            assessment.evaluated_requirement_count,
            policy,
        )
        if computation.report_confidence is not None:
            confidence_level = computation.report_confidence
            confidence_score = computation.report_confidence_score or 0

        return CaseResult(
            case_id=label.case_id,
            category=label.category,
            scoring_version=scoring_version,
            rule_score=computation.rule_score,
            recommendation=computation.recommendation,
            skill_statuses={
                item.normalized_name: item.status for item in computation.skill_matches
            },
            risks={item.code: item.severity.value for item in computation.risks},
            evidence_complete=evidence_complete,
            evidence_total=len(computation.evidence_items),
            required_skill_evidence_complete=required_complete,
            required_skill_evidence_total=len(required),
            blocking_evidence_complete=blocking_complete,
            blocking_evidence_total=len(blocking),
            not_provided_count=assessment.not_provided_requirement_count,
            unknown_count=unknown_count,
            job_information_completeness=assessment.job_information_completeness,
            report_confidence=confidence_score,
            report_confidence_level=confidence_level,
            recommendation_cap=computation.recommendation_cap,
            policy_version=computation.policy_version,
            information_statuses=assessment.statuses,
            duration_ms=round(duration_ms, 4),
            dimension_scores={item.code: item.score for item in computation.dimension_scores},
            weighted_score_sum=round(
                sum(item.weighted_score for item in computation.dimension_scores),
                2,
            ),
            evidence_signature=[
                "|".join(
                    (
                        item.conclusion_key,
                        str(item.resume_skill_id or ""),
                        item.source_location or "",
                        item.job_field,
                        item.matching_rule,
                    )
                )
                for item in computation.evidence_items
            ],
            config_snapshot=config.model_dump(mode="json"),
            expected_order_group=label.expected_order_group,
            expected_order_rank=label.expected_order_rank,
        )

    @staticmethod
    def _trace_complete(item: object) -> bool:
        trace = item
        return bool(
            getattr(trace, "resume_version_id", 0)
            and getattr(trace, "job_field", "")
            and getattr(trace, "job_snippet", "")
            and getattr(trace, "matching_rule", "")
            and (
                not getattr(trace, "resume_evidence", None)
                or (
                    getattr(trace, "resume_skill_id", None)
                    and getattr(trace, "source_location", None)
                    and (
                        getattr(trace, "page_number", None) is not None
                        or getattr(trace, "paragraph_index", None) is not None
                    )
                )
            )
        )

    @staticmethod
    def _resume(fixture: ResumeFixture, case_id: str) -> tuple[ResumeVersion, UserProfile]:
        version = ResumeVersion(
            id=int(case_id[1:]) + 100,
            resume_id=int(case_id[1:]) + 100,
            version_number=1,
            raw_text="Anonymous synthetic evaluation resume.",
            structured_data=EvaluationExecutor._structured_resume(fixture),
            is_current=True,
            is_confirmed=True,
            created_at=ANCHOR,
            updated_at=ANCHOR,
        )
        skill_id = int(case_id[1:]) * 100
        for name in [*fixture.skills, *fixture.unconfirmed_skills]:
            copies = max(fixture.duplicate_evidence.get(name, 1), 1)
            for copy_index in range(copies):
                skill_id += 1
                confirmed = name not in fixture.unconfirmed_skills
                skill = Skill(id=skill_id, name=name, category="TECHNICAL")
                version.skills.append(
                    ResumeSkill(
                        id=skill_id,
                        resume_version_id=version.id,
                        skill_id=skill_id,
                        raw_name=name,
                        confidence=0.95,
                        evidence_text=(
                            f"Delivered a production project using {name}." if confirmed else ""
                        ),
                        evidence_section="work_experience",
                        evidence_source_id=f"page-1-block-{copy_index}",
                        source_location=json.dumps(
                            {
                                "source_type": "page",
                                "page_number": 1,
                                "block_index": copy_index,
                            }
                        ),
                        is_user_confirmed=confirmed,
                        skill=skill,
                    )
                )
        profile = UserProfile(
            user_id=int(case_id[1:]) + 100,
            display_name="Anonymous Evaluation Candidate",
            location=fixture.location,
            target_roles=fixture.target_roles,
            preferences=fixture.preferences,
        )
        return version, profile

    @staticmethod
    def _job(fixture: JobFixture, case_id: str) -> Job:
        job = Job(
            id=int(case_id[1:]) + 100,
            title=fixture.title,
            company="Synthetic Evaluation Company",
            location=fixture.location,
            description=fixture.description,
            requirements=fixture.requirements,
            responsibilities=fixture.responsibilities,
            experience_level=fixture.experience_level,
            education_requirement=fixture.education_requirement,
            language_requirements=fixture.languages,
            employment_type=fixture.employment_type,
            content_hash=(case_id.casefold()[0] * 64),
            raw_data={"industry": fixture.industry} if fixture.industry else {},
            status="ACTIVE",
        )
        for index, item in enumerate(fixture.skills, start=1):
            skill = Skill(id=int(case_id[1:]) * 100 + index, name=item.name, category="TECHNICAL")
            job.skills.append(
                JobSkill(
                    id=int(case_id[1:]) * 100 + index,
                    skill=skill,
                    skill_id=skill.id,
                    is_required=item.required,
                    weight=2 if item.required else 1,
                    evidence_text=(
                        f"{'Required' if item.required else 'Preferred'} skill: {item.name}"
                    ),
                )
            )
        return job

    @staticmethod
    def _structured_resume(fixture: ResumeFixture) -> dict[str, object]:
        def field(value: str) -> dict[str, object]:
            return {
                "value": value,
                "confidence": 1,
                "evidence_text": value,
                "source_location": {"source_type": "page", "page_number": 1},
                "needs_confirmation": False,
            }

        work: list[dict[str, object]] = []
        if fixture.experience_years is not None:
            start_year = 2026 - fixture.experience_years
            work.append(
                {
                    "company": field("Synthetic Labs"),
                    "title": field("Software Engineer"),
                    "start_date": field(f"{start_year}-01"),
                    "end_date": field("2025-12"),
                    "description": field("Delivered synthetic project outcomes."),
                }
            )
        return {
            "basic_info": {"location": field(fixture.location)},
            "education": [{"degree": field(fixture.degree)}],
            "work_experience": work,
            "project_experience": [],
            "technical_skills": [],
            "soft_skills": [],
            "languages": [field(item) for item in fixture.languages],
            "certificates": [field(item) for item in fixture.certificates],
            "awards": [],
            "summary": field("Anonymous synthetic evaluation profile."),
        }
