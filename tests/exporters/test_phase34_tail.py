"""Phase 3 + 4 tail items:

  Phase 3 (revenue side): Pro Forma renders one indented breakout
  row per IncomeStream directly below the Gross Revenue total,
  mirroring the OpEx breakout shipped earlier in Phase 3. Each row
  references Assumptions Block F cells so an LP can trace any
  single revenue stream back to its input.

  Phase 4 (Total Uses formula): the Underwriting Summary "Total
  Uses" KPI becomes ``=s_su_uses_total`` instead of an engine
  scalar, so a Use-line edit on Sources & Uses ripples through
  immediately.

Contract:

  1. Total "Gross Revenue" row remains the Phase 2 SUM-of-Block-F
     formula (unchanged).
  2. One indented breakout row per IncomeStream appears directly
     below the total.
  3. Each breakout's Y0 is blank, Y1 = ``=s_rev_<slug>_y1_monthly*12``,
     Y2 = prior-year × (1 + per-stream escalation_pct).
  4. UW Summary "Total Uses" cell is the literal formula
     ``=s_su_uses_total``.
"""
from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import compute_cash_flows
from app.exporters.investor_export import export_investor_workbook
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)


pytestmark = pytest.mark.asyncio


async def _seed(session: AsyncSession):
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="Phase 3+4 Tail")
    deal_model, _, stream, opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    stream.active_in_phases = ["stabilized"]
    opex.active_in_phases = ["stabilized"]
    await session.flush()
    await compute_cash_flows(deal_model.id, session)
    await session.commit()
    return deal_model


def _find_row(ws, label_exact: str) -> int | None:
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and v.strip() == label_exact:
            return r
    return None


def _find_indented_row(ws, label_substr: str) -> int | None:
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if (
            isinstance(v, str)
            and "•" in v
            and label_substr.lower() in v.lower()
        ):
            return r
    return None


# ── Revenue breakout (Phase 3 revenue side) ──────────────────────────


async def test_gross_revenue_total_row_unchanged(
    session: AsyncSession,
) -> None:
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    ws = wb["Underwriting Pro Forma"]
    row = _find_row(ws, "Gross Revenue")
    assert row is not None
    y1 = ws.cell(row=row, column=3).value
    assert isinstance(y1, str) and y1.startswith("=SUM(s_rev_"), (
        f"Total Gross Revenue Y1 must remain Phase 2 SUM formula; got {y1!r}"
    )


async def test_revenue_breakout_row_appears_below_total(
    session: AsyncSession,
) -> None:
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    ws = wb["Underwriting Pro Forma"]
    total_row = _find_row(ws, "Gross Revenue")
    assert total_row is not None
    breakout = _find_indented_row(ws, "1BR Units")
    assert breakout is not None, (
        "1BR Units breakout row missing below Gross Revenue"
    )
    assert breakout > total_row


async def test_revenue_breakout_y0_blank(session: AsyncSession) -> None:
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    ws = wb["Underwriting Pro Forma"]
    breakout = _find_indented_row(ws, "1BR Units")
    assert breakout is not None
    y0 = ws.cell(row=breakout, column=2).value
    assert y0 in (None, ""), f"got {y0!r}"


async def test_revenue_breakout_y1_references_block_f(
    session: AsyncSession,
) -> None:
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    ws = wb["Underwriting Pro Forma"]
    breakout = _find_indented_row(ws, "1BR Units")
    assert breakout is not None
    y1 = ws.cell(row=breakout, column=3).value
    assert isinstance(y1, str) and y1.startswith("="), f"got {y1!r}"
    assert "s_rev_" in y1 and "_y1_monthly" in y1 and "*12" in y1, (
        f"breakout Y1 must annualize the Block F monthly cell; got {y1!r}"
    )


async def test_revenue_breakout_y2_uses_per_stream_escalation(
    session: AsyncSession,
) -> None:
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    ws = wb["Underwriting Pro Forma"]
    breakout = _find_indented_row(ws, "1BR Units")
    assert breakout is not None
    y2 = ws.cell(row=breakout, column=4).value
    assert isinstance(y2, str) and y2.startswith("="), f"got {y2!r}"
    assert "s_rev_" in y2 and "_escalation_pct" in y2, (
        f"breakout Y2 must reference per-stream escalation_pct; got {y2!r}"
    )
    assert f"C{breakout}" in y2, (
        f"breakout Y2 must reference its own prior-year cell C{breakout}; "
        f"got {y2!r}"
    )


# ── Total Uses formula (Phase 4 tail) ────────────────────────────────


async def test_total_uses_is_formula_referencing_su_total(
    session: AsyncSession,
) -> None:
    scenario = await _seed(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)
    ws = wb["Underwriting Summary"]
    row = _find_row(ws, "Total Uses")
    assert row is not None, "Total Uses row not found"
    v = ws.cell(row=row, column=2).value
    assert v == "=s_su_uses_total", (
        f"Total Uses must be =s_su_uses_total; got {v!r}"
    )
    # Defined-name registration preserved so downstream sheets can keep
    # referencing s_total_uses.
    assert "s_total_uses" in set(wb.defined_names)
