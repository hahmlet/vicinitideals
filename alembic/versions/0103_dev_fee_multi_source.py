"""Multi-source Developer Fee modeling.

Adds four-layer config for Developer Fee:

- ``capital_modules.fee_terms`` JSONB + ``fee_terms_inherited_from_type`` flag.
- New ``capital_vehicle_fee_defaults`` table (org-scoped registry of per-
  ``(vehicle_type, equity_role)`` defaults).
- New ``use_line_source_fee_basis`` join table for per-``(UseLine x Source
  Vehicle)`` inclusion decisions on custom Uses.
- ``use_lines.dev_fee_release_schedule`` JSONB (milestone-weighted release).
- ``use_lines.dev_fee_binding_context`` JSONB (engine-written display data).
- ``use_lines.is_auto_acquisition_fee`` Boolean — auto Acquisition Fee row
  flag analogous to ``is_auto_dev_fee``.
- ``use_lines.dev_fee_acquisition_treatment`` VARCHAR(16) — variant on Dev
  Fee row (``separate_fee``/``split_rate``/``excluded``).
- ``use_lines.dev_fee_acquisition_pct`` Numeric — split-rate reduced %.
- ``use_lines.acquisition_fee_pct`` Numeric — Acquisition Fee target %.

Revision ID: 0103
Revises: 0102
Create Date: 2026-06-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # capital_modules: fee_terms JSONB + inheritance flag
    # ------------------------------------------------------------------
    op.add_column(
        "capital_modules",
        sa.Column(
            "fee_terms",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "capital_modules",
        sa.Column(
            "fee_terms_inherited_from_type",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # ------------------------------------------------------------------
    # use_lines: new columns for release schedule, binding context,
    # acquisition variant, and acquisition-fee target.
    # ------------------------------------------------------------------
    op.add_column(
        "use_lines",
        sa.Column(
            "dev_fee_release_schedule",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "use_lines",
        sa.Column(
            "dev_fee_binding_context",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "use_lines",
        sa.Column(
            "is_auto_acquisition_fee",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "use_lines",
        sa.Column(
            "dev_fee_acquisition_treatment",
            sa.String(16),
            nullable=True,
        ),
    )
    op.add_column(
        "use_lines",
        sa.Column(
            "dev_fee_acquisition_pct",
            sa.Numeric(8, 4),
            nullable=True,
        ),
    )
    op.add_column(
        "use_lines",
        sa.Column(
            "acquisition_fee_pct",
            sa.Numeric(8, 4),
            nullable=True,
        ),
    )

    # ------------------------------------------------------------------
    # capital_vehicle_fee_defaults: per-org registry keyed on
    # (vehicle_type, equity_role). Ships empty; org admin populates.
    # ------------------------------------------------------------------
    op.create_table(
        "capital_vehicle_fee_defaults",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("vehicle_type", sa.String(20), nullable=False),
        sa.Column("equity_role", sa.String(10), nullable=True),
        sa.Column(
            "fee_terms",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "org_id",
            "vehicle_type",
            "equity_role",
            name="uq_vehicle_fee_defaults_org_type_role",
        ),
    )
    op.create_index(
        "ix_capital_vehicle_fee_defaults_org_id",
        "capital_vehicle_fee_defaults",
        ["org_id"],
    )

    # ------------------------------------------------------------------
    # use_line_source_fee_basis: per-(UseLine x CapitalModule) inclusion
    # decision for custom Uses. Composite PK.
    # ------------------------------------------------------------------
    op.create_table(
        "use_line_source_fee_basis",
        sa.Column(
            "use_line_id",
            UUID(as_uuid=True),
            sa.ForeignKey("use_lines.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "capital_module_id",
            UUID(as_uuid=True),
            sa.ForeignKey("capital_modules.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "included_in_basis",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "set_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_use_line_source_fee_basis_module",
        "use_line_source_fee_basis",
        ["capital_module_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_use_line_source_fee_basis_module",
        table_name="use_line_source_fee_basis",
    )
    op.drop_table("use_line_source_fee_basis")
    op.drop_index(
        "ix_capital_vehicle_fee_defaults_org_id",
        table_name="capital_vehicle_fee_defaults",
    )
    op.drop_table("capital_vehicle_fee_defaults")
    op.drop_column("use_lines", "acquisition_fee_pct")
    op.drop_column("use_lines", "dev_fee_acquisition_pct")
    op.drop_column("use_lines", "dev_fee_acquisition_treatment")
    op.drop_column("use_lines", "is_auto_acquisition_fee")
    op.drop_column("use_lines", "dev_fee_binding_context")
    op.drop_column("use_lines", "dev_fee_release_schedule")
    op.drop_column("capital_modules", "fee_terms_inherited_from_type")
    op.drop_column("capital_modules", "fee_terms")
