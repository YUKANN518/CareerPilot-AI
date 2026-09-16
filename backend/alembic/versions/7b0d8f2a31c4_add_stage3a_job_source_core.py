"""add stage 3a job source core

Revision ID: 7b0d8f2a31c4
Revises: 1c4e67a25b20
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "7b0d8f2a31c4"
down_revision: str | Sequence[str] | None = "1c4e67a25b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

old_source_type = sa.Enum(
    "MANUAL",
    "SINGLE_URL",
    "CSV",
    "GENERIC_HTML",
    "API",
    name="jobsourcetype",
    native_enum=False,
    length=24,
)
new_source_type = sa.Enum(
    "MANUAL",
    "CSV",
    "GENERIC_HTML",
    "REST_API",
    "SINGLE_JOB_URL",
    name="jobsourcetype",
    native_enum=False,
    length=24,
)


def upgrade() -> None:
    with op.batch_alter_table("job_sources") as batch_op:
        batch_op.add_column(
            sa.Column("language", sa.String(length=20), nullable=False, server_default="en")
        )
        batch_op.add_column(sa.Column("sync_frequency_minutes", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "last_test_succeeded",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True))

    op.execute("UPDATE job_sources SET source_type = 'REST_API' WHERE source_type = 'API'")
    op.execute(
        "UPDATE job_sources SET source_type = 'SINGLE_JOB_URL' "
        "WHERE source_type = 'SINGLE_URL'"
    )
    with op.batch_alter_table("job_sources") as batch_op:
        batch_op.alter_column(
            "source_type",
            existing_type=old_source_type,
            type_=new_source_type,
            existing_nullable=False,
        )
        batch_op.alter_column(
            "language",
            existing_type=sa.String(length=20),
            server_default=None,
            existing_nullable=False,
        )
        batch_op.alter_column(
            "last_test_succeeded",
            existing_type=sa.Boolean(),
            server_default=None,
            existing_nullable=False,
        )

    with op.batch_alter_table("job_source_configs") as batch_op:
        batch_op.add_column(
            sa.Column(
                "request_body",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "pagination_config",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "source_payload",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.alter_column(
            "request_body",
            existing_type=sa.JSON(),
            server_default=None,
            existing_nullable=False,
        )
        batch_op.alter_column(
            "pagination_config",
            existing_type=sa.JSON(),
            server_default=None,
            existing_nullable=False,
        )
        batch_op.alter_column(
            "source_payload",
            existing_type=sa.JSON(),
            server_default=None,
            existing_nullable=False,
        )

    with op.batch_alter_table("job_sync_tasks") as batch_op:
        batch_op.add_column(
            sa.Column("updated_count", sa.Integer(), nullable=False, server_default=sa.text("0"))
        )
        batch_op.add_column(
            sa.Column(
                "duplicate_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column("task_kind", sa.String(length=16), nullable=False, server_default="SYNC")
        )
        batch_op.add_column(
            sa.Column(
                "result_summary",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(sa.Column("error_message", sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f("ix_job_sync_tasks_task_kind"), ["task_kind"])
        for column_name, column_type in (
            ("updated_count", sa.Integer()),
            ("duplicate_count", sa.Integer()),
            ("task_kind", sa.String(length=16)),
            ("result_summary", sa.JSON()),
        ):
            batch_op.alter_column(
                column_name,
                existing_type=column_type,
                server_default=None,
                existing_nullable=False,
            )

    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("normalized_source_url", sa.String(length=1000)))
        batch_op.add_column(sa.Column("responsibilities", sa.Text()))
        batch_op.add_column(sa.Column("experience_level", sa.String(length=60)))
        batch_op.add_column(sa.Column("education_requirement", sa.Text()))
        batch_op.add_column(
            sa.Column(
                "language_requirements",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "raw_data",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.create_index(
            batch_op.f("ix_jobs_normalized_source_url"),
            ["normalized_source_url"],
        )
        batch_op.create_index(batch_op.f("ix_jobs_experience_level"), ["experience_level"])
        batch_op.alter_column(
            "language_requirements",
            existing_type=sa.JSON(),
            server_default=None,
            existing_nullable=False,
        )
        batch_op.alter_column(
            "raw_data",
            existing_type=sa.JSON(),
            server_default=None,
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_index(batch_op.f("ix_jobs_experience_level"))
        batch_op.drop_index(batch_op.f("ix_jobs_normalized_source_url"))
        batch_op.drop_column("raw_data")
        batch_op.drop_column("language_requirements")
        batch_op.drop_column("education_requirement")
        batch_op.drop_column("experience_level")
        batch_op.drop_column("responsibilities")
        batch_op.drop_column("normalized_source_url")

    with op.batch_alter_table("job_sync_tasks") as batch_op:
        batch_op.drop_index(batch_op.f("ix_job_sync_tasks_task_kind"))
        batch_op.drop_column("error_message")
        batch_op.drop_column("result_summary")
        batch_op.drop_column("task_kind")
        batch_op.drop_column("duplicate_count")
        batch_op.drop_column("updated_count")

    with op.batch_alter_table("job_source_configs") as batch_op:
        batch_op.drop_column("source_payload")
        batch_op.drop_column("pagination_config")
        batch_op.drop_column("request_body")

    op.execute("UPDATE job_sources SET source_type = 'API' WHERE source_type = 'REST_API'")
    op.execute(
        "UPDATE job_sources SET source_type = 'SINGLE_URL' "
        "WHERE source_type = 'SINGLE_JOB_URL'"
    )
    with op.batch_alter_table("job_sources") as batch_op:
        batch_op.alter_column(
            "source_type",
            existing_type=new_source_type,
            type_=old_source_type,
            existing_nullable=False,
        )
        batch_op.drop_column("last_sync_at")
        batch_op.drop_column("last_test_succeeded")
        batch_op.drop_column("sync_frequency_minutes")
        batch_op.drop_column("language")
