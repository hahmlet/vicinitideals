"""REAL-71 itemized operating expense lines

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-03 05:20:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operating_expense_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("annual_amount", sa.Numeric(18, 6), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "escalation_rate_pct_annual",
            sa.Numeric(18, 6),
            nullable=False,
            server_default=sa.text("3"),
        ),
        sa.Column(
            "active_in_phases",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["deal_model_id"], ["deal_models.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("operating_expense_lines")
