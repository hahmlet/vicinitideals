"""Add income_mode to scenarios; noi_stabilized_input + noi_escalation_rate_pct to operational_inputs.

Revision ID: 0039
Revises: 0038
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # scenarios.income_mode — default 'revenue_opex' for all existing rows
    op.add_column(
        "scenarios",
        sa.Column(
            "income_mode",
            sa.String(20),
            nullable=False,
            server_default="revenue_opex",
        ),
    )

    # operational_inputs.noi_stabilized_input — nullable (not set until user enters it)
    op.add_column(
        "operational_inputs",
        sa.Column("noi_stabilized_input", sa.Numeric(18, 6), nullable=True),
    )

    # operational_inputs.noi_escalation_rate_pct — default 3%
    op.add_column(
        "operational_inputs",
        sa.Column(
            "noi_escalation_rate_pct",
            sa.Numeric(18, 6),
            nullable=False,
            server_default="3",
        ),
    )


def downgrade() -> None:
    op.drop_column("operational_inputs", "noi_escalation_rate_pct")
    op.drop_column("operational_inputs", "noi_stabilized_input")
    op.drop_column("scenarios", "income_mode")
