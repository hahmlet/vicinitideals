"""Add email ingest tables and preliminary deal columns.

Revision ID: 0082
Revises: 0081
Create Date: 2026-05-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inbound_emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sender_email", sa.Text(), nullable=False),
        sa.Column("sender_name", sa.Text(), nullable=True),
        sa.Column("subject", sa.Text(), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("raw_mime_b64", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "proforma_task_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "attachments_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inbound_emails_org_id", "inbound_emails", ["org_id"])
    op.create_index("ix_inbound_emails_status", "inbound_emails", ["status"])

    op.create_table(
        "email_deal_suggestions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("inbound_email_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field_path", sa.Text(), nullable=False),
        sa.Column("suggested_value", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source_type", sa.String(40), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(
            ["inbound_email_id"], ["inbound_emails.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_email_deal_suggestions_email_id",
        "email_deal_suggestions",
        ["inbound_email_id"],
    )

    op.add_column(
        "deals",
        sa.Column(
            "is_preliminary", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "deals",
        sa.Column("inbound_email_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_deals_inbound_email_id",
        "deals",
        "inbound_emails",
        ["inbound_email_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_deals_inbound_email_id", "deals", type_="foreignkey")
    op.drop_column("deals", "inbound_email_id")
    op.drop_column("deals", "is_preliminary")
    op.drop_index(
        "ix_email_deal_suggestions_email_id", table_name="email_deal_suggestions"
    )
    op.drop_table("email_deal_suggestions")
    op.drop_index("ix_inbound_emails_status", table_name="inbound_emails")
    op.drop_index("ix_inbound_emails_org_id", table_name="inbound_emails")
    op.drop_table("inbound_emails")
