"""Add milestone_key_to to use_lines for multi-phase spread.

Revision ID: 0037
Revises: 0036
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("use_lines", sa.Column(
        "milestone_key_to", sa.String(60), nullable=True
    ))


def downgrade() -> None:
    op.drop_column("use_lines", "milestone_key_to")
