"""Backfill an ``operation_stabilized`` milestone on every project.

Slice 5c of reserves-spec-align (companion to 0109 — split per
critique #5 so each migration can be reverted independently).

Reserve windows (Interest Reserve, Operating Deficit Reserve,
Operating Reserve) all reference the Stabilization milestone to know
where one window ends and the next begins. The runtime foolproofing
service (``app/services/stabilization_milestone.py``) ensures the
milestone is present when the builder loads a project; this migration
brings every existing project up to that contract in one pass so the
reserve sizer never sees a project without it.

Anchor priority mirrors the runtime service exactly:

  1. ``operation_lease_up``    — natural predecessor
  2. ``construction``          — when no lease-up modeled
  3. ``pre_development``       — pure pre-dev → straight-to-stab structures
  4. ``close``                 — acquisition deals (turnkey rentals)

Anchor is left NULL when no predecessor exists; the UI flags those
projects so the user can pick an explicit ``target_date`` before
compute. ``duration_days`` defaults to 1825 (5 years) to match
``DEFAULT_DURATIONS["operation_stabilized"]``.

Revision ID: 0110
Revises: 0109
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op


revision = "0110"
down_revision = "0109"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Insert one operation_stabilized row per project that lacks one.
    # `sequence_order` lands at max(existing) + 1 so the row sorts after
    # everything that already exists. `trigger_milestone_id` picks the
    # natural predecessor by priority — see module docstring.
    op.execute(
        """
        WITH projects_missing_stab AS (
            SELECT p.id AS project_id,
                   COALESCE(MAX(m.sequence_order), 0) + 1 AS next_seq
            FROM projects p
            LEFT JOIN milestones m ON m.project_id = p.id
            WHERE NOT EXISTS (
                SELECT 1 FROM milestones x
                WHERE x.project_id = p.id
                  AND x.milestone_type = 'operation_stabilized'
            )
            GROUP BY p.id
        ),
        predecessor_pick AS (
            SELECT
                pms.project_id,
                pms.next_seq,
                (
                    SELECT m2.id
                    FROM milestones m2
                    WHERE m2.project_id = pms.project_id
                      AND m2.milestone_type IN (
                          'operation_lease_up',
                          'construction',
                          'pre_development',
                          'close'
                      )
                    ORDER BY CASE m2.milestone_type
                        WHEN 'operation_lease_up' THEN 1
                        WHEN 'construction'       THEN 2
                        WHEN 'pre_development'    THEN 3
                        WHEN 'close'              THEN 4
                    END
                    LIMIT 1
                ) AS trigger_id
            FROM projects_missing_stab pms
        )
        INSERT INTO milestones (
            id,
            project_id,
            milestone_type,
            duration_days,
            sequence_order,
            trigger_milestone_id,
            trigger_offset_days,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            pp.project_id,
            'operation_stabilized',
            1825,
            pp.next_seq,
            pp.trigger_id,
            0,
            NOW(),
            NOW()
        FROM predecessor_pick pp
        """
    )


def downgrade() -> None:
    # Forward-only soft migration. Removing all auto-created Stabilization
    # rows would also remove ones the user has since anchored / edited —
    # we cannot reliably distinguish them from the original backfill.
    # The runtime service will re-create any deleted rows on the next
    # builder load, so a downgrade is effectively a no-op anyway.
    pass
