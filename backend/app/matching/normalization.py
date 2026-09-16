from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.schemas.matching import NormalizedSkill

DICTIONARY_VERSION = "skill-dictionary-v1"


@dataclass(frozen=True)
class SkillDictionaryEntry:
    canonical_name: str
    category: str
    aliases: tuple[str, ...]


LOCAL_DICTIONARY = (
    SkillDictionaryEntry(
        "Python",
        "PROGRAMMING_LANGUAGE",
        ("python", "python3", "py", "python语言", "python 開發"),
    ),
    SkillDictionaryEntry(
        "JavaScript",
        "PROGRAMMING_LANGUAGE",
        ("javascript", "java script", "js", "ecmascript", "javascript语言"),
    ),
    SkillDictionaryEntry(
        "TypeScript",
        "PROGRAMMING_LANGUAGE",
        ("typescript", "type script", "ts", "typescript语言"),
    ),
    SkillDictionaryEntry(
        "Vue",
        "FRONTEND_FRAMEWORK",
        ("vue", "vue.js", "vuejs", "vue 3", "vue3", "vue框架"),
    ),
    SkillDictionaryEntry(
        "React",
        "FRONTEND_FRAMEWORK",
        ("react", "react.js", "reactjs", "react框架"),
    ),
    SkillDictionaryEntry(
        "FastAPI",
        "BACKEND_FRAMEWORK",
        ("fastapi", "fast api", "fast-api", "fastapi框架"),
    ),
    SkillDictionaryEntry(
        "RESTful API",
        "API",
        ("restful api", "rest api", "restful", "rest接口", "rest api设计"),
    ),
    SkillDictionaryEntry(
        "PostgreSQL",
        "DATABASE",
        ("postgresql", "postgres", "postgre sql", "postgresql数据库"),
    ),
    SkillDictionaryEntry(
        "SQL",
        "DATABASE",
        ("sql", "结构化查询语言", "sql语言"),
    ),
    SkillDictionaryEntry(
        "Docker",
        "DEVOPS",
        ("docker", "docker容器", "容器化docker"),
    ),
    SkillDictionaryEntry(
        "Kubernetes",
        "DEVOPS",
        ("kubernetes", "k8s", "kubernetes集群", "容器编排"),
    ),
    SkillDictionaryEntry(
        "CI/CD",
        "DEVOPS",
        ("ci/cd", "cicd", "ci cd", "持续集成", "持续交付", "持续集成持续交付"),
    ),
    SkillDictionaryEntry(
        "Git",
        "DEVELOPER_TOOL",
        ("git", "git版本控制", "版本控制git"),
    ),
    SkillDictionaryEntry(
        "Machine Learning",
        "ARTIFICIAL_INTELLIGENCE",
        ("machine learning", "ml", "机器学习", "機器學習"),
    ),
    SkillDictionaryEntry(
        "Artificial Intelligence",
        "ARTIFICIAL_INTELLIGENCE",
        ("artificial intelligence", "ai", "人工智能", "人工智慧"),
    ),
    SkillDictionaryEntry(
        "NLP",
        "ARTIFICIAL_INTELLIGENCE",
        ("nlp", "natural language processing", "自然语言处理", "自然語言處理"),
    ),
    SkillDictionaryEntry(
        "Data Analysis",
        "DATA",
        ("data analysis", "data analytics", "数据分析", "資料分析"),
    ),
    SkillDictionaryEntry(
        "Project Management",
        "SOFT_SKILL",
        ("project management", "项目管理", "專案管理"),
    ),
    SkillDictionaryEntry(
        "Communication",
        "SOFT_SKILL",
        ("communication", "communication skills", "沟通能力", "溝通能力"),
    ),
)


class SkillNormalizationService:
    """Normalize skill names with a local, versioned and deterministic dictionary."""

    def __init__(
        self,
        database_aliases: Mapping[str, tuple[str, str | None]] | None = None,
    ) -> None:
        self._database_aliases = {
            self._key(alias): value for alias, value in (database_aliases or {}).items()
        }
        self._local_aliases: dict[str, tuple[str, str]] = {}
        self._canonical: dict[str, tuple[str, str]] = {}
        for entry in LOCAL_DICTIONARY:
            self._canonical[self._key(entry.canonical_name)] = (
                entry.canonical_name,
                entry.category,
            )
            for alias in entry.aliases:
                self._local_aliases[self._key(alias)] = (
                    entry.canonical_name,
                    entry.category,
                )
        self._compact_aliases = {
            self._compact(alias): value
            for alias, value in {**self._canonical, **self._local_aliases}.items()
            if len(self._compact(alias)) >= 2
        }

    @staticmethod
    def _key(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value).casefold().strip()
        normalized = re.sub(r"[\s._-]+", " ", normalized)
        normalized = re.sub(r"\s*/\s*", "/", normalized)
        return normalized.strip(" ,;:()[]{}")

    @staticmethod
    def _compact(value: str) -> str:
        return re.sub(r"[\s./_-]+", "", value)

    @property
    def dictionary_version(self) -> str:
        return DICTIONARY_VERSION

    def normalize(self, raw_name: str) -> NormalizedSkill:
        stripped = unicodedata.normalize("NFKC", raw_name).strip()
        key = self._key(stripped)
        if not key:
            return NormalizedSkill(
                raw_name=raw_name,
                normalized_name="",
                category=None,
                normalization_rule="EMPTY_INPUT",
                confidence=0,
                dictionary_version=DICTIONARY_VERSION,
            )
        if key in self._database_aliases:
            name, category = self._database_aliases[key]
            return self._result(raw_name, name, category, "DATABASE_ALIAS", 1)
        if key in self._canonical:
            name, category = self._canonical[key]
            return self._result(raw_name, name, category, "CANONICAL_EXACT", 1)
        if key in self._local_aliases:
            name, category = self._local_aliases[key]
            return self._result(raw_name, name, category, "LOCAL_ALIAS", 0.98)
        compact = self._compact(key)
        if compact in self._compact_aliases:
            name, category = self._compact_aliases[compact]
            return self._result(raw_name, name, category, "PUNCTUATION_ALIAS", 0.95)
        return self._result(
            raw_name,
            stripped,
            None,
            "NORMALIZED_TEXT",
            0.75,
        )

    def known_terms(self) -> Iterable[tuple[str, NormalizedSkill]]:
        seen: set[str] = set()
        terms = [
            *(entry.canonical_name for entry in LOCAL_DICTIONARY),
            *(alias for entry in LOCAL_DICTIONARY for alias in entry.aliases),
            *self._database_aliases.keys(),
        ]
        for term in sorted(terms, key=lambda item: (-len(item), item.casefold())):
            normalized = self.normalize(term)
            if term.casefold() in seen:
                continue
            seen.add(term.casefold())
            yield term, normalized

    def find_mentions(self, text: str) -> list[tuple[int, int, str, NormalizedSkill]]:
        mentions: list[tuple[int, int, str, NormalizedSkill]] = []
        occupied: list[tuple[int, int]] = []
        for term, normalized in self.known_terms():
            escaped = re.escape(term)
            if term.isascii() and term[0].isalnum() and term[-1].isalnum():
                pattern = rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
            else:
                pattern = escaped
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                start, end = match.span()
                if any(start < used_end and end > used_start for used_start, used_end in occupied):
                    continue
                occupied.append((start, end))
                mentions.append((start, end, match.group(0), normalized))
        return sorted(mentions, key=lambda item: item[0])

    @staticmethod
    def _result(
        raw_name: str,
        normalized_name: str,
        category: str | None,
        rule: str,
        confidence: float,
    ) -> NormalizedSkill:
        return NormalizedSkill(
            raw_name=raw_name,
            normalized_name=normalized_name,
            category=category,
            normalization_rule=rule,
            confidence=confidence,
            dictionary_version=DICTIONARY_VERSION,
        )
