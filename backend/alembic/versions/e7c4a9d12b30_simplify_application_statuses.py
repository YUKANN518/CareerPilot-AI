"""simplify application statuses to the portfolio-facing five-state funnel

Revision ID: e7c4a9d12b30
Revises: a1b2c3d4e5f6
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e7c4a9d12b30"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUS_MAPPING = {
    "PREPARING": "SAVED",
    "ASSESSMENT": "INTERVIEW",
    "ACCEPTED": "OFFER",
    "WITHDRAWN": "REJECTED",
}


def upgrade() -> None:
    for old_status, new_status in STATUS_MAPPING.items():
        op.execute(
            "UPDATE application_status_history "
            f"SET from_status = '{new_status}' WHERE from_status = '{old_status}'"
        )
        op.execute(
            "UPDATE application_status_history "
            f"SET to_status = '{new_status}' WHERE to_status = '{old_status}'"
        )
        op.execute(
            f"UPDATE applications SET status = '{new_status}' WHERE status = '{old_status}'"
        )
    op.drop_table("interview_answers")
    op.drop_table("job_sync_logs")
    op.drop_table("job_sync_tasks")
    op.drop_table("job_source_credentials")
    op.drop_table("job_source_configs")
    op.drop_table("learning_tasks")
    op.drop_table("learning_plans")


def downgrade() -> None:
    # Retired feature data and the old status distinctions cannot be reconstructed.
    pass
