from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.users import User


class InterviewSession(TimestampMixin, Base):
    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    resume_version_id: Mapped[int] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="RESTRICT"),
        index=True,
    )
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="RESTRICT"), index=True)
    interview_type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(24), default="PLANNED", nullable=False)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    # Chat-based interview fields (Stage 7 upgrade).
    dify_conversation_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    current_question_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_follow_up_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    chat_status: Mapped[str] = mapped_column(String(32), default="CREATED", nullable=False)

    user: Mapped[User] = relationship()
    questions: Mapped[list[InterviewQuestion]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InterviewQuestion.sequence",
    )
    messages: Mapped[list[InterviewMessage]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="InterviewMessage.sequence",
    )


class InterviewQuestion(TimestampMixin, Base):
    __tablename__ = "interview_questions"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_interview_questions_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer)
    question_type: Mapped[str] = mapped_column(String(40))
    prompt: Mapped[str] = mapped_column(Text)
    parent_question_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="SET NULL"),
        index=True,
    )

    session: Mapped[InterviewSession] = relationship(back_populates="questions")
class InterviewMessage(TimestampMixin, Base):
    """Chat message in the chat-based interview flow (Stage 7 upgrade).

    Stores both AI interviewer messages and user answers. The
    ``turn_metadata`` JSON column holds the hidden per-turn analysis
    (next_action, turn_analysis, unsupported_claims, used_facts, etc.)
    for ASSISTANT messages; it is empty for USER messages.
    """

    __tablename__ = "interview_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_interview_messages_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))  # USER or ASSISTANT
    content: Mapped[str] = mapped_column(Text)
    turn_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    session: Mapped[InterviewSession] = relationship(back_populates="messages")
