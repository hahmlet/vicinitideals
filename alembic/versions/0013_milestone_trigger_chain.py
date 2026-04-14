"""Add trigger_milestone_id and trigger_offset_days to milestones.

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "milestones",
        sa.Column(
            "trigger_milestone_id",
            UUID(as_uuid=True),
            sa.ForeignKey("milestones.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "milestones",
        sa.Column(
            "trigger_offset_days",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("milestones", "trigger_offset_days")
    op.drop_column("milestones", "trigger_milestone_id")
