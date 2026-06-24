"""Tests for deal-wide guest sharing (one link → pick a project → room).

Guest deal routes are auth-exempt, so they run on Windows-local Postgres.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui_documents import _generate_share_slug
from app.models.deal import Deal, ProjectType, Scenario
from app.models.document import DealShare, Document
from app.models.opportunity import Opportunity
from app.models.project import Project

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _doc_storage_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.document_storage_path", str(tmp_path), raising=True
    )


async def _project_under(session, org, deal, name):
    scenario = Scenario(
        id=uuid.uuid4(), deal_id=deal.id, name=name, version=1, is_active=True,
        project_type=ProjectType.value_add,
    )
    session.add(scenario)
    await session.flush()
    project = Project(id=uuid.uuid4(), scenario_id=scenario.id, name=name)
    session.add(project)
    await session.flush()
    return project


async def _seed_deal_with_projects(session: AsyncSession):
    from tests.conftest import seed_org

    org, user = await seed_org(session)
    deal = Deal(id=uuid.uuid4(), org_id=org.id, name="Multi-Project Deal", created_by_user_id=user.id)
    session.add(deal)
    await session.flush()
    p1 = await _project_under(session, org, deal, "North Tower")
    p2 = await _project_under(session, org, deal, "South Annex")
    session.add(Document(
        org_id=org.id, project_id=p1.id, filename="lease.pdf",
        size_bytes=10, sha256="a", storage_key="a",
    ))
    await session.commit()
    return org, user, deal, p1, p2


async def _seed_deal_share(session, org, deal, *, revoked=False):
    ds = DealShare(
        org_id=org.id, deal_id=deal.id, label="Lender",
        slug=_generate_share_slug(), revoked=revoked,
    )
    session.add(ds)
    await session.commit()
    return ds


async def test_landing_lists_projects(client: AsyncClient, session: AsyncSession):
    org, _user, deal, p1, p2 = await _seed_deal_with_projects(session)
    ds = await _seed_deal_share(session, org, deal)

    resp = await client.get(f"/d/{ds.slug}")
    assert resp.status_code == 200, resp.text
    assert "North Tower" in resp.text
    assert "South Annex" in resp.text


async def test_pick_project_opens_room(client: AsyncClient, session: AsyncSession):
    org, _user, deal, p1, p2 = await _seed_deal_with_projects(session)
    ds = await _seed_deal_share(session, org, deal)

    resp = await client.get(f"/d/{ds.slug}/p/{p1.id}")
    assert resp.status_code == 200, resp.text
    assert "lease.pdf" in resp.text
    assert "All projects in this deal" in resp.text


async def test_project_outside_deal_404(client: AsyncClient, session: AsyncSession):
    org, _user, deal, p1, p2 = await _seed_deal_with_projects(session)
    ds = await _seed_deal_share(session, org, deal)
    # A project under a DIFFERENT deal must not be reachable via this link.
    other_deal = Deal(id=uuid.uuid4(), org_id=org.id, name="Other", created_by_user_id=None)
    session.add(other_deal)
    await session.flush()
    foreign = await _project_under(session, org, other_deal, "Foreign")
    await session.commit()

    resp = await client.get(f"/d/{ds.slug}/p/{foreign.id}")
    assert resp.status_code == 404


async def test_revoked_deal_share_404(client: AsyncClient, session: AsyncSession):
    org, _user, deal, p1, p2 = await _seed_deal_with_projects(session)
    ds = await _seed_deal_share(session, org, deal, revoked=True)

    assert (await client.get(f"/d/{ds.slug}")).status_code == 404
    assert (await client.get(f"/d/{ds.slug}/p/{p1.id}")).status_code == 404


async def test_expired_deal_share_404(client: AsyncClient, session: AsyncSession):
    org, _user, deal, p1, p2 = await _seed_deal_with_projects(session)
    ds = await _seed_deal_share(session, org, deal)
    ds.created_at = datetime.now(timezone.utc) - timedelta(days=365)
    await session.commit()

    assert (await client.get(f"/d/{ds.slug}")).status_code == 404


async def test_deal_guest_download(client: AsyncClient, session: AsyncSession, tmp_path):
    org, _user, deal, p1, p2 = await _seed_deal_with_projects(session)
    ds = await _seed_deal_share(session, org, deal)
    # Upload a file through the deal guest route, then download it back.
    up = await client.post(
        f"/d/{ds.slug}/p/{p1.id}/upload",
        files={"files": ("note.pdf", b"%PDF deal", "application/pdf")},
    )
    assert up.status_code == 200, up.text
    assert "note.pdf" in up.text

    doc = (
        await session.execute(
            select(Document).where(
                Document.project_id == p1.id, Document.filename == "note.pdf"
            )
        )
    ).scalar_one()
    dl = await client.get(f"/d/{ds.slug}/p/{p1.id}/documents/{doc.id}/download")
    assert dl.status_code == 200
    assert dl.content == b"%PDF deal"
