"""add deterministic matching fields

Revision ID: d4f7a2c91e30
Revises: a81e4c9d72f6
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d4f7a2c91e30"
down_revision: str | Sequence[str] | None = "a81e4c9d72f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("match_reports") as batch_op:
        batch_op.drop_constraint(
            "fk_match_reports_resume_version_id_resume_versions",
            type_="foreignkey",
        )
        batch_op.create_foreign_key(
            "fk_match_reports_resume_version_id_resume_versions",
            "resume_versions",
            ["resume_version_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.add_column(sa.Column("rule_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("semantic_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("hybrid_score", sa.Float(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "scoring_version",
                sa.String(length=64),
                server_default="deterministic-v1",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "scoring_config_snapshot",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "current_phase",
                sa.String(length=48),
                server_default="VALIDATING_INPUT",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "phase_timings",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "job_requirements_snapshot",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "matched_skills",
                sa.JSON(),
                server_default=sa.text("'[]'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "partial_skills",
                sa.JSON(),
                server_default=sa.text("'[]'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "missing_skills",
                sa.JSON(),
                server_default=sa.text("'[]'"),
                nullable=False,
            )
        )
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("error_code", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("error_message", sa.Text(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_match_reports_scoring_version"),
            ["scoring_version"],
        )

    with op.batch_alter_table("match_details") as batch_op:
        batch_op.add_column(sa.Column("code", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("severity", sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column("explanation", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("remediation", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("matching_rule", sa.String(length=80), nullable=True))
        batch_op.add_column(
            sa.Column(
                "data",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            )
        )
        batch_op.create_index(batch_op.f("ix_match_details_code"), ["code"])

    with op.batch_alter_table("match_evidence") as batch_op:
        batch_op.add_column(sa.Column("resume_version_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("resume_skill_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("source_type", sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column("page_number", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("paragraph_index", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("matching_rule", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("conclusion_key", sa.String(length=160), nullable=True))
        batch_op.add_column(sa.Column("resume_section", sa.String(length=50), nullable=True))
        batch_op.create_foreign_key(
            "fk_match_evidence_resume_version_id_resume_versions",
            "resume_versions",
            ["resume_version_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_match_evidence_resume_skill_id_resume_skills",
            "resume_skills",
            ["resume_skill_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            batch_op.f("ix_match_evidence_resume_version_id"),
            ["resume_version_id"],
        )
        batch_op.create_index(
            batch_op.f("ix_match_evidence_resume_skill_id"),
            ["resume_skill_id"],
        )
        batch_op.create_index(
            batch_op.f("ix_match_evidence_conclusion_key"),
            ["conclusion_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("match_evidence") as batch_op:
        batch_op.drop_index(batch_op.f("ix_match_evidence_conclusion_key"))
        batch_op.drop_index(batch_op.f("ix_match_evidence_resume_skill_id"))
        batch_op.drop_index(batch_op.f("ix_match_evidence_resume_version_id"))
        batch_op.drop_constraint(
            "fk_match_evidence_resume_skill_id_resume_skills",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_match_evidence_resume_version_id_resume_versions",
            type_="foreignkey",
        )
        batch_op.drop_column("matching_rule")
        batch_op.drop_column("resume_section")
        batch_op.drop_column("conclusion_key")
        batch_op.drop_column("paragraph_index")
        batch_op.drop_column("page_number")
        batch_op.drop_column("source_type")
        batch_op.drop_column("resume_skill_id")
        batch_op.drop_column("resume_version_id")

    with op.batch_alter_table("match_details") as batch_op:
        batch_op.drop_index(batch_op.f("ix_match_details_code"))
        batch_op.drop_column("data")
        batch_op.drop_column("matching_rule")
        batch_op.drop_column("remediation")
        batch_op.drop_column("explanation")
        batch_op.drop_column("severity")
        batch_op.drop_column("code")

    with op.batch_alter_table("match_reports") as batch_op:
        batch_op.drop_index(batch_op.f("ix_match_reports_scoring_version"))
        batch_op.drop_column("error_message")
        batch_op.drop_column("error_code")
        batch_op.drop_column("duration_ms")
        batch_op.drop_column("finished_at")
        batch_op.drop_column("started_at")
        batch_op.drop_column("missing_skills")
        batch_op.drop_column("partial_skills")
        batch_op.drop_column("matched_skills")
        batch_op.drop_column("job_requirements_snapshot")
        batch_op.drop_column("phase_timings")
        batch_op.drop_column("current_phase")
        batch_op.drop_column("scoring_config_snapshot")
        batch_op.drop_column("scoring_version")
        batch_op.drop_column("hybrid_score")
        batch_op.drop_column("semantic_score")
        batch_op.drop_column("rule_score")
        batch_op.drop_constraint(
            "fk_match_reports_resume_version_id_resume_versions",
            type_="foreignkey",
        )
        batch_op.create_foreign_key(
            "fk_match_reports_resume_version_id_resume_versions",
            "resume_versions",
            ["resume_version_id"],
            ["id"],
            ondelete="RESTRICT",
        )
