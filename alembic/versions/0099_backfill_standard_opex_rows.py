"""Backfill the new standard operating expense rows.

This migration is additive only: it inserts missing rows for the newly added
standard OpEx labels on existing projects and leaves any existing rows and
values untouched.

Revision ID: 0099
Revises: 0098
Create Date: 2026-05-27
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None


_BACKFILL_ROWS = (
    "Accounting",
    "CapEx Reserve",
    "Telephone / Internet",
    "Utilities — All",
)


def upgrade() -> None:
    # Insert only missing rows. Existing rows with the same label are left alone.
    conn = op.get_bind()
    project_ids = [row[0] for row in conn.execute(sa.text("SELECT id FROM projects"))]
    for project_id in project_ids:
        for label in _BACKFILL_ROWS:
            exists = conn.execute(
                sa.text(
                    """
                    SELECT 1
                    FROM operating_expense_lines
                    WHERE project_id = :project_id
                      AND label = :label
                    LIMIT 1
                    """
                ),
                {"project_id": project_id, "label": label},
            ).first()
            if exists is not None:
                continue
            conn.execute(
                sa.text(
                    """
                    INSERT INTO operating_expense_lines (
                        id,
                        project_id,
                        label,
                        annual_amount,
                        per_value,
                        per_type,
                        scale_with_lease_up,
                        lease_up_floor_pct,
                        escalation_rate_pct_annual,
                        active_in_phases,
                        notes
                    ) VALUES (
                        :id,
                        :project_id,
                        :label,
                        0,
                        0,
                        'flat',
                        false,
                        NULL,
                        3,
                        ARRAY['lease_up', 'stabilized']::text[],
                        NULL
                    )
                    """
                ),
                {"id": str(uuid.uuid4()), "project_id": project_id, "label": label},
            )


def downgrade() -> None:
    # One-way data backfill. Downgrade intentionally does nothing to avoid
    # removing user-created rows that happen to match the same labels.
    pass