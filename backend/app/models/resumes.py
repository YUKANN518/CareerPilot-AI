from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import ResumeStatus

if TYPE_CHECKING:
    from app.models.users import User


class FileAsset(TimestampMixin, Base):
    __tablename__ = "file_assets"
    __table_args__ = (UniqueConstraint("owner_id", "sha256", name="uq_file_assets_owner_sha256"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True)
    original_name: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    file_format: Mapped[str] = mapped_column(String(10), nullable=False)

    owner: Mapped[User] = relationship(back_populates="files")
    resumes: Mapped[list[Resume]] = relationship(back_populates="file_asset")


class Resume(TimestampMixin, Base):
    __tablename__ = "resumes"
    __table_args__ = (Index("ix_resumes_owner_status", "owner_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    file_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("file_assets.id", ondelete="SET NULL"),
        index=True,
    )
    title: Mapped[str] = mapped_column(String(200))
    status: Mapped[ResumeStatus] = mapped_column(
        Enum(ResumeStatus, native_enum=False, length=24),
        default=ResumeStatus.UPLOADED,
        nullable=False,
    )
    extracted_text: Mapped[str | None] = mapped_column(Text)
    extracted_blocks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    parse_result: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    parse_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    last_error_message: Mapped[str | None] = mapped_column(Text)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner: Mapped[User] = relationship(back_populates="resumes")
    file_asset: Mapped[FileAsset | None] = relationship(back_populates="resumes")
    versions: Mapped[list[ResumeVersion]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        order_by="ResumeVersion.version_number",
    )


class ResumeVersion(TimestampMixin, Base):
    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint("resume_id", "version_number", name="uq_resume_versions_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.id", ondelete="CASCADE"),
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer)
    raw_text: Mapped[str | None] = mapped_column(Text)
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="SET NULL"),
        index=True,
    )

    resume: Mapped[Resume] = relationship(back_populates="versions")
    sections: Mapped[list[ResumeSection]] = relationship(
        back_populates="resume_version",
        cascade="all, delete-orphan",
    )
    skills: Mapped[list[ResumeSkill]] = relationship(
        back_populates="resume_version",
        cascade="all, delete-orphan",
    )


class ResumeSection(TimestampMixin, Base):
    __tablename__ = "resume_sections"
    __table_args__ = (
        UniqueConstraint(
            "resume_version_id",
            "section_type",
            "sort_order",
            name="uq_resume_sections_position",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_version_id: Mapped[int] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"),
        index=True,
    )
    section_type: Mapped[str] = mapped_column(String(50), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_locator: Mapped[str | None] = mapped_column(String(255))

    resume_version: Mapped[ResumeVersion] = relationship(back_populates="sections")


class Skill(TimestampMixin, Base):
    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    category: Mapped[str | None] = mapped_column(String(80), index=True)
    description: Mapped[str | None] = mapped_column(Text)

    aliases: Mapped[list[SkillAlias]] = relationship(
        back_populates="skill",
        cascade="all, delete-orphan",
    )
    resume_skills: Mapped[list[ResumeSkill]] = relationship(back_populates="skill")


class SkillAlias(TimestampMixin, Base):
    __tablename__ = "skill_aliases"

    id: Mapped[int] = mapped_column(primary_key=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(120), unique=True, index=True)

    skill: Mapped[Skill] = relationship(back_populates="aliases")


class ResumeSkill(TimestampMixin, Base):
    __tablename__ = "resume_skills"
    __table_args__ = (
        UniqueConstraint(
            "resume_version_id",
            "skill_id",
            "evidence_source_id",
            name="uq_resume_skills_evidence",
        ),
        Index("ix_resume_skills_version_confidence", "resume_version_id", "confidence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    resume_version_id: Mapped[int] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="CASCADE"),
        index=True,
    )
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.id", ondelete="RESTRICT"), index=True)
    raw_name: Mapped[str] = mapped_column(String(120))
    level: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float)
    evidence_text: Mapped[str] = mapped_column(Text)
    evidence_section: Mapped[str] = mapped_column(String(50))
    evidence_source_id: Mapped[str] = mapped_column(String(120))
    source_location: Mapped[str] = mapped_column(String(500))
    is_user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    resume_version: Mapped[ResumeVersion] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship(back_populates="resume_skills")
