from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.users import User


class GeneratedMaterial(TimestampMixin, Base):
    __tablename__ = "generated_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resume_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="SET NULL"),
        index=True,
    )
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"),
        index=True,
    )
    match_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("match_reports.id", ondelete="SET NULL"),
        index=True,
    )
    material_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(24), default="DRAFT", nullable=False)
    content: Mapped[str] = mapped_column(Text)
    facts_used: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    is_human_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship()
