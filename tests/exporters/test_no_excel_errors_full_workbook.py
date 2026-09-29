"""Full-workbook Excel-error scan: after recalc, no cell on any sheet
may carry an Excel error sentinel (``#NAME?``, ``#REF!``, ``#DIV/0!``,
etc.). Catches the class of bug that bit the proforma profile —
formulas referencing names that don't exist, ranges that resolve to
the wrong type, etc. — even when those cells aren't on the parity
test's specific check-list.

Scope: internal profile only. The internal profile renders every
sheet (UW Summary, UW Pro Forma, UW Cash Flow, S&U, Investor Returns,
Waterfall, Unit Mix, Debt Schedule, Assumptions, Sensitivity,
Glossary), so a clean run there proves the named-range graph is
intact for the deliverable LPs actually receive. Other profiles
(lp, lender, proforma) ship a subset of sheets; if they regress
later we can parametrize.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
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
from tests.exporters._parity_helpers import (
    RecalcUnavailableError,
    find_error_cells,
    recalc_workbook,
)


async def _seed_full_scenario(session: AsyncSession):
    """Seed scenario rich enough to exercise the major formula paths:
    debt + equity capital modules wired to the project, then run
    compute_cash_flows so CashFlow / OperationalOutputs rows exist."""
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(
        session, org, user, name="Full-Workbook Error Scan"
    )
    deal_model, _, _, _ = await seed_deal_model_with_financials(
        session, opportunity, user
    )
    project_row = (
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
            capital_module_id=debt.id, project_id=project_row.id,
            amount=Decimal("500000"),
        ),
        CapitalModuleProject(
            capital_module_id=equity.id, project_id=project_row.id,
            amount=Decimal("250000"),
        ),
    ])
    await session.flush()
    await compute_cash_flows(deal_model.id, session)
    await session.commit()
    return deal_model


async def test_internal_profile_has_no_excel_errors_after_recalc(
    session: AsyncSession, tmp_path: Path,
):
    """Export, recalc, walk every cell on every sheet, assert nothing
    resolved to an Excel error sentinel."""
    scenario = await _seed_full_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    try:
        recalc_workbook(path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend available: {exc}")

    errors = find_error_cells(path)
    assert not errors, (
        "post-recalc workbook has Excel error cells:\n"
        + "\n".join(f"  {s}!{c} = {v}" for s, c, v in errors[:20])
        + (f"\n  ... and {len(errors) - 20} more" if len(errors) > 20 else "")
    )


async def test_proforma_profile_has_no_excel_errors_after_recalc(
    session: AsyncSession, tmp_path: Path,
):
    """Same full-workbook scan against the proforma profile. Guards the
    fix for the dangling ``s_module_*_principal`` reference shipped in
    ``597f4ae`` so future profile-set changes can't silently re-break
    it."""
    scenario = await _seed_full_scenario(session)
    blob = await export_investor_workbook(
        scenario.id, session, profile="proforma",
    )
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    try:
        recalc_workbook(path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend available: {exc}")

    errors = find_error_cells(path)
    assert not errors, (
        "post-recalc proforma workbook has Excel error cells:\n"
        + "\n".join(f"  {s}!{c} = {v}" for s, c, v in errors[:20])
        + (f"\n  ... and {len(errors) - 20} more" if len(errors) > 20 else "")
    )
