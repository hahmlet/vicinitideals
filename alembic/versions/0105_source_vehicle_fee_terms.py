"""Move Dev Fee defaults from per-Type table onto Source Vehicle presets.

Replaces the ``capital_vehicle_fee_defaults`` org-scoped table (per
``vehicle_type + equity_role``) with a ``fee_terms`` JSONB column on
``source_vehicles`` (per preset). The per-deal ``capital_modules.fee_terms``
override path is unchanged; only the inheritance source changes from
"Type defaults" to "the preset that prefilled this vehicle".

Data preservation: the prior table never had production data (UI route was
500ing during the brief window it existed), so we drop without copying.

Revision ID: 0105
Revises: 0104
Create Date: 2026-06-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "0105"
down_revision = "0104"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add fee_terms JSONB to source_vehicles
    op.add_column(
        "source_vehicles",
        sa.Column(
            "fee_terms",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # Drop the per-Type defaults table (and its FK to organizations).
    op.drop_table("capital_vehicle_fee_defaults")


def downgrade() -> None:
    # Recreate the dropped table (empty).
    op.create_table(
        "capital_vehicle_fee_defaults",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("vehicle_type", sa.String(32), nullable=False),
        sa.Column("equity_role", sa.String(16), nullable=True),
        sa.Column(
            "fee_terms",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
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
        sa.UniqueConstraint("org_id", "vehicle_type", "equity_role"),
    )

    op.drop_column("source_vehicles", "fee_terms")
