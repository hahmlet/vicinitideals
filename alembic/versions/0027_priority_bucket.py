"""Add priority_bucket classification columns to parcels and scraped_listings

Revision ID: 0027
Revises: 0026
Create Date: 2026-04-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Parcel: add county, jurisdiction, and priority_bucket
    op.add_column("parcels", sa.Column("county", sa.String(120), nullable=True))
    op.add_column("parcels", sa.Column("jurisdiction", sa.String(120), nullable=True))
    op.add_column("parcels", sa.Column("priority_bucket", sa.String(30), nullable=True))
    op.create_index("ix_parcels_priority_bucket", "parcels", ["priority_bucket"])

    # ScrapedListing: add priority_bucket + timestamp
    op.add_column("scraped_listings", sa.Column("priority_bucket", sa.String(30), nullable=True))
    op.add_column("scraped_listings", sa.Column("priority_bucket_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_scraped_listings_priority_bucket", "scraped_listings", ["priority_bucket"])


def downgrade() -> None:
    op.drop_index("ix_scraped_listings_priority_bucket", "scraped_listings")
    op.drop_column("scraped_listings", "priority_bucket_at")
    op.drop_column("scraped_listings", "priority_bucket")

    op.drop_index("ix_parcels_priority_bucket", "parcels")
    op.drop_column("parcels", "priority_bucket")
    op.drop_column("parcels", "jurisdiction")
    op.drop_column("parcels", "county")
