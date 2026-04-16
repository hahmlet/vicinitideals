"""Add HelloData model parity fields.

New columns:
- income_streams: bad_debt_pct, concessions_pct, renovation_absorption_rate
- operational_inputs: asset_mgmt_fee_pct

CapitalSourceSchema gains refi_cap_rate_pct and prepay_penalty_pct as JSONB
fields (no migration needed — extra="allow" on the Pydantic schema).

debt_sizing_mode comment updated to include "dual_constraint" but the column
is already String(20), no DDL change needed.

Revision ID: 0042
Revises: 0041
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── IncomeStream new columns ──────────────────────────────────────────
    op.add_column(
        "income_streams",
        sa.Column("bad_debt_pct", sa.Numeric(18, 6), nullable=False, server_default="0"),
    )
    op.add_column(
        "income_streams",
        sa.Column("concessions_pct", sa.Numeric(18, 6), nullable=False, server_default="0"),
    )
    op.add_column(
        "income_streams",
        sa.Column("renovation_absorption_rate", sa.Numeric(18, 6), nullable=True),
    )

    # ── OperationalInputs new columns ─────────────────────────────────────
    op.add_column(
        "operational_inputs",
        sa.Column("asset_mgmt_fee_pct", sa.Numeric(18, 6), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("operational_inputs", "asset_mgmt_fee_pct")
    op.drop_column("income_streams", "renovation_absorption_rate")
    op.drop_column("income_streams", "concessions_pct")
    op.drop_column("income_streams", "bad_debt_pct")
