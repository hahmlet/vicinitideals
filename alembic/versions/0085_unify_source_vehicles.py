"""Unify org_source_vehicles + user_source_vehicles into single source_vehicles table.

Replaces the two-table polymorphic pattern with a single table carrying a ``scope``
column (``org`` | ``user``) and ``owner_id`` (UUID pointing to org or user).  Adds
the full Phase A field set: vehicle_type, equity_role, draw_cadence, interest carry
fields, floating-rate fields, LIHTC delivery_schedule, closing costs, and
eligible_use_tags.

Adds ``vehicle_type`` and ``equity_role`` snapshot columns to ``capital_modules``.
Upgrades ``capital_modules.source_vehicle_id`` from an unenforceable free UUID to a
proper FK referencing ``source_vehicles.id`` (nullable, ON DELETE SET NULL).

Existing rows in ``capital_modules`` that carried stale org/user vehicle UUIDs have
their ``source_vehicle_id`` cleared (both source tables are dropped so the UUIDs are
no longer valid).  No DML to migrate funder_type → vehicle_type for existing modules;
engine falls back to funder_type for legacy rows (see Phase G).

Revision ID: 0085
Revises: 0084
Create Date: 2026-05-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Create unified source_vehicles table ──────────────────────────────
    op.create_table(
        "source_vehicles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # Ownership
        sa.Column("scope", sa.String(10), nullable=False),       # "org" | "user"
        sa.Column("owner_id", UUID(as_uuid=True), nullable=False),
        # Identity
        sa.Column("label", sa.String(200), nullable=False),
        # 4-type classification
        sa.Column("vehicle_type", sa.String(20), nullable=False),
        sa.Column("equity_role", sa.String(10), nullable=True),
        # Routing
        sa.Column("default_waterfall_position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("draw_cadence", sa.String(30), nullable=False, server_default="monthly"),
        # Interest carry (debt / forgivable_loan)
        sa.Column("interest_rate_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("carry_type", sa.String(30), nullable=True),
        sa.Column("interest_payment_timing", sa.String(30), nullable=True),
        sa.Column("day_count_convention", sa.String(20), nullable=False, server_default="actual_360"),
        sa.Column("io_period_months", sa.Integer, nullable=True),
        sa.Column("amort_term_years", sa.Integer, nullable=True),
        # Floating rate
        sa.Column("rate_series_ref", sa.String(60), nullable=True),
        sa.Column("rate_spread_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("rate_reset_frequency", sa.String(20), nullable=True),
        # Equity
        sa.Column("pref_rate_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("hurdle_tiers", JSONB, nullable=True),
        sa.Column("delivery_schedule", JSONB, nullable=True),
        # Closing costs
        sa.Column("closing_costs_flat", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("closing_costs_pct", sa.Numeric(18, 6), nullable=False, server_default="0"),
        # Forgivable loan
        sa.Column("forgiveness_trigger", sa.String(60), nullable=True),
        # Prepayment
        sa.Column("prepay_penalty_pct", sa.Numeric(18, 6), nullable=False, server_default="0"),
        # Source-Use eligibility
        sa.Column("eligible_use_tags", ARRAY(sa.String), nullable=False, server_default="{}"),
        # Legacy phase window
        sa.Column("active_phase_start", sa.String(60), nullable=True),
        sa.Column("active_phase_end", sa.String(60), nullable=True),
        # JSONB config templates
        sa.Column("source_config", JSONB, nullable=True),
        sa.Column("carry_config", JSONB, nullable=True),
        sa.Column("exit_config", JSONB, nullable=True),
        # Audit
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.UniqueConstraint("scope", "owner_id", "label", name="uq_source_vehicle_scope_owner_label"),
    )
    op.create_index("ix_source_vehicles_scope_owner_id", "source_vehicles", ["scope", "owner_id"])

    # ── 2. Nullify stale source_vehicle_id on capital_modules before dropping tables ──
    op.execute("UPDATE capital_modules SET source_vehicle_id = NULL")

    # ── 3. Drop old FK index and add proper FK constraint ────────────────────
    op.drop_index("ix_capital_modules_source_vehicle_id", table_name="capital_modules")
    op.create_foreign_key(
        "fk_capital_modules_source_vehicle_id",
        "capital_modules",
        "source_vehicles",
        ["source_vehicle_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_capital_modules_source_vehicle_id",
        "capital_modules",
        ["source_vehicle_id"],
    )

    # ── 4. Add vehicle_type + equity_role snapshot columns to capital_modules ─
    op.add_column("capital_modules", sa.Column("vehicle_type", sa.String(20), nullable=True))
    op.add_column("capital_modules", sa.Column("equity_role", sa.String(10), nullable=True))

    # ── 5. Drop old vehicle tables (destructive — no rows preserved) ─────────
    op.drop_table("org_source_vehicles")
    op.drop_table("user_source_vehicles")


def downgrade() -> None:
    # Recreate old tables (empty — no data restored)
    op.create_table(
        "org_source_vehicles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("funder_type", sa.String(60), nullable=False),
        sa.Column("source_config", JSONB, nullable=True),
        sa.Column("carry_config", JSONB, nullable=True),
        sa.Column("exit_config", JSONB, nullable=True),
        sa.Column("active_phase_start", sa.String(60), nullable=True),
        sa.Column("active_phase_end", sa.String(60), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("org_id", "name", name="uq_org_source_vehicle_name"),
    )
    op.create_table(
        "user_source_vehicles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("funder_type", sa.String(60), nullable=False),
        sa.Column("source_config", JSONB, nullable=True),
        sa.Column("carry_config", JSONB, nullable=True),
        sa.Column("exit_config", JSONB, nullable=True),
        sa.Column("active_phase_start", sa.String(60), nullable=True),
        sa.Column("active_phase_end", sa.String(60), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("user_id", "name", name="uq_user_source_vehicle_name"),
    )

    # Remove new columns
    op.drop_column("capital_modules", "equity_role")
    op.drop_column("capital_modules", "vehicle_type")

    # Restore old index (no FK)
    op.drop_constraint("fk_capital_modules_source_vehicle_id", "capital_modules", type_="foreignkey")
    op.drop_index("ix_capital_modules_source_vehicle_id", table_name="capital_modules")
    op.create_index("ix_capital_modules_source_vehicle_id", "capital_modules", ["source_vehicle_id"])

    # Drop new table
    op.drop_index("ix_source_vehicles_scope_owner_id", table_name="source_vehicles")
    op.drop_table("source_vehicles")
