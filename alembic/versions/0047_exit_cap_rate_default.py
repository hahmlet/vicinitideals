"""Set sensible defaults on OperationalInputs and backfill legacy zero rows.

Two columns previously defaulted to 0, which silently disabled downstream
calculations until a user set them:

  - exit_cap_rate_pct         → new default 5 (%)
  - expense_growth_rate_pct_annual → new default 3 (%)

Backfill: any existing row at 0 was almost certainly left at the old
default (never edited), so promote those to the new defaults as well.
Individual scenarios can still override either value.

Revision ID: 0047
Revises: 0046
Create Date: 2026-04-19
"""

from alembic import op
import sqlalchemy as sa

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "operational_inputs",
        "exit_cap_rate_pct",
        server_default=sa.text("5"),
        existing_type=sa.Numeric(18, 6),
        existing_nullable=False,
    )
    op.alter_column(
        "operational_inputs",
        "expense_growth_rate_pct_annual",
        server_default=sa.text("3"),
        existing_type=sa.Numeric(18, 6),
        existing_nullable=False,
    )
    op.execute(
        "UPDATE operational_inputs SET exit_cap_rate_pct = 5 "
        "WHERE exit_cap_rate_pct = 0"
    )
    op.execute(
        "UPDATE operational_inputs SET expense_growth_rate_pct_annual = 3 "
        "WHERE expense_growth_rate_pct_annual = 0"
    )


def downgrade() -> None:
    op.alter_column(
        "operational_inputs",
        "exit_cap_rate_pct",
        server_default=sa.text("0"),
        existing_type=sa.Numeric(18, 6),
        existing_nullable=False,
    )
    op.alter_column(
        "operational_inputs",
        "expense_growth_rate_pct_annual",
        server_default=sa.text("0"),
        existing_type=sa.Numeric(18, 6),
        existing_nullable=False,
    )
