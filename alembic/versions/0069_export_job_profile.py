"""Add export_profile to export_jobs.

Stores which export profile was requested (internal / lp / lender / proforma).
NULL on existing rows = treated as "internal" by the task worker.

Revision ID: 0069
Revises: 0068
Create Date: 2026-05-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='export_jobs' AND column_name='export_profile'"
        )
    ).scalar()
    if not exists:
        op.add_column(
            "export_jobs",
            sa.Column("export_profile", sa.String(20), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("export_jobs", "export_profile")
