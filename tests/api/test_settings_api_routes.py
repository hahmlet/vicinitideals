"""Integration tests for the settings API (app/api/routers/settings.py).

Covers the 15 previously-untested routes:
  - GET+PUT /api/settings/org (batch), PUT /api/settings/org/{field_key}
  - GET+PUT /api/settings/user (batch), PUT /api/settings/user/{field_key}
  - GET /api/settings/resolve, GET /api/settings/resolve/{field_key}
  - GET /api/settings/timeline-defaults, PUT .../timeline-defaults/org + /user
  - GET /api/settings/source-vehicles, POST/PUT/DELETE org + user vehicles

Key behavior under test: the resolution layering — org setting is the
default, a user override wins when the field is user-overridable, and
org-locked fields ignore the user row.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.milestone import MilestoneType
from app.models.settings import OrgSetting, UserSetting
from app.models.source_vehicle import SourceVehicle
from app.settings.defaults import ORG_SET_FIELDS, SYSTEM_BASELINE

from tests.conftest import seed_org

pytestmark = pytest.mark.asyncio

# A field where the user → org → system chain applies (not org-locked).
OVERRIDABLE_KEY = next(k for k in SYSTEM_BASELINE if k not in ORG_SET_FIELDS)


async def _admin(client: AsyncClient, session: AsyncSession):
    """Seed an org + admin user and point the client's X-User-ID at them."""
    org, user = await seed_org(session)
    user.is_org_admin = True
    await session.flush()
    client.headers["X-User-ID"] = str(user.id)
    return org, user


# ---------------------------------------------------------------------------
# Org settings — single upsert + list + admin gate
# ---------------------------------------------------------------------------


async def test_org_setting_upsert_and_list(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, _user = await _admin(client, session)
    org_id = org.id

    resp = await client.put(
        f"/api/settings/org/{OVERRIDABLE_KEY}", data={"value": "1.31"}
    )
    assert resp.status_code == 200, resp.text
    assert "Saved" in resp.text

    row = (
        await session.execute(
            select(OrgSetting).where(
                OrgSetting.org_id == org_id, OrgSetting.field_key == OVERRIDABLE_KEY
            )
        )
    ).scalar_one()
    assert row.value == "1.31"

    listed = await client.get("/api/settings/org")
    assert listed.status_code == 200, listed.text
    by_key = {r["field_key"]: r for r in listed.json()}
    assert by_key[OVERRIDABLE_KEY]["value"] == "1.31"

    # Second PUT updates in place (on_conflict_do_update)
    resp2 = await client.put(
        f"/api/settings/org/{OVERRIDABLE_KEY}", data={"value": "1.45"}
    )
    assert resp2.status_code == 200
    session.expire_all()
    rows = (
        await session.execute(
            select(OrgSetting).where(
                OrgSetting.org_id == org_id, OrgSetting.field_key == OVERRIDABLE_KEY
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].value == "1.45"


async def test_org_settings_require_admin(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)  # is_org_admin defaults False
    await session.flush()
    client.headers["X-User-ID"] = str(user.id)

    assert (await client.get("/api/settings/org")).status_code == 403
    assert (
        await client.put(f"/api/settings/org/{OVERRIDABLE_KEY}", data={"value": "x"})
    ).status_code == 403
    assert (
        await client.put("/api/settings/org", json={OVERRIDABLE_KEY: "x"})
    ).status_code == 403


async def test_org_batch_upsert_values_and_permissions(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, _user = await _admin(client, session)
    org_id = org.id

    resp = await client.put(
        "/api/settings/org",
        json={
            "values": {OVERRIDABLE_KEY: "2.00"},
            "permissions": {OVERRIDABLE_KEY: False},
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ok"] is True

    row = (
        await session.execute(
            select(OrgSetting).where(
                OrgSetting.org_id == org_id, OrgSetting.field_key == OVERRIDABLE_KEY
            )
        )
    ).scalar_one()
    assert row.value == "2.00"
    assert row.user_overridable is False


# ---------------------------------------------------------------------------
# User settings — single upsert + list + batch
# ---------------------------------------------------------------------------


async def test_user_setting_upsert_and_list(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)
    await session.flush()
    user_id = user.id
    client.headers["X-User-ID"] = str(user_id)

    resp = await client.put(
        f"/api/settings/user/{OVERRIDABLE_KEY}", data={"value": "9.99"}
    )
    assert resp.status_code == 200, resp.text

    row = (
        await session.execute(
            select(UserSetting).where(
                UserSetting.user_id == user_id,
                UserSetting.field_key == OVERRIDABLE_KEY,
            )
        )
    ).scalar_one()
    assert row.value == "9.99"

    listed = await client.get("/api/settings/user")
    assert listed.status_code == 200
    by_key = {r["field_key"]: r["value"] for r in listed.json()}
    assert by_key[OVERRIDABLE_KEY] == "9.99"


async def test_user_batch_upsert_skips_org_locked_fields(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await _admin(client, session)
    org_id, user_id = org.id, user.id

    # Lock OVERRIDABLE_KEY at org level (user_overridable=False)
    lock = await client.put(
        "/api/settings/org",
        json={"values": {OVERRIDABLE_KEY: "5.0"}, "permissions": {OVERRIDABLE_KEY: False}},
    )
    assert lock.status_code == 200, lock.text

    org_set_key = next(iter(ORG_SET_FIELDS)) if ORG_SET_FIELDS else None
    body = {OVERRIDABLE_KEY: "7.7"}
    if org_set_key:
        body[org_set_key] = "ignored"

    resp = await client.put("/api/settings/user", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["saved"] == 0  # both fields skipped server-side

    rows = (
        await session.execute(
            select(UserSetting).where(UserSetting.user_id == user_id)
        )
    ).scalars().all()
    assert rows == []

    # Resolve must show the locked org value, not a user value
    resolved = await client.get(f"/api/settings/resolve/{OVERRIDABLE_KEY}")
    assert resolved.status_code == 200
    assert resolved.json()["value"] == "5.0"
    assert org_id is not None  # keep the local binding load-bearing


# ---------------------------------------------------------------------------
# Resolution layering — org default, user override wins
# ---------------------------------------------------------------------------


async def test_resolve_layering_user_override_wins(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, _user = await _admin(client, session)

    # Org sets the default...
    org_put = await client.put(
        f"/api/settings/org/{OVERRIDABLE_KEY}", data={"value": "1.30"}
    )
    assert org_put.status_code == 200

    # Org value resolves before any user override exists
    r1 = await client.get(f"/api/settings/resolve/{OVERRIDABLE_KEY}")
    assert r1.status_code == 200
    assert r1.json()["value"] == "1.30"

    # ...user override wins in the resolve chain
    user_put = await client.put(
        f"/api/settings/user/{OVERRIDABLE_KEY}", data={"value": "1.40"}
    )
    assert user_put.status_code == 200

    r2 = await client.get(f"/api/settings/resolve/{OVERRIDABLE_KEY}")
    assert r2.json()["value"] == "1.40"

    # Batch resolve agrees, and untouched keys fall back to system baseline
    all_resolved = await client.get("/api/settings/resolve")
    assert all_resolved.status_code == 200
    body = all_resolved.json()
    assert body[OVERRIDABLE_KEY] == "1.40"
    untouched = next(
        k for k in SYSTEM_BASELINE if k not in (OVERRIDABLE_KEY,) and k not in ORG_SET_FIELDS
    )
    assert body[untouched] == SYSTEM_BASELINE[untouched]


async def test_resolve_unknown_field_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, _user = await _admin(client, session)
    resp = await client.get("/api/settings/resolve/not_a_real_field")
    assert resp.status_code == 404


async def test_settings_routes_401_for_unknown_user(client: AsyncClient) -> None:
    # Client default X-User-ID is a random UUID with no User row behind it
    resp = await client.get("/api/settings/resolve")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Timeline defaults — org + user layering
# ---------------------------------------------------------------------------


async def test_timeline_defaults_org_then_user_override(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, _user = await _admin(client, session)
    mt = list(MilestoneType)[0].value

    org_put = await client.put(
        "/api/settings/timeline-defaults/org",
        json={"acquisition": {mt: {"included": True, "duration_days": 42}}},
    )
    assert org_put.status_code == 200, org_put.text
    assert org_put.json()["saved"] == 1

    resolved = await client.get("/api/settings/timeline-defaults")
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["acquisition"][mt]["duration_days"] == 42

    user_put = await client.put(
        "/api/settings/timeline-defaults/user",
        json={"acquisition": {mt: {"duration_days": 21}}},
    )
    assert user_put.status_code == 200, user_put.text
    assert user_put.json()["saved"] == 1

    resolved2 = await client.get("/api/settings/timeline-defaults")
    assert resolved2.json()["acquisition"][mt]["duration_days"] == 21


async def test_timeline_defaults_user_respects_org_lock(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, _user = await _admin(client, session)
    mt = list(MilestoneType)[0].value

    org_put = await client.put(
        "/api/settings/timeline-defaults/org",
        json={
            "acquisition": {mt: {"included": True, "duration_days": 30}},
            "permissions": {"acquisition": {mt: {"user_overridable": False}}},
        },
    )
    assert org_put.status_code == 200, org_put.text

    user_put = await client.put(
        "/api/settings/timeline-defaults/user",
        json={"acquisition": {mt: {"duration_days": 5}}},
    )
    assert user_put.status_code == 200
    assert user_put.json()["saved"] == 0  # silently skipped — org locked

    resolved = await client.get("/api/settings/timeline-defaults")
    assert resolved.json()["acquisition"][mt]["duration_days"] == 30


# ---------------------------------------------------------------------------
# Source vehicles — org + user CRUD
# ---------------------------------------------------------------------------


async def test_source_vehicle_org_and_user_lifecycle(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, _user = await _admin(client, session)

    org_created = await client.post(
        "/api/settings/source-vehicles/org",
        json={"name": "Bank Term Loan", "vehicle_type": "debt", "interest_rate_pct": 6.25},
    )
    assert org_created.status_code == 200, org_created.text
    org_vehicle_id = org_created.json()["id"]

    user_created = await client.post(
        "/api/settings/source-vehicles/user",
        json={"name": "My LP Equity", "vehicle_type": "equity"},
    )
    assert user_created.status_code == 200, user_created.text
    user_vehicle_id = user_created.json()["id"]

    listed = await client.get("/api/settings/source-vehicles")
    assert listed.status_code == 200
    by_id = {v["id"]: v for v in listed.json()}
    assert by_id[org_vehicle_id]["owner"] == "org"
    assert by_id[org_vehicle_id]["source_config"]["interest_rate_pct"] == 6.25
    assert by_id[user_vehicle_id]["owner"] == "user"
    assert by_id[user_vehicle_id]["vehicle_type"] == "equity"

    # PUT updates the user vehicle
    updated = await client.put(
        f"/api/settings/source-vehicles/user/{user_vehicle_id}",
        json={"name": "My GP Equity", "vehicle_type": "equity"},
    )
    assert updated.status_code == 200, updated.text
    session.expire_all()
    row = await session.get(SourceVehicle, uuid.UUID(user_vehicle_id))
    assert row.label == "My GP Equity"

    # DELETE user vehicle, then org vehicle — rows actually gone
    assert (
        await client.delete(f"/api/settings/source-vehicles/user/{user_vehicle_id}")
    ).status_code == 200
    assert (
        await client.delete(f"/api/settings/source-vehicles/org/{org_vehicle_id}")
    ).status_code == 200
    session.expire_all()
    assert await session.get(SourceVehicle, uuid.UUID(user_vehicle_id)) is None
    assert await session.get(SourceVehicle, uuid.UUID(org_vehicle_id)) is None


async def test_source_vehicle_legacy_funder_type_normalized(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, _user = await _admin(client, session)
    created = await client.post(
        "/api/settings/source-vehicles/user",
        json={"name": "Bridge Loan", "funder_type": "senior_debt"},
    )
    assert created.status_code == 200, created.text
    assert created.json()["vehicle_type"] == "debt"


async def test_source_vehicle_invalid_type_400(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, _user = await _admin(client, session)
    resp = await client.post(
        "/api/settings/source-vehicles/user",
        json={"name": "Mystery Money", "vehicle_type": "wire_fraud"},
    )
    assert resp.status_code == 400


async def test_delete_org_vehicle_requires_admin(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, admin = await _admin(client, session)
    created = await client.post(
        "/api/settings/source-vehicles/org",
        json={"name": "Org Vehicle", "vehicle_type": "debt"},
    )
    vehicle_id = created.json()["id"]

    # Same org, non-admin user
    from app.models.org import User
    non_admin = User(id=uuid.uuid4(), org_id=admin.org_id, name="Peon")
    session.add(non_admin)
    await session.flush()
    await session.commit()

    client.headers["X-User-ID"] = str(non_admin.id)
    resp = await client.delete(f"/api/settings/source-vehicles/org/{vehicle_id}")
    assert resp.status_code == 403
