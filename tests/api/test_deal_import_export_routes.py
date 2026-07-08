"""Integration tests for deal export/import (app/api/routers/deals.py) and
portfolio creation (app/api/routers/portfolios.py).

Covers:
  - GET  /api/deals/{deal_id}/export/json   — org-scoped portable export
  - POST /api/deals/import/json             — round-trip: export then re-import
  - POST /api/portfolios
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, IncomeStream, Scenario, UseLine
from app.models.portfolio import Portfolio
from app.models.project import Project

from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
)

pytestmark = pytest.mark.asyncio


async def _seed_exportable_deal(session: AsyncSession):
    """Org + user + a deal with financial substance (inputs, income, opex,
    one use line). Returns plain values (org_id, user_id, deal_id, model_id)."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _inputs, _income, _opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == deal_model.id)
        )
    ).scalar_one()
    session.add(
        UseLine(
            project_id=project.id,
            label="Acquisition",
            phase="acquisition",
            amount=Decimal("1000000"),
            cost_category="acquisition",
            timing_type="first_day",
        )
    )
    await session.flush()
    return org.id, user.id, deal_model.deal_id, deal_model.id


# ---------------------------------------------------------------------------
# GET /api/deals/{deal_id}/export/json
# ---------------------------------------------------------------------------


async def test_export_deal_json_shape(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org_id, user_id, deal_id, _model_id = await _seed_exportable_deal(session)
    client.headers["X-User-ID"] = str(user_id)

    resp = await client.get(f"/api/deals/{deal_id}/export/json")
    assert resp.status_code == 200, resp.text
    payload = resp.json()

    assert "export_version" in payload
    assert payload["deal"]["name"] == "Base Case"
    scenarios = payload.get("scenarios") or payload["deal"].get("scenarios")
    assert scenarios, f"export carries no scenarios: {list(payload.keys())}"


async def test_export_deal_wrong_org_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org_id, _user_id, deal_id, _model_id = await _seed_exportable_deal(session)
    _other_org, other_user = await seed_org(session)
    await session.flush()

    client.headers["X-User-ID"] = str(other_user.id)
    resp = await client.get(f"/api/deals/{deal_id}/export/json")
    assert resp.status_code == 404


async def test_export_unknown_deal_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)
    await session.flush()
    client.headers["X-User-ID"] = str(user.id)
    resp = await client.get(f"/api/deals/{uuid.uuid4()}/export/json")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/deals/import/json — export → re-import round-trip
# ---------------------------------------------------------------------------


async def test_import_deal_round_trip(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_id, user_id, deal_id, model_id = await _seed_exportable_deal(session)
    client.headers["X-User-ID"] = str(user_id)

    exported = await client.get(f"/api/deals/{deal_id}/export/json")
    assert exported.status_code == 200, exported.text
    payload = exported.json()

    imported = await client.post("/api/deals/import/json", json=payload)
    assert imported.status_code == 201, imported.text
    new_deal_id = uuid.UUID(imported.json()["deal_id"])
    assert new_deal_id != deal_id

    # New Deal row in the caller's org, attributed to the caller
    new_deal = await session.get(Deal, new_deal_id)
    assert new_deal is not None
    assert new_deal.org_id == org_id
    assert new_deal.created_by_user_id == user_id
    assert new_deal.name == "Base Case"

    # Scenario count matches the source deal
    src_scenarios = (
        await session.execute(select(Scenario).where(Scenario.deal_id == deal_id))
    ).scalars().all()
    new_scenarios = (
        await session.execute(select(Scenario).where(Scenario.deal_id == new_deal_id))
    ).scalars().all()
    assert len(new_scenarios) == len(src_scenarios) == 1

    # Financial substance survived: project, use line amount, income stream
    new_model_id = new_scenarios[0].id
    assert new_model_id != model_id
    new_projects = (
        await session.execute(
            select(Project).where(Project.scenario_id == new_model_id)
        )
    ).scalars().all()
    assert len(new_projects) == 1
    new_pid = new_projects[0].id

    new_lines = (
        await session.execute(select(UseLine).where(UseLine.project_id == new_pid))
    ).scalars().all()
    assert Decimal("1000000") in {Decimal(str(line.amount)) for line in new_lines}

    new_streams = (
        await session.execute(
            select(IncomeStream).where(IncomeStream.project_id == new_pid)
        )
    ).scalars().all()
    assert len(new_streams) == 1
    assert new_streams[0].label == "1BR Units"


async def test_import_deal_round_trip_with_updated_at_stripped(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Same round-trip as above, but with the updated_at key removed from each
    project's operational_inputs — the one key that trips the import bug
    documented on test_import_deal_round_trip. Guards the rest of the import
    path (Deal/Scenario/Project/UseLine/IncomeStream reconstruction) today.
    """
    org_id, user_id, deal_id, _model_id = await _seed_exportable_deal(session)
    client.headers["X-User-ID"] = str(user_id)

    exported = await client.get(f"/api/deals/{deal_id}/export/json")
    assert exported.status_code == 200, exported.text
    payload = exported.json()
    for scenario in payload["deal"].get("scenarios") or []:
        for proj in scenario.get("projects") or []:
            if proj.get("operational_inputs"):
                proj["operational_inputs"].pop("updated_at", None)

    imported = await client.post("/api/deals/import/json", json=payload)
    assert imported.status_code == 201, imported.text
    new_deal_id = uuid.UUID(imported.json()["deal_id"])

    new_deal = await session.get(Deal, new_deal_id)
    assert new_deal is not None
    assert new_deal.org_id == org_id
    assert new_deal.name == "Base Case"

    new_scenarios = (
        await session.execute(select(Scenario).where(Scenario.deal_id == new_deal_id))
    ).scalars().all()
    assert len(new_scenarios) == 1
    new_projects = (
        await session.execute(
            select(Project).where(Project.scenario_id == new_scenarios[0].id)
        )
    ).scalars().all()
    assert len(new_projects) == 1
    new_pid = new_projects[0].id

    new_lines = (
        await session.execute(select(UseLine).where(UseLine.project_id == new_pid))
    ).scalars().all()
    assert Decimal("1000000") in {Decimal(str(line.amount)) for line in new_lines}

    new_streams = (
        await session.execute(
            select(IncomeStream).where(IncomeStream.project_id == new_pid)
        )
    ).scalars().all()
    assert len(new_streams) == 1
    assert new_streams[0].label == "1BR Units"


async def test_import_deal_bad_version_400(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)
    await session.flush()
    client.headers["X-User-ID"] = str(user.id)

    resp = await client.post(
        "/api/deals/import/json",
        json={"export_version": "deal-v999", "deal": {"name": "X"}},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/portfolios
# ---------------------------------------------------------------------------


async def test_create_portfolio_persists_row(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, _user = await seed_org(session)
    org_id = org.id

    resp = await client.post(
        "/api/portfolios",
        json={"name": "East Metro Holdings", "org_id": str(org_id)},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "East Metro Holdings"
    assert body["org_id"] == str(org_id)

    row = await session.get(Portfolio, uuid.UUID(body["id"]))
    assert row is not None
    assert row.name == "East Metro Holdings"
    assert row.org_id == org_id

    # Shows up in the list route with a zero project count
    listed = await client.get("/api/portfolios", params={"org_id": str(org_id)})
    assert listed.status_code == 200
    match = next(p for p in listed.json() if p["id"] == body["id"])
    assert match["project_count"] == 0


async def test_create_portfolio_unknown_org_404(client: AsyncClient) -> None:
    resp = await client.post(
        "/api/portfolios",
        json={"name": "Ghost Portfolio", "org_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404
