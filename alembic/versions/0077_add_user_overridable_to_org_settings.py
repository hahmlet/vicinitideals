"""Add user_overridable column to org_settings.

Revision ID: 0077
Revises: 0076
Create Date: 2026-05-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0077"
down_revision = "0076"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "org_settings",
        sa.Column(
            "user_overridable",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )


def downgrade() -> None:
    op.drop_column("org_settings", "user_overridable")
