from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.schemas.capital import (
    CapitalModuleCreate,
    CapitalModuleRead,
    CapitalModuleUpdate,
    WaterfallDistributionReportRead,
    WaterfallTierCreate,
    WaterfallTierRead,
    WaterfallTierUpdate,
)
from app.schemas.deal import (
    DealModelCreate,
    DealModelRead,
    IncomeStreamCreate,
    IncomeStreamRead,
    IncomeStreamUpdate,
    OperatingExpenseLineCreate,
    OperatingExpenseLineRead,
    OperatingExpenseLineUpdate,
    OperationalInputsCreate,
    OperationalInputsRead,
    OperationalOutputsRead,
)
from app.schemas.project import ProjectCreate, ProjectRead

NOW = datetime(2026, 4, 3, 12, 0, tzinfo=UTC).isoformat()
PROJECT_ID = str(uuid4())
MODEL_ID = str(uuid4())
ORG_ID = str(uuid4())
USER_ID = str(uuid4())
CAPITAL_MODULE_ID = str(uuid4())
WATERFALL_TIER_ID = str(uuid4())

ROUND_TRIP_CASES: list[tuple[type, dict]] = [
    (
        ProjectCreate,
        {
            "name": "Contract Project",
            "org_id": ORG_ID,
            "created_by_user_id": USER_ID,
            "status": "active",
            "project_category": "proposed",
            "source": "manual",
        },
    ),
    (
        ProjectRead,
        {
            "id": PROJECT_ID,
            "name": "Contract Project",
            "org_id": ORG_ID,
            "created_by_user_id": USER_ID,
            "status": "active",
            "project_category": "proposed",
            "source": "manual",
            "created_at": NOW,
        },
    ),
    (
        DealModelCreate,
        {
            "deal_id": PROJECT_ID,
            "created_by_user_id": USER_ID,
            "name": "Contract Model",
            "version": 1,
            "is_active": True,
            "project_type": "acquisition",
        },
    ),
    (
        DealModelRead,
        {
            "id": MODEL_ID,
            "deal_id": PROJECT_ID,
            "created_by_user_id": USER_ID,
            "name": "Contract Model",
            "version": 1,
            "is_active": True,
            "project_type": "acquisition",
            "created_at": NOW,
        },
    ),
    (
        OperationalInputsCreate,
        {
            "project_id": MODEL_ID,
            "unit_count_existing": 12,
            "purchase_price": "1250000",
            "closing_costs_pct": "2.0",
            "renovation_cost_total": "150000",
            "renovation_months": 4,
            "lease_up_months": 3,
            "opex_per_unit_annual": "3600",
            "expense_growth_rate_pct_annual": "3.0",
            "mgmt_fee_pct": "4.0",
            "property_tax_annual": "12000",
            "insurance_annual": "2400",
            "capex_reserve_per_unit_annual": "250",
            "exit_cap_rate_pct": "5.5",
            "selling_costs_pct": "2.0",
            "milestone_dates": {
                "construction_start": "2026-01-15",
                "construction_complete": "2026-07-15",
            },
        },
    ),
    (
        OperationalInputsRead,
        {
            "id": str(uuid4()),
            "project_id": MODEL_ID,
            "unit_count_existing": 12,
            "purchase_price": "1250000",
            "closing_costs_pct": "2.0",
            "exit_cap_rate_pct": "5.5",
            "selling_costs_pct": "2.0",
        },
    ),
    (
        IncomeStreamCreate,
        {
            "project_id": MODEL_ID,
            "stream_type": "residential_rent",
            "label": "Market Rent",
            "unit_count": 12,
            "amount_per_unit_monthly": "1650",
            "stabilized_occupancy_pct": "95",
            "escalation_rate_pct_annual": "2.5",
            "active_in_phases": ["lease_up", "stabilized", "exit"],
        },
    ),
    (
        IncomeStreamRead,
        {
            "id": str(uuid4()),
            "project_id": MODEL_ID,
            "stream_type": "residential_rent",
            "label": "Market Rent",
            "unit_count": 12,
            "amount_per_unit_monthly": "1650",
            "stabilized_occupancy_pct": "95",
            "escalation_rate_pct_annual": "2.5",
            "active_in_phases": ["lease_up", "stabilized", "exit"],
        },
    ),
    (
        OperatingExpenseLineCreate,
        {
            "project_id": MODEL_ID,
            "label": "Utilities",
            "annual_amount": "3600",
            "escalation_rate_pct_annual": "3.0",
            "active_in_phases": ["lease_up", "stabilized", "exit"],
        },
    ),
    (
        OperatingExpenseLineRead,
        {
            "id": str(uuid4()),
            "project_id": MODEL_ID,
            "label": "Utilities",
            "annual_amount": "3600",
            "escalation_rate_pct_annual": "3.0",
            "active_in_phases": ["lease_up", "stabilized", "exit"],
        },
    ),
    (
        CapitalModuleCreate,
        {
            "scenario_id": MODEL_ID,
            "label": "Senior Loan",
            "funder_type": "debt",
            "stack_position": 1,
            "source": {
                "amount": "850000",
                "interest_rate_pct": 6.5,
                "funding_date_trigger": "construction_start",
            },
            "carry": {
                "carry_type": "io_only",
                "io_period_months": 12,
                "payment_frequency": "monthly",
                "capitalized": False,
            },
            "exit_terms": {
                "exit_type": "full_payoff",
                "trigger": "sale",
                "notes": "Pay off at disposition",
            },
            "active_phase_start": "acquisition",
            "active_phase_end": "exit",
        },
    ),
    (
        CapitalModuleRead,
        {
            "id": CAPITAL_MODULE_ID,
            "scenario_id": MODEL_ID,
            "label": "Senior Loan",
            "funder_type": "debt",
            "stack_position": 1,
            "source": {"amount": "850000", "interest_rate_pct": 6.5},
            "carry": {"carry_type": "io_only", "payment_frequency": "monthly", "capitalized": False},
            "exit_terms": {"exit_type": "full_payoff", "trigger": "sale"},
            "active_phase_start": "acquisition",
            "active_phase_end": "exit",
            "created_at": NOW,
        },
    ),
    (
        WaterfallTierCreate,
        {
            "scenario_id": MODEL_ID,
            "capital_module_id": CAPITAL_MODULE_ID,
            "priority": 1,
            "tier_type": "return_of_equity",
            "irr_hurdle_pct": "8.0",
            "lp_split_pct": "90",
            "gp_split_pct": "10",
            "description": "Return sponsor equity first",
        },
    ),
    (
        WaterfallTierRead,
        {
            "id": WATERFALL_TIER_ID,
            "scenario_id": MODEL_ID,
            "capital_module_id": CAPITAL_MODULE_ID,
            "priority": 1,
            "tier_type": "return_of_equity",
            "irr_hurdle_pct": "8.0",
            "lp_split_pct": "90",
            "gp_split_pct": "10",
            "description": "Return sponsor equity first",
        },
    ),
    (
        OperationalOutputsRead,
        {
            "id": str(uuid4()),
            "scenario_id": MODEL_ID,
            "total_project_cost": "1450000",
            "equity_required": "400000",
            "total_timeline_months": 36,
            "noi_stabilized": "198000",
            "cap_rate_on_cost_pct": "6.2",
            "dscr": "1.45",
            "project_irr_levered": "15.7",
            "project_irr_unlevered": "11.9",
            "computed_at": NOW,
        },
    ),
    (
        WaterfallDistributionReportRead,
        {
            "scenario_id": MODEL_ID,
            "investor_count": 1,
            "total_cash_distributed": "27000",
            "investors": [
                {
                    "capital_module_id": CAPITAL_MODULE_ID,
                    "investor_name": "LP Equity",
                    "funder_type": "common_equity",
                    "stack_position": 1,
                    "committed_capital": "40000",
                    "total_cash_distributed": "27000",
                    "ending_cumulative_distributed": "27000",
                    "latest_party_irr_pct": "14.2",
                    "equity_multiple": "0.675",
                    "cash_on_cash_year_1_pct": "50.0",
                    "share_of_total_distributions_pct": "100.0",
                    "timeline": [
                        {
                            "period": 1,
                            "cash_distributed": "5000",
                            "cumulative_distributed": "5000",
                        }
                    ],
                }
            ],
        },
    ),
]


@pytest.mark.parametrize(
    ("schema_cls", "payload"),
    ROUND_TRIP_CASES,
    ids=[schema_cls.__name__ for schema_cls, _ in ROUND_TRIP_CASES],
)
def test_public_schema_round_trip_stays_json_stable(schema_cls: type, payload: dict) -> None:
    parsed = schema_cls.model_validate(payload)
    round_tripped = schema_cls.model_validate_json(parsed.model_dump_json())

    assert round_tripped.model_dump(mode="json") == parsed.model_dump(mode="json")


def test_contract_payload_examples_keep_expected_decimal_strings() -> None:
    outputs = OperationalOutputsRead.model_validate(
        {
            "id": str(uuid4()),
            "scenario_id": MODEL_ID,
            "total_project_cost": Decimal("1450000"),
            "project_irr_levered": Decimal("15.7"),
        }
    )

    dumped = outputs.model_dump(mode="json")

    assert dumped["total_project_cost"] == "1450000"
    assert dumped["project_irr_levered"] == "15.7"


@pytest.mark.parametrize(
    ("schema_cls",),
    [
        (ProjectCreate,),
        (ProjectRead,),
        (DealModelCreate,),
        (DealModelRead,),
        (OperationalInputsCreate,),
        (OperationalInputsRead,),
        (IncomeStreamCreate,),
        (IncomeStreamUpdate,),
        (IncomeStreamRead,),
        (OperatingExpenseLineCreate,),
        (OperatingExpenseLineUpdate,),
        (OperatingExpenseLineRead,),
        (CapitalModuleCreate,),
        (CapitalModuleUpdate,),
        (CapitalModuleRead,),
        (WaterfallTierCreate,),
        (WaterfallTierUpdate,),
        (WaterfallTierRead,),
        (OperationalOutputsRead,),
        (WaterfallDistributionReportRead,),
    ],
    ids=lambda value: value.__name__,
)
def test_public_schemas_publish_examples_for_create_update_read_operations(schema_cls: type) -> None:
    schema = schema_cls.model_json_schema()
    examples = schema.get("examples")

    assert examples, f"{schema_cls.__name__} should publish at least one example payload"
