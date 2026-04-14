"""Add Realie enrichment columns to scraped_listings and create realie_usage table

Revision ID: 0023
Revises: 0022
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # scraped_listings — 3 new columns (phase 1: raw JSON approach)
    op.add_column(
        "scraped_listings",
        sa.Column("realie_enriched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "scraped_listings",
        sa.Column("realie_match_confidence", sa.Numeric(4, 3), nullable=True),
    )
    op.add_column(
        "scraped_listings",
        sa.Column("realie_raw_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # realie_usage — monthly call budget tracking
    op.create_table(
        "realie_usage",
        sa.Column("month", sa.String(7), nullable=False),
        sa.Column("calls_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("call_limit", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("last_call_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("month"),
    )


def downgrade() -> None:
    op.drop_table("realie_usage")
    op.drop_column("scraped_listings", "realie_raw_json")
    op.drop_column("scraped_listings", "realie_match_confidence")
    op.drop_column("scraped_listings", "realie_enriched_at")
