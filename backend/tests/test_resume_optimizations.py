"""Tests for the Stage 3 resume optimization feature.

Covers:

1. Normal generation flow.
2. Fake provider returns deterministic output.
3. Invalid Dify JSON raises a 502 / FAILED material.
4. Empty provider output raises DIFY_EMPTY_OUTPUT.
5. Provider timeout surfaces as a FAILED material.
6. Retry after transient failure produces a fresh material.
7. User A cannot read user B's optimizations.
8. Resume / job / match report ownership verification.
9. evidence_keys that don't exist are rejected server-side.
10. Cross-resume-version evidence is rejected.
11. Missing skills must not appear in suggested_text.
12. The original resume version is never modified.
13. New resume version creation.
14. Only user-confirmed suggestions are applied.
15. History is preserved (archived materials are not overwritten).
16. Failed records are hidden by default.
17. The Dify API key never appears in logs or state snapshots.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.integrations.dify.resume_optimization_providers import (
    FakeResumeOptimizationProvider,
)
from app.models.career import GeneratedMaterial
from app.models.enums import TaskStatus
from app.models.operations import AgentRun
from app.models.resumes import ResumeVersion
from app.models.users import User
from app.schemas.matching import MatchCreate
from app.schemas.resume_optimizations import (
    ResumeOptimizationConfirmPayload,
    ResumeOptimizationCreate,
    ResumeOptimizationGeneration,
    ResumeOptimizationProviderAttempt,
    ResumeOptimizationProviderResult,
    ResumeOptimizationSectionConfirm,
    ResumeOptimizationSectionOutput,
    ResumeOptimizationWorkflowInput,
    ResumeOptimizationWorkflowOutput,
    SectionChangeType,
)
from app.services.matching import MatchService
from app.services.resume_optimizations import ResumeOptimizationService
from tests.test_matching import _create_case, _register_headers


def _successful_report(
    db_session: Session,
    user: User,
    fixture_name: str = "skill_gap",
) -> int:
    case = _create_case(db_session, user, fixture_name)
    result = MatchService(db_session).create(
        user,
        MatchCreate(resume_version_id=case.version.id, job_id=case.job.id),
    )
    return result.report.id


def _build_workflow_input(
    db_session: Session,
    user: User,
    fixture_name: str = "skill_gap",
) -> tuple[ResumeOptimizationWorkflowInput, int, int, int]:
    """Build a workflow input directly so provider tests can run without
    going through the service validation chain.
    """
    case = _create_case(db_session, user, fixture_name)
    report = (
        MatchService(db_session)
        .create(
            user,
            MatchCreate(resume_version_id=case.version.id, job_id=case.job.id),
        )
        .report
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    request = service._workflow_input(case.version, case.job, report)
    return request, case.version.id, case.job.id, report.id


# ---------------------------------------------------------------------------
# 1 + 2: Normal generation with the Fake provider
# ---------------------------------------------------------------------------


def test_resume_optimization_create_with_fake_provider(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    assert report is not None
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    assert optimization.status == "DRAFT"
    assert optimization.resume_version_id == report.resume_version_id
    assert optimization.job_id == report.job_id
    assert optimization.match_report_id == report_id
    assert optimization.summary
    assert optimization.sections  # fake provider returns at least one section
    assert optimization.provider == "fake"
    assert optimization.workflow_run_id is not None
    run = db_session.scalar(select(AgentRun).where(AgentRun.run_type == "resume_optimization"))
    assert run is not None
    assert run.status == TaskStatus.SUCCEEDED
    assert run.state_snapshot["generated_material_id"] == optimization.id


# ---------------------------------------------------------------------------
# 3: Invalid Dify JSON
# ---------------------------------------------------------------------------


class _InvalidJsonProvider:
    def generate_optimization(
        self, request: ResumeOptimizationWorkflowInput
    ) -> ResumeOptimizationProviderResult:
        raise AppError("DIFY_OUTPUT_INVALID", "Dify returned non-JSON", 502)


def test_resume_optimization_invalid_json_creates_failed_record(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, _InvalidJsonProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    assert optimization.status == "FAILED"
    assert optimization.error_code == "DIFY_OUTPUT_INVALID"


# ---------------------------------------------------------------------------
# 4: Empty Dify output
# ---------------------------------------------------------------------------


class _EmptyOutputProvider:
    def generate_optimization(
        self, request: ResumeOptimizationWorkflowInput
    ) -> ResumeOptimizationProviderResult:
        raise AppError("DIFY_EMPTY_OUTPUT", "Dify returned empty outputs", 502)


def test_resume_optimization_empty_output_creates_failed_record(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, _EmptyOutputProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    assert optimization.status == "FAILED"
    assert optimization.error_code == "DIFY_EMPTY_OUTPUT"


# ---------------------------------------------------------------------------
# 5: Timeout
# ---------------------------------------------------------------------------


class _TimeoutProvider:
    def generate_optimization(
        self, request: ResumeOptimizationWorkflowInput
    ) -> ResumeOptimizationProviderResult:
        raise AppError("DIFY_TIMEOUT", "Dify request timed out", 504)


def test_resume_optimization_timeout_creates_failed_record(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, _TimeoutProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    assert optimization.status == "FAILED"
    assert optimization.error_code == "DIFY_TIMEOUT"


# ---------------------------------------------------------------------------
# 6: Retry after failure succeeds
# ---------------------------------------------------------------------------


def test_resume_optimization_retry_creates_new_record(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    failing_service = ResumeOptimizationService(db_session, _EmptyOutputProvider())
    failed = failing_service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    assert failed.status == "FAILED"

    retry_service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    retried = retry_service.retry(admin_user.id, failed.id)
    assert retried.id != failed.id
    assert retried.status == "DRAFT"


# ---------------------------------------------------------------------------
# 7: User isolation
# ---------------------------------------------------------------------------


def test_resume_optimization_user_isolation(
    db_session: Session,
    admin_user: User,
) -> None:
    """User A's optimization must not be readable by user B."""
    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.users import User, UserProfile

    other_user = User(
        email="other@example.com",
        password_hash=hash_password("OtherPassword123!"),
        role=UserRole.USER,
        profile=UserProfile(display_name="Other"),
    )
    db_session.add(other_user)
    db_session.commit()

    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    # User B trying to read user A's optimization should fail
    with pytest.raises(AppError) as exc_info:
        service.get(other_user.id, optimization.id)
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 8: Ownership verification of resume / job / match report
# ---------------------------------------------------------------------------


def test_resume_optimization_ownership_verification(
    db_session: Session,
    admin_user: User,
) -> None:
    """Mismatched resume_version / job / match_report must be rejected."""
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    # Create an unrelated resume version
    from app.models.enums import ResumeStatus
    from app.models.resumes import Resume, ResumeVersion

    other_resume = Resume(
        owner_id=admin_user.id,
        title="Unrelated",
        status=ResumeStatus.CONFIRMED,
    )
    other_version = ResumeVersion(
        resume=other_resume,
        version_number=1,
        structured_data={},
        is_current=False,
        is_confirmed=True,
        raw_text="Unrelated",
    )
    db_session.add(other_version)
    db_session.commit()

    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    with pytest.raises(AppError) as exc_info:
        service.create(
            admin_user.id,
            ResumeOptimizationCreate(
                resume_version_id=other_version.id,
                job_id=report.job_id,
                match_report_id=report_id,
            ),
        )
    assert exc_info.value.code == "RESUME_OPTIMIZATION_INPUT_MISMATCH"


# ---------------------------------------------------------------------------
# 9: evidence_keys must reference real resume evidence
# ---------------------------------------------------------------------------


class _FabricatedEvidenceProvider:
    """Returns evidence_keys that don't exist in the resume."""

    def generate_optimization(
        self, request: ResumeOptimizationWorkflowInput
    ) -> ResumeOptimizationProviderResult:
        output = ResumeOptimizationWorkflowOutput(
            summary="test",
            sections=[
                ResumeOptimizationSectionOutput(
                    section="工作经历",
                    source_section_id="experience-1",
                    original_text="original",
                    suggested_text="suggested",
                    reason="test",
                    related_job_requirement="test",
                    evidence_keys=["fake-evidence-not-in-resume"],
                    change_type=SectionChangeType.EMPHASIZE,
                )
            ],
            keyword_suggestions=[],
            missing_evidence_warnings=[],
            fabrication_warnings=[],
            job_information_warning="",
            generation=ResumeOptimizationGeneration(
                workflow_version="test-v1",
                workflow_run_id="test-run",
                provider="fake",
                latency_ms=10,
            ),
        )
        return ResumeOptimizationProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            attempts=[
                ResumeOptimizationProviderAttempt(
                    sequence=1,
                    http_status=200,
                    status="succeeded",
                    latency_ms=10,
                    retried=False,
                )
            ],
        )


def test_resume_optimization_rejects_fabricated_evidence_keys(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, _FabricatedEvidenceProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    # Server-side validation rejects fabricated evidence keys, producing
    # a FAILED record.
    assert optimization.status == "FAILED"
    assert optimization.error_code == "DIFY_OUTPUT_INVALID"


# ---------------------------------------------------------------------------
# 10: source_section_id must belong to the current resume version
# ---------------------------------------------------------------------------


class _ForeignSectionIdProvider:
    """Returns a source_section_id that doesn't exist in this resume."""

    def generate_optimization(
        self, request: ResumeOptimizationWorkflowInput
    ) -> ResumeOptimizationProviderResult:
        output = ResumeOptimizationWorkflowOutput(
            summary="test",
            sections=[
                ResumeOptimizationSectionOutput(
                    section="项目经历",
                    source_section_id="project-99-not-in-resume",
                    original_text="original",
                    suggested_text="suggested",
                    reason="test",
                    related_job_requirement="test",
                    evidence_keys=[],
                    change_type=SectionChangeType.REWRITE,
                )
            ],
            keyword_suggestions=[],
            missing_evidence_warnings=[],
            fabrication_warnings=[],
            job_information_warning="",
            generation=ResumeOptimizationGeneration(
                workflow_version="test-v1",
                workflow_run_id="test-run",
                provider="fake",
                latency_ms=10,
            ),
        )
        return ResumeOptimizationProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            attempts=[
                ResumeOptimizationProviderAttempt(
                    sequence=1,
                    http_status=200,
                    status="succeeded",
                    latency_ms=10,
                    retried=False,
                )
            ],
        )


def test_resume_optimization_rejects_foreign_section_id(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, _ForeignSectionIdProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    assert optimization.status == "FAILED"
    assert optimization.error_code == "DIFY_OUTPUT_INVALID"


# ---------------------------------------------------------------------------
# 11: Missing skill must not appear in suggested_text
# ---------------------------------------------------------------------------


class _MissingSkillProvider:
    """Injects a missing-skill name into suggested_text."""

    def generate_optimization(
        self, request: ResumeOptimizationWorkflowInput
    ) -> ResumeOptimizationProviderResult:
        missing_name = ""
        for item in request.match_report.missing_skills:
            name = str(item.get("normalized_name") or item.get("job_raw_name") or "")
            if name:
                missing_name = name
                break
        output = ResumeOptimizationWorkflowOutput(
            summary="test",
            sections=[
                ResumeOptimizationSectionOutput(
                    section="工作经历",
                    source_section_id="experience-1",
                    original_text="original",
                    suggested_text=f"Built something with {missing_name}.",
                    reason="test",
                    related_job_requirement="test",
                    evidence_keys=[],
                    change_type=SectionChangeType.REWRITE,
                )
            ],
            keyword_suggestions=[],
            missing_evidence_warnings=[],
            fabrication_warnings=[],
            job_information_warning="",
            generation=ResumeOptimizationGeneration(
                workflow_version="test-v1",
                workflow_run_id="test-run",
                provider="fake",
                latency_ms=10,
            ),
        )
        return ResumeOptimizationProviderResult(
            output=output,
            raw_output=output.model_dump(mode="json"),
            attempts=[
                ResumeOptimizationProviderAttempt(
                    sequence=1,
                    http_status=200,
                    status="succeeded",
                    latency_ms=10,
                    retried=False,
                )
            ],
        )


def test_resume_optimization_rejects_missing_skill_in_suggested_text(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, _MissingSkillProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    assert optimization.status == "FAILED"
    assert optimization.error_code == "DIFY_OUTPUT_INVALID"


# ---------------------------------------------------------------------------
# 12: Original resume version is never modified
# ---------------------------------------------------------------------------


def test_resume_optimization_preserves_original_resume_version(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    original_structured = json.loads(json.dumps(report.resume_version.structured_data))
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    db_session.refresh(report.resume_version)
    assert report.resume_version.structured_data == original_structured


# ---------------------------------------------------------------------------
# 13: New resume version creation
# ---------------------------------------------------------------------------


def test_resume_optimization_create_new_version(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    # Confirm one of the suggested sections
    section = optimization.sections[0]
    confirmed = service.confirm(
        admin_user.id,
        optimization.id,
        ResumeOptimizationConfirmPayload(
            sections=[
                ResumeOptimizationSectionConfirm(
                    source_section_id=section.source_section_id,
                    accepted=True,
                )
            ]
        ),
    )
    assert confirmed.status == "CONFIRMED"
    assert confirmed.is_human_confirmed is True
    # Create the new version
    result = service.create_version(admin_user.id, optimization.id)
    assert result.parent_version_id == report.resume_version_id
    assert result.applied_section_count >= 1
    # The original version is unchanged
    db_session.refresh(report.resume_version)
    assert report.resume_version.is_current is True
    # The new version exists and has a parent link
    new_version = db_session.get(ResumeVersion, result.resume_version["id"])
    assert new_version is not None
    assert new_version.parent_version_id == report.resume_version_id
    assert new_version.is_current is False
    assert new_version.is_confirmed is False


# ---------------------------------------------------------------------------
# 14: Only user-confirmed suggestions are applied
# ---------------------------------------------------------------------------


def test_resume_optimization_only_applies_confirmed_suggestions(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    section = optimization.sections[0]
    # Reject the suggestion (accepted=False)
    confirmed = service.confirm(
        admin_user.id,
        optimization.id,
        ResumeOptimizationConfirmPayload(
            sections=[
                ResumeOptimizationSectionConfirm(
                    source_section_id=section.source_section_id,
                    accepted=False,
                )
            ]
        ),
    )
    assert confirmed.status == "CONFIRMED"
    result = service.create_version(admin_user.id, optimization.id)
    assert result.applied_section_count == 0
    new_version = db_session.get(ResumeVersion, result.resume_version["id"])
    assert new_version is not None
    # The new profile equals the parent profile because nothing was applied
    assert (
        new_version.structured_data["work_experience"][0]["description"]["value"]
        == report.resume_version.structured_data["work_experience"][0]["description"]["value"]
    )


# ---------------------------------------------------------------------------
# 14a: User-edited text re-validation (security review)
# ---------------------------------------------------------------------------


def _first_missing_skill_not_in_original(
    report: Any,
    original_text: str,
) -> str:
    """Pick a missing skill name that is NOT already in original_text.

    For the ``skill_gap`` fixture the work-experience description is
    "Built Python and JavaScript services.", so Python and JavaScript
    are missing skills but already appear in the original text (allowed
    when preserved). SQL is missing and absent from the original, which
    makes it the right token to prove an edit cannot introduce it.
    """
    original_lower = original_text.lower()
    for item in report.missing_skills or []:
        name = str(item.get("normalized_name") or item.get("job_raw_name") or "")
        if name and name.lower() not in original_lower:
            return name
    pytest.fail("No missing skill absent from original_text found in fixture")


def test_resume_optimization_confirm_rejects_missing_skill_in_edited_text(
    db_session: Session,
    admin_user: User,
) -> None:
    """A user must not introduce a missing skill via edited_text on confirm."""
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    section = optimization.sections[0]
    missing_name = _first_missing_skill_not_in_original(report, section.original_text)
    with pytest.raises(AppError) as exc_info:
        service.confirm(
            admin_user.id,
            optimization.id,
            ResumeOptimizationConfirmPayload(
                sections=[
                    ResumeOptimizationSectionConfirm(
                        source_section_id=section.source_section_id,
                        accepted=True,
                        edited_text=f"Built services. Now expert in {missing_name}.",
                    )
                ]
            ),
        )
    assert exc_info.value.code == "RESUME_OPTIMIZATION_EDIT_INVALID"
    assert exc_info.value.status_code == 422
    assert missing_name.lower() in exc_info.value.message.lower()
    # The material must remain in DRAFT (confirm did not persist).
    material = db_session.get(GeneratedMaterial, optimization.id)
    assert material is not None
    assert material.status == "DRAFT"
    assert material.is_human_confirmed is False


def test_resume_optimization_confirm_allows_preserved_missing_skill_in_edited_text(
    db_session: Session,
    admin_user: User,
) -> None:
    """Editing text that merely preserves a missing skill already in the
    original is allowed (it is the user's own existing content)."""
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    section = optimization.sections[0]
    # Keep the original text (which contains missing skills Python /
    # JavaScript) and only append a non-skill phrase. This must succeed.
    confirmed = service.confirm(
        admin_user.id,
        optimization.id,
        ResumeOptimizationConfirmPayload(
            sections=[
                ResumeOptimizationSectionConfirm(
                    source_section_id=section.source_section_id,
                    accepted=True,
                    edited_text=section.original_text + " Improved throughput.",
                )
            ],
            attest_truth=True,
        ),
    )
    assert confirmed.status == "CONFIRMED"
    assert confirmed.is_human_confirmed is True


def test_resume_optimization_create_version_revalidates_edited_text(
    db_session: Session,
    admin_user: User,
) -> None:
    """create_version is a defense-in-depth gate: if the persisted
    facts_used somehow contains an edited_text that introduces a missing
    skill (e.g. tampered or stale), the new version must not be built."""
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    section = optimization.sections[0]
    # Confirm legitimately first.
    service.confirm(
        admin_user.id,
        optimization.id,
        ResumeOptimizationConfirmPayload(
            sections=[
                ResumeOptimizationSectionConfirm(
                    source_section_id=section.source_section_id,
                    accepted=True,
                    edited_text=section.original_text + " Improved throughput.",
                )
            ],
            attest_truth=True,
        ),
    )
    # Tamper the persisted facts_used to inject a missing skill that was
    # not in the original text, simulating a stale/tampered confirmation.
    missing_name = _first_missing_skill_not_in_original(report, section.original_text)
    material = db_session.get(GeneratedMaterial, optimization.id)
    assert material is not None
    facts = material.facts_used or [{}]
    facts[0]["sections"][0]["edited_text"] = (
        section.original_text + f" Now expert in {missing_name}."
    )
    material.facts_used = facts
    db_session.flush()
    with pytest.raises(AppError) as exc_info:
        service.create_version(admin_user.id, optimization.id)
    assert exc_info.value.code == "RESUME_OPTIMIZATION_EDIT_INVALID"
    assert exc_info.value.status_code == 422
    # No new resume version was created.
    new_versions = db_session.scalars(
        select(ResumeVersion).where(ResumeVersion.parent_version_id.is_not(None))
    ).all()
    assert new_versions == []


def test_resume_optimization_edited_text_then_create_version_applies_edit(
    db_session: Session,
    admin_user: User,
) -> None:
    """A clean edited_text is applied to the new version's description."""
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    section = optimization.sections[0]
    clean_edit = section.original_text + " Led a team of three."
    service.confirm(
        admin_user.id,
        optimization.id,
        ResumeOptimizationConfirmPayload(
            sections=[
                ResumeOptimizationSectionConfirm(
                    source_section_id=section.source_section_id,
                    accepted=True,
                    edited_text=clean_edit,
                )
            ],
            attest_truth=True,
        ),
    )
    result = service.create_version(admin_user.id, optimization.id)
    assert result.applied_section_count == 1
    new_version = db_session.get(ResumeVersion, result.resume_version["id"])
    assert new_version is not None
    assert new_version.structured_data["work_experience"][0]["description"]["value"] == clean_edit
    # Parent version stays unchanged.
    db_session.refresh(report.resume_version)
    assert (
        report.resume_version.structured_data["work_experience"][0]["description"]["value"]
        == section.original_text
    )


# ---------------------------------------------------------------------------
# 15: Historical optimizations are not overwritten
# ---------------------------------------------------------------------------


def _add_missing_skill(report: Any, skill_name: str) -> None:
    """Append a missing skill to a persisted match report for tests."""
    missing = list(report.missing_skills or [])
    missing.append({"normalized_name": skill_name, "job_raw_name": skill_name})
    report.missing_skills = missing


def _tamper_stored_original_text(material: Any, new_original: str) -> None:
    """Rewrite the first section's original_text in the persisted material
    content JSON so number/skill revalidation sees a custom original."""
    import json as _json

    payload = _json.loads(material.content)
    if payload.get("sections"):
        payload["sections"][0]["original_text"] = new_original
    material.content = _json.dumps(payload, ensure_ascii=False)


def _tamper_stored_evidence_keys(material: Any, keys: list[str]) -> None:
    """Rewrite the first section's evidence_keys in the persisted material
    content JSON so evidence-text resolution can be exercised."""
    import json as _json

    payload = _json.loads(material.content)
    if payload.get("sections"):
        payload["sections"][0]["evidence_keys"] = keys
    material.content = _json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 16: Number-fact validation on edited_text
# ---------------------------------------------------------------------------


def test_resume_optimization_edit_rejects_unsubstantiated_number(
    db_session: Session,
    admin_user: User,
) -> None:
    """编辑新增 ``提升80%`` 且原文与证据中均无 ``80%`` 时拒绝。"""
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    section = optimization.sections[0]
    with pytest.raises(AppError) as exc_info:
        service.confirm(
            admin_user.id,
            optimization.id,
            ResumeOptimizationConfirmPayload(
                sections=[
                    ResumeOptimizationSectionConfirm(
                        source_section_id=section.source_section_id,
                        accepted=True,
                        edited_text=section.original_text + " 提升80%吞吐量。",
                    )
                ],
                attest_truth=True,
            ),
        )
    assert exc_info.value.code == "RESUME_OPTIMIZATION_EDIT_INVALID"
    assert "80%" in exc_info.value.message
    material = db_session.get(GeneratedMaterial, optimization.id)
    assert material is not None
    assert material.status == "DRAFT"


def test_resume_optimization_edit_allows_preserved_number_in_original(
    db_session: Session,
    admin_user: User,
) -> None:
    """原文已有 ``80%`` 时，edited_text 保留该数字允许通过。"""
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    section = optimization.sections[0]
    # 篡改存储的 original_text 使其包含 ``80%``，模拟原文已有该数字。
    material = db_session.get(GeneratedMaterial, optimization.id)
    assert material is not None
    _tamper_stored_original_text(material, "Built services with 80% uptime.")
    db_session.flush()
    confirmed = service.confirm(
        admin_user.id,
        optimization.id,
        ResumeOptimizationConfirmPayload(
            sections=[
                ResumeOptimizationSectionConfirm(
                    source_section_id=section.source_section_id,
                    accepted=True,
                    edited_text="Built services with 80% uptime. Improved wording.",
                )
            ],
            attest_truth=True,
        ),
    )
    assert confirmed.status == "CONFIRMED"


def test_resume_optimization_edit_allows_number_substantiated_by_evidence(
    db_session: Session,
    admin_user: User,
) -> None:
    """evidence_text 中已有 ``80%`` 时，edited_text 引入 ``80%`` 允许通过。

    通过向匹配报告添加一条 ``MatchEvidence`` 记录(conclusion_key
    = ``num-proof``，resume_evidence 含 ``80%``)，并把章节 evidence_keys
    指向该 key，使证据解析命中。
    """
    from app.models.matching import MatchEvidence

    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    # 向匹配报告第一个 detail 添加一条含 ``80%`` 的证据。
    # 必须通过 relationship append(而非直接设 detail_id + add)，
    # 否则 SQLAlchemy 的 delete-orphan 级联会在后续 commit 时
    # 删除未被 in-memory 集合追踪的行。
    if report.details:
        proof = MatchEvidence(
            resume_evidence="Achieved 80% test coverage on core modules.",
            conclusion_key="num-proof",
            resume_source_id="num-proof-src",
            confidence=0.9,
        )
        report.details[0].evidence.append(proof)
        db_session.flush()

    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    section = optimization.sections[0]
    material = db_session.get(GeneratedMaterial, optimization.id)
    assert material is not None
    # 把章节 evidence_keys 指向 ``num-proof`` 以命中被添加的证据。
    _tamper_stored_evidence_keys(material, ["num-proof"])
    db_session.flush()
    confirmed = service.confirm(
        admin_user.id,
        optimization.id,
        ResumeOptimizationConfirmPayload(
            sections=[
                ResumeOptimizationSectionConfirm(
                    source_section_id=section.source_section_id,
                    accepted=True,
                    edited_text=section.original_text + " Achieved 80% coverage.",
                )
            ],
            attest_truth=True,
        ),
    )
    assert confirmed.status == "CONFIRMED"


# ---------------------------------------------------------------------------
# 17: Missing-skill alias/combo matching (Docker → Docker Compose)
# ---------------------------------------------------------------------------


def test_resume_optimization_keyword_rejects_docker_compose_when_docker_missing(
    db_session: Session,
    admin_user: User,
) -> None:
    """缺失技能 ``Docker`` 时，关键词建议 ``Docker Compose`` 被拒绝。

    直接调用 ``_validate_output`` 单元校验，避免 provider 层的副作用，
    确保校验逻辑本身能拦截组合写法。
    """
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    _add_missing_skill(report, "Docker")
    db_session.flush()

    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    version = report.resume_version
    job = report.job
    request = service._workflow_input(version, job, report)
    # 确认 Docker 确实进入了 missing_skills
    missing_names = {
        str(item.get("normalized_name") or item.get("job_raw_name") or "").lower()
        for item in request.match_report.missing_skills
    }
    assert "docker" in missing_names

    from app.schemas.resume_optimizations import (
        ResumeOptimizationGeneration,
        ResumeOptimizationKeywordSuggestion,
        ResumeOptimizationSectionOutput,
        ResumeOptimizationWorkflowOutput,
        SectionChangeType,
    )

    output = ResumeOptimizationWorkflowOutput(
        summary="test",
        sections=[
            ResumeOptimizationSectionOutput(
                section="工作经历",
                source_section_id="experience-1",
                original_text="Built services.",
                suggested_text="Built services.",
                reason="NO_CHANGE",
                change_type=SectionChangeType.NO_CHANGE,
            )
        ],
        keyword_suggestions=[
            ResumeOptimizationKeywordSuggestion(
                keyword="Docker Compose",
                reason="岗位要求",
                evidence_keys=[],
            )
        ],
        generation=ResumeOptimizationGeneration(
            workflow_version="test-v1",
            workflow_run_id="test-run",
        ),
    )
    with pytest.raises(AppError) as exc_info:
        service._validate_output(output, request, version)
    assert exc_info.value.code == "DIFY_OUTPUT_INVALID"
    assert "Docker" in exc_info.value.message


def test_resume_optimization_edit_rejects_docker_compose_when_docker_missing(
    db_session: Session,
    admin_user: User,
) -> None:
    """缺失技能 ``Docker`` 时，edited_text ``使用 Docker Compose`` 被拒绝。"""
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    _add_missing_skill(report, "Docker")
    db_session.flush()

    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    section = optimization.sections[0]
    with pytest.raises(AppError) as exc_info:
        service.confirm(
            admin_user.id,
            optimization.id,
            ResumeOptimizationConfirmPayload(
                sections=[
                    ResumeOptimizationSectionConfirm(
                        source_section_id=section.source_section_id,
                        accepted=True,
                        edited_text=section.original_text + " 使用 Docker Compose 部署。",
                    )
                ],
                attest_truth=True,
            ),
        )
    assert exc_info.value.code == "RESUME_OPTIMIZATION_EDIT_INVALID"
    assert "docker" in exc_info.value.message.lower()


# ---------------------------------------------------------------------------
# 18: Truth attestation requirement
# ---------------------------------------------------------------------------


def test_resume_optimization_confirm_rejects_edit_without_attest_truth(
    db_session: Session,
    admin_user: User,
) -> None:
    """有 edited_text 但未勾选真实性确认(attest_truth=False)时拒绝。"""
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    section = optimization.sections[0]
    with pytest.raises(AppError) as exc_info:
        service.confirm(
            admin_user.id,
            optimization.id,
            ResumeOptimizationConfirmPayload(
                sections=[
                    ResumeOptimizationSectionConfirm(
                        source_section_id=section.source_section_id,
                        accepted=True,
                        edited_text=section.original_text + " Improved wording.",
                    )
                ],
                attest_truth=False,
            ),
        )
    assert exc_info.value.code == "RESUME_OPTIMIZATION_EDIT_INVALID"
    assert "attest_truth" in exc_info.value.message
    material = db_session.get(GeneratedMaterial, optimization.id)
    assert material is not None
    assert material.status == "DRAFT"


def test_resume_optimization_confirm_accepts_edit_with_attest_truth(
    db_session: Session,
    admin_user: User,
) -> None:
    """勾选真实性确认且其他安全校验通过时允许确认，attest_truth 持久化。"""
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    section = optimization.sections[0]
    confirmed = service.confirm(
        admin_user.id,
        optimization.id,
        ResumeOptimizationConfirmPayload(
            sections=[
                ResumeOptimizationSectionConfirm(
                    source_section_id=section.source_section_id,
                    accepted=True,
                    edited_text=section.original_text + " Improved wording.",
                )
            ],
            attest_truth=True,
        ),
    )
    assert confirmed.status == "CONFIRMED"
    material = db_session.get(GeneratedMaterial, optimization.id)
    assert material is not None
    facts = material.facts_used or [{}]
    assert facts[0].get("attest_truth") is True


# ---------------------------------------------------------------------------
# 19: Shared matcher unit tests (Docker ↔ Docker Compose)
# ---------------------------------------------------------------------------


def test_skill_mentioned_docker_matches_docker_compose() -> None:
    """``Docker`` 应当能识别 ``Docker Compose``(前缀子序列匹配)。"""
    from app.services._fact_validation import skill_mentioned

    assert skill_mentioned("Docker", "使用 Docker Compose 部署") is True
    assert skill_mentioned("docker", "Docker-Compose pipeline") is True
    assert skill_mentioned("CI/CD", "CI/CD pipeline") is True
    # 反向:缺失技能 ``Docker Compose`` 不应误匹配只含 ``Docker`` 的文本
    assert skill_mentioned("Docker Compose", "Built with Docker") is False
    # 大小写 / 标点归一化
    assert skill_mentioned("Python", "Built PYTHON services.") is True


def test_extract_number_phrases_covers_common_units() -> None:
    """数字短语提取覆盖百分比、倍数、人数、时间等。"""
    from app.services._fact_validation import extract_number_phrases

    nums = extract_number_phrases("提升 80%，团队 5人，耗时 3个月，提升 2倍")
    assert "80%" in nums
    assert "5人" in nums
    assert "3个月" in nums
    assert "2倍" in nums


def test_resume_optimization_history_preserved(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    first = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    second = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    assert first.id != second.id
    first_material = db_session.get(GeneratedMaterial, first.id)
    assert first_material is not None
    assert first_material.status == "DRAFT"


# ---------------------------------------------------------------------------
# 16: Failed records are hidden from default list
# ---------------------------------------------------------------------------


def test_resume_optimization_list_hides_failed_by_default(
    db_session: Session,
    admin_user: User,
) -> None:
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    failing_service = ResumeOptimizationService(db_session, _EmptyOutputProvider())
    failed = failing_service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    assert failed.status == "FAILED"
    list_default = ResumeOptimizationService(
        db_session, FakeResumeOptimizationProvider()
    ).list_optimizations(admin_user.id, offset=0, limit=20)
    assert list_default.total == 0
    list_with_failed = ResumeOptimizationService(
        db_session, FakeResumeOptimizationProvider()
    ).list_optimizations(admin_user.id, offset=0, limit=20, include_failed=True)
    assert list_with_failed.total == 1


# ---------------------------------------------------------------------------
# 17: API key never appears in logs or state snapshots
# ---------------------------------------------------------------------------


def test_resume_optimization_no_api_key_in_state_snapshot(
    db_session: Session,
    admin_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Dify API key must never be persisted in run state snapshots."""
    monkeypatch.setenv(
        "DIFY_RESUME_OPTIMIZATION_API_KEY",
        "sk-secret-resume-optimization-key-do-not-log",
    )
    report_id = _successful_report(db_session, admin_user, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )
    service = ResumeOptimizationService(db_session, FakeResumeOptimizationProvider())
    optimization = service.create(
        admin_user.id,
        ResumeOptimizationCreate(
            resume_version_id=report.resume_version_id,
            job_id=report.job_id,
            match_report_id=report_id,
        ),
    )
    runs = db_session.scalars(
        select(AgentRun).where(AgentRun.run_type == "resume_optimization")
    ).all()
    assert runs
    secret = "sk-secret-resume-optimization-key-do-not-log"
    for run in runs:
        snapshot_text = json.dumps(run.state_snapshot, ensure_ascii=False)
        assert secret not in snapshot_text
        for step in run.steps:
            input_text = json.dumps(step.input_summary, ensure_ascii=False)
            output_text = json.dumps(step.output_summary, ensure_ascii=False)
            assert secret not in input_text
            assert secret not in output_text
    material = db_session.get(GeneratedMaterial, optimization.id)
    assert material is not None
    assert secret not in material.content
    assert secret not in json.dumps(material.facts_used, ensure_ascii=False)


# ---------------------------------------------------------------------------
# API-level tests
# ---------------------------------------------------------------------------


async def test_resume_optimization_api_full_flow(
    client: AsyncClient,
    db_session: Session,
) -> None:
    owner_headers = await _register_headers(client, "resume-opt-owner@example.com")
    owner = db_session.scalar(select(User).where(User.email == "resume-opt-owner@example.com"))
    assert owner is not None
    report_id = _successful_report(db_session, owner, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )

    empty = await client.get("/api/resume-optimizations", headers=owner_headers)
    assert empty.status_code == 200
    assert empty.json()["data"]["total"] == 0

    created = await client.post(
        "/api/resume-optimizations",
        headers=owner_headers,
        json={
            "resume_version_id": report.resume_version_id,
            "job_id": report.job_id,
            "match_report_id": report_id,
        },
    )
    assert created.status_code == 201, created.text
    optimization_id = created.json()["data"]["id"]
    assert created.json()["data"]["status"] == "DRAFT"
    assert created.json()["data"]["provider"] == "fake"

    fetched = await client.get(
        f"/api/resume-optimizations/{optimization_id}", headers=owner_headers
    )
    assert fetched.status_code == 200
    assert fetched.json()["data"]["id"] == optimization_id

    # Confirm one section
    section = created.json()["data"]["sections"][0]
    confirmed = await client.post(
        f"/api/resume-optimizations/{optimization_id}/confirm",
        headers=owner_headers,
        json={
            "sections": [
                {
                    "source_section_id": section["source_section_id"],
                    "accepted": True,
                }
            ]
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["data"]["status"] == "CONFIRMED"

    # Create new version
    new_version = await client.post(
        f"/api/resume-optimizations/{optimization_id}/create-version",
        headers=owner_headers,
    )
    assert new_version.status_code == 201, new_version.text
    assert new_version.json()["data"]["applied_section_count"] >= 1


async def test_resume_optimization_api_owner_isolation(
    client: AsyncClient,
    db_session: Session,
) -> None:
    owner_headers = await _register_headers(client, "opt-owner@example.com")
    other_headers = await _register_headers(client, "opt-other@example.com")
    owner = db_session.scalar(select(User).where(User.email == "opt-owner@example.com"))
    assert owner is not None
    report_id = _successful_report(db_session, owner, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )

    created = await client.post(
        "/api/resume-optimizations",
        headers=owner_headers,
        json={
            "resume_version_id": report.resume_version_id,
            "job_id": report.job_id,
            "match_report_id": report_id,
        },
    )
    assert created.status_code == 201
    optimization_id = created.json()["data"]["id"]

    hidden = await client.get(f"/api/resume-optimizations/{optimization_id}", headers=other_headers)
    assert hidden.status_code == 404


async def test_resume_optimization_api_create_version_requires_confirmation(
    client: AsyncClient,
    db_session: Session,
) -> None:
    owner_headers = await _register_headers(client, "opt-confirm@example.com")
    owner = db_session.scalar(select(User).where(User.email == "opt-confirm@example.com"))
    assert owner is not None
    report_id = _successful_report(db_session, owner, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )

    created = await client.post(
        "/api/resume-optimizations",
        headers=owner_headers,
        json={
            "resume_version_id": report.resume_version_id,
            "job_id": report.job_id,
            "match_report_id": report_id,
        },
    )
    assert created.status_code == 201
    optimization_id = created.json()["data"]["id"]

    # Without confirmation, create-version must fail
    failed = await client.post(
        f"/api/resume-optimizations/{optimization_id}/create-version",
        headers=owner_headers,
    )
    assert failed.status_code == 409


async def test_resume_optimization_api_confirm_rejects_missing_skill_in_edit(
    client: AsyncClient,
    db_session: Session,
) -> None:
    """The confirm endpoint must return 422 when edited_text introduces a
    missing skill, and the material must remain DRAFT."""
    owner_headers = await _register_headers(client, "opt-edit@example.com")
    owner = db_session.scalar(select(User).where(User.email == "opt-edit@example.com"))
    assert owner is not None
    report_id = _successful_report(db_session, owner, "skill_gap")
    report = db_session.get(
        __import__("app.models.matching", fromlist=["MatchReport"]).MatchReport,
        report_id,
    )

    created = await client.post(
        "/api/resume-optimizations",
        headers=owner_headers,
        json={
            "resume_version_id": report.resume_version_id,
            "job_id": report.job_id,
            "match_report_id": report_id,
        },
    )
    assert created.status_code == 201, created.text
    optimization_id = created.json()["data"]["id"]
    section = created.json()["data"]["sections"][0]
    missing_name = _first_missing_skill_not_in_original(report, section["original_text"])

    rejected = await client.post(
        f"/api/resume-optimizations/{optimization_id}/confirm",
        headers=owner_headers,
        json={
            "sections": [
                {
                    "source_section_id": section["source_section_id"],
                    "accepted": True,
                    "edited_text": f"Built services. Now expert in {missing_name}.",
                }
            ]
        },
    )
    assert rejected.status_code == 422, rejected.text
    assert rejected.json()["error"]["code"] == "RESUME_OPTIMIZATION_EDIT_INVALID"

    # The material is still DRAFT and can be confirmed cleanly afterwards.
    still_draft = await client.get(
        f"/api/resume-optimizations/{optimization_id}", headers=owner_headers
    )
    assert still_draft.status_code == 200
    assert still_draft.json()["data"]["status"] == "DRAFT"
    assert still_draft.json()["data"]["is_human_confirmed"] is False
