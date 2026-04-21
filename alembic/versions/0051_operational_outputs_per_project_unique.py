"""Swap OperationalOutputs UNIQUE(scenario_id) for UNIQUE(scenario_id, project_id).

Phase 2 lets the engine write one OperationalOutputs row per project, so
the single-row-per-scenario constraint from the original schema has to go.
Multi-project scenarios will have N rows; single-project scenarios keep
exactly one (the existing row, whose project_id was backfilled by
migration 0050).

Revision ID: 0051
Revises: 0050
Create Date: 2026-04-20
"""

from alembic import op


revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


# Postgres auto-names single-column unique constraints ``{table}_{col}_key``.
_OLD_CONSTRAINT = "operational_outputs_scenario_id_key"
_NEW_CONSTRAINT = "uq_operational_outputs_scenario_project"


def upgrade() -> None:
    # Drop the single-column unique constraint. If a site has a different
    # constraint name (unlikely, but possible for legacy installs), the
    # downgrade is a no-op and this can be hand-run.
    op.drop_constraint(_OLD_CONSTRAINT, "operational_outputs", type_="unique")
    op.create_unique_constraint(
        _NEW_CONSTRAINT,
        "operational_outputs",
        ["scenario_id", "project_id"],
    )


def downgrade() -> None:
    op.drop_constraint(_NEW_CONSTRAINT, "operational_outputs", type_="unique")
    op.create_unique_constraint(
        _OLD_CONSTRAINT,
        "operational_outputs",
        ["scenario_id"],
    )
