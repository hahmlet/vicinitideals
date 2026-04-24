"""Add apn_normalized array column to scraped_listings + backfill.

Cross-source APN matching needs a normalized form (uppercase, punctuation
stripped, multi-parcel split). The raw `apn` column remains as-is for GIS
queries which require county-specific formats.

Revision ID: 0054
Revises: 0053
Create Date: 2026-04-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scraped_listings",
        sa.Column(
            "apn_normalized",
            postgresql.ARRAY(sa.String()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )

    # Postgres-only backfill: build the normalized token array inline.
    # Matches app/scrapers/apn_utils.py normalize_apn() logic:
    #   uppercase, split on [,;\s]+, strip non-alphanumeric, drop empties, dedupe + sort.
    op.execute(
        """
        UPDATE scraped_listings
        SET apn_normalized = COALESCE(sub.tokens, ARRAY[]::varchar[])
        FROM (
            SELECT sl.id,
                   ARRAY(
                       SELECT DISTINCT regexp_replace(upper(tok), '[^A-Z0-9]', '', 'g')
                       FROM regexp_split_to_table(sl.apn, '[,;\\s]+') AS tok
                       WHERE tok <> ''
                         AND regexp_replace(upper(tok), '[^A-Z0-9]', '', 'g') <> ''
                       ORDER BY 1
                   ) AS tokens
            FROM scraped_listings sl
            WHERE sl.apn IS NOT NULL AND sl.apn <> ''
        ) AS sub
        WHERE scraped_listings.id = sub.id;
        """
    )

    # GIN index for fast array-overlap queries in the dedup scorer
    op.execute(
        "CREATE INDEX ix_scraped_listings_apn_normalized_gin "
        "ON scraped_listings USING GIN (apn_normalized)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_scraped_listings_apn_normalized_gin")
    op.drop_column("scraped_listings", "apn_normalized")
