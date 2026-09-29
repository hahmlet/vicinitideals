"""Engine-vs-formula parity for the Pro Forma EGI + NOI conversion.

Commit 3 of docs/feature-plans/investor-excel-formula-conversion.md §4.1.

Scope is intentionally narrow: only the rows whose math is a direct
sum/difference of other rows on the same sheet are formula-driven in
this commit (Effective Gross Income, NOI). Gross Revenue, Vacancy
Loss, Operating Expenses, CapEx Reserve, Debt Service, Net Cash Flow
stay as engine values — Debt Service formulas land in commit 4 with
the Debt Schedule conversion, and revenue/opex growth-projection
formulas land in a later commit once an ``s_revenue_growth_rate``
input is wired.

The parity loop:

  1. Cell is a formula (string starting with ``=``) for every Y0..Yn
     column on the EGI + NOI rows
  2. Formula references the GrossRev/Vacancy cells (EGI) or EGI/OpEx
     cells (NOI) on the same column
  3. After Excel recalc (on a COMPUTED deal), the cell value equals the
     Pro Forma's documented basis every year, and tracks the engine's
     effective_gross_income / noi within 3% in every full stabilized
     year -- see the block comment above the value tests for why the
     Pro Forma and the engine differ by design in Y1 and the exit year.
"""
from __future__ import annotations

import re
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.investor_export import (
    _aggregate_scenario_annual,
    _load_all,
    _period_to_year,
    export_investor_workbook,
)
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)
from tests.exporters._parity_helpers import (
    RecalcUnavailableError,
    find_label_row,
    proforma_layout,
    recalc_workbook,
)


async def _seed_scenario(session: AsyncSession):
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(
        session, org, user, name="ProForma-Parity Smoke"
    )
    deal_model, _, _, _ = await seed_deal_model_with_financials(
        session, opportunity, user
    )
    return deal_model


def _proforma_sheet(blob: bytes):
    wb = load_workbook(BytesIO(blob), data_only=False)
    return wb, wb["Underwriting Pro Forma"]


def _find_row_by_label(ws, label: str) -> int | None:
    label_col, _ = proforma_layout(ws)
    return find_label_row(ws, label, col=label_col, exact=True)


_CELL_REF_RE = re.compile(r"[A-Z]+\d+")


async def test_egi_row_is_formula_each_year(session: AsyncSession):
    """Every Y0..Yn cell on the EGI row carries a formula, not a value."""
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    _wb, ws = _proforma_sheet(blob)

    egi_row = _find_row_by_label(ws, "Effective Gross Income")
    assert egi_row is not None

    _, y0_col = proforma_layout(ws)
    # Walk year columns starting at Y0; stop at the first empty cell.
    formula_count = 0
    for c in range(y0_col, ws.max_column + 1):
        v = ws.cell(row=egi_row, column=c).value
        if v is None:
            break
        assert isinstance(v, str) and v.startswith("="), (
            f"EGI Y{c - y0_col} should be a formula; got {v!r}"
        )
        # Must reference at least two cells (GrossRev + Vacancy) on this
        # column. Cell references look like "C5", "C6", etc.
        assert len(_CELL_REF_RE.findall(v)) >= 2, (
            f"EGI formula should reference 2+ cells; got {v!r}"
        )
        formula_count += 1
    assert formula_count > 0


async def test_noi_row_is_formula_each_year(session: AsyncSession):
    """Every Y0..Yn cell on the NOI row carries a formula."""
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    _wb, ws = _proforma_sheet(blob)

    noi_row = _find_row_by_label(ws, "NOI")
    assert noi_row is not None

    _, y0_col = proforma_layout(ws)
    formula_count = 0
    for c in range(y0_col, ws.max_column + 1):
        v = ws.cell(row=noi_row, column=c).value
        if v is None:
            break
        assert isinstance(v, str) and v.startswith("="), (
            f"NOI Y{c - y0_col} should be a formula; got {v!r}"
        )
        # Should subtract (EGI - OpEx) so a minus must appear in the formula.
        assert "-" in v, f"NOI formula expected to contain '-'; got {v!r}"
        formula_count += 1
    assert formula_count > 0


# ── Recalc'd values vs the Pro Forma's documented basis + the engine ────────
#
# The Pro Forma is NOT the engine's calendar-year cash flow, by design
# (see the test_proforma_engine_parity docstring and the Revenue Y1 Sum /
# OpEx Y1 Sum entries in docs/FINANCIAL_MODEL.md):
#
#   Gross Revenue  Y0 = 0; Y1 = sum of stabilized monthly GPR x 12
#                  (s_rev_<slug>_y1_monthly * 12); Yn = Yn-1 x (1 + esc).
#   Vacancy Loss   engine's per-year vacancy_loss, signed negative.
#   OpEx           Y0 = 0; Y1 = sum of OperatingExpenseLine annual
#                  amounts; Yn = Yn-1 x (1 + line esc).
#   CapEx Reserve  engine's per-year capex_reserve.
#   EGI = GR + Vacancy;  NOI = EGI - OpEx - CapEx.
#
# So the value tests make two checks:
#   1. every year's recalc'd cell equals that documented basis ($1), built
#      from the seeded inputs + the COMPUTED engine vacancy/capex; and
#   2. in every FULL stabilized year (12 revenue months in the engine's
#      bucket -- not Y0, not the lease-up year, not the partial exit year)
#      the cell is within 3% of the engine's own year total. The residual
#      gap is escalation timing: the engine compounds monthly from period
#      0, the Pro Forma steps once a year from Y1 (~1.6% at 3%/yr).
#
# The seed zeroes the legacy OperationalInputs OpEx scalars (property
# tax, insurance, opex/unit, mgmt fee %). The engine still honours them
# but calls them superseded by OperatingExpenseLine rows, and the Pro
# Forma OpEx row reads only the lines -- a deal still carrying them would
# show a lower OpEx on the Pro Forma than in the engine.

ENGINE_TOLERANCE = 0.03


async def _seed_computed_scenario(session: AsyncSession):
    from app.engines.cashflow import compute_cash_flows

    org, user = await seed_org(session)
    opportunity = await seed_opportunity(
        session, org, user, name="ProForma-Parity Computed"
    )
    deal_model, inputs, _income, _opex = await seed_deal_model_with_financials(
        session, opportunity, user
    )
    inputs.property_tax_annual = Decimal("0")
    inputs.insurance_annual = Decimal("0")
    inputs.opex_per_unit_annual = Decimal("0")
    inputs.mgmt_fee_pct = Decimal("0")
    await session.flush()
    await compute_cash_flows(deal_model.id, session)
    await session.commit()
    return deal_model


def _esc(pct) -> Decimal:
    return Decimal(1) + Decimal(str(pct or 0)) / Decimal(100)


def _documented_basis(ctx: dict, year_cols: list[int]) -> dict[str, dict[int, float]]:
    """Per-year EGI / NOI the Pro Forma is documented to show."""
    annual = _aggregate_scenario_annual(ctx["cash_flows"])
    gr = {y: Decimal(0) for y in year_cols}
    opex = {y: Decimal(0) for y in year_cols}
    for streams in (ctx.get("income_streams") or {}).values():
        for s in streams:
            if s.amount_fixed_monthly is not None:
                monthly = Decimal(s.amount_fixed_monthly)
            else:
                monthly = Decimal(s.unit_count or 0) * Decimal(
                    s.amount_per_unit_monthly or 0
                )
            for y in year_cols[1:]:
                gr[y] += monthly * 12 * _esc(s.escalation_rate_pct_annual) ** (y - 1)
    for lines in (ctx.get("expense_lines") or {}).values():
        for ln in lines:
            for y in year_cols[1:]:
                opex[y] += Decimal(ln.annual_amount or 0) * _esc(
                    ln.escalation_rate_pct_annual
                ) ** (y - 1)
    egi, noi = {}, {}
    for y in year_cols:
        eng = annual.get(y, {})
        egi[y] = gr[y] - eng.get("vacancy_loss", Decimal(0))
        noi[y] = egi[y] - opex[y] - eng.get("capex_reserve", Decimal(0))
    return {
        "egi": {y: float(v) for y, v in egi.items()},
        "noi": {y: float(v) for y, v in noi.items()},
    }


def _full_operating_years(ctx: dict) -> set[int]:
    """Years whose engine bucket holds 12 revenue-earning months."""
    months: dict[int, int] = {}
    for cfs in ctx["cash_flows"].values():
        for cf in cfs:
            if (cf.gross_revenue or 0) > 0:
                y = _period_to_year(cf.period)
                months[y] = months.get(y, 0) + 1
    return {y for y, n in months.items() if n == 12}


async def _check_row_parity(
    session: AsyncSession, tmp_path: Path, *, label: str, field: str, key: str,
) -> None:
    scenario = await _seed_computed_scenario(session)
    ctx = await _load_all(session, scenario.id)
    annual = _aggregate_scenario_annual(ctx["cash_flows"])
    assert any(v.get(field, 0) for v in annual.values()), (
        "engine produced no cash flows -- compute_cash_flows did not run"
    )
    max_year = min(max(annual) if annual else 0, 10)
    year_cols = list(range(0, max(max_year, 1) + 1))
    expected = _documented_basis(ctx, year_cols)[key]
    full_years = _full_operating_years(ctx) & set(year_cols)
    assert len(full_years) >= 2, (
        f"seed should have several full stabilized years; got {sorted(full_years)}"
    )

    blob = await export_investor_workbook(scenario.id, session)
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)
    try:
        recalc_workbook(path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend: {exc}")

    ws = load_workbook(path, data_only=True)["Underwriting Pro Forma"]
    row = _find_row_by_label(ws, label)
    assert row is not None
    _, y0_col = proforma_layout(ws)
    for col_offset, year in enumerate(year_cols):
        excel_value = ws.cell(row=row, column=y0_col + col_offset).value
        assert isinstance(excel_value, (int, float)), (
            f"{label} Y{year} did not evaluate to a number: {excel_value!r}"
        )
        diff = abs(float(excel_value) - expected[year])
        assert diff < 1.0, (
            f"{label} Y{year} off its documented basis: "
            f"expected={expected[year]:.2f}, excel={excel_value}, diff={diff:.2f}"
        )
        if year in full_years:
            engine_value = float(annual[year][field])
            rel = abs(float(excel_value) - engine_value) / abs(engine_value)
            assert rel < ENGINE_TOLERANCE, (
                f"{label} Y{year} (full stabilized year) drifts {rel:.2%} from "
                f"the engine: engine={engine_value:.2f}, excel={excel_value}"
            )


async def test_egi_evaluates_to_documented_basis_and_tracks_engine(
    session: AsyncSession, tmp_path: Path
):
    """Recalc'd EGI == documented Pro Forma basis each year, and within 3%
    of engine effective_gross_income in every full stabilized year."""
    await _check_row_parity(
        session, tmp_path, label="Effective Gross Income",
        field="effective_gross_income", key="egi",
    )


async def test_noi_evaluates_to_documented_basis_and_tracks_engine(
    session: AsyncSession, tmp_path: Path
):
    """Recalc'd NOI == documented Pro Forma basis each year, and within 3%
    of engine noi in every full stabilized year."""
    await _check_row_parity(
        session, tmp_path, label="NOI", field="noi", key="noi",
    )


async def test_egi_formula_subtracts_vacancy(session: AsyncSession):
    """EGI must net out Vacancy Loss exactly once (no double-count).

    Sign convention (commit e7ba809): the Vacancy Loss row is written
    as signed NEGATIVE numbers so the LP reads a negative line, and the
    EGI formula ADDS the signed vacancy cell (``=GrossRev + Vacancy``).
    Adding a subtraction on top of the negative values would flip back
    to the original double-count bug, so this test pins both halves:

      1. every EGI cell adds the vacancy cell (``+<vac_ref>``), and
      2. every numeric Vacancy Loss cell is <= 0.

    Gross Revenue stays true GPR (occupancy excluded from the
    rent_y1_monthly formula — see test_rent_y1_monthly_excludes_occupancy).
    """
    from openpyxl.utils import get_column_letter

    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    _wb, ws = _proforma_sheet(blob)

    egi_row = _find_row_by_label(ws, "Effective Gross Income")
    vac_row = _find_row_by_label(ws, "Vacancy Loss")
    assert egi_row is not None and vac_row is not None

    _, y0_col = proforma_layout(ws)
    for c in range(y0_col, ws.max_column + 1):
        v = ws.cell(row=egi_row, column=c).value
        if v is None:
            break
        assert isinstance(v, str) and v.startswith("=")
        vac_ref = f"{get_column_letter(c)}{vac_row}"
        assert f"+{vac_ref}" in v, (
            f"EGI Y{c - y0_col} formula must add the signed vacancy cell "
            f"({vac_ref}); got {v!r}"
        )
        assert f"-{vac_ref}" not in v, (
            f"EGI Y{c - y0_col} must not subtract the already-negative "
            f"vacancy cell (double-count); got {v!r}"
        )
        vac_val = ws.cell(row=vac_row, column=c).value
        if isinstance(vac_val, (int, float)):
            assert vac_val <= 0, (
                f"Vacancy Loss Y{c - y0_col} must be written as a signed "
                f"negative value; got {vac_val!r}"
            )


async def test_rent_y1_monthly_excludes_occupancy(session: AsyncSession):
    """``s_rev_<slug>_y1_monthly`` must be count × rent (pre-vacancy).

    Regression: pre-fix formula multiplied by occupancy_pct, making
    Pro Forma's Gross Revenue line already net of vacancy — which
    then double-counted when the EGI formula added a positive vacancy
    cell on top. Y1 monthly is now the true gross potential rent;
    occupancy applies via the Vacancy Loss row and the EGI subtraction.
    """
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)

    rent_names = [
        n for n in wb.defined_names
        if n.startswith("s_rev_") and n.endswith("_y1_monthly")
    ]
    assert rent_names, "no s_rev_*_y1_monthly named ranges emitted"

    for name in rent_names:
        dn = wb.defined_names[name]
        for sheet, coord in dn.destinations:
            cell = wb[sheet][coord]
            formula = cell.value
            assert isinstance(formula, str) and formula.startswith("=")
            assert "occupancy_pct" not in formula, (
                f"{name} must NOT multiply by occupancy "
                f"(applied on Pro Forma instead); got {formula!r}"
            )
