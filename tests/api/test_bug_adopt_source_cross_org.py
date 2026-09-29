"""Bug: GET/POST /ui/models/{id}/projects/{project_id}/adopt-source had no org guard.

The routes only checked that the project belonged to the model, so a user
of another org could list the model's Sources (labels, rates, amounts) and
attach one of them to a project -- a write to another org's capital stack.
Fixed with an org check (404, same as an unknown project).
Router: app/api/routers/ui_model_builder.py (adopt_source_modal,
adopt_source_write; guard now shared as ui_helpers._model_in_user_org).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule, CapitalModuleProject
from app.models.project import Project

from tests.conftest import seed_deal_model, seed_opportunity, seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


async def test_adopt_source_other_org_cannot_read_or_write(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    scen = await seed_deal_model(session, opp, user)
    p1 = Project(id=uuid.uuid4(), scenario_id=scen.id, opportunity_id=opp.id, name="Phase 1")
    p2 = Project(id=uuid.uuid4(), scenario_id=scen.id, opportunity_id=opp.id, name="Phase 2")
    session.add_all([p1, p2])
    mod = CapitalModule(scenario_id=scen.id, label="Secret Bank Loan", vehicle_type="debt",
                        stack_position=1, source={"amount": "900000"})
    session.add(mod)
    await session.flush()
    session.add(CapitalModuleProject(capital_module_id=mod.id, project_id=p1.id,
                                     amount=Decimal("900000"), auto_size=False))
    _other_org, intruder = await seed_org(session)
    await session.commit()
    model_id, p2_id, mod_id, owner_id = scen.id, p2.id, mod.id, user.id
    url = f"/ui/models/{model_id}/projects/{p2_id}/adopt-source"
    hx = {"hx-request": "true"}

    set_client_auth(client, intruder.id)
    resp = await client.get(url, headers=hx)
    assert resp.status_code == 404
    assert "Secret Bank Loan" not in resp.text

    resp = await client.post(url, data={"source_id": str(mod_id)}, headers=hx)
    assert resp.status_code == 404
    session.expire_all()
    rows = list((await session.execute(
        select(CapitalModuleProject).where(CapitalModuleProject.project_id == p2_id)
    )).scalars())
    assert rows == []

    # The owner still can.
    set_client_auth(client, owner_id)
    resp = await client.get(url, headers=hx)
    assert resp.status_code == 200 and "Secret Bank Loan" in resp.text
