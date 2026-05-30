"""Add bank_account_proof JSON column to operational_outputs.

Stores the most recent bank-account proof result (operating-phase
solvency check) so the UI can read it at render time without re-running
the simulation.

Revision ID: 0102
Revises: 0101
Create Date: 2026-05-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0102"
down_revision = "0101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "operational_outputs",
        sa.Column("bank_account_proof", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("operational_outputs", "bank_account_proof")
