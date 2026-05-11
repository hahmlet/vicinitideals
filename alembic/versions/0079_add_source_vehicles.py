"""Add org_source_vehicles, user_source_vehicles tables and capital_modules.source_vehicle_id.

Revision ID: 0079
Revises: 0078
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0079"
down_revision = "0078"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_source_vehicles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("funder_type", sa.String(60), nullable=False),
        sa.Column("source_config", JSONB, nullable=True),
        sa.Column("carry_config", JSONB, nullable=True),
        sa.Column("exit_config", JSONB, nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "name", name="uq_org_source_vehicle_name"),
    )

    op.create_table(
        "user_source_vehicles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("funder_type", sa.String(60), nullable=False),
        sa.Column("source_config", JSONB, nullable=True),
        sa.Column("carry_config", JSONB, nullable=True),
        sa.Column("exit_config", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "name", name="uq_user_source_vehicle_name"),
    )

    # No DB-level FK constraint: source_vehicle_id can point to either table.
    # SET NULL on delete is handled in application-layer delete handlers.
    op.add_column(
        "capital_modules",
        sa.Column("source_vehicle_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_capital_modules_source_vehicle_id",
        "capital_modules",
        ["source_vehicle_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_capital_modules_source_vehicle_id", table_name="capital_modules")
    op.drop_column("capital_modules", "source_vehicle_id")
    op.drop_table("user_source_vehicles")
    op.drop_table("org_source_vehicles")
