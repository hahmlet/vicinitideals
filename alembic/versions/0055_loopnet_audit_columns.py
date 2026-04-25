"""Tier 1 + Tier 3 columns for LoopNet audit-discovered fields.

Tier 1 — first-class typed columns for underwriting/comp metrics:
  - apartment_style          (Mid-Rise / Garden / Low-Rise / High-Rise / Townhome)
  - construction_status      (Existing / Proposed / Under Construction / Renovating)
  - parking_ratio            ("1.39/1,000 SF" — display-formatted; comp filter)
  - building_far             (Decimal — Floor Area Ratio for development analysis)
  - gross_rent_multiplier    (Decimal — direct income comp metric)
  - on_ground_lease          (Boolean — material investment fact)

Tier 3 — display/context surfaces (exposed for UI without raw_json drilling):
  - highlights               (ARRAY of bullet strings)
  - attachments              (JSON list of {url, description} broker docs)
  - nearby_transportation    (JSON list of transit stops with distances)

All optional (nullable). Backfilled from existing raw_json by
scripts/backfill_loopnet_mf_fields.py.

Revision ID: 0055
Revises: 0054
Create Date: 2026-04-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scraped_listings",
        sa.Column("apartment_style", sa.String(40), nullable=True),
    )
    op.add_column(
        "scraped_listings",
        sa.Column("construction_status", sa.String(40), nullable=True),
    )
    op.add_column(
        "scraped_listings",
        sa.Column("parking_ratio", sa.String(60), nullable=True),
    )
    op.add_column(
        "scraped_listings",
        sa.Column("building_far", sa.Numeric(8, 4), nullable=True),
    )
    op.add_column(
        "scraped_listings",
        sa.Column("gross_rent_multiplier", sa.Numeric(8, 4), nullable=True),
    )
    op.add_column(
        "scraped_listings",
        sa.Column("on_ground_lease", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "scraped_listings",
        sa.Column(
            "highlights",
            postgresql.ARRAY(sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )
    op.add_column(
        "scraped_listings",
        sa.Column(
            "attachments",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )
    op.add_column(
        "scraped_listings",
        sa.Column(
            "nearby_transportation",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("scraped_listings", "nearby_transportation")
    op.drop_column("scraped_listings", "attachments")
    op.drop_column("scraped_listings", "highlights")
    op.drop_column("scraped_listings", "on_ground_lease")
    op.drop_column("scraped_listings", "gross_rent_multiplier")
    op.drop_column("scraped_listings", "building_far")
    op.drop_column("scraped_listings", "parking_ratio")
    op.drop_column("scraped_listings", "construction_status")
    op.drop_column("scraped_listings", "apartment_style")
