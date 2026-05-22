"""Add per-project milestone FKs to capital_module_projects.

Multi-project deals can override a CapitalModule's activation window per
project via capital_module_projects.active_from / active_to string fields.
Mirror the FK pattern introduced in 0095 for capital_modules so junction-
level activation is rename-safe, trigger-chain aware, and date-drag friendly
just like the module-level FKs.

Backfill mirrors 0095's logic but scopes the milestone lookup to the
junction row's own project_id (not the entire scenario) so each junction
points at the right project's milestones in multi-project deals.

Revision ID: 0096
Revises: 0095
Create Date: 2026-05-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None


_APS_TO_MILESTONE_TYPE: dict[str, str] = {
    "acquisition":          "close",
    "close":                "close",
    "offer_made":           "offer_made",
    "under_contract":       "under_contract",
    "pre_construction":     "pre_development",
    "pre_development":      "pre_development",
    "construction":         "construction",
    "lease_up":             "operation_lease_up",
    "operation_lease_up":   "operation_lease_up",
    "stabilized":           "operation_stabilized",
    "operation_stabilized": "operation_stabilized",
    "exit":                 "divestment",
    "divestment":           "divestment",
}


def upgrade() -> None:
    op.add_column(
        "capital_module_projects",
        sa.Column(
            "active_from_milestone_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "capital_module_projects",
        sa.Column(
            "active_to_milestone_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "capital_module_projects_active_from_milestone_fkey",
        "capital_module_projects",
        "milestones",
        ["active_from_milestone_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "capital_module_projects_active_to_milestone_fkey",
        "capital_module_projects",
        "milestones",
        ["active_to_milestone_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_capital_module_projects_active_from_milestone_id",
        "capital_module_projects",
        ["active_from_milestone_id"],
    )
    op.create_index(
        "ix_capital_module_projects_active_to_milestone_id",
        "capital_module_projects",
        ["active_to_milestone_id"],
    )

    # Backfill scoped per junction row's project: find the matching milestone
    # on the junction's OWN project (not scenario-wide). This matters for
    # multi-project deals where each project has its own milestone set.
    for aps_value, ms_type in _APS_TO_MILESTONE_TYPE.items():
        op.execute(
            sa.text(
                """
                WITH cand AS (
                  SELECT j.id AS j_id,
                         (
                           SELECT m.id
                           FROM milestones m
                           WHERE m.project_id = j.project_id
                             AND m.milestone_type = :ms_type
                           ORDER BY m.sequence_order, m.id
                           LIMIT 1
                         ) AS ms_id
                  FROM capital_module_projects j
                  WHERE j.active_from = :aps_value
                    AND j.active_from_milestone_id IS NULL
                )
                UPDATE capital_module_projects j
                SET active_from_milestone_id = cand.ms_id
                FROM cand
                WHERE j.id = cand.j_id
                  AND cand.ms_id IS NOT NULL
                """
            ).bindparams(aps_value=aps_value, ms_type=ms_type)
        )

    for aps_value, ms_type in _APS_TO_MILESTONE_TYPE.items():
        op.execute(
            sa.text(
                """
                WITH cand AS (
                  SELECT j.id AS j_id,
                         (
                           SELECT m.id
                           FROM milestones m
                           WHERE m.project_id = j.project_id
                             AND m.milestone_type = :ms_type
                           ORDER BY m.sequence_order, m.id
                           LIMIT 1
                         ) AS ms_id
                  FROM capital_module_projects j
                  WHERE j.active_to = :aps_value
                    AND j.active_to_milestone_id IS NULL
                )
                UPDATE capital_module_projects j
                SET active_to_milestone_id = cand.ms_id
                FROM cand
                WHERE j.id = cand.j_id
                  AND cand.ms_id IS NOT NULL
                """
            ).bindparams(aps_value=aps_value, ms_type=ms_type)
        )


def downgrade() -> None:
    op.drop_index(
        "ix_capital_module_projects_active_to_milestone_id",
        table_name="capital_module_projects",
    )
    op.drop_index(
        "ix_capital_module_projects_active_from_milestone_id",
        table_name="capital_module_projects",
    )
    op.drop_constraint(
        "capital_module_projects_active_to_milestone_fkey",
        "capital_module_projects",
        type_="foreignkey",
    )
    op.drop_constraint(
        "capital_module_projects_active_from_milestone_fkey",
        "capital_module_projects",
        type_="foreignkey",
    )
    op.drop_column("capital_module_projects", "active_to_milestone_id")
    op.drop_column("capital_module_projects", "active_from_milestone_id")
