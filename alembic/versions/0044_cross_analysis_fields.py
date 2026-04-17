"""Add CRE cross-analysis and LTL catchup fields.

Columns added in the second round of April 16 engine work that were
not in the original 0042 migration applied to production.

Revision ID: 0044
Revises: 0043
Create Date: 2026-04-16
"""

from alembic import op
import sqlalchemy as sa

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── IncomeStream (additions beyond 0042) ──────────────────────────────
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
    op.drop_column("income_streams", "catchup_target_rent")
    op.drop_column("income_streams", "renovation_capture_schedule")
