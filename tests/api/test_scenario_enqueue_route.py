"""POST /api/projects/{opportunity_id}/scenarios -- the sensitivity-sweep enqueue.

test_routers.py covers the queued happy path and the 400 range guards. This
file covers what is left: unknown ids, a malformed body, the no-broker fallback
(the sweep runs on the API's own event loop instead), and the pairing between
the opportunity in the URL and the financial scenario in the body.

Celery is always mocked; nothing here reaches Redis or runs the engine.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, ProjectType, Scenario
from app.models.project import Project
from app.models.scenario import Sensitivity, SensitivityStatus
from tests.conftest import seed_opportunity, seed_org

pytestmark = pytest.mark.asyncio

VALID = {
    "variable": "operational.exit_cap_rate_pct",
    "range_min": "4.5",
    "range_max": "6.0",
    "range_steps": 4,
}


async def _stack(session: AsyncSession, name: str = "Sweep"):
    """Org -> Opportunity + Deal -> Scenario -> Project linking the two."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user, name=f"{name} Opp")
    deal = Deal(org_id=org.id, name=f"{name} Deal", created_by_user_id=user.id)
    session.add(deal)
    await session.flush()
    model = Scenario(
        deal_id=deal.id, created_by_user_id=user.id, name=name,
        project_type=ProjectType.acquisition, version=1, is_active=True,
    )
    session.add(model)
    await session.flush()
    session.add(Project(scenario_id=model.id, opportunity_id=opp.id, name="Default Project"))
    await session.commit()
    return user, opp, model


def _hdr(auth_headers: dict[str, str], user) -> dict[str, str]:
    return {**auth_headers, "X-User-ID": str(user.id)}


async def test_unknown_opportunity_and_scenario_404(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    user, opp, model = await _stack(session)
    with patch("app.api.routers.scenarios.sweep_variable.apply_async") as apply_async:
        r1 = await client.post(
            f"/api/projects/{uuid4()}/scenarios",
            json={**VALID, "scenario_id": str(model.id)},
            headers=_hdr(auth_headers, user),
        )
        r2 = await client.post(
            f"/api/projects/{opp.id}/scenarios",
            json={**VALID, "scenario_id": str(uuid4())},
            headers=_hdr(auth_headers, user),
        )
    assert r1.status_code == 404 and r1.json()["message"] == "Opportunity not found"
    assert r2.status_code == 404 and r2.json()["message"] == "Financial scenario not found"
    apply_async.assert_not_called()
    assert (await session.execute(select(Sensitivity))).scalars().all() == []


async def test_malformed_body_422(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    user, opp, model = await _stack(session)
    with patch("app.api.routers.scenarios.sweep_variable.apply_async") as apply_async:
        missing = await client.post(
            f"/api/projects/{opp.id}/scenarios",
            json={"scenario_id": str(model.id)},
            headers=_hdr(auth_headers, user),
        )
        not_a_number = await client.post(
            f"/api/projects/{opp.id}/scenarios",
            json={**VALID, "scenario_id": str(model.id), "range_min": "low"},
            headers=_hdr(auth_headers, user),
        )
    assert missing.status_code == 422
    assert not_a_number.status_code == 422
    apply_async.assert_not_called()


async def test_broker_down_runs_the_sweep_in_process(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    """When Celery cannot take the job the API still answers 201 and runs the
    sweep itself, under a task id it names after the sensitivity."""
    user, opp, model = await _stack(session)
    dispatch = AsyncMock()
    with (
        patch(
            "app.api.routers.scenarios.sweep_variable.apply_async",
            side_effect=ConnectionError("redis unreachable"),
        ),
        patch("app.api.routers.scenarios._dispatch_scenario_sweep", dispatch),
    ):
        resp = await client.post(
            f"/api/projects/{opp.id}/scenarios",
            json={**VALID, "scenario_id": str(model.id)},
            headers=_hdr(auth_headers, user),
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        # Let the fire-and-forget task run while the patch is still active.
        import asyncio

        await asyncio.sleep(0)

    sensitivity_id = body["scenario_id"]
    assert body["status"] == "queued"
    assert body["task_id"] == f"sensitivity-{sensitivity_id}"
    dispatch.assert_awaited_once_with(
        sensitivity_id, task_id=body["task_id"], trace_id=body["trace_id"]
    )

    row = (await session.execute(select(Sensitivity))).scalar_one()
    await session.refresh(row)
    assert str(row.id) == sensitivity_id
    assert row.status == SensitivityStatus.running
    assert row.celery_task_id == body["task_id"]
    assert row.opportunity_id == opp.id
    assert row.scenario_id == model.id
    assert row.created_by_user_id == user.id


async def test_scenario_of_another_opportunity_is_refused(
    client: AsyncClient, session: AsyncSession, auth_headers: dict[str, str]
) -> None:
    """The sweep runs against the scenario in the body but is filed under the
    opportunity in the URL. A scenario no project of that opportunity uses
    produced a sweep labelled with the wrong property."""
    user, opp, _model = await _stack(session, "Mine")
    _u2, _opp2, other_model = await _stack(session, "Theirs")
    with patch("app.api.routers.scenarios.sweep_variable.apply_async") as apply_async:
        resp = await client.post(
            f"/api/projects/{opp.id}/scenarios",
            json={**VALID, "scenario_id": str(other_model.id)},
            headers=_hdr(auth_headers, user),
        )
    assert resp.status_code == 404
    assert resp.json()["message"] == "Financial scenario not found"
    apply_async.assert_not_called()
    assert (await session.execute(select(Sensitivity))).scalars().all() == []
