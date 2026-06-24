"""Integration tests for the document-room router (Phase 1).

Exercises upload (valid + rejected type/empty), list/render, single download,
inline view, bulk archive/recover/delete, zip download, org-scope isolation,
and the feature flag.
"""

from __future__ import annotations

import io
import uuid
import zipfile

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, Scenario, ProjectType
from app.models.document import Document, DocumentStatus
from app.models.opportunity import Opportunity
from app.models.project import Project


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _doc_storage_tmp(tmp_path, monkeypatch):
    """Write uploaded bytes under a tmp dir, not the production volume path."""
    monkeypatch.setattr(
        "app.config.settings.document_storage_path", str(tmp_path), raising=True
    )


async def _auth(client: AsyncClient, user_id) -> None:
    from tests.conftest import set_client_auth

    set_client_auth(client, user_id)


async def _seed_project(session: AsyncSession, *, deal_name: str = "Doc Deal"):
    """Seed org/user/opportunity/deal/scenario/project; return (project, user, org)."""
    from tests.conftest import seed_opportunity, seed_org

    org, user = await seed_org(session)
    opp: Opportunity = await seed_opportunity(session, org, user)
    deal = Deal(id=uuid.uuid4(), org_id=org.id, name=deal_name, created_by_user_id=user.id)
    session.add(deal)
    await session.flush()
    scenario = Scenario(
        id=uuid.uuid4(),
        deal_id=deal.id,
        created_by_user_id=user.id,
        name="Base Case",
        version=1,
        is_active=True,
        project_type=ProjectType.value_add,
    )
    session.add(scenario)
    await session.flush()
    project = Project(
        id=uuid.uuid4(),
        scenario_id=scenario.id,
        opportunity_id=opp.id,
        name="Main Project",
    )
    session.add(project)
    await session.commit()
    return project, user, org


def _upload(name: str, content: bytes, ctype: str = "application/pdf"):
    return {"files": (name, content, ctype)}


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

async def test_upload_creates_document(client: AsyncClient, session: AsyncSession):
    project, user, _org = await _seed_project(session)
    await _auth(client, user.id)

    resp = await client.post(
        f"/ui/projects/{project.id}/documents/upload",
        files=_upload("Rent Roll.pdf", b"%PDF-1.4 data"),
        data={"show": "active"},
    )
    assert resp.status_code == 200, resp.text
    assert "Rent Roll.pdf" in resp.text

    rows = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalars().all()
    assert len(rows) == 1
    doc = rows[0]
    assert doc.org_id == _org.id
    assert doc.size_bytes == len(b"%PDF-1.4 data")
    assert doc.sha256 is not None
    assert doc.status == DocumentStatus.active


async def test_upload_rejects_disallowed_extension(client: AsyncClient, session: AsyncSession):
    project, user, _org = await _seed_project(session)
    await _auth(client, user.id)

    resp = await client.post(
        f"/ui/projects/{project.id}/documents/upload",
        files=_upload("malware.exe", b"MZ", ctype="application/octet-stream"),
        data={"show": "active"},
    )
    assert resp.status_code == 200, resp.text
    assert "not allowed" in resp.text
    rows = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalars().all()
    assert rows == []


async def test_upload_skips_empty_file(client: AsyncClient, session: AsyncSession):
    project, user, _org = await _seed_project(session)
    await _auth(client, user.id)

    resp = await client.post(
        f"/ui/projects/{project.id}/documents/upload",
        files=_upload("blank.pdf", b""),
        data={"show": "active"},
    )
    assert resp.status_code == 200
    count = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalars().all()
    assert count == []


# ---------------------------------------------------------------------------
# Download / view
# ---------------------------------------------------------------------------

async def test_download_returns_bytes(client: AsyncClient, session: AsyncSession):
    project, user, _org = await _seed_project(session)
    await _auth(client, user.id)
    await client.post(
        f"/ui/projects/{project.id}/documents/upload",
        files=_upload("Lease.pdf", b"PDFBYTES"),
        data={"show": "active"},
    )
    doc = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalar_one()

    resp = await client.get(f"/ui/documents/{doc.id}/download")
    assert resp.status_code == 200
    assert resp.content == b"PDFBYTES"
    assert "attachment" in resp.headers["content-disposition"]


async def test_view_pdf_is_inline(client: AsyncClient, session: AsyncSession):
    project, user, _org = await _seed_project(session)
    await _auth(client, user.id)
    await client.post(
        f"/ui/projects/{project.id}/documents/upload",
        files=_upload("Plan.pdf", b"%PDF inline"),
        data={"show": "active"},
    )
    doc = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalar_one()

    resp = await client.get(f"/ui/documents/{doc.id}/view")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.headers["content-disposition"].startswith("inline")


# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------

async def _upload_n(client, project_id, names):
    ids = []
    for n in names:
        await client.post(
            f"/ui/projects/{project_id}/documents/upload",
            files=_upload(n, b"data-" + n.encode()),
            data={"show": "active"},
        )
    return ids


async def test_bulk_archive_then_recover(client: AsyncClient, session: AsyncSession):
    project, user, _org = await _seed_project(session)
    await _auth(client, user.id)
    await _upload_n(client, project.id, ["a.pdf", "b.pdf"])
    docs = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalars().all()
    ids = [str(d.id) for d in docs]

    # Archive both
    resp = await client.post(
        f"/ui/projects/{project.id}/documents/bulk",
        data={"action": "archive", "ids": ids, "show": "active"},
    )
    assert resp.status_code == 200
    for d in docs:
        await session.refresh(d)
        assert d.status == DocumentStatus.archived
        assert d.archived_at is not None

    # Recover one
    resp = await client.post(
        f"/ui/projects/{project.id}/documents/bulk",
        data={"action": "recover", "ids": [ids[0]], "show": "archived"},
    )
    assert resp.status_code == 200
    await session.refresh(docs[0])
    assert docs[0].status == DocumentStatus.active


async def test_bulk_delete_removes_rows(client: AsyncClient, session: AsyncSession):
    project, user, _org = await _seed_project(session)
    await _auth(client, user.id)
    await _upload_n(client, project.id, ["x.pdf", "y.pdf"])
    docs = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalars().all()
    ids = [str(d.id) for d in docs]

    resp = await client.post(
        f"/ui/projects/{project.id}/documents/bulk",
        data={"action": "delete", "ids": ids, "show": "active"},
    )
    assert resp.status_code == 200
    remaining = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalars().all()
    assert remaining == []


async def test_zip_download_contains_selected(client: AsyncClient, session: AsyncSession):
    project, user, _org = await _seed_project(session)
    await _auth(client, user.id)
    await _upload_n(client, project.id, ["one.pdf", "two.pdf"])
    docs = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalars().all()
    ids = [str(d.id) for d in docs]

    resp = await client.get(
        f"/ui/projects/{project.id}/documents/zip", params={"ids": ids}
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert sorted(zf.namelist()) == ["one.pdf", "two.pdf"]


# ---------------------------------------------------------------------------
# Org isolation + feature flag
# ---------------------------------------------------------------------------

async def test_cross_org_access_is_404(client: AsyncClient, session: AsyncSession):
    project, owner, _org = await _seed_project(session)
    await _auth(client, owner.id)
    await client.post(
        f"/ui/projects/{project.id}/documents/upload",
        files=_upload("secret.pdf", b"private"),
        data={"show": "active"},
    )
    doc = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalar_one()

    # A user from a different org
    from tests.conftest import seed_org

    _other_org, intruder = await seed_org(session)
    await session.commit()
    await _auth(client, intruder.id)

    assert (await client.get(f"/projects/{project.id}/documents")).status_code == 404
    assert (await client.get(f"/ui/documents/{doc.id}/download")).status_code == 404


async def test_feature_flag_off_returns_404(client: AsyncClient, session: AsyncSession, monkeypatch):
    project, user, _org = await _seed_project(session)
    await _auth(client, user.id)
    monkeypatch.setattr("app.config.settings.documents_module_enabled", False, raising=True)

    resp = await client.get(f"/projects/{project.id}/documents")
    assert resp.status_code == 404


async def test_page_renders_for_owner(client: AsyncClient, session: AsyncSession):
    project, user, _org = await _seed_project(session)
    await _auth(client, user.id)
    resp = await client.get(f"/projects/{project.id}/documents")
    assert resp.status_code == 200, resp.text
    assert "Documents" in resp.text
    assert "Main Project" in resp.text
