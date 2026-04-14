"""Refactor entity renames — Phase 1a

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-04

Renames tables and FK columns to match the new entity hierarchy:
  projects        → opportunities        (purchase transaction)
  deal_models     → deals                (financial scenario)
  properties      → buildings            (structure on a parcel)

  deals.project_id              → deals.opportunity_id
  capital_modules.deal_model_id → capital_modules.deal_id
  waterfall_tiers.deal_model_id → waterfall_tiers.deal_id
  waterfall_results.deal_model_id → waterfall_results.deal_id
  use_lines.deal_model_id       → use_lines.deal_id

  Also adds source_type column to opportunities (scraped | manual).

  NOTE: income_streams, operating_expense_lines, operational_inputs still carry
  deal_model_id — those are re-keyed to project_id in Phase 1b when the new
  projects table is created.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # 1. Rename tables
    # -------------------------------------------------------------------------
    op.rename_table("projects", "opportunities")
    op.rename_table("deal_models", "deals")
    op.rename_table("properties", "buildings")

    # -------------------------------------------------------------------------
    # 2. deals.project_id → deals.opportunity_id
    #    (FK references opportunities.id — table was just renamed)
    # -------------------------------------------------------------------------
    with op.batch_alter_table("deals") as batch_op:
        batch_op.alter_column("project_id", new_column_name="opportunity_id")

    # -------------------------------------------------------------------------
    # 3. capital_modules.deal_model_id → capital_modules.deal_id
    # -------------------------------------------------------------------------
    with op.batch_alter_table("capital_modules") as batch_op:
        batch_op.alter_column("deal_model_id", new_column_name="deal_id")

    # -------------------------------------------------------------------------
    # 4. waterfall_tiers.deal_model_id → waterfall_tiers.deal_id
    # -------------------------------------------------------------------------
    with op.batch_alter_table("waterfall_tiers") as batch_op:
        batch_op.alter_column("deal_model_id", new_column_name="deal_id")

    # -------------------------------------------------------------------------
    # 5. waterfall_results.deal_model_id → waterfall_results.deal_id
    # -------------------------------------------------------------------------
    with op.batch_alter_table("waterfall_results") as batch_op:
        batch_op.alter_column("deal_model_id", new_column_name="deal_id")

    # -------------------------------------------------------------------------
    # 6. use_lines.deal_model_id → use_lines.deal_id
    # -------------------------------------------------------------------------
    with op.batch_alter_table("use_lines") as batch_op:
        batch_op.alter_column("deal_model_id", new_column_name="deal_id")

    # -------------------------------------------------------------------------
    # 7. Add source_type to opportunities (scraped | manual)
    # -------------------------------------------------------------------------
    op.add_column(
        "opportunities",
        sa.Column(
            "source_type",
            sa.String(20),
            nullable=False,
            server_default="manual",
        ),
    )


def downgrade() -> None:
    # Reverse in the opposite order

    op.drop_column("opportunities", "source_type")

    with op.batch_alter_table("use_lines") as batch_op:
        batch_op.alter_column("deal_id", new_column_name="deal_model_id")

    with op.batch_alter_table("waterfall_results") as batch_op:
        batch_op.alter_column("deal_id", new_column_name="deal_model_id")

    with op.batch_alter_table("waterfall_tiers") as batch_op:
        batch_op.alter_column("deal_id", new_column_name="deal_model_id")

    with op.batch_alter_table("capital_modules") as batch_op:
        batch_op.alter_column("deal_id", new_column_name="deal_model_id")

    with op.batch_alter_table("deals") as batch_op:
        batch_op.alter_column("opportunity_id", new_column_name="project_id")

    op.rename_table("buildings", "properties")
    op.rename_table("deals", "deal_models")
    op.rename_table("opportunities", "projects")
