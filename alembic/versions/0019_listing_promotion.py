"""Add listing promotion fields to Opportunity and auto_promote to SavedSearchCriteria

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SavedSearchCriteria: flag controlling auto-promotion at ingest time
    op.add_column(
        "saved_search_criteria",
        sa.Column("auto_promote", sa.Boolean(), nullable=False, server_default="true"),
    )

    # Opportunity: promotion audit fields
    op.add_column(
        "opportunities",
        sa.Column("promotion_source", sa.String(20), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column(
            "promotion_ruleset_id",
            UUID(as_uuid=True),
            sa.ForeignKey("saved_search_criteria.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_opportunities_promotion_ruleset_id",
        "opportunities",
        ["promotion_ruleset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_opportunities_promotion_ruleset_id", table_name="opportunities")
    op.drop_column("opportunities", "promotion_ruleset_id")
    op.drop_column("opportunities", "promotion_source")
    op.drop_column("saved_search_criteria", "auto_promote")
