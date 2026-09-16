from __future__ import annotations

import re
from time import perf_counter

from app.ai.providers.base import ProviderResponse, ResumeAIProvider
from app.schemas.resume import (
    BasicInfo,
    EducationItem,
    EvidenceField,
    ProjectExperienceItem,
    ResumeProfile,
    SourceLocation,
    StructuredSkill,
    TextBlock,
    WorkExperienceItem,
)

TECHNICAL_SKILLS = {
    "python": ("Python", "programming_language"),
    "fastapi": ("FastAPI", "backend_framework"),
    "vue": ("Vue", "frontend_framework"),
    "typescript": ("TypeScript", "programming_language"),
    "sqlalchemy": ("SQLAlchemy", "database"),
    "sqlite": ("SQLite", "database"),
}
SOFT_SKILLS = {
    "communication": "Communication",
    "teamwork": "Teamwork",
    "沟通": "沟通",
    "团队": "团队协作",
}


class MockAIProvider(ResumeAIProvider):
    """Deterministic offline provider for tests and no-key local development."""

    async def structure_resume(
        self,
        raw_text: str,
        blocks: list[TextBlock],
    ) -> ProviderResponse:
        started = perf_counter()
        profile = self._build_profile(raw_text, blocks)
        return ProviderResponse(
            raw_content=profile.model_dump_json(),
            provider_name="mock",
            model_name="offline-resume-fixture-v1",
            latency_ms=max(1, int((perf_counter() - started) * 1000)),
        )

    def _build_profile(self, raw_text: str, blocks: list[TextBlock]) -> ResumeProfile:
        first_block = blocks[0] if blocks else None
        first_line = first_block.text.splitlines()[0].strip() if first_block else ""
        email_match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", raw_text)
        phone_match = re.search(r"(?:\+?\d[\d -]{7,}\d)", raw_text)

        basic_info = BasicInfo(
            full_name=self._field(first_line, first_block, 0.92 if first_line else 0.1),
            email=self._field(
                email_match.group(0) if email_match else "",
                self._find_block(blocks, email_match.group(0)) if email_match else None,
                0.98 if email_match else 0.1,
            ),
            phone=self._field(
                phone_match.group(0) if phone_match else "",
                self._find_block(blocks, phone_match.group(0)) if phone_match else None,
                0.9 if phone_match else 0.1,
            ),
            location=self._field(
                self._find_location(raw_text),
                self._find_block(blocks, self._find_location(raw_text)),
                0.75 if self._find_location(raw_text) else 0.1,
            ),
        )

        technical_skills = [
            self._skill(canonical, category, block)
            for keyword, (canonical, category) in TECHNICAL_SKILLS.items()
            if (block := self._find_block(blocks, keyword)) is not None
        ]
        soft_skills = [
            self._skill(canonical, "soft_skill", block)
            for keyword, canonical in SOFT_SKILLS.items()
            if (block := self._find_block(blocks, keyword)) is not None
        ]

        education_block = self._find_block(blocks, "university") or self._find_block(blocks, "大学")
        work_block = self._find_block(blocks, "intern") or self._find_block(blocks, "实习")
        project_block = self._find_block(blocks, "project") or self._find_block(blocks, "项目")

        return ResumeProfile(
            basic_info=basic_info,
            education=[self._education(education_block)] if education_block else [],
            work_experience=[self._work(work_block)] if work_block else [],
            project_experience=[self._project(project_block)] if project_block else [],
            technical_skills=technical_skills,
            soft_skills=soft_skills,
            languages=self._languages(blocks),
            certificates=[],
            awards=[],
            summary=self._field(raw_text[:500], first_block, 0.65),
        )

    def _education(self, block: TextBlock) -> EducationItem:
        field = self._field(block.text, block, 0.72)
        empty = self._field("", None, 0.1)
        return EducationItem(
            institution=field,
            degree=empty,
            field_of_study=empty,
            start_date=empty,
            end_date=empty,
            description=field,
        )

    def _work(self, block: TextBlock) -> WorkExperienceItem:
        field = self._field(block.text, block, 0.7)
        empty = self._field("", None, 0.1)
        return WorkExperienceItem(
            company=field,
            title=field,
            start_date=empty,
            end_date=empty,
            description=field,
        )

    def _project(self, block: TextBlock) -> ProjectExperienceItem:
        field = self._field(block.text, block, 0.7)
        empty = self._field("", None, 0.1)
        return ProjectExperienceItem(
            name=field,
            role=empty,
            start_date=empty,
            end_date=empty,
            description=field,
        )

    def _languages(self, blocks: list[TextBlock]) -> list[EvidenceField]:
        result: list[EvidenceField] = []
        for keyword, name in (("english", "English"), ("英语", "英语"), ("中文", "中文")):
            block = self._find_block(blocks, keyword)
            if block is not None:
                result.append(self._field(name, block, 0.8))
        return result

    def _skill(
        self,
        canonical_name: str,
        category: str,
        block: TextBlock,
    ) -> StructuredSkill:
        location = self._location(block)
        return StructuredSkill(
            value=canonical_name,
            category=category,
            level=None,
            confidence=0.86,
            evidence_text=block.text,
            source_location=location,
            needs_confirmation=False,
        )

    def _field(
        self,
        value: str,
        block: TextBlock | None,
        confidence: float,
    ) -> EvidenceField:
        return EvidenceField(
            value=value,
            confidence=confidence,
            evidence_text=block.text if block else "",
            source_location=self._location(block),
            needs_confirmation=confidence < 0.7,
        )

    @staticmethod
    def _find_block(blocks: list[TextBlock], text: str) -> TextBlock | None:
        needle = text.casefold()
        if not needle:
            return None
        return next((block for block in blocks if needle in block.text.casefold()), None)

    @staticmethod
    def _find_location(raw_text: str) -> str:
        for location in ("Shanghai", "Beijing", "深圳", "上海", "北京"):
            if location.casefold() in raw_text.casefold():
                return location
        return ""

    @staticmethod
    def _location(block: TextBlock | None) -> SourceLocation:
        if block is None:
            return SourceLocation(source_type="unknown", label="not-found")
        if block.source_type == "page":
            label = f"page:{block.page_number}:block:{block.block_index}"
        elif block.source_type == "paragraph":
            label = f"paragraph:{block.paragraph_index}"
        else:
            label = f"table:{block.table_index}:row:{block.row_index}"
        return SourceLocation(
            source_type=block.source_type,
            page_number=block.page_number,
            block_index=block.block_index,
            paragraph_index=block.paragraph_index,
            table_index=block.table_index,
            row_index=block.row_index,
            label=label,
        )
