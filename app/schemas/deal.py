"""Deal, Scenario, OperationalInputs, IncomeStream, CashFlow, OperationalOutputs schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.gap_adjustment_names import is_reserved_label


def _validate_label_not_reserved(v: str | None) -> str | None:
    """Reject Gap Adjustment reserved labels on user-facing Create/Update.

    The slider feature owns these labels — the API blocks human attempts to
    create new lines with them or to rename other lines into them. Phantom
    rows themselves are managed via the dedicated /sliders endpoint, which
    bypasses these schemas.
    """
    if v is not None and is_reserved_label(v):
        raise ValueError(
            f"label {v!r} is reserved for the Gap Adjustment slider feature; "
            "phantom rows are managed by the slider, pick a different label"
        )
    return v

from app.models.cashflow import LineItemCategory, PeriodType

_EXAMPLE_ORG_ID = "11111111-1111-1111-1111-111111111111"
_EXAMPLE_DEAL_ID = "22222222-2222-2222-2222-222222222222"
_EXAMPLE_SCENARIO_ID = "33333333-3333-3333-3333-333333333333"
_EXAMPLE_PROJECT_ID = "44444444-4444-4444-4444-444444444444"
_EXAMPLE_STREAM_ID = "55555555-5555-5555-5555-555555555555"
_EXAMPLE_EXPENSE_LINE_ID = "66666666-6666-6666-6666-666666666666"
_EXAMPLE_OUTPUT_ID = "77777777-7777-7777-7777-777777777777"
_EXAMPLE_USER_ID = "88888888-8888-8888-8888-888888888888"
_EXAMPLE_CREATED_AT = "2026-04-03T12:00:00Z"


def _example_config(example: dict[str, object], *, from_attributes: bool = False) -> ConfigDict:
    config: dict[str, object] = {"json_schema_extra": {"examples": [example]}}
    if from_attributes:
        config["from_attributes"] = True
    return ConfigDict(**config)


from app.models.deal import DealStatus, IncomeStreamType, ProjectType, UseLinePhase  # noqa: E402


# ---------------------------------------------------------------------------
# Deal (top-level entity)
# ---------------------------------------------------------------------------

class DealBase(BaseModel):
    name: str
    status: DealStatus = DealStatus.active


class DealCreate(DealBase):
    org_id: uuid.UUID
    created_by_user_id: uuid.UUID | None = None

    model_config = _example_config(
        {
            "org_id": _EXAMPLE_ORG_ID,
            "created_by_user_id": _EXAMPLE_USER_ID,
            "name": "619 NE 190th Ave",
            "status": "active",
        }
    )


class DealRead(DealBase):
    id: uuid.UUID
    org_id: uuid.UUID
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime

    model_config = _example_config(
        {
            "id": _EXAMPLE_DEAL_ID,
            "org_id": _EXAMPLE_ORG_ID,
            "created_by_user_id": _EXAMPLE_USER_ID,
            "name": "619 NE 190th Ave",
            "status": "active",
            "created_at": _EXAMPLE_CREATED_AT,
        },
        from_attributes=True,
    )


# ---------------------------------------------------------------------------
# Scenario (financial plan for a Deal — was Scenario)
# ---------------------------------------------------------------------------

class ScenarioBase(BaseModel):
    name: str
    version: int = 1
    is_active: bool = True
    project_type: ProjectType
    # Income mode selector: "revenue_opex" (income streams + expense lines,
    # default) or "noi" (user enters stabilized NOI directly via
    # OperationalInputs.noi_stabilized_input).  Added to JSON export in
    # deal-json-v2 so Phase B NOI-mode deals round-trip correctly.
    income_mode: str = "revenue_opex"
    # ── deal-json-v3 round-trip fields (mirror ORM Scenario) ─────────────
    # Reserve floors for draw schedule validation.
    min_reserve_construction: Decimal | None = None
    min_reserve_operational: Decimal | None = None
    # 10Y Treasury at underwriting time; NULL → settings default (4.25%).
    risk_free_rate_pct: Decimal | None = None
    # Investor hurdle rate for DCF NPV / WEM; NULL → 8.0% default.
    discount_rate_pct: Decimal | None = None
    # Deal Health RAG threshold overrides (occ/oer/dscr/margin greens).
    health_thresholds: dict | None = None
    # Source Vehicle selected at deal creation (no FK — org or user scope).
    source_vehicle_id: uuid.UUID | None = None


class ScenarioCreate(ScenarioBase):
    deal_id: uuid.UUID
    created_by_user_id: uuid.UUID | None = None

    model_config = _example_config(
        {
            "deal_id": _EXAMPLE_DEAL_ID,
            "created_by_user_id": _EXAMPLE_USER_ID,
            "name": "Base Case",
            "version": 1,
            "is_active": True,
            "project_type": "acquisition",
        }
    )


class ScenarioRead(ScenarioBase):
    id: uuid.UUID
    deal_id: uuid.UUID
    created_by_user_id: uuid.UUID | None = None
    created_at: datetime

    model_config = _example_config(
        {
            "id": _EXAMPLE_SCENARIO_ID,
            "deal_id": _EXAMPLE_DEAL_ID,
            "created_by_user_id": _EXAMPLE_USER_ID,
            "name": "Base Case",
            "version": 1,
            "is_active": True,
            "project_type": "acquisition",
            "created_at": _EXAMPLE_CREATED_AT,
        },
        from_attributes=True,
    )




# ---------------------------------------------------------------------------
# OperationalInputs
# ---------------------------------------------------------------------------

class OperationalInputsBase(BaseModel):
    unit_count_existing: int | None = None
    unit_count_new: int = 0
    unit_count_after_conversion: int | None = None
    building_sqft: Decimal | None = None
    lot_sqft: Decimal | None = None

    # Deprecated acquisition scalars — use UseLine rows (kept for engine compatibility)
    purchase_price: Decimal | None = None
    closing_costs_pct: Decimal | None = None

    hold_phase_enabled: bool = False
    hold_months: int | None = None
    hold_vacancy_rate_pct: Decimal | None = None

    entitlement_months: int | None = None
    entitlement_cost: Decimal | None = None
    carrying_cost_pct_annual: Decimal | None = None

    # Deprecated construction/renovation cost scalars — use UseLine rows
    hard_cost_per_unit: Decimal | None = None
    soft_cost_pct_of_hard: Decimal | None = None
    contingency_pct: Decimal | None = None
    construction_months: int | None = None
    renovation_cost_total: Decimal | None = None
    renovation_months: int | None = None
    conversion_cost_per_unit: Decimal | None = None
    change_of_use_permit_cost: Decimal | None = None
    income_reduction_pct_during_reno: Decimal | None = None

    lease_up_months: int | None = None
    initial_occupancy_pct: Decimal | None = None
    lease_up_curve: str | None = None  # "linear" (default) or "s_curve"
    lease_up_curve_steepness: Decimal | None = None  # S-curve steepness (1=flat, 10=steep, default 5)

    # Deprecated OpEx scalars — use OperatingExpenseLine rows
    opex_per_unit_annual: Decimal = Decimal("0")
    expense_growth_rate_pct_annual: Decimal = Decimal("0")
    mgmt_fee_pct: Decimal = Decimal("0")
    property_tax_annual: Decimal = Decimal("0")
    insurance_annual: Decimal = Decimal("0")
    capex_reserve_per_unit_annual: Decimal = Decimal("0")
    going_in_cap_rate_pct: Decimal | None = None

    exit_cap_rate_pct: Decimal = Decimal("0")
    # Deprecated exit scalar — use UseLine with phase=exit
    selling_costs_pct: Decimal = Decimal("0")
    # Manual sale-price override; when > 0, wins over NOI / exit_cap valuation.
    sale_price_override: Decimal | None = None

    milestone_dates: dict[str, str] | None = None

    # ── Deal Setup Wizard + Phase B multi-debt ──────────────────────────
    # Written by the wizard before any module work begins.  All of these
    # fields were missing from the JSON export prior to April 2026, which
    # meant Phase B deals could not round-trip through the exporter.
    deal_setup_complete: bool = False

    # Legacy single-select: "perm_only" | "construction_to_perm" | "construction_and_perm".
    # Superseded by debt_types for new deals but kept for pre-migration deals.
    debt_structure: str | None = None

    # Ordered list of funder_type strings, e.g.
    # ["pre_development_loan", "construction_loan", "permanent_debt"]
    debt_types: list[str] | None = None

    # Per-debt milestone assignments and retirement chain.
    # {funder_type: {"active_from": str, "active_to": str, "retired_by": str | null}}
    debt_milestone_config: dict[str, dict] | None = None

    # "gap_fill" | "dscr_capped"
    debt_sizing_mode: str | None = None

    # % of TPC to maintain as minimum balance during construction (construction debt only)
    construction_floor_pct: Decimal | None = None

    # Months of projected debt service to maintain at stabilization start
    operation_reserve_months: int = 6

    # Per-debt terms for auto-created CapitalModule(s).
    # {funder_type: {rate_pct, amort_years, loan_type, sizing_approach, ltv_pct, ...}}
    debt_terms: dict[str, dict] | None = None

    # Asset management fee as % of (NOI - debt service), deducted pre-waterfall
    asset_mgmt_fee_pct: Decimal | None = None

    # ── NOI mode inputs (used when Scenario.income_mode == 'noi') ───────
    noi_stabilized_input: Decimal | None = None
    noi_escalation_rate_pct: Decimal = Decimal("3")
    # Engine-owned: True when noi_stabilized_input was auto-seeded by the
    # KNN comp engine. In the Base for round-trip fidelity only — the
    # public inputs upsert route strips it (see models.py).
    noi_auto_seeded: bool = False

    # Affordable housing — enables AMI rent tier columns (deal-json-v3).
    affordable_housing_project: bool = False


class OperationalInputsCreate(OperationalInputsBase):
    project_id: uuid.UUID

    model_config = _example_config(
        {
            "project_id": _EXAMPLE_PROJECT_ID,
            "unit_count_existing": 12,
            "renovation_months": 4,
            "lease_up_months": 3,
            "expense_growth_rate_pct_annual": "3.0",
            "exit_cap_rate_pct": "5.5",
            "milestone_dates": {
                "construction_start": "2026-01-15",
                "construction_complete": "2026-07-15",
            },
        }
    )


class OperationalInputsRead(OperationalInputsBase):
    id: uuid.UUID
    project_id: uuid.UUID

    model_config = _example_config(
        {
            "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "project_id": _EXAMPLE_PROJECT_ID,
            "unit_count_existing": 12,
            "exit_cap_rate_pct": "5.5",
        },
        from_attributes=True,
    )


# ---------------------------------------------------------------------------
# IncomeStream
# ---------------------------------------------------------------------------

class IncomeStreamBase(BaseModel):
    stream_type: IncomeStreamType
    label: str
    unit_count: int | None = None
    amount_per_unit_monthly: Decimal | None = None
    amount_fixed_monthly: Decimal | None = None
    stabilized_occupancy_pct: Decimal = Decimal("95")
    bad_debt_pct: Decimal = Decimal("0")
    concessions_pct: Decimal = Decimal("0")
    renovation_absorption_rate: Decimal | None = None
    # Discrete capture schedule: [{year: 1, capture_pct: 0}, {year: 2, capture_pct: 50}, ...]
    renovation_capture_schedule: list[dict] | None = None
    escalation_rate_pct_annual: Decimal = Decimal("0")
    # LTL catchup: target rent to ramp toward (capped at LTL_CATCHUP_CAP_PCT/yr)
    catchup_target_rent: Decimal | None = None
    active_in_phases: list[str] = []
    notes: str | None = None


class IncomeStreamCreate(IncomeStreamBase):
    project_id: uuid.UUID

    _validate_label = field_validator("label")(_validate_label_not_reserved)

    model_config = _example_config(
        {
            "project_id": _EXAMPLE_PROJECT_ID,
            "stream_type": "residential_rent",
            "label": "Market Rent",
            "unit_count": 12,
            "amount_per_unit_monthly": "1650",
            "stabilized_occupancy_pct": "95",
            "escalation_rate_pct_annual": "2.5",
            "active_in_phases": ["lease_up", "stabilized", "exit"],
        }
    )


class IncomeStreamUpdate(BaseModel):
    stream_type: IncomeStreamType | None = None
    label: str | None = None
    unit_count: int | None = None
    amount_per_unit_monthly: Decimal | None = None
    amount_fixed_monthly: Decimal | None = None
    stabilized_occupancy_pct: Decimal | None = None
    escalation_rate_pct_annual: Decimal | None = None
    active_in_phases: list[str] | None = None
    notes: str | None = None

    _validate_label = field_validator("label")(_validate_label_not_reserved)

    model_config = _example_config(
        {
            "label": "Renovated Market Rent",
            "amount_per_unit_monthly": "1825",
            "escalation_rate_pct_annual": "3.0",
            "active_in_phases": ["lease_up", "stabilized", "exit"],
        }
    )


class IncomeStreamRead(IncomeStreamBase):
    id: uuid.UUID
    project_id: uuid.UUID

    model_config = _example_config(
        {
            "id": _EXAMPLE_STREAM_ID,
            "project_id": _EXAMPLE_PROJECT_ID,
            "stream_type": "residential_rent",
            "label": "Market Rent",
            "unit_count": 12,
            "amount_per_unit_monthly": "1650",
            "stabilized_occupancy_pct": "95",
            "escalation_rate_pct_annual": "2.5",
            "active_in_phases": ["lease_up", "stabilized", "exit"],
        },
        from_attributes=True,
    )


# ---------------------------------------------------------------------------
# OperatingExpenseLine
# ---------------------------------------------------------------------------

class OperatingExpenseLineBase(BaseModel):
    label: str
    annual_amount: Decimal = Decimal("0")
    per_value: Decimal | None = None
    per_type: str | None = None  # flat | per_unit | per_sqft_residential | per_sqft_commercial
    scale_with_lease_up: bool = False
    lease_up_floor_pct: Decimal | None = None
    escalation_rate_pct_annual: Decimal = Decimal("3")
    active_in_phases: list[str] = []
    notes: str | None = None


class OperatingExpenseLineCreate(OperatingExpenseLineBase):
    project_id: uuid.UUID

    _validate_label = field_validator("label")(_validate_label_not_reserved)

    model_config = _example_config(
        {
            "project_id": _EXAMPLE_PROJECT_ID,
            "label": "Utilities",
            "annual_amount": "3600",
            "escalation_rate_pct_annual": "3.0",
            "active_in_phases": ["lease_up", "stabilized", "exit"],
        }
    )


class OperatingExpenseLineUpdate(BaseModel):
    label: str | None = None
    annual_amount: Decimal | None = None
    per_value: Decimal | None = None
    per_type: str | None = None
    scale_with_lease_up: bool | None = None
    lease_up_floor_pct: Decimal | None = None
    escalation_rate_pct_annual: Decimal | None = None
    active_in_phases: list[str] | None = None
    notes: str | None = None

    _validate_label = field_validator("label")(_validate_label_not_reserved)

    model_config = _example_config(
        {
            "annual_amount": "4200",
            "escalation_rate_pct_annual": "3.5",
            "notes": "Includes common-area electric and water.",
        }
    )


class OperatingExpenseLineRead(OperatingExpenseLineBase):
    id: uuid.UUID
    project_id: uuid.UUID

    model_config = _example_config(
        {
            "id": _EXAMPLE_EXPENSE_LINE_ID,
            "project_id": _EXAMPLE_PROJECT_ID,
            "label": "Utilities",
            "annual_amount": "3600",
            "escalation_rate_pct_annual": "3.0",
            "active_in_phases": ["lease_up", "stabilized", "exit"],
        },
        from_attributes=True,
    )


# ---------------------------------------------------------------------------
# UseLine
# ---------------------------------------------------------------------------

_EXAMPLE_USE_LINE_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


# ---------------------------------------------------------------------------
# Dev Fee multi-source schemas (release schedule, binding context,
# use_line_source_fee_basis join). See docs/feature-plans/developer-fee-
# multi-source.md.
# ---------------------------------------------------------------------------


class DevFeeReleaseScheduleEntry(BaseModel):
    """One milestone weight in the Dev Fee release schedule."""

    milestone_id: uuid.UUID
    weight: Decimal


class DevFeeFinalHoldback(BaseModel):
    """Final holdback portion of the Dev Fee, released at a single milestone."""

    milestone_id: uuid.UUID
    pct: Decimal


class DevFeeReleaseScheduleSchema(BaseModel):
    """Milestone-weighted Dev Fee release schedule.

    Sum of all `weights[].weight` + `final_holdback.pct` must equal 1.0
    (validated at API write time and again in the engine before scheduling).
    Stored as JSONB on `use_lines.dev_fee_release_schedule`.
    """

    model_config = ConfigDict(extra="allow")

    weights: list[DevFeeReleaseScheduleEntry] = Field(default_factory=list)
    final_holdback: DevFeeFinalHoldback | None = None


class DevFeePerSourceAllocation(BaseModel):
    """One Source Vehicle's per-fee allowance + funded contribution."""

    capital_module_id: uuid.UUID
    vehicle_label: str | None = None
    allowable: Decimal | None = None
    funded_at_close: Decimal = Decimal("0")
    basis: Decimal | None = None


class PendingCustomUseDecision(BaseModel):
    """One unresolved (custom UseLine x constrained Vehicle) inclusion decision."""

    use_line_id: uuid.UUID
    capital_module_id: uuid.UUID


class DevFeeBindingContextSchema(BaseModel):
    """Engine-written display data for the Dev Fee row.

    Stored as JSONB on `use_lines.dev_fee_binding_context`. Read-only —
    never user-written. The explainer modal renders this directly.
    """

    model_config = ConfigDict(extra="allow")

    elected_fee: Decimal | None = None
    binding_source_id: uuid.UUID | None = None
    binding_dollar_cap: Decimal | None = None
    overage: Decimal = Decimal("0")
    per_source_allocation: list[DevFeePerSourceAllocation] = Field(default_factory=list)
    headroom_by_source: dict[str, Decimal] = Field(default_factory=dict)
    funded_at_close: Decimal = Decimal("0")
    deferred: Decimal = Decimal("0")
    release_schedule: list[dict] = Field(default_factory=list)
    last_compute_signature: str | None = None
    structural_diff_detected: bool = False
    structural_diff_delta: dict = Field(default_factory=dict)
    pending_custom_use_decisions: list[PendingCustomUseDecision] = Field(default_factory=list)
    acquisition_treatment: str | None = None
    # Acquisition Fee parallel block (when treatment="separate_fee").
    acquisition_fee_context: dict | None = None


class UseLineSourceFeeBasisSchema(BaseModel):
    """Per-(UseLine x CapitalModule) custom-Use inclusion decision."""

    use_line_id: uuid.UUID
    capital_module_id: uuid.UUID
    included_in_basis: bool


class UseLineBase(BaseModel):
    label: str
    phase: UseLinePhase | None = None
    # Phase B: milestone FK timing — preferred over phase string when set
    active_from_milestone_id: uuid.UUID | None = None
    spread_to_milestone_id: uuid.UUID | None = None
    amount: Decimal = Decimal("0")
    timing_type: str = "first_day"
    is_deferred: bool = False
    cost_category: str | None = None
    # Stamped at engine auto-create time. Round-trips through snapshot
    # revert + deal export/import so user renames of engine-created rows
    # don't lose their Dev Fee basis classification.
    dev_fee_basis_bucket: str | None = None
    notes: str | None = None
    # ── deal-json-v3 round-trip fields (mirror ORM UseLine) ──────────────
    # Source-Use eligibility routing: CapitalModule UUID whitelist. Restore
    # helpers remap these to the NEW module IDs on import/revert.
    eligible_module_ids: list[uuid.UUID] = Field(default_factory=list)
    # Engine-owned flags/blobs. In the Base for round-trip fidelity only —
    # the public create route strips them (see USE_LINE_ENGINE_OWNED_FIELDS
    # and models.py create_use_line); UseLineUpdate never exposes them.
    is_auto_dev_fee: bool = False
    is_auto_acquisition_fee: bool = False
    is_auto_finance_cost: bool = False
    # Engine-written display blob (binding source, headroom, allocations).
    dev_fee_binding_context: dict = Field(default_factory=dict)
    # Dev Fee multi-source config (auto Dev Fee row only).
    dev_fee_pct: Decimal | None = None
    dev_fee_basis: str | None = None
    # Kept as a raw dict (not DevFeeReleaseScheduleSchema) so engine-written
    # keys survive the round-trip. Contains milestone_ids — remapped by the
    # restore helpers on import/revert.
    dev_fee_release_schedule: dict = Field(default_factory=dict)
    dev_fee_acquisition_treatment: str | None = None
    dev_fee_acquisition_pct: Decimal | None = None
    # Auto Acquisition Fee row only.
    acquisition_fee_pct: Decimal | None = None


# Engine-owned UseLine fields that must never be writable through the public
# create/update API. They exist on UseLineBase purely so snapshot revert and
# deal-json export/import round-trip engine state without loss.
USE_LINE_ENGINE_OWNED_FIELDS: frozenset[str] = frozenset({
    "is_auto_dev_fee",
    "is_auto_acquisition_fee",
    "is_auto_finance_cost",
    "dev_fee_binding_context",
})


class UseLineCreate(UseLineBase):
    _validate_label = field_validator("label")(_validate_label_not_reserved)

    model_config = _example_config(
        {
            "label": "Land Acquisition",
            "phase": "acquisition",
            "amount": "1200000",
            "timing_type": "first_day",
            "is_deferred": False,
        }
    )


class UseLineUpdate(BaseModel):
    label: str | None = None
    phase: UseLinePhase | None = None
    active_from_milestone_id: uuid.UUID | None = None
    spread_to_milestone_id: uuid.UUID | None = None
    amount: Decimal | None = None
    timing_type: str | None = None
    is_deferred: bool | None = None
    notes: str | None = None
    # Dev Fee multi-source fields (auto Dev Fee row only).
    dev_fee_pct: Decimal | None = None
    dev_fee_basis: str | None = None
    dev_fee_release_schedule: DevFeeReleaseScheduleSchema | None = None
    dev_fee_acquisition_treatment: str | None = None
    dev_fee_acquisition_pct: Decimal | None = None
    # Auto Acquisition Fee row only.
    acquisition_fee_pct: Decimal | None = None

    _validate_label = field_validator("label")(_validate_label_not_reserved)

    model_config = _example_config({"amount": "1350000", "notes": "Revised after appraisal"})


class UseLineRead(UseLineBase):
    id: uuid.UUID
    project_id: uuid.UUID

    model_config = _example_config(
        {
            "id": _EXAMPLE_USE_LINE_ID,
            "project_id": _EXAMPLE_PROJECT_ID,
            "label": "Land Acquisition",
            "phase": "acquisition",
            "amount": "1200000",
            "is_deferred": False,
        },
        from_attributes=True,
    )


# ---------------------------------------------------------------------------
# UnitMix
# ---------------------------------------------------------------------------

class UnitMixBase(BaseModel):
    label: str
    unit_count: int = 1
    avg_sqft: Decimal | None = None
    beds: Decimal | None = None  # 0, 1, 2, 3, 4, 5+ (stored as numeric)
    baths: Decimal | None = None  # 0.5 increments: 0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5+
    market_rent_per_unit: Decimal | None = None
    in_place_rent_per_unit: Decimal | None = None
    unit_strategy: str | None = None  # "base_escalation" | "ltl_catchup" | "value_add_renovation"
    post_reno_rent_per_unit: Decimal | None = None
    notes: str | None = None


class UnitMixRead(UnitMixBase):
    id: uuid.UUID
    project_id: uuid.UUID

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# OperationalOutputs
# ---------------------------------------------------------------------------

class OperationalOutputsBase(BaseModel):
    total_project_cost: Decimal | None = None
    equity_required: Decimal | None = None
    total_timeline_months: int | None = None
    noi_stabilized: Decimal | None = None
    cap_rate_on_cost_pct: Decimal | None = None
    dscr: Decimal | None = None
    debt_yield_pct: Decimal | None = None
    project_irr_levered: Decimal | None = None
    project_irr_unlevered: Decimal | None = None
    sensitivity_matrix: dict | None = None
    computed_at: datetime | None = None


class OperationalOutputsCreate(OperationalOutputsBase):
    scenario_id: uuid.UUID


class OperationalOutputsRead(OperationalOutputsBase):
    id: uuid.UUID
    scenario_id: uuid.UUID

    model_config = _example_config(
        {
            "id": _EXAMPLE_OUTPUT_ID,
            "scenario_id": _EXAMPLE_SCENARIO_ID,
            "total_project_cost": "1450000",
            "equity_required": "400000",
            "total_timeline_months": 36,
            "noi_stabilized": "198000",
            "cap_rate_on_cost_pct": "6.2",
            "dscr": "1.45",
            "project_irr_levered": "15.7",
            "project_irr_unlevered": "11.9",
            "computed_at": _EXAMPLE_CREATED_AT,
        },
        from_attributes=True,
    )


# ---------------------------------------------------------------------------
# WorkflowRunManifest
# ---------------------------------------------------------------------------

class WorkflowRunManifestRead(BaseModel):
    id: uuid.UUID
    run_id: str
    scenario_id: uuid.UUID
    engine: str
    inputs_json: dict[str, Any] | None = None
    outputs_json: dict[str, Any] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# CashFlow
# ---------------------------------------------------------------------------

class CashFlowBase(BaseModel):
    period: int
    period_type: PeriodType
    gross_revenue: Decimal = Decimal("0")
    vacancy_loss: Decimal = Decimal("0")
    effective_gross_income: Decimal = Decimal("0")
    operating_expenses: Decimal = Decimal("0")
    capex_reserve: Decimal = Decimal("0")
    noi: Decimal = Decimal("0")
    debt_service: Decimal = Decimal("0")
    net_cash_flow: Decimal = Decimal("0")
    cumulative_cash_flow: Decimal = Decimal("0")


class CashFlowCreate(CashFlowBase):
    scenario_id: uuid.UUID


class CashFlowRead(CashFlowBase):
    id: uuid.UUID
    scenario_id: uuid.UUID

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# CashFlowLineItem
# ---------------------------------------------------------------------------

class CashFlowLineItemBase(BaseModel):
    period: int
    income_stream_id: uuid.UUID | None = None
    category: LineItemCategory
    label: str
    base_amount: Decimal = Decimal("0")
    adjustments: dict | None = None
    net_amount: Decimal = Decimal("0")


class CashFlowLineItemCreate(CashFlowLineItemBase):
    scenario_id: uuid.UUID


class CashFlowLineItemRead(CashFlowLineItemBase):
    id: uuid.UUID
    scenario_id: uuid.UUID

    model_config = {"from_attributes": True}
