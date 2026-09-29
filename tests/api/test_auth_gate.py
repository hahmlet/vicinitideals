"""The login gate: who may reach /api/ and the UI pages, and as whom.

Two holes were live on production until 2026-09-28:

1. Any value in the old unsigned ``vd_user_id`` cookie opened every UI page
   (``curl -b "vd_user_id=x" /flats/lots`` returned the FLATS results).
2. ``/api/`` needed neither a session nor the API key, and routes trusted the
   ``X-User-ID`` header from anyone (anonymous ``GET /api/users`` listed users;
   a made-up ``X-User-ID`` read projects).

The rules now (``require_auth_for_ui`` in app/api/main.py,
``get_current_user_id`` in app/api/deps.py):

- /api/ needs a signed session cookie OR a valid X-API-Key.
- With a session, the caller IS the session's user; X-User-ID is ignored.
- With the API key (MCP, scripts, smoke check), X-User-ID is trusted.
- Guest share links and the Resend webhook stay reachable anonymously.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from app.models.org import User
from app.models.settings import UserSetting
from tests.conftest import seed_org

pytestmark = pytest.mark.asyncio


def _anonymous(client: AsyncClient) -> None:
    """Strip everything that could identify the caller."""
    client.headers.pop("X-User-ID", None)
    client.headers.pop("X-API-Key", None)
    client.cookies.clear()


async def _two_users_with_settings(session: AsyncSession) -> tuple[User, User]:
    org, alice = await seed_org(session)
    bob = User(id=uuid.uuid4(), org_id=org.id, name="Bob", display_color="#000000")
    session.add(bob)
    await session.flush()
    session.add_all([
        UserSetting(user_id=alice.id, org_id=org.id, field_key="alice_key", value="a"),
        UserSetting(user_id=bob.id, org_id=org.id, field_key="bob_secret", value="b"),
    ])
    await session.commit()
    return alice, bob


# ---------------------------------------------------------------------------
# Anonymous callers are refused
# ---------------------------------------------------------------------------

async def test_anonymous_api_users_is_401(client: AsyncClient, session: AsyncSession):
    await seed_org(session)
    await session.commit()
    _anonymous(client)

    resp = await client.get("/api/users")
    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


async def test_anonymous_api_with_made_up_user_id_is_401(client: AsyncClient):
    _anonymous(client)
    resp = await client.get(
        "/api/projects", headers={"X-User-ID": "00000000-0000-4000-8000-000000000001"}
    )
    assert resp.status_code == 401


async def test_anonymous_htmx_api_call_redirects_to_login(client: AsyncClient):
    _anonymous(client)
    resp = await client.get("/api/users", headers={"hx-request": "true"})
    assert resp.status_code == 401
    assert resp.headers["HX-Redirect"].startswith("/login")


async def test_wrong_api_key_is_401(client: AsyncClient):
    _anonymous(client)
    resp = await client.get("/api/users", headers={"X-API-Key": "not-the-key"})
    assert resp.status_code == 401


@pytest.mark.parametrize("path", ["/deals", "/flats/lots"])
async def test_forged_legacy_cookie_redirects_to_login(client: AsyncClient, path: str):
    _anonymous(client)
    client.cookies.set("vd_user_id", "x")
    resp = await client.get(path, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


async def test_legacy_cookie_with_real_user_uuid_is_not_a_login(
    client: AsyncClient, session: AsyncSession
):
    _org, user = await seed_org(session)
    await session.commit()
    _anonymous(client)
    client.cookies.set("vd_user_id", str(user.id))

    assert (await client.get("/deals", follow_redirects=False)).status_code == 303
    assert (await client.get("/api/users")).status_code == 401


async def test_forged_session_signature_is_refused(client: AsyncClient):
    _anonymous(client)
    client.cookies.set(COOKIE_NAME, "not-a-signed-token")
    assert (await client.get("/api/users")).status_code == 401
    assert (await client.get("/deals", follow_redirects=False)).status_code == 303


# ---------------------------------------------------------------------------
# A signed session works, and fixes the caller's identity
# ---------------------------------------------------------------------------

async def test_session_can_call_api_projects(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    await session.commit()
    _anonymous(client)
    client.cookies.set(COOKIE_NAME, create_session_token(user.id, email_verified=True))

    resp = await client.get("/api/projects")
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


async def test_session_user_ignores_a_different_x_user_id(
    client: AsyncClient, session: AsyncSession
):
    alice, bob = await _two_users_with_settings(session)
    _anonymous(client)
    client.cookies.set(COOKIE_NAME, create_session_token(alice.id, email_verified=True))

    resp = await client.get("/api/settings/user", headers={"X-User-ID": str(bob.id)})
    assert resp.status_code == 200, resp.text
    keys = {row["field_key"] for row in resp.json()}
    assert keys == {"alice_key"}, "session user read another user's settings"


async def test_unverified_session_cannot_call_api(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    await session.commit()
    _anonymous(client)
    client.cookies.set(COOKIE_NAME, create_session_token(user.id, email_verified=False))

    resp = await client.get("/api/users")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# The API key keeps today's behaviour: X-User-ID is trusted
# ---------------------------------------------------------------------------

async def test_api_key_with_x_user_id_acts_as_that_user(
    client: AsyncClient, session: AsyncSession, api_key: str
):
    _alice, bob = await _two_users_with_settings(session)
    _anonymous(client)

    resp = await client.get(
        "/api/settings/user", headers={"X-API-Key": api_key, "X-User-ID": str(bob.id)}
    )
    assert resp.status_code == 200, resp.text
    assert {row["field_key"] for row in resp.json()} == {"bob_secret"}


async def test_api_key_alone_lists_users(client: AsyncClient, session: AsyncSession, api_key: str):
    """The deploy smoke check calls /api/users with only the key."""
    await seed_org(session)
    await session.commit()
    _anonymous(client)
    resp = await client.get("/api/users", headers={"X-API-Key": api_key})
    assert resp.status_code == 200


async def test_api_key_does_not_open_ui_pages(client: AsyncClient, api_key: str):
    _anonymous(client)
    resp = await client.get("/deals", headers={"X-API-Key": api_key}, follow_redirects=False)
    assert resp.status_code == 303


# ---------------------------------------------------------------------------
# Public paths stay public
# ---------------------------------------------------------------------------

async def test_health_is_public(client: AsyncClient):
    _anonymous(client)
    assert (await client.get("/health")).status_code == 200


async def test_resend_webhook_reaches_its_signature_check(client: AsyncClient, monkeypatch):
    """Anonymous by design; the route's own Svix check refuses a bad signature."""
    monkeypatch.setattr("app.config.settings.resend_webhook_secret", "whsec_dGVzdA==")
    _anonymous(client)
    resp = await client.post("/api/email-ingest", content=b"{}")
    # 403 from the Svix check, not 401 from the login gate.
    assert resp.status_code == 403
    assert "Svix" in resp.json()["message"]


async def test_guest_share_link_works_anonymously(client: AsyncClient, session: AsyncSession):
    from tests.api.test_ui_documents_guest_routes import _project_share, _seed

    org, _deal, north, _south, _n_task, _s_task = await _seed(session)
    share = await _project_share(session, org, north)
    _anonymous(client)

    resp = await client.get(f"/share/{share.slug}/tasks")
    assert resp.status_code == 200
    assert "Leases" in resp.text
