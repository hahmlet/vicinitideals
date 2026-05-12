"""Add debug_log column to inbound_emails for AI processing diagnostics.

Revision ID: 0083
Revises: 0082
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inbound_emails",
        sa.Column("debug_log", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("inbound_emails", "debug_log")
