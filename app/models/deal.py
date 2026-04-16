"""Deal, Scenario (financial scenario), OperationalInputs, IncomeStream, UseLine, OperatingExpenseLine.

Entity hierarchy:
  Deal          — top-level investment thesis; groups Opportunities + Scenarios
  Scenario      — one financial plan for the deal (was DealModel / the old deals table)
  Project       — post-acquisition dev effort within a Scenario (one per parcel/building)

The old `Deal` ORM class is now `Scenario`.  A backward-compat alias DealModel = Scenario
is kept so existing code continues to import without immediate churn.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ProjectType(str, enum.Enum):
    """Scenario type — determines the default milestone sequence and CapEx template."""
    acquisition_minor_reno = "acquisition_minor_reno"
    acquisition_major_reno = "acquisition_major_reno"
    acquisition_conversion = "acquisition_conversion"
    new_construction = "new_construction"


class UseLinePhase(str, enum.Enum):
    acquisition = "acquisition"
    pre_construction = "pre_construction"
    construction = "construction"
    renovation = "renovation"
    conversion = "conversion"
    operation = "operation"
    exit = "exit"
    other = "other"


class UseLineTiming(str, enum.Enum):
    first_day = "first_day"   # lump sum on month 1 of the phase
    spread = "spread"         # divided evenly across all months of the phase


class IncomeStreamType(str, enum.Enum):
    residential_rent = "residential_rent"
    commercial_rent = "commercial_rent"
    parking = "parking"
    laundry = "laundry"
    utility_water = "utility_water"
    utility_electric = "utility_electric"
    utility_gas = "utility_gas"
    utility_internet = "utility_internet"
    storage = "storage"
    pet_fee = "pet_fee"
    deposit_forfeit = "deposit_forfeit"
    other = "other"


class DealStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


# ---------------------------------------------------------------------------
# Deal — top-level investment thesis
# ---------------------------------------------------------------------------

class Deal(Base):
    """Top-level deal entity.

    A Deal groups one or more Opportunities (the physical assets being considered)
    with one or more Scenarios (financial plans for how to pursue the deal).
    """

    __tablename__ = "deals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DealStatus] = mapped_column(
        String(30), nullable=False, default=DealStatus.active
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(  # type: ignore[name-defined]
        "Organization", back_populates="deals"
    )
    created_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        "User", foreign_keys=[created_by_user_id]
    )
    deal_opportunities: Mapped[list["DealOpportunity"]] = relationship(
        "DealOpportunity", back_populates="deal", cascade="all, delete-orphan"
    )
    scenarios: Mapped[list["Scenario"]] = relationship(
        "Scenario", back_populates="deal", cascade="all, delete-orphan"
    )


class DealOpportunity(Base):
    """Many-to-many join: a Deal can draw from multiple Opportunities."""

    __tablename__ = "deal_opportunities"
    __table_args__ = (
        UniqueConstraint("deal_id", "opportunity_id", name="uq_deal_opportunity"),
    )

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        primary_key=True,
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        primary_key=True,
    )

    # Relationships
    deal: Mapped["Deal"] = relationship("Deal", back_populates="deal_opportunities")
    opportunity: Mapped["Opportunity"] = relationship(  # type: ignore[name-defined]
        "Opportunity", back_populates="deal_opportunities"
    )


# ---------------------------------------------------------------------------
# Scenario — one financial plan for a Deal (was DealModel / deals table)
# ---------------------------------------------------------------------------

class Scenario(Base):
    """A financial scenario for a Deal — one specific plan for how to pursue it.

    Was previously called DealModel (and stored in the `deals` table).
    Multiple Scenarios can exist per Deal; each represents a different end state
    or financing approach.  The DealModel alias is kept for backward compat.
    """

    __tablename__ = "scenarios"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("deals.id", ondelete="CASCADE"), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Kept for backward compat / single-project scenarios — canonical location is Project.deal_type
    project_type: Mapped[ProjectType] = mapped_column(String(60), nullable=False)
    # "revenue_opex" (default) | "noi" — controls which income path the cashflow engine uses
    income_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="revenue_opex")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    deal: Mapped["Deal"] = relationship("Deal", back_populates="scenarios")
    projects: Mapped[list["Project"]] = relationship(  # type: ignore[name-defined]
        "Project", back_populates="scenario", passive_deletes=True
    )
    capital_modules: Mapped[list["CapitalModule"]] = relationship(  # type: ignore[name-defined]
        "CapitalModule", back_populates="scenario"
    )
    waterfall_tiers: Mapped[list["WaterfallTier"]] = relationship(  # type: ignore[name-defined]
        "WaterfallTier", back_populates="scenario"
    )
    waterfall_results: Mapped[list["WaterfallResult"]] = relationship(  # type: ignore[name-defined]
        "WaterfallResult", back_populates="scenario"
    )
    cash_flows: Mapped[list["CashFlow"]] = relationship(  # type: ignore[name-defined]
        "CashFlow", back_populates="scenario"
    )
    cash_flow_line_items: Mapped[list["CashFlowLineItem"]] = relationship(  # type: ignore[name-defined]
        "CashFlowLineItem", back_populates="scenario"
    )
    workflow_run_manifests: Mapped[list["WorkflowRunManifest"]] = relationship(  # type: ignore[name-defined]
        "WorkflowRunManifest", back_populates="scenario"
    )
    sensitivities: Mapped[list["Sensitivity"]] = relationship(  # type: ignore[name-defined]
        "Sensitivity", back_populates="scenario"
    )
    portfolio_scenarios: Mapped[list["PortfolioProject"]] = relationship(  # type: ignore[name-defined]
        "PortfolioProject", back_populates="scenario"
    )
    operational_outputs: Mapped["OperationalOutputs | None"] = relationship(  # type: ignore[name-defined]
        "OperationalOutputs", back_populates="scenario", uselist=False
    )
    draw_sources: Mapped[list["DrawSource"]] = relationship(  # type: ignore[name-defined]
        "DrawSource", back_populates="scenario", cascade="all, delete-orphan",
        order_by="DrawSource.sort_order",
    )
    # Reserve floors for draw schedule validation
    min_reserve_construction: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    min_reserve_operational: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)


# Backward-compat alias — old code importing DealModel still works
DealModel = Scenario


# ---------------------------------------------------------------------------
# OperationalInputs — scalar inputs for the cash flow engine (Project-level)
# ---------------------------------------------------------------------------

class OperationalInputs(Base):
    """Scalar inputs for the cash flow engine — belongs to Project, not Scenario."""

    __tablename__ = "operational_inputs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id"),
        unique=True,
        nullable=False,
    )

    # Unit / area
    unit_count_existing: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_count_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unit_count_after_conversion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    building_sqft: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    lot_sqft: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Acquisition (deprecated: use UseLine rows instead — kept for engine compatibility)
    purchase_price: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    closing_costs_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Hold phase
    hold_phase_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hold_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hold_vacancy_rate_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Entitlement
    entitlement_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entitlement_cost: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    carrying_cost_pct_annual: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Construction (deprecated cost fields: use UseLine rows instead — kept for engine compat)
    hard_cost_per_unit: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    soft_cost_pct_of_hard: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    contingency_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    construction_months: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Renovation (deprecated cost field: use UseLine rows instead — kept for engine compat)
    renovation_cost_total: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    renovation_months: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Conversion (deprecated cost fields: use UseLine rows instead — kept for engine compat)
    conversion_cost_per_unit: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    change_of_use_permit_cost: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    income_reduction_pct_during_reno: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Lease-up
    lease_up_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initial_occupancy_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Stabilized operations (deprecated OpEx scalars: use OperatingExpenseLine rows instead)
    opex_per_unit_annual: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    expense_growth_rate_pct_annual: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    mgmt_fee_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    property_tax_annual: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    insurance_annual: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    capex_reserve_per_unit_annual: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)

    # Exit (deprecated scalar: use UseLine with phase=exit instead)
    hold_period_years: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=5)
    exit_cap_rate_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    selling_costs_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)

    # Milestone tracking
    milestone_dates: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)

    # ── Deal Setup Wizard ────────────────────────────────────────────────────
    # Set by the deal setup wizard before any module work begins.
    deal_setup_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Legacy single-select: "perm_only" | "construction_to_perm" | "construction_and_perm"
    # Superseded by debt_types for new deals; kept for backward compat.
    debt_structure: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Multi-debt selection: list of funder_type strings in stack order.
    # e.g. ["pre_development_loan", "acquisition_loan", "construction_loan", "permanent_debt"]
    debt_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Per-debt milestone assignments and retirement chain.
    # {funder_type: {"active_from": str, "active_to": str, "retired_by": str|null}}
    debt_milestone_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # "gap_fill" | "dscr_capped" | "dual_constraint"
    debt_sizing_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    dscr_minimum: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("1.15"))
    # % of TPC to maintain as minimum balance during construction (only when construction debt)
    construction_floor_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    # months of projected debt service to maintain at stabilization start
    operation_reserve_months: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    # Per-debt terms for auto-created CapitalModule(s).
    # New structure: {funder_type: {rate_pct, amort_years, loan_type, sizing_approach, ltv_pct}}
    # Legacy flat keys (perm_rate_pct, perm_amort_years, construction_rate_pct) still read for old deals.
    debt_terms: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Asset management fee as % of (NOI - debt service), deducted pre-waterfall
    asset_mgmt_fee_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # ── NOI mode inputs (only used when DealModel.income_mode == 'noi') ──────
    # Annual stabilized NOI entered/pre-filled from listing; NULL = not yet set
    noi_stabilized_input: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    # Annual escalation rate applied month-by-month to the NOI input
    noi_escalation_rate_pct: Mapped[object] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("3")
    )

    # Relationships
    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        "Project", back_populates="operational_inputs"
    )


class OperatingExpenseLine(Base):
    __tablename__ = "operating_expense_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    annual_amount: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    per_value: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    per_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scale_with_lease_up: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    lease_up_floor_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    escalation_rate_pct_annual: Mapped[object] = mapped_column(
        Numeric(18, 6), nullable=False, default=3
    )
    active_in_phases: Mapped[list[str]] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        "Project", back_populates="expense_lines"
    )


class IncomeStream(Base):
    __tablename__ = "income_streams"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    stream_type: Mapped[IncomeStreamType] = mapped_column(String(60), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    amount_per_unit_monthly: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    amount_fixed_monthly: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    stabilized_occupancy_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=95)
    bad_debt_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    concessions_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    # Fraction of renovation premium absorbed per month during construction+lease-up
    # (0 = full premium from day one; 1.0 = linear ramp over reno+lease-up timeline)
    renovation_absorption_rate: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    escalation_rate_pct_annual: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    active_in_phases: Mapped[list[str]] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        "Project", back_populates="income_streams"
    )
    cash_flow_line_items: Mapped[list["CashFlowLineItem"]] = relationship(  # type: ignore[name-defined]
        "CashFlowLineItem", back_populates="income_stream"
    )


class UnitMix(Base):
    """Unit type breakdown for a Project (deal-local copy — not linked back to Building).

    Populated from the Building's unit count at Deal Setup and freely editable
    within the deal context.  Used to seed IncomeStream rows and to provide a
    per-unit denominator for $/unit expense lines.
    """

    __tablename__ = "unit_mix"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    unit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    avg_sqft: Mapped[object | None] = mapped_column(Numeric(18, 2), nullable=True)
    avg_monthly_rent: Mapped[object | None] = mapped_column(Numeric(18, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        "Project", back_populates="unit_mix"
    )


class UseLine(Base):
    """A one-time capital expenditure or use-of-funds line item (Project-level)."""

    __tablename__ = "use_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    phase: Mapped[UseLinePhase] = mapped_column(String(60), nullable=False)
    milestone_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    milestone_key_to: Mapped[str | None] = mapped_column(String(60), nullable=True)
    amount: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    timing_type: Mapped[str] = mapped_column(String(20), nullable=False, default="first_day")
    is_deferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        "Project", back_populates="use_lines"
    )
