"""Functional index on LOWER(brokerages.name) for case-insensitive lookup.

The Crexi upsert now performs a case-insensitive lookup against existing
brokerages before inserting, so we don't create separate rows for "SMIRE",
"Smire", and "smire". This index makes that lookup O(log n) instead of a
sequential scan.

We do NOT add a UNIQUE functional index — there are existing duplicates in
production that would block the migration. Manual dedup happens via the
existing dedup UI when convenient.

Revision ID: 0058
Revises: 0057
Create Date: 2026-04-24
"""

import sqlalchemy as sa
from alembic import op


revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_brokerages_lower_name",
        "brokerages",
        [sa.text("LOWER(name)")],
    )


def downgrade() -> None:
    op.drop_index("ix_brokerages_lower_name", table_name="brokerages")
