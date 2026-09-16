"""add stage 3b user job ownership

Revision ID: a81e4c9d72f6
Revises: 7b0d8f2a31c4
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "a81e4c9d72f6"
down_revision: str | Sequence[str] | None = "7b0d8f2a31c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("owner_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("import_method", sa.String(length=24), nullable=True))
        batch_op.create_foreign_key(
            "fk_jobs_owner_id_users",
            "users",
            ["owner_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(batch_op.f("ix_jobs_owner_id"), ["owner_id"])
        batch_op.create_index(batch_op.f("ix_jobs_import_method"), ["import_method"])


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_index(batch_op.f("ix_jobs_import_method"))
        batch_op.drop_index(batch_op.f("ix_jobs_owner_id"))
        batch_op.drop_constraint("fk_jobs_owner_id_users", type_="foreignkey")
        batch_op.drop_column("import_method")
        batch_op.drop_column("owner_id")
