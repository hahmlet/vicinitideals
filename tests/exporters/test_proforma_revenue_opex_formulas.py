"""Pro Forma Y1 Gross Revenue and Y1 OpEx must be formulas referencing
Assumptions Block F / G cells, not engine-computed hardcoded values.

Contract:

  1. Y1 Gross Revenue cell = ``=SUM(s_rev_<slug1>_y1_monthly, s_rev_<slug2>_y1_monthly, ...)*12``
     where slugs come from ``_all_revenue_slugs(ctx)``.
  2. Y1 OpEx cell = ``=SUM(s_opex_<slug1>_annual, s_opex_<slug2>_annual, ...)``.
  3. Y0 stays at engine value (construction-phase math differs from
     stabilized inputs).
  4. Y2+ keeps the existing growth-chain formula referencing the prior
     year's cell — confirms the Phase B chain still works on top of
     the new Y1 formula seed.
  5. Multi-project scenarios with duplicate stream labels get
     globally-resolved slugs (no silent collision overwrite).
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.cashflow import compute_cash_flows
from app.exporters.investor_export import export_investor_workbook
from app.models.deal import IncomeStream, IncomeStreamType, OperatingExpenseLine
from app.models.project import Project
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)


pytestmark = pytest.mark.asyncio


def _find_row(ws, label_text: str) -> int | None:
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and v.strip() == label_text:
            return r
    return None


async def _seed_with_one_stream_one_opex(session: AsyncSession):
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="PF Y1 Formula")
    deal_model, _, stream, opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    # Activate the seeded stream + opex in the stabilized phase so the
    # engine produces non-zero Y1 revenue/opex. Without this, engine
    # Y1 = 0 and the phase-gating in `_build_uw_proforma` (rightly)
    # suppresses the input-formula override, which would break the
    # assertions below that the Y1 cell IS a formula.
    stream.active_in_phases = ["stabilized"]
    opex.active_in_phases = ["stabilized"]
    await session.flush()
    await compute_cash_flows(deal_model.id, session)
    await session.commit()
    return deal_model


async def test_y1_gross_revenue_is_sum_of_block_f_y1_monthly_times_12(
    session: AsyncSession,
) -> None:
    scenario = await _seed_with_one_stream_one_opex(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)

    ws = wb["Underwriting Pro Forma"]
    gr_row = _find_row(ws, "Gross Revenue")
    assert gr_row is not None, "Gross Revenue row not found"

    # Y1 = column 3 (Y0 in col 2, Y1 in col 3).
    y1 = ws.cell(row=gr_row, column=3).value
    assert isinstance(y1, str) and y1.startswith("="), (
        f"Y1 Gross Revenue must be a formula, got {y1!r}"
    )
    assert "s_rev_" in y1, f"Y1 formula must reference Block F cells: {y1}"
    assert "_y1_monthly" in y1, f"Y1 formula must use _y1_monthly cells: {y1}"
    assert "*12" in y1, f"Y1 formula must annualize via *12: {y1}"


async def test_y1_opex_is_sum_of_block_g_annual_cells(
    session: AsyncSession,
) -> None:
    scenario = await _seed_with_one_stream_one_opex(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)

    ws = wb["Underwriting Pro Forma"]
    opex_row = _find_row(ws, "Operating Expenses")
    assert opex_row is not None, "Operating Expenses row not found"

    y1 = ws.cell(row=opex_row, column=3).value
    assert isinstance(y1, str) and y1.startswith("="), (
        f"Y1 OpEx must be a formula, got {y1!r}"
    )
    assert "s_opex_" in y1, f"Y1 formula must reference Block G: {y1}"
    assert "_annual" in y1, f"Y1 formula must use _annual cells: {y1}"


async def test_y0_gross_revenue_stays_engine_value(
    session: AsyncSession,
) -> None:
    """Y0 (pre-op) is construction-phase math — must NOT use the
    stabilized Y1 input formula."""
    scenario = await _seed_with_one_stream_one_opex(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)

    ws = wb["Underwriting Pro Forma"]
    gr_row = _find_row(ws, "Gross Revenue")
    y0 = ws.cell(row=gr_row, column=2).value
    # Y0 should be a numeric engine value, not a formula. (Or None / 0.)
    if isinstance(y0, str) and y0.startswith("="):
        pytest.fail(f"Y0 Gross Revenue must stay engine value, got formula: {y0}")


async def test_y2_gross_revenue_growth_chain_still_works(
    session: AsyncSession,
) -> None:
    """Phase B growth chain (Y2+ = prior * (1 + s_revenue_growth_rate))
    must keep working on top of the new Y1 input formula."""
    scenario = await _seed_with_one_stream_one_opex(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)

    ws = wb["Underwriting Pro Forma"]
    gr_row = _find_row(ws, "Gross Revenue")
    # Y2 = column 4. Should be ``=C{gr_row}*(1+s_revenue_growth_rate)``.
    y2 = ws.cell(row=gr_row, column=4).value
    assert isinstance(y2, str) and y2.startswith("="), (
        f"Y2 Gross Revenue must be a formula, got {y2!r}"
    )
    assert "s_revenue_growth_rate" in y2, (
        f"Y2 formula must reference scenario growth rate: {y2}"
    )


async def _seed_multi_project_duplicate_stream_labels(session: AsyncSession):
    """Two projects, each with a stream labeled '1BR Units' — verifies
    cross-project slug collision resolves with _2 suffix."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="Multi-Proj Dup Labels")
    deal_model, _, stream, opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    # Activate primary stream + opex in stabilized phase (see
    # _seed_with_one_stream_one_opex for the why).
    stream.active_in_phases = ["stabilized"]
    opex.active_in_phases = ["stabilized"]
    await session.flush()

    extra = Project(
        id=uuid4(), scenario_id=deal_model.id,
        opportunity_id=None, name="Second",
    )
    session.add(extra)
    await session.flush()
    from app.models.deal import OperationalInputs as _OI
    session.add(_OI(
        id=uuid4(), project_id=extra.id,
        unit_count_new=4, exit_cap_rate_pct=Decimal("5.5"),
    ))
    await session.flush()
    # The seed already added "1BR Units" on the primary; add the same
    # label on Second so the two collide cross-project.
    session.add(IncomeStream(
        id=uuid4(), project_id=extra.id,
        stream_type=IncomeStreamType.residential_rent,
        label="1BR Units",
        unit_count=4, amount_per_unit_monthly=Decimal("1500"),
        stabilized_occupancy_pct=Decimal("95"),
        escalation_rate_pct_annual=Decimal("3.0"),
        active_in_phases=["stabilized"],
    ))
    await session.flush()
    await compute_cash_flows(deal_model.id, session)
    await session.commit()
    return deal_model


async def test_cross_project_duplicate_stream_labels_dedupe_globally(
    session: AsyncSession,
) -> None:
    """Two streams on different projects with the same label must
    resolve to distinct slugs (``1br_units`` + ``1br_units_2``) — not
    silently shadow each other."""
    scenario = await _seed_multi_project_duplicate_stream_labels(session)
    blob = await export_investor_workbook(scenario.id, session)
    wb = load_workbook(BytesIO(blob), data_only=False)

    defined = {name for name in wb.defined_names}
    assert "s_rev_1br_units_unit_count" in defined
    assert "s_rev_1br_units_2_unit_count" in defined, (
        "cross-project label collision must resolve with _2 suffix"
    )

    # Pro Forma Y1 formula must reference BOTH dedup'd cells.
    ws = wb["Underwriting Pro Forma"]
    gr_row = _find_row(ws, "Gross Revenue")
    y1 = ws.cell(row=gr_row, column=3).value
    assert isinstance(y1, str)
    assert "s_rev_1br_units_y1_monthly" in y1
    assert "s_rev_1br_units_2_y1_monthly" in y1
