"""Integration tests for the auth boundary (app/api/routers/auth_routes.py).

Covers:
  - POST /login (correct + wrong password, disabled account), GET/POST /logout
  - GET /register
  - GET /verify-email (valid + invalid token)
  - POST /resend-verification
  - GET+POST /forgot-password
  - GET+POST /reset-password (valid round-trip; token single-use via
    password-hash-prefix binding)
  - GET /ui/onboarding/check-slug (available + taken)

A commit deleted the onboarding routes once before with zero coverage —
these tests are the guard against that class of regression.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import (
    COOKIE_NAME,
    create_session_token,
    hash_password,
    verify_password,
)
from app.emails.tokens import make_email_verification_token, make_password_reset_token
from app.models.org import MembershipStatus, User

from tests.conftest import seed_org

pytestmark = pytest.mark.asyncio

PASSWORD = "correct-horse-battery"


async def _seed_login_user(
    session: AsyncSession, *, email: str = "login@example.com", **overrides
) -> User:
    org, user = await seed_org(session)
    user.email = email
    user.hashed_password = hash_password(PASSWORD)
    user.is_active = True
    user.membership_status = MembershipStatus.ACTIVE
    user.email_verified = True
    for k, v in overrides.items():
        setattr(user, k, v)
    await session.flush()
    return user


# ---------------------------------------------------------------------------
# POST /login
# ---------------------------------------------------------------------------


async def test_login_correct_password_sets_session_cookie(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await _seed_login_user(session)
    user_id = user.id

    resp = await client.post(
        "/login",
        data={"email": "login@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    assert resp.headers["location"] == "/deals"
    set_cookie = resp.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie
    assert "HttpOnly" in set_cookie

    # last_login stamped
    await session.refresh(await session.get(User, user_id))
    assert (await session.get(User, user_id)).last_login is not None


async def test_login_wrong_password_401(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _seed_login_user(session)

    resp = await client.post(
        "/login",
        data={"email": "login@example.com", "password": "wrong-password"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert "invalid email or password" in resp.text.lower()
    assert COOKIE_NAME not in resp.headers.get("set-cookie", "")


async def test_login_unknown_email_401(client: AsyncClient) -> None:
    resp = await client.post(
        "/login",
        data={"email": "ghost@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 401


async def test_login_disabled_account_403(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _seed_login_user(session, email="disabled@example.com", is_active=False)

    resp = await client.post(
        "/login",
        data={"email": "disabled@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 403


async def test_login_user_without_org_redirects_to_onboarding(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = User(
        id=uuid.uuid4(),
        org_id=None,
        name="No Org",
        email="noorg@example.com",
        hashed_password=hash_password(PASSWORD),
        is_active=True,
        membership_status=MembershipStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()

    resp = await client.post(
        "/login",
        data={"email": "noorg@example.com", "password": PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/onboarding"


# ---------------------------------------------------------------------------
# GET/POST /logout
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["get", "post"])
async def test_logout_clears_cookie_and_redirects(
    client: AsyncClient, session: AsyncSession, method: str
) -> None:
    user = await _seed_login_user(session)
    client.cookies.set(COOKIE_NAME, create_session_token(user.id))

    resp = await getattr(client, method)("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    # Cookie deletion arrives as a Set-Cookie with empty value / immediate expiry
    set_cookie = resp.headers.get("set-cookie", "")
    assert COOKIE_NAME in set_cookie


# ---------------------------------------------------------------------------
# GET /register
# ---------------------------------------------------------------------------


async def test_register_page_renders(client: AsyncClient) -> None:
    resp = await client.get("/register")
    assert resp.status_code == 200
    assert "password" in resp.text.lower()


async def test_register_page_unknown_org_slug_404(client: AsyncClient) -> None:
    resp = await client.get("/register", params={"org": "no-such-org"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /verify-email
# ---------------------------------------------------------------------------


async def test_verify_email_valid_token_marks_verified(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await _seed_login_user(session, email="verifyme@example.com")
    user.email_verified = False
    user.email_verified_at = None
    await session.flush()
    user_id = user.id

    token = make_email_verification_token(user_id)
    resp = await client.get("/verify-email", params={"token": token})
    assert resp.status_code == 200, resp.text
    assert "verified" in resp.text.lower()
    # Session cookie re-issued with the verified claim
    assert COOKIE_NAME in resp.headers.get("set-cookie", "")

    session.expire_all()
    row = await session.get(User, user_id)
    assert row.email_verified is True
    assert row.email_verified_at is not None


async def test_verify_email_invalid_token_400(client: AsyncClient) -> None:
    resp = await client.get("/verify-email", params={"token": "garbage-token"})
    assert resp.status_code == 400
    assert "invalid" in resp.text.lower() or "expired" in resp.text.lower()


async def test_verify_email_missing_token_400(client: AsyncClient) -> None:
    resp = await client.get("/verify-email")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /resend-verification
# ---------------------------------------------------------------------------


async def test_resend_verification_sends_email_for_unverified_user(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await _seed_login_user(session, email="resend@example.com")
    user.email_verified = False
    await session.flush()
    client.cookies.set(COOKIE_NAME, create_session_token(user.id))

    with patch(
        "app.api.routers.auth_routes.send_verification_email", new=AsyncMock()
    ) as sender:
        resp = await client.post("/resend-verification", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/profile?verification_sent=1"
    sender.assert_awaited_once()
    assert sender.await_args.kwargs["to"] == "resend@example.com"


async def test_resend_verification_already_verified_skips_send(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await _seed_login_user(session, email="already@example.com")
    client.cookies.set(COOKIE_NAME, create_session_token(user.id))

    with patch(
        "app.api.routers.auth_routes.send_verification_email", new=AsyncMock()
    ) as sender:
        resp = await client.post("/resend-verification", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == "/profile?verified=1"
    sender.assert_not_awaited()


async def test_resend_verification_unauthenticated_redirects_login(
    client: AsyncClient,
) -> None:
    resp = await client.post("/resend-verification", follow_redirects=False)
    assert resp.status_code == 303
    # The auth middleware intercepts first and appends ?next=; either way an
    # unauthenticated caller lands on /login.
    assert resp.headers["location"].startswith("/login")


# ---------------------------------------------------------------------------
# GET+POST /forgot-password
# ---------------------------------------------------------------------------


async def test_forgot_password_page_renders(client: AsyncClient) -> None:
    resp = await client.get("/forgot-password")
    assert resp.status_code == 200


async def test_forgot_password_known_email_sends_reset(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _seed_login_user(session, email="forgot@example.com")

    with patch(
        "app.api.routers.auth_routes.send_password_reset_email", new=AsyncMock()
    ) as sender:
        resp = await client.post(
            "/forgot-password",
            data={"email": "forgot@example.com"},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/forgot-password?sent=1"
    sender.assert_awaited_once()


async def test_forgot_password_unknown_email_same_response_no_send(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Anti-enumeration: unknown email returns the identical confirmation."""
    with patch(
        "app.api.routers.auth_routes.send_password_reset_email", new=AsyncMock()
    ) as sender:
        resp = await client.post(
            "/forgot-password",
            data={"email": "nobody@example.com"},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/forgot-password?sent=1"
    sender.assert_not_awaited()


# ---------------------------------------------------------------------------
# GET+POST /reset-password — round-trip + single-use binding
# ---------------------------------------------------------------------------


async def test_reset_password_round_trip_and_token_single_use(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await _seed_login_user(session, email="reset@example.com")
    user_id = user.id
    token = make_password_reset_token(user_id, user.hashed_password)

    # GET renders the form for a signature-valid token
    form = await client.get("/reset-password", params={"token": token})
    assert form.status_code == 200, form.text

    # POST applies the new password and logs the user in
    new_password = "brand-new-password-1"
    resp = await client.post(
        "/reset-password",
        data={
            "token": token,
            "password": new_password,
            "password_confirm": new_password,
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    assert resp.headers["location"] == "/deals"
    assert COOKIE_NAME in resp.headers.get("set-cookie", "")

    session.expire_all()
    row = await session.get(User, user_id)
    assert verify_password(new_password, row.hashed_password)
    assert not verify_password(PASSWORD, row.hashed_password)
    # Reset proves mailbox ownership — email marked verified
    assert row.email_verified is True

    # Replaying the same token must fail: it was bound to the OLD password
    # hash prefix, which changed on reset (single-use guarantee).
    replay = await client.post(
        "/reset-password",
        data={
            "token": token,
            "password": "attacker-password-9",
            "password_confirm": "attacker-password-9",
        },
        follow_redirects=False,
    )
    assert replay.status_code == 400
    assert "already been used" in replay.text or "already used" in replay.text.lower()

    session.expire_all()
    row = await session.get(User, user_id)
    assert verify_password(new_password, row.hashed_password)


async def test_reset_password_get_invalid_token_400(client: AsyncClient) -> None:
    resp = await client.get("/reset-password", params={"token": "junk"})
    assert resp.status_code == 400


async def test_reset_password_post_mismatched_passwords_400(
    client: AsyncClient, session: AsyncSession
) -> None:
    user = await _seed_login_user(session, email="mismatch@example.com")
    token = make_password_reset_token(user.id, user.hashed_password)

    resp = await client.post(
        "/reset-password",
        data={"token": token, "password": "aaaaaaaa1", "password_confirm": "bbbbbbbb2"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "do not match" in resp.text.lower()


# ---------------------------------------------------------------------------
# GET /ui/onboarding/check-slug
# ---------------------------------------------------------------------------


async def test_check_slug_available(client: AsyncClient, session: AsyncSession) -> None:
    resp = await client.get(
        "/ui/onboarding/check-slug",
        params={"slug": "totally-unused-slug"},
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 200
    assert "Available" in resp.text


async def test_check_slug_taken(client: AsyncClient, session: AsyncSession) -> None:
    org, _ = await seed_org(session)
    resp = await client.get(
        "/ui/onboarding/check-slug",
        params={"slug": org.slug},
        headers={"hx-request": "true"},
    )
    assert resp.status_code == 200
    assert "Already taken" in resp.text


async def test_check_slug_empty_returns_blank(client: AsyncClient) -> None:
    resp = await client.get(
        "/ui/onboarding/check-slug", headers={"hx-request": "true"}
    )
    assert resp.status_code == 200
    assert resp.text == ""
