"""add knowledge document indexing fields

Revision ID: c4a1e7b9d236
Revises: b2c5e9a3f041
Create Date: 2026-07-22

Adds indexing-related columns to ``knowledge_documents`` for the Stage 4A
Career Assistant knowledge base QA feature:

- ``content_hash``: SHA-256 of extracted text, used for change detection
  and deduplication of re-indexing work.
- ``index_path``: relative path to the FAISS index directory for this
  document.
- ``error_code`` / ``error_message``: structured failure info when
  indexing fails (mirrors ``resumes.last_error_code`` pattern).
- ``indexed_at``: timestamp of the last successful indexing run.

All columns are nullable so existing rows remain valid without backfill.
No new table is created; the existing ``knowledge_documents`` table is
extended in place.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a1e7b9d236"
down_revision: str | Sequence[str] | None = "b2c5e9a3f041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_documents") as batch_op:
        batch_op.add_column(
            sa.Column("content_hash", sa.String(length=64), nullable=True)
        )
        batch_op.add_column(
            sa.Column("index_path", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("error_code", sa.String(length=80), nullable=True)
        )
        batch_op.add_column(
            sa.Column("error_message", sa.Text(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_index(
            "ix_knowledge_documents_content_hash",
            ["content_hash"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("knowledge_documents") as batch_op:
        batch_op.drop_index(
            "ix_knowledge_documents_content_hash",
            table_name="knowledge_documents",
        )
        batch_op.drop_column("indexed_at")
        batch_op.drop_column("error_message")
        batch_op.drop_column("error_code")
        batch_op.drop_column("index_path")
        batch_op.drop_column("content_hash")
