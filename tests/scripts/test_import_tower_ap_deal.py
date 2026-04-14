from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from vicinitideals.models import Base  # imports all ORM models, enabling create_all


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_import_tower_ap_deal_creates_two_projects_and_one_portfolio(
    tmp_path: Path,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    formulas = {
        "organization": {"name": "Import Test Org", "slug": "import-test-org"},
        "portfolio_name": "Tower + A&P Portfolio",
        "projects": [
            {
                "project": {"name": "Tower", "status": "active", "project_category": "historical", "source": "manual"},
                "deal_model": {"name": "Tower", "project_type": "acquisition_minor_reno"},
                "operational_inputs": {
                    "purchase_price": 1000000,
                    "closing_costs_pct": 2.0,
                    "renovation_cost_total": 120000,
                    "renovation_months": 4,
                    "lease_up_months": 3,
                    "unit_count_existing": 10,
                    "opex_per_unit_annual": 4200,
                    "expense_growth_rate_pct_annual": 2.5,
                    "mgmt_fee_pct": 4.0,
                    "property_tax_annual": 18000,
                    "insurance_annual": 6000,
                    "capex_reserve_per_unit_annual": 300,
                    "hold_period_years": 5,
                    "exit_cap_rate_pct": 5.5,
                    "selling_costs_pct": 2.0
                },
                "income_streams": [
                    {
                        "stream_type": "residential_rent",
                        "label": "Tower Residential",
                        "unit_count": 10,
                        "amount_per_unit_monthly": 1750,
                        "stabilized_occupancy_pct": 95,
                        "escalation_rate_pct_annual": 2.0,
                        "active_in_phases": ["lease_up", "stabilized", "exit"]
                    }
                ],
                "capital_modules": [
                    {
                        "label": "Tower Senior Loan",
                        "funder_type": "senior_debt",
                        "stack_position": 1,
                        "source": {"amount": 800000, "interest_rate_pct": 6.0},
                        "carry": {"carry_type": "io_only", "payment_frequency": "monthly"},
                        "exit_terms": {"exit_type": "full_payoff", "trigger": "sale"},
                        "active_phase_start": "acquisition",
                        "active_phase_end": "exit"
                    },
                    {
                        "label": "Tower Common Equity",
                        "funder_type": "common_equity",
                        "stack_position": 2,
                        "source": {"pct_of_total_cost": 100},
                        "carry": {"carry_type": "none", "payment_frequency": "at_exit"},
                        "exit_terms": {"exit_type": "profit_share", "trigger": "sale", "profit_share_pct": 100},
                        "active_phase_start": "acquisition",
                        "active_phase_end": "exit"
                    }
                ],
                "waterfall_tiers": [
                    {"priority": 1, "tier_type": "debt_service", "description": "Debt service", "capital_module_label": "Tower Senior Loan"},
                    {"priority": 2, "tier_type": "return_of_equity", "lp_split_pct": 100, "gp_split_pct": 0, "description": "Return LP capital"},
                    {"priority": 3, "tier_type": "residual", "lp_split_pct": 90, "gp_split_pct": 10, "description": "Residual split"}
                ]
            },
            {
                "project": {"name": "A&P", "status": "active", "project_category": "historical", "source": "manual"},
                "deal_model": {"name": "A&P", "project_type": "acquisition_conversion"},
                "operational_inputs": {
                    "purchase_price": 900000,
                    "closing_costs_pct": 1.5,
                    "hold_phase_enabled": True,
                    "hold_months": 2,
                    "entitlement_months": 3,
                    "entitlement_cost": 45000,
                    "construction_months": 6,
                    "conversion_cost_per_unit": 40000,
                    "unit_count_existing": 8,
                    "unit_count_after_conversion": 12,
                    "lease_up_months": 4,
                    "initial_occupancy_pct": 50,
                    "opex_per_unit_annual": 3900,
                    "expense_growth_rate_pct_annual": 2.0,
                    "mgmt_fee_pct": 3.5,
                    "property_tax_annual": 15000,
                    "insurance_annual": 5200,
                    "capex_reserve_per_unit_annual": 275,
                    "hold_period_years": 4,
                    "exit_cap_rate_pct": 5.75,
                    "selling_costs_pct": 2.25
                },
                "income_streams": [
                    {
                        "stream_type": "residential_rent",
                        "label": "A&P Residential",
                        "unit_count": 12,
                        "amount_per_unit_monthly": 1650,
                        "stabilized_occupancy_pct": 94,
                        "escalation_rate_pct_annual": 2.0,
                        "active_in_phases": ["lease_up", "stabilized", "exit"]
                    }
                ],
                "capital_modules": [
                    {
                        "label": "A&P Senior Loan",
                        "funder_type": "senior_debt",
                        "stack_position": 1,
                        "source": {"amount": 700000, "interest_rate_pct": 6.25},
                        "carry": {"carry_type": "io_only", "payment_frequency": "monthly"},
                        "exit_terms": {"exit_type": "full_payoff", "trigger": "sale"},
                        "active_phase_start": "acquisition",
                        "active_phase_end": "exit"
                    },
                    {
                        "label": "A&P Common Equity",
                        "funder_type": "common_equity",
                        "stack_position": 2,
                        "source": {"pct_of_total_cost": 100},
                        "carry": {"carry_type": "none", "payment_frequency": "at_exit"},
                        "exit_terms": {"exit_type": "profit_share", "trigger": "sale", "profit_share_pct": 100},
                        "active_phase_start": "acquisition",
                        "active_phase_end": "exit"
                    }
                ],
                "waterfall_tiers": [
                    {"priority": 1, "tier_type": "debt_service", "description": "Debt service", "capital_module_label": "A&P Senior Loan"},
                    {"priority": 2, "tier_type": "return_of_equity", "lp_split_pct": 100, "gp_split_pct": 0, "description": "Return LP capital"},
                    {"priority": 3, "tier_type": "residual", "lp_split_pct": 85, "gp_split_pct": 15, "description": "Residual split"}
                ]
            }
        ]
    }
    formulas_path = tmp_path / "formulas.json"
    formulas_path.write_text(json.dumps(formulas), encoding="utf-8")

    from vicinitideals.scripts.import_tower_ap_deal import import_tower_ap_deal

    async with session_factory() as session:
        summary = await import_tower_ap_deal(formulas_path, session=session)

    assert summary["portfolio"]["name"] == "Tower + A&P Portfolio"
    assert {project["name"] for project in summary["projects"]} == {"Tower", "A&P"}
    for project in summary["projects"]:
        assert project["cashflow"]["cash_flow_count"] > 0
        assert project["waterfall"]["waterfall_result_count"] > 0
