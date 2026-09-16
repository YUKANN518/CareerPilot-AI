from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import JobSourceType, SourceStatus

if TYPE_CHECKING:
    from app.models.applications import Application
    from app.models.matching import MatchReport
    from app.models.resumes import Skill
    from app.models.users import User


class JobSource(TimestampMixin, Base):
    __tablename__ = "job_sources"
    __table_args__ = (Index("ix_job_sources_type_status", "source_type", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_by_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), unique=True)
    source_type: Mapped[JobSourceType] = mapped_column(
        Enum(JobSourceType, native_enum=False, length=24),
        nullable=False,
    )
    status: Mapped[SourceStatus] = mapped_column(
        Enum(SourceStatus, native_enum=False, length=16),
        default=SourceStatus.DRAFT,
        nullable=False,
    )
    base_url: Mapped[str | None] = mapped_column(String(1000))
    region: Mapped[str | None] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(20), default="en", nullable=False)
    sync_frequency_minutes: Mapped[int | None] = mapped_column(Integer)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_test_succeeded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


    jobs: Mapped[list[Job]] = relationship(back_populates="source", passive_deletes=True)



class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("source_id", "external_job_id", name="uq_jobs_source_external"),
        Index("ix_jobs_company_title", "company", "title"),
        Index("ix_jobs_location_status", "location", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("job_sources.id", ondelete="SET NULL"),
        index=True,
    )
    import_method: Mapped[str | None] = mapped_column(String(24), index=True)
    external_job_id: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(240), index=True)
    company: Mapped[str] = mapped_column(String(240), index=True)
    location: Mapped[str | None] = mapped_column(String(240), index=True)
    salary_min: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    salary_max: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str | None] = mapped_column(String(3))
    description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[str | None] = mapped_column(Text)
    employment_type: Mapped[str | None] = mapped_column(String(60), index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source_url: Mapped[str | None] = mapped_column(String(1000), index=True)
    normalized_source_url: Mapped[str | None] = mapped_column(String(1000), index=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    responsibilities: Mapped[str | None] = mapped_column(Text)
    experience_level: Mapped[str | None] = mapped_column(String(60), index=True)
    education_requirement: Mapped[str | None] = mapped_column(Text)
    language_requirements: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", nullable=False, index=True)

    source: Mapped[JobSource | None] = relationship(back_populates="jobs")
    owner: Mapped[User | None] = relationship(foreign_keys=[owner_id])
    skills: Mapped[list[JobSkill]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
    favorites: Mapped[list[JobFavorite]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )
    match_reports: Mapped[list[MatchReport]] = relationship(back_populates="job")
    applications: Mapped[list[Application]] = relationship(back_populates="job")


class JobSkill(TimestampMixin, Base):
    __tablename__ = "job_skills"
    __table_args__ = (UniqueConstraint("job_id", "skill_id", name="uq_job_skills_job_skill"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"), index=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    evidence_text: Mapped[str | None] = mapped_column(Text)

    job: Mapped[Job] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship()


class JobFavorite(TimestampMixin, Base):
    __tablename__ = "job_favorites"
    __table_args__ = (UniqueConstraint("user_id", "job_id", name="uq_job_favorites_user_job"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)

    user: Mapped[User] = relationship(back_populates="job_favorites")
    job: Mapped[Job] = relationship(back_populates="favorites")
