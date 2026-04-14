"""Add unit_mix table for deal-local unit type breakdown

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "unit_mix",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("unit_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("avg_sqft", sa.Numeric(18, 2), nullable=True),
        sa.Column("avg_monthly_rent", sa.Numeric(18, 2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_unit_mix_project_id", "unit_mix", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_unit_mix_project_id", table_name="unit_mix")
    op.drop_table("unit_mix")
