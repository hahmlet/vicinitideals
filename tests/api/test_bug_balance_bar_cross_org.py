"""Bug: GET /ui/models/{id}/balance-bar leaked another org's Sources-vs-Uses
numbers.

balance-bar is a deprecated alias that delegates to the calc-status pill
(GET /ui/models/{id}/calc-status), and neither route checked that the model
belongs to the signed-in user's org, so a user of org B who knew a model id
of org A got org A's dollar gap ("-$250,000 Sources Gap"). Fixed with the
shared org guard ``ui_helpers._model_in_user_org`` across the read-only
/ui/models/{id}/... panels (404, same as an unknown model); the sibling
panels are covered in tests/api/test_model_routes_cross_org.py.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule, CapitalModuleProject
from app.models.deal import UseLine, UseLinePhase
from app.models.project import Project

from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
    set_client_auth,
)

pytestmark = pytest.mark.asyncio


async def test_balance_bar_hides_other_orgs_numbers(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    scen, _i, _inc, _opx = await seed_deal_model_with_financials(session, opp, user)
    project = (
        await session.execute(select(Project).where(Project.scenario_id == scen.id))
    ).scalar_one()
    session.add(UseLine(project_id=project.id, label="Purchase Price",
                        phase=UseLinePhase.acquisition, amount=Decimal("1000000"),
                        timing_type="first_day"))
    mod = CapitalModule(scenario_id=scen.id, label="LP Equity", vehicle_type="equity",
                        stack_position=1, source={"amount": "750000"})
    session.add(mod)
    await session.flush()
    session.add(CapitalModuleProject(capital_module_id=mod.id, project_id=project.id,
                                     amount=Decimal("750000"), auto_size=False))
    _other_org, intruder = await seed_org(session)
    await session.commit()
    model_id, intruder_id = scen.id, intruder.id

    # Sanity: the owner sees the gap, so absence below is the guard, not
    # an empty pill.
    set_client_auth(client, user.id)
    owner = await client.get(f"/ui/models/{model_id}/balance-bar", headers={"hx-request": "true"})
    assert "-$250,000 Sources Gap" in owner.text

    set_client_auth(client, intruder_id)
    resp = await client.get(f"/ui/models/{model_id}/balance-bar", headers={"hx-request": "true"})
    assert resp.status_code == 404
    assert "250,000" not in resp.text
