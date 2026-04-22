"""Add updated_at to input tables for staleness tracking.

Phase 3a introduces a staleness indicator ("an input was edited since the
last compute"). The rule is::

    is_stale = max(upstream_inputs.updated_at) > operational_outputs.computed_at

where ``operational_outputs`` is per-project as of migration 0050. Most
input tables don't carry an ``updated_at`` yet — this migration adds it
to every input table the staleness computation needs to read.

The column is ``DateTime(timezone=True)``, ``server_default=now()``,
``onupdate=now()``. On fresh inserts Postgres stamps the value; on any
UPDATE the DB re-stamps automatically. Backfill sets every existing row
to ``now()`` so staleness doesn't light up immediately post-deploy
(operators want "stale" to mean *someone edited this deal since its last
compute*, not *this deal existed before we added the column*).

Tables already carrying ``updated_at`` (skipped):
  - capital_module_projects (migration 0048)
  - project_anchors (migration 0048)

Tables that get ``updated_at`` here:
  - capital_modules
  - waterfall_tiers
  - operational_inputs
  - operating_expense_lines
  - income_streams
  - unit_mix
  - use_lines
  - milestones

Revision ID: 0052
Revises: 0051
Create Date: 2026-04-21
"""

from alembic import op
import sqlalchemy as sa


revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


_TABLES = (
    "capital_modules",
    "waterfall_tiers",
    "operational_inputs",
    "operating_expense_lines",
    "income_streams",
    "unit_mix",
    "use_lines",
    "milestones",
)


def upgrade() -> None:
    for tbl in _TABLES:
        op.add_column(
            tbl,
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                onupdate=sa.func.now(),
                nullable=False,
            ),
        )
    # Postgres fills via server_default on existing rows automatically when
    # the column is added with NOT NULL + server_default. No explicit
    # backfill needed. (SQLite in tests rebuilds the table via create_all.)


def downgrade() -> None:
    for tbl in reversed(_TABLES):
        op.drop_column(tbl, "updated_at")
