"""Integration tests for previously-untested routes in app/api/routers/ui_model_outputs.py.

Covers:
  - POST /ui/models/{id}/proforma-confirm            (IncomeStream / OpEx / unit_mix write)
  - GET  /ui/models/{id}/proforma-status/{task_id}   (poll: queued / running / error / stale / done)
  - GET  /ui/models/{id}/proforma-skip               (wizard -> Step 2)
  - GET  /ui/models/{id}/proforma-restart            (wizard -> Step 1)
  - GET  /ui/models/{id}/proforma-from-staged        (org guard + Redis-staged file dispatch)
  - POST /ui/models/{id}/upload-proforma-doc         (Celery kwargs: 0-based page lists)
  - POST /ui/models/{id}/upload-proforma-multi       (per-file email_config + one task per file)
  - GET  /ui/source-vehicles/{vehicle_id}/prefill    (owner scoping: org vs user vehicles)
  - GET  /ui/models/{id}/history                     (drawer render + org guard)
  - GET  /ui/models/{id}/history/export.json         (structured diff + org guard)

Redis is replaced by an in-memory stand-in (``redis.from_url`` monkeypatched)
and Celery's ``send_task`` by a recorder — same pattern as
tests/api/test_proforma_cache.py. Everything else hits the real test DB.

Cross-org write on proforma-confirm and the manually-added-unit-row drop are
covered in their own tests/api/test_bug_*.py files.
"""

from __future__ import annotations

import json
import time
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import (
    IncomeStream,
    IncomeStreamType,
    OperatingExpenseLine,
    ScenarioSnapshot,
)
from app.models.project import Project
from app.models.source_vehicle import SourceVehicle

from tests.conftest import (
    seed_deal_model_with_financials,
    seed_opportunity,
    seed_org,
    set_client_auth,
)

pytestmark = pytest.mark.asyncio

_HX = {"hx-request": "true"}


# ---------------------------------------------------------------------------
# In-memory Redis + Celery recorder
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


async def _seed_model(session: AsyncSession):
    """Financial-seeded scenario (8 x $1,450 rent stream, $8,640 PM opex line).

    Returns plain ids (org_id, user_id, model_id, project_id)."""
    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal_model, _inputs, _income, _opex = await seed_deal_model_with_financials(
        session, opp, user
    )
    project = (
        await session.execute(select(Project).where(Project.scenario_id == deal_model.id))
    ).scalar_one()
    await session.commit()
    return org.id, user.id, deal_model.id, project.id


async def _streams(session: AsyncSession, project_id) -> list[IncomeStream]:
    session.expire_all()
    return list(
        (
            await session.execute(
                select(IncomeStream)
                .where(IncomeStream.project_id == project_id)
                .order_by(IncomeStream.label)
            )
        ).scalars()
    )


async def _opex(session: AsyncSession, project_id) -> list[OperatingExpenseLine]:
    session.expire_all()
    return list(
        (
            await session.execute(
                select(OperatingExpenseLine)
                .where(OperatingExpenseLine.project_id == project_id)
                .order_by(OperatingExpenseLine.label)
            )
        ).scalars()
    )


# ---------------------------------------------------------------------------
# POST /ui/models/{id}/proforma-confirm
# ---------------------------------------------------------------------------


def _confirm_form(**overrides) -> dict:
    """The review template's parallel arrays: one per-unit row (1BR), one
    flat-rate row (Retail), three expense rows of which the third (Debt
    Service, below the line) is left unchecked."""
    form = {
        "rent_type": "in_place",
        "unit_type_include[]": ["0", "1"],
        "unit_type_name[]": ["1BR", "Retail"],
        "unit_type_count[]": ["6", "0"],
        "unit_type_sqft[]": ["650", "0"],
        "unit_type_rent[]": ["1,250", "2,500"],
        "unit_type_market_rent[]": ["1,400", ""],
        "unit_type_mode[]": ["unit", "flat"],
        "unit_type_stream_type[]": ["commercial_rent", "commercial_rent"],
        "expense_include[]": ["0", "1"],
        "expense_orig_label[]": ["Water/Sewer", "Mgmt Fee", "Debt Service"],
        "expense_label[]": ["Utilities", "Management Fee", "Utilities"],
        "expense_amount[]": ["12,000", "9,500", "60,000"],
    }
    form.update(overrides)
    return form


async def test_proforma_confirm_overwrites_streams_opex_and_unit_mix(
    client: AsyncClient, session: AsyncSession, redis_store
) -> None:
    _org_id, user_id, model_id, project_id = await _seed_model(session)
    set_client_auth(client, user_id)

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-confirm", data=_confirm_form(), headers=_HX
    )
    assert resp.status_code == 200, resp.text[:500]
    # Hands back the wizard at Step 2 (debt types).
    assert 'name="step" value="2"' in resp.text

    streams = await _streams(session, project_id)
    # Seeded "1BR Units" stream is replaced (overwrite semantics).
    assert [s.label for s in streams] == ["1BR Rent", "Retail"]
    unit, flat = streams
    assert unit.stream_type == IncomeStreamType.residential_rent
    assert unit.unit_count == 6
    assert unit.amount_per_unit_monthly == Decimal("1250")
    assert unit.catchup_target_rent == Decimal("1400")
    assert unit.stabilized_occupancy_pct == Decimal("95")
    assert unit.escalation_rate_pct_annual == Decimal("3")
    assert unit.active_in_phases == ["lease_up", "stabilized"]
    assert flat.stream_type == IncomeStreamType.commercial_rent
    assert flat.amount_fixed_monthly == Decimal("2500")
    assert flat.unit_count is None and flat.amount_per_unit_monthly is None
    assert flat.stabilized_occupancy_pct == Decimal("100")

    lines = await _opex(session, project_id)
    # Seeded "Property Management" gone; unchecked Debt Service not written.
    assert [(line.label, line.annual_amount, line.notes) for line in lines] == [
        ("Management Fee", Decimal("9500"), "Mgmt Fee"),
        ("Utilities", Decimal("12000"), "Water/Sewer"),
    ]
    assert sum(line.annual_amount for line in lines) == Decimal("21500")

    project = await session.get(Project, project_id)
    assert len(project.unit_mix) == 1
    row = project.unit_mix[0]
    assert row["label"] == "1BR"
    assert row["unit_count"] == 6
    assert row["avg_sqft"] == 650
    assert row["in_place_rent_per_unit"] == 1250
    assert row["market_rent_per_unit"] == 1400


async def test_proforma_confirm_market_rent_type_and_unchecked_unit_row(
    client: AsyncClient, session: AsyncSession, redis_store
) -> None:
    _org_id, user_id, model_id, project_id = await _seed_model(session)
    set_client_auth(client, user_id)

    form = _confirm_form(
        rent_type="market",
        **{
            "unit_type_include[]": ["0"],  # Retail row unchecked
            "expense_include[]": [],
            "expense_orig_label[]": [],
            "expense_label[]": [],
            "expense_amount[]": [],
        },
    )
    resp = await client.post(f"/ui/models/{model_id}/proforma-confirm", data=form, headers=_HX)
    assert resp.status_code == 200, resp.text[:500]

    streams = await _streams(session, project_id)
    assert [s.label for s in streams] == ["1BR Rent"]
    assert streams[0].amount_per_unit_monthly == Decimal("1250")
    project = await session.get(Project, project_id)
    assert project.unit_mix[0]["market_rent_per_unit"] == 1250
    assert "in_place_rent_per_unit" not in project.unit_mix[0]

    # No expense rows submitted -> existing OpEx left untouched.
    lines = await _opex(session, project_id)
    assert [(line.label, line.annual_amount) for line in lines] == [
        ("Property Management", Decimal("8640"))
    ]


async def test_proforma_confirm_routes_to_project_in_hx_current_url(
    client: AsyncClient, session: AsyncSession, redis_store
) -> None:
    _org_id, user_id, model_id, project_id = await _seed_model(session)
    p1 = await session.get(Project, project_id)
    p2 = Project(
        id=uuid.uuid4(), scenario_id=model_id, opportunity_id=p1.opportunity_id, name="Phase 2"
    )
    session.add(p2)
    await session.commit()
    p2_id = p2.id
    set_client_auth(client, user_id)

    resp = await client.post(
        f"/ui/models/{model_id}/proforma-confirm",
        data=_confirm_form(),
        headers={
            **_HX,
            "HX-Current-URL": f"http://test/models/{model_id}/builder?project={p2_id}",
        },
    )
    assert resp.status_code == 200, resp.text[:500]

    assert [s.label for s in await _streams(session, p2_id)] == ["1BR Rent", "Retail"]
    # Project 1 keeps its seeded rows.
    assert [s.label for s in await _streams(session, project_id)] == ["1BR Units"]
    assert [line.label for line in await _opex(session, project_id)] == ["Property Management"]


async def test_proforma_confirm_unknown_model_404(
    client: AsyncClient, session: AsyncSession, redis_store
) -> None:
    _org_id, user_id, _model_id, _project_id = await _seed_model(session)
    set_client_auth(client, user_id)
    resp = await client.post(
        f"/ui/models/{uuid.uuid4()}/proforma-confirm", data=_confirm_form(), headers=_HX
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /ui/models/{id}/proforma-status/{task_id}
# ---------------------------------------------------------------------------


async def test_proforma_status_states(
    client: AsyncClient, session: AsyncSession, redis_store
) -> None:
    _org_id, user_id, model_id, _project_id = await _seed_model(session)
    set_client_auth(client, user_id)
    tid = "task-abc"
    url = f"/ui/models/{model_id}/proforma-status/{tid}"

    # Nothing in Redis yet -> queued poller (keeps polling this task).
    resp = await client.get(url, headers=_HX)
    assert resp.status_code == 200
    assert f"/proforma-status/{tid}" in resp.text
    assert "Import Failed" not in resp.text

    # Running with a fresh heartbeat -> progress message.
    redis_store[f"proforma:{tid}:progress"] = json.dumps(
        {"status": "running", "step": 2, "total": 3, "message": "Mapping expenses",
         "updated_at": time.time()}
    ).encode()
    resp = await client.get(url, headers=_HX)
    assert "Mapping expenses" in resp.text
    assert "Import Failed" not in resp.text

    # Running but heartbeat older than 180 s -> timed-out error.
    redis_store[f"proforma:{tid}:progress"] = json.dumps(
        {"status": "running", "step": 1, "updated_at": time.time() - 600}
    ).encode()
    resp = await client.get(url, headers=_HX)
    assert "Import Failed" in resp.text
    assert "timed out" in resp.text

    # Worker-reported error.
    redis_store[f"proforma:{tid}:progress"] = json.dumps(
        {"status": "error", "message": "No revenue table found"}
    ).encode()
    resp = await client.get(url, headers=_HX)
    assert "Import Failed" in resp.text
    assert "No revenue table found" in resp.text

    # Done -> review table populated from the stored result.
    redis_store[f"proforma:{tid}:progress"] = json.dumps({"status": "done"}).encode()
    redis_store[f"proforma:{tid}:filename"] = b"om.xlsx"
    redis_store[f"proforma:{tid}:result"] = json.dumps({
        "unit_types": [{"name": "2BR/1BA", "count": 4, "avg_sqft": 900,
                        "avg_monthly_rent": 1875, "confidence": 0.9}],
        "expense_lines": [{"original_label": "Garbage", "mapped_category": "Utilities",
                           "annual_amount": 3300, "confidence": 0.9,
                           "is_operating_expense": True}],
        "warnings": [],
    }).encode()
    resp = await client.get(url, headers=_HX)
    assert resp.status_code == 200
    assert f"/ui/models/{model_id}/proforma-confirm" in resp.text
    assert 'value="2BR/1BA"' in resp.text
    assert 'name="unit_type_rent[]" value="1875"' in resp.text
    assert 'value="Garbage"' in resp.text
    assert 'name="expense_amount[]" value="3300"' in resp.text
    assert "om.xlsx" in resp.text


# ---------------------------------------------------------------------------
# proforma-skip / proforma-restart
# ---------------------------------------------------------------------------


async def test_proforma_skip_returns_wizard_step_2(
    client: AsyncClient, session: AsyncSession, redis_store
) -> None:
    _org_id, user_id, model_id, project_id = await _seed_model(session)
    set_client_auth(client, user_id)
    resp = await client.get(f"/ui/models/{model_id}/proforma-skip", headers=_HX)
    assert resp.status_code == 200, resp.text[:500]
    assert 'name="step" value="2"' in resp.text
    # Skip writes nothing: seeded revenue/opex intact.
    assert [s.label for s in await _streams(session, project_id)] == ["1BR Units"]


async def test_proforma_restart_returns_wizard_step_1(
    client: AsyncClient, session: AsyncSession, redis_store
) -> None:
    _org_id, user_id, model_id, _project_id = await _seed_model(session)
    set_client_auth(client, user_id)
    resp = await client.get(f"/ui/models/{model_id}/proforma-restart", headers=_HX)
    assert resp.status_code == 200, resp.text[:500]
    assert 'name="step" value="1"' in resp.text
    assert 'name="step" value="2"' not in resp.text


# ---------------------------------------------------------------------------
# GET /ui/models/{id}/proforma-from-staged
# ---------------------------------------------------------------------------


async def test_proforma_from_staged_email_config_fast_path(
    client: AsyncClient, session: AsyncSession, redis_store, celery_calls
) -> None:
    org_id, user_id, model_id, _project_id = await _seed_model(session)
    set_client_auth(client, user_id)
    tid = "staged-1"
    redis_store[f"proforma:{tid}:org_id"] = str(org_id).encode()
    redis_store[f"proforma:{tid}:file"] = b"%PDF-fake"
    redis_store[f"proforma:{tid}:email_config"] = json.dumps({
        "file_kind": "doc", "rev_pages": "3-4, 2", "opex_pages": "",
        "import_revenue": True, "import_opex": False,
    }).encode()

    resp = await client.get(
        f"/ui/models/{model_id}/proforma-from-staged", params={"task_id": tid}, headers=_HX
    )
    assert resp.status_code == 200, resp.text[:500]
    assert f"/proforma-status/{tid}" in resp.text
    assert len(celery_calls) == 1
    _name, kw = celery_calls[0]
    assert kw["task_id"] == tid and kw["model_id"] == str(model_id)
    assert kw["file_kind"] == "doc"
    # 1-based "3-4, 2" -> sorted 0-based [1, 2, 3]; empty string -> None.
    assert kw["revenue_pages"] == [1, 2, 3]
    assert kw["opex_pages"] is None
    assert kw["import_opex"] is False


async def test_proforma_from_staged_expired_file(
    client: AsyncClient, session: AsyncSession, redis_store, celery_calls
) -> None:
    _org_id, user_id, model_id, _project_id = await _seed_model(session)
    set_client_auth(client, user_id)
    resp = await client.get(
        f"/ui/models/{model_id}/proforma-from-staged", params={"task_id": "gone"}, headers=_HX
    )
    assert resp.status_code == 200
    assert "expired or not found" in resp.text
    assert celery_calls == []


async def test_proforma_from_staged_rejects_other_orgs_task_and_model(
    client: AsyncClient, session: AsyncSession, redis_store, celery_calls
) -> None:
    _org_id, user_id, model_id, _project_id = await _seed_model(session)
    other_org, other_user = await seed_org(session)
    await session.commit()
    other_org_id, other_user_id = other_org.id, other_user.id

    # Task staged for a different org than the requesting user's -> 404.
    tid = "staged-foreign"
    redis_store[f"proforma:{tid}:org_id"] = str(other_org_id).encode()
    redis_store[f"proforma:{tid}:file"] = b"x"
    set_client_auth(client, user_id)
    resp = await client.get(
        f"/ui/models/{model_id}/proforma-from-staged", params={"task_id": tid}, headers=_HX
    )
    assert resp.status_code == 404

    # A user of another org cannot drive this org's model -> 404.
    set_client_auth(client, other_user_id)
    resp = await client.get(
        f"/ui/models/{model_id}/proforma-from-staged", params={"task_id": tid}, headers=_HX
    )
    assert resp.status_code == 404
    assert celery_calls == []


# ---------------------------------------------------------------------------
# POST upload-proforma-doc / upload-proforma-multi
# ---------------------------------------------------------------------------


async def test_upload_proforma_doc_queues_parse_with_page_lists(
    client: AsyncClient, session: AsyncSession, redis_store, celery_calls
) -> None:
    _org_id, user_id, model_id, _project_id = await _seed_model(session)
    set_client_auth(client, user_id)
    resp = await client.post(
        f"/ui/models/{model_id}/upload-proforma-doc",
        data={"task_id": "doc-1", "revenue_enabled": "on", "opex_enabled": "",
              "revenue_pages": "5-6", "opex_pages": ""},
        headers=_HX,
    )
    assert resp.status_code == 200, resp.text[:500]
    assert "/proforma-status/doc-1" in resp.text
    assert len(celery_calls) == 1
    _name, kw = celery_calls[0]
    assert kw["file_kind"] == "doc"
    assert kw["import_revenue"] is True and kw["import_opex"] is False
    assert kw["revenue_pages"] == [4, 5]
    assert kw["opex_pages"] is None


async def test_upload_proforma_multi_stores_config_and_queues_each_file(
    client: AsyncClient, session: AsyncSession, redis_store, celery_calls
) -> None:
    _org_id, user_id, model_id, _project_id = await _seed_model(session)
    set_client_auth(client, user_id)
    resp = await client.post(
        f"/ui/models/{model_id}/upload-proforma-multi",
        data={
            "task_id_0": "f0", "file_kind_0": "xlsx", "rev_sheet_0": "Rent Roll",
            "rev_range_0": "A1:F20", "opex_sheet_0": "", "opex_range_0": "",
            "task_id_1": "f1", "file_kind_1": "doc", "rev_pages_1": "", "opex_pages_1": "",
        },
        headers=_HX,
    )
    assert resp.status_code == 200, resp.text[:500]
    # Progress poller is for the first file.
    assert "/proforma-status/f0" in resp.text

    assert [kw["task_id"] for _n, kw in celery_calls] == ["f0", "f1"]
    kw0, kw1 = celery_calls[0][1], celery_calls[1][1]
    assert kw0["revenue_sheet"] == "Rent Roll" and kw0["revenue_range"] == "A1:F20"
    assert kw0["import_revenue"] is True and kw0["import_opex"] is False
    # Neither side picked -> both default on.
    assert kw1["import_revenue"] is True and kw1["import_opex"] is True

    cfg0 = json.loads(redis_store["proforma:f0:email_config"])
    assert cfg0["rev_sheet"] == "Rent Roll" and cfg0["import_opex"] is False


async def test_upload_proforma_multi_no_rows_400(
    client: AsyncClient, session: AsyncSession, redis_store, celery_calls
) -> None:
    _org_id, user_id, model_id, _project_id = await _seed_model(session)
    set_client_auth(client, user_id)
    resp = await client.post(
        f"/ui/models/{model_id}/upload-proforma-multi", data={"x": "1"}, headers=_HX
    )
    assert resp.status_code == 400
    assert celery_calls == []


# ---------------------------------------------------------------------------
# GET /ui/source-vehicles/{vehicle_id}/prefill
# ---------------------------------------------------------------------------


async def _seed_vehicle(session, *, scope: str, owner_id, label: str) -> uuid.UUID:
    v = SourceVehicle(
        scope=scope,
        owner_id=owner_id,
        label=label,
        vehicle_type="debt",
        interest_rate_pct=Decimal("6.250000"),
        amort_term_years=30,
        carry_type="io_only",
        source_config={"ltv_pct": 65, "dscr_min": 1.25},
        carry_config={"phases": [{"name": "operation", "carry_type": "pi"}]},
        exit_config={"vehicle": "sale"},
    )
    session.add(v)
    await session.flush()
    return v.id


async def test_prefill_returns_org_vehicle_fields(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    vid = await _seed_vehicle(session, scope="org", owner_id=org.id, label="Bank Perm")
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.get(f"/ui/source-vehicles/{vid}/prefill", headers=_HX)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["vehicle_name"] == "Bank Perm"
    assert body["owner"] == "org"
    assert body["source_interest_rate"] == 6.25
    assert body["amort_term_years"] == 30
    assert body["ltv_pct"] == 65
    assert body["dscr_min"] == 1.25
    # Operation phase overrides the column carry_type; construction falls back.
    assert body["operation_carry_type"] == "pi"
    assert body["construction_carry_type"] == "io_only"
    assert body["exit_vehicle"] == "sale"


async def test_prefill_scopes_to_owner(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_a, user_a = await seed_org(session)
    # Second user in org A — owns a personal vehicle.
    from app.models.org import User

    teammate = User(id=uuid.uuid4(), org_id=org_a.id, name="Teammate", display_color="#000000")
    session.add(teammate)
    org_b, user_b = await seed_org(session)
    await session.flush()
    own_personal = await _seed_vehicle(session, scope="user", owner_id=user_a.id, label="Mine")
    mates_personal = await _seed_vehicle(session, scope="user", owner_id=teammate.id, label="Mate")
    org_b_vehicle = await _seed_vehicle(session, scope="org", owner_id=org_b.id, label="B Perm")
    # A "user" vehicle whose owner_id happens to equal org A's id must not be
    # served as an org vehicle (scope and owner must both match).
    spoof = await _seed_vehicle(session, scope="user", owner_id=org_a.id, label="Spoof")
    await session.commit()
    set_client_auth(client, user_a.id)

    resp = await client.get(f"/ui/source-vehicles/{own_personal}/prefill", headers=_HX)
    assert resp.status_code == 200 and resp.json()["owner"] == "user"
    for vid in (mates_personal, org_b_vehicle, spoof, uuid.uuid4()):
        resp = await client.get(f"/ui/source-vehicles/{vid}/prefill", headers=_HX)
        assert resp.status_code == 404, (vid, resp.text)

    # Org B's own user can read it.
    set_client_auth(client, user_b.id)
    resp = await client.get(f"/ui/source-vehicles/{org_b_vehicle}/prefill", headers=_HX)
    assert resp.status_code == 200 and resp.json()["vehicle_name"] == "B Perm"


async def test_prefill_unauthenticated_401(client: AsyncClient, session: AsyncSession) -> None:
    org, _user = await seed_org(session)
    vid = await _seed_vehicle(session, scope="org", owner_id=org.id, label="X")
    await session.commit()
    resp = await client.get(f"/ui/source-vehicles/{vid}/prefill", headers=_HX)
    assert resp.status_code in (401, 303)
    assert "vehicle_name" not in resp.text


# ---------------------------------------------------------------------------
# GET /ui/models/{id}/history  and  /history/export.json
# ---------------------------------------------------------------------------


async def _seed_snapshots(session: AsyncSession, model_id) -> None:
    session.add_all([
        ScenarioSnapshot(
            scenario_id=model_id, version=1, triggered_by="compute",
            inputs_json={"operational_inputs": {"exit_cap_rate_pct": 5.5}},
            outputs_json={"noi_stabilized": 120000, "dscr": 1.31},
        ),
        ScenarioSnapshot(
            scenario_id=model_id, version=2, triggered_by="compute", label="Higher cap",
            inputs_json={"operational_inputs": {"exit_cap_rate_pct": 6.0}},
            outputs_json={"noi_stabilized": 132000, "dscr": 1.31},
        ),
    ])
    await session.commit()


async def test_history_export_json_structured_diff(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org_id, user_id, model_id, _project_id = await _seed_model(session)
    await _seed_snapshots(session, model_id)
    set_client_auth(client, user_id)

    resp = await client.get(f"/ui/models/{model_id}/history/export.json")
    assert resp.status_code == 200, resp.text
    assert f"history-{model_id}.json" in resp.headers["content-disposition"]
    body = resp.json()
    assert body["scenario_id"] == str(model_id)
    v1, v2 = body["entries"]
    assert v1["version"] == 1 and v1["note"] == "baseline" and v1["input_changes"] == []
    assert v2["version"] == 2 and v2["label"] == "Higher cap"
    changes = {c["field"]: c for c in v2["input_changes"]}
    assert changes["exit_cap_rate_pct"]["before"] == 5.5
    assert changes["exit_cap_rate_pct"]["after"] == 6.0
    # Only the output that moved is reported.
    assert v2["output_changes"] == {"noi_stabilized": {"before": 120000, "after": 132000}}
    assert v2["outputs"]["noi_stabilized"] == 132000


async def test_history_export_json_other_org_forbidden(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org_id, _user_id, model_id, _project_id = await _seed_model(session)
    await _seed_snapshots(session, model_id)
    _other_org, other_user = await seed_org(session)
    await session.commit()
    set_client_auth(client, other_user.id)

    resp = await client.get(f"/ui/models/{model_id}/history/export.json")
    assert resp.status_code == 403
    assert "entries" not in resp.text and "132000" not in resp.text


async def test_history_export_json_unauthenticated_and_missing(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org_id, user_id, model_id, _project_id = await _seed_model(session)
    resp = await client.get(f"/ui/models/{model_id}/history/export.json", headers=_HX)
    assert resp.status_code == 401
    set_client_auth(client, user_id)
    resp = await client.get(f"/ui/models/{uuid.uuid4()}/history/export.json")
    assert resp.status_code == 404


async def test_history_drawer_lists_snapshots_and_guards_org(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org_id, user_id, model_id, _project_id = await _seed_model(session)
    await _seed_snapshots(session, model_id)
    _other_org, other_user = await seed_org(session)
    await session.commit()
    other_user_id = other_user.id

    set_client_auth(client, user_id)
    resp = await client.get(f"/ui/models/{model_id}/history", headers=_HX)
    assert resp.status_code == 200, resp.text[:500]
    assert "v1" in resp.text and "v2" in resp.text
    assert "Higher cap" in resp.text
    assert f"/ui/models/{model_id}/history/" in resp.text  # revert form

    set_client_auth(client, other_user_id)
    resp = await client.get(f"/ui/models/{model_id}/history", headers=_HX)
    assert resp.status_code == 403
    assert "Higher cap" not in resp.text
