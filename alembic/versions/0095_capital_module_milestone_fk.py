"""Add active_from_milestone_id / active_to_milestone_id FKs to capital_modules.

CapitalModule.active_phase_start has been a free-form string ("acquisition",
"close", "operation_stabilized", milestone-key variants from the wizard) that
the engine maps to use-line phases via _APS_TO_USE_PHASE. The mapping is
brittle: a wizard value that doesn't appear in the table (or whose phase
mapping doesn't match the deal's actual phase plan) lands the auto-generated
"Total Finance Costs" UseLine in the wrong period — most painfully in the
first stabilized month for perm-only deals, crushing Year-1 stabilized profit.

This migration adds direct FKs from CapitalModule to Milestone so the engine
can resolve the activation timing the same way it does for milestone-anchored
UseLines (see _build_use_line_phase_overrides). Trigger-chain offsets, date
drags, and rename-safety all carry through.

Multi-project deals: the FK targets a milestone in a single project. Per-
project overrides remain on capital_module_projects.active_from string. A
follow-up migration may extend the junction with its own milestone FKs.

Backfill: for each existing capital_modules row with active_phase_start set,
finds a milestone on one of the scenario's projects whose milestone_type
matches the string and sets the FK. Best-effort — unmatched rows keep the
string field and the legacy mapping path.

Revision ID: 0095
Revises: 0094
Create Date: 2026-05-21
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None


# Wizard / legacy phase-key values → MilestoneType enum values they should map to.
# Pure-phase synonyms ("acquisition" → close, "pre_construction" → pre_development)
# are included so older rows can be backfilled. Unmapped values stay NULL.
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
        "capital_modules",
        sa.Column(
            "active_from_milestone_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "capital_modules",
        sa.Column(
            "active_to_milestone_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "capital_modules_active_from_milestone_fkey",
        "capital_modules",
        "milestones",
        ["active_from_milestone_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "capital_modules_active_to_milestone_fkey",
        "capital_modules",
        "milestones",
        ["active_to_milestone_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_capital_modules_active_from_milestone_id",
        "capital_modules",
        ["active_from_milestone_id"],
    )
    op.create_index(
        "ix_capital_modules_active_to_milestone_id",
        "capital_modules",
        ["active_to_milestone_id"],
    )

    # Backfill: try to wire each existing module to a milestone on one of its
    # scenario's projects, matching milestone_type to the phase-start string.
    # Multi-project scenarios pick the milestone on the lowest project_id
    # (deterministic) — operator can re-pick via the UI when needed.
    for aps_value, ms_type in _APS_TO_MILESTONE_TYPE.items():
        op.execute(
            sa.text(
                """
                WITH cand AS (
                  SELECT cm.id AS cm_id,
                         (
                           SELECT m.id
                           FROM milestones m
                           JOIN projects p ON p.id = m.project_id
                           WHERE p.scenario_id = cm.scenario_id
                             AND m.milestone_type = :ms_type
                           ORDER BY p.id, m.sequence_order, m.id
                           LIMIT 1
                         ) AS ms_id
                  FROM capital_modules cm
                  WHERE cm.active_phase_start = :aps_value
                    AND cm.active_from_milestone_id IS NULL
                )
                UPDATE capital_modules cm
                SET active_from_milestone_id = cand.ms_id
                FROM cand
                WHERE cm.id = cand.cm_id
                  AND cand.ms_id IS NOT NULL
                """
            ).bindparams(aps_value=aps_value, ms_type=ms_type)
        )

    # Same backfill for active_phase_end → active_to_milestone_id.
    for aps_value, ms_type in _APS_TO_MILESTONE_TYPE.items():
        op.execute(
            sa.text(
                """
                WITH cand AS (
                  SELECT cm.id AS cm_id,
                         (
                           SELECT m.id
                           FROM milestones m
                           JOIN projects p ON p.id = m.project_id
                           WHERE p.scenario_id = cm.scenario_id
                             AND m.milestone_type = :ms_type
                           ORDER BY p.id, m.sequence_order, m.id
                           LIMIT 1
                         ) AS ms_id
                  FROM capital_modules cm
                  WHERE cm.active_phase_end = :aps_value
                    AND cm.active_to_milestone_id IS NULL
                )
                UPDATE capital_modules cm
                SET active_to_milestone_id = cand.ms_id
                FROM cand
                WHERE cm.id = cand.cm_id
                  AND cand.ms_id IS NOT NULL
                """
            ).bindparams(aps_value=aps_value, ms_type=ms_type)
        )


def downgrade() -> None:
    op.drop_index(
        "ix_capital_modules_active_to_milestone_id",
        table_name="capital_modules",
    )
    op.drop_index(
        "ix_capital_modules_active_from_milestone_id",
        table_name="capital_modules",
    )
    op.drop_constraint(
        "capital_modules_active_to_milestone_fkey",
        "capital_modules",
        type_="foreignkey",
    )
    op.drop_constraint(
        "capital_modules_active_from_milestone_fkey",
        "capital_modules",
        type_="foreignkey",
    )
    op.drop_column("capital_modules", "active_to_milestone_id")
    op.drop_column("capital_modules", "active_from_milestone_id")
