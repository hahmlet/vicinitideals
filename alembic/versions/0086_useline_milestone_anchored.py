"""Add milestone FK columns to use_lines; drop legacy milestone_key string columns.

Replaces the string-based ``milestone_key`` / ``milestone_key_to`` columns with
proper UUID FK references to the ``milestones`` table.  Also makes ``phase``
nullable so future UseLines can be created with only milestone FKs and no
legacy phase string.

The existing ``phase`` column is kept (nullable) for backward compatibility:
the cashflow engine falls back to phase-string timing when ``active_from_milestone_id``
is NULL.  The ``milestone_key`` and ``milestone_key_to`` columns are dropped —
they were never reliably read by the engine.

Revision ID: 0086
Revises: 0085
Create Date: 2026-05-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make phase nullable (was NOT NULL — existing rows keep their value)
    op.alter_column("use_lines", "phase", nullable=True)

    # Drop dead string columns
    op.drop_column("use_lines", "milestone_key")
    op.drop_column("use_lines", "milestone_key_to")

    # Add milestone FK columns
    op.add_column(
        "use_lines",
        sa.Column(
            "active_from_milestone_id",
            UUID(as_uuid=True),
            sa.ForeignKey("milestones.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "use_lines",
        sa.Column(
            "spread_to_milestone_id",
            UUID(as_uuid=True),
            sa.ForeignKey("milestones.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_use_lines_active_from_milestone_id",
        "use_lines",
        ["active_from_milestone_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_use_lines_active_from_milestone_id", table_name="use_lines")
    op.drop_column("use_lines", "spread_to_milestone_id")
    op.drop_column("use_lines", "active_from_milestone_id")

    op.add_column(
        "use_lines",
        sa.Column("milestone_key", sa.String(60), nullable=True),
    )
    op.add_column(
        "use_lines",
        sa.Column("milestone_key_to", sa.String(60), nullable=True),
    )

    op.alter_column("use_lines", "phase", nullable=False)
