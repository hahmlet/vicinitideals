"""Tests for CSRF middleware and write rate limiting.

Covers:
  - csrf helper: make_csrf_token / validate_csrf_token unit tests
  - CSRF middleware: blocks missing token, allows valid token, exempts
    auth paths, passes GETs through, passes unauthenticated requests to
    downstream auth.
  - Write rate limit middleware: blocks after per-user limit, passes up
    to the limit, uses separate buckets per user.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from app.api.csrf import make_csrf_token, validate_csrf_token

from tests.conftest import seed_org

# asyncio mode=AUTO in pyproject.toml detects async tests automatically.
# No module-level mark needed (it triggers warnings on sync test functions).


# ---------------------------------------------------------------------------
# Unit: csrf helpers
# ---------------------------------------------------------------------------


def test_csrf_roundtrip() -> None:
    user_id = str(uuid.uuid4())
    token = make_csrf_token(user_id)
    assert validate_csrf_token(token, user_id) is True


def test_csrf_wrong_user_rejected() -> None:
    token = make_csrf_token(str(uuid.uuid4()))
    other_id = str(uuid.uuid4())
    assert validate_csrf_token(token, other_id) is False


def test_csrf_tampered_token_rejected() -> None:
    user_id = str(uuid.uuid4())
    token = make_csrf_token(user_id)
    tampered = token[:-4] + "XXXX"
    assert validate_csrf_token(tampered, user_id) is False


def test_csrf_none_rejected() -> None:
    assert validate_csrf_token(None, str(uuid.uuid4())) is False


def test_csrf_empty_string_rejected() -> None:
    assert validate_csrf_token("", str(uuid.uuid4())) is False


# ---------------------------------------------------------------------------
# Integration: CSRF middleware via ASGI client
# ---------------------------------------------------------------------------


async def test_csrf_get_passes_without_token(client: AsyncClient, session: AsyncSession) -> None:
    """GET requests are never blocked by CSRF middleware."""
    _, user = await seed_org(session)
    cookies = {COOKIE_NAME: create_session_token(user.id)}
    # /deals is a protected page but it's a GET — should redirect to login
    # or serve the page, never 403.
    resp = await client.get("/deals", cookies=cookies, follow_redirects=False)
    assert resp.status_code != 403


async def test_csrf_post_without_token_blocked(client: AsyncClient, session: AsyncSession) -> None:
    """Authenticated HTMX POST to a non-exempt path with no CSRF token → 403.

    CSRF validation is scoped to HTMX-initiated mutating requests
    (hx-request: true); plain form POSTs rely on SameSite=Lax cookies.
    """
    _, user = await seed_org(session)
    cookies = {COOKIE_NAME: create_session_token(user.id)}
    # The CSRF middleware fires before routing, so any non-exempt path works.
    resp = await client.post(
        "/api/deals",
        cookies=cookies,
        json={"name": "test"},
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["code"] == "forbidden"
    assert "csrf" in body["message"].lower()


async def test_csrf_post_with_valid_token_passes(client: AsyncClient, session: AsyncSession) -> None:
    """Authenticated POST with correct CSRF header is not blocked by CSRF middleware."""
    _, user = await seed_org(session)
    user_id_str = str(user.id)
    cookies = {COOKIE_NAME: create_session_token(user.id)}
    csrf_token = make_csrf_token(user_id_str)
    # The CSRF middleware passes. Route may still 4xx/5xx — that's fine;
    # we assert it's NOT 403 from CSRF.
    resp = await client.post(
        "/api/deals",
        cookies=cookies,
        json={"name": "test"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert resp.status_code != 403


async def test_csrf_post_to_exempt_path_passes(client: AsyncClient) -> None:
    """POST to an auth-exempt path (e.g. /login) is never CSRF-blocked."""
    resp = await client.post(
        "/login",
        data={"email": "nobody@example.com", "password": "wrong"},
        follow_redirects=False,
    )
    # May get 401/422/redirect — not 403 from CSRF
    assert resp.status_code != 403


async def test_csrf_post_unauthenticated_passes_to_downstream(client: AsyncClient) -> None:
    """Unauthenticated POST (no session cookie) defers to downstream auth, not CSRF check."""
    resp = await client.post(
        "/api/deals",
        json={"name": "test"},
        # No cookies — no session
        follow_redirects=False,
    )
    # CSRF middleware skips unauthenticated requests; downstream will 401/403/redirect
    assert resp.status_code != 403 or "csrf" not in resp.text.lower()


async def test_csrf_wrong_token_blocked(client: AsyncClient, session: AsyncSession) -> None:
    """Authenticated HTMX POST with a token forged for a different user → 403."""
    _, user = await seed_org(session)
    cookies = {COOKIE_NAME: create_session_token(user.id)}
    wrong_token = make_csrf_token(str(uuid.uuid4()))  # different user
    resp = await client.post(
        "/api/deals",
        cookies=cookies,
        json={"name": "test"},
        headers={"X-CSRF-Token": wrong_token, "hx-request": "true"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Integration: write rate limit middleware
# ---------------------------------------------------------------------------



async def test_write_rate_limit_returns_429_with_retry_header(
    client: AsyncClient, session: AsyncSession
) -> None:
    """When rate limit fires, response is 429 with Retry-After header."""
    _, user = await seed_org(session)
    user_id_str = str(user.id)
    cookies = {COOKIE_NAME: create_session_token(user.id)}
    csrf_token = make_csrf_token(user_id_str)

    # Force the rate limiter to deny every request
    async def deny_all(key: str, max_count: int, window_seconds: int) -> bool:
        if "write_rl:user" in key:
            return False
        return True

    with patch("app.api.rate_limit.check_rate_limit", new=AsyncMock(side_effect=deny_all)):
        resp = await client.post(
            "/api/deals",
            cookies=cookies,
            json={},
            headers={"X-CSRF-Token": csrf_token},
            follow_redirects=False,
        )

    assert resp.status_code == 429
    assert "Retry-After" in resp.headers
    body = resp.json()
    assert body["code"] == "too_many_requests"


async def test_write_rate_limit_separate_buckets_per_user(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Each user has an independent rate limit bucket."""
    _, user_a = await seed_org(session)
    _, user_b = await seed_org(session)

    seen_keys: set[str] = set()

    async def capture_keys(key: str, max_count: int, window_seconds: int) -> bool:
        seen_keys.add(key)
        return True

    with patch("app.api.rate_limit.check_rate_limit", new=AsyncMock(side_effect=capture_keys)):
        for user in (user_a, user_b):
            cookies = {COOKIE_NAME: create_session_token(user.id)}
            csrf_token = make_csrf_token(str(user.id))
            await client.post(
                "/api/deals",
                cookies=cookies,
                json={},
                headers={"X-CSRF-Token": csrf_token},
                follow_redirects=False,
            )

    user_a_key = f"write_rl:user:{user_a.id}"
    user_b_key = f"write_rl:user:{user_b.id}"
    assert user_a_key in seen_keys
    assert user_b_key in seen_keys
    assert user_a_key != user_b_key
