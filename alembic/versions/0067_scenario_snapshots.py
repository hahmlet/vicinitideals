"""Add scenario_snapshots table and wire Scenario.version to compute cycle.

Each row captures the full serialized input state + key output metrics
at the moment a Compute run completes.  The version column on scenarios
already exists (migration 0001) but was always 0; this migration adds no
DDL for it — we simply begin incrementing it from application code.

Revision ID: 0067
Revises: 0066
Create Date: 2026-05-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name='scenario_snapshots'"
        )
    ).scalar()
    if not exists:
        op.create_table(
            "scenario_snapshots",
            sa.Column("id", UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "scenario_id",
                UUID(as_uuid=True),
                sa.ForeignKey("scenarios.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("version", sa.Integer, nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "triggered_by",
                sa.String(20),
                nullable=False,
                server_default="compute",
            ),
            sa.Column("label", sa.Text, nullable=True),
            sa.Column("inputs_json", JSONB, nullable=False),
            sa.Column("outputs_json", JSONB, nullable=False),
        )


def downgrade() -> None:
    op.drop_table("scenario_snapshots")
