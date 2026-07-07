"""REST/MCP DrawSource CRUD — Slice 5 (REST parity).

Covers:
- Round-trip: create (auto sort_order) → list → update window/commitment → delete
- 404 scoping on wrong / missing model_id
- The UI and REST surfaces share app/services/draw_sources.py, so the
  round-trip here also exercises the code path the builder UI runs.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import DrawSource

pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


async def _seed_model(session: AsyncSession):
    from tests.conftest import (
        seed_deal_model_with_financials,
        seed_opportunity,
        seed_org,
    )

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    return org, user, opp, deal_model


async def test_draw_source_crud_roundtrip(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, _, _, deal_model = await _seed_model(session)

    created = await client.post(
        f"/api/models/{deal_model.id}/draw-sources",
        json={
            "label": "LP Equity",
            "source_type": "equity",
            "active_from_milestone": "close",
            "active_to_milestone": "construction",
            "total_commitment": "2500000",
        },
    )
    assert created.status_code == 201, created.text
    first = created.json()
    assert first["label"] == "LP Equity"
    assert first["sort_order"] == 1  # appended after max (none) → 1
    assert Decimal(str(first["total_commitment"])) == Decimal("2500000")

    second = (await client.post(
        f"/api/models/{deal_model.id}/draw-sources",
        json={
            "label": "Construction Loan",
            "source_type": "debt",
            "annual_interest_rate": "6.5",
            "draw_every_n_months": 0,  # normalized to 1 (same as UI handler)
            "active_from_milestone": "construction",
            "active_to_milestone": "operation_lease_up",
        },
    )).json()
    assert second["sort_order"] == 2
    assert second["draw_every_n_months"] == 1

    listed = (await client.get(f"/api/models/{deal_model.id}/draw-sources")).json()
    assert [d["label"] for d in listed] == ["LP Equity", "Construction Loan"]

    # Update the active window + commitment (same fields the UI PATCH sets).
    updated = await client.patch(
        f"/api/models/{deal_model.id}/draw-sources/{first['id']}",
        json={
            "active_from_milestone": "pre_development",
            "active_to_milestone": "operation_stabilized",
            "total_commitment": "3000000",
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["active_from_milestone"] == "pre_development"
    assert body["active_to_milestone"] == "operation_stabilized"
    assert Decimal(str(body["total_commitment"])) == Decimal("3000000")
    assert body["label"] == "LP Equity"  # untouched fields survive

    model_db_id = deal_model.id  # capture before expire_all (async lazy-load)
    deleted = await client.delete(
        f"/api/models/{deal_model.id}/draw-sources/{first['id']}"
    )
    assert deleted.status_code == 204

    session.expire_all()
    remaining = list((await session.execute(
        select(DrawSource).where(DrawSource.scenario_id == model_db_id)
    )).scalars())
    assert [d.label for d in remaining] == ["Construction Loan"]


async def test_draw_source_404_on_wrong_model(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user, _, deal_model = await _seed_model(session)

    created = (await client.post(
        f"/api/models/{deal_model.id}/draw-sources",
        json={
            "label": "LP Equity",
            "active_from_milestone": "close",
            "active_to_milestone": "construction",
        },
    )).json()

    missing_model = uuid.uuid4()
    assert (
        await client.get(f"/api/models/{missing_model}/draw-sources")
    ).status_code == 404
    assert (
        await client.post(
            f"/api/models/{missing_model}/draw-sources",
            json={
                "label": "X",
                "active_from_milestone": "close",
                "active_to_milestone": "close",
            },
        )
    ).status_code == 404

    # A draw source reached through a DIFFERENT (real) model must 404 too.
    from tests.conftest import seed_deal_model_with_financials, seed_opportunity

    other_opp = await seed_opportunity(session, org, user)
    other_model, _, _, _ = await seed_deal_model_with_financials(
        session, other_opp, user
    )
    cross = await client.patch(
        f"/api/models/{other_model.id}/draw-sources/{created['id']}",
        json={"label": "Hijack"},
    )
    assert cross.status_code == 404
    cross_del = await client.delete(
        f"/api/models/{other_model.id}/draw-sources/{created['id']}"
    )
    assert cross_del.status_code == 404

    # Nonexistent source under the right model.
    assert (
        await client.delete(
            f"/api/models/{deal_model.id}/draw-sources/{uuid.uuid4()}"
        )
    ).status_code == 404
