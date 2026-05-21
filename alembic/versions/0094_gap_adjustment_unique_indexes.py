"""Dedupe gap-adjustment phantom rows and enforce one-per-project.

Concurrent Gap Adjustment slider POSTs raced the SELECT-then-INSERT
upsert paths in ``app/api/routers/models.py`` and could leave a project
with multiple phantom rows sharing the same reserved label. The next
read via ``scalar_one_or_none()`` then crashed with MultipleResultsFound
(see ``_has_any_gap_adjustment`` in ``app/api/routers/ui.py``).

This migration:
1. Collapses any existing duplicate phantom rows per (project_id, label),
   keeping the most recent by ``updated_at`` then ``id`` (deterministic).
2. Adds a partial unique index per affected table so the database itself
   guarantees one phantom row per project.

Reserved labels (defined in ``app/schemas/gap_adjustment_names.py``):
- ``Gap Adjustment — Revenue``           → ``income_streams``
- ``Gap Adjustment — OpEx``              → ``operating_expense_lines``
- ``Gap Adjustment — Purchase Price``    → ``use_lines``

Revision ID: 0094
Revises: 0093
Create Date: 2026-05-20
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None


_REVENUE_LABEL = "Gap Adjustment — Revenue"
_OPEX_LABEL = "Gap Adjustment — OpEx"
_PP_LABEL = "Gap Adjustment — Purchase Price"


def _dedupe(table: str, label: str) -> None:
    """Keep newest (updated_at, id) per project_id for this reserved label."""
    op.execute(
        sa.text(
            f"""
            DELETE FROM {table} a
            USING {table} b
            WHERE a.project_id = b.project_id
              AND a.label = :label
              AND b.label = :label
              AND (a.updated_at, a.id) < (b.updated_at, b.id)
            """
        ).bindparams(label=label)
    )


def upgrade() -> None:
    _dedupe("income_streams", _REVENUE_LABEL)
    _dedupe("operating_expense_lines", _OPEX_LABEL)
    _dedupe("use_lines", _PP_LABEL)

    op.create_index(
        "uq_income_streams_revenue_phantom",
        "income_streams",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text(f"label = '{_REVENUE_LABEL}'"),
    )
    op.create_index(
        "uq_operating_expense_lines_opex_phantom",
        "operating_expense_lines",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text(f"label = '{_OPEX_LABEL}'"),
    )
    op.create_index(
        "uq_use_lines_pp_phantom",
        "use_lines",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text(f"label = '{_PP_LABEL}'"),
    )


def downgrade() -> None:
    op.drop_index("uq_use_lines_pp_phantom", table_name="use_lines")
    op.drop_index(
        "uq_operating_expense_lines_opex_phantom",
        table_name="operating_expense_lines",
    )
    op.drop_index("uq_income_streams_revenue_phantom", table_name="income_streams")
