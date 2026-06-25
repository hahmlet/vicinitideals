"""Widen source_vehicles.vehicle_type from VARCHAR(20) to VARCHAR(50).

Revision ID: 0122
Revises: 0121
"""

import sqlalchemy as sa
from alembic import op

revision = "0122"
down_revision = "0121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "source_vehicles",
        "vehicle_type",
        existing_type=sa.String(20),
        type_=sa.String(50),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "source_vehicles",
        "vehicle_type",
        existing_type=sa.String(50),
        type_=sa.String(20),
        existing_nullable=False,
    )
