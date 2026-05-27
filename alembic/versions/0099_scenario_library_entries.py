"""Scenario Library entries for reusable deal snapshots.

Revision ID: 0099
Revises: 0098
Create Date: 2026-05-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenario_library_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_scenario_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("seeded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seeded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_scenario_id"], ["scenarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scenario_library_entries_org_id", "scenario_library_entries", ["org_id"], unique=False)
    op.create_index("ix_scenario_library_entries_source_deal_id", "scenario_library_entries", ["source_deal_id"], unique=False)
    op.create_index("ix_scenario_library_entries_source_scenario_id", "scenario_library_entries", ["source_scenario_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scenario_library_entries_source_scenario_id", table_name="scenario_library_entries")
    op.drop_index("ix_scenario_library_entries_source_deal_id", table_name="scenario_library_entries")
    op.drop_index("ix_scenario_library_entries_org_id", table_name="scenario_library_entries")
    op.drop_table("scenario_library_entries")
