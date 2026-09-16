"""Service layer for resume optimization (Stage 3).

The service orchestrates:

* Building the Dify workflow input strictly from real database rows
  (resume version, job, match report). Front-end supplied resume content
  is never trusted directly.
* Calling the resume optimization provider with retries handled inside
  the provider.
* Validating the returned output against the anti-fabrication rules
  defined in the stage spec. Validation is enforced server-side and is
  not solely reliant on the prompt.
* Persisting the optimization record as a ``GeneratedMaterial`` row
  with status ``DRAFT`` (or ``FAILED`` on error), plus an ``AgentRun``
  / ``AgentStep`` / ``ModelUsageLog`` audit trail.
* Confirming user-accepted suggestions and creating a new immutable
  resume version that only applies accepted section suggestions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.integrations.dify.resume_optimization_providers import (
    ResumeOptimizationProvider,
)
from app.job_sources.source_names import canonical_source_name, is_discovery_platform
from app.models.career import GeneratedMaterial
from app.models.enums import TaskStatus
from app.models.matching import MatchReport
from app.models.operations import AgentRun, AgentStep, AuditLog, ModelUsageLog
from app.models.resumes import ResumeVersion
from app.repositories.resume_optimizations import ResumeOptimizationRepository
from app.schemas.resume import ResumeProfile
from app.schemas.resume_optimizations import (
    ResumeOptimizationConfirmPayload,
    ResumeOptimizationCreate,
    ResumeOptimizationCreateVersionResult,
    ResumeOptimizationGeneration,
    ResumeOptimizationKeywordSuggestionRead,
    ResumeOptimizationListRead,
    ResumeOptimizationProviderResult,
    ResumeOptimizationRead,
    ResumeOptimizationSectionConfirm,
    ResumeOptimizationSectionOutput,
    ResumeOptimizationSectionRead,
    ResumeOptimizationStatus,
    ResumeOptimizationWorkflowInput,
    ResumeOptimizationWorkflowOutput,
)
from app.services._fact_validation import (
    extract_number_phrases,
    skill_mentioned,
)

MATERIAL_TYPE_RESUME_OPTIMIZATION = "resume_optimization"
RUN_TYPE_RESUME_OPTIMIZATION = "resume_optimization"

# Anti-fabrication utilities (``skill_mentioned``, ``extract_number_phrases``,
# ``assert_no_missing_skills``, ``find_unsubstantiated_numbers``) are imported
# from ``app.services._fact_validation``. See that module for documentation.


class ResumeOptimizationService:
    def __init__(
        self,
        session: Session,
        provider: ResumeOptimizationProvider,
    ) -> None:
        self.session = session
        self.provider = provider
        self.repository = ResumeOptimizationRepository(session)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(
        self,
        user_id: int,
        payload: ResumeOptimizationCreate,
    ) -> ResumeOptimizationRead:
        """Generate a new resume optimization suggestion set."""
        report = self._owned_successful_report(payload.match_report_id, user_id)
        self._validate_input_relationships(payload, report, user_id)
        version = self._owned_confirmed_version(payload.resume_version_id, user_id)
        job = self.repository.get_owned_job(payload.job_id, user_id)
        if job is None:
            raise AppError("JOB_NOT_FOUND", "The job was not found", 404)
        request = self._workflow_input(version, job, report)
        run = self._start_run(user_id, request)
        started = perf_counter()
        try:
            result = self.provider.generate_optimization(request)
            self._validate_output(result.output, request, version)
            material = self._persist_success(
                user_id,
                version,
                job,
                report,
                result,
                run,
                started,
            )
            self._audit(
                user_id,
                "RESUME_OPTIMIZATION_CREATED",
                material.id,
                {
                    "resume_version_id": version.id,
                    "job_id": job.id,
                    "match_report_id": report.id,
                },
            )
            self.session.commit()
            return self._read(material, run)
        except AppError as exc:
            material = self._persist_failure(
                user_id,
                version,
                job,
                report,
                run,
                started,
                exc.code,
                exc.message,
            )
            self.session.commit()
            if exc.status_code >= 500:
                return self._read(material, run)
            raise
        except Exception:
            material = self._persist_failure(
                user_id,
                version,
                job,
                report,
                run,
                started,
                "RESUME_OPTIMIZATION_GENERATION_FAILED",
                "The resume optimization could not be generated",
            )
            self.session.commit()
            return self._read(material, run)

    def list_optimizations(
        self,
        user_id: int,
        *,
        offset: int,
        limit: int,
        include_failed: bool = False,
    ) -> ResumeOptimizationListRead:
        rows, total = self.repository.list_owned(
            user_id=user_id,
            offset=offset,
            limit=limit,
            include_failed=include_failed,
        )
        run_by_material = self._run_by_material(user_id)
        return ResumeOptimizationListRead(
            items=[self._read(row, run_by_material.get(row.id)) for row in rows],
            total=total,
            offset=offset,
            limit=limit,
        )

    def get(self, user_id: int, material_id: int) -> ResumeOptimizationRead:
        material = self._owned_material(material_id, user_id)
        run = self.repository.latest_run_for_material(material.id, user_id)
        return self._read(material, run)

    def confirm(
        self,
        user_id: int,
        material_id: int,
        payload: ResumeOptimizationConfirmPayload,
    ) -> ResumeOptimizationRead:
        material = self._owned_material(material_id, user_id)
        if material.status == ResumeOptimizationStatus.FAILED.value:
            raise AppError(
                "RESUME_OPTIMIZATION_FAILED",
                "Failed optimizations cannot be confirmed",
                409,
            )
        if material.status == ResumeOptimizationStatus.ARCHIVED.value:
            raise AppError(
                "RESUME_OPTIMIZATION_ARCHIVED",
                "Archived optimizations cannot be confirmed",
                409,
            )
        if material.status == ResumeOptimizationStatus.CONFIRMED.value:
            raise AppError(
                "RESUME_OPTIMIZATION_ALREADY_CONFIRMED",
                "Optimization already confirmed",
                409,
            )
        stored = self._stored_output(material)
        self._validate_confirm_payload(stored, payload)
        merged_sections = self._merge_confirmations(stored.sections, payload.sections)
        # 加载父简历版本,供数字事实校验解析 evidence_text 使用。
        parent_version: ResumeVersion | None = None
        if material.resume_version_id is not None:
            parent_version = self.repository.get_owned_resume_version(
                material.resume_version_id, user_id
            )
        # Re-run anti-fabrication checks on user-edited text. The original
        # ``_validate_output`` gate only inspects Dify's ``suggested_text``;
        # ``edited_text`` bypasses it, so a user must not be able to claim
        # a missing skill (which the match report says they lack) via the
        # edit path. The same gate enforces number-fact substantiation
        # and the truth attestation for free-text edits.
        self._revalidate_edited_sections(
            stored,
            merged_sections,
            self._missing_skill_names_from_material(material),
            attest_truth=payload.attest_truth,
            parent_version=parent_version,
            material=material,
        )
        material.facts_used = self._facts_used_with_confirmation(
            stored, merged_sections, payload.attest_truth
        )
        # Keep ``content`` as the canonical Dify workflow output
        # (``ResumeOptimizationWorkflowOutput`` schema). The user's
        # accept / reject / edit state is persisted separately in
        # ``facts_used`` so the strict output schema still validates
        # when ``create_version`` re-reads it later.
        material.is_human_confirmed = True
        material.status = ResumeOptimizationStatus.CONFIRMED.value
        self._audit(user_id, "RESUME_OPTIMIZATION_CONFIRMED", material.id, {})
        self.session.commit()
        run = self.repository.latest_run_for_material(material.id, user_id)
        return self._read(material, run)

    def retry(self, user_id: int, material_id: int) -> ResumeOptimizationRead:
        material = self._owned_material(material_id, user_id)
        if material.status != ResumeOptimizationStatus.FAILED.value:
            raise AppError(
                "RESUME_OPTIMIZATION_RETRY_NOT_ALLOWED",
                "Only failed optimizations can be retried",
                409,
            )
        if (
            material.resume_version_id is None
            or material.job_id is None
            or material.match_report_id is None
        ):
            raise AppError(
                "RESUME_OPTIMIZATION_SOURCE_MISSING",
                "The source resume version, job or match report is missing",
                409,
            )
        return self.create(
            user_id,
            ResumeOptimizationCreate(
                resume_version_id=material.resume_version_id,
                job_id=material.job_id,
                match_report_id=material.match_report_id,
            ),
        )

    def create_version(
        self,
        user_id: int,
        material_id: int,
    ) -> ResumeOptimizationCreateVersionResult:
        """Apply the user-confirmed suggestions to a new immutable version.

        The original ``ResumeVersion`` is never modified. A new
        ``ResumeVersion`` row is created with ``parent_version_id`` set
        to the source version, and ``is_current`` is set to ``False``
        unless the caller explicitly promotes it later.
        """
        material = self._owned_material(material_id, user_id)
        if material.status != ResumeOptimizationStatus.CONFIRMED.value:
            raise AppError(
                "RESUME_OPTIMIZATION_NOT_CONFIRMED",
                "Only confirmed optimizations can produce a new version",
                409,
            )
        if material.resume_version_id is None:
            raise AppError(
                "RESUME_OPTIMIZATION_SOURCE_MISSING",
                "The source resume version is missing",
                409,
            )
        parent_version = self.repository.get_owned_resume_version(
            material.resume_version_id, user_id
        )
        if parent_version is None:
            raise AppError(
                "RESUME_VERSION_NOT_FOUND",
                "The parent resume version was not found",
                404,
            )
        stored = self._stored_output(material)
        merged_sections = self._sections_from_confirmed(material, stored)
        # Defense-in-depth: re-run anti-fabrication checks on the edited
        # text persisted in ``facts_used`` so a tampered or stale
        # confirmation cannot introduce a missing skill when the new
        # version is built. ``confirm`` already validates this, but
        # ``create_version`` is the final gate before the new profile is
        # materialised. The attestation flag is read back from the
        # persisted audit metadata.
        persisted_attest = self._attest_truth_from_facts(material)
        self._revalidate_edited_sections(
            stored,
            merged_sections,
            self._missing_skill_names_from_material(material),
            attest_truth=persisted_attest,
            parent_version=parent_version,
            material=material,
        )
        new_profile = self._apply_suggestions_to_profile(parent_version, merged_sections)
        new_version = ResumeVersion(
            resume_id=parent_version.resume_id,
            version_number=self.repository.next_version_number(parent_version.resume_id),
            raw_text=parent_version.raw_text,
            structured_data=new_profile.model_dump(mode="json"),
            is_current=False,
            is_confirmed=False,
            parent_version_id=parent_version.id,
        )
        self.session.add(new_version)
        self.session.flush()
        material.status = ResumeOptimizationStatus.ARCHIVED.value
        self._audit(
            user_id,
            "RESUME_OPTIMIZATION_VERSION_CREATED",
            material.id,
            {
                "new_resume_version_id": new_version.id,
                "parent_resume_version_id": parent_version.id,
            },
        )
        self.session.commit()
        self.session.refresh(new_version)
        return ResumeOptimizationCreateVersionResult(
            resume_version={
                "id": new_version.id,
                "resume_id": new_version.resume_id,
                "version_number": new_version.version_number,
                "parent_version_id": new_version.parent_version_id,
                "is_current": new_version.is_current,
                "is_confirmed": new_version.is_confirmed,
            },
            applied_section_count=sum(1 for item in merged_sections if item.accepted),
            parent_version_id=parent_version.id,
        )

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _owned_successful_report(self, report_id: int, user_id: int) -> MatchReport:
        report = self.repository.get_owned_match_report(report_id, user_id)
        if report is None:
            raise AppError("MATCH_NOT_FOUND", "The match report was not found", 404)
        if report.status != TaskStatus.SUCCEEDED:
            raise AppError(
                "MATCH_REPORT_NOT_READY",
                "Only successful match reports can drive resume optimization",
                409,
            )
        return report

    def _owned_confirmed_version(
        self,
        version_id: int,
        user_id: int,
    ) -> ResumeVersion:
        version = self.repository.get_owned_resume_version(version_id, user_id)
        if version is None:
            raise AppError("RESUME_VERSION_NOT_FOUND", "The resume version was not found", 404)
        if not version.is_confirmed:
            raise AppError(
                "RESUME_VERSION_NOT_CONFIRMED",
                "Only confirmed resume versions can be optimized",
                409,
            )
        return version

    def _owned_material(
        self,
        material_id: int,
        user_id: int,
    ) -> GeneratedMaterial:
        material = self.repository.get_owned_material(material_id, user_id)
        if material is None:
            raise AppError(
                "RESUME_OPTIMIZATION_NOT_FOUND",
                "The resume optimization record was not found",
                404,
            )
        return material

    def _validate_input_relationships(
        self,
        payload: ResumeOptimizationCreate,
        report: MatchReport,
        user_id: int,
    ) -> None:
        """The resume version, job and match report must be mutually linked."""
        if report.resume_version_id != payload.resume_version_id:
            raise AppError(
                "RESUME_OPTIMIZATION_INPUT_MISMATCH",
                "The match report does not reference the supplied resume version",
                409,
            )
        if report.job_id != payload.job_id:
            raise AppError(
                "RESUME_OPTIMIZATION_INPUT_MISMATCH",
                "The match report does not reference the supplied job",
                409,
            )
        version = self.repository.get_owned_resume_version(payload.resume_version_id, user_id)
        if version is None:
            raise AppError("RESUME_VERSION_NOT_FOUND", "The resume version was not found", 404)

    def _validate_output(
        self,
        output: ResumeOptimizationWorkflowOutput,
        request: ResumeOptimizationWorkflowInput,
        version: ResumeVersion,
    ) -> None:
        """Server-side anti-fabrication checks (not prompt-only).

        Verifies:

        * ``evidence_keys`` reference real resume evidence in the
          current resume version.
        * ``source_section_id`` is one of the section identifiers
          derived from the resume version.
        * ``suggested_text`` does not introduce a missing skill (a skill
          the match report says the user lacks) as if the user had
          already mastered it.
        * Missing-skill names never appear in ``keyword_suggestions``
          as if the user already has them.

        Note: arbitrary "unknown skill" detection (a skill that is not
        in the resume, not matched, not partial and not missing) is not
        enforced because it requires a comprehensive skill dictionary.
        """
        allowed_section_ids = self._allowed_section_ids(version)
        allowed_evidence_keys = self._allowed_evidence_keys(request, version)
        missing_skill_names = {
            str(item.get("normalized_name") or item.get("job_raw_name") or "").lower()
            for item in request.match_report.missing_skills
            if item.get("normalized_name") or item.get("job_raw_name")
        }
        for section in output.sections:
            if section.source_section_id not in allowed_section_ids:
                raise AppError(
                    "DIFY_OUTPUT_INVALID",
                    (
                        "source_section_id '"
                        + section.source_section_id
                        + "' does not belong to the current resume version"
                    ),
                    502,
                )
            for key in section.evidence_keys:
                if key not in allowed_evidence_keys:
                    raise AppError(
                        "DIFY_OUTPUT_INVALID",
                        (
                            "evidence_key '"
                            + key
                            + "' does not match any evidence in the current resume version"
                        ),
                        502,
                    )
            self._assert_no_missing_skills(
                section.suggested_text,
                section.original_text,
                missing_skill_names,
                context=f"section '{section.section}' suggested_text",
            )
            # Note: arbitrary "unknown skill" detection (a skill not in
            # the resume, not matched, not partial, not missing) is
            # intentionally NOT enforced here. Detecting novel skill
            # claims in free text requires a comprehensive skill
            # dictionary / NLP, which is out of scope for the
            # deterministic-v1.1 stage. The enforceable, dictionary-free
            # guard is the missing-skill check above; the strict prompt
            # and Pydantic schema are the remaining controls.
        for kw in output.keyword_suggestions:
            for key in kw.evidence_keys:
                if key not in allowed_evidence_keys:
                    raise AppError(
                        "DIFY_OUTPUT_INVALID",
                        (
                            "keyword suggestion evidence_key '"
                            + key
                            + "' does not match any resume evidence"
                        ),
                        502,
                    )
            # 关键词建议不得是把缺失技能写成用户已有技能。复用共享
            # ``_skill_mentioned`` 匹配器，使 ``Docker`` 能拦截关键词
            # ``Docker Compose``(缺失技能作为前缀子序列被识别)。
            if any(skill_mentioned(name, kw.keyword) for name in missing_skill_names):
                raise AppError(
                    "DIFY_OUTPUT_INVALID",
                    (
                        "keyword '"
                        + kw.keyword
                        + "' is a missing skill and cannot be added to the resume"
                    ),
                    502,
                )

    def _assert_no_missing_skills(
        self,
        text: str,
        original_text: str,
        missing_skill_names: set[str],
        *,
        context: str,
    ) -> None:
        """Reject suggestions that introduce a missing skill as if mastered.

        使用共享的 ``_skill_mentioned`` 归一化匹配器，使 ``Docker`` 能
        识别 ``Docker Compose``、``CI/CD`` 能识别 ``CI/CD pipeline`` 等
        组合写法。一个缺失技能若已出现在 ``original_text`` 中，则视为
        用户原有内容保留，不触发拒绝;仅当 ``text`` 新引入该缺失技能
        (原文未提及)时才拒绝。这样既能阻止 LLM 把缺失技能改写成
        已掌握，也不会误判用户保留自身原文的情况。
        """
        for name in missing_skill_names:
            if not name:
                continue
            if skill_mentioned(name, text) and not skill_mentioned(name, original_text):
                raise AppError(
                    "DIFY_OUTPUT_INVALID",
                    ("Missing skill '" + name + "' must not appear in " + context),
                    502,
                )

    def _allowed_section_ids(self, version: ResumeVersion) -> set[str]:
        """Return the set of valid ``source_section_id`` values.

        The resume profile stored in ``structured_data`` is divided into
        sections with deterministic identifiers (``summary``, ``experience-N``,
        ``project-N``, ``education-N``, ``skill-N``). Suggestions must
        reference one of these — they cannot invent sections.
        """
        ids: set[str] = {"summary"}
        try:
            profile = ResumeProfile.model_validate(version.structured_data)
        except Exception:
            return ids
        for index, _ in enumerate(profile.work_experience, start=1):
            ids.add(f"experience-{index}")
        for index, _ in enumerate(profile.project_experience, start=1):
            ids.add(f"project-{index}")
        for index, _ in enumerate(profile.education, start=1):
            ids.add(f"education-{index}")
        for index, _ in enumerate(profile.technical_skills, start=1):
            ids.add(f"skill-{index}")
        return ids

    def _allowed_evidence_keys(
        self,
        request: ResumeOptimizationWorkflowInput,
        version: ResumeVersion,
    ) -> set[str]:
        """Evidence keys come from the match report evidence and the
        resume skill evidence identifiers.

        We accept any evidence key that was sent to the Dify workflow
        in ``match_report.evidence`` (so the LLM can reference them) as
        well as synthetic ``resume-evidence-N`` identifiers derived from
        the resume skill evidence text.
        """
        keys: set[str] = set()
        for item in request.match_report.evidence:
            for field in ("resume_evidence", "conclusion_key", "resume_source_id"):
                value = item.get(field)
                if isinstance(value, str) and value:
                    keys.add(value)
        for index in range(1, len(version.structured_data.get("technical_skills", []) or []) + 1):
            keys.add(f"resume-evidence-{index}")
        return keys

    def _validate_confirm_payload(
        self,
        stored: ResumeOptimizationWorkflowOutput,
        payload: ResumeOptimizationConfirmPayload,
    ) -> None:
        valid_section_ids = {section.source_section_id for section in stored.sections}
        for item in payload.sections:
            if item.source_section_id not in valid_section_ids:
                raise AppError(
                    "RESUME_OPTIMIZATION_CONFIRM_INVALID",
                    (
                        "source_section_id '"
                        + item.source_section_id
                        + "' does not match any suggestion"
                    ),
                    422,
                )
            if item.accepted and item.edited_text is not None and not item.edited_text.strip():
                raise AppError(
                    "RESUME_OPTIMIZATION_CONFIRM_INVALID",
                    "edited_text cannot be empty when accepted",
                    422,
                )

    def _missing_skill_names_from_material(
        self,
        material: GeneratedMaterial,
    ) -> set[str]:
        """Reconstruct the missing-skill name set for re-validation.

        The original ``_validate_output`` gate had the workflow request
        in scope; ``confirm`` and ``create_version`` do not, so the
        missing-skill names are rebuilt from the persisted match report
        linked to the material. This lets the anti-fabrication check run
        again on user-edited text without re-building the full request.
        """
        if material.match_report_id is None:
            return set()
        report = self.session.get(MatchReport, material.match_report_id)
        if report is None:
            return set()
        names: set[str] = set()
        for item in report.missing_skills or []:
            name = str(item.get("normalized_name") or item.get("job_raw_name") or "")
            if name:
                names.add(name.lower())
        return names

    def _attest_truth_from_facts(self, material: GeneratedMaterial) -> bool:
        """从持久化的 ``facts_used`` 审计元数据中读回真实性声明。

        ``confirm`` 写入 ``attest_truth``;``create_version`` 重校时
        读回，确保纵深防御使用与确认时一致的声明状态。缺失或类型
        异常时安全回退为 ``False``(拒绝 edited_text)。
        """
        facts = material.facts_used or []
        if not facts or not isinstance(facts, list):
            return False
        first = facts[0]
        if not isinstance(first, dict):
            return False
        return bool(first.get("attest_truth", False))

    def _revalidate_edited_sections(
        self,
        stored: ResumeOptimizationWorkflowOutput,
        merged_sections: list[ResumeOptimizationSectionRead],
        missing_skill_names: set[str],
        *,
        attest_truth: bool = False,
        parent_version: ResumeVersion | None = None,
        material: GeneratedMaterial | None = None,
    ) -> None:
        """对用户 ``edited_text`` 重新执行全部防虚构校验。

        仅检查被接受(``accepted``)且携带非空 ``edited_text`` 的章节。
        对未被编辑的章节，``create_version`` 会落库的是已经过
        ``_validate_output`` 校验的 ``suggested_text``，无需重校。

        本方法执行三类校验:

        1. **真实性声明**:若任何章节携带 ``edited_text``，则
           ``attest_truth`` 必须为 ``True``。这覆盖公司、项目、证书等
           确定性代码无法完整识别的自由文本事实。
        2. **缺失技能**:复用共享 ``_skill_mentioned`` 匹配器，使
           ``Docker`` 能识别 ``Docker Compose``。若原文已有该缺失技能
           则视为保留用户内容放行;仅当 edited_text **新引入** 缺失技能
           时拒绝。
        3. **数字事实**:提取 original_text 与 evidence_text 中的数字
           短语(百分比、金额、人数、倍数、时间、数量等)，edited_text
           新增的数字必须已存在于 original_text 或 evidence_text 中，
           否则视为虚构数字成果拒绝。

        所有失败统一抛 ``RESUME_OPTIMIZATION_EDIT_INVALID`` (422)，
        因为编辑内容的来源是用户而非 Dify。
        """
        original_by_id = {
            section.source_section_id: section.original_text for section in stored.sections
        }
        evidence_keys_by_id = {
            section.source_section_id: list(section.evidence_keys) for section in stored.sections
        }
        has_any_edit = False
        for item in merged_sections:
            if not item.accepted:
                continue
            if not item.edited_text or not item.edited_text.strip():
                continue
            has_any_edit = True
            original = original_by_id.get(item.source_section_id, "")
            # --- 1. 真实性声明在循环外统一校验，这里先收集 has_any_edit ---

            # --- 2. 缺失技能(共享匹配器) ---
            for name in missing_skill_names:
                if not name:
                    continue
                if skill_mentioned(name, item.edited_text) and not skill_mentioned(name, original):
                    raise AppError(
                        "RESUME_OPTIMIZATION_EDIT_INVALID",
                        (
                            "edited_text for section '"
                            + item.section
                            + "' must not introduce the missing skill '"
                            + name
                            + "'"
                        ),
                        422,
                    )

            # --- 3. 数字事实 ---
            evidence_text = self._evidence_text_for_section(
                evidence_keys_by_id.get(item.source_section_id, []),
                parent_version,
                material,
            )
            allowed_numbers = extract_number_phrases(original) | extract_number_phrases(
                evidence_text
            )
            edited_numbers = extract_number_phrases(item.edited_text)
            new_numbers = edited_numbers - allowed_numbers
            if new_numbers:
                raise AppError(
                    "RESUME_OPTIMIZATION_EDIT_INVALID",
                    (
                        "edited_text for section '"
                        + item.section
                        + "' introduces unsubstantiated numbers: "
                        + ", ".join(sorted(new_numbers))
                        + ". Each new number must already appear in the original "
                        + "text or in the cited resume evidence."
                    ),
                    422,
                )

        # --- 1. 真实性声明(覆盖自由文本事实) ---
        if has_any_edit and not attest_truth:
            raise AppError(
                "RESUME_OPTIMIZATION_EDIT_INVALID",
                "Confirming edited text requires attesting that the manually-edited "
                "content is真实准确 and can be substantiated on request "
                "(set attest_truth=true).",
                422,
            )

    def _evidence_text_for_section(
        self,
        evidence_keys: list[str],
        parent_version: ResumeVersion | None,
        material: GeneratedMaterial | None,
    ) -> str:
        """将章节的 ``evidence_keys`` 解析为可读的证据文本拼接。

        支持两类 key:

        * ``resume-evidence-N``:对应 ``parent_version.structured_data``
          中第 N 个 technical_skill 的 ``evidence_text``。
        * 其他字符串:视为匹配报告证据的 ``conclusion_key`` /
          ``resume_source_id`` / ``resume_evidence``，从匹配报告
          ``details[].evidence[]`` 中按字段值匹配并取
          ``resume_evidence`` 文本。

        无法解析的 key 安全忽略(不贡献证据文本，等价于空字符串)。
        ``parent_version`` 在 ``create_version`` 路径必传;``confirm``
        路径可能为 ``None``，此时仅解析匹配报告证据。
        """
        if not evidence_keys:
            return ""
        key_set = set(evidence_keys)
        parts: list[str] = []

        # resume-evidence-N → technical_skills[N-1].evidence_text
        if parent_version is not None:
            tech_skills = parent_version.structured_data.get("technical_skills") or []
            for key in evidence_keys:
                if isinstance(key, str) and key.startswith("resume-evidence-"):
                    try:
                        index = int(key.rsplit("-", 1)[-1])
                    except ValueError:
                        continue
                    if 1 <= index <= len(tech_skills):
                        skill = tech_skills[index - 1]
                        if isinstance(skill, dict):
                            value = skill.get("evidence_text")
                            if isinstance(value, str) and value:
                                parts.append(value)

        # 匹配报告证据:从 material.match_report_id 解析
        if material is None or material.match_report_id is None:
            return " ".join(parts)
        report = self.session.get(MatchReport, material.match_report_id)
        if report is None:
            return " ".join(parts)
        for detail in report.details or []:
            for evidence in detail.evidence or []:
                # evidence 可能是 MatchEvidence ORM 对象或 dict，
                # 统一用 getattr / .get 兼容两种形态。
                conclusion_key = (
                    getattr(evidence, "conclusion_key", None)
                    if not isinstance(evidence, dict)
                    else evidence.get("conclusion_key")
                )
                resume_source_id = (
                    getattr(evidence, "resume_source_id", None)
                    if not isinstance(evidence, dict)
                    else evidence.get("resume_source_id")
                )
                resume_evidence_field = (
                    getattr(evidence, "resume_evidence", None)
                    if not isinstance(evidence, dict)
                    else evidence.get("resume_evidence")
                )
                matched = False
                for value in (conclusion_key, resume_source_id, resume_evidence_field):
                    if isinstance(value, str) and value in key_set:
                        matched = True
                        break
                if matched and isinstance(resume_evidence_field, str) and resume_evidence_field:
                    parts.append(resume_evidence_field)
        return " ".join(parts)

    def _merge_confirmations(
        self,
        sections: list[ResumeOptimizationSectionOutput],
        confirmations: list[ResumeOptimizationSectionConfirm],
    ) -> list[ResumeOptimizationSectionRead]:
        confirmation_by_id = {item.source_section_id: item for item in confirmations}
        merged: list[ResumeOptimizationSectionRead] = []
        for section in sections:
            confirmation = confirmation_by_id.get(section.source_section_id)
            accepted = bool(confirmation and confirmation.accepted)
            edited_text = confirmation.edited_text if confirmation else None
            merged.append(
                ResumeOptimizationSectionRead(
                    section=section.section,
                    source_section_id=section.source_section_id,
                    original_text=section.original_text,
                    suggested_text=section.suggested_text,
                    reason=section.reason,
                    related_job_requirement=section.related_job_requirement,
                    evidence_keys=list(section.evidence_keys),
                    change_type=section.change_type,
                    accepted=accepted,
                    edited_text=edited_text,
                )
            )
        return merged

    def _sections_from_confirmed(
        self,
        material: GeneratedMaterial,
        stored: ResumeOptimizationWorkflowOutput,
    ) -> list[ResumeOptimizationSectionRead]:
        facts = material.facts_used or []
        sections_data = facts[0].get("sections") if facts else None
        if not isinstance(sections_data, list):
            return []
        result: list[ResumeOptimizationSectionRead] = []
        for item in sections_data:
            if not isinstance(item, dict):
                continue
            try:
                result.append(ResumeOptimizationSectionRead.model_validate(item))
            except Exception:
                continue
        return result

    # ------------------------------------------------------------------
    # Workflow input building
    # ------------------------------------------------------------------

    def _workflow_input(
        self,
        version: ResumeVersion,
        job: Any,
        report: MatchReport,
    ) -> ResumeOptimizationWorkflowInput:
        from app.schemas.resume_optimizations import (
            ResumeOptimizationJobInput,
            ResumeOptimizationMatchReportInput,
            ResumeOptimizationResumeInput,
        )

        profile_data = version.structured_data or {}
        summary_value = profile_data.get("summary") or {}
        summary_text = (
            summary_value.get("value")
            if isinstance(summary_value, dict)
            else str(summary_value or "")
        )
        resume_input = ResumeOptimizationResumeInput(
            resume_version_id=version.id,
            summary=str(summary_text or "")[:4000],
            education=list(profile_data.get("education", []) or []),
            experiences=list(profile_data.get("work_experience", []) or []),
            projects=list(profile_data.get("project_experience", []) or []),
            skills=list(profile_data.get("technical_skills", []) or []),
            evidence=self._resume_evidence(profile_data, version),
        )
        source_name = ""
        is_summary_only = False
        if job.source is not None:
            source_name = canonical_source_name(job.source.name) or job.source.name
            is_summary_only = is_discovery_platform(job.source.name)
        completeness = self._job_information_completeness(report)
        job_input = ResumeOptimizationJobInput(
            job_id=job.id,
            title=job.title,
            company=job.company,
            summary=self._job_summary(job),
            source_name=source_name,
            source_url=job.source_url,
            information_completeness=completeness,
            is_summary_only=is_summary_only,
        )
        match_input = ResumeOptimizationMatchReportInput(
            report_id=report.id,
            final_score=report.final_score,
            matched_skills=self._json_list(report.matched_skills),
            partial_skills=self._json_list(report.partial_skills),
            missing_skills=self._json_list(report.missing_skills),
            blocking_risks=self._json_list(report.hard_constraint_warnings),
            evidence=self._match_evidence(report),
        )
        return ResumeOptimizationWorkflowInput(
            resume=resume_input,
            job=job_input,
            match_report=match_input,
        )

    def _resume_evidence(
        self,
        profile_data: dict[str, Any],
        version: ResumeVersion,
    ) -> list[dict[str, Any]]:
        """Synthesise evidence rows from the resume's structured profile.

        Each evidence row is keyed by ``resume-evidence-N`` so that
        suggestions can reference them via ``evidence_keys`` and the
        server-side validator can confirm the keys exist.
        """
        rows: list[dict[str, Any]] = []
        for index, item in enumerate(profile_data.get("technical_skills", []) or [], start=1):
            if not isinstance(item, dict):
                continue
            rows.append(
                {
                    "key": f"resume-evidence-{index}",
                    "skill": item.get("value"),
                    "evidence_text": item.get("evidence_text"),
                    "section": item.get("evidence_section"),
                }
            )
        return rows[:120]

    def _match_evidence(self, report: MatchReport) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for detail in report.details:
            for item in detail.evidence:
                rows.append(
                    {
                        "detail_code": detail.code,
                        "category": detail.category,
                        "resume_evidence": item.resume_evidence,
                        "conclusion_key": item.conclusion_key,
                        "resume_source_id": item.resume_source_id,
                        "job_evidence": item.job_evidence,
                        "confidence": item.confidence,
                        "resume_section": item.resume_section,
                    }
                )
        return rows[:120]

    @staticmethod
    def _job_summary(job: Any) -> str:
        parts = [job.description, job.responsibilities, job.requirements]
        return "\n".join(part for part in parts if part).strip()[:8000]

    @staticmethod
    def _job_information_completeness(report: MatchReport) -> float:
        for detail in report.details:
            if detail.category == "REPORT_METADATA" and detail.code == "REPORT_TRUST":
                value = detail.data.get("job_information_completeness")
                if isinstance(value, (int, float)):
                    return float(value)
        return 0.0

    @staticmethod
    def _json_list(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [dict(item) for item in values]

    # ------------------------------------------------------------------
    # Run / persistence helpers
    # ------------------------------------------------------------------

    def _start_run(
        self,
        user_id: int,
        request: ResumeOptimizationWorkflowInput,
    ) -> AgentRun:
        run = AgentRun(
            user_id=user_id,
            run_type=RUN_TYPE_RESUME_OPTIMIZATION,
            status=TaskStatus.RUNNING,
            started_at=datetime.now(UTC),
            state_snapshot={
                "user_id": user_id,
                "resume_version_id": request.resume.resume_version_id,
                "job_id": request.job.job_id,
                "match_report_id": request.match_report.report_id,
                "is_summary_only": request.job.is_summary_only,
                "information_completeness": request.job.information_completeness,
            },
        )
        self.repository.add_run(run)
        run.steps.append(
            AgentStep(
                sequence=1,
                node_name="dify_resume_optimization_workflow",
                status=TaskStatus.RUNNING,
                started_at=run.started_at,
                input_summary={
                    "resume_version_id": request.resume.resume_version_id,
                    "job_id": request.job.job_id,
                    "match_report_id": request.match_report.report_id,
                    "matched_skill_count": len(request.match_report.matched_skills),
                    "missing_skill_count": len(request.match_report.missing_skills),
                    "blocking_risk_count": len(request.match_report.blocking_risks),
                },
            )
        )
        self.session.flush()
        return run

    def _persist_success(
        self,
        user_id: int,
        version: ResumeVersion,
        job: Any,
        report: MatchReport,
        result: ResumeOptimizationProviderResult,
        run: AgentRun,
        started: float,
    ) -> GeneratedMaterial:
        latency_ms = result.output.generation.latency_ms or self._elapsed_ms(started)
        material = GeneratedMaterial(
            user_id=user_id,
            resume_version_id=version.id,
            job_id=job.id,
            match_report_id=report.id,
            material_type=MATERIAL_TYPE_RESUME_OPTIMIZATION,
            status=ResumeOptimizationStatus.DRAFT.value,
            content=self._serialize_content(result.output, sections=None),
            facts_used=self._facts_used(result.output),
            is_human_confirmed=False,
        )
        self.repository.add_material(material)
        run.status = TaskStatus.SUCCEEDED
        run.finished_at = datetime.now(UTC)
        run.state_snapshot = {
            **run.state_snapshot,
            "generated_material_id": material.id,
            "workflow_run_id": result.output.generation.workflow_run_id,
            "workflow_version": result.output.generation.workflow_version,
            "provider": result.output.generation.provider,
            "latency_ms": latency_ms,
            "raw_output": result.raw_output,
            "attempts": [attempt.model_dump(mode="json") for attempt in result.attempts],
        }
        self._record_attempts_as_steps(run, result.attempts, latency_ms, succeeded=True)
        self.session.add(
            ModelUsageLog(
                user_id=user_id,
                agent_run_id=run.id,
                provider=result.output.generation.provider,
                model_name="dify-workflow",
                operation=RUN_TYPE_RESUME_OPTIMIZATION,
                latency_ms=latency_ms,
                is_success=True,
            )
        )
        return material

    def _persist_failure(
        self,
        user_id: int,
        version: ResumeVersion,
        job: Any,
        report: MatchReport,
        run: AgentRun,
        started: float,
        code: str,
        message: str,
    ) -> GeneratedMaterial:
        material = GeneratedMaterial(
            user_id=user_id,
            resume_version_id=version.id,
            job_id=job.id,
            match_report_id=report.id,
            material_type=MATERIAL_TYPE_RESUME_OPTIMIZATION,
            status=ResumeOptimizationStatus.FAILED.value,
            content="{}",
            facts_used=[],
            is_human_confirmed=False,
        )
        self.repository.add_material(material)
        latency_ms = self._elapsed_ms(started)
        run.status = TaskStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.error_code = code
        run.error_message = message
        run.state_snapshot = {
            **run.state_snapshot,
            "generated_material_id": material.id,
            "latency_ms": latency_ms,
            "error_code": code,
            "error_message": message,
        }
        for step in run.steps:
            step.status = TaskStatus.FAILED
            step.finished_at = run.finished_at
            step.duration_ms = latency_ms
            step.error_message = "The resume optimization workflow failed"
        self.session.add(
            ModelUsageLog(
                user_id=user_id,
                agent_run_id=run.id,
                provider="dify",
                model_name="dify-workflow",
                operation=RUN_TYPE_RESUME_OPTIMIZATION,
                latency_ms=latency_ms,
                is_success=False,
                error_code=code,
            )
        )
        return material

    def _record_attempts_as_steps(
        self,
        run: AgentRun,
        attempts: list[Any],
        latency_ms: int,
        *,
        succeeded: bool,
    ) -> None:
        if not attempts:
            return
        next_sequence = max((step.sequence for step in run.steps), default=0) + 1
        for attempt in attempts:
            run.steps.append(
                AgentStep(
                    sequence=next_sequence,
                    node_name="dify_workflow_attempt",
                    status=TaskStatus.SUCCEEDED if succeeded else TaskStatus.FAILED,
                    started_at=run.started_at,
                    finished_at=run.finished_at,
                    duration_ms=attempt.latency_ms,
                    retry_count=1 if attempt.retried else 0,
                    input_summary={
                        "sequence": attempt.sequence,
                        "retried": attempt.retried,
                    },
                    output_summary={
                        "http_status": attempt.http_status,
                        "workflow_run_id": attempt.workflow_run_id,
                        "workflow_id": attempt.workflow_id,
                        "status": attempt.status,
                        "error": attempt.error,
                        "total_steps": attempt.total_steps,
                        "elapsed_time": attempt.elapsed_time,
                        "outputs_keys": attempt.outputs_keys,
                        "error_code": attempt.error_code,
                        "error_message": attempt.error_message,
                        "latency_ms": attempt.latency_ms,
                    },
                )
            )
            next_sequence += 1

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def _serialize_content(
        self,
        output: ResumeOptimizationWorkflowOutput,
        sections: list[ResumeOptimizationSectionRead] | None,
    ) -> str:
        """Serialise the workflow output for storage.

        The ``content`` column stores the canonical output JSON. When
        ``sections`` is supplied (after user confirmation), the
        per-section ``accepted`` and ``edited_text`` flags are merged in
        so the stored representation matches what the user confirmed.
        """
        payload = output.model_dump(mode="json")
        if sections is not None:
            payload["sections"] = [item.model_dump(mode="json") for item in sections]
        return json.dumps(payload, ensure_ascii=False)

    def _facts_used(self, output: ResumeOptimizationWorkflowOutput) -> list[dict[str, Any]]:
        return [
            {
                "summary": output.summary,
                "sections": [section.model_dump(mode="json") for section in output.sections],
                "keyword_suggestions": [
                    kw.model_dump(mode="json") for kw in output.keyword_suggestions
                ],
                "missing_evidence_warnings": list(output.missing_evidence_warnings),
                "fabrication_warnings": list(output.fabrication_warnings),
                "job_information_warning": output.job_information_warning,
            }
        ]

    def _facts_used_with_confirmation(
        self,
        stored: ResumeOptimizationWorkflowOutput,
        merged_sections: list[ResumeOptimizationSectionRead],
        attest_truth: bool = False,
    ) -> list[dict[str, Any]]:
        return [
            {
                "summary": stored.summary,
                "sections": [section.model_dump(mode="json") for section in merged_sections],
                "keyword_suggestions": [
                    kw.model_dump(mode="json") for kw in stored.keyword_suggestions
                ],
                "missing_evidence_warnings": list(stored.missing_evidence_warnings),
                "fabrication_warnings": list(stored.fabrication_warnings),
                "job_information_warning": stored.job_information_warning,
                # 审计元数据:用户在确认时是否勾选真实性声明。create_version
                # 重校时据此判断 edited_text 是否经过用户显式背书。
                "attest_truth": bool(attest_truth),
            }
        ]

    def _stored_output(self, material: GeneratedMaterial) -> ResumeOptimizationWorkflowOutput:
        try:
            payload = json.loads(material.content) if material.content else {}
        except json.JSONDecodeError as exc:
            raise AppError(
                "RESUME_OPTIMIZATION_CORRUPT",
                "Stored optimization content is corrupt",
                500,
            ) from exc
        return ResumeOptimizationWorkflowOutput.model_validate(payload)

    @staticmethod
    def _empty_output() -> ResumeOptimizationWorkflowOutput:
        """Return an empty output object for failed or corrupt records."""
        return ResumeOptimizationWorkflowOutput(
            summary="",
            sections=[],
            keyword_suggestions=[],
            missing_evidence_warnings=[],
            fabrication_warnings=[],
            job_information_warning="",
            generation=ResumeOptimizationGeneration(
                workflow_version="unknown",
                workflow_run_id=None,
                provider="unknown",
                latency_ms=None,
            ),
        )

    def _read(
        self,
        material: GeneratedMaterial,
        run: AgentRun | None,
    ) -> ResumeOptimizationRead:
        snapshot = run.state_snapshot if run is not None else {}
        try:
            stored = self._stored_output(material)
        except (AppError, ValidationError):
            stored = self._empty_output()
        sections = self._sections_for_read(material, stored)
        return ResumeOptimizationRead(
            id=material.id,
            user_id=material.user_id,
            resume_version_id=material.resume_version_id or 0,
            job_id=material.job_id or 0,
            match_report_id=material.match_report_id or 0,
            status=ResumeOptimizationStatus(material.status),
            summary=stored.summary,
            sections=sections,
            keyword_suggestions=[
                ResumeOptimizationKeywordSuggestionRead(
                    keyword=kw.keyword,
                    reason=kw.reason,
                    evidence_keys=list(kw.evidence_keys),
                )
                for kw in stored.keyword_suggestions
            ],
            missing_evidence_warnings=list(stored.missing_evidence_warnings),
            fabrication_warnings=list(stored.fabrication_warnings),
            job_information_warning=stored.job_information_warning,
            is_human_confirmed=material.is_human_confirmed,
            workflow_run_id=self._optional_str(snapshot.get("workflow_run_id")),
            workflow_version=self._optional_str(snapshot.get("workflow_version")),
            provider=self._optional_str(snapshot.get("provider")),
            latency_ms=self._optional_int(snapshot.get("latency_ms")),
            error_code=run.error_code if run is not None else None,
            error_message=run.error_message if run is not None else None,
            created_at=material.created_at,
            updated_at=material.updated_at,
        )

    def _sections_for_read(
        self,
        material: GeneratedMaterial,
        stored: ResumeOptimizationWorkflowOutput,
    ) -> list[ResumeOptimizationSectionRead]:
        # If the user has confirmed, the persisted facts_used holds the
        # accepted/edited flags; otherwise read sections from the stored
        # output as-is.
        facts = material.facts_used or []
        if facts and isinstance(facts[0], dict) and isinstance(facts[0].get("sections"), list):
            sections_data = facts[0]["sections"]
            result: list[ResumeOptimizationSectionRead] = []
            for item in sections_data:
                if not isinstance(item, dict):
                    continue
                try:
                    result.append(ResumeOptimizationSectionRead.model_validate(item))
                except Exception:
                    continue
            if result:
                return result
        return [
            ResumeOptimizationSectionRead(
                section=section.section,
                source_section_id=section.source_section_id,
                original_text=section.original_text,
                suggested_text=section.suggested_text,
                reason=section.reason,
                related_job_requirement=section.related_job_requirement,
                evidence_keys=list(section.evidence_keys),
                change_type=section.change_type,
                accepted=False,
                edited_text=None,
            )
            for section in stored.sections
        ]

    def _run_by_material(self, user_id: int) -> dict[int, AgentRun]:
        result: dict[int, AgentRun] = {}
        for run in self.repository.list_runs_for_user(user_id):
            material_id = self._optional_int(run.state_snapshot.get("generated_material_id"))
            if material_id is not None and material_id not in result:
                result[material_id] = run
        return result

    def _audit(
        self,
        user_id: int,
        action: str,
        material_id: int,
        details: dict[str, Any],
    ) -> None:
        self.session.add(
            AuditLog(
                actor_id=user_id,
                action=action,
                resource_type="resume_optimization",
                resource_id=str(material_id),
                details=details,
            )
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(round((perf_counter() - started) * 1000), 0)

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        return value if isinstance(value, int) else None

    # ------------------------------------------------------------------
    # New resume version creation
    # ------------------------------------------------------------------

    def _apply_suggestions_to_profile(
        self,
        parent_version: ResumeVersion,
        merged_sections: list[ResumeOptimizationSectionRead],
    ) -> ResumeProfile:
        """Apply only the user-accepted section suggestions to a copy of
        the parent profile.

        Unaccepted sections are kept verbatim. Skill evidence is never
        removed or invented: the rewrite only touches the ``description``
        /``summary`` text fields of existing sections.
        """
        profile = ResumeProfile.model_validate(parent_version.structured_data)
        accepted_by_section: dict[str, ResumeOptimizationSectionRead] = {
            item.source_section_id: item for item in merged_sections if item.accepted
        }
        # Rewrite work experience descriptions
        for index, experience in enumerate(profile.work_experience, start=1):
            key = f"experience-{index}"
            accepted = accepted_by_section.get(key)
            if accepted is None:
                continue
            new_text = (
                accepted.edited_text.strip()
                if accepted.edited_text and accepted.edited_text.strip()
                else accepted.suggested_text
            )
            if new_text:
                experience.description = experience.description.model_copy(
                    update={
                        "value": new_text,
                        "evidence_text": new_text,
                    }
                )
        # Rewrite project descriptions
        for index, project in enumerate(profile.project_experience, start=1):
            key = f"project-{index}"
            accepted = accepted_by_section.get(key)
            if accepted is None:
                continue
            new_text = (
                accepted.edited_text.strip()
                if accepted.edited_text and accepted.edited_text.strip()
                else accepted.suggested_text
            )
            if new_text:
                project.description = project.description.model_copy(
                    update={
                        "value": new_text,
                        "evidence_text": new_text,
                    }
                )
        # Rewrite the summary
        accepted_summary = accepted_by_section.get("summary")
        if accepted_summary is not None:
            new_text = (
                accepted_summary.edited_text.strip()
                if accepted_summary.edited_text and accepted_summary.edited_text.strip()
                else accepted_summary.suggested_text
            )
            if new_text:
                profile.summary = profile.summary.model_copy(
                    update={"value": new_text, "evidence_text": new_text}
                )
        return profile
