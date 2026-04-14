"""Deal, Scenario, OperationalInputs, IncomeStream, CashFlow, OperationalOutputs schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict

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
# Scenario (financial plan for a Deal — was DealModel)
# ---------------------------------------------------------------------------

class ScenarioBase(BaseModel):
    name: str
    version: int = 1
    is_active: bool = True
    project_type: ProjectType


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
            "project_type": "acquisition_minor_reno",
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
            "project_type": "acquisition_minor_reno",
            "created_at": _EXAMPLE_CREATED_AT,
        },
        from_attributes=True,
    )


# Backward-compat aliases — old code importing DealModel* still works
DealModelBase = ScenarioBase
DealModelCreate = ScenarioCreate
DealModelRead = ScenarioRead


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

    # Deprecated OpEx scalars — use OperatingExpenseLine rows
    opex_per_unit_annual: Decimal = Decimal("0")
    expense_growth_rate_pct_annual: Decimal = Decimal("0")
    mgmt_fee_pct: Decimal = Decimal("0")
    property_tax_annual: Decimal = Decimal("0")
    insurance_annual: Decimal = Decimal("0")
    capex_reserve_per_unit_annual: Decimal = Decimal("0")

    hold_period_years: Decimal = Decimal("5")
    exit_cap_rate_pct: Decimal = Decimal("0")
    # Deprecated exit scalar — use UseLine with phase=exit
    selling_costs_pct: Decimal = Decimal("0")

    milestone_dates: dict[str, str] | None = None


class OperationalInputsCreate(OperationalInputsBase):
    project_id: uuid.UUID

    model_config = _example_config(
        {
            "project_id": _EXAMPLE_PROJECT_ID,
            "unit_count_existing": 12,
            "renovation_months": 4,
            "lease_up_months": 3,
            "expense_growth_rate_pct_annual": "3.0",
            "hold_period_years": "5",
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
            "hold_period_years": "5",
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
    escalation_rate_pct_annual: Decimal = Decimal("0")
    active_in_phases: list[str] = []
    notes: str | None = None


class IncomeStreamCreate(IncomeStreamBase):
    project_id: uuid.UUID

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


class UseLineBase(BaseModel):
    label: str
    phase: UseLinePhase
    amount: Decimal = Decimal("0")
    timing_type: str = "first_day"
    is_deferred: bool = False
    notes: str | None = None


class UseLineCreate(UseLineBase):
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
    amount: Decimal | None = None
    timing_type: str | None = None
    is_deferred: bool | None = None
    notes: str | None = None

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
# OperationalOutputs
# ---------------------------------------------------------------------------

class OperationalOutputsBase(BaseModel):
    total_project_cost: Decimal | None = None
    equity_required: Decimal | None = None
    total_timeline_months: int | None = None
    noi_stabilized: Decimal | None = None
    cap_rate_on_cost_pct: Decimal | None = None
    dscr: Decimal | None = None
    project_irr_levered: Decimal | None = None
    project_irr_unlevered: Decimal | None = None
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
