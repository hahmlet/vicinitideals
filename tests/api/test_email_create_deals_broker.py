"""Broker linking on POST /ui/deals/email/{id}/create-deals.

Covers:
- Accepted broker suggestions → Broker created (email lowercased, name split)
  and linked to every Opportunity created from the email
- Repeat sender email (different case) → existing Broker reused, no new row
- Rejected broker suggestion (accepted=False) → no Broker, no link
- Unreviewed suggestion (accepted=None) → applied, same as acquisition_cost
- Name-only suggestion (no email) → no Broker (email is the dedupe key)
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_db
from app.api.main import app
from app.models.broker import Broker
from app.models.email_ingest import EmailDealSuggestion, InboundEmail
from app.models.opportunity import Opportunity


# ---------------------------------------------------------------------------
# In-memory Redis stand-in (same as tests/api/test_email_create_deals.py)
# ---------------------------------------------------------------------------

class _FakeRedis:
    def __init__(self, store: dict, *, decode_responses: bool = False):
        self._store = store
        self._decode = decode_responses

    def get(self, key: str):
        val = self._store.get(key)
        if val is None:
            return None
        if self._decode:
            return val.decode() if isinstance(val, bytes) else val
        return val if isinstance(val, bytes) else str(val).encode()

    def set(self, key: str, value, ex=None):
        if isinstance(value, str):
            value = value.encode()
        elif not isinstance(value, bytes):
            value = str(value).encode()
        self._store[key] = value

    def getdel(self, key: str):
        val = self.get(key)
        self._store.pop(key, None)
        return val


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _auth_client_kwargs(user_id) -> dict:
    """AsyncClient kwargs for an authenticated HTMX request.

    HTMX requests no longer bypass require_auth_for_ui (2026-07-08 fix), so
    carry a signed session cookie; authenticated HTMX mutations must also
    present a matching CSRF token. X-User-ID stays for the route's own
    user lookup.
    """
    from app.api.auth import COOKIE_NAME, create_session_token
    from app.api.csrf import make_csrf_token

    uid = str(user_id)
    return {
        "headers": {
            "X-User-ID": uid,
            "hx-request": "true",
            "X-CSRF-Token": make_csrf_token(uid),
        },
        "cookies": {COOKIE_NAME: create_session_token(uid)},
    }


async def _seed_org_and_user(session):
    from app.models.org import Organization, User
    suffix = uuid.uuid4().hex[:8]
    org = Organization(id=uuid.uuid4(), name=f"Broker Test Org {suffix}", slug=f"broker-test-{suffix}")
    session.add(org)
    await session.flush()
    user = User(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Test User",
        email=f"test-{suffix}@example.com",
        hashed_password="$2b$12$dummy_hash_not_used_in_tests",
    )
    session.add(user)
    await session.flush()
    return org, user


async def _seed_inbound_email(session, org_id: uuid.UUID, task_ids: list[str]) -> InboundEmail:
    attachments_meta = [
        {"proforma_task_id": tid, "filename": f"file_{i}.xlsx", "size_bytes": 1024}
        for i, tid in enumerate(task_ids)
    ]
    row = InboundEmail(
        id=uuid.uuid4(),
        org_id=org_id,
        sender_email="broker@example.com",
        status="pending_review",
        proforma_task_ids=task_ids,
        attachments_meta=attachments_meta,
    )
    session.add(row)
    await session.flush()
    return row


async def _seed_broker_suggestions(
    session,
    email_row: InboundEmail,
    *,
    name: str | None = "Jane Doe",
    email: str | None = "Jane.Doe@Brokerage.com",
    accepted: bool | None = None,
) -> None:
    for field_path, value in (("broker_name", name), ("broker_email", email)):
        if value is None:
            continue
        session.add(EmailDealSuggestion(
            inbound_email_id=email_row.id,
            opportunity_id=None,
            field_path=field_path,
            suggested_value=value,
            confidence=0.7,
            source_type="llm_extraction",
            accepted=accepted,
        ))
    await session.flush()


async def _post_create_deals(session, user, email_row, *, n_files: int = 1):
    store: dict = {}

    def _fake_from_url(url, **kwargs):
        return _FakeRedis(store, decode_responses=kwargs.get("decode_responses", False))

    async def _db_override() -> AsyncGenerator:
        yield session

    data: dict[str, str] = {}
    for i in range(n_files):
        data.update({
            f"task_id_{i}": email_row.proforma_task_ids[i],
            f"file_kind_{i}": "xlsx",
            f"deal_name_{i}": f"Deal {i}",
            f"rev_sheet_{i}": "Revenue",
        })

    app.dependency_overrides[get_db] = _db_override
    try:
        with patch("redis.from_url", _fake_from_url):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
                **_auth_client_kwargs(user.id),
            ) as client:
                resp = await client.post(
                    f"/ui/deals/email/{email_row.id}/create-deals",
                    data=data,
                    follow_redirects=False,
                )
    finally:
        app.dependency_overrides.pop(get_db, None)
    return resp


async def _brokers(session) -> list[Broker]:
    return list((await session.execute(select(Broker))).scalars().all())


async def _opportunities(session, org_id) -> list[Opportunity]:
    return list((await session.execute(
        select(Opportunity).where(Opportunity.org_id == org_id)
    )).scalars().all())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_accepted_broker_creates_and_links(session):
    """Accepted suggestions → Broker row (lowercased email, split name) linked
    to every Opportunity created from the email."""
    org, user = await _seed_org_and_user(session)
    email_row = await _seed_inbound_email(session, org.id, ["task-b1", "task-b2"])
    await _seed_broker_suggestions(session, email_row, accepted=True)
    await session.commit()

    resp = await _post_create_deals(session, user, email_row, n_files=2)
    assert resp.status_code == 303

    brokers = await _brokers(session)
    assert len(brokers) == 1
    broker = brokers[0]
    assert broker.email == "jane.doe@brokerage.com"
    assert broker.first_name == "Jane"
    assert broker.last_name == "Doe"

    opps = await _opportunities(session, org.id)
    assert len(opps) == 2
    assert all(o.broker_id == broker.id for o in opps)


@pytest.mark.asyncio
async def test_repeat_sender_reuses_existing_broker(session):
    """Second email from the same broker (different email case) links to the
    existing Broker row instead of creating a duplicate."""
    org, user = await _seed_org_and_user(session)
    existing = Broker(id=uuid.uuid4(), email="JANE.DOE@BROKERAGE.COM")
    session.add(existing)
    email_row = await _seed_inbound_email(session, org.id, ["task-r1"])
    await _seed_broker_suggestions(session, email_row, accepted=True)
    await session.commit()

    resp = await _post_create_deals(session, user, email_row)
    assert resp.status_code == 303

    brokers = await _brokers(session)
    assert len(brokers) == 1, "must reuse the existing broker, not create a duplicate"
    assert brokers[0].id == existing.id

    # Missing name fields got filled from the suggestion (never overwritten).
    await session.refresh(existing)
    assert existing.first_name == "Jane"
    assert existing.last_name == "Doe"

    opps = await _opportunities(session, org.id)
    assert opps[0].broker_id == existing.id


@pytest.mark.asyncio
async def test_rejected_broker_creates_nothing(session):
    """accepted=False → no Broker row, opportunity has no broker link."""
    org, user = await _seed_org_and_user(session)
    email_row = await _seed_inbound_email(session, org.id, ["task-x1"])
    await _seed_broker_suggestions(session, email_row, accepted=False)
    await session.commit()

    resp = await _post_create_deals(session, user, email_row)
    assert resp.status_code == 303

    assert await _brokers(session) == []
    opps = await _opportunities(session, org.id)
    assert opps[0].broker_id is None


@pytest.mark.asyncio
async def test_unreviewed_broker_suggestion_is_applied(session):
    """accepted=None (user never clicked) → broker still created/linked,
    matching how acquisition_cost is applied without an explicit accept."""
    org, user = await _seed_org_and_user(session)
    email_row = await _seed_inbound_email(session, org.id, ["task-u1"])
    await _seed_broker_suggestions(session, email_row, accepted=None)
    await session.commit()

    resp = await _post_create_deals(session, user, email_row)
    assert resp.status_code == 303

    brokers = await _brokers(session)
    assert len(brokers) == 1
    opps = await _opportunities(session, org.id)
    assert opps[0].broker_id == brokers[0].id


@pytest.mark.asyncio
async def test_name_only_suggestion_creates_no_broker(session):
    """Without an email suggestion there is no safe dedupe key → no Broker."""
    org, user = await _seed_org_and_user(session)
    email_row = await _seed_inbound_email(session, org.id, ["task-n1"])
    await _seed_broker_suggestions(session, email_row, email=None, accepted=True)
    await session.commit()

    resp = await _post_create_deals(session, user, email_row)
    assert resp.status_code == 303

    assert await _brokers(session) == []
    opps = await _opportunities(session, org.id)
    assert opps[0].broker_id is None
