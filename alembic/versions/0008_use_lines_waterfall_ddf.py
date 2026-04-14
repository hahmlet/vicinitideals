"""Add use_lines table and WaterfallTier DDF fields

Revision ID: 0008
Revises: 0006
Create Date: 2026-04-04 12:00:00.000000

Schema changes aligned with the 8-component deal modeling framework:
  - Add use_lines table (additive — scalar Use fields in operational_inputs are kept
    as deprecated nullable columns for cashflow engine compatibility)
  - Add WaterfallTier.max_pct_of_distributable + interest_rate_pct for DDF tiers
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0008"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. use_lines table
    # -------------------------------------------------------------------------
    op.create_table(
        "use_lines",
        sa.Column("id", PG_UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "deal_model_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("deal_models.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("phase", sa.String(60), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("is_deferred", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index("ix_use_lines_deal_model_id", "use_lines", ["deal_model_id"])

    # -------------------------------------------------------------------------
    # 2. Add DDF fields to waterfall_tiers
    # -------------------------------------------------------------------------
    with op.batch_alter_table("waterfall_tiers") as batch_op:
        batch_op.add_column(
            sa.Column("max_pct_of_distributable", sa.Numeric(18, 6), nullable=True)
        )
        batch_op.add_column(
            sa.Column("interest_rate_pct", sa.Numeric(18, 6), nullable=True)
        )


def downgrade() -> None:
    # Restore waterfall_tiers columns
    with op.batch_alter_table("waterfall_tiers") as batch_op:
        batch_op.drop_column("interest_rate_pct")
        batch_op.drop_column("max_pct_of_distributable")

    # Drop use_lines table
    op.drop_index("ix_use_lines_deal_model_id", table_name="use_lines")
    op.drop_table("use_lines")
