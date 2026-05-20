"""Add is_auto_finance_cost flag to use_lines.

Marks engine-managed Total Finance Costs rows (one per CapitalModule).
Mirror of is_auto_dev_fee (migration 0092). User edit to any field on
such a row flips the flag to False — engine stops recomputing.  User
deletes the row → next compute creates a fresh auto-managed row.

Revision ID: 0093
Revises: 0092
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "use_lines",
        sa.Column(
            "is_auto_finance_cost",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("use_lines", "is_auto_finance_cost")
