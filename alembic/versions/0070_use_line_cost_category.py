"""Add cost_category to use_lines.

Classifies each use line as acquisition / soft / hard so the S&U panel
can render collapsible sub-tables and the Excel export can produce a
per-category breakdown.  Existing rows are backfilled via label-pattern
UPDATEs derived from auditing production data; engine-generated rows
(source_capital_module_id IS NOT NULL) will be overwritten on the next
cashflow run anyway.

Revision ID: 0070
Revises: 0069
Create Date: 2026-05-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    is_offline = op.get_context().as_sql
    if is_offline:
        op.execute(
            "ALTER TABLE use_lines "
            "ADD COLUMN IF NOT EXISTS cost_category VARCHAR(60) DEFAULT 'soft'"
        )
    else:
        conn = op.get_bind()
        exists = conn.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='use_lines' AND column_name='cost_category'"
            )
        ).scalar()
        if not exists:
            op.add_column(
                "use_lines",
                sa.Column(
                    "cost_category",
                    sa.String(60),
                    nullable=True,
                    server_default="soft",
                ),
            )

    # Strategy: set acquisition and hard by label; everything else stays
    # as the server_default 'soft'. Both branches issue the same UPDATEs.

    # ── Acquisition ──────────────────────────────────────────────────────────
    op.execute(
        "UPDATE use_lines SET cost_category = 'acquisition' WHERE "
        "label LIKE '% - Acquisition'"
        " OR label = 'Acquisition'"
        " OR label = 'Purchase Price'"
        " OR label LIKE 'Gap Adjustment%'"
        " OR label LIKE 'Acquisition Loan (auto)%'"
    )

    # ── Hard ─────────────────────────────────────────────────────────────────
    op.execute(
        "UPDATE use_lines SET cost_category = 'hard' WHERE "
        "label = 'Construction'"
        " OR label = 'Hard Construction'"
    )

    # ── Soft (explicit, in case server_default didn't backfill nulls) ─────────
    op.execute(
        "UPDATE use_lines SET cost_category = 'soft' "
        "WHERE cost_category IS NULL"
    )


def downgrade() -> None:
    op.drop_column("use_lines", "cost_category")
