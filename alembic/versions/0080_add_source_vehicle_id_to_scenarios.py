"""Add source_vehicle_id to scenarios table.

Revision ID: 0080
Revises: 0079
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column("source_vehicle_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_scenarios_source_vehicle_id",
        "scenarios",
        ["source_vehicle_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_scenarios_source_vehicle_id", table_name="scenarios")
    op.drop_column("scenarios", "source_vehicle_id")
