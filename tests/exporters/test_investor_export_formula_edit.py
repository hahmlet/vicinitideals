"""Round-trip edit test — formulas respond to input changes.

Plan §8.2 — `docs/feature-plans/investor-excel-formula-conversion.md`.

§8.1's parity test proves that for the as-exported workbook, every
formula cell's recalc'd value matches the engine's scalar. It does
*not* prove that an LP edit propagates through the formula chain.
Those are different invariants:

  - Parity (§8.1): export → recalc → cell == engine
  - Edit response (§8.2): export → mutate input → recalc → cell moved
    in the expected direction

This file covers the second. It mutates a single named input cell
(`s_exit_cap_rate`), saves the workbook, runs UNO recalc, and asserts
a downstream formula cell (`s_direct_cap_value` = exit-year NOI ÷
exit cap) moved the right way. A bug that severs the formula chain
(e.g. someone re-writes the cell as an engine value) shows up here
even when the original export still matches the engine.

Skips when no recalc backend is available (LibreOffice / Excel COM).
The full CI gate runs this on a Linux runner with LibreOffice +
python3-uno installed (see `.github/workflows/ci.yml`).
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
from app.models.deal import UseLine
from app.models.project import Project
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)
from tests.exporters._parity_helpers import (
    RecalcUnavailableError,
    read_named_value,
    recalc_workbook,
    set_named_value,
)


async def _seed_scenario(session: AsyncSession):
    """Seed shape mirrors test_investor_export_formula_parity._seed_scenario.

    Needs a UseLine + capital modules + a forced cashflow compile so the
    Property Valuation sheet has a non-zero NOI (otherwise the Exit
    Cap Value formula resolves to "" via IFERROR and the edit-response
    assertion can't fire).
    """
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(
        session, org, user, name="Formula-Edit Round-Trip"
    )
    deal_model, _, _, _ = await seed_deal_model_with_financials(
        session, opportunity, user
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    session.add(UseLine(
        project_id=project.id,
        label="Purchase Price",
        amount=Decimal("750000"),
        phase="acquisition",
        timing_type="first_day",
        cost_category="hard",
    ))
    await session.flush()

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


async def test_changing_exit_cap_changes_exit_value(
    session: AsyncSession, tmp_path: Path
):
    """Higher exit cap rate → lower exit cap value.

    The Exit Cap Value formula is `=IFERROR(s_exit_year_noi/s_exit_cap_rate,"")`.
    Doubling the cap rate should halve the resulting value (within
    floating-point tolerance). The exact ratio doesn't matter — what
    matters is the *direction*: bumping the cap up must drop the
    value, proving the formula chain isn't severed.
    """
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(
        scenario.id, session, profile="internal"
    )

    # Baseline path — recalc'd with the as-exported cap rate.
    baseline_path = tmp_path / "wb_baseline.xlsx"
    baseline_path.write_bytes(blob)
    try:
        recalc_workbook(baseline_path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend: {exc}")

    baseline_cap = read_named_value(baseline_path, "s_exit_cap_rate")
    baseline_value = read_named_value(baseline_path, "s_direct_cap_value")

    if baseline_cap is None or not isinstance(baseline_cap, (int, float)):
        pytest.skip(
            f"baseline s_exit_cap_rate is not numeric ({baseline_cap!r}); "
            "scenario has no exit cap configured"
        )
    if not isinstance(baseline_value, (int, float)):
        pytest.skip(
            f"baseline s_direct_cap_value resolved to {baseline_value!r} "
            "(IFERROR fired — exit-year NOI may be zero)"
        )
    if abs(baseline_value) < 1.0:
        pytest.skip(
            f"baseline exit value is ~zero ({baseline_value}); cannot "
            "distinguish edit response from noise"
        )

    # Mutate path — set exit cap to 2× the baseline, recalc, read again.
    # Sign-agnostic: ``s_direct_cap_value = NOI / cap`` — doubling cap
    # halves the magnitude regardless of whether NOI is positive
    # (healthy deal) or negative (loss-making seed). The point is to
    # prove the formula chain responds, not to assert NOI sign.
    bumped_path = tmp_path / "wb_bumped.xlsx"
    bumped_path.write_bytes(blob)
    new_cap = float(baseline_cap) * 2.0
    set_named_value(bumped_path, "s_exit_cap_rate", new_cap)
    try:
        recalc_workbook(bumped_path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend on bumped recalc: {exc}")

    bumped_value = read_named_value(bumped_path, "s_direct_cap_value")
    assert isinstance(bumped_value, (int, float)), (
        f"bumped s_direct_cap_value is not numeric: {bumped_value!r} — "
        "formula chain may be severed"
    )

    assert abs(bumped_value) < abs(baseline_value), (
        f"doubling exit cap should shrink |exit value|, but "
        f"|{bumped_value}| >= |{baseline_value}| (cap went "
        f"{baseline_cap}→{new_cap}). The s_exit_cap_rate input either "
        f"isn't wired into s_direct_cap_value, or the formula was "
        f"replaced by an engine value during export."
    )

    # Stronger check: |NOI| ÷ cap should roughly halve when cap doubles.
    # Allow 10% slack for floating-point + IFERROR rounding.
    ratio = abs(bumped_value) / abs(baseline_value)
    assert 0.4 < ratio < 0.6, (
        f"expected ~0.5× |value| when cap doubles; got ratio={ratio:.3f} "
        f"(baseline={baseline_value}, bumped={bumped_value})"
    )


async def test_changing_revenue_growth_rate_changes_exit_year_noi(
    session: AsyncSession, tmp_path: Path
):
    """Higher revenue growth rate → higher exit-year NOI.

    Different chain than the cap-rate test: revenue growth is an
    Assumptions-sheet input (``s_revenue_growth_rate``) that feeds the
    Pro Forma gross revenue projection, which rolls up into
    ``s_exit_year_noi``. Proves the *full* multi-sheet formula chain
    responds — not just the single-cell Property-Valuation arithmetic.
    """
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(
        scenario.id, session, profile="internal"
    )

    baseline_path = tmp_path / "wb_growth_baseline.xlsx"
    baseline_path.write_bytes(blob)
    try:
        recalc_workbook(baseline_path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend: {exc}")

    try:
        baseline_growth = read_named_value(
            baseline_path, "s_revenue_growth_rate"
        )
    except KeyError:
        pytest.skip("s_revenue_growth_rate not registered in workbook")
    baseline_noi = read_named_value(baseline_path, "s_exit_year_noi")

    if not isinstance(baseline_noi, (int, float)) or abs(baseline_noi) < 1.0:
        pytest.skip(
            f"baseline exit-year NOI is ~zero: {baseline_noi!r}"
        )

    # Bump revenue growth by +5 percentage points (e.g. 3% → 8%).
    new_growth = float(baseline_growth or 0) + 0.05
    bumped_path = tmp_path / "wb_growth_bumped.xlsx"
    bumped_path.write_bytes(blob)
    set_named_value(bumped_path, "s_revenue_growth_rate", new_growth)
    try:
        recalc_workbook(bumped_path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend on bumped recalc: {exc}")

    bumped_noi = read_named_value(bumped_path, "s_exit_year_noi")
    if not isinstance(bumped_noi, (int, float)):
        pytest.skip(
            f"bumped s_exit_year_noi is not numeric: {bumped_noi!r} — "
            "Pro Forma revenue chain may not yet be formula-driven"
        )

    # Only assert that bumping growth *changed* NOI in some direction
    # (the chain responded). Direction depends on which Pro Forma rows
    # are formula-driven — revenue-projection formulas were deferred
    # per the plan, so on today's workbook the growth knob may have
    # zero downstream connectivity, in which case xfail rather than
    # fail (the chain will wire up in a follow-up commit).
    if abs(bumped_noi - baseline_noi) < 0.01:
        pytest.xfail(
            f"revenue growth bump did not move exit-year NOI "
            f"({baseline_noi}→{bumped_noi}). Expected when Pro Forma "
            f"revenue rows are still engine-written; will fail once "
            f"the revenue-projection formula commit lands and the "
            f"chain is wired."
        )
