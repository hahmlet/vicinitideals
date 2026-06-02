"""Stamp dev_fee basis bucket on use_lines.

Adds the ``use_lines.dev_fee_basis_bucket`` VARCHAR(40) NULL column. The
multi-source Developer Fee engine reads this stamped bucket first when
classifying a UseLine into a basis bucket, so user renames of engine-
auto-created rows (e.g. renaming "Interest Reserve" to "IR — Senior
Construction") don't break the inclusion/exclusion config saved on the
Source Vehicle preset (basis_exclusions list).

Backfill: existing rows get a one-time stamp derived from current
``label`` / ``cost_category`` using the same rules ``classify_basis_bucket``
applies as a fallback. New rows are stamped at engine auto-create sites.

Revision ID: 0106
Revises: 0105
Create Date: 2026-06-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0106"
down_revision = "0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "use_lines",
        sa.Column("dev_fee_basis_bucket", sa.String(40), nullable=True),
    )

    # One-shot backfill mirroring classify_basis_bucket()'s label-pattern
    # branch + cost_category remainder branch. Only stamps rows whose label
    # matches an engine-auto-created pattern; user-added custom rows stay
    # NULL and inherit the cost_category-derived bucket at classify time
    # (acq_remaining / soft_remaining / hard_remaining / other).
    op.execute(
        """
        UPDATE use_lines SET dev_fee_basis_bucket = CASE
            WHEN label IN ('Acquisition', 'Gap Adjustment — Purchase Price')
                THEN 'acquisition'
            WHEN label IN (
                'Interest Reserve',
                'Pre-Development Interest Reserve',
                'Acquisition Interest Reserve',
                'Construction Interest Reserve'
            )
                THEN 'interest_reserve'
            WHEN label IN (
                'Capitalized Construction Interest',
                'Capitalized Pre-Development Interest',
                'Capitalized Acquisition Interest'
            )
                THEN 'capitalized_interest'
            WHEN label LIKE '%% — Total Finance Costs'
                THEN 'total_finance_costs'
            WHEN label = 'Operating Reserve'
                THEN 'operating_reserve'
            WHEN label = 'Lease-Up Reserve'
                THEN 'lease_up_reserve'
            WHEN label = 'Construction DS Reserve'
                THEN 'construction_ds_reserve'
            WHEN label = 'Cash Flow Support Reserve'
                THEN 'cash_flow_support_reserve'
            ELSE NULL
        END
        WHERE dev_fee_basis_bucket IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("use_lines", "dev_fee_basis_bucket")
