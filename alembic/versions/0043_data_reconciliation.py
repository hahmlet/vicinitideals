"""Add data reconciliation columns for parcel-listing matching.

New columns on scraped_listings:
- jurisdiction (from matched parcel, authoritative GIS source)
- match_strategy (apn / address / spatial / manual)
- match_confidence (0.0–1.0 quality score)
- lot_size_mismatch (flag when listing lot > parcel lot by 20%+)

New column on parcels:
- apn_normalized (stripped of dashes/spaces/dots for fuzzy APN matching)

New indexes on parcels:
- latitude, longitude (for spatial proximity queries)

Revision ID: 0043
Revises: 0042
Create Date: 2026-04-16
"""

import re

from alembic import op
import sqlalchemy as sa

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def _normalize_apn(apn: str) -> str:
    """Strip formatting characters for matching — mirrors app/reconciliation/matcher.py."""
    return re.sub(r"[\s\-\.\,]+", "", apn).upper()


def upgrade() -> None:
    # ── scraped_listings reconciliation columns ───────────────────────────
    op.add_column(
        "scraped_listings",
        sa.Column("jurisdiction", sa.String(120), nullable=True),
    )
    op.add_column(
        "scraped_listings",
        sa.Column("match_strategy", sa.String(30), nullable=True),
    )
    op.add_column(
        "scraped_listings",
        sa.Column("match_confidence", sa.Numeric(4, 3), nullable=True),
    )
    op.add_column(
        "scraped_listings",
        sa.Column("lot_size_mismatch", sa.Boolean(), nullable=True, server_default="false"),
    )
    op.create_index("ix_scraped_listings_jurisdiction", "scraped_listings", ["jurisdiction"])

    # ── parcels APN normalization column ──────────────────────────────────
    op.add_column(
        "parcels",
        sa.Column("apn_normalized", sa.String(100), nullable=True),
    )

    # Backfill apn_normalized from existing apn values
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, apn FROM parcels WHERE apn IS NOT NULL")).fetchall()
    if rows:
        for row_id, apn in rows:
            normalized = _normalize_apn(apn)
            conn.execute(
                sa.text("UPDATE parcels SET apn_normalized = :norm WHERE id = :id"),
                {"norm": normalized, "id": row_id},
            )

    op.create_index("ix_parcels_apn_normalized", "parcels", ["apn_normalized"])

    # ── Spatial proximity indexes ─────────────────────────────────────────
    op.create_index("ix_parcels_latitude", "parcels", ["latitude"])
    op.create_index("ix_parcels_longitude", "parcels", ["longitude"])


def downgrade() -> None:
    op.drop_index("ix_parcels_longitude", table_name="parcels")
    op.drop_index("ix_parcels_latitude", table_name="parcels")
    op.drop_index("ix_parcels_apn_normalized", table_name="parcels")
    op.drop_column("parcels", "apn_normalized")
    op.drop_index("ix_scraped_listings_jurisdiction", table_name="scraped_listings")
    op.drop_column("scraped_listings", "lot_size_mismatch")
    op.drop_column("scraped_listings", "match_confidence")
    op.drop_column("scraped_listings", "match_strategy")
    op.drop_column("scraped_listings", "jurisdiction")
