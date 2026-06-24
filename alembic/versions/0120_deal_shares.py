"""Add deal_shares — revocable guest links to a whole Deal's document rooms.

Revision ID: 0120
Revises: 0119
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0120"
down_revision = "0119"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deal_shares",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("NOW()")),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deal_shares_deal", "deal_shares", ["org_id", "deal_id"])
    op.create_index("ix_deal_shares_slug", "deal_shares", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_deal_shares_slug", table_name="deal_shares")
    op.drop_index("ix_deal_shares_deal", table_name="deal_shares")
    op.drop_table("deal_shares")
