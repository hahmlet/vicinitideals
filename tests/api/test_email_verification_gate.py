"""Hard email-verification gate tests.

Covers:
  - Verified session → can reach a protected page.
  - Unverified session → redirected to /verify-email-required with ?next=.
  - Unverified session → can still reach /profile, /verify-email-required,
    /onboarding, /pending-approval (recovery + onboarding surfaces).
  - Legacy UUID-only session token → bypasses the gate entirely
    (back-compat; old sessions don't carry the ev claim).

The gate decision is made in middleware from the signed cookie claim, with
no DB read per request. Tests therefore set cookies directly rather than
exercising /login each time.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from tests.conftest import seed_org


pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


@pytest.fixture(autouse=True)
def _patch_async_session_local(session: AsyncSession, monkeypatch):
    """Thread the test session through the onboarding_guard middleware.

    The middleware in app/api/main.py uses ``app.db.AsyncSessionLocal``
    directly (bypassing FastAPI DI), so without this patch any request
    to a non-exempt path tries to connect to the production DB hostname.
    """

    @asynccontextmanager
    async def _factory():
        yield session

    monkeypatch.setattr("app.db.AsyncSessionLocal", _factory)


def _set_session(
    client: AsyncClient,
    user_id,
    *,
    email_verified: bool | None = None,
) -> None:
    client.cookies.set(
        COOKIE_NAME,
        create_session_token(user_id, email_verified=email_verified),
    )


# ---------------------------------------------------------------------------
# Verified vs unverified vs legacy
# ---------------------------------------------------------------------------

# /settings is auth-required, exempt from the onboarding_guard (so its
# AsyncSessionLocal call is skipped — see the _PUBLIC tuple in
# app/api/main.py), and not in the email-verification exempt list.
# That makes it the canonical target for testing the gate's redirect
# without needing the production DB hostname to resolve.
_GATED_PATH = "/settings"


async def test_unverified_user_redirected_to_verify_gate(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    _, user = await seed_org(session)
    user.email = "unverified@example.com"
    user.email_verified = False
    session.add(user)
    await session.commit()
    _set_session(client, user.id, email_verified=False)

    resp = await client.get(_GATED_PATH, follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/verify-email-required?next=")
    assert "%2Fsettings" in resp.headers["location"]


async def test_verified_user_passes_gate(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    _, user = await seed_org(session)
    user.email = "verified@example.com"
    user.email_verified = True
    session.add(user)
    await session.commit()
    _set_session(client, user.id, email_verified=True)

    resp = await client.get(_GATED_PATH, follow_redirects=False)

    # Gate passes — must not be the verify-required redirect. Any other
    # status (200 render, 303 to another route) is acceptable since this
    # test is only asserting the gate didn't kick in.
    assert not (
        resp.status_code == 303
        and resp.headers.get("location", "").startswith("/verify-email-required")
    )


async def test_legacy_uuid_only_session_bypasses_gate(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    _, user = await seed_org(session)
    await session.commit()
    # No email_verified kwarg → legacy UUID-only token.
    _set_session(client, user.id)

    resp = await client.get(_GATED_PATH, follow_redirects=False)

    assert not (
        resp.status_code == 303
        and resp.headers.get("location", "").startswith("/verify-email-required")
    )


# ---------------------------------------------------------------------------
# Recovery + onboarding surfaces stay reachable for unverified users
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "/profile",
        "/verify-email-required",
        "/onboarding",
        "/pending-approval",
    ],
)
async def test_unverified_user_can_reach_recovery_and_onboarding_paths(
    client: AsyncClient,
    session: AsyncSession,
    path: str,
) -> None:
    _, user = await seed_org(session)
    user.email = "stuck@example.com"
    user.email_verified = False
    session.add(user)
    await session.commit()
    _set_session(client, user.id, email_verified=False)

    resp = await client.get(path, follow_redirects=False)

    # None of these paths should bounce to the verify-required gate.
    if resp.status_code == 303:
        assert not resp.headers.get("location", "").startswith(
            "/verify-email-required"
        ), f"{path} was incorrectly gated"


# ---------------------------------------------------------------------------
# /verify-email-required renders with 403 + next param
# ---------------------------------------------------------------------------

async def test_verify_email_required_page_renders(client: AsyncClient) -> None:
    resp = await client.get("/verify-email-required?next=/deals", follow_redirects=False)
    assert resp.status_code == 403
    assert b"Verify your email" in resp.content
