"""add learning plan structured task fields

Revision ID: f3a8c1d05b71
Revises: d4f7a2c91e30
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f3a8c1d05b71"
down_revision: str | Sequence[str] | None = "d4f7a2c91e30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("learning_tasks") as batch_op:
        batch_op.add_column(sa.Column("target_skill", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("priority", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("estimated_hours", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "success_criteria",
                sa.JSON(),
                server_default=sa.text("'[]'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "source_conclusion_keys",
                sa.JSON(),
                server_default=sa.text("'[]'"),
                nullable=False,
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("learning_tasks") as batch_op:
        batch_op.drop_column("source_conclusion_keys")
        batch_op.drop_column("success_criteria")
        batch_op.drop_column("estimated_hours")
        batch_op.drop_column("priority")
        batch_op.drop_column("target_skill")
