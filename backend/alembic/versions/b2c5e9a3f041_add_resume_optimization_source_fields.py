"""add resume optimization source fields

Revision ID: b2c5e9a3f041
Revises: f3a8c1d05b71
Create Date: 2026-07-22

Adds:
- generated_materials.match_report_id (nullable FK to match_reports)
- resume_versions.parent_version_id (nullable FK to resume_versions)

These columns record the provenance of resume optimization outputs and
the parent version used to create an optimized resume version. Both are
nullable so existing rows remain valid without backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c5e9a3f041"
down_revision: str | Sequence[str] | None = "f3a8c1d05b71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("generated_materials") as batch_op:
        batch_op.add_column(
            sa.Column("match_report_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_generated_materials_match_report_id_match_reports",
            "match_reports",
            ["match_report_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_generated_materials_match_report_id",
            ["match_report_id"],
            unique=False,
        )

    with op.batch_alter_table("resume_versions") as batch_op:
        batch_op.add_column(
            sa.Column("parent_version_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_resume_versions_parent_version_id_resume_versions",
            "resume_versions",
            ["parent_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_resume_versions_parent_version_id",
            ["parent_version_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("resume_versions") as batch_op:
        batch_op.drop_index(
            "ix_resume_versions_parent_version_id", table_name="resume_versions"
        )
        batch_op.drop_constraint(
            "fk_resume_versions_parent_version_id_resume_versions",
            type_="foreignkey",
        )
        batch_op.drop_column("parent_version_id")

    with op.batch_alter_table("generated_materials") as batch_op:
        batch_op.drop_index(
            "ix_generated_materials_match_report_id",
            table_name="generated_materials",
        )
        batch_op.drop_constraint(
            "fk_generated_materials_match_report_id_match_reports",
            type_="foreignkey",
        )
        batch_op.drop_column("match_report_id")
