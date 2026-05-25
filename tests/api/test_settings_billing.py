from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from app.config import settings
from tests.conftest import seed_org


pytestmark = pytest.mark.asyncio


async def _auth(client: AsyncClient, user_id) -> None:
    client.cookies.set(COOKIE_NAME, create_session_token(user_id))


async def test_billing_page_redirects_to_login_when_unauthenticated(
    client: AsyncClient,
) -> None:
    resp = await client.get("/settings/billing", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?next=/settings/billing"


async def test_billing_page_renders_for_authenticated_user(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "", raising=False)

    org, user = await seed_org(session)
    await session.commit()
    await _auth(client, user.id)

    resp = await client.get("/settings/billing")
    assert resp.status_code == 200
    assert "Billing" in resp.text
    assert "Stripe Not Configured" in resp.text


async def test_billing_setup_session_redirects_when_stripe_not_configured(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "", raising=False)

    org, user = await seed_org(session)
    await session.commit()
    await _auth(client, user.id)

    resp = await client.post(
        "/settings/billing/stripe/setup-session",
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings/billing?stripe=config-missing"
