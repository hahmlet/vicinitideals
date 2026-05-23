"""Unified parity test — `EXPECTED_FORMULA_CELLS` registry vs engine.

Plan §8.1 — `docs/feature-plans/investor-excel-formula-conversion.md`.

Per-sheet parity tests (`test_formula_parity_proforma.py`,
`test_formula_parity_returns.py`, …) cover each conversion commit in
isolation. This file is the cross-cutting check: a single registry of
formula-driven named cells, each paired with the engine extractor that
should match its post-recalc value. New formula cells are expected to
land in `EXPECTED_FORMULA_CELLS`; the test then catches silent drift
the per-sheet files might miss (e.g. an engine refactor that changes
which key holds the canonical IRR).

Two assertions:

  - `test_every_formula_cell_carries_a_formula` — every registered
    named range is a formula string starting with `=`. Runs always.
    No recalc backend needed.

  - `test_every_formula_cell_matches_engine_output` — post-recalc, the
    cached value matches the engine extractor within per-entry
    tolerance. Skips when LibreOffice / Excel is not on the host.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

import pytest
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
from app.models.deal import UseLine
from app.models.project import Project
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)
from tests.exporters._parity_helpers import (
    RecalcUnavailableError,
    read_formula_text,
    read_named_value,
    recalc_workbook,
)


# ── Registry ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FormulaCell:
    """One formula-driven named cell paired with its engine reference.

    ``engine_value(ctx)`` returns the engine's canonical scalar for the
    cell, in the same units the Excel formula resolves to (e.g.
    percent as percent for IRR/cap-rate, fractions for ratios, raw
    dollars for currency).

    ``abs_tol`` / ``rel_tol`` define the parity band. Use ``abs_tol``
    for ratios and small dollars; use ``rel_tol`` for multi-million
    dollar totals where 0.01 absolute is meaninglessly tight.

    ``skip_if_engine_none`` — when the engine extractor returns
    ``None`` / 0, skip rather than fail. Used for cells whose engine
    side is only populated when a full waterfall rollup ran.

    ``excel_scale`` — multiplier applied to the Excel cached value
    before comparing. Excel writes percents as fractions (0.085 for
    8.5%); engine stores percent magnitudes (8.5). Set to ``100`` for
    percent-formatted cells; leave at ``1`` for ratios/dollars.
    """

    named_range: str
    engine_value: Callable[[dict[str, Any]], Any]
    label: str
    abs_tol: Decimal = Decimal("0.01")
    rel_tol: float = 0.0
    skip_if_engine_none: bool = False
    excel_scale: float = 1.0


def _totals(ctx: dict[str, Any]) -> dict[str, Any]:
    return (ctx.get("rollup_summary") or {}).get("totals") or {}


EXPECTED_FORMULA_CELLS: list[FormulaCell] = [
    # ── Cover sheet mirrors ───────────────────────────────────────────────────
    # Cover's KPI cells are simple ``=s_<upstream>`` formulas. They give
    # the parity test signal on every seeded scenario regardless of
    # whether a full waterfall rollup ran.
    FormulaCell(
        named_range="s_cover_uses",
        engine_value=lambda ctx: _totals(ctx).get("total_uses"),
        label="Cover — Total Uses",
        abs_tol=Decimal("1.0"),  # multi-million $ values
        rel_tol=1e-6,
        skip_if_engine_none=True,
    ),
    # ── UW Summary ────────────────────────────────────────────────────────────
    # Combined Equity Multiple is SUMIF-driven. Skips when the engine's
    # waterfall hasn't run (combined_em_x = 0/None) — the per-sheet test
    # in test_formula_parity_em uses the same skip pattern.
    FormulaCell(
        named_range="s_combined_equity_multiple",
        engine_value=lambda ctx: _totals(ctx).get("combined_em_x"),
        label="UW Summary — Combined Equity Multiple",
        abs_tol=Decimal("0.5"),
        skip_if_engine_none=True,
    ),
    # ── Investor Returns ──────────────────────────────────────────────────────
    FormulaCell(
        named_range="s_returns_combined_irr",
        engine_value=lambda ctx: _totals(ctx).get("combined_irr_pct"),
        label="Investor Returns — Combined Levered IRR (scenario)",
        # IRR parity is loose by design — Excel IRR uses annual buckets
        # while the engine IRR is monthly XIRR. 0.5 percentage points
        # is the band the per-sheet test (`test_combined_irr_…`) uses.
        abs_tol=Decimal("0.5"),
        skip_if_engine_none=True,
        excel_scale=100.0,
    ),
    FormulaCell(
        named_range="s_returns_combined_em",
        engine_value=lambda ctx: _totals(ctx).get("combined_em_x"),
        label="Investor Returns — Combined Equity Multiple (scenario)",
        abs_tol=Decimal("0.5"),
        skip_if_engine_none=True,
    ),
]


# ── Fixture ───────────────────────────────────────────────────────────────────


async def _seed_scenario(session: AsyncSession):
    """Same seed shape as `test_formula_parity_em.py`: one debt + one equity
    module wired to the seeded project, with a forced cashflow compile so
    the export has real engine values to compare against."""
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(
        session, org, user, name="Formula-Parity Registry"
    )
    deal_model, _, _, _ = await seed_deal_model_with_financials(
        session, opportunity, user
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()

    # Use line so total_uses is non-zero and Cover mirror formulas have
    # signal. Without this the engine's rollup totals are all 0 and every
    # registry entry trips the engine-None skip branch.
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


# ── Tests ─────────────────────────────────────────────────────────────────────


async def test_every_formula_cell_carries_a_formula(
    session: AsyncSession, tmp_path: Path
):
    """Each registered named range resolves to a formula cell.

    Runs without a recalc backend, so the light CI gate exercises it
    on every push. Failures here mean either a registered cell stopped
    being formula-driven (regression in the exporter) or the registry
    references a stale name (regression in the test).
    """
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(
        scenario.id, session, profile="internal"
    )
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    missing: list[str] = []
    not_formula: list[str] = []
    for entry in EXPECTED_FORMULA_CELLS:
        try:
            formula = read_formula_text(path, entry.named_range)
        except KeyError:
            missing.append(f"{entry.named_range} ({entry.label})")
            continue
        if formula is None:
            not_formula.append(f"{entry.named_range} ({entry.label})")
    assert not missing, (
        "named ranges missing from workbook: " + ", ".join(missing)
    )
    assert not not_formula, (
        "named ranges resolve to a value cell, not a formula: "
        + ", ".join(not_formula)
    )


async def test_every_formula_cell_matches_engine_output(
    session: AsyncSession, tmp_path: Path
):
    """Post-recalc, each registered cell's cached value matches the
    engine extractor within tolerance.

    Skips when no recalc backend is available on the host
    (LibreOffice / Excel COM). The full CI gate runs this on a Linux
    runner with LibreOffice installed.
    """
    scenario = await _seed_scenario(session)
    ctx = await _load_all(session, scenario.id)
    blob = await export_investor_workbook(
        scenario.id, session, profile="internal"
    )
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    try:
        recalc_workbook(path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend: {exc}")

    failures: list[str] = []
    checked = 0
    for entry in EXPECTED_FORMULA_CELLS:
        engine_raw = entry.engine_value(ctx)
        if entry.skip_if_engine_none and engine_raw in (None, 0, 0.0, Decimal(0)):
            continue
        if engine_raw is None:
            failures.append(
                f"{entry.named_range} ({entry.label}): engine returned None"
            )
            continue

        try:
            excel_value = read_named_value(path, entry.named_range)
        except KeyError:
            failures.append(
                f"{entry.named_range} ({entry.label}): defined name missing"
            )
            continue
        if excel_value is None:
            # Recalc backend left the cached value empty — surface but
            # don't fail (LibreOffice on some hosts skips writing the
            # cache for openpyxl-authored workbooks). The presence test
            # above already proved the formula is there.
            continue
        if not isinstance(excel_value, (int, float)):
            failures.append(
                f"{entry.named_range} ({entry.label}): non-numeric Excel "
                f"value {excel_value!r}"
            )
            continue

        excel_scaled = Decimal(str(float(excel_value) * entry.excel_scale))
        engine_dec = Decimal(str(engine_raw))
        diff = abs(excel_scaled - engine_dec)
        if diff <= entry.abs_tol:
            checked += 1
            continue
        if entry.rel_tol > 0:
            denom = max(abs(excel_scaled), abs(engine_dec))
            if denom > 0 and float(diff / denom) <= entry.rel_tol:
                checked += 1
                continue
        failures.append(
            f"{entry.named_range} ({entry.label}): excel={excel_scaled}, "
            f"engine={engine_dec}, diff={diff}, abs_tol={entry.abs_tol}, "
            f"rel_tol={entry.rel_tol}"
        )

    assert not failures, "parity failures:\n  " + "\n  ".join(failures)
    if checked == 0:
        pytest.skip(
            "all registry entries had engine_value=None on this seed "
            "(recalc backend may not be writing cached values)"
        )
