"""Add is_admin column to users; backfill site admin.

Revision ID: 0075
Revises: 0074
Create Date: 2026-05-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0075"
down_revision = "0074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.execute("UPDATE users SET is_admin = TRUE WHERE lower(name) = 'stephen ketch'")


def downgrade() -> None:
    op.drop_column("users", "is_admin")
