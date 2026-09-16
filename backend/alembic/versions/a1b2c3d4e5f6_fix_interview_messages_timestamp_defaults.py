"""fix interview_messages timestamp server defaults

Revision ID: a1b2c3d4e5f6
Revises: ceb28daa6b95
Create Date: 2026-07-23 21:00:00.000000

Adds the missing ``server_default=func.now()`` to the
``interview_messages.created_at`` and ``interview_messages.updated_at``
columns. The original migration ``ceb28daa6b95`` created these columns
without server defaults, causing NOT NULL constraint failures when
SQLAlchemy relied on the database to populate them.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "ceb28daa6b95"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("interview_messages", schema=None) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        )


def downgrade() -> None:
    with op.batch_alter_table("interview_messages", schema=None) as batch_op:
        batch_op.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )
        batch_op.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )
