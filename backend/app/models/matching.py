from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import RequirementStatus, TaskStatus

if TYPE_CHECKING:
    from app.models.jobs import Job
    from app.models.resumes import ResumeVersion
    from app.models.users import User


class MatchReport(TimestampMixin, Base):
    __tablename__ = "match_reports"
    __table_args__ = (
        Index("ix_match_reports_user_created", "user_id", "created_at"),
        Index("ix_match_reports_job_score", "job_id", "final_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resume_version_id: Mapped[int] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"),
        index=True,
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, native_enum=False, length=24),
        default=TaskStatus.PENDING,
        nullable=False,
    )
    final_score: Mapped[float | None] = mapped_column(Float)
    rule_score: Mapped[float | None] = mapped_column(Float)
    semantic_score: Mapped[float | None] = mapped_column(Float)
    hybrid_score: Mapped[float | None] = mapped_column(Float)
    scoring_version: Mapped[str] = mapped_column(
        String(64),
        default="deterministic-v1",
        nullable=False,
        index=True,
    )
    scoring_config_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    current_phase: Mapped[str] = mapped_column(
        String(48),
        default="VALIDATING_INPUT",
        nullable=False,
    )
    phase_timings: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    job_requirements_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=dict,
        nullable=False,
    )
    matched_skills: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    partial_skills: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    missing_skills: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    recommendation_level: Mapped[str | None] = mapped_column(String(40))
    dimension_scores: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    hard_constraint_warnings: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    explanation: Mapped[str | None] = mapped_column(Text)
    recommended_actions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)

    user: Mapped[User] = relationship(back_populates="match_reports")
    resume_version: Mapped[ResumeVersion] = relationship()
    job: Mapped[Job] = relationship(back_populates="match_reports")
    details: Mapped[list[MatchDetail]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
    )


class MatchDetail(TimestampMixin, Base):
    __tablename__ = "match_details"
    __table_args__ = (Index("ix_match_details_report_status", "report_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("match_reports.id", ondelete="CASCADE"),
        index=True,
    )
    category: Mapped[str] = mapped_column(String(60), index=True)
    requirement: Mapped[str] = mapped_column(Text)
    status: Mapped[RequirementStatus] = mapped_column(
        Enum(RequirementStatus, native_enum=False, length=16),
        nullable=False,
    )
    score: Mapped[float | None] = mapped_column(Float)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    code: Mapped[str | None] = mapped_column(String(80), index=True)
    severity: Mapped[str | None] = mapped_column(String(16))
    explanation: Mapped[str | None] = mapped_column(Text)
    remediation: Mapped[str | None] = mapped_column(Text)
    matching_rule: Mapped[str | None] = mapped_column(String(80))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    report: Mapped[MatchReport] = relationship(back_populates="details")
    evidence: Mapped[list[MatchEvidence]] = relationship(
        back_populates="detail",
        cascade="all, delete-orphan",
    )


class MatchEvidence(TimestampMixin, Base):
    __tablename__ = "match_evidence"

    id: Mapped[int] = mapped_column(primary_key=True)
    detail_id: Mapped[int] = mapped_column(
        ForeignKey("match_details.id", ondelete="CASCADE"),
        index=True,
    )
    resume_evidence: Mapped[str | None] = mapped_column(Text)
    resume_source_id: Mapped[str | None] = mapped_column(String(120))
    job_evidence: Mapped[str | None] = mapped_column(Text)
    job_source_id: Mapped[str | None] = mapped_column(String(120))
    confidence: Mapped[float | None] = mapped_column(Float)
    resume_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"),
        index=True,
    )
    resume_skill_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_skills.id", ondelete="SET NULL"),
        index=True,
    )
    source_type: Mapped[str | None] = mapped_column(String(24))
    page_number: Mapped[int | None] = mapped_column(Integer)
    paragraph_index: Mapped[int | None] = mapped_column(Integer)
    matching_rule: Mapped[str | None] = mapped_column(String(80))
    conclusion_key: Mapped[str | None] = mapped_column(String(160), index=True)
    resume_section: Mapped[str | None] = mapped_column(String(50))

    detail: Mapped[MatchDetail] = relationship(back_populates="evidence")
