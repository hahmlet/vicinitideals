"""Add discount_rate_pct to scenarios.

Stores the investor's required rate of return (hurdle rate) per scenario.
Used by the investor export to compute DCF NPV and Weighted Equity Multiple.
NULL on existing rows; exporter defaults to 8.0% when absent.

Revision ID: 0065
Revises: 0064
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='scenarios' AND column_name='discount_rate_pct'"
        )
    ).scalar()
    if not exists:
        op.add_column(
            "scenarios",
            sa.Column("discount_rate_pct", sa.Numeric(18, 6), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("scenarios", "discount_rate_pct")
