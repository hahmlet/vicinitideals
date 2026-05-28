"""Tests for org onboarding, registration flows, and member management.

Covers:
  - POST /register (no org) → user created without org_id, redirects /onboarding
  - POST /register with ?org_slug= → pending user, redirects /pending-approval
  - POST /register with invite token → pending user, invite accepted_at set
  - POST /ui/onboarding/step with taken slug → error in response
  - POST /ui/onboarding/complete → org created, user.org_id set, HX-Redirect: /deals
  - POST /settings/organization/members/{id}/approve → membership_status becomes active
  - POST /settings/organization/members/{id}/remove → user deleted
  - Non-admin approve attempt → 403
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from app.config import settings
from app.emails.tokens import make_invite_token
from app.models.org import MembershipStatus, OrgInvite, Organization, User

from tests.conftest import seed_org, set_client_auth

# The onboarding_guard middleware calls AsyncSessionLocal() directly (bypasses
# FastAPI DI), so it can't reach the test DB. Sending hx-request:true causes
# the guard to skip its DB check (HTMX requests are exempt). CSRF middleware
# still fires for HTMX POSTs — set_client_auth satisfies both.
_HTMX = {"hx-request": "true"}


# ---------------------------------------------------------------------------
# POST /register — no org → user gets org_id=None, redirects /onboarding
# ---------------------------------------------------------------------------


async def test_register_no_org_creates_user_without_org_id(
    client: AsyncClient, session: AsyncSession
) -> None:
    with patch("app.api.routers.auth_routes.send_verification_email", new=AsyncMock()):
        resp = await client.post(
            "/register",
            data={
                "name": "New User",
                "email": "newuser@example.com",
                "password": "password123",
                "password_confirm": "password123",
            },
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/onboarding"

    user = (
        await session.execute(select(User).where(User.email == "newuser@example.com"))
    ).scalar_one_or_none()
    assert user is not None
    assert user.org_id is None
    assert user.membership_status == MembershipStatus.ACTIVE


# ---------------------------------------------------------------------------
# POST /register — with org slug → pending member, redirects /pending-approval
# ---------------------------------------------------------------------------


async def test_register_with_org_slug_creates_pending_user(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, _ = await seed_org(session)

    with patch("app.api.routers.auth_routes.send_verification_email", new=AsyncMock()):
        resp = await client.post(
            "/register",
            data={
                "name": "Joiner",
                "email": "joiner@example.com",
                "password": "password123",
                "password_confirm": "password123",
                "org_slug": org.slug,
            },
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/pending-approval"

    user = (
        await session.execute(select(User).where(User.email == "joiner@example.com"))
    ).scalar_one_or_none()
    assert user is not None
    assert user.org_id == org.id
    assert user.membership_status == MembershipStatus.PENDING
    assert user.is_org_admin is False


# ---------------------------------------------------------------------------
# POST /register — with invite token → invite accepted_at marked
# ---------------------------------------------------------------------------


async def test_register_with_invite_token_marks_invite_accepted(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await seed_org(session)
    email = "invited@example.com"
    token = make_invite_token(org.id, email)
    expires = datetime.now(UTC) + timedelta(seconds=settings.invite_token_max_age_seconds)
    invite = OrgInvite(
        id=uuid.uuid4(),
        org_id=org.id,
        invited_by_id=admin.id,
        email=email,
        token=token,
        expires_at=expires,
    )
    session.add(invite)
    await session.flush()

    with patch("app.api.routers.auth_routes.send_verification_email", new=AsyncMock()):
        resp = await client.post(
            "/register",
            data={
                "name": "Invited User",
                "email": email,
                "password": "password123",
                "password_confirm": "password123",
                "invite_token": token,
            },
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/pending-approval"

    await session.refresh(invite)
    assert invite.accepted_at is not None

    user = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    assert user is not None
    assert user.membership_status == MembershipStatus.PENDING


# ---------------------------------------------------------------------------
# POST /register — duplicate email → error
# ---------------------------------------------------------------------------


async def test_register_duplicate_email_returns_error(
    client: AsyncClient, session: AsyncSession
) -> None:
    _, existing = await seed_org(session)
    existing.email = "taken@example.com"
    await session.flush()

    with patch("app.api.routers.auth_routes.send_verification_email", new=AsyncMock()):
        resp = await client.post(
            "/register",
            data={
                "name": "Dupe",
                "email": "taken@example.com",
                "password": "password123",
                "password_confirm": "password123",
            },
            follow_redirects=False,
        )

    assert resp.status_code == 400
    assert "already exists" in resp.text.lower()


# ---------------------------------------------------------------------------
# POST /ui/onboarding/step — step 1 with taken slug → error fragment
# ---------------------------------------------------------------------------


async def test_onboarding_step1_taken_slug_returns_error(
    client: AsyncClient, session: AsyncSession
) -> None:
    taken_org = Organization(id=uuid.uuid4(), name="Existing", slug="taken-slug")
    onboard_user = User(
        id=uuid.uuid4(),
        org_id=None,
        name="Onboarder",
        email="onboarder@example.com",
        hashed_password="x",
        is_active=True,
        membership_status=MembershipStatus.ACTIVE,
    )
    session.add_all([taken_org, onboard_user])
    await session.flush()

    client.cookies.set(COOKIE_NAME, create_session_token(onboard_user.id))

    resp = await client.post(
        "/ui/onboarding/step",
        data={"_step": "1", "org_name": "Existing", "org_slug": "taken-slug"},
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert "already taken" in resp.text.lower()


# ---------------------------------------------------------------------------
# POST /ui/onboarding/complete → org created, user.org_id set, HX-Redirect
# ---------------------------------------------------------------------------


async def test_onboarding_complete_creates_org_and_redirects(
    client: AsyncClient, session: AsyncSession
) -> None:
    onboard_user = User(
        id=uuid.uuid4(),
        org_id=None,
        name="Founder",
        email="founder@example.com",
        hashed_password="x",
        is_active=True,
        membership_status=MembershipStatus.ACTIVE,
    )
    session.add(onboard_user)
    await session.flush()

    client.cookies.set(COOKIE_NAME, create_session_token(onboard_user.id))

    with patch("app.emails.send_invite_email", new=AsyncMock()):
        with patch("app.api.rate_limit.check_rate_limit", new=AsyncMock(return_value=True)):
            resp = await client.post(
                "/ui/onboarding/complete",
                data={"org_name": "My Org", "org_slug": "my-org"},
                follow_redirects=False,
            )

    assert resp.status_code == 200
    assert resp.headers.get("hx-redirect") == "/deals"

    await session.refresh(onboard_user)
    assert onboard_user.org_id is not None
    assert onboard_user.is_org_admin is True

    org = await session.get(Organization, onboard_user.org_id)
    assert org is not None
    assert org.slug == "my-org"
    assert org.name == "My Org"


# ---------------------------------------------------------------------------
# POST /settings/organization/members/{id}/approve → membership_status active
# ---------------------------------------------------------------------------


async def test_settings_approve_member_sets_active(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await seed_org(session)
    admin.is_org_admin = True
    pending_member = User(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Pending",
        email="pending@example.com",
        hashed_password="x",
        is_active=True,
        membership_status=MembershipStatus.PENDING,
    )
    session.add(pending_member)
    await session.flush()

    set_client_auth(client, admin.id)

    resp = await client.post(
        f"/settings/organization/members/{pending_member.id}/approve",
        headers=_HTMX,
        follow_redirects=False,
    )

    assert resp.status_code == 200
    await session.refresh(pending_member)
    assert pending_member.membership_status == MembershipStatus.ACTIVE


# ---------------------------------------------------------------------------
# POST /settings/organization/members/{id}/remove → user deleted
# ---------------------------------------------------------------------------


async def test_settings_remove_member_deletes_user(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await seed_org(session)
    admin.is_org_admin = True
    member = User(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Member",
        email="member@example.com",
        hashed_password="x",
        is_active=True,
        membership_status=MembershipStatus.PENDING,
    )
    session.add(member)
    await session.flush()

    member_id = member.id
    set_client_auth(client, admin.id)

    resp = await client.post(
        f"/settings/organization/members/{member_id}/remove",
        headers=_HTMX,
        follow_redirects=False,
    )

    assert resp.status_code == 200
    removed = await session.get(User, member_id)
    assert removed is None


# ---------------------------------------------------------------------------
# Non-admin cannot approve
# ---------------------------------------------------------------------------


async def test_settings_approve_requires_admin(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, non_admin = await seed_org(session)
    target = User(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Target",
        email="target@example.com",
        hashed_password="x",
        is_active=True,
        membership_status=MembershipStatus.PENDING,
    )
    session.add(target)
    await session.flush()

    set_client_auth(client, non_admin.id)

    resp = await client.post(
        f"/settings/organization/members/{target.id}/approve",
        headers=_HTMX,
        follow_redirects=False,
    )

    assert resp.status_code == 403
