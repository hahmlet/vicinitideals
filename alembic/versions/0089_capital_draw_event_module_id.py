"""Add module_id FK to capital_draw_events for per-module draw attribution.

Revision ID: 0089
Revises: 0088
Create Date: 2026-05-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PGUUID

revision = "0089"
down_revision = "0088"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "capital_draw_events",
        sa.Column(
            "module_id",
            PGUUID(as_uuid=True),
            sa.ForeignKey("capital_modules.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_capital_draw_events_module_id",
        "capital_draw_events",
        ["module_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_capital_draw_events_module_id", table_name="capital_draw_events")
    op.drop_column("capital_draw_events", "module_id")
