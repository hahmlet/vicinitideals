"""Add org_deal_type_defaults and user_deal_type_defaults tables.

Revision ID: 0078
Revises: 0077
Create Date: 2026-05-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0078"
down_revision = "0077"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "org_deal_type_defaults",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("deal_type", sa.String(40), nullable=False),
        sa.Column("milestone_type", sa.String(40), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("starts_after_type", sa.String(40), nullable=True),
        sa.Column("offset_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("user_overridable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("updated_by", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("org_id", "deal_type", "milestone_type", name="uq_org_deal_type_defaults"),
    )
    op.create_table(
        "user_deal_type_defaults",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("deal_type", sa.String(40), nullable=False),
        sa.Column("milestone_type", sa.String(40), nullable=False),
        sa.Column("included", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("duration_days", sa.Integer(), nullable=True),
        sa.Column("starts_after_type", sa.String(40), nullable=True),
        sa.Column("offset_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("user_id", "deal_type", "milestone_type", name="uq_user_deal_type_defaults"),
    )


def downgrade() -> None:
    op.drop_table("user_deal_type_defaults")
    op.drop_table("org_deal_type_defaults")
