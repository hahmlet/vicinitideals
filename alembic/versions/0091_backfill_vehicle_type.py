"""Backfill vehicle_type + equity_role on capital_modules from label patterns.

Migration 0090 dropped funder_type without pre-populating vehicle_type on
existing rows. This migration backfills from known label patterns and adds
a NOT NULL constraint so new rows cannot be created without a type.

Revision ID: 0091
Revises: 0090
Create Date: 2026-05-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None

# Label keyword → (vehicle_type, equity_role)
# Ordered most-specific first. Fallback = equity/gp (owner equity default).
_LABEL_MAP = [
    ("bond",           "debt",            None),
    ("construction",   "debt",            None),
    ("permanent",      "debt",            None),
    ("perm debt",      "debt",            None),
    ("bridge",         "debt",            None),
    ("mezzanine",      "debt",            None),
    ("mezz",           "debt",            None),
    ("pre-development","debt",            None),
    ("pre_development","debt",            None),
    ("acquisition loan","debt",           None),
    ("forgivable",     "forgivable_loan", None),
    ("grant",          "grant",           None),
    ("lp equity",      "equity",          "lp"),
    ("preferred equity","equity",         "lp"),
    ("lihtc",          "equity",          "lp"),
    ("htc",            "equity",          "lp"),
    ("gp equity",      "equity",          "gp"),
    ("owner equity",   "equity",          "gp"),
    ("common equity",  "equity",          "gp"),
]


def upgrade() -> None:
    conn = op.get_bind()

    # Backfill rows that still have NULL vehicle_type
    rows = conn.execute(
        sa.text("SELECT id, label FROM capital_modules WHERE vehicle_type IS NULL")
    ).fetchall()

    for row_id, label in rows:
        label_lc = (label or "").lower()
        vt, er = "equity", "gp"  # safe fallback
        for kw, vehicle_type, equity_role in _LABEL_MAP:
            if kw in label_lc:
                vt, er = vehicle_type, equity_role
                break
        conn.execute(
            sa.text(
                "UPDATE capital_modules SET vehicle_type = :vt, equity_role = :er "
                "WHERE id = :id"
            ),
            {"vt": vt, "er": er, "id": str(row_id)},
        )

    # Set NOT NULL on vehicle_type (all rows now populated)
    op.alter_column("capital_modules", "vehicle_type", nullable=False)


def downgrade() -> None:
    op.alter_column("capital_modules", "vehicle_type", nullable=True)
