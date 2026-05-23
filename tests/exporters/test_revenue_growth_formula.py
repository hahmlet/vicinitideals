"""Phase A: Gross Revenue Y2+ on Pro Forma sheets must be a growth-chain formula
``=prev_year_cell * (1 + s_revenue_growth_rate)``.

Mirrors the OpEx / CapEx Reserve growth-chain contract established in Phase B
so a single LP edit to the Revenue Growth Rate Assumption ripples through
every downstream year on the pro forma. Y0/Y1 stay as engine-computed seed
values; Y2+ become formulas.

Guards three contracts:

  1. ``s_revenue_growth_rate`` named range is registered on the Assumptions
     sheet (so the formula isn't dangling).
  2. The Gross Revenue Y2+ cell is a formula referencing
     ``s_revenue_growth_rate`` and the prior-year cell.
  3. Y0 + Y1 stay numeric (engine-seeded) so the chain has a base value.
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import compute_cash_flows
from app.exporters.investor_export import export_investor_workbook
from app.models.capital import (
    CapitalModule,
    CapitalModuleProject,
    EquityRole,
    VehicleType,
)
from app.models.project import Project
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)


async def _seed(session: AsyncSession):
    """Seed a scenario rich enough to produce >= 3 annual columns so the
    Y2+ revenue growth chain has cells to inspect."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="Revenue Growth Smoke")
    deal_model, _, _, _ = await seed_deal_model_with_financials(
        session, opp, user
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    debt = CapitalModule(
        scenario_id=deal_model.id,
        label="Senior Loan",
        vehicle_type=VehicleType.debt.value,
        stack_position=1,
        source={
            "amount": "500000", "interest_rate_pct": 6.5,
            "amort_term_years": 30, "hold_term_years": 10,
        },
        carry={"carry_type": "pi", "payment_frequency": "monthly"},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="acquisition", active_phase_end="exit",
    )
    equity = CapitalModule(
        scenario_id=deal_model.id,
        label="LP Equity",
        vehicle_type=VehicleType.equity.value,
        equity_role=EquityRole.lp.value,
        stack_position=2,
        source={"amount": "250000"},
        carry={"carry_type": "none", "payment_frequency": "monthly"},
        exit_terms={"exit_type": "full_payoff", "trigger": "sale"},
        active_phase_start="acquisition", active_phase_end="exit",
    )
    session.add_all([debt, equity])
    await session.flush()
    session.add_all([
        CapitalModuleProject(
            capital_module_id=debt.id, project_id=project.id,
            amount=Decimal("500000"),
        ),
        CapitalModuleProject(
            capital_module_id=equity.id, project_id=project.id,
            amount=Decimal("250000"),
        ),
    ])
    await session.flush()
    await compute_cash_flows(deal_model.id, session)
    await session.commit()
    return deal_model


def _find_row(ws, label_substr: str) -> int | None:
    needle = label_substr.lower()
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and needle in v.lower():
            return r
    return None


def _find_pro_forma_sheet(wb):
    for name in wb.sheetnames:
        low = name.lower()
        if "pro forma" in low or "proforma" in low:
            return wb[name]
    return None


@pytest.mark.parametrize("profile", ["internal", "lp", "lender", "proforma"])
async def test_revenue_growth_named_range_registered(
    session: AsyncSession, profile: str
):
    """``s_revenue_growth_rate`` must be defined on every profile that
    ships the Pro Forma sheet, or the Y2+ formulas would dangle to #NAME?."""
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session, profile=profile)
    wb = load_workbook(BytesIO(blob), data_only=False)
    assert "s_revenue_growth_rate" in wb.defined_names, (
        f"profile={profile} missing s_revenue_growth_rate defined name"
    )


@pytest.mark.parametrize("profile", ["internal", "lp", "lender", "proforma"])
async def test_gross_revenue_y2_plus_is_growth_formula(
    session: AsyncSession, profile: str
):
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session, profile=profile)
    wb = load_workbook(BytesIO(blob), data_only=False)

    ws = _find_pro_forma_sheet(wb)
    assert ws is not None, f"profile={profile} missing Pro Forma sheet"

    gr_row = _find_row(ws, "gross revenue")
    assert gr_row is not None, (
        f"profile={profile} missing Gross Revenue row on Pro Forma sheet"
    )

    # Y0=col B, Y1=col C, Y2=col D (first growth-chain year).
    y2 = ws.cell(row=gr_row, column=4).value
    assert isinstance(y2, str) and y2.startswith("="), (
        f"profile={profile}: Gross Revenue Y2 must be formula; got {y2!r}"
    )
    assert "s_revenue_growth_rate" in y2, (
        f"profile={profile}: Y2 formula missing s_revenue_growth_rate ref; got {y2!r}"
    )
    # Prior-year cell ref: same row, col C (Y1).
    assert f"C{gr_row}" in y2, (
        f"profile={profile}: Y2 formula must reference prior-year cell C{gr_row}; "
        f"got {y2!r}"
    )


@pytest.mark.parametrize("profile", ["internal", "lp", "lender", "proforma"])
async def test_gross_revenue_y0_y1_remain_numeric_seeds(
    session: AsyncSession, profile: str
):
    """Growth chain needs a numeric base. Y0+Y1 must stay engine-seeded."""
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session, profile=profile)
    wb = load_workbook(BytesIO(blob), data_only=False)

    ws = _find_pro_forma_sheet(wb)
    assert ws is not None

    gr_row = _find_row(ws, "gross revenue")
    assert gr_row is not None

    y0 = ws.cell(row=gr_row, column=2).value
    y1 = ws.cell(row=gr_row, column=3).value
    for label, val in (("Y0", y0), ("Y1", y1)):
        assert not (isinstance(val, str) and val.startswith("=")), (
            f"profile={profile}: Gross Revenue {label} must be numeric seed, "
            f"got formula {val!r}"
        )
