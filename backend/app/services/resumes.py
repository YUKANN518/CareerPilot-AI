from __future__ import annotations

import builtins
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from pydantic import ValidationError
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.providers.base import AIProviderError, ProviderResponse, ResumeAIProvider
from app.core.config import Settings
from app.core.exceptions import AppError
from app.files.extraction import ResumeTextExtractor
from app.files.storage import PrivateFileStorage
from app.files.validation import read_upload_limited, validate_resume_upload
from app.models.enums import ResumeStatus
from app.models.operations import ModelUsageLog
from app.models.resumes import (
    FileAsset,
    Resume,
    ResumeSection,
    ResumeSkill,
    ResumeVersion,
    Skill,
    SkillAlias,
)
from app.models.users import User
from app.repositories.resumes import ResumeRepository
from app.schemas.resume import (
    BasicInfo,
    EvidenceField,
    ExtractionResult,
    FileAssetRead,
    ParseResultRead,
    ResumeProfile,
    ResumeRead,
    ResumeSkillRead,
    ResumeUploadResult,
    ResumeVersionRead,
    SourceLocation,
    TextBlock,
    count_low_confidence_fields,
)
from app.semantic.embeddings import embedding_provider_from_settings
from app.semantic.index import SemanticIndexService

LOCAL_SKILL_ALIASES = {
    "py": "Python",
    "python3": "Python",
    "vue3": "Vue",
    "vue.js": "Vue",
    "ts": "TypeScript",
    "js": "JavaScript",
    "fast api": "FastAPI",
}


class ResumeService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        provider: ResumeAIProvider | None = None,
        semantic_index: SemanticIndexService | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.provider = provider
        self.semantic_index = semantic_index
        self.repository = ResumeRepository(session)
        self.storage = PrivateFileStorage(settings.upload_directory)
        self.extractor = ResumeTextExtractor()

    async def upload(self, owner: User, upload: UploadFile) -> ResumeUploadResult:
        original_filename = upload.filename
        content_type = upload.content_type
        try:
            content = await read_upload_limited(
                upload,
                self.settings.resume_max_upload_bytes,
            )
        finally:
            await upload.close()
        validated = validate_resume_upload(
            original_filename,
            content_type,
            content,
            self.settings.resume_max_upload_bytes,
        )

        newly_saved_storage_key: str | None = None
        asset = self.repository.find_asset_by_hash(owner.id, validated.sha256)
        if asset is not None:
            existing = self.repository.find_resume_by_asset(owner.id, asset.id)
            if existing is not None:
                return ResumeUploadResult(resume=self._resume_read(existing), duplicate=True)
            if not self.storage.exists(asset.storage_key):
                asset.storage_key = self.storage.save(
                    owner.id,
                    validated.file_format,
                    validated.content,
                )
        else:
            storage_key = self.storage.save(
                owner.id,
                validated.file_format,
                validated.content,
            )
            newly_saved_storage_key = storage_key
            asset = FileAsset(
                owner_id=owner.id,
                storage_key=storage_key,
                original_name=validated.original_name,
                mime_type=validated.mime_type,
                size_bytes=validated.size_bytes,
                sha256=validated.sha256,
                file_format=validated.file_format,
            )
            self.session.add(asset)

        resume = Resume(
            owner_id=owner.id,
            file_asset=asset,
            title=Path(validated.original_name).stem,
            status=ResumeStatus.UPLOADED,
        )
        self.session.add(resume)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            duplicate_asset = self.repository.find_asset_by_hash(owner.id, validated.sha256)
            if newly_saved_storage_key is not None and (
                duplicate_asset is None or duplicate_asset.storage_key != newly_saved_storage_key
            ):
                self.storage.delete(newly_saved_storage_key)
            if duplicate_asset is None:
                raise AppError("UPLOAD_CONFLICT", "简历上传发生冲突，请重试", 409) from exc
            duplicate_resume = self.repository.find_resume_by_asset(owner.id, duplicate_asset.id)
            if duplicate_resume is None:
                raise AppError("UPLOAD_CONFLICT", "简历上传发生冲突，请重试", 409) from exc
            return ResumeUploadResult(
                resume=self._resume_read(duplicate_resume),
                duplicate=True,
            )
        self.session.refresh(resume)
        return ResumeUploadResult(resume=self._resume_read(resume), duplicate=False)

    def list(self, owner: User) -> list[ResumeRead]:
        return [self._resume_read(resume) for resume in self.repository.list_for_owner(owner.id)]

    def get(self, resume_id: int, owner: User) -> ResumeRead:
        return self._resume_read(self._owned_resume(resume_id, owner.id))

    def get_file(self, resume_id: int, owner: User) -> tuple[Path, FileAsset]:
        resume = self._owned_resume(resume_id, owner.id)
        if resume.file_asset is None:
            raise AppError("FILE_NOT_FOUND", "简历没有关联原始文件", 404)
        return self.storage.resolve_existing(resume.file_asset.storage_key), resume.file_asset

    def extract(self, resume_id: int, owner: User) -> ExtractionResult:
        resume = self._owned_resume(resume_id, owner.id)
        self._require_status(
            resume,
            {ResumeStatus.UPLOADED, ResumeStatus.FAILED, ResumeStatus.EXTRACTED},
            "当前状态不能执行文本提取",
        )
        if resume.file_asset is None:
            raise AppError("FILE_NOT_FOUND", "简历没有关联原始文件", 404)

        resume.status = ResumeStatus.EXTRACTING
        resume.last_error_code = None
        resume.last_error_message = None
        self.session.commit()
        try:
            path = self.storage.resolve_existing(resume.file_asset.storage_key)
            output = self.extractor.extract(path, resume.file_asset.file_format)
        except AppError as exc:
            resume.status = ResumeStatus.FAILED
            resume.last_error_code = exc.code
            resume.last_error_message = exc.message
            self.session.commit()
            raise

        resume.extracted_text = output.raw_text
        resume.extracted_blocks = [block.model_dump(mode="json") for block in output.blocks]
        resume.status = ResumeStatus.EXTRACTED
        resume.extracted_at = datetime.now(UTC)
        resume.parse_result = None
        resume.parse_attempts = 0
        self.session.commit()
        return ExtractionResult(
            resume_id=resume.id,
            status=resume.status,
            character_count=len(output.raw_text),
            blocks=output.blocks,
        )

    async def parse(self, resume_id: int, owner: User) -> ParseResultRead:
        resume = self._owned_resume(resume_id, owner.id)
        self._require_status(
            resume,
            {ResumeStatus.EXTRACTED, ResumeStatus.FAILED},
            "请先完成文本提取，再执行结构化解析",
        )
        if not resume.extracted_text or not resume.extracted_blocks:
            raise AppError("TEXT_NOT_EXTRACTED", "请先完成文本提取", 409)
        if self.provider is None:
            raise AppError("AI_PROVIDER_NOT_CONFIGURED", "AI Provider 未注入", 500)

        blocks = [TextBlock.model_validate(block) for block in resume.extracted_blocks]
        resume.status = ResumeStatus.PARSING
        resume.parse_attempts = 0
        resume.last_error_code = None
        resume.last_error_message = None
        self.session.commit()

        total_attempts = self.settings.resume_parse_retries + 1
        for attempt in range(1, total_attempts + 1):
            resume.parse_attempts = attempt
            try:
                response = await self.provider.structure_resume(resume.extracted_text, blocks)
                profile = ResumeProfile.model_validate_json(response.raw_content)
                self._validate_skill_evidence(profile, resume.extracted_text)
            except (AIProviderError, ValidationError, ValueError) as exc:
                code = exc.code if isinstance(exc, AIProviderError) else "AI_OUTPUT_INVALID"
                self._log_usage(owner.id, None, code)
                resume.last_error_code = code
                resume.last_error_message = "结构化输出无效，已进入重试或人工填写流程"
                self.session.commit()
                continue

            self._log_usage(owner.id, response, None)
            resume.parse_result = profile.model_dump(mode="json")
            resume.status = ResumeStatus.NEEDS_CONFIRMATION
            resume.parsed_at = datetime.now(UTC)
            resume.last_error_code = None
            resume.last_error_message = None
            self.session.commit()
            return self._parse_result(resume)

        manual_profile = self._empty_profile()
        resume.parse_result = manual_profile.model_dump(mode="json")
        resume.status = ResumeStatus.NEEDS_CONFIRMATION
        resume.parsed_at = datetime.now(UTC)
        resume.last_error_code = "AI_PARSE_FAILED"
        resume.last_error_message = "自动解析重试失败，请人工填写并确认"
        self.session.commit()
        return self._parse_result(resume)

    def get_parse_result(self, resume_id: int, owner: User) -> ParseResultRead:
        return self._parse_result(self._owned_resume(resume_id, owner.id))

    def update_parse_result(
        self,
        resume_id: int,
        owner: User,
        profile: ResumeProfile,
    ) -> ParseResultRead:
        resume = self._owned_resume(resume_id, owner.id)
        self._require_status(
            resume,
            {ResumeStatus.NEEDS_CONFIRMATION, ResumeStatus.CONFIRMED},
            "当前状态不能修改解析结果",
        )
        if not resume.extracted_text:
            raise AppError("TEXT_NOT_EXTRACTED", "简历缺少提取文本", 409)
        self._validate_skill_evidence(profile, resume.extracted_text)
        resume.parse_result = profile.model_dump(mode="json")
        resume.status = ResumeStatus.NEEDS_CONFIRMATION
        resume.last_error_code = None
        resume.last_error_message = None
        self.session.commit()
        return self._parse_result(resume)

    def confirm(self, resume_id: int, owner: User) -> ResumeVersionRead:
        resume = self._owned_resume(resume_id, owner.id)
        self._require_status(
            resume,
            {ResumeStatus.NEEDS_CONFIRMATION},
            "只有待确认的解析结果可以生成版本",
        )
        if resume.parse_result is None or not resume.extracted_text:
            raise AppError("PARSE_RESULT_MISSING", "没有可确认的结构化结果", 409)
        try:
            profile = ResumeProfile.model_validate(resume.parse_result)
        except ValidationError as exc:
            raise AppError("PARSE_RESULT_INVALID", "结构化结果校验失败", 422) from exc
        self._validate_skill_evidence(profile, resume.extracted_text)

        self.session.execute(
            update(ResumeVersion)
            .where(ResumeVersion.resume_id == resume.id, ResumeVersion.is_current.is_(True))
            .values(is_current=False)
        )
        version = ResumeVersion(
            resume_id=resume.id,
            version_number=self.repository.next_version_number(resume.id),
            raw_text=resume.extracted_text,
            structured_data=profile.model_dump(mode="json"),
            is_current=True,
            is_confirmed=True,
        )
        self.session.add(version)
        self.session.flush()
        self._save_sections(version, profile)
        self._save_skills(version, profile)
        resume.status = ResumeStatus.CONFIRMED
        resume.confirmed_at = datetime.now(UTC)
        self.session.commit()
        self.session.refresh(version)
        return self._version_read(version)

    def list_versions(
        self,
        resume_id: int,
        owner: User,
    ) -> builtins.list[ResumeVersionRead]:
        self._owned_resume(resume_id, owner.id)
        return [
            self._version_read(version)
            for version in self.repository.list_versions(resume_id, owner.id)
        ]

    def get_version(self, version_id: int, owner: User) -> ResumeVersionRead:
        version = self.repository.get_version_for_owner(version_id, owner.id)
        if version is None:
            raise AppError("RESUME_VERSION_NOT_FOUND", "简历版本不存在", 404)
        return self._version_read(version)

    def list_version_skills(
        self,
        version_id: int,
        owner: User,
    ) -> builtins.list[ResumeSkillRead]:
        version = self.repository.get_version_for_owner(version_id, owner.id)
        if version is None:
            raise AppError("RESUME_VERSION_NOT_FOUND", "简历版本不存在", 404)
        return [
            ResumeSkillRead(
                id=item.id,
                normalized_name=item.skill.name,
                raw_name=item.raw_name,
                category=item.skill.category,
                level=item.level,
                confidence=item.confidence,
                evidence_text=item.evidence_text,
                evidence_section=item.evidence_section,
                source_location=SourceLocation.model_validate_json(item.source_location),
                resume_version_id=item.resume_version_id,
                is_user_confirmed=item.is_user_confirmed,
            )
            for item in version.skills
        ]

    def delete(self, resume_id: int, owner: User) -> None:
        resume = self._owned_resume(resume_id, owner.id)
        version_ids = [version.id for version in resume.versions]
        asset = resume.file_asset
        storage_key = asset.storage_key if asset is not None else None
        asset_id = asset.id if asset is not None else None
        delete_physical_file = False
        self.session.delete(resume)
        self.session.flush()
        if (
            asset is not None
            and asset_id is not None
            and self.repository.count_asset_references(asset_id) == 0
        ):
            self.session.delete(asset)
            delete_physical_file = True
        self.session.commit()
        if storage_key is not None and delete_physical_file:
            self.storage.delete(storage_key)
        index = self.semantic_index
        if index is None and Path(self.settings.faiss_index_dir).exists():
            index = SemanticIndexService(
                self.settings,
                embedding_provider_from_settings(self.settings),
            )
        if index is not None:
            for version_id in version_ids:
                index.delete_resume_index(owner.id, version_id)

    def _owned_resume(self, resume_id: int, owner_id: int) -> Resume:
        resume = self.repository.get_for_owner(resume_id, owner_id)
        if resume is None:
            raise AppError("RESUME_NOT_FOUND", "简历不存在", 404)
        return resume

    @staticmethod
    def _require_status(
        resume: Resume,
        allowed: set[ResumeStatus],
        message: str,
    ) -> None:
        if resume.status not in allowed:
            raise AppError("INVALID_RESUME_STATE", message, 409)

    def _resume_read(self, resume: Resume) -> ResumeRead:
        if resume.file_asset is None:
            raise AppError("FILE_NOT_FOUND", "简历没有关联原始文件", 404)
        return ResumeRead(
            id=resume.id,
            title=resume.title,
            status=resume.status,
            file=FileAssetRead.model_validate(resume.file_asset),
            parse_attempts=resume.parse_attempts,
            extracted_at=resume.extracted_at,
            parsed_at=resume.parsed_at,
            confirmed_at=resume.confirmed_at,
            created_at=resume.created_at,
            updated_at=resume.updated_at,
            version_count=len(resume.versions),
            last_error_code=resume.last_error_code,
            last_error_message=resume.last_error_message,
        )

    def _parse_result(self, resume: Resume) -> ParseResultRead:
        profile = (
            ResumeProfile.model_validate(resume.parse_result)
            if resume.parse_result is not None
            else None
        )
        return ParseResultRead(
            resume_id=resume.id,
            status=resume.status,
            result=profile,
            parse_attempts=resume.parse_attempts,
            low_confidence_count=(
                count_low_confidence_fields(
                    profile,
                    self.settings.resume_low_confidence_threshold,
                )
                if profile is not None
                else 0
            ),
            error_code=resume.last_error_code,
            error_message=resume.last_error_message,
        )

    def _version_read(self, version: ResumeVersion) -> ResumeVersionRead:
        return ResumeVersionRead(
            id=version.id,
            resume_id=version.resume_id,
            version_number=version.version_number,
            structured_data=ResumeProfile.model_validate(version.structured_data),
            is_current=version.is_current,
            is_confirmed=version.is_confirmed,
            parent_version_id=version.parent_version_id,
            created_at=version.created_at,
        )

    def _save_sections(self, version: ResumeVersion, profile: ResumeProfile) -> None:
        profile_data = profile.model_dump(mode="json")
        for sort_order, (section_type, content) in enumerate(profile_data.items()):
            self.session.add(
                ResumeSection(
                    resume_version_id=version.id,
                    section_type=section_type,
                    sort_order=sort_order,
                    content={"value": content},
                    source_locator=self._first_source_label(content),
                )
            )

    def _save_skills(self, version: ResumeVersion, profile: ResumeProfile) -> None:
        saved: set[tuple[str, str]] = set()
        skill_groups = (
            ("technical_skills", profile.technical_skills),
            ("soft_skills", profile.soft_skills),
        )
        for section, skills in skill_groups:
            for item in skills:
                canonical_name = LOCAL_SKILL_ALIASES.get(item.value.casefold(), item.value.strip())
                source_id = item.source_location.label
                dedupe_key = (canonical_name.casefold(), source_id)
                if dedupe_key in saved:
                    continue
                saved.add(dedupe_key)
                skill = self.repository.find_skill(canonical_name)
                if skill is None:
                    skill = Skill(name=canonical_name, category=item.category)
                    self.session.add(skill)
                    self.session.flush()
                    if canonical_name.casefold() != item.value.casefold():
                        self.session.add(SkillAlias(skill_id=skill.id, alias=item.value))
                self.session.add(
                    ResumeSkill(
                        resume_version_id=version.id,
                        skill_id=skill.id,
                        raw_name=item.value,
                        level=item.level,
                        confidence=item.confidence,
                        evidence_text=item.evidence_text,
                        evidence_section=self._skill_evidence_section(item, profile, section),
                        evidence_source_id=source_id,
                        source_location=item.source_location.model_dump_json(),
                        is_user_confirmed=True,
                    )
                )

    @staticmethod
    def _skill_evidence_section(
        skill: EvidenceField,
        profile: ResumeProfile,
        declared_section: str,
    ) -> str:
        grouped_records = (
            ("project_experience", profile.project_experience),
            ("work_experience", profile.work_experience),
            ("education", profile.education),
        )
        for section, records in grouped_records:
            for record in records:
                if any(
                    ResumeService._evidence_field_matches(skill, value)
                    for value in record.__dict__.values()
                    if isinstance(value, EvidenceField)
                ):
                    return section
        other_fields: list[EvidenceField] = [
            *profile.basic_info.__dict__.values(),
            *profile.languages,
            *profile.certificates,
            *profile.awards,
            profile.summary,
        ]
        if any(
            ResumeService._evidence_field_matches(skill, value)
            for value in other_fields
            if isinstance(value, EvidenceField)
        ):
            return "other_resume_text"
        if declared_section in {"technical_skills", "soft_skills"}:
            return "skill_section"
        return "other_resume_text"

    @staticmethod
    def _evidence_field_matches(skill: EvidenceField, field: EvidenceField) -> bool:
        if skill.source_location.label != field.source_location.label:
            return False
        needle = re.sub(r"\s+", " ", skill.evidence_text).strip().casefold()
        haystack = re.sub(
            r"\s+",
            " ",
            f"{field.value} {field.evidence_text}",
        ).strip().casefold()
        return bool(needle and haystack and (needle in haystack or haystack in needle))

    def _log_usage(
        self,
        user_id: int,
        response: ProviderResponse | None,
        error_code: str | None,
    ) -> None:
        self.session.add(
            ModelUsageLog(
                user_id=user_id,
                provider=response.provider_name if response else self.settings.ai_provider,
                model_name=response.model_name if response else self.settings.openai_chat_model,
                operation="resume_structuring",
                prompt_version=response.prompt_version if response else "unknown",
                prompt_tokens=response.prompt_tokens if response else 0,
                completion_tokens=response.completion_tokens if response else 0,
                latency_ms=response.latency_ms if response else None,
                is_success=error_code is None,
                error_code=error_code,
            )
        )

    @staticmethod
    def _validate_skill_evidence(profile: ResumeProfile, raw_text: str) -> None:
        normalized_source = re.sub(r"\s+", " ", raw_text).casefold()
        for skill in [*profile.technical_skills, *profile.soft_skills]:
            normalized_evidence = re.sub(r"\s+", " ", skill.evidence_text).strip().casefold()
            if not normalized_evidence or normalized_evidence not in normalized_source:
                raise ValueError(f"技能 {skill.value} 的证据不在简历原文中")

    @staticmethod
    def _first_source_label(content: Any) -> str | None:
        if isinstance(content, dict):
            location = content.get("source_location")
            if isinstance(location, dict) and isinstance(location.get("label"), str):
                return str(location["label"])[:255]
            for value in content.values():
                if label := ResumeService._first_source_label(value):
                    return label
        if isinstance(content, list):
            for value in content:
                if label := ResumeService._first_source_label(value):
                    return label
        return None

    @staticmethod
    def _empty_profile() -> ResumeProfile:
        unknown_location = SourceLocation(source_type="unknown", label="manual-entry-required")

        def empty_field() -> EvidenceField:
            return EvidenceField(
                value="",
                confidence=0,
                evidence_text="",
                source_location=unknown_location,
                needs_confirmation=True,
            )

        return ResumeProfile(
            basic_info=BasicInfo(
                full_name=empty_field(),
                email=empty_field(),
                phone=empty_field(),
                location=empty_field(),
            ),
            education=[],
            work_experience=[],
            project_experience=[],
            technical_skills=[],
            soft_skills=[],
            languages=[],
            certificates=[],
            awards=[],
            summary=empty_field(),
        )
