"""Add noi_auto_seeded flag to operational_inputs.

When the builder page silently seeds noi_stabilized_input from the KNN comp
engine (cashflow.py-side market recommendation), set this flag so the UI can
surface a banner asking the user to confirm or override. Cleared when the
user submits the NOI form.

Revision ID: 0061
Revises: 0060
Create Date: 2026-04-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0061"
down_revision = "0060"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operational_inputs",
        sa.Column(
            "noi_auto_seeded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("operational_inputs", "noi_auto_seeded")
