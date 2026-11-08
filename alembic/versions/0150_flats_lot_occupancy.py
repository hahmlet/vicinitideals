"""flats.lot_occupancy: what stands on each lot (vacant / teardown / house / larger)

FOLLOWUPS 125. A label beside the lot, never a colour (ruling
2026-10-14-existing-buildings-stay-green). Filled by
``scripts/flats_lot_occupancy.py load`` from a build of the footprint map
against a county copy's lots; the Lots page filters on ``label``.

Revision ID: 0150
Revises: 0149
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0150"
down_revision = "0149"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "lot_occupancy",
        sa.Column("lot_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.lots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "snapshot_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.snapshots.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("label", sa.String(20), nullable=False),
        sa.Column("disagreement", sa.String(40), nullable=True),
        sa.Column("building_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("main_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("footprint_sqft", sa.Numeric(14, 1), nullable=True),
        sa.Column("largest_sqft", sa.Numeric(14, 1), nullable=True),
        sa.Column("coverage", sa.Numeric(6, 4), nullable=True),
        sa.Column("building_value", sa.Numeric(16, 2), nullable=True),
        sa.Column("total_value", sa.Numeric(16, 2), nullable=True),
        sa.Column("year_built", sa.Integer(), nullable=True),
        sa.Column("roll_building_sqft", sa.Numeric(14, 1), nullable=True),
        sa.Column("source", sa.String(160), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_flats_lot_occupancy_snapshot_label", "lot_occupancy", ["snapshot_id", "label"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_flats_lot_occupancy_snapshot_label", table_name="lot_occupancy", schema=SCHEMA)
    op.drop_table("lot_occupancy", schema=SCHEMA)
