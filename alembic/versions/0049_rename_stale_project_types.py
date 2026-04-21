"""Rename stale ProjectType enum values on existing Deals.

Commit 81b2596 (2026-04-19) renamed the ProjectType enum identifiers:

    acquisition_minor_reno → acquisition
    acquisition_major_reno → value_add
    acquisition_conversion → conversion

The rename was code-only under the assumption the DB would be wiped before
production. At least one scenario/project row survived the wipe and still
carries a pre-rename identifier, which crashes the cashflow engine at
_build_phase_plan with ``ValueError: Unsupported project_type``.

This migration does the data backfill the earlier commit skipped. Columns
are String(60), not a PG enum type, so plain UPDATEs suffice.

Revision ID: 0049
Revises: 0048
Create Date: 2026-04-20
"""

from alembic import op


revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


_RENAME_MAP = {
    "acquisition_minor_reno": "acquisition",
    "acquisition_major_reno": "value_add",
    "acquisition_conversion": "conversion",
}


def upgrade() -> None:
    for old, new in _RENAME_MAP.items():
        op.execute(
            f"UPDATE scenarios SET project_type = '{new}' "
            f"WHERE project_type = '{old}'"
        )
        op.execute(
            f"UPDATE projects SET deal_type = '{new}' "
            f"WHERE deal_type = '{old}'"
        )


def downgrade() -> None:
    # Not reversible: the old identifiers are no longer a valid ProjectType
    # enum in the Python code, so restoring them would re-break compute. If
    # you ever need to roll back, the correct move is to revert the code
    # commit that removed them (81b2596) first.
    pass
