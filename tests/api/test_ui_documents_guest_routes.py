"""Integration tests for the guest (link-holder) document-room routes not
covered by test_document_shares.py / test_deal_shares.py / test_document_filters.py.

Project share (base ``/share/{token}``):
    GET /documents/{id}/view   GET /zip   GET /tasks   GET /tasks/{id}/download
    GET ?view=tasks
Deal share (base ``/d/{slug}``):
    GET /zip   GET /p/{pid}/rows   GET /p/{pid}/documents/{id}/view
    GET /p/{pid}/zip   GET /p/{pid}/tasks   POST /p/{pid}/tasks/{id}/upload
    GET /p/{pid}/tasks/{id}/download

Guests hold no session, so the failures that matter are leaks: an archived
document, another project's document or task, a revoked link. Each must 404.
"""

from __future__ import annotations

import io
import uuid
import zipfile

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui_documents import _generate_share_slug
from app.models.deal import Deal, ProjectType, Scenario
from app.models.document import (
    DealShare,
    Document,
    DocumentShare,
    DocumentStatus,
    DocumentTask,
)
from app.models.project import Project
from app.storage.documents import save_document

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


async def _seed(session: AsyncSession):
    """Org, deal 'Harbor' with projects North + South, a task per project."""
    from tests.conftest import seed_org

    org, user = await seed_org(session)
    deal = Deal(id=uuid.uuid4(), org_id=org.id, name="Harbor", created_by_user_id=user.id)
    session.add(deal)
    await session.flush()
    north = await _project(session, deal, "North")
    south = await _project(session, deal, "South")
    n_task = DocumentTask(org_id=org.id, project_id=north.id, title="Leases", notes="<b>ask</b>")
    s_task = DocumentTask(org_id=org.id, project_id=south.id, title="Survey")
    session.add_all([n_task, s_task])
    await session.commit()
    return org, deal, north, south, n_task, s_task


def _doc(org, project, task, filename, body, *, status=DocumentStatus.active) -> Document:
    key = f"{org.id}/{project.id}/{uuid.uuid4().hex}{filename[filename.rfind('.'):]}"
    save_document(key, body)
    return Document(
        org_id=org.id, project_id=project.id, task_id=task.id if task else None,
        filename=filename, name_label=filename.rsplit(".", 1)[0], size_bytes=len(body),
        sha256="x", storage_key=key, status=status,
    )


async def _project_share(session, org, project, *, revoked=False) -> DocumentShare:
    share = DocumentShare(
        org_id=org.id, project_id=project.id, slug=_generate_share_slug(), revoked=revoked
    )
    session.add(share)
    await session.commit()
    return share


async def _deal_share(session, org, deal) -> DealShare:
    ds = DealShare(org_id=org.id, deal_id=deal.id, slug=_generate_share_slug())
    session.add(ds)
    await session.commit()
    return ds


def _names(resp) -> list[str]:
    return zipfile.ZipFile(io.BytesIO(resp.content)).namelist()


# ---------------------------------------------------------------------------
# Project share
# ---------------------------------------------------------------------------

async def test_share_view_inline_and_leaks_404(client: AsyncClient, session: AsyncSession):
    org, _deal, north, south, n_task, s_task = await _seed(session)
    pdf = _doc(org, north, n_task, "plan.pdf", b"%PDF plan")
    docx = _doc(org, north, n_task, "memo.docx", b"PK memo")
    old = _doc(org, north, n_task, "old.pdf", b"%PDF old", status=DocumentStatus.archived)
    other = _doc(org, south, s_task, "south.pdf", b"%PDF south")
    session.add_all([pdf, docx, old, other])
    share = await _project_share(session, org, north)
    base = f"/share/{share.slug}"

    ok = await client.get(f"{base}/documents/{pdf.id}/view")
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("application/pdf")
    assert ok.headers["content-disposition"].startswith("inline")
    assert ok.content == b"%PDF plan"

    # No native preview and no converted one -> 404, not a raw download.
    assert (await client.get(f"{base}/documents/{docx.id}/view")).status_code == 404
    # Archived and other-project documents are invisible to the link.
    assert (await client.get(f"{base}/documents/{old.id}/view")).status_code == 404
    assert (await client.get(f"{base}/documents/{other.id}/view")).status_code == 404
    assert (await client.get(f"{base}/documents/{uuid.uuid4()}/view")).status_code == 404


async def test_share_zip_has_active_docs_and_notes_only(
    client: AsyncClient, session: AsyncSession
):
    org, _deal, north, south, n_task, s_task = await _seed(session)
    session.add_all([
        _doc(org, north, n_task, "lease.pdf", b"L"),
        _doc(org, north, n_task, "old.pdf", b"O", status=DocumentStatus.archived),
        _doc(org, south, s_task, "south.pdf", b"S"),
    ])
    share = await _project_share(session, org, north)

    resp = await client.get(f"/share/{share.slug}/zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    names = _names(resp)
    assert "Leases/notes.txt" in names
    files = [n for n in names if not n.endswith("notes.txt")]
    assert len(files) == 1 and files[0].startswith("Leases/North - Leases - lease - Draft")


async def test_share_tasks_list_and_page_tasks_view(client: AsyncClient, session: AsyncSession):
    org, _deal, north, _south, _n_task, _s_task = await _seed(session)
    share = await _project_share(session, org, north)

    rows = await client.get(f"/share/{share.slug}/tasks")
    assert rows.status_code == 200
    assert "Leases" in rows.text and "Survey" not in rows.text

    page = await client.get(f"/share/{share.slug}", params={"view": "tasks"})
    assert page.status_code == 200
    assert "Leases" in page.text and "Survey" not in page.text


async def test_share_task_zip_and_foreign_task_404(client: AsyncClient, session: AsyncSession):
    org, _deal, north, _south, n_task, s_task = await _seed(session)
    session.add(_doc(org, north, n_task, "lease.pdf", b"L"))
    share = await _project_share(session, org, north)

    resp = await client.get(f"/share/{share.slug}/tasks/{n_task.id}/download")
    assert resp.status_code == 200
    assert 'filename="Leases.zip"' in resp.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert b"Task: Leases" in zf.read("notes.txt")
    assert b"ask" in zf.read("notes.txt")
    assert len(zf.namelist()) == 2

    # A task of a sibling project in the same org is not reachable through this link.
    assert (
        await client.get(f"/share/{share.slug}/tasks/{s_task.id}/download")
    ).status_code == 404
    assert (
        await client.get(f"/share/{share.slug}/tasks/{uuid.uuid4()}/download")
    ).status_code == 404


async def test_revoked_share_closes_every_guest_route(client: AsyncClient, session: AsyncSession):
    org, _deal, north, _south, n_task, _s_task = await _seed(session)
    doc = _doc(org, north, n_task, "plan.pdf", b"P")
    session.add(doc)
    share = await _project_share(session, org, north, revoked=True)
    base = f"/share/{share.slug}"
    for path in (
        "/zip", "/tasks", "/rows", f"/documents/{doc.id}/view",
        f"/tasks/{n_task.id}/download",
    ):
        assert (await client.get(base + path)).status_code == 404, path
    up = await client.post(
        f"{base}/tasks/{n_task.id}/upload", files={"files": ("x.pdf", b"X", "application/pdf")}
    )
    assert up.status_code == 404


# ---------------------------------------------------------------------------
# Deal share
# ---------------------------------------------------------------------------

async def test_deal_share_zip_folders_projects(client: AsyncClient, session: AsyncSession):
    org, deal, north, south, n_task, s_task = await _seed(session)
    session.add_all([
        _doc(org, north, n_task, "lease.pdf", b"L"),
        _doc(org, south, s_task, "survey.pdf", b"S"),
    ])
    ds = await _deal_share(session, org, deal)

    resp = await client.get(f"/d/{ds.slug}/zip")
    assert resp.status_code == 200
    assert 'filename="Harbor.zip"' in resp.headers["content-disposition"]
    names = _names(resp)
    assert any(n.startswith("North/Leases/North - Leases - lease") for n in names), names
    assert any(n.startswith("South/Survey/South - Survey - survey") for n in names), names

    assert (await client.get("/d/NoSuchSlug1/zip")).status_code == 404


async def test_deal_share_project_rows_view_zip(client: AsyncClient, session: AsyncSession):
    org, deal, north, south, n_task, s_task = await _seed(session)
    lease = _doc(org, north, n_task, "lease.pdf", b"%PDF L")
    survey = _doc(org, south, s_task, "survey.pdf", b"%PDF S")
    session.add_all([lease, survey])
    ds = await _deal_share(session, org, deal)
    base = f"/d/{ds.slug}/p/{north.id}"

    rows = await client.get(f"{base}/rows")
    assert rows.status_code == 200
    assert "lease" in rows.text and "survey" not in rows.text

    view = await client.get(f"{base}/documents/{lease.id}/view")
    assert view.status_code == 200 and view.content == b"%PDF L"
    # A document of the sibling project is not reachable under North's base.
    assert (await client.get(f"{base}/documents/{survey.id}/view")).status_code == 404

    z = await client.get(f"{base}/zip")
    assert z.status_code == 200
    files = [n for n in _names(z) if not n.endswith("notes.txt")]
    assert files and all(n.startswith("Leases/") for n in files)


async def test_deal_share_foreign_project_404(client: AsyncClient, session: AsyncSession):
    org, deal, _north, _south, _n, _s = await _seed(session)
    ds = await _deal_share(session, org, deal)
    # A project under a different deal (different org) must not open.
    org2, deal2, other, _s2, _n2, _s2t = await _seed(session)
    for path in ("/rows", "/zip", "/tasks"):
        assert (await client.get(f"/d/{ds.slug}/p/{other.id}{path}")).status_code == 404, path
    assert (await client.get(f"/d/{ds.slug}/p/{uuid.uuid4()}/rows")).status_code == 404


async def test_deal_share_tasks_upload_download(client: AsyncClient, session: AsyncSession):
    org, deal, north, _south, n_task, s_task = await _seed(session)
    ds = await _deal_share(session, org, deal)
    base = f"/d/{ds.slug}/p/{north.id}"

    tasks = await client.get(f"{base}/tasks")
    assert tasks.status_code == 200
    assert "Leases" in tasks.text and "Survey" not in tasks.text

    up = await client.post(
        f"{base}/tasks/{n_task.id}/upload",
        files={"files": ("estoppel.pdf", b"%PDF E", "application/pdf")},
        data={"name_label": "Estoppel", "stage": "final"},
    )
    assert up.status_code == 200, up.text
    assert "North - Leases - Estoppel - Final" in up.text
    doc = (
        await session.execute(select(Document).where(Document.project_id == north.id))
    ).scalar_one()
    assert doc.task_id == n_task.id
    assert doc.uploaded_by_user_id is None  # guests are anonymous

    dl = await client.get(f"{base}/tasks/{n_task.id}/download")
    assert dl.status_code == 200
    assert any("Estoppel" in n for n in _names(dl))

    # South's task through North's base: refused, and nothing is written.
    bad_up = await client.post(
        f"{base}/tasks/{s_task.id}/upload",
        files={"files": ("x.pdf", b"X", "application/pdf")},
    )
    assert bad_up.status_code == 404
    assert (await client.get(f"{base}/tasks/{s_task.id}/download")).status_code == 404
    count = (
        await session.execute(select(Document).where(Document.task_id == s_task.id))
    ).scalars().all()
    assert count == []


async def test_deal_share_task_upload_rejects_bad_file(client: AsyncClient, session: AsyncSession):
    """A refused file used to vanish without a word: the task card re-rendered
    as if the upload had worked. The guest must be told why."""
    org, deal, north, _south, n_task, _s_task = await _seed(session)
    ds = await _deal_share(session, org, deal)
    resp = await client.post(
        f"/d/{ds.slug}/p/{north.id}/tasks/{n_task.id}/upload",
        files={"files": ("run.exe", b"MZ", "application/octet-stream")},
    )
    assert resp.status_code == 200
    assert "run.exe: file type not allowed" in resp.text
    rows = (
        await session.execute(select(Document).where(Document.project_id == north.id))
    ).scalars().all()
    assert rows == []
