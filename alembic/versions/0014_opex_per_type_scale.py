"""Add per_value, per_type, scale_with_lease_up, lease_up_floor_pct to operating_expense_lines.

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operating_expense_lines", sa.Column("per_value", sa.Numeric(18, 6), nullable=True))
    op.add_column("operating_expense_lines", sa.Column("per_type", sa.String(40), nullable=True))
    op.add_column("operating_expense_lines", sa.Column("scale_with_lease_up", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("operating_expense_lines", sa.Column("lease_up_floor_pct", sa.Numeric(18, 6), nullable=True))


def downgrade() -> None:
    op.drop_column("operating_expense_lines", "lease_up_floor_pct")
    op.drop_column("operating_expense_lines", "scale_with_lease_up")
    op.drop_column("operating_expense_lines", "per_type")
    op.drop_column("operating_expense_lines", "per_value")
