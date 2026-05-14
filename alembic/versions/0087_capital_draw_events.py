"""Add capital_draw_events table for per-period capital draw audit trail.

Replaces the month-0 total_sources pre-seed in the cashflow engine.
Each compute_cash_flows run purges prior rows for the scenario and
re-inserts one row per draw event per period.

Revision ID: 0087
Revises: 0086
Create Date: 2026-05-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0087"
down_revision = "0086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "capital_draw_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "scenario_id",
            UUID(as_uuid=True),
            sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("period_type", sa.String(60), nullable=True),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("allocation_reason", sa.String(40), nullable=False, server_default="period_funding"),
        sa.Column("use_line_label", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_capital_draw_events_scenario_period",
        "capital_draw_events",
        ["scenario_id", "period"],
    )
    op.create_index(
        "ix_capital_draw_events_project",
        "capital_draw_events",
        ["scenario_id", "project_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_capital_draw_events_project", table_name="capital_draw_events")
    op.drop_index("ix_capital_draw_events_scenario_period", table_name="capital_draw_events")
    op.drop_table("capital_draw_events")
