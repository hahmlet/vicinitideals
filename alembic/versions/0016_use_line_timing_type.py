"""Add timing_type to use_lines

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "use_lines",
        sa.Column("timing_type", sa.String(20), nullable=False, server_default="first_day"),
    )


def downgrade() -> None:
    op.drop_column("use_lines", "timing_type")
