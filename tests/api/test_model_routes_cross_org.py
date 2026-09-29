"""Two-org boundaries for the /ui/models/{id}/... routes that had no org check.

A user of org B who knew a model id of org A could read org A's builder
panels (Sources/Uses gap, nav-card totals, calc-status diagnostics, Source
coverage), open or advance its setup wizard, and queue or read pro forma
parses against it. Each route now answers 404 outside the org, the same as
an unknown model. Shared guard: ``ui_helpers._model_in_user_org``.

Routers: app/api/routers/ui_model_builder.py, ui_wizards.py,
ui_model_outputs.py.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capital import CapitalModule, CapitalModuleProject
from app.models.deal import OperationalInputs, Scenario
from app.models.project import Project

from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
    set_client_auth,
)

pytestmark = pytest.mark.asyncio

_HX = {"hx-request": "true"}
_SECRET = "Secret Harbor Bank"


class _FakeRedis:
    def __init__(self, store: dict, decode_responses: bool):
        self._store = store
        self._decode = decode_responses

    def _out(self, val):
        if val is None:
            return None
        if self._decode:
            return val.decode() if isinstance(val, (bytes, bytearray)) else val
        return val if isinstance(val, (bytes, bytearray)) else str(val).encode()

    def get(self, key):
        return self._out(self._store.get(key))

    def getdel(self, key):
        return self._out(self._store.pop(key, None))

    def set(self, key, value, ex=None):
        if isinstance(value, str):
            value = value.encode()
        self._store[key] = bytes(value)
        return True

    def delete(self, *keys):
        return sum(1 for k in keys if self._store.pop(k, None) is not None)


@pytest.fixture
def redis_store(monkeypatch) -> dict:
    import redis  # type: ignore

    store: dict = {}

    def _from_url(_url, decode_responses: bool = False, **_kw):
        return _FakeRedis(store, decode_responses)

    monkeypatch.setattr(redis, "from_url", _from_url)
    return store


@pytest.fixture
def celery_calls(monkeypatch) -> list[tuple[str, dict]]:
    from app.tasks.celery_app import celery_app

    calls: list[tuple[str, dict]] = []

    def _fake_send_task(name, args=None, kwargs=None, **_kw):
        calls.append((name, dict(kwargs or {})))
        return None

    monkeypatch.setattr(celery_app, "send_task", _fake_send_task)
    return calls


async def _two_orgs(session: AsyncSession) -> dict:
    """Org A owns a financial-seeded model with one named Source; org B has
    one user and nothing else. Returns plain ids."""
    org, owner = await seed_org(session)
    opp = await seed_opportunity(session, org, owner)
    scen, _i, _inc, _opx = await seed_deal_model_with_financials(session, opp, owner)
    project = (
        await session.execute(select(Project).where(Project.scenario_id == scen.id))
    ).scalar_one()
    mod = CapitalModule(scenario_id=scen.id, label=_SECRET, vehicle_type="debt",
                        stack_position=1, source={"amount": "900000"})
    session.add(mod)
    await session.flush()
    session.add(CapitalModuleProject(capital_module_id=mod.id, project_id=project.id,
                                     amount=Decimal("900000"), auto_size=False))
    _other_org, intruder = await seed_org(session)
    await session.commit()
    return {
        "model_id": scen.id, "project_id": project.id, "source_id": mod.id,
        "owner_id": owner.id, "intruder_id": intruder.id,
    }


# ---------------------------------------------------------------------------
# Read-only builder panels (ui_model_builder.py)
# ---------------------------------------------------------------------------

_READ_PANELS = [
    "/ui/panel/{model_id}?module=sources",
    "/ui/models/{model_id}/sources/{source_id}/coverage",
    "/ui/models/{model_id}/calc-status",
    "/ui/models/{model_id}/calc-status/modal",
    "/ui/models/{model_id}/balance-bar",
    "/ui/models/{model_id}/module-nav",
    "/ui/models/{model_id}/setup",
    "/ui/models/{model_id}/proforma-skip",
    "/ui/models/{model_id}/proforma-restart",
    "/ui/models/{model_id}/proforma-resume",
]


@pytest.mark.parametrize("path", _READ_PANELS)
async def test_read_panel_is_404_for_another_org(
    client: AsyncClient, session: AsyncSession, redis_store, path: str
) -> None:
    ids = await _two_orgs(session)
    url = path.format(**ids)

    # Sanity: the owner gets the panel, so the 404 below is the guard.
    set_client_auth(client, ids["owner_id"])
    owner = await client.get(url, headers=_HX)
    assert owner.status_code == 200, owner.text[:300]

    set_client_auth(client, ids["intruder_id"])
    resp = await client.get(url, headers=_HX)
    assert resp.status_code == 404
    assert _SECRET not in resp.text
    assert "900,000" not in resp.text


async def test_panel_owner_sees_source_intruder_does_not(
    client: AsyncClient, session: AsyncSession
) -> None:
    ids = await _two_orgs(session)
    url = f"/ui/models/{ids['model_id']}/sources/{ids['source_id']}/coverage"
    set_client_auth(client, ids["owner_id"])
    assert _SECRET in (await client.get(url, headers=_HX)).text
    set_client_auth(client, ids["intruder_id"])
    assert _SECRET not in (await client.get(url, headers=_HX)).text


async def test_add_project_search_is_404_for_another_orgs_scenario(
    client: AsyncClient, session: AsyncSession
) -> None:
    ids = await _two_orgs(session)
    url = f"/ui/deals/{ids['model_id']}/add-project/search"
    set_client_auth(client, ids["owner_id"])
    assert (await client.get(url, params={"q": "main"}, headers=_HX)).status_code == 200
    set_client_auth(client, ids["intruder_id"])
    assert (await client.get(url, params={"q": "main"}, headers=_HX)).status_code == 404


# ---------------------------------------------------------------------------
# Setup wizard writes (ui_wizards.py)
# ---------------------------------------------------------------------------


async def test_setup_wizard_step_and_complete_are_404_for_another_org(
    client: AsyncClient, session: AsyncSession
) -> None:
    ids = await _two_orgs(session)
    model_id = ids["model_id"]
    set_client_auth(client, ids["intruder_id"])

    resp = await client.post(
        f"/ui/models/{model_id}/setup/step",
        data={"step": "2", "debt_types": "permanent_debt"}, headers=_HX,
    )
    assert resp.status_code == 404

    resp = await client.post(f"/ui/models/{model_id}/setup/complete", data={}, headers=_HX)
    assert resp.status_code == 404

    session.expire_all()
    scen = await session.get(Scenario, model_id)
    assert scen is not None
    inputs = (await session.execute(
        select(OperationalInputs).where(OperationalInputs.project_id == ids["project_id"])
    )).scalar_one_or_none()
    assert inputs is None or not (inputs.debt_types or [])
    mods = list((await session.execute(
        select(CapitalModule).where(CapitalModule.scenario_id == model_id)
    )).scalars())
    assert [m.label for m in mods] == [_SECRET]


# ---------------------------------------------------------------------------
# Pro forma parse queue / results (ui_model_outputs.py)
# ---------------------------------------------------------------------------


async def test_proforma_uploads_do_not_queue_for_another_org(
    client: AsyncClient, session: AsyncSession, redis_store, celery_calls
) -> None:
    ids = await _two_orgs(session)
    model_id = ids["model_id"]
    redis_store["proforma:t1:file"] = b"%PDF-fake"
    redis_store["proforma:t1:kind"] = b"doc"
    set_client_auth(client, ids["intruder_id"])

    posts = [
        ("upload-proforma", {"task_id": "t1", "revenue_sheet": "Rent"}),
        ("upload-proforma-doc", {"task_id": "t1", "revenue_enabled": "on"}),
        ("upload-proforma-multi", {"task_id_0": "t1", "file_kind_0": "doc"}),
        ("proforma-reanalyze", {"task_id": "t1"}),
        ("proforma-purge-cache", {"task_id": "t1", "file_hash": "a" * 64}),
    ]
    for route, data in posts:
        resp = await client.post(f"/ui/models/{model_id}/{route}", data=data, headers=_HX)
        assert resp.status_code == 404, route

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-preflight",
        files={"file": ("om.pdf", b"%PDF-fake", "application/pdf")}, headers=_HX,
    )
    assert resp.status_code == 404

    assert celery_calls == []
    assert "proforma:t1:email_config" not in redis_store


async def test_proforma_status_hides_results_from_another_org(
    client: AsyncClient, session: AsyncSession, redis_store
) -> None:
    ids = await _two_orgs(session)
    model_id = ids["model_id"]
    redis_store["proforma:t2:progress"] = json.dumps({"status": "done"}).encode()
    redis_store["proforma:t2:result"] = json.dumps({
        "unit_types": [{"name": "Penthouse Omega", "count": 1, "avg_sqft": 900,
                        "avg_monthly_rent": 1875, "confidence": 0.9}],
        "expense_lines": [], "warnings": [],
    }).encode()
    url = f"/ui/models/{model_id}/proforma-status/t2"

    set_client_auth(client, ids["owner_id"])
    owner = await client.get(url, headers=_HX)
    assert owner.status_code == 200 and "Penthouse Omega" in owner.text

    set_client_auth(client, ids["intruder_id"])
    resp = await client.get(url, headers=_HX)
    assert resp.status_code == 404
    assert "Penthouse Omega" not in resp.text
