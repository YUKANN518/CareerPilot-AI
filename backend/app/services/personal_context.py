"""Personal context retrieval service for Stage 4B personalised QA.

Reads the user's own private data (resume, match reports and applications)
and converts it into ``PersonalContextChunk``
objects that can be passed to the Dify knowledge QA workflow alongside
the shared knowledge-base chunks.

All queries are strictly owner-scoped on ``user_id``. The service never
crosses ownership boundaries and never exposes other users' data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.applications import Application
from app.models.matching import MatchReport
from app.models.resumes import Resume, ResumeVersion
from app.schemas.career_assistant import PersonalContextChunk


@dataclass(frozen=True)
class _PersonalContextLimits:
    """Per-source caps to keep the workflow input within ``max_length=10``."""

    resume: int = 2
    match_report: int = 3
    application: int = 2


class PersonalContextService:
    """Retrieve user-private data as ``PersonalContextChunk`` objects."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._limits = _PersonalContextLimits()

    def retrieve(self, user_id: int, question: str) -> list[PersonalContextChunk]:
        """Build the personal context list for one user and question.

        Returns at most 10 chunks across all sources. Each chunk's
        ``chunk_text`` is a compact, self-contained summary so the Dify
        LLM can answer without seeing the full resume or match report.
        """
        chunks: list[PersonalContextChunk] = []
        chunks.extend(self._resume_chunks(user_id))
        chunks.extend(self._match_report_chunks(user_id, question))
        chunks.extend(self._application_chunks(user_id))
        return chunks[:10]

    # ------------------------------------------------------------------
    # Source-specific retrievers
    # ------------------------------------------------------------------

    def _resume_chunks(self, user_id: int) -> list[PersonalContextChunk]:
        resume = self.session.scalar(
            select(Resume)
            .where(Resume.owner_id == user_id)
            .order_by(Resume.created_at.desc())
            .limit(1)
        )
        if resume is None:
            return []
        version = self.session.scalar(
            select(ResumeVersion)
            .where(
                ResumeVersion.resume_id == resume.id,
                ResumeVersion.is_current.is_(True),
            )
            .order_by(ResumeVersion.version_number.desc())
            .limit(1)
        )
        if version is None:
            version = self.session.scalar(
                select(ResumeVersion)
                .where(ResumeVersion.resume_id == resume.id)
                .order_by(ResumeVersion.version_number.desc())
                .limit(1)
            )
        if version is None or not version.structured_data:
            return []

        summary_text = self._summarise_resume(resume.title, version)
        if not summary_text:
            return []
        return [
            PersonalContextChunk(
                source_type="resume",
                source_id=version.id,
                title=resume.title,
                category="resume",
                chunk_text=summary_text,
                chunk_index=0,
                score=1.0,
            )
        ]

    def _match_report_chunks(
        self,
        user_id: int,
        question: str,
    ) -> list[PersonalContextChunk]:
        reports = list(
            self.session.scalars(
                select(MatchReport)
                .where(MatchReport.user_id == user_id)
                .order_by(MatchReport.created_at.desc())
                .limit(self._limits.match_report)
            ).all()
        )
        chunks: list[PersonalContextChunk] = []
        for index, report in enumerate(reports):
            text = self._summarise_match_report(report)
            if not text:
                continue
            chunks.append(
                PersonalContextChunk(
                    source_type="match_report",
                    source_id=report.id,
                    title=f"Match report #{report.id}",
                    category="match_report",
                    chunk_text=text,
                    chunk_index=index,
                    score=1.0,
                )
            )
        return chunks

    def _application_chunks(self, user_id: int) -> list[PersonalContextChunk]:
        applications = list(
            self.session.scalars(
                select(Application)
                .where(Application.user_id == user_id)
                .order_by(Application.created_at.desc())
                .limit(self._limits.application)
            ).all()
        )
        chunks: list[PersonalContextChunk] = []
        for index, app in enumerate(applications):
            text = self._summarise_application(app)
            if not text:
                continue
            chunks.append(
                PersonalContextChunk(
                    source_type="application",
                    source_id=app.id,
                    title=f"Application #{app.id}",
                    category="application",
                    chunk_text=text,
                    chunk_index=index,
                    score=1.0,
                )
            )
        return chunks

    # ------------------------------------------------------------------
    # Summarisers (compact, self-contained text for the LLM)
    # ------------------------------------------------------------------

    @staticmethod
    def _summarise_resume(title: str, version: ResumeVersion) -> str:
        data = version.structured_data or {}
        parts: list[str] = [f"Resume: {title} (version {version.version_number})"]

        basic = data.get("basic_info") or {}
        if isinstance(basic, dict):
            full_name = _evidence_value(basic.get("full_name"))
            summary = _evidence_value(basic.get("summary"))
            if full_name:
                parts.append(f"Name: {full_name}")
            if summary:
                parts.append(f"Summary: {summary}")

        skills: list[str] = []
        for group_key in ("technical_skills", "soft_skills"):
            group = data.get(group_key)
            if isinstance(group, list):
                for item in group:
                    name = _evidence_value(item.get("name")) if isinstance(item, dict) else ""
                    if name:
                        skills.append(name)
        if skills:
            parts.append(f"Skills: {', '.join(skills[:20])}")

        experience = data.get("work_experience")
        if isinstance(experience, list):
            for item in experience[:3]:
                if not isinstance(item, dict):
                    continue
                company = _evidence_value(item.get("company"))
                role = _evidence_value(item.get("title"))
                desc = _evidence_value(item.get("description"))
                if company or role:
                    parts.append(
                        f"Experience: {role or ''} @ {company or ''}".strip()
                        + (f" — {desc}" if desc else "")
                    )

        education = data.get("education")
        if isinstance(education, list):
            for item in education[:2]:
                if not isinstance(item, dict):
                    continue
                institution = _evidence_value(item.get("institution"))
                degree = _evidence_value(item.get("degree"))
                field = _evidence_value(item.get("field_of_study"))
                if institution or degree:
                    parts.append(
                        f"Education: {degree or ''} in {field or ''} @ {institution or ''}".strip()
                    )

        text = "\n".join(part for part in parts if part.strip())
        return text[:4000]

    @staticmethod
    def _summarise_match_report(report: MatchReport) -> str:
        parts: list[str] = [
            f"Match report #{report.id} (score: {report.final_score:.2f})"
            if report.final_score is not None
            else f"Match report #{report.id}"
        ]
        matched = report.matched_skills or []
        partial = report.partial_skills or []
        missing = report.missing_skills or []
        if matched:
            names = ", ".join(_skill_name(item) for item in matched[:15])
            parts.append(f"Matched skills: {names}")
        if partial:
            names = ", ".join(_skill_name(item) for item in partial[:10])
            parts.append(f"Partial skills: {names}")
        if missing:
            names = ", ".join(_skill_name(item) for item in missing[:10])
            parts.append(f"Missing skills: {names}")
        if report.recommendation_level:
            parts.append(f"Recommendation: {report.recommendation_level}")
        if report.explanation:
            parts.append(f"Explanation: {report.explanation[:500]}")
        text = "\n".join(part for part in parts if part.strip())
        return text[:4000]

    @staticmethod
    def _summarise_application(app: Application) -> str:
        parts: list[str] = [f"Application #{app.id} (status: {app.status.value})"]
        if app.notes:
            parts.append(f"Notes: {app.notes[:500]}")
        if app.next_action_at:
            parts.append(f"Next action: {app.next_action_at.isoformat()}")
        text = "\n".join(part for part in parts if part.strip())
        return text[:4000]


def _evidence_value(field: object) -> str:
    """Extract the ``value`` from an evidence-field dict, or return ``""``."""
    if isinstance(field, dict):
        value = field.get("value")
        if isinstance(value, str):
            return value
    return ""


def _skill_name(item: object) -> str:
    """Extract a skill name from a match-report skill dict."""
    if isinstance(item, dict):
        for key in ("name", "skill_name", "label"):
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
        return json.dumps(item, ensure_ascii=False)[:80]
    return str(item)[:80]
