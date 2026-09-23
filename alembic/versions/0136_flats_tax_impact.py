"""flats.tax_snapshots, flats.tax_impact_lots -- what a green lot pays in tax

The pitch to a city is "the pod on this lot pays $Y more property tax than
what is there now, or than one new house". A tax snapshot prices every green
lot of one jurisdiction three ways -- today (A), one new single-family house
(B), the pod partitioned into four fee-simple lots at the low and high end of
its per-unit value band (C) -- under Oregon's Measures 5 and 50
(``flats/tax/``), and stores the figures with every input behind them in
``params``. A one-off: nothing recomputes a snapshot when lots are re-screened.

Revision ID: 0136
Revises: 0135
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0136"
down_revision = "0135"
branch_labels = None
depends_on = None

SCHEMA = "flats"

SCENARIOS = ("a", "b", "c_low", "c_high")
FIGURES = ("av", "total", "local_option", "city", "city_local_option", "ten_year")


def upgrade() -> None:
    op.create_table(
        "tax_snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("jurisdiction", sa.String(length=80), nullable=False),
        sa.Column("tax_year", sa.String(length=16), nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["run_id"], [f"{SCHEMA}.runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema=SCHEMA,
    )
    op.create_table(
        "tax_impact_lots",
        sa.Column("tax_snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("lot_id", sa.BigInteger(), nullable=False),
        sa.Column("tlid", sa.String(length=40), nullable=False),
        sa.Column("green_source", sa.String(length=16), nullable=False),
        sa.Column("taxcode", sa.String(length=8), nullable=True),
        *[
            sa.Column(f"{s}_{f}", sa.Numeric(14, 2), nullable=True)
            for s in SCENARIOS
            for f in FIGURES
        ],
        sa.Column("notes", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["tax_snapshot_id"], [f"{SCHEMA}.tax_snapshots.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lot_id"], [f"{SCHEMA}.lots.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tax_snapshot_id", "lot_id"),
        schema=SCHEMA,
    )
    op.create_index("ix_flats_tax_impact_lots_lot", "tax_impact_lots", ["lot_id"], unique=False, schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_flats_tax_impact_lots_lot", table_name="tax_impact_lots", schema=SCHEMA)
    op.drop_table("tax_impact_lots", schema=SCHEMA)
    op.drop_table("tax_snapshots", schema=SCHEMA)
