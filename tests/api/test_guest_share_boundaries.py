"""Guest share links: the edges of the grant.

Routes covered (anonymous, no session):
    GET /d/{slug}/p/{project_id}/documents/{document_id}/view
    GET /d/{slug}/p/{project_id}/tasks
    GET /d/{slug}/p/{project_id}/tasks/{task_id}/download
    GET /d/{slug}/p/{project_id}/zip
    GET /share/{token}/documents/{document_id}/view

test_ui_documents_guest_routes.py covers the happy paths and a sibling
project's document. This file swaps every id in the URL for one outside the
grant (another org's project, document and task; a project of another deal in
the SAME org) and checks the two ways a link dies: revoked and aged past
``doc_share_token_max_age_seconds``. Every refusal must be a 404 that carries
none of the foreign content.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui_documents import _generate_share_slug
from app.models.deal import Deal, ProjectType, Scenario
from app.models.document import (
    DealShare,
    Document,
    DocumentPreviewStatus,
    DocumentShare,
    DocumentStatus,
    DocumentTask,
)
from app.models.project import Project
from app.storage.documents import save_document
from tests.conftest import seed_org

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _doc_storage_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.document_storage_path", str(tmp_path), raising=True
    )


async def _project(session, deal, name) -> Project:
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


def _doc(org, project, task, filename, body) -> Document:
    key = f"{org.id}/{project.id}/{uuid.uuid4().hex}{filename[filename.rfind('.'):]}"
    save_document(key, body)
    return Document(
        org_id=org.id, project_id=project.id, task_id=task.id if task else None,
        filename=filename, name_label=filename.rsplit(".", 1)[0], size_bytes=len(body),
        sha256="x", storage_key=key, status=DocumentStatus.active,
    )


async def _world(session: AsyncSession, deal_name: str):
    """One org, one deal with one project, one task and one PDF in that task."""
    org, user = await seed_org(session)
    deal = Deal(id=uuid.uuid4(), org_id=org.id, name=deal_name, created_by_user_id=user.id)
    session.add(deal)
    await session.flush()
    project = await _project(session, deal, f"{deal_name} P")
    task = DocumentTask(org_id=org.id, project_id=project.id, title=f"{deal_name} Task")
    session.add(task)
    await session.flush()
    doc = _doc(org, project, task, f"{deal_name.lower()}.pdf", f"%PDF {deal_name}".encode())
    session.add(doc)
    await session.commit()
    return org, user, deal, project, task, doc


async def _deal_share(session, org, deal, *, revoked=False, created_at=None) -> DealShare:
    ds = DealShare(org_id=org.id, deal_id=deal.id, slug=_generate_share_slug(), revoked=revoked)
    if created_at is not None:
        ds.created_at = created_at
    session.add(ds)
    await session.commit()
    return ds


async def _project_share(session, org, project, *, revoked=False, created_at=None):
    share = DocumentShare(
        org_id=org.id, project_id=project.id, slug=_generate_share_slug(), revoked=revoked
    )
    if created_at is not None:
        share.created_at = created_at
    session.add(share)
    await session.commit()
    return share


def _deal_paths(project, task, doc) -> list[str]:
    return [
        f"/p/{project.id}/documents/{doc.id}/view",
        f"/p/{project.id}/tasks",
        f"/p/{project.id}/tasks/{task.id}/download",
        f"/p/{project.id}/zip",
    ]


_STALE = datetime.now(timezone.utc) - timedelta(days=400)


# ---------------------------------------------------------------------------
# Deal share: foreign ids
# ---------------------------------------------------------------------------

async def test_deal_link_cannot_reach_another_orgs_project(
    client: AsyncClient, session: AsyncSession
):
    org_a, _u, deal_a, _pa, _ta, _da = await _world(session, "Alpha")
    _ob, _ub, _deal_b, proj_b, task_b, doc_b = await _world(session, "Bravo")
    ds = await _deal_share(session, org_a, deal_a)

    for path in _deal_paths(proj_b, task_b, doc_b):
        resp = await client.get(f"/d/{ds.slug}{path}")
        assert resp.status_code == 404, path
        assert b"Bravo" not in resp.content, path


async def test_deal_link_cannot_splice_foreign_ids_under_its_own_project(
    client: AsyncClient, session: AsyncSession
):
    """Own project in the URL, another org's document / task id after it."""
    org_a, _u, deal_a, proj_a, task_a, doc_a = await _world(session, "Alpha")
    _ob, _ub, _deal_b, _pb, task_b, doc_b = await _world(session, "Bravo")
    ds = await _deal_share(session, org_a, deal_a)
    base = f"/d/{ds.slug}/p/{proj_a.id}"

    view = await client.get(f"{base}/documents/{doc_b.id}/view")
    assert view.status_code == 404 and b"Bravo" not in view.content
    dl = await client.get(f"{base}/tasks/{task_b.id}/download")
    assert dl.status_code == 404 and b"Bravo" not in dl.content

    # The link still serves its own content.
    own = await client.get(f"{base}/documents/{doc_a.id}/view")
    assert own.status_code == 200 and own.content == b"%PDF Alpha"
    own_zip = await client.get(f"{base}/tasks/{task_a.id}/download")
    assert own_zip.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(own_zip.content)).namelist()
    assert "notes.txt" in names and any("alpha" in n for n in names)


async def test_deal_link_cannot_reach_another_deal_in_the_same_org(
    client: AsyncClient, session: AsyncSession
):
    """Same org, two deals: sharing one deal must not open the other."""
    org, user, deal_a, _pa, _ta, _da = await _world(session, "Alpha")
    deal_c = Deal(id=uuid.uuid4(), org_id=org.id, name="Charlie", created_by_user_id=user.id)
    session.add(deal_c)
    await session.flush()
    proj_c = await _project(session, deal_c, "Charlie P")
    task_c = DocumentTask(org_id=org.id, project_id=proj_c.id, title="Charlie Task")
    session.add(task_c)
    await session.flush()
    doc_c = _doc(org, proj_c, task_c, "charlie.pdf", b"%PDF Charlie")
    session.add(doc_c)
    await session.commit()
    ds = await _deal_share(session, org, deal_a)

    for path in _deal_paths(proj_c, task_c, doc_c):
        resp = await client.get(f"/d/{ds.slug}{path}")
        assert resp.status_code == 404, path
        assert b"Charlie" not in resp.content, path


async def test_deal_tasks_rows_list_only_that_project(
    client: AsyncClient, session: AsyncSession
):
    org_a, _u, deal_a, proj_a, _ta, _da = await _world(session, "Alpha")
    await _world(session, "Bravo")
    ds = await _deal_share(session, org_a, deal_a)

    resp = await client.get(f"/d/{ds.slug}/p/{proj_a.id}/tasks")
    assert resp.status_code == 200
    assert "Alpha Task" in resp.text
    assert "Bravo Task" not in resp.text


# ---------------------------------------------------------------------------
# Deal share: dead links
# ---------------------------------------------------------------------------

async def test_revoked_deal_link_closes_project_routes(
    client: AsyncClient, session: AsyncSession
):
    org, _u, deal, proj, task, doc = await _world(session, "Alpha")
    ds = await _deal_share(session, org, deal, revoked=True)
    for path in _deal_paths(proj, task, doc):
        resp = await client.get(f"/d/{ds.slug}{path}")
        assert resp.status_code == 404, path
        assert b"%PDF Alpha" not in resp.content


async def test_expired_deal_link_closes_project_routes(
    client: AsyncClient, session: AsyncSession
):
    org, _u, deal, proj, task, doc = await _world(session, "Alpha")
    ds = await _deal_share(session, org, deal, created_at=_STALE)
    for path in _deal_paths(proj, task, doc):
        assert (await client.get(f"/d/{ds.slug}{path}")).status_code == 404, path

    # A fresh link to the same deal still opens: the age check is per link.
    fresh = await _deal_share(session, org, deal)
    ok = await client.get(f"/d/{fresh.slug}/p/{proj.id}/documents/{doc.id}/view")
    assert ok.status_code == 200 and ok.content == b"%PDF Alpha"


# ---------------------------------------------------------------------------
# Project share view
# ---------------------------------------------------------------------------

async def test_project_link_view_refuses_foreign_org_document(
    client: AsyncClient, session: AsyncSession
):
    org_a, _u, _deal_a, proj_a, _ta, doc_a = await _world(session, "Alpha")
    _ob, _ub, _deal_b, _pb, _tb, doc_b = await _world(session, "Bravo")
    share = await _project_share(session, org_a, proj_a)

    foreign = await client.get(f"/share/{share.slug}/documents/{doc_b.id}/view")
    assert foreign.status_code == 404 and b"Bravo" not in foreign.content
    own = await client.get(f"/share/{share.slug}/documents/{doc_a.id}/view")
    assert own.status_code == 200 and own.content == b"%PDF Alpha"


async def test_expired_project_link_view_404(client: AsyncClient, session: AsyncSession):
    org, _u, _deal, proj, _t, doc = await _world(session, "Alpha")
    share = await _project_share(session, org, proj, created_at=_STALE)
    resp = await client.get(f"/share/{share.slug}/documents/{doc.id}/view")
    assert resp.status_code == 404
    assert b"%PDF Alpha" not in resp.content


async def test_project_link_view_serves_converted_preview(
    client: AsyncClient, session: AsyncSession
):
    """An Office file with a ready preview is shown as the converted PDF,
    inline, never as the raw .docx bytes."""
    org, _u, _deal, proj, task, _doc_pdf = await _world(session, "Alpha")
    docx = _doc(org, proj, task, "memo.docx", b"PK raw docx")
    preview_key = f"{org.id}/{proj.id}/preview-{uuid.uuid4().hex}.pdf"
    save_document(preview_key, b"%PDF converted memo")
    docx.preview_status = DocumentPreviewStatus.ready
    docx.preview_key = preview_key
    session.add(docx)
    share = await _project_share(session, org, proj)

    resp = await client.get(f"/share/{share.slug}/documents/{docx.id}/view")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.headers["content-disposition"].startswith("inline")
    assert resp.content == b"%PDF converted memo"
