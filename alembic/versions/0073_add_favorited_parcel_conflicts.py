"""Add is_favorited and parcel_conflicts_ack to opportunities.

Revision ID: 0073
Revises: 0072
Create Date: 2026-05-06
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0073"
down_revision = "0072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("is_favorited", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "opportunities",
        sa.Column("parcel_conflicts_ack", JSONB(), nullable=True),
    )

    # Backfill: any opportunity already referenced by a project gets is_favorited = TRUE.
    # Projects only exist once a deal/scenario has been created, so this marks
    # all "in-pipeline" opportunities as favorited at migration time.
    op.execute(
        """
        UPDATE opportunities
        SET is_favorited = TRUE
        WHERE id IN (
            SELECT DISTINCT opportunity_id
            FROM projects
            WHERE opportunity_id IS NOT NULL
        )
        """
    )


def downgrade() -> None:
    op.drop_column("opportunities", "parcel_conflicts_ack")
    op.drop_column("opportunities", "is_favorited")
