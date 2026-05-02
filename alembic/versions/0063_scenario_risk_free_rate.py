"""Add risk_free_rate_pct to scenarios.

Stores the 10Y Treasury rate at the time of underwriting so the investor
export can compute Cap Rate Spread and Levered IRR Spread in the Spread Stack
KPI block. NULL on existing rows; falls back to
settings.default_risk_free_rate_pct (4.25%) at export time.

Revision ID: 0063
Revises: 0062
Create Date: 2026-05-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column("risk_free_rate_pct", sa.Numeric(18, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scenarios", "risk_free_rate_pct")
