from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from app.models.project import Project
from app.models.scenario_library import ScenarioLibraryEntry
from tests.conftest import seed_deal_model, seed_opportunity, seed_org


pytestmark = pytest.mark.asyncio


async def _auth(client: AsyncClient, user_id: uuid.UUID) -> None:
    client.cookies.set(COOKIE_NAME, create_session_token(user_id))


async def _seed_model_with_project(session: AsyncSession):
    org, user = await seed_org(session)
    user.email = "stephenjketch@gmail.com"
    opp = await seed_opportunity(session, org, user, name="Capture Test Opp")
    model = await seed_deal_model(session, opp, user, name="Capture Test Model")
    project = Project(
        id=uuid.uuid4(),
        scenario_id=model.id,
        opportunity_id=opp.id,
        name="Default Project",
    )
    session.add(project)
    await session.commit()
    return org, user, model


async def test_builder_shows_capture_button_for_stephen(client: AsyncClient, session: AsyncSession) -> None:
    _org, user, model = await _seed_model_with_project(session)
    await _auth(client, user.id)

    response = await client.get(f"/models/{model.id}/builder", follow_redirects=True)

    assert response.status_code == 200
    assert "Create Test Scenario" in response.text


async def test_builder_hides_capture_button_for_other_users(client: AsyncClient, session: AsyncSession) -> None:
    org, user = await seed_org(session)
    user.email = "other@example.com"
    opp = await seed_opportunity(session, org, user, name="No Capture Opp")
    model = await seed_deal_model(session, opp, user, name="No Capture Model")
    project = Project(
        id=uuid.uuid4(),
        scenario_id=model.id,
        opportunity_id=opp.id,
        name="Default Project",
    )
    session.add(project)
    await session.commit()

    await _auth(client, user.id)
    response = await client.get(f"/models/{model.id}/builder", follow_redirects=True)

    assert response.status_code == 200
    assert "Create Test Scenario" not in response.text


async def test_capture_creates_scenario_library_entry(client: AsyncClient, session: AsyncSession) -> None:
    org, user, model = await _seed_model_with_project(session)
    await _auth(client, user.id)

    response = await client.post(
        f"/ui/models/{model.id}/scenario-library",
        data={
            "name": "Regression Case A",
            "tags": "mf,regression",
            "note": "Created from builder",
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    entry_id = uuid.UUID(payload["id"])

    entry = await session.get(ScenarioLibraryEntry, entry_id)
    assert entry is not None
    assert entry.org_id == org.id
    assert entry.name == "Regression Case A"
    assert entry.tags == ["mf", "regression"]
    assert entry.payload_json.get("snapshot_version") == "ui-full-v1"
    assert "portable" in entry.payload_json
    assert "full_snapshot" in entry.payload_json

    # Query sanity: it should appear in org-scoped listing.
    rows = list((await session.execute(
        select(ScenarioLibraryEntry).where(ScenarioLibraryEntry.org_id == org.id)
    )).scalars())
    assert len(rows) == 1


async def test_seed_creates_new_deal_and_tracks_seed_count(client: AsyncClient, session: AsyncSession) -> None:
    _org, user, model = await _seed_model_with_project(session)
    await _auth(client, user.id)

    capture = await client.post(
        f"/ui/models/{model.id}/scenario-library",
        data={
            "name": "Regression Seed Source",
            "tags": "seed,regression",
            "note": "source for seed test",
        },
    )
    assert capture.status_code == 201, capture.text
    entry_id = uuid.UUID(capture.json()["id"])

    seed = await client.post(f"/ui/admin/scenarios/{entry_id}/seed")
    assert seed.status_code == 200, seed.text
    body = seed.json()
    assert body.get("deal_id")
    assert body.get("model_id")
    assert str(body.get("redirect", "")).startswith(f"/models/{body['model_id']}/builder")

    entry = await session.get(ScenarioLibraryEntry, entry_id)
    assert entry is not None
    assert entry.seeded_count == 1
    assert entry.last_seeded_at is not None


async def test_seed_returns_not_found_for_non_manager(client: AsyncClient, session: AsyncSession) -> None:
    _org, stephen, model = await _seed_model_with_project(session)
    await _auth(client, stephen.id)

    capture = await client.post(
        f"/ui/models/{model.id}/scenario-library",
        data={"name": "Seed ACL Case"},
    )
    assert capture.status_code == 201, capture.text
    entry_id = uuid.UUID(capture.json()["id"])

    _org2, other_user = await seed_org(session)
    other_user.org_id = stephen.org_id
    other_user.email = "other@example.com"
    session.add(other_user)
    await session.commit()

    await _auth(client, other_user.id)
    seed = await client.post(f"/ui/admin/scenarios/{entry_id}/seed")
    assert seed.status_code == 404
