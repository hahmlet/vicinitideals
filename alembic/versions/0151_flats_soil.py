"""flats.soil_map_units, flats.soil_components, flats.lot_soil: the USDA soil survey per lot

FOLLOWUPS 196. A note beside the lot, never a colour: nothing that screens
reads these tables. Map units (by ``mukey``) and their components (by
``cokey``) are stored once; each lot holds one row per map unit touching it,
plus the part no survey covers (``mukey`` NULL). Filled by
``scripts/flats_lot_soil.py load``.

Revision ID: 0151
Revises: 0150
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0151"
down_revision = "0150"
branch_labels = None
depends_on = None

SCHEMA = "flats"


def upgrade() -> None:
    op.create_table(
        "soil_map_units",
        sa.Column("mukey", sa.String(30), primary_key=True),
        sa.Column("areasymbol", sa.String(20), nullable=False),
        sa.Column("areaname", sa.String(160)),
        sa.Column("saverest", sa.String(40)),
        sa.Column("musym", sa.String(20)),
        sa.Column("nationalmusym", sa.String(20)),
        sa.Column("muname", sa.String(240)),
        sa.Column("mukind", sa.String(40)),
        sa.Column("drclassdcd", sa.String(60)),
        sa.Column("hydgrpdcd", sa.String(10)),
        sa.Column("hydclprs", sa.Numeric(6, 1)),
        sa.Column("wtdepannmin", sa.Numeric(8, 1)),
        sa.Column("brockdepmin", sa.Numeric(8, 1)),
        sa.Column("engdwobdcd", sa.String(40)),
        sa.Column("dwellings_dcd", sa.String(40)),
        sa.Column("small_commercial_dcd", sa.String(40)),
        sa.Column("wet_season_status", sa.String(20)),
        sa.Column("wet_season_cm", sa.Numeric(8, 1)),
        sa.Column("wet_season_months", sa.String(120)),
        sa.Column("wet_season_cokey", sa.String(30)),
        sa.Column("source", sa.String(400)),
        schema=SCHEMA,
    )
    op.create_table(
        "soil_components",
        sa.Column("cokey", sa.String(30), primary_key=True),
        sa.Column(
            "mukey", sa.String(30), sa.ForeignKey(f"{SCHEMA}.soil_map_units.mukey", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("compname", sa.String(120)),
        sa.Column("comppct_r", sa.Numeric(6, 1)),
        sa.Column("majcompflag", sa.String(10)),
        sa.Column("compkind", sa.String(60)),
        sa.Column("taxclname", sa.String(240)),
        sa.Column("taxorder", sa.String(60)),
        sa.Column("taxsuborder", sa.String(60)),
        sa.Column("taxgrtgroup", sa.String(60)),
        sa.Column("taxsubgrp", sa.String(120)),
        sa.Column("taxpartsize", sa.String(120)),
        sa.Column("drainagecl", sa.String(60)),
        sa.Column("hydricrating", sa.String(20)),
        sa.Column("hydgrp", sa.String(10)),
        sa.Column("water_table_cm", sa.Numeric(8, 1)),
        sa.Column("water_table_month", sa.String(20)),
        sa.Column("lep_max", sa.Numeric(6, 2)),
        sa.Column("restriction_cm", sa.Numeric(8, 1)),
        sa.Column("restriction_kind", sa.String(80)),
        sa.Column("dwellings_rating", sa.String(40)),
        sa.Column("dwellings_reasons", sa.Text()),
        sa.Column("small_commercial_rating", sa.String(40)),
        sa.Column("small_commercial_reasons", sa.Text()),
        sa.Column("wet_season_status", sa.String(20)),
        sa.Column("wet_season_cm", sa.Numeric(8, 1)),
        sa.Column("wet_season_months", sa.String(120)),
        sa.Column("months", JSONB()),
        schema=SCHEMA,
    )
    op.create_index("ix_flats_soil_components_mukey", "soil_components", ["mukey"], schema=SCHEMA)
    op.create_table(
        "lot_soil",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("lot_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.lots.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "snapshot_id", sa.BigInteger(), sa.ForeignKey(f"{SCHEMA}.snapshots.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "mukey", sa.String(30), sa.ForeignKey(f"{SCHEMA}.soil_map_units.mukey", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("area_sqft", sa.Numeric(14, 1), nullable=False),
        sa.Column("share", sa.Numeric(8, 5), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_flats_lot_soil_lot", "lot_soil", ["lot_id"], schema=SCHEMA)
    op.create_index("ix_flats_lot_soil_snapshot", "lot_soil", ["snapshot_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_flats_lot_soil_snapshot", table_name="lot_soil", schema=SCHEMA)
    op.drop_index("ix_flats_lot_soil_lot", table_name="lot_soil", schema=SCHEMA)
    op.drop_table("lot_soil", schema=SCHEMA)
    op.drop_index("ix_flats_soil_components_mukey", table_name="soil_components", schema=SCHEMA)
    op.drop_table("soil_components", schema=SCHEMA)
    op.drop_table("soil_map_units", schema=SCHEMA)
