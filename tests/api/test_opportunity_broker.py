"""Tie manually-created Opportunities to Brokers.

Covers the broker picker added to the opportunity wizard (create) and the
inline broker editor on the opportunity detail page (edit / clear).
The ``broker_id`` FK + relationship already existed — these tests exercise the
UI wiring that lets a user actually set it.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.broker import Broker
from app.models.opportunity import Opportunity
from tests.conftest import seed_opportunity, seed_org, set_client_auth


async def _broker(session) -> Broker:
    broker = Broker(id=uuid.uuid4(), first_name="Jane", last_name="Doe")
    session.add(broker)
    await session.flush()
    return broker


async def test_wizard_step1_saves_broker(client: AsyncClient, session: AsyncSession):
    org, user = await seed_org(session)
    broker = await _broker(session)
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.post(
        "/ui/opportunities/wizard/step",
        data={
            "step": "1",
            "name": "Manual Broker Oppo",
            "deal_type": "value_add",
            "notes": "",
            "broker_id": str(broker.id),
        },
    )
    assert resp.status_code == 200

    opp = (await session.execute(
        select(Opportunity).where(Opportunity.name == "Manual Broker Oppo")
    )).scalars().first()
    assert opp is not None
    assert opp.broker_id == broker.id


async def test_set_broker_route_updates_then_clears(client: AsyncClient, session: AsyncSession):
    org, user = await seed_org(session)
    broker = await _broker(session)
    opp = await seed_opportunity(session, org, user, name="Edit Broker Oppo")
    await session.commit()
    set_client_auth(client, user.id)

    # Assign a broker (HTMX inline editor).
    r1 = await client.post(
        f"/ui/opportunities/{opp.id}/set-broker",
        data={"broker_id": str(broker.id)},
        headers={"hx-request": "true"},
    )
    assert r1.status_code == 200
    await session.refresh(opp)
    assert opp.broker_id == broker.id

    # Clear it (— None — pick).
    r2 = await client.post(
        f"/ui/opportunities/{opp.id}/set-broker",
        data={"broker_id": ""},
        headers={"hx-request": "true"},
    )
    assert r2.status_code == 200
    await session.refresh(opp)
    assert opp.broker_id is None
