"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-01 00:00:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # organizations
    # -------------------------------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    # -------------------------------------------------------------------------
    # users
    # -------------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("display_color", sa.String(20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # projects
    # -------------------------------------------------------------------------
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("project_category", sa.String(50), nullable=False),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # project_visibilities
    # -------------------------------------------------------------------------
    op.create_table(
        "project_visibilities",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("hidden", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("project_id", "user_id"),
    )

    # -------------------------------------------------------------------------
    # parcels
    # -------------------------------------------------------------------------
    op.create_table(
        "parcels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("apn", sa.String(100), nullable=False),
        sa.Column("address_normalized", sa.Text(), nullable=True),
        sa.Column("address_raw", sa.Text(), nullable=True),
        sa.Column("owner_name", sa.String(255), nullable=True),
        sa.Column("owner_mailing_address", sa.Text(), nullable=True),
        sa.Column("lot_sqft", sa.Numeric(18, 6), nullable=True),
        sa.Column("zoning_code", sa.String(50), nullable=True),
        sa.Column("zoning_description", sa.Text(), nullable=True),
        sa.Column("current_use", sa.String(255), nullable=True),
        sa.Column("assessed_value_land", sa.Numeric(18, 6), nullable=True),
        sa.Column("assessed_value_improvements", sa.Numeric(18, 6), nullable=True),
        sa.Column("year_built", sa.Integer(), nullable=True),
        sa.Column("building_sqft", sa.Numeric(18, 6), nullable=True),
        sa.Column("unit_count", sa.Integer(), nullable=True),
        sa.Column("geometry", sa.JSON(), nullable=True),
        sa.Column("scraped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_updated",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("apn"),
    )

    # -------------------------------------------------------------------------
    # project_parcels
    # -------------------------------------------------------------------------
    op.create_table(
        "project_parcels",
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parcel_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relationship", sa.String(50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["parcel_id"], ["parcels.id"]),
        sa.PrimaryKeyConstraint("project_id", "parcel_id"),
    )

    # -------------------------------------------------------------------------
    # parcel_transformations
    # -------------------------------------------------------------------------
    op.create_table(
        "parcel_transformations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transformation_type", sa.String(50), nullable=False),
        sa.Column("input_apns", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("output_apns", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("effective_lot_sqft", sa.Numeric(18, 6), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # permit_stubs
    # -------------------------------------------------------------------------
    op.create_table(
        "permit_stubs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("permit_number", sa.String(100), nullable=True),
        sa.Column("permit_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # ingest_jobs  (before scraped_listings which FK to it)
    # -------------------------------------------------------------------------
    op.create_table(
        "ingest_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("triggered_by", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("records_fetched", sa.Integer(), nullable=False),
        sa.Column("records_new", sa.Integer(), nullable=False),
        sa.Column("records_duplicate_exact", sa.Integer(), nullable=False),
        sa.Column("records_flagged_review", sa.Integer(), nullable=False),
        sa.Column("records_rejected", sa.Integer(), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # scraped_listings
    # -------------------------------------------------------------------------
    op.create_table(
        "scraped_listings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingest_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("listing_url", sa.Text(), nullable=False),
        sa.Column("address_normalized", sa.Text(), nullable=True),
        sa.Column("address_raw", sa.Text(), nullable=True),
        sa.Column("asking_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("unit_count", sa.Integer(), nullable=True),
        sa.Column("asking_cap_rate_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("year_built", sa.Integer(), nullable=True),
        sa.Column("lot_sqft", sa.Numeric(18, 6), nullable=True),
        sa.Column("building_sqft", sa.Numeric(18, 6), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column("is_new", sa.Boolean(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("matches_saved_criteria", sa.Boolean(), nullable=False),
        sa.Column("canonical_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "scraped_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("linked_project_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["ingest_job_id"], ["ingest_jobs.id"]),
        sa.ForeignKeyConstraint(["linked_project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("listing_url"),
    )

    # -------------------------------------------------------------------------
    # deal_models
    # -------------------------------------------------------------------------
    op.create_table(
        "deal_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("project_type", sa.String(60), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # operational_inputs
    # -------------------------------------------------------------------------
    op.create_table(
        "operational_inputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("unit_count_existing", sa.Integer(), nullable=True),
        sa.Column("unit_count_new", sa.Integer(), nullable=False),
        sa.Column("unit_count_after_conversion", sa.Integer(), nullable=True),
        sa.Column("building_sqft", sa.Numeric(18, 6), nullable=True),
        sa.Column("lot_sqft", sa.Numeric(18, 6), nullable=True),
        sa.Column("purchase_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("closing_costs_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("hold_phase_enabled", sa.Boolean(), nullable=False),
        sa.Column("hold_months", sa.Integer(), nullable=True),
        sa.Column("hold_vacancy_rate_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("entitlement_months", sa.Integer(), nullable=True),
        sa.Column("entitlement_cost", sa.Numeric(18, 6), nullable=True),
        sa.Column("carrying_cost_pct_annual", sa.Numeric(18, 6), nullable=True),
        sa.Column("hard_cost_per_unit", sa.Numeric(18, 6), nullable=True),
        sa.Column("soft_cost_pct_of_hard", sa.Numeric(18, 6), nullable=True),
        sa.Column("contingency_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("construction_months", sa.Integer(), nullable=True),
        sa.Column("renovation_cost_total", sa.Numeric(18, 6), nullable=True),
        sa.Column("renovation_months", sa.Integer(), nullable=True),
        sa.Column("conversion_cost_per_unit", sa.Numeric(18, 6), nullable=True),
        sa.Column("change_of_use_permit_cost", sa.Numeric(18, 6), nullable=True),
        sa.Column("income_reduction_pct_during_reno", sa.Numeric(18, 6), nullable=True),
        sa.Column("lease_up_months", sa.Integer(), nullable=True),
        sa.Column("initial_occupancy_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("opex_per_unit_annual", sa.Numeric(18, 6), nullable=False),
        sa.Column("expense_growth_rate_pct_annual", sa.Numeric(18, 6), nullable=False),
        sa.Column("mgmt_fee_pct", sa.Numeric(18, 6), nullable=False),
        sa.Column("property_tax_annual", sa.Numeric(18, 6), nullable=False),
        sa.Column("insurance_annual", sa.Numeric(18, 6), nullable=False),
        sa.Column("capex_reserve_per_unit_annual", sa.Numeric(18, 6), nullable=False),
        sa.Column("hold_period_years", sa.Numeric(18, 6), nullable=False),
        sa.Column("exit_cap_rate_pct", sa.Numeric(18, 6), nullable=False),
        sa.Column("selling_costs_pct", sa.Numeric(18, 6), nullable=False),
        sa.Column("milestone_dates", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["deal_model_id"], ["deal_models.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_model_id"),
    )

    # -------------------------------------------------------------------------
    # income_streams
    # -------------------------------------------------------------------------
    op.create_table(
        "income_streams",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stream_type", sa.String(60), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("unit_count", sa.Integer(), nullable=True),
        sa.Column("amount_per_unit_monthly", sa.Numeric(18, 6), nullable=True),
        sa.Column("amount_fixed_monthly", sa.Numeric(18, 6), nullable=True),
        sa.Column("stabilized_occupancy_pct", sa.Numeric(18, 6), nullable=False),
        sa.Column("escalation_rate_pct_annual", sa.Numeric(18, 6), nullable=False),
        sa.Column("active_in_phases", postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["deal_model_id"], ["deal_models.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # capital_modules
    # -------------------------------------------------------------------------
    op.create_table(
        "capital_modules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("funder_type", sa.String(60), nullable=False),
        sa.Column("stack_position", sa.Integer(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=True),
        sa.Column("carry", sa.JSON(), nullable=True),
        sa.Column("exit_terms", sa.JSON(), nullable=True),
        sa.Column("active_phase_start", sa.String(60), nullable=True),
        sa.Column("active_phase_end", sa.String(60), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["deal_model_id"], ["deal_models.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # waterfall_tiers
    # -------------------------------------------------------------------------
    op.create_table(
        "waterfall_tiers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capital_module_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("tier_type", sa.String(60), nullable=False),
        sa.Column("irr_hurdle_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("lp_split_pct", sa.Numeric(18, 6), nullable=False),
        sa.Column("gp_split_pct", sa.Numeric(18, 6), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.ForeignKeyConstraint(["deal_model_id"], ["deal_models.id"]),
        sa.ForeignKeyConstraint(["capital_module_id"], ["capital_modules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # waterfall_results
    # -------------------------------------------------------------------------
    op.create_table(
        "waterfall_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("tier_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("capital_module_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cash_distributed", sa.Numeric(18, 6), nullable=False),
        sa.Column("cumulative_distributed", sa.Numeric(18, 6), nullable=False),
        sa.Column("party_irr_pct", sa.Numeric(18, 6), nullable=True),
        sa.ForeignKeyConstraint(["deal_model_id"], ["deal_models.id"]),
        sa.ForeignKeyConstraint(["tier_id"], ["waterfall_tiers.id"]),
        sa.ForeignKeyConstraint(["capital_module_id"], ["capital_modules.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # operational_outputs
    # -------------------------------------------------------------------------
    op.create_table(
        "operational_outputs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("total_project_cost", sa.Numeric(18, 6), nullable=True),
        sa.Column("equity_required", sa.Numeric(18, 6), nullable=True),
        sa.Column("total_timeline_months", sa.Integer(), nullable=True),
        sa.Column("noi_stabilized", sa.Numeric(18, 6), nullable=True),
        sa.Column("cap_rate_on_cost_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("dscr", sa.Numeric(18, 6), nullable=True),
        sa.Column("project_irr_levered", sa.Numeric(18, 6), nullable=True),
        sa.Column("project_irr_unlevered", sa.Numeric(18, 6), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["deal_model_id"], ["deal_models.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_model_id"),
    )

    # -------------------------------------------------------------------------
    # cash_flows
    # -------------------------------------------------------------------------
    op.create_table(
        "cash_flows",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("period_type", sa.String(60), nullable=False),
        sa.Column("gross_revenue", sa.Numeric(18, 6), nullable=False),
        sa.Column("vacancy_loss", sa.Numeric(18, 6), nullable=False),
        sa.Column("effective_gross_income", sa.Numeric(18, 6), nullable=False),
        sa.Column("operating_expenses", sa.Numeric(18, 6), nullable=False),
        sa.Column("capex_reserve", sa.Numeric(18, 6), nullable=False),
        sa.Column("noi", sa.Numeric(18, 6), nullable=False),
        sa.Column("debt_service", sa.Numeric(18, 6), nullable=False),
        sa.Column("net_cash_flow", sa.Numeric(18, 6), nullable=False),
        sa.Column("cumulative_cash_flow", sa.Numeric(18, 6), nullable=False),
        sa.ForeignKeyConstraint(["deal_model_id"], ["deal_models.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # cash_flow_line_items
    # -------------------------------------------------------------------------
    op.create_table(
        "cash_flow_line_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period", sa.Integer(), nullable=False),
        sa.Column("income_stream_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(60), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("base_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("adjustments", sa.JSON(), nullable=True),
        sa.Column("net_amount", sa.Numeric(18, 6), nullable=False),
        sa.ForeignKeyConstraint(["deal_model_id"], ["deal_models.id"]),
        sa.ForeignKeyConstraint(["income_stream_id"], ["income_streams.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # scenarios
    # -------------------------------------------------------------------------
    op.create_table(
        "scenarios",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_model_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("variable", sa.String(255), nullable=False),
        sa.Column("range_min", sa.Numeric(18, 6), nullable=False),
        sa.Column("range_max", sa.Numeric(18, 6), nullable=False),
        sa.Column("range_steps", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["deal_model_id"], ["deal_models.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # scenario_results
    # -------------------------------------------------------------------------
    op.create_table(
        "scenario_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variable_value", sa.Numeric(18, 6), nullable=False),
        sa.Column("project_irr_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("lp_irr_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("gp_irr_pct", sa.Numeric(18, 6), nullable=True),
        sa.Column("equity_multiple", sa.Numeric(18, 6), nullable=True),
        sa.Column("cash_on_cash_year1_pct", sa.Numeric(18, 6), nullable=True),
        sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # portfolios
    # -------------------------------------------------------------------------
    op.create_table(
        "portfolios",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # portfolio_projects
    # -------------------------------------------------------------------------
    op.create_table(
        "portfolio_projects",
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("deal_model_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("capital_contribution", sa.Numeric(18, 6), nullable=True),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["deal_model_id"], ["deal_models.id"]),
        sa.PrimaryKeyConstraint("portfolio_id", "project_id"),
    )

    # -------------------------------------------------------------------------
    # gantt_entries
    # -------------------------------------------------------------------------
    op.create_table(
        "gantt_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("portfolio_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("phase", sa.String(60), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(["portfolio_id"], ["portfolios.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # dedup_candidates
    # -------------------------------------------------------------------------
    op.create_table(
        "dedup_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingest_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_a_type", sa.String(30), nullable=False),
        sa.Column("record_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_b_type", sa.String(30), nullable=False),
        sa.Column("record_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("match_signals", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["ingest_job_id"], ["ingest_jobs.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # -------------------------------------------------------------------------
    # saved_search_criteria
    # -------------------------------------------------------------------------
    op.create_table(
        "saved_search_criteria",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("min_units", sa.Integer(), nullable=True),
        sa.Column("max_units", sa.Integer(), nullable=True),
        sa.Column("max_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("zip_codes", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("property_types", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("sources", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("saved_search_criteria")
    op.drop_table("dedup_candidates")
    op.drop_table("gantt_entries")
    op.drop_table("portfolio_projects")
    op.drop_table("portfolios")
    op.drop_table("scenario_results")
    op.drop_table("scenarios")
    op.drop_table("cash_flow_line_items")
    op.drop_table("cash_flows")
    op.drop_table("operational_outputs")
    op.drop_table("waterfall_results")
    op.drop_table("waterfall_tiers")
    op.drop_table("capital_modules")
    op.drop_table("income_streams")
    op.drop_table("operational_inputs")
    op.drop_table("deal_models")
    op.drop_table("scraped_listings")
    op.drop_table("ingest_jobs")
    op.drop_table("permit_stubs")
    op.drop_table("parcel_transformations")
    op.drop_table("project_parcels")
    op.drop_table("parcels")
    op.drop_table("project_visibilities")
    op.drop_table("projects")
    op.drop_table("users")
    op.drop_table("organizations")
