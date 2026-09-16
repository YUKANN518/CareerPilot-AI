"""add resume center workflow fields

Revision ID: 1c4e67a25b20
Revises: 6a1b1e896948
Create Date: 2026-07-17
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "1c4e67a25b20"
down_revision: str | Sequence[str] | None = "6a1b1e896948"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

old_resume_status = sa.Enum(
    "DRAFT",
    "PARSED",
    "CONFIRMED",
    "ARCHIVED",
    name="resumestatus",
    native_enum=False,
    length=16,
)
new_resume_status = sa.Enum(
    "UPLOADED",
    "EXTRACTING",
    "EXTRACTED",
    "PARSING",
    "NEEDS_CONFIRMATION",
    "CONFIRMED",
    "FAILED",
    "ARCHIVED",
    name="resumestatus",
    native_enum=False,
    length=24,
)


def upgrade() -> None:
    with op.batch_alter_table("file_assets") as batch_op:
        batch_op.add_column(sa.Column("file_format", sa.String(length=10), nullable=True))

    op.execute(
        """
        UPDATE file_assets
        SET file_format = CASE
            WHEN lower(mime_type) = 'application/pdf' THEN 'pdf'
            WHEN lower(mime_type) LIKE '%wordprocessingml%' THEN 'docx'
            WHEN lower(original_name) LIKE '%.pdf' THEN 'pdf'
            WHEN lower(original_name) LIKE '%.docx' THEN 'docx'
            ELSE 'unknown'
        END
        """
    )
    with op.batch_alter_table("file_assets") as batch_op:
        batch_op.alter_column(
            "file_format",
            existing_type=sa.String(length=10),
            nullable=False,
        )

    with op.batch_alter_table("resume_skills") as batch_op:
        batch_op.add_column(
            sa.Column(
                "source_location",
                sa.String(length=500),
                nullable=False,
                server_default=(
                    '{"source_type":"unknown","page_number":null,'
                    '"block_index":null,"paragraph_index":null,'
                    '"table_index":null,"row_index":null,"label":"legacy"}'
                ),
            )
        )
        batch_op.add_column(
            sa.Column(
                "is_user_confirmed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )

    with op.batch_alter_table("resumes") as batch_op:
        batch_op.add_column(sa.Column("extracted_text", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "extracted_blocks",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch_op.add_column(sa.Column("parse_result", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "parse_attempts",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch_op.add_column(
            sa.Column("last_error_code", sa.String(length=80), nullable=True)
        )
        batch_op.add_column(sa.Column("last_error_message", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True)
        )

    op.execute("UPDATE resumes SET status = 'UPLOADED' WHERE status = 'DRAFT'")
    op.execute("UPDATE resumes SET status = 'NEEDS_CONFIRMATION' WHERE status = 'PARSED'")
    with op.batch_alter_table("resumes") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=old_resume_status,
            type_=new_resume_status,
            existing_nullable=False,
        )
        batch_op.alter_column(
            "extracted_blocks",
            existing_type=sa.JSON(),
            server_default=None,
            existing_nullable=False,
        )
        batch_op.alter_column(
            "parse_attempts",
            existing_type=sa.Integer(),
            server_default=None,
            existing_nullable=False,
        )

    with op.batch_alter_table("resume_skills") as batch_op:
        batch_op.alter_column(
            "source_location",
            existing_type=sa.String(length=500),
            server_default=None,
            existing_nullable=False,
        )
        batch_op.alter_column(
            "is_user_confirmed",
            existing_type=sa.Boolean(),
            server_default=None,
            existing_nullable=False,
        )


def downgrade() -> None:
    op.execute(
        """
        UPDATE resumes
        SET status = CASE
            WHEN status IN ('PARSING', 'NEEDS_CONFIRMATION') THEN 'PARSED'
            WHEN status = 'CONFIRMED' THEN 'CONFIRMED'
            WHEN status = 'ARCHIVED' THEN 'ARCHIVED'
            ELSE 'DRAFT'
        END
        """
    )
    with op.batch_alter_table("resumes") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=new_resume_status,
            type_=old_resume_status,
            existing_nullable=False,
        )
        batch_op.drop_column("confirmed_at")
        batch_op.drop_column("parsed_at")
        batch_op.drop_column("extracted_at")
        batch_op.drop_column("last_error_message")
        batch_op.drop_column("last_error_code")
        batch_op.drop_column("parse_attempts")
        batch_op.drop_column("parse_result")
        batch_op.drop_column("extracted_blocks")
        batch_op.drop_column("extracted_text")

    with op.batch_alter_table("resume_skills") as batch_op:
        batch_op.drop_column("is_user_confirmed")
        batch_op.drop_column("source_location")

    with op.batch_alter_table("file_assets") as batch_op:
        batch_op.drop_column("file_format")
