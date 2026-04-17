"""Add HelloData.ai enrichment columns and usage tracking table.

New on scraped_listings:
- hellodata_skip (bool) — user/auto flag to skip enrichment
- hellodata_enriched_at (ts) — set when any HelloData endpoint returned data
- hellodata_property_id (str) — HelloData UUID from /property/search
- hellodata_raw_search / raw_rents / raw_expenses / raw_comparables (JSON)
- hellodata_market_rent_per_unit / per_sqft (numeric)
- hellodata_egi_per_unit / noi_per_unit / opex_per_unit (numeric)
- hellodata_occupancy_pct (numeric)

New table: hellodata_usage — monthly budget tracking in cents.

Revision ID: 0045
Revises: 0044
Create Date: 2026-04-17
"""

from alembic import op
import sqlalchemy as sa

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── scraped_listings HelloData columns ────────────────────────────────
    op.add_column(
        "scraped_listings",
        sa.Column("hellodata_skip", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "scraped_listings",
        sa.Column("hellodata_enriched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "scraped_listings",
        sa.Column("hellodata_property_id", sa.String(64), nullable=True),
    )
    op.add_column("scraped_listings", sa.Column("hellodata_raw_search", sa.JSON(), nullable=True))
    op.add_column("scraped_listings", sa.Column("hellodata_raw_rents", sa.JSON(), nullable=True))
    op.add_column("scraped_listings", sa.Column("hellodata_raw_expenses", sa.JSON(), nullable=True))
    op.add_column("scraped_listings", sa.Column("hellodata_raw_comparables", sa.JSON(), nullable=True))

    # Synthesized comp fields
    op.add_column("scraped_listings", sa.Column("hellodata_market_rent_per_unit", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("hellodata_market_rent_per_sqft", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("hellodata_egi_per_unit", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("hellodata_noi_per_unit", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("hellodata_opex_per_unit", sa.Numeric(18, 6), nullable=True))
    op.add_column("scraped_listings", sa.Column("hellodata_occupancy_pct", sa.Numeric(5, 4), nullable=True))

    # ── hellodata_usage table ─────────────────────────────────────────────
    op.create_table(
        "hellodata_usage",
        sa.Column("month", sa.String(7), primary_key=True),
        sa.Column("calls_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("budget_cents", sa.Integer(), nullable=False, server_default="10000"),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_call_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("hellodata_usage")
    for col in (
        "hellodata_occupancy_pct",
        "hellodata_opex_per_unit",
        "hellodata_noi_per_unit",
        "hellodata_egi_per_unit",
        "hellodata_market_rent_per_sqft",
        "hellodata_market_rent_per_unit",
        "hellodata_raw_comparables",
        "hellodata_raw_expenses",
        "hellodata_raw_rents",
        "hellodata_raw_search",
        "hellodata_property_id",
        "hellodata_enriched_at",
        "hellodata_skip",
    ):
        op.drop_column("scraped_listings", col)
