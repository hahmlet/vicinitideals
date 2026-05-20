"""Add auto Developer Fee fields to use_lines.

Auto-computed Developer Fee Use Line is seeded on every new deal. The engine
recomputes its `amount` each pass from `dev_fee_pct` * a basis (purchase price
or TPC excl self) determined per deal type. User overrides the % via the Use
drawer; $ is read-only and derived.

Fields:
- is_auto_dev_fee: marks the auto-managed Dev Fee row (one per scenario)
- dev_fee_pct: override % (snapshot from org/user default at seed time;
  user-editable thereafter)
- dev_fee_basis: 'purchase_price' or 'tpc_excl_self'

Revision ID: 0092
Revises: 0091
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "use_lines",
        sa.Column(
            "is_auto_dev_fee",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "use_lines",
        sa.Column("dev_fee_pct", sa.Numeric(8, 4), nullable=True),
    )
    op.add_column(
        "use_lines",
        sa.Column("dev_fee_basis", sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("use_lines", "dev_fee_basis")
    op.drop_column("use_lines", "dev_fee_pct")
    op.drop_column("use_lines", "is_auto_dev_fee")
