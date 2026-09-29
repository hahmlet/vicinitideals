"""Integration tests for the email_ingest JSON router (app/api/routers/email_ingest.py).

Covers:
  - POST /api/email-ingest                          Resend (Svix-signed) webhook
  - POST /api/email-suggestions/{id}/accept         mark a suggestion accepted
  - POST /api/email-suggestions/{id}/reject         mark it rejected

The webhook tests sign real payloads with a test secret, so the HMAC check
itself is exercised — not patched out. The Celery hand-off is patched and
asserted on.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.email_ingest import EmailDealSuggestion, InboundEmail, InboundEmailStatus

from tests.conftest import seed_org

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("api_key_auth")]

_KEY = b"test-webhook-key-0123456789abcdef"
_SECRET = "whsec_" + base64.b64encode(_KEY).decode()
_DELAY = "app.tasks.email_ingest.process_inbound_email.delay"


@pytest.fixture
def webhook_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr(settings, "resend_webhook_secret", _SECRET)
    monkeypatch.setattr(settings, "inbound_email_org_id", None)
    return _SECRET


def _signed(body: bytes, *, ts: int | None = None, key: bytes = _KEY) -> dict[str, str]:
    svix_id = f"msg_{uuid.uuid4().hex}"
    stamp = str(ts if ts is not None else int(time.time()))
    sig = base64.b64encode(
        hmac.new(key, f"{svix_id}.{stamp}.".encode() + body, hashlib.sha256).digest()
    ).decode()
    return {
        "svix-id": svix_id,
        "svix-timestamp": stamp,
        "svix-signature": f"v1,{sig}",
        "content-type": "application/json",
    }


def _payload(**data) -> bytes:
    return json.dumps({
        "type": "email.received",
        "data": {
            "email_id": "re_123",
            "from": "broker@example.com",
            "subject": "12-plex in Gresham",
            "attachments": [{"filename": "OM.pdf"}],
            **data,
        },
    }).encode()


async def _inbound(session: AsyncSession) -> list[InboundEmail]:
    session.expunge_all()  # fresh read; keeps seeded objects readable
    return list((await session.execute(select(InboundEmail))).scalars())


# ---------------------------------------------------------------------------
# POST /api/email-ingest
# ---------------------------------------------------------------------------


async def test_webhook_stores_email_and_queues_fetch(
    client: AsyncClient, session: AsyncSession, webhook_secret: str
) -> None:
    org, _user = await seed_org(session)
    await session.commit()
    body = _payload()

    with patch(_DELAY) as delay:
        resp = await client.post("/api/email-ingest", content=body, headers=_signed(body))

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "accepted"
    rows = await _inbound(session)
    assert len(rows) == 1
    row = rows[0]
    assert str(row.id) == resp.json()["id"]
    assert row.org_id == org.id
    assert row.sender_email == "broker@example.com"
    assert row.subject == "12-plex in Gresham"
    assert row.attachments_meta == [{"filename": "OM.pdf"}]
    assert row.status == InboundEmailStatus.pending.value
    delay.assert_called_once_with(str(row.id), "re_123")


async def test_webhook_rejects_bad_signatures(
    client: AsyncClient, session: AsyncSession, webhook_secret: str
) -> None:
    await seed_org(session)
    await session.commit()
    body = _payload()

    forged = _signed(body, key=b"not-the-key")
    stale = _signed(body, ts=int(time.time()) - 3600)
    tampered = _signed(body)
    unsigned = {"content-type": "application/json"}

    with patch(_DELAY) as delay:
        for headers, content in (
            (forged, body),
            (stale, body),
            (tampered, body.replace(b"Gresham", b"Salem")),
            (unsigned, body),
        ):
            resp = await client.post("/api/email-ingest", content=content, headers=headers)
            assert resp.status_code == 403, (headers, resp.text)

    delay.assert_not_called()
    assert await _inbound(session) == []


async def test_webhook_refuses_everything_without_a_secret(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "resend_webhook_secret", "")
    await seed_org(session)
    await session.commit()
    body = _payload()

    resp = await client.post("/api/email-ingest", content=body, headers=_signed(body))

    assert resp.status_code == 403
    assert await _inbound(session) == []


async def test_webhook_ignores_other_events_and_requires_email_id(
    client: AsyncClient, session: AsyncSession, webhook_secret: str
) -> None:
    await seed_org(session)
    await session.commit()

    other = json.dumps({"type": "email.bounced", "data": {"email_id": "re_1"}}).encode()
    no_id = _payload(email_id=None)

    with patch(_DELAY) as delay:
        ignored = await client.post("/api/email-ingest", content=other, headers=_signed(other))
        missing = await client.post("/api/email-ingest", content=no_id, headers=_signed(no_id))

    assert ignored.status_code == 200
    assert ignored.json()["status"] == "ignored"
    assert missing.status_code == 400
    delay.assert_not_called()
    assert await _inbound(session) == []


async def test_webhook_routes_to_configured_org_when_several_exist(
    client: AsyncClient, session: AsyncSession, webhook_secret: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _org_a, _ = await seed_org(session)
    org_b, _ = await seed_org(session)
    await session.commit()
    body = _payload()

    # Two orgs and no INBOUND_EMAIL_ORG_ID: refuse rather than guess
    with patch(_DELAY):
        ambiguous = await client.post("/api/email-ingest", content=body, headers=_signed(body))
    assert ambiguous.status_code == 500
    assert await _inbound(session) == []

    monkeypatch.setattr(settings, "inbound_email_org_id", org_b.id)
    with patch(_DELAY):
        routed = await client.post("/api/email-ingest", content=body, headers=_signed(body))
    assert routed.status_code == 200, routed.text
    assert [r.org_id for r in await _inbound(session)] == [org_b.id]


# ---------------------------------------------------------------------------
# POST /api/email-suggestions/{id}/accept | /reject
# ---------------------------------------------------------------------------


async def _seed_suggestion(session: AsyncSession, org_id: uuid.UUID) -> EmailDealSuggestion:
    email_row = InboundEmail(
        id=uuid.uuid4(),
        org_id=org_id,
        sender_email="broker@example.com",
        status=InboundEmailStatus.pending.value,
        proforma_task_ids=[],
        attachments_meta=[],
    )
    session.add(email_row)
    await session.flush()
    suggestion = EmailDealSuggestion(
        id=uuid.uuid4(),
        inbound_email_id=email_row.id,
        field_path="asking_price",
        suggested_value="1250000",
        source_type="body",
    )
    session.add(suggestion)
    await session.flush()
    return suggestion


async def test_accept_then_reject_suggestion(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, user = await seed_org(session)
    suggestion = await _seed_suggestion(session, org.id)
    await session.commit()
    headers = {"X-User-ID": str(user.id)}

    accepted = await client.post(f"/api/email-suggestions/{suggestion.id}/accept", headers=headers)
    assert accepted.status_code == 200, accepted.text
    assert "Asking Price" in accepted.text
    assert "1250000" in accepted.text
    assert "✓ Accepted" in accepted.text
    await session.refresh(suggestion)
    assert suggestion.accepted is True

    rejected = await client.post(f"/api/email-suggestions/{suggestion.id}/reject", headers=headers)
    assert rejected.status_code == 200
    assert "✓ Accepted" not in rejected.text
    await session.refresh(suggestion)
    assert suggestion.accepted is False


async def test_suggestion_in_another_org_is_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    _org, user = await seed_org(session)
    other_org, _other = await seed_org(session)
    theirs = await _seed_suggestion(session, other_org.id)
    await session.commit()
    headers = {"X-User-ID": str(user.id)}

    for action in ("accept", "reject"):
        resp = await client.post(f"/api/email-suggestions/{theirs.id}/{action}", headers=headers)
        assert resp.status_code == 404

    missing = await client.post(f"/api/email-suggestions/{uuid.uuid4()}/accept", headers=headers)
    assert missing.status_code == 404

    await session.refresh(theirs)
    assert theirs.accepted is None
