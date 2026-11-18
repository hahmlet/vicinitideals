"""flats.lot_hazards, flats.hazard_layers: mapped ground hazards per lot

FOLLOWUPS 198. Landslide, earthquake-liquefaction and flood classes per lot,
a note beside the lot, never a colour: nothing that screens reads these
tables. Filled by ``scripts/flats_lot_hazards.py load``.

Follows 0151 (the soil notes, FOLLOWUPS 196), which reached main first.

Revision ID: 0152
Revises: 0151
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0152"
down_revision = "0151"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "lot_hazards",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("lot_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.lots.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "snapshot_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.snapshots.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("hazard", sa.String(20), nullable=False),
        sa.Column("layer", sa.String(40), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("class_code", sa.String(120)),
        sa.Column("class_label", sa.String(240)),
        sa.Column("area_sqft", sa.Numeric(14, 1), nullable=False),
        sa.Column("share", sa.Numeric(8, 5), nullable=False),
        sa.Column("detail", JSONB()),
        schema=SCHEMA,
    )
    op.create_index("ix_flats_lot_hazards_lot", "lot_hazards", ["lot_id"], schema=SCHEMA)
    op.create_index("ix_flats_lot_hazards_snapshot_layer", "lot_hazards", ["snapshot_id", "layer"], schema=SCHEMA)
    op.create_table(
        "hazard_layers",
        sa.Column(
            "snapshot_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.snapshots.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("layer", sa.String(40), primary_key=True),
        sa.Column("source", sa.String(600), nullable=False),
        sa.Column("detail", JSONB()),
        sa.Column("loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("hazard_layers", schema=SCHEMA)
    op.drop_index("ix_flats_lot_hazards_snapshot_layer", table_name="lot_hazards", schema=SCHEMA)
    op.drop_index("ix_flats_lot_hazards_lot", table_name="lot_hazards", schema=SCHEMA)
    op.drop_table("lot_hazards", schema=SCHEMA)
