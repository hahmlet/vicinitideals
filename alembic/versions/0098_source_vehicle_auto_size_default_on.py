"""Normalize Source Vehicle auto_size to default ON.

Revision ID: 0098
Revises: 0097
Create Date: 2026-05-26
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Normalize all persisted source vehicle presets to include auto_size=true.
    op.execute(
        """
        UPDATE source_vehicles
        SET source_config = COALESCE(source_config, '{}'::jsonb) || '{"auto_size": true}'::jsonb
        """
    )

    # Normalize all capital modules to include auto_size=true at the source JSON level.
    op.execute(
        """
        UPDATE capital_modules
        SET source = COALESCE(source, '{}'::jsonb) || '{"auto_size": true}'::jsonb
        """
    )

    # Normalize all per-project junction rows and make future inserts default ON.
    op.execute(
        """
        UPDATE capital_module_projects
        SET auto_size = true
        WHERE auto_size IS DISTINCT FROM true
        """
    )
    op.alter_column(
        "capital_module_projects",
        "auto_size",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Data normalization is intentionally retained; only the DB default is reverted.
    op.alter_column(
        "capital_module_projects",
        "auto_size",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        existing_nullable=False,
    )
