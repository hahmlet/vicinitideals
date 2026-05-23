"""Phase B: Operating Expenses + CapEx Reserve grow via a chain formula
that multiplies the prior year by ``(1 + s_opex_growth_rate)``. Y0 and
Y1 stay engine-driven (the seed); Y2..Y_n become formulas so a single
edit to the Assumptions ``OpEx Growth Rate (annual)`` cell ripples
through every downstream year — and through NOI/Net Cash Flow because
those are already derived formulas referencing OpEx.

Guards two distinct codepaths:

  - ``_build_uw_proforma`` (internal/lp/lender profiles) — Underwriting
    Pro Forma sheet
  - ``_write_pf_table`` (proforma profile) — Pro Forma sheet shared by
    ``_build_proforma_combined`` and ``_build_proforma_project_sheet``
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO

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
    Y2+ growth chain has cells to inspect. Mirrors the full-workbook
    error-scan fixture."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="Phase B Growth Chain")
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


def _find_row(ws, label_prefix: str) -> int | None:
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and v.startswith(label_prefix):
            return r
    return None


def _assert_growth_chain(ws, row: int, growth_name: str) -> None:
    """Y2 onward must be ``=<prev_col><row>*(1+<growth_name>)``."""
    # Y0 is column B (col 2), Y1 is C, Y2 is D, ...
    chain_started = False
    for c in range(4, ws.max_column + 1):  # start at Y2 (col D)
        v = ws.cell(row=row, column=c).value
        if v is None:
            break
        assert isinstance(v, str) and v.startswith("="), (
            f"row {row} col {c} expected formula; got {v!r}"
        )
        assert growth_name in v, (
            f"row {row} col {c} expected growth chain referencing "
            f"{growth_name!r}; got {v!r}"
        )
        chain_started = True
    assert chain_started, (
        f"row {row} has no Y2+ cells — workbook has too few years to "
        f"exercise the growth chain"
    )


# ── Internal profile: Underwriting Pro Forma ─────────────────────────────────


async def test_uw_proforma_opex_grows_via_chain(session: AsyncSession):
    """Internal-profile Underwriting Pro Forma OpEx Y2+ = chain formula."""
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    ws = wb["Underwriting Pro Forma"]

    opex_row = _find_row(ws, "Operating Expenses")
    assert opex_row is not None, "Operating Expenses row not found"

    _assert_growth_chain(ws, opex_row, "s_opex_growth_rate")


async def test_uw_proforma_capex_grows_via_chain(session: AsyncSession):
    """Internal-profile UW Pro Forma CapEx Reserve Y2+ = chain formula."""
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    ws = wb["Underwriting Pro Forma"]

    capex_row = _find_row(ws, "CapEx Reserve")
    assert capex_row is not None, "CapEx Reserve row not found"

    _assert_growth_chain(ws, capex_row, "s_opex_growth_rate")


# ── Proforma profile: Pro Forma sheet ─────────────────────────────────────────


async def test_proforma_opex_grows_via_chain(session: AsyncSession):
    """Proforma-profile Pro Forma OpEx Y2+ = chain formula."""
    scenario = await _seed(session)
    blob = await export_investor_workbook(
        scenario.id, session, profile="proforma",
    )
    wb = load_workbook(BytesIO(blob), data_only=False)
    ws = wb["Pro Forma"]

    opex_row = _find_row(ws, "Operating Expenses")
    assert opex_row is not None

    _assert_growth_chain(ws, opex_row, "s_opex_growth_rate")


async def test_proforma_capex_grows_via_chain(session: AsyncSession):
    """Proforma-profile Pro Forma CapEx Reserve Y2+ = chain formula."""
    scenario = await _seed(session)
    blob = await export_investor_workbook(
        scenario.id, session, profile="proforma",
    )
    wb = load_workbook(BytesIO(blob), data_only=False)
    ws = wb["Pro Forma"]

    capex_row = _find_row(ws, "CapEx Reserve")
    assert capex_row is not None

    _assert_growth_chain(ws, capex_row, "s_opex_growth_rate")


# ── OER row picks up OpEx changes ────────────────────────────────────────────


async def test_uw_proforma_oer_is_formula(session: AsyncSession):
    """OER row references the OpEx + EGI cells so growth-chain edits flow."""
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    ws = wb["Underwriting Pro Forma"]

    oer_row = _find_row(ws, "OER (OpEx")
    assert oer_row is not None, "OER row not found"

    formula_count = 0
    for c in range(2, ws.max_column + 1):
        v = ws.cell(row=oer_row, column=c).value
        if v is None:
            break
        assert isinstance(v, str) and v.startswith("="), (
            f"OER col {c} expected formula; got {v!r}"
        )
        assert "IFERROR" in v, f"OER col {c} should be IFERROR-guarded; got {v!r}"
        formula_count += 1
    assert formula_count > 0


async def test_proforma_oer_is_formula(session: AsyncSession):
    """Proforma profile OER row likewise references the OpEx + EGI cells."""
    scenario = await _seed(session)
    blob = await export_investor_workbook(
        scenario.id, session, profile="proforma",
    )
    wb = load_workbook(BytesIO(blob), data_only=False)
    ws = wb["Pro Forma"]

    oer_row = _find_row(ws, "OER (OpEx")
    assert oer_row is not None

    formula_count = 0
    for c in range(2, ws.max_column + 1):
        v = ws.cell(row=oer_row, column=c).value
        if v is None:
            break
        assert isinstance(v, str) and v.startswith("="), (
            f"OER col {c} expected formula; got {v!r}"
        )
        assert "IFERROR" in v
        formula_count += 1
    assert formula_count > 0
