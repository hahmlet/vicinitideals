"""Email ingest creates only Opportunity, not Deal.

Architecture correction: previously the email ingest task created
Opportunity + Deal + Scenario + Project upfront. That duplicated the
new /deals/new?opp_id=<id> modal flow which creates Deal+Scenario+Project
from the user-confirmed Opportunity. Email ingest now stops at Opportunity
creation and hands off to the modal.

This migration:
- inbound_emails.deal_id -> inbound_emails.opportunity_id
- email_deal_suggestions.deal_id -> email_deal_suggestions.opportunity_id
- drops the deals.is_preliminary + deals.inbound_email_id columns the old
  flow added to anchor the preliminary Deal back to its source email

Revision ID: 0084
Revises: 0083
Create Date: 2026-05-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0084"
down_revision = "0083"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- inbound_emails: deal_id -> opportunity_id -----------------------
    op.drop_constraint(
        "inbound_emails_deal_id_fkey", "inbound_emails", type_="foreignkey"
    )
    op.drop_column("inbound_emails", "deal_id")
    op.add_column(
        "inbound_emails",
        sa.Column("opportunity_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "inbound_emails_opportunity_id_fkey",
        "inbound_emails",
        "opportunities",
        ["opportunity_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- email_deal_suggestions: deal_id -> opportunity_id --------------
    op.drop_constraint(
        "email_deal_suggestions_deal_id_fkey",
        "email_deal_suggestions",
        type_="foreignkey",
    )
    op.drop_column("email_deal_suggestions", "deal_id")
    op.add_column(
        "email_deal_suggestions",
        sa.Column("opportunity_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "email_deal_suggestions_opportunity_id_fkey",
        "email_deal_suggestions",
        "opportunities",
        ["opportunity_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- deals: drop columns the old preliminary-deal flow added --------
    op.drop_constraint(
        "deals_inbound_email_id_fkey", "deals", type_="foreignkey"
    )
    op.drop_column("deals", "inbound_email_id")
    op.drop_column("deals", "is_preliminary")


def downgrade() -> None:
    # --- deals: restore -------------------------------------------------
    op.add_column(
        "deals",
        sa.Column(
            "is_preliminary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "deals",
        sa.Column(
            "inbound_email_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "deals_inbound_email_id_fkey",
        "deals",
        "inbound_emails",
        ["inbound_email_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # --- email_deal_suggestions: opportunity_id -> deal_id -------------
    op.drop_constraint(
        "email_deal_suggestions_opportunity_id_fkey",
        "email_deal_suggestions",
        type_="foreignkey",
    )
    op.drop_column("email_deal_suggestions", "opportunity_id")
    op.add_column(
        "email_deal_suggestions",
        sa.Column(
            "deal_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "email_deal_suggestions_deal_id_fkey",
        "email_deal_suggestions",
        "deals",
        ["deal_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # --- inbound_emails: opportunity_id -> deal_id ---------------------
    op.drop_constraint(
        "inbound_emails_opportunity_id_fkey",
        "inbound_emails",
        type_="foreignkey",
    )
    op.drop_column("inbound_emails", "opportunity_id")
    op.add_column(
        "inbound_emails",
        sa.Column(
            "deal_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "inbound_emails_deal_id_fkey",
        "inbound_emails",
        "deals",
        ["deal_id"],
        ["id"],
        ondelete="SET NULL",
    )
