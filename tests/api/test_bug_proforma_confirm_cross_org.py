"""Bug: POST /ui/models/{id}/proforma-confirm had no org guard.

Any signed-in user could post a pro forma import against another org's
model and the route would delete and rewrite that model's income streams,
OpEx lines and unit mix. Fixed by the same org check the builder form
route uses (404 "Deal model not found" when the model's Deal is not in the
user's org). Router: app/api/routers/ui_model_outputs.py (proforma_confirm).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import IncomeStream, OperatingExpenseLine
from app.models.project import Project

from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
    set_client_auth,
)

pytestmark = pytest.mark.asyncio


async def test_proforma_confirm_other_org_cannot_overwrite_revenue_or_opex(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    scen, _inputs, _inc, _opx = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(select(Project).where(Project.scenario_id == scen.id))
    ).scalar_one()
    _other_org, intruder = await seed_org(session)
    await session.commit()
    model_id, project_id = scen.id, project.id

    set_client_auth(client, intruder.id)
    resp = await client.post(
        f"/ui/models/{model_id}/proforma-confirm",
        data={
            "rent_type": "in_place",
            "unit_type_include[]": ["0"],
            "unit_type_name[]": ["Studio"],
            "unit_type_count[]": ["1"],
            "unit_type_sqft[]": ["1"],
            "unit_type_rent[]": ["1"],
            "unit_type_mode[]": ["unit"],
            "unit_type_stream_type[]": ["residential_rent"],
            "expense_include[]": [],
            "expense_orig_label[]": ["X"],
            "expense_label[]": ["Utilities"],
            "expense_amount[]": ["1"],
        },
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 404

    session.expire_all()
    streams = list((await session.execute(
        select(IncomeStream).where(IncomeStream.project_id == project_id)
    )).scalars())
    assert [(s.label, s.unit_count, s.amount_per_unit_monthly) for s in streams] == [
        ("1BR Units", 8, Decimal("1450"))
    ]
    lines = list((await session.execute(
        select(OperatingExpenseLine).where(OperatingExpenseLine.project_id == project_id)
    )).scalars())
    assert [(line.label, line.annual_amount) for line in lines] == [
        ("Property Management", Decimal("8640"))
    ]
    assert not (await session.get(Project, project_id)).unit_mix
