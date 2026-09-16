"""add prompt version to model usage logs

Revision ID: f4b7c8d9e012
Revises: e7c4a9d12b30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4b7c8d9e012"
down_revision: str | None = "e7c4a9d12b30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_usage_logs",
        sa.Column("prompt_version", sa.String(length=80), nullable=False, server_default="unknown"),
    )


def downgrade() -> None:
    op.drop_column("model_usage_logs", "prompt_version")
