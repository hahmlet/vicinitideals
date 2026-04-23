"""LoopNet scraper support: API call log, listing snapshots, field conflict log,
plus polygon_tags array on scraped_listings for polygon-tier classification.

Four changes, all additive:

  - api_call_log             — monthly budget tracking for LoopNet RapidAPI
  - listing_snapshots        — 30-day experiment snapshots of SaleDetails/ExtendedDetails
  - field_conflict_log       — per-field disagreement log written on manual dedup merges
  - scraped_listings.polygon_tags — ARRAY(String) tagging each listing with the polygon
                                    name(s) that contain its lat/lng; drives target vs
                                    comp-only filtering

Revision ID: 0048
Revises: 0047
Create Date: 2026-04-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ----------------------------------- scraped_listings.polygon_tags (new col)
    op.add_column(
        "scraped_listings",
        sa.Column(
            "polygon_tags",
            postgresql.ARRAY(sa.String()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
    )
    # ------------------------------------------------------------------ api_call_log
    op.create_table(
        "api_call_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("endpoint", sa.String(64), nullable=False),
        sa.Column("listing_source_id", sa.String(64), nullable=True),
        sa.Column(
            "called_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("status_code", sa.Integer, nullable=True),
        sa.Column("billing_month", sa.Date, nullable=False),
    )
    op.create_index(
        "ix_api_call_log_month_source",
        "api_call_log",
        ["billing_month", "source"],
    )

    # --------------------------------------------------------- listing_snapshots
    op.create_table(
        "listing_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scraped_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "captured_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("endpoint", sa.String(32), nullable=False),
        sa.Column(
            "raw_json",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("source_last_updated", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_listing_snapshots_listing_captured",
        "listing_snapshots",
        ["listing_id", "captured_at"],
    )

    # ------------------------------------------------------- field_conflict_log
    op.create_table(
        "field_conflict_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "merge_candidate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("dedup_candidates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "canonical_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scraped_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "loser_listing_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("scraped_listings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field_name", sa.String(64), nullable=False),
        sa.Column("canonical_value", sa.Text, nullable=True),
        sa.Column("loser_value", sa.Text, nullable=True),
        sa.Column("canonical_source", sa.String(32), nullable=False),
        sa.Column("loser_source", sa.String(32), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column(
            "resolved_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "resolved_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_field_conflict_log_field_action",
        "field_conflict_log",
        ["field_name", "action"],
    )
    op.create_index(
        "ix_field_conflict_log_sources",
        "field_conflict_log",
        ["canonical_source", "loser_source"],
    )


def downgrade() -> None:
    op.drop_index("ix_field_conflict_log_sources", table_name="field_conflict_log")
    op.drop_index("ix_field_conflict_log_field_action", table_name="field_conflict_log")
    op.drop_table("field_conflict_log")

    op.drop_index("ix_listing_snapshots_listing_captured", table_name="listing_snapshots")
    op.drop_table("listing_snapshots")

    op.drop_index("ix_api_call_log_month_source", table_name="api_call_log")
    op.drop_table("api_call_log")

    op.drop_column("scraped_listings", "polygon_tags")
