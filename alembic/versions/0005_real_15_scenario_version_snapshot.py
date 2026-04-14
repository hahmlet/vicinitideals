"""REAL-15 scenario model version snapshot

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-03 18:15:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scenarios",
        sa.Column("model_version_snapshot", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scenarios", "model_version_snapshot")
