"""Add health_thresholds to scenarios.

Stores per-scenario Deal Health RAG thresholds (occupancy, OER, DSCR, NCF
margin) so the investor export uses deal-specific benchmarks instead of
hardcoded values.  NULL on existing rows; exporter falls back to deal-type
defaults at export time.

Revision ID: 0064
Revises: 0063
Create Date: 2026-05-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='scenarios' AND column_name='health_thresholds'"
        )
    ).scalar()
    if not exists:
        op.add_column(
            "scenarios",
            sa.Column("health_thresholds", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("scenarios", "health_thresholds")
