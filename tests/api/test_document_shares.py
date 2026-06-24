"""Integration tests for external document sharing (Phase 3).

Guest routes are auth-exempt and token-gated, so they run without a session.
Owner create/revoke routes require an authenticated session (CI/LAN).
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.emails.tokens import make_doc_share_token
from app.models.deal import Deal, Scenario, ProjectType
from app.models.document import Document, DocumentShare, DocumentTask
from app.models.opportunity import Opportunity
from app.models.project import Project

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _doc_storage_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.document_storage_path", str(tmp_path), raising=True
    )


async def _auth(client: AsyncClient, user_id) -> None:
    from tests.conftest import set_client_auth

    set_client_auth(client, user_id)


async def _seed_project(session: AsyncSession):
    from tests.conftest import seed_opportunity, seed_org

    org, user = await seed_org(session)
    opp: Opportunity = await seed_opportunity(session, org, user)
    deal = Deal(id=uuid.uuid4(), org_id=org.id, name="Share Deal", created_by_user_id=user.id)
    session.add(deal)
    await session.flush()
    scenario = Scenario(
        id=uuid.uuid4(), deal_id=deal.id, created_by_user_id=user.id,
        name="Base", version=1, is_active=True, project_type=ProjectType.value_add,
    )
    session.add(scenario)
    await session.flush()
    project = Project(id=uuid.uuid4(), scenario_id=scenario.id, opportunity_id=opp.id, name="Shared P")
    session.add(project)
    await session.commit()
    return project, user, org


async def _seed_share(
    session: AsyncSession,
    org,
    project,
    *,
    revoked=False,
    can_upload=True,
    can_download=True,
    expires_at=None,
) -> DocumentShare:
    share = DocumentShare(
        org_id=org.id,
        project_id=project.id,
        label="Lender",
        revoked=revoked,
        can_upload=can_upload,
        can_download=can_download,
        expires_at=expires_at,
    )
    session.add(share)
    await session.commit()
    return share


# ── Guest (no auth) ────────────────────────────────────────────────────────

async def test_guest_page_loads(client: AsyncClient, session: AsyncSession):
    project, _user, org = await _seed_project(session)
    share = await _seed_share(session, org, project)
    token = make_doc_share_token(share.id)

    resp = await client.get(f"/share/{token}")
    assert resp.status_code == 200, resp.text
    assert "Shared P" in resp.text


async def test_guest_invalid_token_404(client: AsyncClient, session: AsyncSession):
    resp = await client.get("/share/totally-bogus-token")
    assert resp.status_code == 404


async def test_guest_revoked_share_404(client: AsyncClient, session: AsyncSession):
    project, _user, org = await _seed_project(session)
    share = await _seed_share(session, org, project, revoked=True)
    token = make_doc_share_token(share.id)

    assert (await client.get(f"/share/{token}")).status_code == 404


async def test_guest_upload_and_download(client: AsyncClient, session: AsyncSession):
    project, _user, org = await _seed_project(session)
    share = await _seed_share(session, org, project)
    token = make_doc_share_token(share.id)

    up = await client.post(
        f"/share/{token}/upload",
        files={"files": ("guest.pdf", b"%PDF guest", "application/pdf")},
    )
    assert up.status_code == 200
    assert "guest.pdf" in up.text

    doc = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalar_one()
    assert doc.task_id is None

    dl = await client.get(f"/share/{token}/documents/{doc.id}/download")
    assert dl.status_code == 200
    assert dl.content == b"%PDF guest"


async def test_guest_cannot_access_other_project_doc(client: AsyncClient, session: AsyncSession):
    project, _user, org = await _seed_project(session)
    share = await _seed_share(session, org, project)
    token = make_doc_share_token(share.id)
    # A document on a DIFFERENT project — must not be reachable via this token.
    other_project, _u2, other_org = await _seed_project(session)
    other_doc = Document(
        org_id=other_org.id, project_id=other_project.id,
        filename="secret.pdf", size_bytes=3, sha256="x", storage_key="k",
    )
    session.add(other_doc)
    await session.commit()

    resp = await client.get(f"/share/{token}/documents/{other_doc.id}/download")
    assert resp.status_code == 404


async def test_guest_task_upload(client: AsyncClient, session: AsyncSession):
    project, _user, org = await _seed_project(session)
    share = await _seed_share(session, org, project)
    token = make_doc_share_token(share.id)
    task = DocumentTask(org_id=org.id, project_id=project.id, title="Leases")
    session.add(task)
    await session.commit()

    resp = await client.post(
        f"/share/{token}/tasks/{task.id}/upload",
        files={"files": ("t.pdf", b"TT", "application/pdf")},
    )
    assert resp.status_code == 200
    doc = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalar_one()
    assert doc.task_id == task.id


async def test_guest_has_no_destructive_route(client: AsyncClient, session: AsyncSession):
    project, _user, org = await _seed_project(session)
    share = await _seed_share(session, org, project)
    token = make_doc_share_token(share.id)
    # No archive/delete endpoint exists under /share/. A bulk-style POST 404s.
    resp = await client.post(f"/share/{token}/bulk", data={"action": "delete"})
    assert resp.status_code in (404, 405)


# ── Owner (auth — CI/LAN) ──────────────────────────────────────────────────

async def test_owner_create_and_revoke(client: AsyncClient, session: AsyncSession):
    project, user, org = await _seed_project(session)
    await _auth(client, user.id)

    created = await client.post(f"/ui/projects/{project.id}/shares", data={"label": "Bank"})
    assert created.status_code == 200, created.text
    share = (
        await session.execute(select(DocumentShare).where(DocumentShare.project_id == project.id))
    ).scalar_one()
    assert share.revoked is False

    revoked = await client.post(f"/ui/shares/{share.id}/revoke")
    assert revoked.status_code == 200
    await session.refresh(share)
    assert share.revoked is True
    assert share.revoked_at is not None


# ── Per-link permissions + expiry ──────────────────────────────────────────

async def test_owner_create_with_permissions_and_expiry(
    client: AsyncClient, session: AsyncSession
):
    project, user, org = await _seed_project(session)
    await _auth(client, user.id)

    created = await client.post(
        f"/ui/projects/{project.id}/shares",
        data={"label": "Lender", "can_upload": "true", "expires_days": "7"},
    )
    assert created.status_code == 200, created.text
    share = (
        await session.execute(select(DocumentShare).where(DocumentShare.project_id == project.id))
    ).scalar_one()
    # can_download checkbox omitted → False; can_upload checked → True.
    assert share.can_upload is True
    assert share.can_download is False
    assert share.expires_at is not None


async def test_guest_upload_blocked_when_disabled(client: AsyncClient, session: AsyncSession):
    project, _user, org = await _seed_project(session)
    share = await _seed_share(session, org, project, can_upload=False)
    token = make_doc_share_token(share.id)

    resp = await client.post(
        f"/share/{token}/upload",
        files={"files": ("nope.pdf", b"%PDF no", "application/pdf")},
    )
    assert resp.status_code == 403


async def test_guest_download_blocked_but_view_allowed(
    client: AsyncClient, session: AsyncSession
):
    project, _user, org = await _seed_project(session)
    # Upload allowed so we can stage a file; download disabled.
    share = await _seed_share(session, org, project, can_upload=True, can_download=False)
    token = make_doc_share_token(share.id)

    up = await client.post(
        f"/share/{token}/upload",
        files={"files": ("look.pdf", b"%PDF look", "application/pdf")},
    )
    assert up.status_code == 200
    doc = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalar_one()

    # Download is gated...
    assert (await client.get(f"/share/{token}/documents/{doc.id}/download")).status_code == 403
    assert (await client.get(f"/share/{token}/zip")).status_code == 403
    # ...but inline view of a PDF is always allowed.
    view = await client.get(f"/share/{token}/documents/{doc.id}/view")
    assert view.status_code == 200
    assert view.headers["content-type"].startswith("application/pdf")


async def test_guest_expired_share_404(client: AsyncClient, session: AsyncSession):
    from datetime import datetime, timedelta, timezone

    project, _user, org = await _seed_project(session)
    share = await _seed_share(
        session, org, project, expires_at=datetime.now(timezone.utc) - timedelta(days=1)
    )
    token = make_doc_share_token(share.id)

    assert (await client.get(f"/share/{token}")).status_code == 404
