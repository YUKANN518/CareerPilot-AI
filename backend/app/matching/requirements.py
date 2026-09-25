from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from app.matching.normalization import SkillNormalizationService
from app.models.jobs import Job
from app.schemas.matching import (
    AvailabilityStatus,
    BlockingPolicyConfig,
    JobRequirements,
    JobSkillRequirement,
)

EXTRACTOR_VERSION = "job-requirements-v1"
PREFERRED_MARKERS = (
    "preferred",
    "nice to have",
    "plus",
    "bonus",
    "优先",
    "加分",
    "更佳",
)
REQUIRED_MARKERS = (
    "required",
    "requirement",
    "must",
    "need",
    "proficient",
    "要求",
    "必须",
    "熟练",
    "掌握",
)
GRADUATE_MARKERS = (
    "fresh graduate",
    "new graduate",
    "new grad",
    "graduates welcome",
    "应届生",
    "应届毕业生",
    "毕业生可",
)


class JobRequirementExtractor:
    """Extract only explicit or dictionary-backed job requirements."""

    def __init__(
        self,
        normalizer: SkillNormalizationService,
        policy: BlockingPolicyConfig | None = None,
    ) -> None:
        self.normalizer = normalizer
        self.policy = policy

    def extract(self, job: Job) -> JobRequirements:
        warnings: list[str] = []
        skills = self._extract_skills(job)
        combined = "\n".join(
            value for value in (job.requirements, job.description, job.responsibilities) if value
        )
        minimum_years, graduate_exception = self._extract_experience(
            job.experience_level,
            combined,
        )
        education_level = self._extract_education(job.education_requirement, combined)
        languages = self._extract_languages(job.language_requirements, combined)
        certificates, certificates_required = self._extract_certificates(combined)
        work_eligibility = self._extract_work_eligibility(combined)
        experience_required = self._criterion_is_explicit(
            combined,
            ("experience", "years", "yrs", "年经验", "年工作", "工作经验"),
        )
        education_required = self._criterion_is_explicit(
            combined,
            (
                "degree",
                "bachelor",
                "master",
                "doctorate",
                "学历",
                "本科",
                "硕士",
                "博士",
            ),
        )
        language_required = self._criterion_is_explicit(
            combined,
            (
                "english",
                "mandarin",
                "chinese",
                "japanese",
                "german",
                "french",
                "英语",
                "中文",
                "日语",
                "德语",
                "法语",
            ),
        )
        language_preferred = self._criterion_is_preferred(
            combined,
            (
                "english",
                "mandarin",
                "chinese",
                "japanese",
                "german",
                "french",
                "英语",
                "中文",
                "日语",
                "德语",
                "法语",
            ),
        )
        if len(languages) > 1 and not self._multiple_languages_are_unambiguous(combined):
            language_required = False
        certificate_preferred = self._criterion_is_preferred(
            combined,
            tuple(certificates),
        )
        certificate_required = self._criterion_is_explicit(
            combined,
            tuple(certificates),
        )

        if not skills:
            warnings.append("未识别到明确或技能词典支持的技能要求")
        if minimum_years is None:
            warnings.append("岗位未提供最低经验要求")
        if education_level is None:
            warnings.append("岗位未提供学历要求")
        if not job.requirements:
            warnings.append("岗位要求字段不完整")

        return JobRequirements(
            job_title=job.title,
            industry=self._optional_raw_string(job.raw_data.get("industry")),
            salary_min=float(job.salary_min) if job.salary_min is not None else None,
            salary_max=float(job.salary_max) if job.salary_max is not None else None,
            skills=skills,
            minimum_experience_years=minimum_years,
            experience_status=self._availability(minimum_years),
            graduate_exception=graduate_exception,
            education_level=education_level,
            education_status=self._availability(education_level),
            languages=languages,
            language_status=self._availability(languages),
            location=job.location,
            location_status=self._availability(job.location),
            employment_type=job.employment_type,
            employment_status=self._availability(job.employment_type),
            certificates=certificates,
            certificates_required=certificates_required,
            certificate_status=self._availability(certificates),
            work_eligibility=work_eligibility,
            work_eligibility_status=self._availability(work_eligibility),
            experience_required_explicit=experience_required,
            education_required_explicit=education_required,
            education_non_substitutable=education_required,
            language_required_explicit=language_required,
            language_preferred=language_preferred,
            certificate_required_explicit=certificate_required,
            certificate_preferred=certificate_preferred,
            warnings=warnings,
            extractor_version=EXTRACTOR_VERSION,
        )

    def _extract_skills(self, job: Job) -> list[JobSkillRequirement]:
        requirements: dict[str, JobSkillRequirement] = {}
        for item in job.skills:
            normalized = self.normalizer.normalize(item.skill.name)
            self._merge_skill(
                requirements,
                normalized.normalized_name,
                JobSkillRequirement(
                    raw_name=item.skill.name,
                    normalized_name=normalized.normalized_name,
                    category=item.skill.category or normalized.category,
                    required=item.is_required,
                    weight=max(item.weight, 1),
                    evidence_text=item.evidence_text or item.skill.name,
                    source_field="job_skills",
                    normalization_rule=normalized.normalization_rule,
                    confidence=normalized.confidence,
                ),
            )

        raw_skill_groups = (
            ("required_skills", True),
            ("must_have_skills", True),
            ("preferred_skills", False),
            ("nice_to_have_skills", False),
            ("skills", False),
        )
        for field_name, required in raw_skill_groups:
            for raw_name in self._as_strings(job.raw_data.get(field_name)):
                normalized = self.normalizer.normalize(raw_name)
                self._merge_skill(
                    requirements,
                    normalized.normalized_name,
                    JobSkillRequirement(
                        raw_name=raw_name,
                        normalized_name=normalized.normalized_name,
                        category=normalized.category,
                        required=required,
                        weight=2 if required else 1,
                        evidence_text=raw_name,
                        source_field=f"raw_data.{field_name}",
                        normalization_rule=normalized.normalization_rule,
                        confidence=normalized.confidence,
                    ),
                )

        text = job.requirements or ""
        for start, end, raw_name, normalized in self.normalizer.find_mentions(text):
            context = self._snippet(text, start, end)
            context_key = context.casefold()
            preferred = any(marker in context_key for marker in PREFERRED_MARKERS)
            required = not preferred and (
                any(marker in context_key for marker in REQUIRED_MARKERS) or bool(text)
            )
            self._merge_skill(
                requirements,
                normalized.normalized_name,
                JobSkillRequirement(
                    raw_name=raw_name,
                    normalized_name=normalized.normalized_name,
                    category=normalized.category,
                    required=required,
                    weight=2 if required else 1,
                    evidence_text=context,
                    source_field="requirements",
                    normalization_rule=normalized.normalization_rule,
                    confidence=normalized.confidence,
                ),
            )
        return sorted(
            requirements.values(),
            key=lambda item: (not item.required, item.normalized_name.casefold()),
        )

    @staticmethod
    def _merge_skill(
        requirements: dict[str, JobSkillRequirement],
        key: str,
        candidate: JobSkillRequirement,
    ) -> None:
        normalized_key = key.casefold()
        existing = requirements.get(normalized_key)
        if existing is None or (candidate.required and not existing.required):
            requirements[normalized_key] = candidate

    @staticmethod
    def _extract_experience(
        experience_level: str | None,
        text: str,
    ) -> tuple[float | None, bool]:
        graduate_exception = any(marker in text.casefold() for marker in GRADUATE_MARKERS)
        patterns = (
            r"(\d+(?:\.\d+)?)\s*(?:\+|年以上|年|years?|yrs?)",
            r"(?:at least|minimum|至少)\s*(\d+(?:\.\d+)?)\s*(?:years?|年)",
        )
        years: list[float] = []
        for pattern in patterns:
            years.extend(float(value) for value in re.findall(pattern, text, re.IGNORECASE))
        if years:
            return min(years), graduate_exception
        level_years = {
            "intern": 0,
            "internship": 0,
            "entry": 0,
            "junior": 1,
            "mid": 3,
            "middle": 3,
            "senior": 5,
            "lead": 7,
            "principal": 8,
            "应届": 0,
            "初级": 1,
            "中级": 3,
            "高级": 5,
            "资深": 7,
        }
        normalized_level = (experience_level or "").casefold()
        for marker, value in level_years.items():
            if marker in normalized_level:
                return float(value), graduate_exception
        return None, graduate_exception

    @staticmethod
    def _extract_education(value: str | None, text: str) -> str | None:
        haystack = f"{value or ''}\n{text}".casefold()
        levels = (
            ("DOCTORATE", ("doctorate", "doctoral", "phd", "博士")),
            ("MASTER", ("master", "硕士", "研究生")),
            ("BACHELOR", ("bachelor", "undergraduate degree", "本科", "学士")),
            ("ASSOCIATE", ("associate degree", "大专", "专科")),
            ("HIGH_SCHOOL", ("high school", "高中")),
        )
        for level, markers in levels:
            if any(marker in haystack for marker in markers):
                return level
        return None

    @staticmethod
    def _extract_languages(configured: list[str] | None, text: str) -> list[str]:
        languages = list(dict.fromkeys(item.strip() for item in (configured or []) if item.strip()))
        markers = (
            ("English", ("english", "英语", "英文")),
            ("Mandarin Chinese", ("mandarin", "普通话", "中文", "chinese")),
            ("Cantonese", ("cantonese", "粤语", "廣東話")),
            ("Japanese", ("japanese", "日语", "日文")),
            ("German", ("german", "德语")),
            ("French", ("french", "法语")),
        )
        normalized_text = text.casefold()
        for language, aliases in markers:
            if any(alias in normalized_text for alias in aliases):
                languages.append(language)
        return list(dict.fromkeys(languages))

    @staticmethod
    def _extract_certificates(text: str) -> tuple[list[str], bool]:
        certificates: list[str] = []
        required = False
        patterns = (
            ("PMP", r"(?<![A-Za-z0-9])PMP(?![A-Za-z0-9])"),
            ("AWS Certified", r"\bAWS\s+Certifi(?:ed|cation)\b"),
            ("CPA", r"\bCPA\b"),
            ("CFA", r"\bCFA\b"),
            ("教师资格证", r"教师资格证"),
        )
        for name, pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                certificates.append(name)
                context = JobRequirementExtractor._snippet(text, match.start(), match.end())
                context_key = context.casefold()
                required = required or any(marker in context_key for marker in REQUIRED_MARKERS)
        return certificates, required

    @staticmethod
    def _extract_work_eligibility(text: str) -> str | None:
        patterns = (
            r"[^。\n.]{0,60}(?:work authorization|eligible to work|visa sponsorship)[^。\n.]{0,80}",
            r"[^。\n.]{0,60}(?:工作许可|工作签证|签证担保|公民身份)[^。\n.]{0,80}",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return " ".join(match.group(0).split())[:300]
        return None

    @staticmethod
    def _as_strings(value: Any) -> Iterable[str]:
        if isinstance(value, str):
            return [item.strip() for item in re.split(r"[,，;/]", value) if item.strip()]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @staticmethod
    def _availability(value: object) -> AvailabilityStatus:
        if value is None or value == "" or value == []:
            return AvailabilityStatus.NOT_PROVIDED
        return AvailabilityStatus.PROVIDED

    @staticmethod
    def _snippet(text: str, start: int, end: int) -> str:
        delimiters = (".", "。", ";", "\n", "\uff1b")
        left = max((text.rfind(marker, 0, start) for marker in delimiters), default=-1) + 1
        right_candidates = [
            position for marker in delimiters if (position := text.find(marker, end)) >= 0
        ]
        right = min(right_candidates, default=len(text))
        if right - left > 240:
            left = max(0, start - 80)
            right = min(len(text), end + 100)
        return " ".join(text[left:right].split())

    @staticmethod
    def _optional_raw_string(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _criterion_is_explicit(
        self,
        text: str,
        criterion_markers: tuple[str, ...],
    ) -> bool:
        if self.policy is None:
            return False
        return self._criterion_has_marker(
            text,
            criterion_markers,
            tuple(self.policy.explicit_requirement_markers),
        )

    def _criterion_is_preferred(
        self,
        text: str,
        criterion_markers: tuple[str, ...],
    ) -> bool:
        if self.policy is None:
            return False
        return self._criterion_has_marker(
            text,
            criterion_markers,
            tuple(self.policy.preferred_requirement_markers),
        )

    @staticmethod
    def _criterion_has_marker(
        text: str,
        criterion_markers: tuple[str, ...],
        policy_markers: tuple[str, ...],
    ) -> bool:
        if not criterion_markers:
            return False
        for sentence in re.split(r"[。\n.;\uff1b]", text.casefold()):
            if any(marker.casefold() in sentence for marker in criterion_markers) and any(
                marker.casefold() in sentence for marker in policy_markers
            ):
                return True
        return False

    @staticmethod
    def _multiple_languages_are_unambiguous(text: str) -> bool:
        markers = (
            "both languages",
            "all languages",
            "each language",
            "all are required",
            "均须",
            "全部必须",
            "均需达到",
            "cefr",
            "ielts",
            "toefl",
            "jlpt",
            "hsk",
        )
        normalized = text.casefold()
        return any(marker in normalized for marker in markers)
