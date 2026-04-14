"""REAL-15 scenario run versioning

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-03 19:45:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0006"
down_revision = ("0005", "0007")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "scenario_results",
        sa.Column("run_number", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("scenario_results", "run_number")
    op.drop_column("scenarios", "run_count")
