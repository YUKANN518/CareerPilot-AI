from __future__ import annotations

from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import AppError
from app.matching.config import scoring_config_for
from app.matching.normalization import SkillNormalizationService
from app.matching.policy import JobInformationAssessor
from app.matching.requirements import JobRequirementExtractor
from app.matching.scoring import DeterministicMatchEngine, recommendation_for_score
from app.models.enums import RequirementStatus, TaskStatus
from app.models.jobs import Job
from app.models.matching import MatchDetail, MatchEvidence, MatchReport
from app.models.operations import AuditLog
from app.models.resumes import ResumeVersion
from app.models.users import User
from app.repositories.matching import MatchRepository
from app.schemas.matching import (
    DimensionScore,
    EvidenceCoverage,
    EvidenceTrace,
    JobInformationAssessment,
    JobRequirements,
    MatchComputation,
    MatchCreate,
    MatchCreateResult,
    MatchDetailRead,
    MatchEvidenceRead,
    MatchInputSnapshot,
    MatchListRead,
    MatchPhase,
    MatchReportRead,
    MatchStatus,
    MatchStatusRead,
    RecommendationLevel,
    RecommendedAction,
    RiskItem,
    ScoringConfig,
    SemanticEvidence,
    SemanticSummary,
    SkillMatch,
    SkillMatchStatus,
)
from app.semantic.embeddings import EmbeddingProvider, embedding_provider_from_settings
from app.semantic.index import SemanticIndexService
from app.semantic.matching import SemanticMatchingService, SemanticMatchResult


class MatchService:
    def __init__(
        self,
        session: Session,
        config: ScoringConfig | None = None,
        *,
        settings: Settings | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        semantic_index: SemanticIndexService | None = None,
    ) -> None:
        self.session = session
        self.repository = MatchRepository(session)
        self.settings = settings or get_settings()
        self._configured_scoring = config
        self._embedding_provider = embedding_provider
        self._semantic_index = semantic_index
        self.config = config or scoring_config_for(self.settings.default_scoring_version)

    def create(
        self,
        user: User,
        payload: MatchCreate,
        *,
        force: bool = False,
    ) -> MatchCreateResult:
        self.config = self._select_config(payload.scoring_version)
        config_snapshot = self.config.model_dump(mode="json")
        resume_version, job = self._load_inputs(user, payload)
        inputs_matchable = resume_version.is_confirmed and job.status == "ACTIVE"
        if inputs_matchable and not force:
            existing = self.repository.find_successful(
                user_id=user.id,
                resume_version_id=resume_version.id,
                job_id=job.id,
                scoring_version=self.config.version,
                scoring_config_snapshot=config_snapshot,
            )
            if existing is not None:
                return MatchCreateResult(report=self._report_read(existing), reused=True)

        report = MatchReport(
            user_id=user.id,
            resume_version_id=resume_version.id,
            job_id=job.id,
            status=TaskStatus.PENDING,
            scoring_version=self.config.version,
            scoring_config_snapshot=config_snapshot,
            current_phase=MatchPhase.VALIDATING_INPUT.value,
            started_at=datetime.now(UTC),
        )
        self.session.add(report)
        self.session.flush()
        self._audit(user.id, "MATCH_CREATED", report.id, payload.model_dump())
        self.session.commit()

        try:
            self._validate_matchable_inputs(resume_version, job)
            self._run(report, resume_version, job, user)
        except AppError as exc:
            self._mark_failed(report, exc.code, exc.message)
            raise
        except Exception as exc:
            self._mark_failed(
                report,
                "MATCH_CALCULATION_FAILED",
                "The match could not be calculated",
            )
            raise AppError(
                "MATCH_CALCULATION_FAILED",
                "The match could not be calculated",
                500,
            ) from exc
        return MatchCreateResult(report=self._report_read(report), reused=False)

    def recalculate(self, user: User, report_id: int) -> MatchCreateResult:
        report = self._owned_report(report_id, user.id)
        return self.create(
            user,
            MatchCreate(
                resume_version_id=report.resume_version_id,
                job_id=report.job_id,
                scoring_version=report.scoring_version,
            ),
            force=True,
        )

    def list_reports(
        self,
        user: User,
        *,
        resume_version_id: int | None,
        job_id: int | None,
        offset: int,
        limit: int,
    ) -> MatchListRead:
        reports, total = self.repository.list_owned(
            user_id=user.id,
            resume_version_id=resume_version_id,
            job_id=job_id,
            offset=offset,
            limit=limit,
        )
        return MatchListRead(
            items=[self._report_read(report) for report in reports],
            total=total,
            offset=offset,
            limit=limit,
        )

    def get(self, user: User, report_id: int) -> MatchReportRead:
        return self._report_read(self._owned_report(report_id, user.id))

    def job_history(
        self,
        user: User,
        job_id: int,
        *,
        offset: int,
        limit: int,
    ) -> MatchListRead:
        if self.repository.get_visible_job(job_id, user.id) is None:
            raise AppError("JOB_NOT_FOUND", "The job was not found", 404)
        return self.list_reports(
            user,
            resume_version_id=None,
            job_id=job_id,
            offset=offset,
            limit=limit,
        )

    def resume_history(
        self,
        user: User,
        version_id: int,
        *,
        offset: int,
        limit: int,
    ) -> MatchListRead:
        if self.repository.get_resume_version_for_owner(version_id, user.id) is None:
            raise AppError(
                "RESUME_VERSION_NOT_FOUND",
                "The confirmed resume version was not found",
                404,
            )
        return self.list_reports(
            user,
            resume_version_id=version_id,
            job_id=None,
            offset=offset,
            limit=limit,
        )

    def details(self, user: User, report_id: int) -> list[MatchDetailRead]:
        report = self._owned_report(report_id, user.id)
        return [self._detail_read(detail) for detail in report.details]

    def status(self, user: User, report_id: int) -> MatchStatusRead:
        report = self._owned_report(report_id, user.id)
        return MatchStatusRead(
            id=report.id,
            status=self._api_status(report.status),
            current_phase=MatchPhase(report.current_phase),
            phase_timings_ms=report.phase_timings,
            duration_ms=report.duration_ms,
            error_code=report.error_code,
            error_message=report.error_message,
        )

    def _load_inputs(
        self,
        user: User,
        payload: MatchCreate,
    ) -> tuple[ResumeVersion, Job]:
        version = self.repository.get_resume_version_for_owner(
            payload.resume_version_id,
            user.id,
        )
        if version is None:
            raise AppError(
                "RESUME_VERSION_NOT_FOUND",
                "The confirmed resume version was not found",
                404,
            )
        job = self.repository.get_visible_job(payload.job_id, user.id)
        if job is None:
            raise AppError("JOB_NOT_FOUND", "The job was not found", 404)
        return version, job

    @staticmethod
    def _validate_matchable_inputs(version: ResumeVersion, job: Job) -> None:
        if not version.is_confirmed:
            raise AppError(
                "RESUME_VERSION_NOT_CONFIRMED",
                "Only a confirmed resume version can be matched",
                409,
            )
        if job.status != "ACTIVE":
            raise AppError(
                "JOB_NOT_AVAILABLE",
                "The job is not available for matching",
                409,
            )

    def workflow_compute_deterministic(
        self,
        user: User,
        payload: MatchCreate,
    ) -> dict[str, Any]:
        """Compute reusable rule artifacts without creating a report."""
        self.config = self._select_config(payload.scoring_version)
        version, job = self._load_inputs(user, payload)
        self._validate_matchable_inputs(version, job)
        normalizer = SkillNormalizationService(self.repository.skill_dictionary())
        requirements = JobRequirementExtractor(
            normalizer,
            self.config.blocking_policy,
        ).extract(job)
        assessment = (
            JobInformationAssessor.assess(job, requirements)
            if self.config.blocking_policy is not None
            else None
        )
        if not any(
            item.is_user_confirmed and item.evidence_text.strip() for item in version.skills
        ):
            raise AppError(
                "RESUME_SKILL_EVIDENCE_REQUIRED",
                "The resume version has no confirmed skill evidence",
                422,
            )
        computation = DeterministicMatchEngine(normalizer, self.config).calculate(
            version,
            requirements,
            user.profile,
            assessment,
        )
        return {
            "scoring_config": self.config.model_dump(mode="json"),
            "requirements": requirements.model_dump(mode="json"),
            "job_information": assessment.model_dump(mode="json") if assessment else None,
            "computation": computation.model_dump(mode="json"),
        }

    def workflow_validate_inputs(self, user: User, payload: MatchCreate) -> None:
        self.config = self._select_config(payload.scoring_version)
        version, job = self._load_inputs(user, payload)
        self._validate_matchable_inputs(version, job)

    def workflow_compute_semantic(
        self,
        user: User,
        payload: MatchCreate,
    ) -> dict[str, Any]:
        """Run the existing semantic service for a hybrid workflow node."""
        self.config = self._select_config(payload.scoring_version)
        version, job = self._load_inputs(user, payload)
        self._validate_matchable_inputs(version, job)
        semantic_config = self.config.semantic
        if semantic_config is None:
            raise AppError("HYBRID_CONFIG_INVALID", "Semantic configuration is missing", 500)
        result = SemanticMatchingService(self._index_service(), semantic_config).calculate(
            version,
            job,
            user.id,
        )
        return {
            "score": result.score,
            "evidence": [item.model_dump(mode="json") for item in result.evidence],
            "summary": result.summary.model_dump(mode="json"),
        }

    def create_from_workflow(
        self,
        user: User,
        payload: MatchCreate,
        artifacts: dict[str, Any],
    ) -> MatchCreateResult:
        """Persist precomputed LangGraph artifacts through the canonical report writer."""
        self.config = self._select_config(payload.scoring_version)
        config_snapshot = self.config.model_dump(mode="json")
        version, job = self._load_inputs(user, payload)
        self._validate_matchable_inputs(version, job)
        existing = self.repository.find_successful(
            user_id=user.id,
            resume_version_id=version.id,
            job_id=job.id,
            scoring_version=self.config.version,
            scoring_config_snapshot=config_snapshot,
        )
        if existing is not None:
            return MatchCreateResult(report=self._report_read(existing), reused=True)
        report = MatchReport(
            user_id=user.id,
            resume_version_id=version.id,
            job_id=job.id,
            status=TaskStatus.PENDING,
            scoring_version=self.config.version,
            scoring_config_snapshot=config_snapshot,
            current_phase=MatchPhase.VALIDATING_INPUT.value,
            started_at=datetime.now(UTC),
        )
        self.session.add(report)
        self.session.flush()
        self._audit(user.id, "MATCH_RUN_REPORT_CREATED", report.id, payload.model_dump())
        self.session.commit()
        try:
            self._run(report, version, job, user, artifacts=artifacts)
        except Exception:
            self.session.rollback()
            raise
        return MatchCreateResult(report=self._report_read(report), reused=False)

    def _run(
        self,
        report: MatchReport,
        resume_version: ResumeVersion,
        job: Job,
        user: User,
        *,
        artifacts: dict[str, Any] | None = None,
    ) -> None:
        report.status = TaskStatus.RUNNING
        timings: dict[str, int] = {MatchPhase.VALIDATING_INPUT.value: 0}
        if artifacts is None:
            started = perf_counter()
            rule_artifacts = self.workflow_compute_deterministic(
                user,
                MatchCreate(
                    resume_version_id=resume_version.id,
                    job_id=job.id,
                    scoring_version=self.config.version,
                ),
            )
            timings[MatchPhase.MATCHING_RULES.value] = self._elapsed_ms(started)
        else:
            rule_artifacts = artifacts
            timings[MatchPhase.MATCHING_RULES.value] = 0
        requirements = JobRequirements.model_validate(rule_artifacts["requirements"])
        job_information_raw = rule_artifacts.get("job_information")
        job_information = (
            JobInformationAssessment.model_validate(job_information_raw)
            if job_information_raw is not None
            else None
        )
        computation = MatchComputation.model_validate(rule_artifacts["computation"])
        report.job_requirements_snapshot = requirements.model_dump(mode="json")

        semantic_result: SemanticMatchResult | None = None
        semantic_raw = rule_artifacts.get("semantic")
        if semantic_raw is not None:
            semantic_result = SemanticMatchResult(
                score=float(semantic_raw["score"]),
                evidence=[
                    SemanticEvidence.model_validate(item) for item in semantic_raw["evidence"]
                ],
                summary=SemanticSummary.model_validate(semantic_raw["summary"]),
            )
            timings[MatchPhase.MATCHING_SEMANTIC.value] = 0
        elif self.config.version == "hybrid-v1":
            semantic_config = self.config.semantic
            hybrid_weights = self.config.hybrid_weights
            if semantic_config is None or hybrid_weights is None:
                raise AppError(
                    "HYBRID_CONFIG_INVALID",
                    "The hybrid scoring configuration is incomplete",
                    500,
                )
            self._set_phase(report, MatchPhase.MATCHING_SEMANTIC)
            started = perf_counter()
            semantic_result = SemanticMatchingService(
                self._index_service(),
                semantic_config,
            ).calculate(resume_version, job, user.id)
            hybrid_score = round(
                computation.rule_score * hybrid_weights.deterministic
                + semantic_result.score * hybrid_weights.semantic,
                2,
            )
            computation.recommendation = recommendation_for_score(
                hybrid_score,
                computation.risks,
                computation.recommendation_cap,
            )
            computation.explanation = (
                f"Hybrid score {hybrid_score:.2f}/100 combines deterministic-v1.1 "
                f"rule score ({hybrid_weights.deterministic:.0%}) and local semantic "
                f"score ({hybrid_weights.semantic:.0%}). Semantic similarity cannot "
                "override blocking risks or completeness caps."
            )
            timings[MatchPhase.MATCHING_SEMANTIC.value] = self._elapsed_ms(started)
            report.phase_timings = timings.copy()
            self.session.commit()
        if semantic_result is not None and self.config.hybrid_weights is not None:
            hybrid_score = round(
                computation.rule_score * self.config.hybrid_weights.deterministic
                + semantic_result.score * self.config.hybrid_weights.semantic,
                2,
            )
            computation.recommendation = recommendation_for_score(
                hybrid_score,
                computation.risks,
                computation.recommendation_cap,
            )
            computation.explanation = (
                f"Hybrid score {hybrid_score:.2f}/100 combines deterministic-v1.1 "
                "rules and local semantic relevance. Semantic similarity cannot override "
                "blocking risks or completeness caps."
            )

        self._set_phase(report, MatchPhase.VERIFYING_EVIDENCE)
        started = perf_counter()
        self._persist_details(report, computation.skill_matches, computation.evidence_items)
        self._persist_dimensions(report, computation.dimension_scores)
        self._persist_risks(report, computation.risks)
        self._persist_condition_details(report, requirements, computation.risks)
        self._persist_report_metadata(
            report,
            computation,
            job_information,
            resume_version,
            job,
        )
        if semantic_result is not None:
            self._persist_semantic_result(report, semantic_result)
        self.session.flush()
        timings[MatchPhase.VERIFYING_EVIDENCE.value] = self._elapsed_ms(started)
        report.phase_timings = timings.copy()
        self.session.commit()

        self._set_phase(report, MatchPhase.CALCULATING_SCORE)
        started = perf_counter()
        report.rule_score = computation.rule_score
        report.semantic_score = semantic_result.score if semantic_result is not None else None
        report.hybrid_score = (
            round(
                computation.rule_score * self.config.hybrid_weights.deterministic
                + semantic_result.score * self.config.hybrid_weights.semantic,
                2,
            )
            if semantic_result is not None and self.config.hybrid_weights is not None
            else None
        )
        report.final_score = (
            report.hybrid_score if report.hybrid_score is not None else computation.rule_score
        )
        report.dimension_scores = [
            item.model_dump(mode="json") for item in computation.dimension_scores
        ]
        report.matched_skills = self._skills_for_status(
            computation.skill_matches,
            SkillMatchStatus.MATCHED,
        )
        report.partial_skills = self._skills_for_status(
            computation.skill_matches,
            SkillMatchStatus.PARTIAL,
            SkillMatchStatus.UNKNOWN,
        )
        report.missing_skills = self._skills_for_status(
            computation.skill_matches,
            SkillMatchStatus.MISSING,
        )
        report.hard_constraint_warnings = [
            item.model_dump(mode="json") for item in computation.risks
        ]
        report.recommendation_level = computation.recommendation.value
        report.explanation = computation.explanation
        report.recommended_actions = [
            item.model_dump(mode="json") for item in computation.recommended_actions
        ]
        timings[MatchPhase.CALCULATING_SCORE.value] = self._elapsed_ms(started)
        report.phase_timings = timings.copy()
        self.session.commit()

        self._set_phase(report, MatchPhase.SAVING_REPORT)
        started = perf_counter()
        report.current_phase = MatchPhase.COMPLETED.value
        report.status = TaskStatus.SUCCEEDED
        report.finished_at = datetime.now(UTC)
        report.duration_ms = self._duration_ms(report.started_at, report.finished_at)
        timings[MatchPhase.SAVING_REPORT.value] = self._elapsed_ms(started)
        timings[MatchPhase.COMPLETED.value] = 0
        report.phase_timings = timings
        self._audit(
            user.id,
            "MATCH_COMPLETED",
            report.id,
            {
                "rule_score": report.rule_score,
                "semantic_score": report.semantic_score,
                "hybrid_score": report.hybrid_score,
                "scoring_version": report.scoring_version,
            },
        )
        self.session.commit()
        self.session.refresh(report)

    def _persist_details(
        self,
        report: MatchReport,
        skill_matches: list[SkillMatch],
        evidence_items: list[EvidenceTrace],
    ) -> None:
        for order, skill_match in enumerate(skill_matches):
            detail = MatchDetail(
                report=report,
                category="SKILL",
                requirement=skill_match.job_raw_name,
                status=self._requirement_status(skill_match.status),
                score=round(skill_match.score * 100, 2),
                sort_order=order,
                code=f"SKILL_{skill_match.status.value}",
                explanation=skill_match.explanation,
                matching_rule=skill_match.matching_rule,
                data=skill_match.model_dump(mode="json"),
            )
            for evidence in evidence_items:
                if evidence.conclusion_key.casefold() != skill_match.normalized_name.casefold():
                    continue
                detail.evidence.append(
                    MatchEvidence(
                        resume_evidence=evidence.resume_evidence,
                        resume_source_id=evidence.source_location,
                        job_evidence=evidence.job_snippet,
                        job_source_id=evidence.job_field,
                        confidence=evidence.confidence,
                        resume_version_id=evidence.resume_version_id,
                        resume_skill_id=evidence.resume_skill_id,
                        source_type=evidence.source_type,
                        page_number=evidence.page_number,
                        paragraph_index=evidence.paragraph_index,
                        matching_rule=evidence.matching_rule,
                        conclusion_key=evidence.conclusion_key,
                        resume_section=evidence.resume_section,
                    )
                )
            self.session.add(detail)

    def _persist_dimensions(
        self,
        report: MatchReport,
        dimensions: list[DimensionScore],
    ) -> None:
        for order, dimension in enumerate(dimensions, start=100):
            self.session.add(
                MatchDetail(
                    report=report,
                    category="DIMENSION",
                    requirement=dimension.label,
                    status=self._score_status(dimension.score),
                    score=dimension.score,
                    sort_order=order,
                    code=dimension.code,
                    explanation=dimension.explanation,
                    matching_rule=self.config.version,
                    data=dimension.model_dump(mode="json"),
                )
            )

    def _persist_risks(
        self,
        report: MatchReport,
        risks: list[RiskItem],
    ) -> None:
        for order, risk in enumerate(risks, start=200):
            detail = MatchDetail(
                report=report,
                category="RISK",
                requirement=risk.job_requirement or risk.code,
                status=RequirementStatus.WARNING,
                score=None,
                sort_order=order,
                code=risk.code,
                severity=risk.severity.value,
                explanation=risk.explanation,
                remediation=risk.remediation,
                matching_rule=self.config.version,
                data=risk.model_dump(mode="json"),
            )
            detail.evidence.append(
                MatchEvidence(
                    conclusion_key=risk.code,
                    resume_evidence=risk.resume_evidence,
                    resume_section=None,
                    resume_source_id=(
                        "structured_resume_profile" if risk.resume_evidence else None
                    ),
                    job_evidence=risk.job_requirement,
                    job_source_id="extracted_job_requirement",
                    confidence=1,
                    resume_version_id=report.resume_version_id,
                    source_type="structured",
                    matching_rule=self.config.version,
                )
            )
            self.session.add(detail)

    def _persist_condition_details(
        self,
        report: MatchReport,
        requirements: JobRequirements,
        risks: list[RiskItem],
    ) -> None:
        risk_by_code = {risk.code: risk for risk in risks}
        conditions = (
            (
                "EXPERIENCE",
                requirements.experience_status.value,
                requirements.minimum_experience_years,
                ("MINIMUM_EXPERIENCE_NOT_MET",),
                ("EXPERIENCE_UNKNOWN",),
            ),
            (
                "EDUCATION",
                requirements.education_status.value,
                requirements.education_level,
                ("EDUCATION_REQUIREMENT_NOT_MET",),
                ("EDUCATION_UNKNOWN",),
            ),
            (
                "LANGUAGE",
                requirements.language_status.value,
                ", ".join(requirements.languages),
                ("LANGUAGE_REQUIREMENT_NOT_MET",),
                ("LANGUAGE_CAPABILITY_UNKNOWN",),
            ),
            (
                "LOCATION",
                requirements.location_status.value,
                requirements.location,
                (),
                ("LOCATION_COMPATIBILITY_UNKNOWN",),
            ),
            (
                "WORK_ELIGIBILITY",
                requirements.work_eligibility_status.value,
                requirements.work_eligibility,
                ("WORK_ELIGIBILITY_BLOCKED",),
                ("WORK_ELIGIBILITY_UNKNOWN",),
            ),
            (
                "CERTIFICATE",
                requirements.certificate_status.value,
                ", ".join(requirements.certificates),
                ("CERTIFICATE_REQUIREMENT_NOT_MET",),
                ("CERTIFICATE_STATUS_UNKNOWN",),
            ),
        )
        for order, (code, availability, job_value, unsatisfied, unknown) in enumerate(
            conditions,
            start=300,
        ):
            related = next(
                (
                    risk_by_code[risk_code]
                    for risk_code in (*unsatisfied, *unknown)
                    if risk_code in risk_by_code
                ),
                None,
            )
            if availability == "NOT_PROVIDED":
                condition_status = "NOT_REQUIRED"
                storage_status = RequirementStatus.SATISFIED
            elif any(risk_code in risk_by_code for risk_code in unsatisfied):
                condition_status = "UNSATISFIED"
                storage_status = RequirementStatus.MISSING
            elif any(risk_code in risk_by_code for risk_code in unknown):
                condition_status = "UNKNOWN"
                storage_status = RequirementStatus.WARNING
            else:
                condition_status = "SATISFIED"
                storage_status = RequirementStatus.SATISFIED
            detail = MatchDetail(
                report=report,
                category="CONDITION",
                requirement=str(job_value or code),
                status=storage_status,
                score=None,
                sort_order=order,
                code=code,
                explanation=(
                    related.explanation
                    if related is not None
                    else f"{code} condition is {condition_status}."
                ),
                remediation=related.remediation if related is not None else None,
                matching_rule=self.config.version,
                data={
                    "code": code,
                    "status": condition_status,
                    "job_requirement": job_value,
                    "resume_evidence": (related.resume_evidence if related is not None else None),
                },
            )
            detail.evidence.append(
                MatchEvidence(
                    conclusion_key=code,
                    resume_evidence=(
                        related.resume_evidence
                        if related is not None
                        else "Confirmed structured resume profile"
                    ),
                    resume_source_id=f"resume_section:{code.casefold()}",
                    job_evidence=str(job_value) if job_value is not None else None,
                    job_source_id=f"job_requirement:{code.casefold()}",
                    confidence=1,
                    resume_version_id=report.resume_version_id,
                    resume_section=code.casefold(),
                    source_type="structured",
                    matching_rule=self.config.version,
                )
            )
            self.session.add(detail)

    def _persist_report_metadata(
        self,
        report: MatchReport,
        computation: MatchComputation,
        assessment: JobInformationAssessment | None,
        resume_version: ResumeVersion,
        job: Job,
    ) -> None:
        data: dict[str, Any] = {
            "job_information_completeness": computation.job_information_completeness,
            "report_confidence": (
                computation.report_confidence.value
                if computation.report_confidence is not None
                else None
            ),
            "report_confidence_score": computation.report_confidence_score,
            "completeness_warning": computation.completeness_warning,
            "evaluated_requirement_count": computation.evaluated_requirement_count,
            "unknown_requirement_count": computation.unknown_requirement_count,
            "not_provided_requirement_count": computation.not_provided_requirement_count,
            "recommendation_cap": (
                computation.recommendation_cap.value
                if computation.recommendation_cap is not None
                else None
            ),
            "policy_version": computation.policy_version,
            "policy_config_snapshot": (
                computation.policy_config_snapshot.model_dump(mode="json")
                if computation.policy_config_snapshot is not None
                else None
            ),
            "information_statuses": (
                {key: value.value for key, value in assessment.statuses.items()}
                if assessment is not None
                else {}
            ),
            "input_snapshot": {
                "resume": {
                    "resume_id": resume_version.resume_id,
                    "version_id": resume_version.id,
                    "version_number": resume_version.version_number,
                    "is_confirmed": resume_version.is_confirmed,
                    "created_at": resume_version.created_at.isoformat(),
                },
                "job": {
                    "job_id": job.id,
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "content_hash": job.content_hash,
                    "import_method": job.import_method,
                    "description": job.description,
                    "requirements": job.requirements,
                    "responsibilities": job.responsibilities,
                },
            },
        }
        self.session.add(
            MatchDetail(
                report=report,
                category="REPORT_METADATA",
                requirement="Report trust and policy metadata",
                status=RequirementStatus.SATISFIED,
                score=computation.report_confidence_score,
                sort_order=400,
                code="REPORT_TRUST",
                explanation=computation.completeness_warning,
                matching_rule=computation.policy_version,
                data=data,
            )
        )

    def _persist_semantic_result(
        self,
        report: MatchReport,
        result: SemanticMatchResult,
    ) -> None:
        embedding = self.config.embedding_config
        self.session.add(
            MatchDetail(
                report=report,
                category="SEMANTIC",
                requirement="Local semantic relevance evidence",
                status=self._score_status(result.score),
                score=result.score,
                sort_order=500,
                code="SEMANTIC_SUMMARY",
                explanation=(
                    "Semantic similarity supplements project, experience, skill, education, "
                    "and certificate relevance; it does not prove a skill or override "
                    "qualification conflicts."
                ),
                matching_rule=self.config.semantic.version if self.config.semantic else None,
                data={
                    "embedding_model": embedding.model if embedding else None,
                    "embedding_config_snapshot": (
                        embedding.model_dump(mode="json") if embedding else None
                    ),
                    "semantic_config_snapshot": (
                        self.config.semantic.model_dump(mode="json")
                        if self.config.semantic
                        else None
                    ),
                    "semantic_summary": result.summary.model_dump(mode="json"),
                    "semantic_evidence": [item.model_dump(mode="json") for item in result.evidence],
                },
            )
        )

    def _mark_failed(self, report: MatchReport, code: str, message: str) -> None:
        self.session.rollback()
        persisted = self.session.get(MatchReport, report.id)
        if persisted is None:
            return
        persisted.status = TaskStatus.FAILED
        persisted.error_code = code
        persisted.error_message = message
        persisted.finished_at = datetime.now(UTC)
        persisted.duration_ms = self._duration_ms(
            persisted.started_at,
            persisted.finished_at,
        )
        self.session.commit()

    def _owned_report(self, report_id: int, user_id: int) -> MatchReport:
        report = self.repository.get_owned_report(report_id, user_id)
        if report is None:
            raise AppError("MATCH_NOT_FOUND", "The match report was not found", 404)
        return report

    def _report_read(self, report: MatchReport) -> MatchReportRead:
        evidence_items = [
            self._evidence_trace(evidence)
            for detail in report.details
            for evidence in detail.evidence
        ]
        requirements = (
            JobRequirements.model_validate(report.job_requirements_snapshot)
            if report.job_requirements_snapshot
            else None
        )
        metadata = next(
            (
                detail.data
                for detail in report.details
                if detail.category == "REPORT_METADATA" and detail.code == "REPORT_TRUST"
            ),
            {},
        )
        semantic_metadata = next(
            (
                detail.data
                for detail in report.details
                if detail.category == "SEMANTIC" and detail.code == "SEMANTIC_SUMMARY"
            ),
            {},
        )
        matched_skills = [SkillMatch.model_validate(item) for item in report.matched_skills]
        partial_skills = [SkillMatch.model_validate(item) for item in report.partial_skills]
        missing_skills = [SkillMatch.model_validate(item) for item in report.missing_skills]
        return MatchReportRead(
            id=report.id,
            user_id=report.user_id,
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            status=self._api_status(report.status),
            current_phase=MatchPhase(report.current_phase),
            rule_score=report.rule_score,
            semantic_score=report.semantic_score,
            hybrid_score=report.hybrid_score,
            final_score=report.final_score,
            scoring_version=report.scoring_version,
            scoring_config_snapshot=ScoringConfig.model_validate(report.scoring_config_snapshot),
            dimension_scores=[
                DimensionScore.model_validate(item) for item in report.dimension_scores
            ],
            matched_skills=matched_skills,
            partial_skills=partial_skills,
            missing_skills=missing_skills,
            hard_requirement_risks=[
                RiskItem.model_validate(item) for item in report.hard_constraint_warnings
            ],
            evidence_items=evidence_items,
            recommendation=(
                RecommendationLevel(report.recommendation_level)
                if report.recommendation_level
                else None
            ),
            explanation=report.explanation,
            recommended_actions=[
                RecommendedAction.model_validate(item) for item in report.recommended_actions
            ],
            job_requirements=requirements,
            phase_timings_ms=report.phase_timings,
            duration_ms=report.duration_ms,
            error_code=report.error_code,
            error_message=report.error_message,
            started_at=report.started_at,
            completed_at=report.finished_at,
            created_at=report.created_at,
            updated_at=report.updated_at,
            job_information_completeness=metadata.get("job_information_completeness"),
            report_confidence=metadata.get("report_confidence"),
            report_confidence_score=metadata.get("report_confidence_score"),
            completeness_warning=metadata.get("completeness_warning"),
            evaluated_requirement_count=int(metadata.get("evaluated_requirement_count") or 0),
            unknown_requirement_count=int(metadata.get("unknown_requirement_count") or 0),
            not_provided_requirement_count=int(metadata.get("not_provided_requirement_count") or 0),
            recommendation_cap=metadata.get("recommendation_cap"),
            policy_version=metadata.get("policy_version"),
            policy_config_snapshot=metadata.get("policy_config_snapshot"),
            embedding_model=semantic_metadata.get("embedding_model"),
            embedding_config_snapshot=semantic_metadata.get("embedding_config_snapshot"),
            semantic_config_snapshot=semantic_metadata.get("semantic_config_snapshot"),
            semantic_evidence=[
                SemanticEvidence.model_validate(item)
                for item in semantic_metadata.get("semantic_evidence", [])
            ],
            semantic_summary=(
                SemanticSummary.model_validate(semantic_metadata["semantic_summary"])
                if semantic_metadata.get("semantic_summary")
                else None
            ),
            evidence_coverage=self._evidence_coverage(
                matched_skills,
                partial_skills,
                missing_skills,
            ),
            input_snapshot=(
                MatchInputSnapshot.model_validate(metadata["input_snapshot"])
                if metadata.get("input_snapshot")
                else None
            ),
        )

    @staticmethod
    def _evidence_coverage(
        matched: list[SkillMatch],
        partial: list[SkillMatch],
        missing: list[SkillMatch],
    ) -> EvidenceCoverage:
        all_matches = [*matched, *partial, *missing]
        total = len(all_matches)
        verified = sum(item.status is SkillMatchStatus.MATCHED for item in all_matches)
        partially_supported = sum(
            item.status is SkillMatchStatus.PARTIAL for item in all_matches
        )
        missing_count = sum(item.status is SkillMatchStatus.MISSING for item in all_matches)
        unknown = sum(item.status is SkillMatchStatus.UNKNOWN for item in all_matches)
        return EvidenceCoverage(
            total_requirements=total,
            verified=verified,
            partially_supported=partially_supported,
            missing=missing_count,
            unknown=unknown,
            coverage_percent=round(verified / total * 100, 2) if total else 0,
        )

    def _select_config(self, requested_version: str | None) -> ScoringConfig:
        if requested_version is None and self._configured_scoring is not None:
            config = self._configured_scoring
        else:
            version = requested_version or self.settings.default_scoring_version
            try:
                config = scoring_config_for(version)
            except ValueError as exc:
                raise AppError(
                    "SCORING_VERSION_UNSUPPORTED",
                    "The requested scoring version is not supported",
                    422,
                ) from exc
        if config.version != "hybrid-v1":
            return config
        provider = self._provider()
        semantic = config.semantic
        if semantic is None:
            raise AppError(
                "HYBRID_CONFIG_INVALID",
                "The hybrid scoring configuration is incomplete",
                500,
            )
        return config.model_copy(
            update={
                "embedding_config": provider.config_snapshot,
                "semantic": semantic.model_copy(
                    update={
                        "top_k": self.settings.semantic_top_k,
                        "similarity_threshold": (self.settings.semantic_similarity_threshold),
                    }
                ),
            }
        )

    def _provider(self) -> EmbeddingProvider:
        if self._embedding_provider is None:
            self._embedding_provider = embedding_provider_from_settings(self.settings)
        return self._embedding_provider

    def _index_service(self) -> SemanticIndexService:
        if self._semantic_index is None:
            self._semantic_index = SemanticIndexService(self.settings, self._provider())
        return self._semantic_index

    def _detail_read(self, detail: MatchDetail) -> MatchDetailRead:
        return MatchDetailRead(
            id=detail.id,
            report_id=detail.report_id,
            category=detail.category,
            requirement=detail.requirement,
            status=detail.status.value,
            score=detail.score,
            sort_order=detail.sort_order,
            code=detail.code,
            severity=detail.severity,
            explanation=detail.explanation,
            remediation=detail.remediation,
            matching_rule=detail.matching_rule,
            data=detail.data,
            evidence=[
                MatchEvidenceRead(
                    id=item.id,
                    detail_id=item.detail_id,
                    **self._evidence_trace(item).model_dump(),
                )
                for item in detail.evidence
            ],
        )

    @staticmethod
    def _evidence_trace(evidence: MatchEvidence) -> EvidenceTrace:
        return EvidenceTrace(
            conclusion_key=evidence.conclusion_key or "unknown",
            resume_version_id=evidence.resume_version_id or 0,
            resume_skill_id=evidence.resume_skill_id,
            resume_evidence=evidence.resume_evidence,
            resume_section=evidence.resume_section,
            source_type=evidence.source_type,
            page_number=evidence.page_number,
            paragraph_index=evidence.paragraph_index,
            source_location=evidence.resume_source_id,
            job_field=evidence.job_source_id or "unknown",
            job_snippet=evidence.job_evidence or "",
            matching_rule=evidence.matching_rule or "unknown",
            confidence=evidence.confidence or 0,
        )

    @staticmethod
    def _skills_for_status(
        matches: list[SkillMatch],
        *statuses: SkillMatchStatus,
    ) -> list[dict[str, Any]]:
        return [item.model_dump(mode="json") for item in matches if item.status in statuses]

    @staticmethod
    def _api_status(status: TaskStatus) -> MatchStatus:
        if status is TaskStatus.SUCCEEDED:
            return MatchStatus.SUCCESS
        if status is TaskStatus.RUNNING:
            return MatchStatus.RUNNING
        if status is TaskStatus.FAILED:
            return MatchStatus.FAILED
        if status is TaskStatus.CANCELLED:
            return MatchStatus.CANCELLED
        return MatchStatus.PENDING

    @staticmethod
    def _requirement_status(status: SkillMatchStatus) -> RequirementStatus:
        return {
            SkillMatchStatus.MATCHED: RequirementStatus.SATISFIED,
            SkillMatchStatus.PARTIAL: RequirementStatus.PARTIAL,
            SkillMatchStatus.MISSING: RequirementStatus.MISSING,
            SkillMatchStatus.UNKNOWN: RequirementStatus.WARNING,
        }[status]

    @staticmethod
    def _score_status(score: float) -> RequirementStatus:
        if score >= 80:
            return RequirementStatus.SATISFIED
        if score >= 50:
            return RequirementStatus.PARTIAL
        return RequirementStatus.MISSING

    @staticmethod
    def _set_phase(report: MatchReport, phase: MatchPhase) -> None:
        report.current_phase = phase.value

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(round((perf_counter() - started) * 1000), 0)

    @staticmethod
    def _duration_ms(started: datetime | None, finished: datetime) -> int | None:
        if started is None:
            return None
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        if finished.tzinfo is None:
            finished = finished.replace(tzinfo=UTC)
        return max(round((finished - started).total_seconds() * 1000), 0)

    def _audit(
        self,
        user_id: int,
        action: str,
        report_id: int,
        details: dict[str, Any],
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=user_id,
                action=action,
                resource_type="match_report",
                resource_id=str(report_id),
                details=details,
            )
        )
