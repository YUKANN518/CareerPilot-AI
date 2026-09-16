from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.models.jobs import Job
from app.models.resumes import ResumeVersion


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _field_value(value: object) -> str:
    if isinstance(value, dict):
        raw = value.get("value")
        return str(raw).strip() if raw is not None else ""
    return str(value).strip() if value is not None else ""


def _source(value: object) -> tuple[int | None, int | None]:
    if not isinstance(value, dict):
        return None, None
    location = value.get("source_location")
    if not isinstance(location, dict):
        return None, None
    page = location.get("page_number")
    paragraph = location.get("paragraph_index")
    return (
        int(page) if isinstance(page, int) and page > 0 else None,
        int(paragraph) if isinstance(paragraph, int) and paragraph >= 0 else None,
    )


def _record_text(record: object) -> tuple[str, int | None, int | None]:
    if not isinstance(record, dict):
        return _field_value(record), None, None
    values = [_field_value(value) for value in record.values()]
    source = next(
        (_source(value) for value in record.values() if _source(value) != (None, None)),
        (None, None),
    )
    return " | ".join(value for value in values if value), source[0], source[1]


class SemanticDocumentFactory:
    def __init__(self, *, chunk_size: int = 600, chunk_overlap: int = 80) -> None:
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def resume_documents(self, version: ResumeVersion, user_id: int) -> list[Document]:
        if not version.is_confirmed:
            return []
        documents: list[Document] = []
        structured = version.structured_data
        section_map = {
            "project_experience": "project_experience",
            "work_experience": "work_experience",
            "education": "education",
            "certificates": "certificate",
        }
        for source_key, section in section_map.items():
            records = structured.get(source_key, [])
            if not isinstance(records, list):
                continue
            for index, record in enumerate(records):
                text, page, paragraph = _record_text(record)
                documents.extend(
                    self._documents(
                        text,
                        {
                            "user_id": user_id,
                            "resume_version_id": version.id,
                            "job_id": 0,
                            "source_type": "resume",
                            "source_record_id": f"{source_key}:{index}",
                            "section": section,
                            "page_number": page,
                            "paragraph_index": paragraph,
                        },
                    )
                )
        for skill in version.skills:
            if not skill.is_user_confirmed or not skill.evidence_text.strip():
                continue
            page, paragraph = self._skill_location(skill.source_location)
            documents.extend(
                self._documents(
                    f"{skill.skill.name}: {skill.evidence_text}",
                    {
                        "user_id": user_id,
                        "resume_version_id": version.id,
                        "job_id": 0,
                        "source_type": "resume",
                        "source_record_id": f"resume_skill:{skill.id}",
                        "section": "skill_evidence",
                        "page_number": page,
                        "paragraph_index": paragraph,
                    },
                )
            )
        return self._deduplicate(documents)

    def job_documents(self, job: Job) -> list[Document]:
        owner_id = job.owner_id or 0
        fields: list[tuple[str, str | None]] = [
            ("title", job.title),
            ("description", job.description),
            ("responsibilities", job.responsibilities),
            ("requirements", job.requirements),
            ("experience_requirement", job.experience_level),
            ("education_requirement", job.education_requirement),
            ("language_requirement", " | ".join(job.language_requirements)),
        ]
        required = [item.skill.name for item in job.skills if item.is_required]
        preferred = [item.skill.name for item in job.skills if not item.is_required]
        fields.extend(
            [
                ("required_skills", " | ".join(required)),
                ("preferred_skills", " | ".join(preferred)),
            ]
        )
        documents: list[Document] = []
        for field, text in fields:
            documents.extend(
                self._documents(
                    text or "",
                    {
                        "user_id": owner_id,
                        "resume_version_id": 0,
                        "job_id": job.id,
                        "source_type": "job",
                        "source_record_id": f"job:{job.id}:{field}",
                        "section": field,
                        "page_number": None,
                        "paragraph_index": None,
                    },
                )
            )
        return self._deduplicate(documents)

    def _documents(self, text: str, metadata: dict[str, object]) -> list[Document]:
        cleaned = " ".join(text.split())
        if not cleaned:
            return []
        chunks = self.splitter.split_text(cleaned)
        result = []
        for index, chunk in enumerate(chunks):
            content_hash = _hash(chunk)
            result.append(
                Document(
                    page_content=chunk,
                    metadata={
                        **metadata,
                        "source_record_id": f"{metadata['source_record_id']}:{index}",
                        "original_text": cleaned,
                        "content_hash": content_hash,
                    },
                )
            )
        return result

    @staticmethod
    def _deduplicate(documents: Iterable[Document]) -> list[Document]:
        result: list[Document] = []
        seen: set[str] = set()
        for document in documents:
            content_hash = str(document.metadata["content_hash"])
            if content_hash in seen:
                continue
            seen.add(content_hash)
            result.append(document)
        return result

    @staticmethod
    def _skill_location(raw: str) -> tuple[int | None, int | None]:
        try:
            location = json.loads(raw)
        except (TypeError, ValueError):
            return None, None
        page = location.get("page_number")
        paragraph = location.get("paragraph_index")
        return (
            int(page) if isinstance(page, int) and page > 0 else None,
            int(paragraph) if isinstance(paragraph, int) and paragraph >= 0 else None,
        )
