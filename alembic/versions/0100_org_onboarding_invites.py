"""Org onboarding: nullable org_id, membership_status, org_invites table.

Revision ID: 0099
Revises: 0098
Create Date: 2026-05-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make org_id nullable — users exist briefly without an org between
    # registration and onboarding wizard completion.
    op.alter_column(
        "users",
        "org_id",
        existing_type=UUID(as_uuid=True),
        nullable=True,
    )

    # membership_status: 'active' (default) or 'pending' (awaiting admin approval).
    # Existing users backfill to 'active'.
    op.add_column(
        "users",
        sa.Column(
            "membership_status",
            sa.String(20),
            nullable=False,
            server_default="active",
        ),
    )

    # org_invites: tracks email invites sent by org admins.
    op.create_table(
        "org_invites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invited_by_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("token", sa.String(512), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_org_invites_org_id", "org_invites", ["org_id"])
    op.create_index("ix_org_invites_token", "org_invites", ["token"])


def downgrade() -> None:
    op.drop_index("ix_org_invites_token", table_name="org_invites")
    op.drop_index("ix_org_invites_org_id", table_name="org_invites")
    op.drop_table("org_invites")
    op.drop_column("users", "membership_status")
    op.alter_column(
        "users",
        "org_id",
        existing_type=UUID(as_uuid=True),
        nullable=False,
    )
