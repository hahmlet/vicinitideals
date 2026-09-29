"""Engine-vs-formula parity for the Combined Equity Multiple cells on
UW Summary and Investor Returns. Verifies the new SUMIF-over-
``r_uw_cf_levered`` formula evaluates to a sensible value post-recalc
and is in the same ballpark as the engine's ``combined_em_x``.

Skips when no recalc backend (Excel COM / LibreOffice) is available —
matches the gating used by ``test_formula_parity_returns``.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import compute_cash_flows
from app.exporters.investor_export import (
    _load_all,
    export_investor_workbook,
)
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
from tests.exporters._parity_seeds import (
    engine_annual_ncf,
    seed_all_equity_acquisition,
)
from tests.exporters._parity_helpers import (
    RecalcUnavailableError,
    recalc_workbook,
)


async def _seed(session: AsyncSession):
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="EM Parity")
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
        carry={"carry_type": "io_only", "payment_frequency": "monthly"},
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


def _find(ws, needle: str) -> int | None:
    n = needle.lower()
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and n in v.lower():
            return r
    return None


async def test_combined_em_evaluates_in_sane_range(
    session: AsyncSession, tmp_path: Path
):
    """Post-recalc, the EM formula returns a numeric ≥0 (or 0 from IFERROR).
    EM is typically 1.0–5.0× for a healthy deal; we widen the band to
    avoid coupling to the seed's specific numbers."""
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session, profile="internal")
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)
    try:
        recalc_workbook(path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend: {exc}")

    wb = load_workbook(path, data_only=True)
    for sheet, label in (
        ("Underwriting Summary", "combined equity multiple"),
        ("Investor Returns", "combined equity multiple (scenario)"),
    ):
        ws = wb[sheet]
        r = _find(ws, label)
        assert r is not None, f"{sheet}: row missing"
        val = ws.cell(row=r, column=2).value
        if val is None:
            pytest.fail(
                f"{sheet}: EM cell empty after recalc -- the recalc "
                f"engine did not evaluate it"
            )
        assert isinstance(val, (int, float)), (
            f"{sheet}: EM not numeric post-recalc; got {val!r}"
        )
        assert 0.0 <= float(val) <= 50.0, (
            f"{sheet}: EM out of sane range; got {val}"
        )


async def test_property_valuation_formulas_evaluate(
    session: AsyncSession, tmp_path: Path
):
    """Going-In Cap Value, Exit Cap Value, Cap Spread post-recalc all
    evaluate to numerics (or empty string when IFERROR fires on missing
    cap input)."""
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session, profile="internal")
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)
    try:
        recalc_workbook(path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend: {exc}")

    wb = load_workbook(path, data_only=True)
    ws = wb["Underwriting Summary"]
    for label in (
        "going-in cap value",
        "exit cap value",
        "cap spread",
    ):
        r = _find(ws, label)
        assert r is not None, f"row missing: {label}"
        val = ws.cell(row=r, column=2).value
        # Accept numeric or "" (IFERROR-empty when cap input is 0/missing).
        assert val is None or isinstance(val, (int, float, str)), (
            f"{label!r}: unexpected type post-recalc: {val!r}"
        )
        if isinstance(val, str) and val and val.startswith("="):
            pytest.fail(
                f"{label!r}: formula not evaluated; recalc backend may "
                f"have skipped this sheet ({val!r})"
            )


async def test_em_parity_within_band(
    session: AsyncSession, tmp_path: Path
):
    """On an all-equity $800k acquisition (tests/exporters/_parity_seeds.py),
    the recalc'd Combined Equity Multiple equals

      1. the same SUMIF(>0) / -SUMIF(<0) over the engine's net_cash_flow
         summed into the workbook's year buckets (like with like), and
      2. the engine's own combined_em_x (monthly series) within 0.05x --
         annual bucketing nets a year's mixed-sign months before the
         ratio is taken, which moves it slightly.
    """
    scenario = await seed_all_equity_acquisition(session, name="EM Parity")
    ctx = await _load_all(session, scenario.id)
    engine_em = float(
        (ctx.get("rollup_summary") or {}).get("totals", {}).get("combined_em_x") or 0
    )
    annual = engine_annual_ncf(ctx)
    assert annual[0] < 0, f"seed must invest equity at Y0; got {annual[0]}"
    assert engine_em > 1.0, f"engine EM should be a real multiple; got {engine_em}"
    annual_em = sum(x for x in annual if x > 0) / -sum(x for x in annual if x < 0)

    blob = await export_investor_workbook(scenario.id, session, profile="internal")
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)
    try:
        recalc_workbook(path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend: {exc}")

    wb = load_workbook(path, data_only=True)
    for sheet, label in (
        ("Underwriting Summary", "combined equity multiple"),
        ("Investor Returns", "combined equity multiple (scenario)"),
    ):
        ws = wb[sheet]
        r = _find(ws, label)
        assert r is not None, f"{sheet}: row missing"
        excel_em = ws.cell(row=r, column=2).value
        assert isinstance(excel_em, (int, float)), (
            f"{sheet}: EM did not evaluate to a number: {excel_em!r}"
        )
        assert abs(float(excel_em) - annual_em) < 1e-4, (
            f"{sheet}: EM {excel_em} != EM of the engine's annual NCF "
            f"{annual_em} -- the formula reads the wrong stream"
        )
        assert abs(float(excel_em) - engine_em) < 0.05, (
            f"{sheet}: EM parity: engine={engine_em}x, excel={excel_em}x"
        )
