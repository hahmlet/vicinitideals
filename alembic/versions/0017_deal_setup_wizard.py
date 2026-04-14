"""Add deal setup wizard fields to operational_inputs

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("operational_inputs", sa.Column("deal_setup_complete", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("operational_inputs", sa.Column("debt_structure", sa.String(40), nullable=True))
    op.add_column("operational_inputs", sa.Column("debt_sizing_mode", sa.String(20), nullable=True))
    op.add_column("operational_inputs", sa.Column("dscr_minimum", sa.Numeric(18, 6), nullable=False, server_default="1.15"))
    op.add_column("operational_inputs", sa.Column("construction_floor_pct", sa.Numeric(18, 6), nullable=True))
    op.add_column("operational_inputs", sa.Column("operation_reserve_months", sa.Integer(), nullable=False, server_default="6"))
    op.add_column("operational_inputs", sa.Column("debt_terms", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("operational_inputs", "debt_terms")
    op.drop_column("operational_inputs", "operation_reserve_months")
    op.drop_column("operational_inputs", "construction_floor_pct")
    op.drop_column("operational_inputs", "dscr_minimum")
    op.drop_column("operational_inputs", "debt_sizing_mode")
    op.drop_column("operational_inputs", "debt_structure")
    op.drop_column("operational_inputs", "deal_setup_complete")
