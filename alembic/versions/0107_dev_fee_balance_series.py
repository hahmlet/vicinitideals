"""Add OperationalOutputs.dev_fee_balance_series for deferred Dev Fee tracking.

Phase B of the Float Earnings work wires deferred Dev Fee paydown
through the existing CF waterfall via a new
``WaterfallTierType.deferred_developer_fee`` tier consumer. The
engine writes a period-by-period balance schedule
(opening, paydown_amount, closing) onto this column so the explainer
modal can render it.

Always written (None when scenario has no deferred Dev Fee) so stale
data clears when the user removes the last deferred source.

Revision ID: 0107
Revises: 0106
Create Date: 2026-06-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operational_outputs",
        sa.Column("dev_fee_balance_series", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("operational_outputs", "dev_fee_balance_series")
