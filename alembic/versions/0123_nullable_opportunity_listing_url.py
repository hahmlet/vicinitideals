"""Make opportunities.listing_url nullable for user-generated projects.

Revision ID: 0123
Revises: 0122
"""

import sqlalchemy as sa
from alembic import op

revision = "0123"
down_revision = "0122"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("opportunities", "listing_url", nullable=True)


def downgrade() -> None:
    # Back-fill empty strings so no-default rows don't block the NOT NULL restore.
    op.execute("UPDATE opportunities SET listing_url = '' WHERE listing_url IS NULL")
    op.alter_column("opportunities", "listing_url", nullable=False)
