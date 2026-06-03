"""Expand capital_modules.vehicle_type from VARCHAR(20) to VARCHAR(50).

`deferred_developer_fee` is 22 characters and was being rejected by the
20-char constraint.

Revision ID: 0102
Revises: 0101
"""
from alembic import op
import sqlalchemy as sa

revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "capital_modules",
        "vehicle_type",
        type_=sa.String(50),
        existing_type=sa.String(20),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "capital_modules",
        "vehicle_type",
        type_=sa.String(20),
        existing_type=sa.String(50),
        existing_nullable=True,
    )
