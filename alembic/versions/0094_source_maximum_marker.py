"""Source maximum (grant cap) JSONB key — schema marker, no DDL.

Adds the `maximum` key to `capital_modules.source` JSONB for grant /
forgivable_loan / tax_credit sources that have per-Use eligibility set.

When `maximum` is non-null AND at least one Use has the module's ID in
its `eligible_module_ids` array (added in migration 0088), the cashflow
engine treats the source as capped consumption:
    source.amount = min(maximum, sum of eligible Use remaining buckets)

When `maximum` is null, the source contributes the user-entered
`amount` directly (legacy behavior — backward compatible for all
existing rows).

Because `capital_modules.source` is a JSONB column with no fixed
sub-schema, no DDL is required to add the key.  This migration exists
purely to anchor the schema version that the new engine path expects.

Revision ID: 0094
Revises: 0093
Create Date: 2026-05-20
"""

from __future__ import annotations

revision = "0094"
down_revision = "0093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # No DDL — JSONB key added via Pydantic schema (app/schemas/capital.py)
    # and engine writeback (app/engines/grant_caps.py).
    pass


def downgrade() -> None:
    # No-op: existing rows without `maximum` continue to work as legacy
    # fixed-amount sources. Engine treats missing key as null.
    pass
