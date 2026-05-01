"""Drop redundant debt fields from operational_inputs; backfill perm-debt
hold_term_years + dscr_min onto each CapitalModule.source.

Migration:
  1. Backfill perm-debt CapitalModule.source.hold_term_years from
     carry.amort_term_years (or 5 if missing).
  2. Backfill perm-debt CapitalModule.source.dscr_min from
     OperationalInputs.dscr_minimum (per-project lookup).
  3. Drop columns: hold_period_years, perm_rate_pct, perm_amort_years,
     dscr_minimum.

Retains debt_terms (used as wizard staging) and hold_phase_enabled /
hold_months (separate phase-plan toggles, unrelated to perm-debt hold).

Revision ID: 0060
Revises: 0059
Create Date: 2026-04-29
"""

import sqlalchemy as sa
from alembic import op

revision = "0060"
down_revision = "0059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── Step 1+2: backfill perm-debt modules ────────────────────────────────
    # source/carry columns are JSON (not JSONB) on legacy prod schemas, so
    # cast both sides to jsonb for the merge then back to json on assignment.
    # amort_term_years can live in carry (phased) OR source; check carry first.
    conn.execute(sa.text("""
        UPDATE capital_modules cm
        SET source = (
            COALESCE(cm.source::jsonb, '{}'::jsonb)
            || jsonb_build_object(
                'hold_term_years',
                COALESCE(
                    (cm.carry::jsonb->>'amort_term_years')::int,
                    (cm.source::jsonb->>'amort_term_years')::int,
                    5
                ),
                'dscr_min',
                COALESCE(
                    (
                        SELECT (oi.dscr_minimum)::float
                        FROM operational_inputs oi
                        JOIN projects p ON p.id = oi.project_id
                        WHERE p.scenario_id = cm.scenario_id
                          AND oi.dscr_minimum IS NOT NULL
                        ORDER BY p.created_at ASC
                        LIMIT 1
                    ),
                    1.20
                )
            )
        )::json
        WHERE cm.funder_type = 'permanent_debt'
    """))

    # ── Step 3: drop columns (tolerate columns that never existed on this DB)
    conn.execute(sa.text(
        "ALTER TABLE operational_inputs DROP COLUMN IF EXISTS hold_period_years"
    ))
    conn.execute(sa.text(
        "ALTER TABLE operational_inputs DROP COLUMN IF EXISTS perm_rate_pct"
    ))
    conn.execute(sa.text(
        "ALTER TABLE operational_inputs DROP COLUMN IF EXISTS perm_amort_years"
    ))
    conn.execute(sa.text(
        "ALTER TABLE operational_inputs DROP COLUMN IF EXISTS dscr_minimum"
    ))


def downgrade() -> None:
    op.add_column(
        "operational_inputs",
        sa.Column("hold_period_years", sa.Numeric(8, 6), nullable=True),
    )
    op.add_column(
        "operational_inputs",
        sa.Column("perm_rate_pct", sa.Numeric(8, 6), nullable=True),
    )
    op.add_column(
        "operational_inputs",
        sa.Column("perm_amort_years", sa.Integer(), nullable=True),
    )
    op.add_column(
        "operational_inputs",
        sa.Column("dscr_minimum", sa.Numeric(8, 6), nullable=True),
    )
    # Backfill from CapitalModule sources is NOT performed on downgrade —
    # the per-loan values cannot be cleanly mapped back to a deal-level scalar.
