"""Add float_earnings_series JSON column to operational_outputs.

Stores per-source float-earnings (T-bond yield on Day-1 draws) results
so the UI can read the period-level balance schedule and warnings at
render time without re-running the simulation. Always written (None
when no float_earnings sources exist) so stale data clears.

Revision ID: 0103
Revises: 0102
Create Date: 2026-06-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operational_outputs",
        sa.Column("float_earnings_series", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("operational_outputs", "float_earnings_series")
