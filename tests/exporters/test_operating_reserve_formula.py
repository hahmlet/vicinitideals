"""Operating Reserve UseLine on the S&U sheet must become a formula:
``=s_operating_reserve_months * s_y1_opex / 12``.

Closes the user-reported gap where editing the Operating Reserve months
input on Assumptions didn't ripple into the Sources & Uses page.

Guards three contracts:

  1. The Operating Reserve cell is a formula, not a scalar
  2. The Y1 OpEx defined name ``s_y1_opex`` is registered on every
     profile that renders S&U (so the formula isn't dangling)
  3. The formula references both ``s_operating_reserve_months`` and
     ``s_y1_opex`` (catches regressions where one operand drops out)
"""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exporters.investor_export import export_investor_workbook
from app.models.deal import UseLine
from app.models.project import Project
from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)


async def _seed_with_op_reserve(session: AsyncSession):
    """Seed a scenario + add an explicit Operating Reserve UseLine."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name="Op-Reserve Smoke")
    deal_model, _, _, _ = await seed_deal_model_with_financials(
        session, opp, user
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()
    session.add(
        UseLine(
            id=uuid4(),
            project_id=project.id,
            label="Operating Reserve",
            cost_category="soft",
            amount=Decimal("48000"),
        )
    )
    await session.flush()
    return deal_model


def _find_op_reserve_cell(ws):
    """Walk col A for a row labeled like ``Operating Reserve``; return col B value."""
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and "operating reserve" in v.lower():
            return ws.cell(row=r, column=2).value
    return None


@pytest.mark.parametrize("profile", ["internal", "lp", "lender", "proforma"])
async def test_operating_reserve_is_formula(
    session: AsyncSession, profile: str
):
    """Every profile that ships S&U renders Operating Reserve as a formula."""
    scenario = await _seed_with_op_reserve(session)
    blob = await export_investor_workbook(
        scenario.id, session, profile=profile,
    )
    wb = load_workbook(BytesIO(blob), data_only=False)

    # Locate the S&U sheet (may be named "Sources & Uses" or similar)
    su_sheet = None
    for name in wb.sheetnames:
        if "Sources" in name and "Uses" in name:
            su_sheet = wb[name]
            break
    assert su_sheet is not None, f"profile={profile} missing S&U sheet"

    value = _find_op_reserve_cell(su_sheet)
    assert isinstance(value, str) and value.startswith("="), (
        f"profile={profile}: Operating Reserve must be a formula; got {value!r}"
    )
    assert "s_operating_reserve_months" in value
    assert "s_y1_opex" in value


@pytest.mark.parametrize("profile", ["internal", "lp", "lender", "proforma"])
async def test_y1_opex_and_reserve_months_names_registered(
    session: AsyncSession, profile: str
):
    """Both operand named ranges must be registered so the formula resolves."""
    scenario = await _seed_with_op_reserve(session)
    blob = await export_investor_workbook(
        scenario.id, session, profile=profile,
    )
    wb = load_workbook(BytesIO(blob), data_only=False)

    assert "s_y1_opex" in wb.defined_names, (
        f"profile={profile} missing s_y1_opex defined name "
        f"(formula would dangle to #NAME?)"
    )
    assert "s_operating_reserve_months" in wb.defined_names, (
        f"profile={profile} missing s_operating_reserve_months defined name"
    )
