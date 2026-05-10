"""add affordable_housing_project to operational_inputs

Revision ID: 0071
Revises: 0070
Create Date: 2026-05-06
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operational_inputs",
        sa.Column(
            "affordable_housing_project",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("operational_inputs", "affordable_housing_project")
