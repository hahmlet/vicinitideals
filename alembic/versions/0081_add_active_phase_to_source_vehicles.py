"""Add active_phase_start/end to org and user source vehicle tables.

Revision ID: 0081
Revises: 0080
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("org_source_vehicles", sa.Column("active_phase_start", sa.String(60), nullable=True))
    op.add_column("org_source_vehicles", sa.Column("active_phase_end", sa.String(60), nullable=True))
    op.add_column("user_source_vehicles", sa.Column("active_phase_start", sa.String(60), nullable=True))
    op.add_column("user_source_vehicles", sa.Column("active_phase_end", sa.String(60), nullable=True))


def downgrade() -> None:
    op.drop_column("user_source_vehicles", "active_phase_end")
    op.drop_column("user_source_vehicles", "active_phase_start")
    op.drop_column("org_source_vehicles", "active_phase_end")
    op.drop_column("org_source_vehicles", "active_phase_start")
