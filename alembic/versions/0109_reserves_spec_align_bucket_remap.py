"""Remap reserve UseLine basis buckets to the reserves-spec-align vocabulary.

Slice 5c of reserves-spec-align (split from a single migration per
critique #5 so a failure here does not block the Stabilization
backfill in 0110, and either can be reverted independently).

What this does:

* ``cash_flow_support_reserve``  →  ``operating_deficit_reserve``
  Cash Flow Support Reserve was a debugging-era fallback removed in
  Slice 5b. Operating Deficit Reserve is the spec's first-class home
  for the operating shortfall. Engine-emitted CFSR rows kept their
  ``label`` but the bucket migrates so multi-source Dev Fee
  inclusion/exclusion rules now key off the new bucket.

* ``lease_up_reserve``           →  ``interest_reserve``
  The Lease-Up Reserve concept was merged into the umbrella IR in an
  earlier slice; the bucket value left on rows that pre-date the merge
  is moved to the IR bucket so the Dev Fee binding pipeline does not
  see a stale bucket key.

Behavior of un-stamped rows is unaffected — they continue to pick up
their bucket via ``classify_basis_bucket``'s label fallback at compute
time. This migration only touches the stamped column.

Revision ID: 0109
Revises: 0108
Create Date: 2026-06-03
"""

from __future__ import annotations

from alembic import op


revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE use_lines
        SET dev_fee_basis_bucket = 'operating_deficit_reserve'
        WHERE dev_fee_basis_bucket = 'cash_flow_support_reserve'
        """
    )
    op.execute(
        """
        UPDATE use_lines
        SET dev_fee_basis_bucket = 'interest_reserve'
        WHERE dev_fee_basis_bucket = 'lease_up_reserve'
        """
    )


def downgrade() -> None:
    # Not symmetric — the new vocabulary is the source of truth going
    # forward; we cannot reliably tell a post-spec ODR row from a
    # pre-spec CFSR row without keeping an extra column. The downgrade
    # leaves the new vocabulary in place (forward-only soft migration).
    pass
