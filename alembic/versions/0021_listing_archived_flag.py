"""Add archived flag to scraped_listings; is_new no longer cleared by scraper

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scraped_listings",
        sa.Column("archived", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("scraped_listings", "archived")
