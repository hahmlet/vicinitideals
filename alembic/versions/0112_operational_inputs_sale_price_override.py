"""Add ``operational_inputs.sale_price_override``.

Manual sale-price override for the exit/disposition value. When set (> 0),
the cash-flow reversion uses this figure instead of stabilized
NOI / ``exit_cap_rate_pct``. Needed for projects whose stabilized NOI is
negative (lease-up drag), where the cap-rate formula yields a meaningless or
negative sale price. NULL → fall back to cap-rate valuation (existing
behaviour), so the column is additive and back-compatible.

Revision ID: 0112
Revises: 0111
Create Date: 2026-06-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0112"
down_revision = "0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operational_inputs",
        sa.Column("sale_price_override", sa.Numeric(18, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("operational_inputs", "sale_price_override")
