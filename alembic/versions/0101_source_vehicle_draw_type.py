"""Add draw_type column to source_vehicles.

Revision ID: 0101
Revises: 0100
Create Date: 2026-05-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "source_vehicles",
        sa.Column("draw_type", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("source_vehicles", "draw_type")
