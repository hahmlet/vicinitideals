"""Add HelloData model parity, CRE cross-analysis, and LTL catchup fields.

New columns:
- income_streams: bad_debt_pct, concessions_pct, renovation_absorption_rate,
  renovation_capture_schedule, catchup_target_rent
- operational_inputs: asset_mgmt_fee_pct, lease_up_curve, lease_up_curve_steepness
- operational_outputs: debt_yield_pct, sensitivity_matrix
- unit_mix: market_rent_per_unit, in_place_rent_per_unit, unit_strategy,
  post_reno_rent_per_unit

CapitalSourceSchema gains refi_cap_rate_pct and prepay_penalty_pct as JSONB
fields (no migration needed — extra="allow" on the Pydantic schema).

Revision ID: 0042
Revises: 0041
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── IncomeStream ──────────────────────────────────────────────────────
    op.add_column(
        "income_streams",
        sa.Column("bad_debt_pct", sa.Numeric(18, 6), nullable=False, server_default="0"),
    )
    op.add_column(
        "income_streams",
        sa.Column("concessions_pct", sa.Numeric(18, 6), nullable=False, server_default="0"),
    )
    op.add_column(
        "income_streams",
        sa.Column("renovation_absorption_rate", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "income_streams",
        sa.Column("renovation_capture_schedule", sa.JSON(), nullable=True),
    )
    op.add_column(
        "income_streams",
        sa.Column("catchup_target_rent", sa.Numeric(18, 6), nullable=True),
    )

    # ── OperationalInputs ─────────────────────────────────────────────────
    op.add_column(
        "operational_inputs",
        sa.Column("asset_mgmt_fee_pct", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "operational_inputs",
        sa.Column("lease_up_curve", sa.String(20), nullable=True),
    )
    op.add_column(
        "operational_inputs",
        sa.Column("lease_up_curve_steepness", sa.Numeric(18, 6), nullable=True),
    )

    # ── OperationalOutputs ────────────────────────────────────────────────
    op.add_column(
        "operational_outputs",
        sa.Column("debt_yield_pct", sa.Numeric(18, 6), nullable=True),
    )
    op.add_column(
        "operational_outputs",
        sa.Column("sensitivity_matrix", sa.JSON(), nullable=True),
    )

    # ── UnitMix ───────────────────────────────────────────────────────────
    op.add_column(
        "unit_mix",
        sa.Column("market_rent_per_unit", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "unit_mix",
        sa.Column("in_place_rent_per_unit", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "unit_mix",
        sa.Column("unit_strategy", sa.String(40), nullable=True),
    )
    op.add_column(
        "unit_mix",
        sa.Column("post_reno_rent_per_unit", sa.Numeric(18, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("unit_mix", "post_reno_rent_per_unit")
    op.drop_column("unit_mix", "unit_strategy")
    op.drop_column("unit_mix", "in_place_rent_per_unit")
    op.drop_column("unit_mix", "market_rent_per_unit")
    op.drop_column("operational_outputs", "sensitivity_matrix")
    op.drop_column("operational_outputs", "debt_yield_pct")
    op.drop_column("operational_inputs", "lease_up_curve_steepness")
    op.drop_column("operational_inputs", "lease_up_curve")
    op.drop_column("operational_inputs", "asset_mgmt_fee_pct")
    op.drop_column("income_streams", "catchup_target_rent")
    op.drop_column("income_streams", "renovation_capture_schedule")
    op.drop_column("income_streams", "renovation_absorption_rate")
    op.drop_column("income_streams", "concessions_pct")
    op.drop_column("income_streams", "bad_debt_pct")
