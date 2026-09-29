"""Integration tests for the email-ingest UI reads.

Routes covered:
    GET /ui/email-inbox
    GET /ui/deals/email/{inbound_email_id}/review

Inbound emails are org-owned (a broker's email body, attachments and the AI
suggestions extracted from them). The question these tests answer: can a
signed-in user of org B list or open org A's inbound email by id?
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_ingest import EmailDealSuggestion, InboundEmail, InboundEmailStatus
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


def _email(org, subject: str, *, body: str = "") -> InboundEmail:
    return InboundEmail(
        id=uuid.uuid4(), org_id=org.id, sender_email=f"broker-{uuid.uuid4().hex[:6]}@example.test",
        subject=subject, body_text=body, status=InboundEmailStatus.pending_review.value,
        proforma_task_ids=[], attachments_meta=[],
    )


async def test_inbox_lists_only_own_org_emails(client: AsyncClient, session: AsyncSession):
    org_a, user_a = await seed_org(session)
    org_b, _user_b = await seed_org(session)
    mine = _email(org_a, "Alpha OM: 12 units on Division")
    theirs = _email(org_b, "Bravo OM: secret off-market")
    session.add_all([mine, theirs])
    await session.commit()
    set_client_auth(client, user_a.id)

    resp = await client.get("/ui/email-inbox")
    assert resp.status_code == 200
    assert "Alpha OM: 12 units on Division" in resp.text
    assert mine.sender_email in resp.text
    assert f"/ui/deals/email/{mine.id}/review" in resp.text
    assert "Bravo OM" not in resp.text
    assert str(theirs.id) not in resp.text


async def test_inbox_requires_session(client: AsyncClient, session: AsyncSession):
    resp = await client.get("/ui/email-inbox", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/login")


async def test_review_shows_own_email_and_staged_file(
    client: AsyncClient, session: AsyncSession
):
    org, user = await seed_org(session)
    email = _email(org, "Alpha OM review", body="Asking 2.1M, 12 units")
    # A staged PDF (not xlsx, so no Redis read for sheet names).
    email.proforma_task_ids = ["task-om-1"]
    email.attachments_meta = [
        {"proforma_task_id": "task-om-1", "filename": "Alpha_OM.pdf", "size_bytes": 2048}
    ]
    session.add(email)
    await session.flush()
    session.add(EmailDealSuggestion(
        inbound_email_id=email.id, field_path="asking_price", suggested_value="2100000",
        confidence=0.9, source_type="email_body",
    ))
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.get(f"/ui/deals/email/{email.id}/review")
    assert resp.status_code == 200
    assert "Alpha OM review" in resp.text
    assert email.sender_email in resp.text
    assert "Asking 2.1M, 12 units" in resp.text
    # The config table offers the staged file for deal creation.
    assert f"/ui/deals/email/{email.id}/create-deals" in resp.text
    assert "Alpha_OM.pdf" in resp.text


async def test_review_of_other_orgs_email_is_404(client: AsyncClient, session: AsyncSession):
    org_a, _user_a = await seed_org(session)
    _org_b, user_b = await seed_org(session)
    email = _email(org_a, "Alpha private OM", body="Seller will take 1.8M")
    session.add(email)
    await session.commit()
    set_client_auth(client, user_b.id)

    resp = await client.get(f"/ui/deals/email/{email.id}/review")
    assert resp.status_code == 404
    assert "Alpha private OM" not in resp.text
    assert "Seller will take" not in resp.text


async def test_review_unknown_email_is_404(client: AsyncClient, session: AsyncSession):
    _org, user = await seed_org(session)
    await session.commit()
    set_client_auth(client, user.id)
    resp = await client.get(f"/ui/deals/email/{uuid.uuid4()}/review")
    assert resp.status_code == 404
