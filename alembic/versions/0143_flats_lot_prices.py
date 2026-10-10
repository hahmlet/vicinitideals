"""flats.lot_prices: each lot's price inputs as plain numbers

The Lots page filters and sorts on price per home (FOLLOWUPS 66). Working the
price out of each lot's JSON, and matching its zone against a few hundred
rules, on every request hung production (2026-10-10). The slow inputs are
stored here, one narrow row per lot: the price with its source name and as-of
date, a copy of the lot's area, and the zone's two density limits. Pods, homes
and price per home stay arithmetic on these numbers, so the pod size and the
road share remain adjustable per request.

The table is filled by the bridge loader (``scripts/flats_load_bridge.py``) and,
for a copy loaded earlier, by ``scripts/flats_backfill_lot_prices.py``. This
migration creates it empty; until it is filled the Lots page shows every lot
as "no price" (never hidden by the filter) rather than guessing.

Revision ID: 0143
Revises: 0142
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0143"
down_revision = "0142"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "lot_prices",
        sa.Column(
            "lot_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.lots.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "snapshot_id",
            sa.BigInteger(),
            sa.ForeignKey(f"{SCHEMA}.snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(16, 2), nullable=True),
        sa.Column("source", sa.String(80), nullable=True),
        sa.Column("as_of", sa.String(160), nullable=True),
        sa.Column("area_sqft", sa.Numeric(14, 2), nullable=True),
        sa.Column("cap_du_per_acre", sa.Numeric(10, 2), nullable=True),
        sa.Column("cap_unit_lot_sqft", sa.Numeric(12, 2), nullable=True),
        schema=SCHEMA,
    )
    op.create_index("ix_flats_lot_prices_snapshot", "lot_prices", ["snapshot_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_flats_lot_prices_snapshot", table_name="lot_prices", schema=SCHEMA)
    op.drop_table("lot_prices", schema=SCHEMA)
