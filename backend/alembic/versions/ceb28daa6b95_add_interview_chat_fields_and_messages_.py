"""add interview chat fields and messages table

Revision ID: ceb28daa6b95
Revises: c4a1e7b9d236
Create Date: 2026-07-23 01:51:03.818626
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ceb28daa6b95"
down_revision: str | Sequence[str] | None = "c4a1e7b9d236"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add chat-based interview columns to interview_sessions.
    with op.batch_alter_table("interview_sessions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("dify_conversation_id", sa.String(160), nullable=True)
        )
        batch_op.add_column(
            sa.Column("current_question_index", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("current_follow_up_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("chat_status", sa.String(32), nullable=False, server_default="CREATED")
        )

    # Create interview_messages table for chat-based interview flow.
    op.create_table(
        "interview_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer(),
            sa.ForeignKey("interview_sessions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("turn_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "session_id", "sequence", name="uq_interview_messages_sequence"
        ),
    )


def downgrade() -> None:
    op.drop_table("interview_messages")
    with op.batch_alter_table("interview_sessions", schema=None) as batch_op:
        batch_op.drop_column("chat_status")
        batch_op.drop_column("current_follow_up_count")
        batch_op.drop_column("current_question_index")
        batch_op.drop_column("dify_conversation_id")
