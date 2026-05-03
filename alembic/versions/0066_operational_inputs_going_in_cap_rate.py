"""Add going_in_cap_rate_pct to operational_inputs.

Market cap rate at acquisition — used by the investor export to compute the
Going-In Market Value (Stabilized NOI / Going-In Cap).  NULL on existing rows;
the exporter already guards with `getattr(..., 0)` and shows "(no Going-In Cap
configured)" when the field is absent.

Revision ID: 0066
Revises: 0065
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='operational_inputs' AND column_name='going_in_cap_rate_pct'"
        )
    ).scalar()
    if not exists:
        op.add_column(
            "operational_inputs",
            sa.Column("going_in_cap_rate_pct", sa.Numeric(18, 6), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("operational_inputs", "going_in_cap_rate_pct")
