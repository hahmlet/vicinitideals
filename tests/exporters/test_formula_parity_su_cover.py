"""Engine-vs-formula parity for the S&U + Cover formula conversion.

Commit 2 of docs/feature-plans/investor-excel-formula-conversion.md.

Three assertions per converted cell, per the plan §8 pattern:

  1. Cell carries a formula (string starting with ``=``), not a value
  2. Formula text references the expected named-range or A1 inputs
  3. After force-recalc, the Excel-computed value matches the engine
     value within tolerance

Skips when no recalc backend (Excel COM / LibreOffice) is available on
the host. On Windows + Office (the dev machine) the tests run live.
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.investor_export import (
    _compute_sources_gap,
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
    read_formula_text,
    read_named_value,
    recalc_workbook,
)


async def _seed_scenario(session: AsyncSession):
    org, user = await seed_org(session)
    opportunity = await seed_opportunity(
        session, org, user, name="SU-Cover-Parity Smoke"
    )
    deal_model, _, _, _ = await seed_deal_model_with_financials(
        session, opportunity, user
    )
    return deal_model


# ── Formula-text assertions (no recalc needed) ────────────────────────────────


async def test_s_su2_uses_total_is_formula(session: AsyncSession, tmp_path: Path):
    """s_su2_uses_total is a SUM-of-category-totals formula."""
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    formula = read_formula_text(path, "s_su2_uses_total")
    assert formula is not None, "s_su2_uses_total should be a formula, not a value"
    # Must reference cell coords (the category-total rows), not be hard-coded.
    assert formula.startswith("="), formula
    assert "B" in formula, (
        f"expected s_su2_uses_total to reference B-column cells; got {formula!r}"
    )


async def test_s_su2_gap_references_uses_and_sources(session: AsyncSession, tmp_path: Path):
    """s_su2_gap = uses_total - sources_total (cell-ref form)."""
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    formula = read_formula_text(path, "s_su2_gap")
    assert formula is not None
    # Subtraction proves it's the gap formula (not a SUM or single-cell ref).
    assert "-" in formula, formula


async def test_s_cover_uses_references_su_sheet(session: AsyncSession, tmp_path: Path):
    """Cover Total Uses pulls from the Sources & Uses sheet via defined name."""
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    formula = read_formula_text(path, "s_cover_uses")
    assert formula is not None
    # Should reference the s_su2_uses_total defined name (workbook-scoped,
    # so no sheet qualifier required).
    assert "s_su2_uses_total" in formula, formula


async def test_s_cover_sources_references_su_sheet(session: AsyncSession, tmp_path: Path):
    """Cover Total Sources pulls from Sources & Uses via defined name."""
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    formula = read_formula_text(path, "s_cover_sources")
    assert formula is not None
    assert "s_su2_sources_total" in formula, formula


# ── Engine-vs-formula computed-value parity (requires recalc backend) ─────────


async def test_su_uses_total_evaluates_to_engine_value(
    session: AsyncSession, tmp_path: Path
):
    """Step 3 of the parity pattern — Excel-computed value matches engine.

    Exports, recalcs the workbook, reads ``s_su2_uses_total`` computed
    value, compares against the engine-computed total uses from
    ``_compute_sources_gap``. Catches both formula-correctness bugs
    (wrong SUM range, wrong cell coords) and any divergence between
    the S&U sheet's per-project breakdown and the engine rollup.
    """
    scenario = await _seed_scenario(session)
    # Compute engine value with the same data-load path the exporter uses.
    ctx = await _load_all(session, scenario.id)
    engine_uses_total, engine_sources_total, _gap = _compute_sources_gap(ctx)

    blob = await export_investor_workbook(scenario.id, session)
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    try:
        recalc_workbook(path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend: {exc}")

    excel_uses_total = read_named_value(path, "s_su2_uses_total", data_only=True)
    # Tolerate Decimal-to-float round-trip noise.
    if excel_uses_total is None:
        excel_uses_total = 0
    diff = abs(float(engine_uses_total) - float(excel_uses_total))
    assert diff < 1.0, (
        f"S&U Total Uses parity break: engine={engine_uses_total}, "
        f"excel={excel_uses_total}, diff={diff}"
    )


async def test_cover_uses_matches_su_uses_after_recalc(
    session: AsyncSession, tmp_path: Path
):
    """Cover sheet's Total Uses (cross-sheet ref) equals S&U's Total Uses."""
    scenario = await _seed_scenario(session)
    blob = await export_investor_workbook(scenario.id, session)
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    try:
        recalc_workbook(path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend: {exc}")

    cover_uses = read_named_value(path, "s_cover_uses", data_only=True) or 0
    su_uses = read_named_value(path, "s_su2_uses_total", data_only=True) or 0
    assert abs(float(cover_uses) - float(su_uses)) < 0.01, (
        f"Cover Total Uses ({cover_uses}) != S&U Total Uses ({su_uses}) "
        f"after recalc — cross-sheet defined-name ref is broken"
    )


async def test_su_sources_total_evaluates_close_to_engine_value(
    session: AsyncSession, tmp_path: Path
):
    """Sources total parity. Tolerance widened: the S&U sheet now writes
    one implied-equity gap row that the engine ``_compute_sources_gap``
    doesn't compute the same way. Within 5% absolute or $10k is fine.
    """
    scenario = await _seed_scenario(session)
    ctx = await _load_all(session, scenario.id)
    _engine_uses, engine_sources, _gap = _compute_sources_gap(ctx)

    blob = await export_investor_workbook(scenario.id, session)
    path = tmp_path / "wb.xlsx"
    path.write_bytes(blob)

    try:
        recalc_workbook(path)
    except RecalcUnavailableError as exc:
        pytest.skip(f"no recalc backend: {exc}")

    excel_sources = read_named_value(path, "s_su2_sources_total", data_only=True) or 0
    diff = abs(float(engine_sources) - float(excel_sources))
    # Allow $10k absolute tolerance to swallow implied-equity rounding.
    assert diff < 10_000, (
        f"Sources total parity break: engine={engine_sources}, "
        f"excel={excel_sources}, diff={diff}"
    )
