"""Add draw_sources table and reserve columns to scenarios.

Revision ID: 0034
Revises: 0033
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Reserve floor columns on scenarios
    op.add_column("scenarios", sa.Column(
        "min_reserve_construction", sa.Numeric(18, 6), nullable=True
    ))
    op.add_column("scenarios", sa.Column(
        "min_reserve_operational", sa.Numeric(18, 6), nullable=True
    ))

    # draw_sources — one row per source per scenario
    op.create_table(
        "draw_sources",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("scenario_id", UUID(as_uuid=True),
                  sa.ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sort_order", sa.Integer, nullable=False, default=0),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(30), nullable=False),   # "equity" | "debt"
        sa.Column("draw_every_n_months", sa.Integer, nullable=False, default=1),
        sa.Column("annual_interest_rate", sa.Numeric(18, 6), nullable=False, default=0),
        sa.Column("active_from_milestone", sa.String(60), nullable=False),
        sa.Column("active_to_milestone", sa.String(60), nullable=False),
        sa.Column("total_commitment", sa.Numeric(18, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_draw_sources_scenario_id", "draw_sources", ["scenario_id"])


def downgrade() -> None:
    op.drop_index("ix_draw_sources_scenario_id", table_name="draw_sources")
    op.drop_table("draw_sources")
    op.drop_column("scenarios", "min_reserve_operational")
    op.drop_column("scenarios", "min_reserve_construction")
