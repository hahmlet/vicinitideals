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
import sqlalchemy as sa


revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


_NEW_CONSTRAINT = "uq_operational_outputs_scenario_project"


def upgrade() -> None:
    # The existing single-column unique on scenario_id may carry one of two
    # names depending on this DB's history:
    #   - ``operational_outputs_scenario_id_key`` (fresh install, matches
    #     SQLAlchemy auto-naming against the current ORM column name)
    #   - ``operational_outputs_deal_model_id_key`` (prod, legacy name from
    #     before the scenarios/deal_models rename; the constraint was kept
    #     as-is during that rename)
    # Find the real name from pg_constraint and drop it. On SQLite (tests)
    # there's no enforced unique constraint to drop — Base.metadata builds
    # the new UniqueConstraint from the ORM class directly.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        rows = bind.execute(
            sa.text(
                """
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'operational_outputs'::regclass
                  AND contype = 'u'
                  AND pg_get_constraintdef(oid) = 'UNIQUE (scenario_id)'
                """
            )
        ).fetchall()
        for row in rows:
            op.drop_constraint(row[0], "operational_outputs", type_="unique")

    op.create_unique_constraint(
        _NEW_CONSTRAINT,
        "operational_outputs",
        ["scenario_id", "project_id"],
    )


def downgrade() -> None:
    op.drop_constraint(_NEW_CONSTRAINT, "operational_outputs", type_="unique")
    # Restore the standard name (fresh-install convention). Databases that
    # had the legacy ``operational_outputs_deal_model_id_key`` name do NOT
    # get that legacy name back — this is intentional; rollback always lands
    # on the current SQLAlchemy convention.
    op.create_unique_constraint(
        "operational_outputs_scenario_id_key",
        "operational_outputs",
        ["scenario_id"],
    )
