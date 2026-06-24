"""Integration tests for the document-room task view (Phase 2)."""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, Scenario, ProjectType
from app.models.document import Document, DocumentTask, DocumentTaskStatus
from app.models.milestone import Milestone, MilestoneType
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
    deal = Deal(id=uuid.uuid4(), org_id=org.id, name="Task Deal", created_by_user_id=user.id)
    session.add(deal)
    await session.flush()
    scenario = Scenario(
        id=uuid.uuid4(), deal_id=deal.id, created_by_user_id=user.id,
        name="Base", version=1, is_active=True, project_type=ProjectType.value_add,
    )
    session.add(scenario)
    await session.flush()
    project = Project(id=uuid.uuid4(), scenario_id=scenario.id, opportunity_id=opp.id, name="P1")
    session.add(project)
    await session.commit()
    return project, user, org


async def test_create_and_list_tasks(client: AsyncClient, session: AsyncSession):
    project, user, _org = await _seed_project(session)
    await _auth(client, user.id)

    resp = await client.post(
        f"/ui/projects/{project.id}/tasks",
        data={"title": "Tenant Leases", "status": "all"},
    )
    assert resp.status_code == 200, resp.text
    assert "Tenant Leases" in resp.text

    rows = (
        await session.execute(select(DocumentTask).where(DocumentTask.project_id == project.id))
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].status == DocumentTaskStatus.pending


async def test_status_filter(client: AsyncClient, session: AsyncSession):
    project, user, org = await _seed_project(session)
    await _auth(client, user.id)
    session.add_all([
        DocumentTask(org_id=org.id, project_id=project.id, title="A", status=DocumentTaskStatus.pending),
        DocumentTask(org_id=org.id, project_id=project.id, title="B", status=DocumentTaskStatus.complete),
    ])
    await session.commit()

    resp = await client.get(f"/ui/projects/{project.id}/tasks", params={"status": "complete"})
    assert resp.status_code == 200
    assert "B" in resp.text
    assert "A" not in resp.text


async def test_update_status_and_notes(client: AsyncClient, session: AsyncSession):
    project, user, org = await _seed_project(session)
    await _auth(client, user.id)
    task = DocumentTask(org_id=org.id, project_id=project.id, title="Survey")
    session.add(task)
    await session.commit()

    resp = await client.post(
        f"/ui/tasks/{task.id}",
        data={"status": "in_progress", "notes": "Ordered from vendor", "due_kind": "date", "due_date": "2026-09-01"},
    )
    assert resp.status_code == 200
    await session.refresh(task)
    assert task.status == DocumentTaskStatus.in_progress
    assert task.notes == "Ordered from vendor"
    assert task.due_date == date(2026, 9, 1)


async def test_relative_due_via_milestone(client: AsyncClient, session: AsyncSession):
    project, user, org = await _seed_project(session)
    await _auth(client, user.id)
    ms = Milestone(
        id=uuid.uuid4(), project_id=project.id, milestone_type=MilestoneType.close,
        target_date=date(2026, 1, 1), duration_days=10, sequence_order=1,
    )
    task = DocumentTask(org_id=org.id, project_id=project.id, title="Closing docs")
    session.add_all([ms, task])
    await session.commit()

    resp = await client.post(
        f"/ui/tasks/{task.id}",
        data={"due_kind": "milestone", "due_milestone_id": str(ms.id), "due_offset_days": "3"},
    )
    assert resp.status_code == 200
    await session.refresh(task)
    assert task.due_milestone_id == ms.id
    assert task.due_offset_days == 3
    # Rendered card shows resolved date: 2026-01-01 + 10d duration + 3d offset = 2026-01-14
    assert "Jan 14, 2026" in resp.text


async def test_upload_to_task_assigns_task_id(client: AsyncClient, session: AsyncSession):
    project, user, org = await _seed_project(session)
    await _auth(client, user.id)
    task = DocumentTask(org_id=org.id, project_id=project.id, title="Leases")
    session.add(task)
    await session.commit()

    resp = await client.post(
        f"/ui/tasks/{task.id}/upload",
        files={"files": ("lease1.pdf", b"%PDF lease", "application/pdf")},
    )
    assert resp.status_code == 200
    assert "lease1.pdf" in resp.text
    doc = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalar_one()
    assert doc.task_id == task.id


async def test_task_zip_has_notes_and_files(client: AsyncClient, session: AsyncSession):
    project, user, org = await _seed_project(session)
    await _auth(client, user.id)
    task = DocumentTask(org_id=org.id, project_id=project.id, title="Diligence", notes="grab all")
    session.add(task)
    await session.commit()
    await client.post(
        f"/ui/tasks/{task.id}/upload",
        files={"files": ("a.pdf", b"AAA", "application/pdf")},
    )

    resp = await client.get(f"/ui/tasks/{task.id}/download")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert "notes.txt" in names
    assert "a.pdf" in names
    assert b"grab all" in zf.read("notes.txt")


async def test_delete_task_detaches_documents(client: AsyncClient, session: AsyncSession):
    project, user, org = await _seed_project(session)
    await _auth(client, user.id)
    task = DocumentTask(org_id=org.id, project_id=project.id, title="X")
    session.add(task)
    await session.commit()
    await client.post(
        f"/ui/tasks/{task.id}/upload",
        files={"files": ("k.pdf", b"K", "application/pdf")},
    )

    resp = await client.post(f"/ui/tasks/{task.id}/delete", data={"status": "all"})
    assert resp.status_code == 200
    # Task gone, document kept but detached.
    assert (await session.get(DocumentTask, task.id)) is None
    doc = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalar_one()
    assert doc.task_id is None


async def test_cross_org_task_access_404(client: AsyncClient, session: AsyncSession):
    project, owner, _org = await _seed_project(session)
    await _auth(client, owner.id)
    task = DocumentTask(org_id=_org.id, project_id=project.id, title="secret")
    session.add(task)
    await session.commit()

    from tests.conftest import seed_org

    _other, intruder = await seed_org(session)
    await session.commit()
    await _auth(client, intruder.id)
    assert (await client.get(f"/ui/tasks/{task.id}/edit")).status_code == 404
    assert (await client.get(f"/ui/tasks/{task.id}/download")).status_code == 404
