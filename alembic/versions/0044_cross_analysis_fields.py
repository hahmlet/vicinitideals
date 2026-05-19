"""No-op migration — all columns already added by 0042.

Originally intended to add cross-analysis fields not yet in the 0042
that was applied to production. 0042 was subsequently updated to include
all of those columns, making this migration a complete duplicate.
Kept as a no-op to preserve the migration chain (0043 → 0044 → 0045+).

Revision ID: 0044
Revises: 0043
Create Date: 2026-04-16
"""

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
