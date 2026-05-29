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
  3. After Excel recalc, the cell value == engine.effective_gross_income
     (or .noi) for that year within tolerance
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.investor_export import (
    _aggregate_scenario_annual,
    _load_all,
    export_investor_workbook,
)
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)
from tests.exporters._parity_helpers import (
    RecalcUnavailableError,
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
    for r in range(1, ws.max_row + 1):
        if ws.cell(row=r, column=1).value == label:
            return r
    return None


async def test_egi_row_is_formula_each_year(session: AsyncSession):
    """Every Y0..Yn cell on the EGI row carries a formula, not a value."""
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    _wb, ws = _proforma_sheet(blob)

    egi_row = _find_row_by_label(ws, "Effective Gross Income")
    assert egi_row is not None

    # Walk columns starting at 2 (Y0); stop at the first empty cell.
    formula_count = 0
    for c in range(2, ws.max_column + 1):
        v = ws.cell(row=egi_row, column=c).value
        if v is None:
            break
        assert isinstance(v, str) and v.startswith("="), (
            f"EGI Y{c - 2} should be a formula; got {v!r}"
        )
        # Must reference at least two cells (GrossRev + Vacancy) on this
        # column. Cell references look like "B5", "B6", etc.
        assert v.count("B") + v.count("C") + v.count("D") + v.count("E") >= 2, (
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

    formula_count = 0
    for c in range(2, ws.max_column + 1):
        v = ws.cell(row=noi_row, column=c).value
        if v is None:
            break
        assert isinstance(v, str) and v.startswith("="), (
            f"NOI Y{c - 2} should be a formula; got {v!r}"
        )
        # Should subtract (EGI - OpEx) so a minus must appear in the formula.
        assert "-" in v, f"NOI formula expected to contain '-'; got {v!r}"
        formula_count += 1
    assert formula_count > 0


async def test_egi_evaluates_to_engine_value(
    session: AsyncSession, tmp_path: Path
):
    """Excel-recalc'd EGI == engine effective_gross_income for each year."""
    scenario = await _seed_scenario(session)
    ctx = await _load_all(session, scenario.id)
    annual = _aggregate_scenario_annual(ctx["cash_flows"])

    blob = await export_investor_workbook(scenario.id, session)
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    try:
        recalc_workbook(path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend: {exc}")

    wb = load_workbook(path, data_only=True)
    ws = wb["Underwriting Pro Forma"]
    egi_row = _find_row_by_label(ws, "Effective Gross Income")
    assert egi_row is not None

    max_year = min(max(annual) if annual else 0, 10)
    year_cols = list(range(0, max(max_year, 1) + 1))

    for col_offset, year in enumerate(year_cols):
        engine_value = float(annual.get(year, {}).get("effective_gross_income", 0))
        excel_value = ws.cell(row=egi_row, column=2 + col_offset).value
        if excel_value is None:
            excel_value = 0
        diff = abs(float(excel_value) - engine_value)
        assert diff < 1.0, (
            f"EGI Y{year} parity break: engine={engine_value}, "
            f"excel={excel_value}, diff={diff}"
        )


async def test_noi_evaluates_to_engine_value(
    session: AsyncSession, tmp_path: Path
):
    """Excel-recalc'd NOI == engine noi for each year."""
    scenario = await _seed_scenario(session)
    ctx = await _load_all(session, scenario.id)
    annual = _aggregate_scenario_annual(ctx["cash_flows"])

    blob = await export_investor_workbook(scenario.id, session)
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    try:
        recalc_workbook(path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend: {exc}")

    wb = load_workbook(path, data_only=True)
    ws = wb["Underwriting Pro Forma"]
    noi_row = _find_row_by_label(ws, "NOI")
    assert noi_row is not None

    max_year = min(max(annual) if annual else 0, 10)
    year_cols = list(range(0, max(max_year, 1) + 1))

    for col_offset, year in enumerate(year_cols):
        engine_value = float(annual.get(year, {}).get("noi", 0))
        excel_value = ws.cell(row=noi_row, column=2 + col_offset).value
        if excel_value is None:
            excel_value = 0
        diff = abs(float(excel_value) - engine_value)
        assert diff < 1.0, (
            f"NOI Y{year} parity break: engine={engine_value}, "
            f"excel={excel_value}, diff={diff}"
        )


async def test_egi_formula_subtracts_vacancy(session: AsyncSession):
    """Each EGI cell must subtract Vacancy Loss, not add it.

    Regression: prior to the vacancy-sign fix, EGI was emitted as
    ``=GrossRev + Vacancy`` while the engine stored vacancy_loss as a
    positive haircut and Pro Forma Gross Revenue was already net of
    occupancy. The combined effect overstated NOI by the vacancy
    amount. Fix flips the EGI sign to '-' and removes occupancy from
    the rent_y1_monthly formula so Gross Revenue shows true GPR.
    """
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    _wb, ws = _proforma_sheet(blob)

    egi_row = _find_row_by_label(ws, "Effective Gross Income")
    vac_row = _find_row_by_label(ws, "Vacancy Loss")
    assert egi_row is not None and vac_row is not None

    for c in range(2, ws.max_column + 1):
        v = ws.cell(row=egi_row, column=c).value
        if v is None:
            break
        assert isinstance(v, str) and v.startswith("=")
        vac_ref = f"{chr(ord('A') + c - 1)}{vac_row}"
        assert f"-{vac_ref}" in v, (
            f"EGI Y{c - 2} formula must subtract vacancy ({vac_ref}); "
            f"got {v!r}"
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
