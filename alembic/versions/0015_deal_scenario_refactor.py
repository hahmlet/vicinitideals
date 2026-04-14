"""Deal → Scenario architectural refactor.

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-05

Summary of DB changes:

  Phase 1 — Rename sensitivity-analysis tables to free up `scenarios` name
    scenarios        → sensitivities
    scenario_results → sensitivity_results
    sensitivities.project_id     → opportunity_id
    sensitivities.deal_model_id  → scenario_id
    sensitivity_results.scenario_id → sensitivity_id

  Phase 2 — Rename old financial-plan `deals` → temporary `scenarios_fp`
    (to avoid a name collision while we create the new top-level `deals` table)

  Phase 3 — Create new top-level `deals` + `deal_opportunities`
    Backfill: one new Deal per existing fp row (org_id from linked Opportunity)
    Backfill: one deal_opportunity row per fp row
    Add scenarios_fp.deal_id (backfill from new deals via temporary _fp_row_id helper column)
    Drop scenarios_fp.opportunity_id
    Rename scenarios_fp → scenarios

  Phase 4 — Rename FK columns in all dependent tables
    projects.deal_id              → scenario_id
    capital_modules.deal_id       → scenario_id
    waterfall_tiers.deal_id       → scenario_id
    waterfall_results.deal_id     → scenario_id
    cash_flows.deal_model_id      → scenario_id
    cash_flow_line_items.deal_model_id → scenario_id
    operational_outputs.deal_model_id  → scenario_id
    workflow_run_manifests.model_id    → scenario_id
    portfolio_projects.deal_model_id   → scenario_id
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # =========================================================================
    # Phase 1 — Rename sensitivity-analysis tables
    # =========================================================================

    op.rename_table("scenarios", "sensitivities")

    with op.batch_alter_table("sensitivities") as batch_op:
        batch_op.alter_column("project_id", new_column_name="opportunity_id")
        batch_op.alter_column("deal_model_id", new_column_name="scenario_id")

    op.rename_table("scenario_results", "sensitivity_results")

    with op.batch_alter_table("sensitivity_results") as batch_op:
        batch_op.alter_column("scenario_id", new_column_name="sensitivity_id")

    # =========================================================================
    # Phase 2 — Rename old financial-plan `deals` to a temp name
    # =========================================================================

    op.rename_table("deals", "scenarios_fp")

    # =========================================================================
    # Phase 3 — Create new top-level `deals` table
    # =========================================================================

    # 3a. Create `deals` with a temporary `_fp_row_id` column for backfill tracking
    op.create_table(
        "deals",
        sa.Column("id", PG_UUID(as_uuid=True), nullable=False),
        sa.Column(
            "_fp_row_id",
            PG_UUID(as_uuid=True),
            nullable=True,
            comment="Temporary backfill reference — dropped at end of migration",
        ),
        sa.Column(
            "org_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=True,
        ),
        sa.Column(
            "created_by_user_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("name", sa.String(255), nullable=False, server_default="Unnamed Deal"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # 3b. Backfill: one new top-level Deal per existing fp row
    op.execute(
        """
        INSERT INTO deals (id, _fp_row_id, org_id, created_by_user_id, name, status, created_at)
        SELECT
            gen_random_uuid(),
            fp.id,
            opp.org_id,
            fp.created_by_user_id,
            fp.name,
            'active',
            fp.created_at
        FROM scenarios_fp fp
        LEFT JOIN opportunities opp ON opp.id = fp.opportunity_id
        """
    )

    # 3c. Create `deal_opportunities` join table
    op.create_table(
        "deal_opportunities",
        sa.Column(
            "deal_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("deals.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "opportunity_id",
            PG_UUID(as_uuid=True),
            sa.ForeignKey("opportunities.id", ondelete="CASCADE"),
            nullable=False,
            primary_key=True,
        ),
        sa.UniqueConstraint("deal_id", "opportunity_id", name="uq_deal_opportunity"),
    )

    # 3d. Backfill deal_opportunities
    op.execute(
        """
        INSERT INTO deal_opportunities (deal_id, opportunity_id)
        SELECT nd.id, fp.opportunity_id
        FROM deals nd
        JOIN scenarios_fp fp ON fp.id = nd._fp_row_id
        WHERE fp.opportunity_id IS NOT NULL
        """
    )

    # 3e. Add `deal_id` (nullable) to scenarios_fp
    op.add_column(
        "scenarios_fp",
        sa.Column("deal_id", PG_UUID(as_uuid=True), nullable=True),
    )

    # 3f. Backfill scenarios_fp.deal_id from the new deals table via _fp_row_id
    op.execute(
        """
        UPDATE scenarios_fp fp
        SET deal_id = nd.id
        FROM deals nd
        WHERE nd._fp_row_id = fp.id
        """
    )

    # 3g. Make deal_id NOT NULL (every fp row should now have a deal_id)
    op.alter_column("scenarios_fp", "deal_id", nullable=False)

    # 3h. Add FK constraint for scenarios_fp.deal_id → deals.id
    op.create_foreign_key(
        "fk_scenarios_fp_deal_id",
        "scenarios_fp",
        "deals",
        ["deal_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 3i. Drop opportunity_id from scenarios_fp (now carried by deal_opportunities)
    op.drop_column("scenarios_fp", "opportunity_id")

    # 3j. Drop the temporary backfill column from deals
    op.drop_column("deals", "_fp_row_id")

    # 3k. Make org_id NOT NULL (every deal row was backfilled)
    op.alter_column("deals", "org_id", nullable=False)

    # 3l. Rename scenarios_fp → scenarios (the final financial-plan table name)
    op.rename_table("scenarios_fp", "scenarios")

    # =========================================================================
    # Phase 4 — Rename FK columns in dependent tables
    # =========================================================================

    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column("deal_id", new_column_name="scenario_id")

    with op.batch_alter_table("capital_modules") as batch_op:
        batch_op.alter_column("deal_id", new_column_name="scenario_id")

    with op.batch_alter_table("waterfall_tiers") as batch_op:
        batch_op.alter_column("deal_id", new_column_name="scenario_id")

    with op.batch_alter_table("waterfall_results") as batch_op:
        batch_op.alter_column("deal_id", new_column_name="scenario_id")

    with op.batch_alter_table("cash_flows") as batch_op:
        batch_op.alter_column("deal_model_id", new_column_name="scenario_id")

    with op.batch_alter_table("cash_flow_line_items") as batch_op:
        batch_op.alter_column("deal_model_id", new_column_name="scenario_id")

    with op.batch_alter_table("operational_outputs") as batch_op:
        batch_op.alter_column("deal_model_id", new_column_name="scenario_id")

    with op.batch_alter_table("workflow_run_manifests") as batch_op:
        batch_op.alter_column("model_id", new_column_name="scenario_id")

    with op.batch_alter_table("portfolio_projects") as batch_op:
        batch_op.alter_column("deal_model_id", new_column_name="scenario_id")

    # sensitivities.scenario_id was renamed from deal_model_id in Phase 1.
    # After renaming scenarios_fp → scenarios in Phase 3, its FK now correctly
    # references scenarios.id.


def downgrade() -> None:
    # =========================================================================
    # Reverse Phase 4
    # =========================================================================

    with op.batch_alter_table("portfolio_projects") as batch_op:
        batch_op.alter_column("scenario_id", new_column_name="deal_model_id")

    with op.batch_alter_table("workflow_run_manifests") as batch_op:
        batch_op.alter_column("scenario_id", new_column_name="model_id")

    with op.batch_alter_table("operational_outputs") as batch_op:
        batch_op.alter_column("scenario_id", new_column_name="deal_model_id")

    with op.batch_alter_table("cash_flow_line_items") as batch_op:
        batch_op.alter_column("scenario_id", new_column_name="deal_model_id")

    with op.batch_alter_table("cash_flows") as batch_op:
        batch_op.alter_column("scenario_id", new_column_name="deal_model_id")

    with op.batch_alter_table("waterfall_results") as batch_op:
        batch_op.alter_column("scenario_id", new_column_name="deal_id")

    with op.batch_alter_table("waterfall_tiers") as batch_op:
        batch_op.alter_column("scenario_id", new_column_name="deal_id")

    with op.batch_alter_table("capital_modules") as batch_op:
        batch_op.alter_column("scenario_id", new_column_name="deal_id")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column("scenario_id", new_column_name="deal_id")

    # =========================================================================
    # Reverse Phase 3 — restore scenarios → deals (old financial-plan table)
    # =========================================================================

    op.rename_table("scenarios", "scenarios_fp")

    # Restore opportunity_id (from deal_opportunities)
    op.add_column(
        "scenarios_fp",
        sa.Column("opportunity_id", PG_UUID(as_uuid=True), nullable=True),
    )
    op.execute(
        """
        UPDATE scenarios_fp fp
        SET opportunity_id = do_.opportunity_id
        FROM deal_opportunities do_
        JOIN deals nd ON nd.id = do_.deal_id
        WHERE nd.id = fp.deal_id
        """
    )

    # Drop deal_id + FK
    op.drop_constraint("fk_scenarios_fp_deal_id", "scenarios_fp", type_="foreignkey")
    op.drop_column("scenarios_fp", "deal_id")

    # Drop deal_opportunities + new deals rows
    op.drop_table("deal_opportunities")
    op.drop_table("deals")

    # Rename back to `deals`
    op.rename_table("scenarios_fp", "deals")

    # =========================================================================
    # Reverse Phase 1
    # =========================================================================

    with op.batch_alter_table("sensitivity_results") as batch_op:
        batch_op.alter_column("sensitivity_id", new_column_name="scenario_id")

    op.rename_table("sensitivity_results", "scenario_results")

    with op.batch_alter_table("sensitivities") as batch_op:
        batch_op.alter_column("scenario_id", new_column_name="deal_model_id")
        batch_op.alter_column("opportunity_id", new_column_name="project_id")

    op.rename_table("sensitivities", "scenarios")
