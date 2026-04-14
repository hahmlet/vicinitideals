"""Add net_rentable_sqft to buildings

Revision ID: 0026
Revises: 0025
Create Date: 2026-04-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "buildings",
        sa.Column("net_rentable_sqft", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("buildings", "net_rentable_sqft")
