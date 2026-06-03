"""Backfill ``operational_inputs.initial_occupancy_pct`` from NULL to 0.

Reserves-spec-align follow-up (2026-06-03).

As of commit ``1c524b5`` the cash-flow engine treats NULL
``initial_occupancy_pct`` as 0% (matching the wizard slider's default
rendering). Prior to that commit the engine treated NULL as 50%, so
every legacy row that was never touched by the slider would silently
flip its lease-up ramp shape on the next ``Compute`` -- changing
revenue, Operating Deficit Reserve sizing, and equity required.

This migration writes 0 onto every NULL row so the data layer matches
the new engine default explicitly. Rows already carrying an
explicit user value (any non-NULL number, including 0) are left
untouched.

Forward-only: there is no information in the data to distinguish a
"was-NULL, backfilled to 0" row from a "user-explicitly-set-to-0" row,
so a downgrade cannot restore prior state. The migration is
idempotent -- rerunning is a no-op once every row is non-NULL.

Revision ID: 0111
Revises: 0110
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op


revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE operational_inputs
        SET initial_occupancy_pct = 0
        WHERE initial_occupancy_pct IS NULL
        """
    )


def downgrade() -> None:
    # Cannot distinguish backfilled-0 from user-set-0. No-op.
    pass
