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
    false,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ProjectType(str, enum.Enum):
    """Scenario type — determines the default milestone sequence and CapEx template."""
    acquisition = "acquisition"
    value_add = "value_add"
    conversion = "conversion"
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

    # Market rate context — risk-free rate at time of underwriting (10Y Treasury).
    # Scenario-level: same value across all projects and all Base/Down/Up scenarios.
    # NULL → falls back to settings.default_risk_free_rate_pct (4.25%).
    risk_free_rate_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)


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
    # "linear" (default) or "s_curve" — controls occupancy ramp shape during lease-up
    lease_up_curve: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # S-curve steepness: 1 = flat/linear, 10 = steep S-curve (default 5)
    lease_up_curve_steepness: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # Stabilized operations (deprecated OpEx scalars: use OperatingExpenseLine rows instead)
    opex_per_unit_annual: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    expense_growth_rate_pct_annual: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=3, server_default="3")
    mgmt_fee_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    property_tax_annual: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    insurance_annual: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    capex_reserve_per_unit_annual: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)

    # Exit (deprecated scalar: use UseLine with phase=exit instead)
    exit_cap_rate_pct: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=5, server_default="5")
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
    # % of TPC to maintain as minimum balance during construction (only when construction debt)
    construction_floor_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    # months of projected debt service to maintain at stabilization start
    operation_reserve_months: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    # Per-debt terms — used as wizard staging (engine reads CapitalModule directly).
    # Shape: {funder_type: {rate_pct, amort_years, loan_type, hold_term_years, dscr_min, ltv_pct, ...}}
    debt_terms: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Asset management fee as % of (NOI - debt service), deducted pre-waterfall
    asset_mgmt_fee_pct: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)

    # ── NOI mode inputs (only used when DealModel.income_mode == 'noi') ──────
    # Annual stabilized NOI entered/pre-filled from listing; NULL = not yet set
    noi_stabilized_input: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    # True when noi_stabilized_input was silently seeded by the KNN comp engine
    # at builder load (income_mode="noi", no listing NOI). Cleared when the
    # user submits the NOI form. Drives the "auto-filled — confirm or override"
    # banner so the value isn't accepted blindly.
    noi_auto_seeded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    # Annual escalation rate applied month-by-month to the NOI input
    noi_escalation_rate_pct: Mapped[object] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("3")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        "Project", back_populates="operational_inputs"
    )


# Synonym map for legacy free-text OpEx labels → canonical categories.
# Used by the investor export to fold pre-vocabulary entries into the
# STANDARD_OPEX_CATEGORIES set. Two sources feed this map:
#   1. Engine-emitted hardcoded labels — `app/engines/cashflow.py` writes
#      "Property Tax", "Insurance", "Operating Expenses", "Management Fee",
#      "Carrying Cost" from legacy OperationalInputs scalar fields. These
#      need to project onto the canonical vocabulary so the export's OpEx
#      breakout doesn't show "Property Tax" $0 next to a user-entered
#      "Real Estate Taxes" with the actual value.
#   2. Common user variants observed in legacy seed data (`Subject Model`,
#      etc.) — typos and spelling variants from before the dropdown landed.
# The map is intentionally small; new typos go through Phase B2's dropdown
# enforcement.
OPEX_SYNONYMS: dict[str, str] = {
    # Engine-emitted labels
    "Property Tax": "Real Estate Taxes",
    "Operating Expenses": "Other",
    "Management Fee": "Property Management",
    "Carrying Cost": "Other",
    # Common user variants
    "Property Insurance": "Insurance",
    "Office / Admin": "Administrative",
    "Office/Admin": "Administrative",
    "Payroll & On-Site Staff": "Payroll",
    "On-Site Staff": "Payroll",
    "Garbage / Refuse": "Utilities — Trash",
    "Garbage / Trash": "Utilities — Trash",
    "Garbage": "Utilities — Trash",
    "Trash": "Utilities — Trash",
    "Refuse": "Utilities — Trash",
    "Grabage": "Utilities — Trash",  # known typo in seed data
    "Water / Sewer": "Utilities — Water/Sewer",
    "Water/Sewer": "Utilities — Water/Sewer",
    "Sewer": "Utilities — Water/Sewer",
    "Electric": "Utilities — Electric",
    "Electricity": "Utilities — Electric",
    "Gas": "Utilities — Gas",
    "Natural Gas": "Utilities — Gas",
}


def normalize_opex_label(label: str | None) -> str:
    """Map a free-text OpEx label to a canonical STANDARD_OPEX_CATEGORIES
    entry, falling back to the trimmed label itself if no synonym match.
    Whitespace is stripped on input — the export already does this for
    label-key dedup, this is the second guard."""
    cleaned = (label or "").strip()
    return OPEX_SYNONYMS.get(cleaned, cleaned)


# Universal multifamily OpEx categories — present on every CRE pro forma
# regardless of the deal's specifics. The investor export's OpEx breakout
# always renders these rows, even when the engine has $0 for them, so a
# missing data point is *visible* to the LP. A CRE professional reading a
# pro forma without a Property Tax line treats it as broken; explicitly
# showing $0 prompts the right "is this configured?" question.
ALWAYS_SHOWN_OPEX_CATEGORIES: tuple[str, ...] = (
    "Real Estate Taxes",
    "Insurance",
    "Property Management",
)


# Standard OpEx categories — controlled vocabulary surfaced in the
# OpEx-line entry UI as a dropdown. Free-text labels are still accepted at
# the DB layer (no constraint), but the UI nudges new entries toward this
# canonical set so the investor export can group by exact label without
# being defeated by typos like "Garbage" vs "Grabage". "Other" is the
# catch-all — anything that doesn't fit the standard list lumps in here.
# Order is the dropdown render order; alphabetical-ish within usage groups.
STANDARD_OPEX_CATEGORIES: tuple[str, ...] = (
    "Real Estate Taxes",
    "Insurance",
    "Property Management",
    "Utilities — Water/Sewer",
    "Utilities — Electric",
    "Utilities — Gas",
    "Utilities — Trash",
    "Repairs & Maintenance",
    "Marketing & Leasing",
    "Administrative",
    "Payroll",
    "Landscaping & Snow Removal",
    "Pest Control",
    "Cleaning & Janitorial",
    "Security",
    "Resident Services",
    "Compliance & Legal",
    "Bank/Software Fees",
    "Other",
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
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

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
    # Discrete capture schedule: JSON list of {year: int, capture_pct: float}
    # e.g. [{"year": 1, "capture_pct": 0}, {"year": 2, "capture_pct": 50}, {"year": 3, "capture_pct": 100}]
    # If set, overrides renovation_absorption_rate with discrete steps (PropRise-style)
    renovation_capture_schedule: Mapped[list | None] = mapped_column(JSON, nullable=True)
    escalation_rate_pct_annual: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    # LTL catchup: target rent to ramp toward (market_rent from UnitMix)
    # When set, escalation is accelerated up to ltl_catchup_cap until target is reached,
    # then reverts to escalation_rate_pct_annual.
    catchup_target_rent: Mapped[object | None] = mapped_column(Numeric(18, 6), nullable=True)
    active_in_phases: Mapped[list[str]] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

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
    # Bed/bath as numeric fields — come from comp data or user input. 0–4+ beds,
    # 0–3+ baths in 0.5 increments. Label is derived from these for display.
    beds: Mapped[object | None] = mapped_column(Numeric(4, 1), nullable=True)
    baths: Mapped[object | None] = mapped_column(Numeric(4, 1), nullable=True)
    # Loss-to-lease: market rent vs in-place rent spread
    market_rent_per_unit: Mapped[object | None] = mapped_column(Numeric(18, 2), nullable=True)
    in_place_rent_per_unit: Mapped[object | None] = mapped_column(Numeric(18, 2), nullable=True)
    # Unit strategy: "base_escalation" | "ltl_catchup" | "value_add_renovation"
    unit_strategy: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Post-renovation rent (only for value_add_renovation strategy)
    post_reno_rent_per_unit: Mapped[object | None] = mapped_column(Numeric(18, 2), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

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
    # Engine-injected reserve use-lines (Interest Reserve, Capitalized
    # Interest, Acq Interest, Lease-Up Reserve) tag the originating
    # CapitalModule so the Underwriting rollup can sum reserves per source.
    # NULL for user-entered uses. Added in migration 0048.
    source_capital_module_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("capital_modules.id", ondelete="SET NULL"),
        nullable=True,
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    phase: Mapped[UseLinePhase] = mapped_column(String(60), nullable=False)
    milestone_key: Mapped[str | None] = mapped_column(String(60), nullable=True)
    milestone_key_to: Mapped[str | None] = mapped_column(String(60), nullable=True)
    amount: Mapped[object] = mapped_column(Numeric(18, 6), nullable=False, default=0)
    timing_type: Mapped[str] = mapped_column(String(20), nullable=False, default="first_day")
    is_deferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project: Mapped["Project"] = relationship(  # type: ignore[name-defined]
        "Project", back_populates="use_lines"
    )
