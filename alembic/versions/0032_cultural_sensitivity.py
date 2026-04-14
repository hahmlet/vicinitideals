"""Add cultural_sensitivity to parcels table.

Revision ID: 0032
Revises: 0031
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parcels", sa.Column("cultural_sensitivity", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("parcels", "cultural_sensitivity")
