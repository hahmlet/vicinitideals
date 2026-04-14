"""Add realie_skip to scraped_listings and multi_parcel_dismissed to opportunities

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scraped_listings",
        sa.Column("realie_skip", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "opportunities",
        sa.Column("multi_parcel_dismissed", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("opportunities", "multi_parcel_dismissed")
    op.drop_column("scraped_listings", "realie_skip")
