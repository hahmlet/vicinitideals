"""Integration tests for settings routes that had no coverage.

Routes covered (all in app/api/routers/ui_settings.py):

  POST /settings/billing/stripe/subscription/cancel
  POST /settings/billing/stripe/subscription/reactivate
  GET  /settings/organization
  POST /settings/organization
  POST /settings/organization/invite
  POST /settings/organization/invites/{invite_id}/resend
  GET  /ui/settings/scenario-templates
  POST /ui/settings/scenario-templates/{template_id}/delete
  POST /ui/settings/scenario-templates/{template_id}/set-org-default
  POST /ui/settings/scenario-templates/{template_id}/set-user-default
  POST /ui/admin/backfill-listing-buckets
  GET  /settings/preferences
  GET  /splash

Stripe is never reached: ``ui_settings._stripe_api_request`` is replaced by a
recorder. Email is never sent: ``app.emails.send_invite_email`` is patched,
and the Redis rate limiter is patched open.

Bug regressions live in their own files (tests/api/test_bug_*.py) so each fix
can be committed with its test.
"""
from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers import ui_settings as ui
from app.config import settings
from app.models.opportunity import Opportunity
from app.models.org import OrgInvite, Organization, User
from app.models.scenario_template import ScenarioTemplate
from app.models.settings import UserSetting
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio

HX = {"hx-request": "true"}

# The scenario-template list partial formats dates with ``%-m/%-d/%Y``, which
# Windows strftime rejects. Tests that render a template ROW run in CI (Linux).
_SKIP_WIN = pytest.mark.skipif(
    sys.platform == "win32",
    reason="partials/scenario_templates_list.html uses Linux-only %-m strftime",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _org_with_admin(session: AsyncSession, label: str) -> tuple[Organization, User]:
    org, admin = await seed_org(session)
    org.name = f"Org {label}"
    admin.name = f"Admin {label}"
    admin.email = f"admin-{label.lower()}-{uuid.uuid4().hex[:6]}@example.com"
    admin.is_org_admin = True
    await session.flush()
    return org, admin


async def _member(session: AsyncSession, org: Organization, label: str) -> User:
    user = User(
        id=uuid.uuid4(),
        org_id=org.id,
        name=f"Member {label}",
        email=f"member-{label.lower()}-{uuid.uuid4().hex[:6]}@example.com",
        is_org_admin=False,
    )
    session.add(user)
    await session.flush()
    return user


def _customer_row(user: User, customer_id: str) -> UserSetting:
    return UserSetting(
        id=uuid.uuid4(),
        user_id=user.id,
        org_id=user.org_id,
        field_key="stripe_customer_id",
        value=customer_id,
    )


def _invite(org: Organization, inviter: User, email: str, **kw: Any) -> OrgInvite:
    return OrgInvite(
        id=uuid.uuid4(),
        org_id=org.id,
        invited_by_id=inviter.id,
        email=email,
        token=f"tok-{uuid.uuid4().hex}",
        expires_at=kw.pop("expires_at", datetime.now(UTC) + timedelta(days=2)),
        **kw,
    )


def _template(org: Organization, user: User, name: str) -> ScenarioTemplate:
    return ScenarioTemplate(
        id=uuid.uuid4(),
        org_id=org.id,
        created_by_user_id=user.id,
        name=name,
        template_json={},
        created_at=datetime.now(UTC),
    )


class _FakeStripe:
    """Records every Stripe call; serves one subscription list per customer."""

    def __init__(self, subs_by_customer: dict[str, list[dict[str, Any]]]):
        self.subs_by_customer = subs_by_customer
        self.calls: list[tuple[str, str, Any, Any]] = []

    async def __call__(self, method, endpoint, *, data=None, params=None):
        self.calls.append((method, endpoint, data, params))
        if method == "GET" and endpoint == "/v1/subscriptions":
            return {"data": self.subs_by_customer.get((params or {}).get("customer"), [])}
        return {}

    @property
    def writes(self) -> list[tuple[str, Any]]:
        return [(ep, data) for (m, ep, data, _p) in self.calls if m == "POST"]


def _sub(sub_id: str, status: str = "active", *, cancel_at_period_end: bool = False) -> dict:
    return {
        "id": sub_id,
        "status": status,
        "cancel_at_period_end": cancel_at_period_end,
        "items": {"data": [{"id": f"si_{sub_id}", "quantity": 1,
                            "price": {"id": "price_x", "recurring": {"interval": "month"}}}]},
    }


@pytest.fixture
def stripe_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy", raising=False)


def _install(monkeypatch: pytest.MonkeyPatch, fake: _FakeStripe) -> _FakeStripe:
    monkeypatch.setattr(ui, "_stripe_api_request", fake)
    return fake


# ---------------------------------------------------------------------------
# Billing: cancel / reactivate (money-affecting)
# ---------------------------------------------------------------------------


async def test_cancel_requires_session(client: AsyncClient, monkeypatch, stripe_on) -> None:
    fake = _install(monkeypatch, _FakeStripe({}))
    resp = await client.post("/settings/billing/stripe/subscription/cancel")
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")
    assert fake.calls == []


async def test_cancel_without_stripe_config_touches_nothing(
    client: AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "stripe_secret_key", "", raising=False)
    fake = _install(monkeypatch, _FakeStripe({}))
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.post("/settings/billing/stripe/subscription/cancel")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings/billing?stripe=config-missing"
    assert fake.calls == []


async def test_cancel_without_customer_makes_no_stripe_call(
    client: AsyncClient, session: AsyncSession, monkeypatch, stripe_on
) -> None:
    fake = _install(monkeypatch, _FakeStripe({}))
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.post("/settings/billing/stripe/subscription/cancel")
    assert resp.headers["location"] == "/settings/billing?stripe=no-subscription"
    assert fake.calls == []
    # No Stripe customer is created as a side effect of a cancel.
    rows = (await session.execute(
        select(UserSetting).where(UserSetting.user_id == user.id)
    )).scalars().all()
    assert rows == []


async def test_cancel_targets_only_the_callers_own_subscription(
    client: AsyncClient, session: AsyncSession, monkeypatch, stripe_on
) -> None:
    """Billing is per user: a non-admin member cancels THEIR subscription and
    nothing else -- not the org admin's, not another org's."""
    org, admin = await _org_with_admin(session, "A")
    member = await _member(session, org, "A")
    _org_b, other = await _org_with_admin(session, "B")
    session.add_all([
        _customer_row(admin, "cus_admin"),
        _customer_row(member, "cus_member"),
        _customer_row(other, "cus_other"),
    ])
    await session.commit()
    fake = _install(monkeypatch, _FakeStripe({
        "cus_admin": [_sub("sub_admin")],
        "cus_member": [_sub("sub_member")],
        "cus_other": [_sub("sub_other")],
    }))
    set_client_auth(client, member.id)

    resp = await client.post("/settings/billing/stripe/subscription/cancel")

    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings/billing?stripe=cancel-scheduled"
    reads = [p for (m, ep, _d, p) in fake.calls if m == "GET"]
    assert reads == [{"customer": "cus_member", "status": "all", "limit": 10}]
    assert fake.writes == [("/v1/subscriptions/sub_member", [("cancel_at_period_end", "true")])]


async def test_cancel_picks_the_live_subscription_over_an_old_canceled_one(
    client: AsyncClient, session: AsyncSession, monkeypatch, stripe_on
) -> None:
    _org, user = await seed_org(session)
    session.add(_customer_row(user, "cus_1"))
    await session.commit()
    fake = _install(monkeypatch, _FakeStripe({
        "cus_1": [_sub("sub_old", "canceled"), _sub("sub_live", "active")],
    }))
    set_client_auth(client, user.id)

    resp = await client.post("/settings/billing/stripe/subscription/cancel")
    assert resp.headers["location"] == "/settings/billing?stripe=cancel-scheduled"
    assert fake.writes == [("/v1/subscriptions/sub_live", [("cancel_at_period_end", "true")])]


async def test_cancel_already_canceled_subscription_is_a_no_op(
    client: AsyncClient, session: AsyncSession, monkeypatch, stripe_on
) -> None:
    _org, user = await seed_org(session)
    session.add(_customer_row(user, "cus_1"))
    await session.commit()
    fake = _install(monkeypatch, _FakeStripe({"cus_1": [_sub("sub_1", "canceled")]}))
    set_client_auth(client, user.id)

    resp = await client.post("/settings/billing/stripe/subscription/cancel")
    assert resp.headers["location"] == "/settings/billing?stripe=already-cancelled"
    assert fake.writes == []


async def test_cancel_with_no_subscriptions_at_stripe(
    client: AsyncClient, session: AsyncSession, monkeypatch, stripe_on
) -> None:
    _org, user = await seed_org(session)
    session.add(_customer_row(user, "cus_1"))
    await session.commit()
    fake = _install(monkeypatch, _FakeStripe({"cus_1": []}))
    set_client_auth(client, user.id)

    resp = await client.post("/settings/billing/stripe/subscription/cancel")
    assert resp.headers["location"] == "/settings/billing?stripe=no-subscription"
    assert fake.writes == []


async def test_reactivate_requires_session(client: AsyncClient, monkeypatch, stripe_on) -> None:
    fake = _install(monkeypatch, _FakeStripe({}))
    resp = await client.post("/settings/billing/stripe/subscription/reactivate")
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")
    assert fake.calls == []


async def test_reactivate_undoes_a_scheduled_cancel_on_own_subscription(
    client: AsyncClient, session: AsyncSession, monkeypatch, stripe_on
) -> None:
    org, admin = await _org_with_admin(session, "A")
    member = await _member(session, org, "A")
    session.add_all([_customer_row(admin, "cus_admin"), _customer_row(member, "cus_member")])
    await session.commit()
    fake = _install(monkeypatch, _FakeStripe({
        "cus_admin": [_sub("sub_admin", cancel_at_period_end=True)],
        "cus_member": [_sub("sub_member", cancel_at_period_end=True)],
    }))
    set_client_auth(client, member.id)

    resp = await client.post("/settings/billing/stripe/subscription/reactivate")
    assert resp.headers["location"] == "/settings/billing?stripe=reactivated"
    assert fake.writes == [("/v1/subscriptions/sub_member", [("cancel_at_period_end", "false")])]


async def test_reactivate_when_nothing_is_scheduled_makes_no_write(
    client: AsyncClient, session: AsyncSession, monkeypatch, stripe_on
) -> None:
    _org, user = await seed_org(session)
    session.add(_customer_row(user, "cus_1"))
    await session.commit()
    fake = _install(monkeypatch, _FakeStripe({"cus_1": [_sub("sub_1")]}))
    set_client_auth(client, user.id)

    resp = await client.post("/settings/billing/stripe/subscription/reactivate")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings/billing"
    assert fake.writes == []


async def test_reactivate_without_customer_or_config(
    client: AsyncClient, session: AsyncSession, monkeypatch
) -> None:
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)

    monkeypatch.setattr(settings, "stripe_secret_key", "", raising=False)
    fake = _install(monkeypatch, _FakeStripe({}))
    resp = await client.post("/settings/billing/stripe/subscription/reactivate")
    assert resp.headers["location"] == "/settings/billing?stripe=config-missing"

    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_dummy", raising=False)
    resp = await client.post("/settings/billing/stripe/subscription/reactivate")
    assert resp.headers["location"] == "/settings/billing?stripe=no-subscription"
    assert fake.calls == []


# ---------------------------------------------------------------------------
# Organization: page, rename, invite, resend
# ---------------------------------------------------------------------------


async def test_org_page_requires_session(client: AsyncClient) -> None:
    resp = await client.get("/settings/organization")
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


async def test_org_page_shows_own_org_and_not_another_orgs_invites(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_a, admin_a = await _org_with_admin(session, "Alpha")
    org_b, admin_b = await _org_with_admin(session, "Bravo")
    session.add_all([
        _invite(org_a, admin_a, "alpha-invitee@example.com"),
        _invite(org_b, admin_b, "bravo-invitee@example.com"),
    ])
    await session.commit()
    set_client_auth(client, admin_b.id)

    resp = await client.get("/settings/organization")
    assert resp.status_code == 200
    assert "Org Bravo" in resp.text
    assert "bravo-invitee@example.com" in resp.text
    assert "Org Alpha" not in resp.text
    assert "alpha-invitee@example.com" not in resp.text
    assert "Admin Alpha" not in resp.text


async def test_org_page_hides_pending_invites_from_non_admin(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await _org_with_admin(session, "A")
    member = await _member(session, org, "A")
    session.add(_invite(org, admin, "secret-invitee@example.com"))
    await session.commit()
    set_client_auth(client, member.id)

    resp = await client.get("/settings/organization")
    assert resp.status_code == 200
    assert "secret-invitee@example.com" not in resp.text
    # Non-admins get the read-only name, not the rename form.
    assert 'name="org_name"' not in resp.text


async def test_admin_renames_org_and_normalises_slug(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await _org_with_admin(session, "A")
    await session.commit()
    set_client_auth(client, admin.id)
    new_slug = f"New Slug {uuid.uuid4().hex[:6]}"

    resp = await client.post(
        "/settings/organization",
        data={"org_name": "  Renamed Org  ", "org_slug": new_slug},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/settings/organization"
    await session.refresh(org)
    assert org.name == "Renamed Org"
    assert org.slug == new_slug.lower().replace(" ", "-")


async def test_rename_without_slug_keeps_slug(client: AsyncClient, session: AsyncSession) -> None:
    org, admin = await _org_with_admin(session, "A")
    await session.commit()
    old_slug = org.slug
    set_client_auth(client, admin.id)

    resp = await client.post("/settings/organization", data={"org_name": "Just Name"})
    assert resp.status_code == 303
    await session.refresh(org)
    assert (org.name, org.slug) == ("Just Name", old_slug)


async def test_non_admin_cannot_rename_org(client: AsyncClient, session: AsyncSession) -> None:
    org, _admin = await _org_with_admin(session, "A")
    member = await _member(session, org, "A")
    await session.commit()
    old = (org.name, org.slug)
    set_client_auth(client, member.id)

    resp = await client.post(
        "/settings/organization", data={"org_name": "Hijacked", "org_slug": "hijacked"}
    )
    assert resp.status_code == 403
    await session.refresh(org)
    assert (org.name, org.slug) == old


async def test_admin_invite_creates_row_in_own_org_and_sends_email(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await _org_with_admin(session, "A")
    await session.commit()
    set_client_auth(client, admin.id)

    send = AsyncMock()
    with patch("app.emails.send_invite_email", new=send), \
         patch("app.api.rate_limit.check_rate_limit", new=AsyncMock(return_value=True)):
        resp = await client.post(
            "/settings/organization/invite",
            data={"invite_email": "  New.Person@Example.com "},
            headers=HX,
        )

    assert resp.status_code == 200
    assert "Invite sent to new.person@example.com" in resp.text
    rows = (await session.execute(
        select(OrgInvite).where(OrgInvite.email == "new.person@example.com")
    )).scalars().all()
    assert len(rows) == 1
    inv = rows[0]
    assert inv.org_id == org.id
    assert inv.invited_by_id == admin.id
    assert inv.accepted_at is None
    assert inv.expires_at > datetime.now(UTC)
    send.assert_awaited_once()
    kw = send.await_args.kwargs
    assert kw["to"] == "new.person@example.com"
    assert kw["org_name"] == "Org A"
    assert kw["invite_url"].endswith(f"/register?invite={inv.token}")


async def test_non_admin_cannot_invite(client: AsyncClient, session: AsyncSession) -> None:
    org, _admin = await _org_with_admin(session, "A")
    member = await _member(session, org, "A")
    await session.commit()
    set_client_auth(client, member.id)

    send = AsyncMock()
    with patch("app.emails.send_invite_email", new=send), \
         patch("app.api.rate_limit.check_rate_limit", new=AsyncMock(return_value=True)):
        resp = await client.post(
            "/settings/organization/invite",
            data={"invite_email": "friend@example.com"},
            headers=HX,
        )

    assert resp.status_code == 403
    assert (await session.execute(select(OrgInvite))).scalars().all() == []
    send.assert_not_awaited()


async def test_invite_requires_email(client: AsyncClient, session: AsyncSession) -> None:
    _org, admin = await _org_with_admin(session, "A")
    await session.commit()
    set_client_auth(client, admin.id)

    send = AsyncMock()
    with patch("app.emails.send_invite_email", new=send):
        resp = await client.post(
            "/settings/organization/invite", data={"invite_email": "  "}, headers=HX
        )
    assert resp.status_code == 400
    assert (await session.execute(select(OrgInvite))).scalars().all() == []
    send.assert_not_awaited()


async def test_invite_rate_limited_writes_nothing(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, admin = await _org_with_admin(session, "A")
    await session.commit()
    set_client_auth(client, admin.id)

    send = AsyncMock()
    with patch("app.emails.send_invite_email", new=send), \
         patch("app.api.rate_limit.check_rate_limit", new=AsyncMock(return_value=False)):
        resp = await client.post(
            "/settings/organization/invite", data={"invite_email": "x@example.com"}, headers=HX
        )
    assert resp.status_code == 429
    assert (await session.execute(select(OrgInvite))).scalars().all() == []
    send.assert_not_awaited()


async def test_admin_resends_own_org_invite_rotating_token(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await _org_with_admin(session, "A")
    inv = _invite(org, admin, "pending@example.com",
                  expires_at=datetime.now(UTC) + timedelta(hours=1))
    session.add(inv)
    await session.commit()
    old_token, old_expiry = inv.token, inv.expires_at
    set_client_auth(client, admin.id)

    send = AsyncMock()
    with patch("app.emails.send_invite_email", new=send), \
         patch("app.api.rate_limit.check_rate_limit", new=AsyncMock(return_value=True)):
        resp = await client.post(
            f"/settings/organization/invites/{inv.id}/resend", headers=HX
        )

    assert resp.status_code == 200
    assert "Resent to pending@example.com" in resp.text
    await session.refresh(inv)
    assert inv.token != old_token
    assert inv.expires_at > old_expiry
    send.assert_awaited_once()
    assert send.await_args.kwargs["to"] == "pending@example.com"
    assert send.await_args.kwargs["invite_url"].endswith(f"/register?invite={inv.token}")


async def test_admin_cannot_resend_another_orgs_invite(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_a, admin_a = await _org_with_admin(session, "A")
    _org_b, admin_b = await _org_with_admin(session, "B")
    inv = _invite(org_a, admin_a, "a-invitee@example.com")
    session.add(inv)
    await session.commit()
    old = (inv.token, inv.expires_at)
    set_client_auth(client, admin_b.id)

    send = AsyncMock()
    with patch("app.emails.send_invite_email", new=send), \
         patch("app.api.rate_limit.check_rate_limit", new=AsyncMock(return_value=True)):
        resp = await client.post(
            f"/settings/organization/invites/{inv.id}/resend", headers=HX
        )

    assert resp.status_code == 404
    await session.refresh(inv)
    assert (inv.token, inv.expires_at) == old
    send.assert_not_awaited()


async def test_non_admin_cannot_resend_invite(client: AsyncClient, session: AsyncSession) -> None:
    org, admin = await _org_with_admin(session, "A")
    member = await _member(session, org, "A")
    inv = _invite(org, admin, "p@example.com")
    session.add(inv)
    await session.commit()
    old_token = inv.token
    set_client_auth(client, member.id)

    send = AsyncMock()
    with patch("app.emails.send_invite_email", new=send):
        resp = await client.post(
            f"/settings/organization/invites/{inv.id}/resend", headers=HX
        )
    assert resp.status_code == 403
    await session.refresh(inv)
    assert inv.token == old_token
    send.assert_not_awaited()


async def test_resend_of_accepted_invite_is_refused(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await _org_with_admin(session, "A")
    inv = _invite(org, admin, "done@example.com", accepted_at=datetime.now(UTC))
    session.add(inv)
    await session.commit()
    old_token = inv.token
    set_client_auth(client, admin.id)

    send = AsyncMock()
    with patch("app.emails.send_invite_email", new=send), \
         patch("app.api.rate_limit.check_rate_limit", new=AsyncMock(return_value=True)):
        resp = await client.post(
            f"/settings/organization/invites/{inv.id}/resend", headers=HX
        )
    assert resp.status_code == 400
    await session.refresh(inv)
    assert inv.token == old_token
    send.assert_not_awaited()


async def test_resend_unknown_invite_404(client: AsyncClient, session: AsyncSession) -> None:
    _org, admin = await _org_with_admin(session, "A")
    await session.commit()
    set_client_auth(client, admin.id)
    resp = await client.post(
        f"/settings/organization/invites/{uuid.uuid4()}/resend", headers=HX
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Scenario templates
# ---------------------------------------------------------------------------


async def test_template_list_empty_for_org_without_templates(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_a, admin_a = await _org_with_admin(session, "A")
    _org_b, admin_b = await _org_with_admin(session, "B")
    session.add(_template(org_a, admin_a, "Alpha Secret Template"))
    await session.commit()
    set_client_auth(client, admin_b.id)

    resp = await client.get("/ui/settings/scenario-templates", headers=HX)
    assert resp.status_code == 200
    assert "Alpha Secret Template" not in resp.text
    assert "No templates saved yet" in resp.text


@_SKIP_WIN
async def test_template_list_shows_only_own_org(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_a, admin_a = await _org_with_admin(session, "A")
    org_b, admin_b = await _org_with_admin(session, "B")
    session.add_all([
        _template(org_a, admin_a, "Alpha Secret Template"),
        _template(org_b, admin_b, "Bravo Own Template"),
    ])
    await session.commit()
    set_client_auth(client, admin_b.id)

    resp = await client.get("/ui/settings/scenario-templates", headers=HX)
    assert resp.status_code == 200
    assert "Bravo Own Template" in resp.text
    assert "Alpha Secret Template" not in resp.text


async def test_template_list_requires_session(client: AsyncClient) -> None:
    resp = await client.get("/ui/settings/scenario-templates", headers=HX)
    assert resp.status_code == 401


async def test_delete_template_clears_every_default_pointer(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await _org_with_admin(session, "A")
    member = await _member(session, org, "A")
    tmpl = _template(org, admin, "Doomed")
    keep = _template(org, admin, "Keeper")
    session.add_all([tmpl, keep])
    await session.flush()
    org.default_template_id = tmpl.id
    admin.default_template_id = tmpl.id
    member.default_template_id = keep.id
    await session.commit()
    set_client_auth(client, admin.id)

    resp = await client.post(
        f"/ui/settings/scenario-templates/{tmpl.id}/delete", headers=HX
    )
    assert resp.status_code == 200
    assert await session.get(ScenarioTemplate, tmpl.id) is None
    await session.refresh(org)
    await session.refresh(admin)
    await session.refresh(member)
    assert org.default_template_id is None
    assert admin.default_template_id is None
    assert member.default_template_id == keep.id


async def test_other_org_cannot_delete_template(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_a, admin_a = await _org_with_admin(session, "A")
    _org_b, admin_b = await _org_with_admin(session, "B")
    tmpl = _template(org_a, admin_a, "Alpha's")
    session.add(tmpl)
    await session.flush()
    org_a.default_template_id = tmpl.id
    await session.commit()
    set_client_auth(client, admin_b.id)

    resp = await client.post(
        f"/ui/settings/scenario-templates/{tmpl.id}/delete", headers=HX
    )
    assert resp.status_code == 404
    still_there = (await session.execute(
        select(ScenarioTemplate.id).where(ScenarioTemplate.id == tmpl.id)
    )).scalar_one_or_none()
    assert still_there == tmpl.id
    await session.refresh(org_a)
    assert org_a.default_template_id == tmpl.id


async def test_admin_sets_org_default(client: AsyncClient, session: AsyncSession) -> None:
    org, admin = await _org_with_admin(session, "A")
    tmpl = _template(org, admin, "T")
    session.add(tmpl)
    await session.commit()
    set_client_auth(client, admin.id)

    resp = await client.post(
        f"/ui/settings/scenario-templates/{tmpl.id}/set-org-default", headers=HX
    )
    assert resp.status_code == 200
    await session.refresh(org)
    assert org.default_template_id == tmpl.id


async def test_non_admin_cannot_set_org_default(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await _org_with_admin(session, "A")
    member = await _member(session, org, "A")
    tmpl = _template(org, admin, "T")
    session.add(tmpl)
    await session.commit()
    set_client_auth(client, member.id)

    resp = await client.post(
        f"/ui/settings/scenario-templates/{tmpl.id}/set-org-default", headers=HX
    )
    assert resp.status_code == 403
    await session.refresh(org)
    assert org.default_template_id is None


async def test_other_org_admin_cannot_set_org_default_to_foreign_template(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_a, admin_a = await _org_with_admin(session, "A")
    org_b, admin_b = await _org_with_admin(session, "B")
    tmpl = _template(org_a, admin_a, "Alpha's")
    session.add(tmpl)
    await session.commit()
    set_client_auth(client, admin_b.id)

    resp = await client.post(
        f"/ui/settings/scenario-templates/{tmpl.id}/set-org-default", headers=HX
    )
    assert resp.status_code == 404
    await session.refresh(org_a)
    await session.refresh(org_b)
    assert org_a.default_template_id is None
    assert org_b.default_template_id is None


async def test_member_sets_own_user_default(client: AsyncClient, session: AsyncSession) -> None:
    org, admin = await _org_with_admin(session, "A")
    member = await _member(session, org, "A")
    tmpl = _template(org, admin, "T")
    session.add(tmpl)
    await session.commit()
    set_client_auth(client, member.id)

    resp = await client.post(
        f"/ui/settings/scenario-templates/{tmpl.id}/set-user-default", headers=HX
    )
    assert resp.status_code == 200
    await session.refresh(member)
    await session.refresh(admin)
    await session.refresh(org)
    assert member.default_template_id == tmpl.id
    # Only the caller's pointer moves.
    assert admin.default_template_id is None
    assert org.default_template_id is None


async def test_cannot_set_user_default_to_another_orgs_template(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_a, admin_a = await _org_with_admin(session, "A")
    _org_b, admin_b = await _org_with_admin(session, "B")
    tmpl = _template(org_a, admin_a, "Alpha's")
    session.add(tmpl)
    await session.commit()
    set_client_auth(client, admin_b.id)

    resp = await client.post(
        f"/ui/settings/scenario-templates/{tmpl.id}/set-user-default", headers=HX
    )
    assert resp.status_code == 404
    await session.refresh(admin_b)
    assert admin_b.default_template_id is None


# ---------------------------------------------------------------------------
# Admin backfill, preferences, splash
# ---------------------------------------------------------------------------


def _listing(org: Organization, **kw: Any) -> Opportunity:
    return Opportunity(
        id=uuid.uuid4(),
        org_id=org.id,
        source="crexi",
        source_id=uuid.uuid4().hex,
        source_url=f"https://crexi.example/{uuid.uuid4().hex}",
        **kw,
    )


async def test_site_admin_backfill_classifies_only_unbucketed_listings(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await _org_with_admin(session, "A")
    admin.is_admin = True
    out_of_market = _listing(org, county="Lane")
    portland = _listing(org, county="Multnomah", city="Portland")
    already = _listing(org, county="Lane", priority_bucket="contextual")
    session.add_all([out_of_market, portland, already])
    await session.commit()
    set_client_auth(client, admin.id)

    resp = await client.post("/ui/admin/backfill-listing-buckets")
    assert resp.status_code == 200
    assert resp.json() == {"updated": 2}
    for row in (out_of_market, portland, already):
        await session.refresh(row)
    assert out_of_market.priority_bucket == "out_of_market"
    assert portland.priority_bucket == "contextual"
    # A bucket that was already set is not re-classified.
    assert already.priority_bucket == "contextual"


async def test_backfill_requires_session(client: AsyncClient) -> None:
    resp = await client.post("/ui/admin/backfill-listing-buckets")
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


async def test_preferences_requires_session(client: AsyncClient) -> None:
    resp = await client.get("/settings/preferences")
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


async def test_preferences_renders_for_member(client: AsyncClient, session: AsyncSession) -> None:
    org, _admin = await _org_with_admin(session, "A")
    member = await _member(session, org, "A")
    await session.commit()
    set_client_auth(client, member.id)

    resp = await client.get("/settings/preferences")
    assert resp.status_code == 200
    assert "<html" in resp.text.lower()


async def test_splash_is_unreachable_from_a_browser_session(
    client: AsyncClient, session: AsyncSession
) -> None:
    """/splash is the pre-auth "who's working today?" picker. It is not in
    the UI path list, so the API-key middleware refuses a browser session
    (403). Its template lists every user in every org, so it must stay
    unreachable to browsers unless it is scoped first."""
    _org, user = await seed_org(session)
    user.name = "Splash Viewer"
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.get("/splash")
    assert resp.status_code == 403
    assert "Splash Viewer" not in resp.text


async def test_splash_renders_for_api_key_plus_session(
    client: AsyncClient, session: AsyncSession, api_key: str
) -> None:
    org, admin = await _org_with_admin(session, "A")
    member = await _member(session, org, "A")
    await session.commit()
    set_client_auth(client, admin.id)
    client.headers["X-API-Key"] = api_key

    resp = await client.get("/splash")
    assert resp.status_code == 200
    assert admin.name in resp.text
    assert member.name in resp.text
