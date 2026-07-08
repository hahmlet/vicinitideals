"""Integration tests for the model-creation API (app/api/routers/models.py).

This is the "creation API" class of routes that shipped a production
regression with no test coverage. Covers:

  - GET+POST /api/projects/{project_id}/models        (compat alias — Opportunity id)
  - POST     /api/opportunities/{opportunity_id}/models
  - PATCH    /api/models/{model_id}
  - POST     /api/models/{model_id}/use-lines
  - GET      /api/models/{model_id}/use-lines
  - PUT+PATCH /api/models/{model_id}/use-lines/{use_line_id}
  - PUT      /api/models/{model_id}/inputs

Assertions target DB substance (rows created/updated), not just status codes.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, OperationalInputs, Scenario, UseLine
from app.models.project import Project

from tests.conftest import seed_deal_model_with_financials, seed_opportunity, seed_org

pytestmark = pytest.mark.asyncio


async def _seed_opp(session: AsyncSession):
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    return org, user, opp


# ---------------------------------------------------------------------------
# POST /api/opportunities/{opportunity_id}/models
# ---------------------------------------------------------------------------


async def test_create_opportunity_model_creates_deal_scenario_and_project(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user, opp = await _seed_opp(session)
    org_id, user_id, opp_id, opp_name = org.id, user.id, opp.id, opp.name

    resp = await client.post(
        f"/api/opportunities/{opp_id}/models",
        json={
            "name": "Base Case",
            "project_type": "value_add",
            "created_by_user_id": str(user_id),
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Base Case"
    assert body["project_type"] == "value_add"
    model_id = uuid.UUID(body["id"])

    # Scenario persisted, linked to a new Deal in the opportunity's org
    scenario = await session.get(Scenario, model_id)
    assert scenario is not None
    deal = await session.get(Deal, scenario.deal_id)
    assert deal is not None
    assert deal.org_id == org_id
    assert deal.name == opp_name
    assert deal.created_by_user_id == user_id

    # Default Project wired to the opportunity
    project = (
        await session.execute(select(Project).where(Project.scenario_id == model_id))
    ).scalar_one()
    assert project.opportunity_id == opp_id


async def test_create_opportunity_model_unknown_opportunity_404(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        f"/api/opportunities/{uuid.uuid4()}/models",
        json={"name": "X", "project_type": "acquisition"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET+POST /api/projects/{project_id}/models  (backward-compat alias)
# ---------------------------------------------------------------------------


async def test_project_models_alias_create_and_list(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, user, opp = await _seed_opp(session)
    opp_id, user_id = opp.id, user.id

    create = await client.post(
        f"/api/projects/{opp_id}/models",
        json={
            "name": "Alias Created",
            "project_type": "acquisition",
            "created_by_user_id": str(user_id),
        },
    )
    assert create.status_code == 201, create.text
    model_id = create.json()["id"]

    listed = await client.get(f"/api/projects/{opp_id}/models")
    assert listed.status_code == 200, listed.text
    ids = {m["id"] for m in listed.json()}
    assert model_id in ids

    # The non-alias list route sees the same scenario
    listed2 = await client.get(f"/api/opportunities/{opp_id}/models")
    assert listed2.status_code == 200
    assert model_id in {m["id"] for m in listed2.json()}


async def test_list_project_models_unknown_opportunity_404(
    client: AsyncClient,
) -> None:
    resp = await client.get(f"/api/projects/{uuid.uuid4()}/models")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/models/{model_id}
# ---------------------------------------------------------------------------


async def test_patch_model_updates_name_in_db(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    model_id = deal_model.id

    resp = await client.patch(
        f"/api/models/{model_id}",
        json={"name": "Renamed Case", "project_type": "value_add"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Renamed Case"

    session.expire_all()
    row = await session.get(Scenario, model_id)
    assert row.name == "Renamed Case"


async def test_patch_model_name_only_requires_project_type(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Documents CURRENT behavior: DealModelPatchRequest inherits ScenarioBase,
    where project_type is a required field — so a partial PATCH sending only
    {"name": ...} is rejected with 422 even though the route applies
    exclude_unset semantics. A true partial-update schema would accept it.
    """
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)

    resp = await client.patch(
        f"/api/models/{deal_model.id}", json={"name": "Only Name"}
    )
    assert resp.status_code == 422, resp.text


async def test_patch_model_unknown_model_404(client: AsyncClient) -> None:
    resp = await client.patch(
        f"/api/models/{uuid.uuid4()}",
        json={"name": "X", "project_type": "acquisition"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Use lines — POST create / GET list / PUT / PATCH
# ---------------------------------------------------------------------------


async def _seed_model(session: AsyncSession):
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _, _, _ = await seed_deal_model_with_financials(session, opp, user)
    return deal_model


async def test_create_use_line_persists_row(
    client: AsyncClient, session: AsyncSession
) -> None:
    deal_model = await _seed_model(session)
    model_id = deal_model.id

    resp = await client.post(
        f"/api/models/{model_id}/use-lines",
        json={
            "label": "Land Acquisition",
            "phase": "acquisition",
            "amount": "1200000",
            "timing_type": "first_day",
            "cost_category": "acquisition",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    use_line_id = uuid.UUID(body["id"])

    row = await session.get(UseLine, use_line_id)
    assert row is not None
    assert row.label == "Land Acquisition"
    assert Decimal(str(row.amount)) == Decimal("1200000")

    listed = await client.get(f"/api/models/{model_id}/use-lines")
    assert listed.status_code == 200
    assert str(use_line_id) in {u["id"] for u in listed.json()}


async def test_create_use_line_strips_engine_owned_fields(
    client: AsyncClient, session: AsyncSession
) -> None:
    """is_auto_* flags exist on the schema for round-trip fidelity only; the
    public create route must strip them so a client can't forge an
    engine-owned row (which would then be undeletable via the auto-fee guard)."""
    deal_model = await _seed_model(session)

    resp = await client.post(
        f"/api/models/{deal_model.id}/use-lines",
        json={
            "label": "Forged Fee",
            "phase": "construction",
            "amount": "1000",
            "is_auto_dev_fee": True,
        },
    )
    assert resp.status_code == 201, resp.text
    row = await session.get(UseLine, uuid.UUID(resp.json()["id"]))
    assert row.is_auto_dev_fee is False


async def test_update_use_line_put_and_patch(
    client: AsyncClient, session: AsyncSession
) -> None:
    deal_model = await _seed_model(session)
    model_id = deal_model.id

    created = await client.post(
        f"/api/models/{model_id}/use-lines",
        json={"label": "Soft Costs", "phase": "construction", "amount": "50000"},
    )
    assert created.status_code == 201, created.text
    use_line_id = created.json()["id"]

    put = await client.put(
        f"/api/models/{model_id}/use-lines/{use_line_id}",
        json={"amount": "75000", "notes": "revised"},
    )
    assert put.status_code == 200, put.text

    patch = await client.patch(
        f"/api/models/{model_id}/use-lines/{use_line_id}",
        json={"label": "Soft Costs v2"},
    )
    assert patch.status_code == 200, patch.text

    session.expire_all()
    row = await session.get(UseLine, uuid.UUID(use_line_id))
    assert Decimal(str(row.amount)) == Decimal("75000")
    assert row.notes == "revised"
    assert row.label == "Soft Costs v2"


async def test_update_use_line_wrong_model_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A use line belonging to scenario A must not be reachable through
    scenario B's URL (cross-scenario ownership check)."""
    model_a = await _seed_model(session)
    model_b = await _seed_model(session)
    model_a_id, model_b_id = model_a.id, model_b.id

    created = await client.post(
        f"/api/models/{model_a_id}/use-lines",
        json={"label": "A-only", "phase": "acquisition", "amount": "1"},
    )
    use_line_id = created.json()["id"]

    resp = await client.put(
        f"/api/models/{model_b_id}/use-lines/{use_line_id}",
        json={"amount": "999"},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/models/{model_id}/inputs
# ---------------------------------------------------------------------------


async def test_put_inputs_creates_then_updates(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, user, opp = await _seed_opp(session)
    opp_id, user_id = opp.id, user.id

    # Create a model through the API — its default project has no inputs yet
    created = await client.post(
        f"/api/opportunities/{opp_id}/models",
        json={
            "name": "Inputs Test",
            "project_type": "acquisition",
            "created_by_user_id": str(user_id),
        },
    )
    model_id = created.json()["id"]

    first = await client.put(
        f"/api/models/{model_id}/inputs",
        json={"unit_count_new": 12, "purchase_price": "2500000"},
    )
    assert first.status_code == 200, first.text

    project = (
        await session.execute(
            select(Project).where(Project.scenario_id == uuid.UUID(model_id))
        )
    ).scalar_one()
    project_id = project.id
    inputs = (
        await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == project_id)
        )
    ).scalar_one()
    inputs_id = inputs.id
    assert inputs.unit_count_new == 12
    assert Decimal(str(inputs.purchase_price)) == Decimal("2500000")

    # Second PUT updates the same row (upsert, not duplicate)
    second = await client.put(
        f"/api/models/{model_id}/inputs",
        json={"unit_count_new": 20},
    )
    assert second.status_code == 200, second.text

    session.expire_all()
    rows = (
        await session.execute(
            select(OperationalInputs).where(OperationalInputs.project_id == project_id)
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == inputs_id
    assert rows[0].unit_count_new == 20
    # Field not sent on second PUT is preserved (exclude_unset)
    assert Decimal(str(rows[0].purchase_price)) == Decimal("2500000")


async def test_put_inputs_strips_engine_owned_noi_auto_seeded(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, inputs, _, _ = await seed_deal_model_with_financials(session, opp, user)
    model_id, inputs_id = deal_model.id, inputs.id

    resp = await client.put(
        f"/api/models/{model_id}/inputs",
        json={"unit_count_new": 9, "noi_auto_seeded": True},
    )
    assert resp.status_code == 200, resp.text

    session.expire_all()
    row = await session.get(OperationalInputs, inputs_id)
    assert row.unit_count_new == 9
    assert bool(row.noi_auto_seeded) is False
