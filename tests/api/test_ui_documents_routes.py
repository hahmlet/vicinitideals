"""Integration tests for the document-room owner routes not covered elsewhere.

test_documents.py / test_document_tasks.py / test_document_shares.py cover the
upload, archive/recover/delete, zip-by-ids, task create/list/update/upload/zip/
delete and project-share create/revoke paths. This file fills in the rest:

    GET  /ui/projects/{id}/documents/rows     POST /ui/documents/{id}/stage
    POST /ui/documents/{id}/move              GET  /ui/documents/{id}/view (office, preview)
    GET  /ui/projects/{id}/documents/zip (bad input)
    GET  /ui/deals/{id}/documents/zip         POST /ui/projects/{id}/documents/bulk (move, tasks view)
    GET  /ui/tasks/{id}/edit                  POST /ui/tasks/{id}/notes
    POST /ui/tasks/{id} (cross-org)           POST /ui/tasks/{id}/upload (cross-org)
    GET  /ui/projects/{id}/shares             POST /ui/shares/{id}/revoke (guards)
    GET/POST /ui/deals/{id}/deal-shares       POST /ui/deal-shares/{id}/revoke

Every route gets its happy path plus the obvious failure (unknown id -> 404,
another org -> 404, bad input -> 4xx, never a 500).
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, ProjectType, Scenario
from app.models.document import (
    DealShare,
    Document,
    DocumentPreviewStatus,
    DocumentShare,
    DocumentStage,
    DocumentStatus,
    DocumentTask,
)
from app.models.milestone import Milestone, MilestoneType
from app.models.project import Project

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _doc_storage_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.document_storage_path", str(tmp_path), raising=True
    )


def _auth(client: AsyncClient, user_id) -> None:
    from tests.conftest import set_client_auth

    set_client_auth(client, user_id)


async def _seed(session: AsyncSession, *, deal_name: str = "Room Deal", project_name: str = "Main"):
    """Org + user + deal + scenario + project; returns (org, user, deal, project)."""
    from tests.conftest import seed_opportunity, seed_org

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)
    deal = Deal(id=uuid.uuid4(), org_id=org.id, name=deal_name, created_by_user_id=user.id)
    session.add(deal)
    await session.flush()
    scenario = Scenario(
        id=uuid.uuid4(), deal_id=deal.id, created_by_user_id=user.id,
        name="Base", version=1, is_active=True, project_type=ProjectType.value_add,
    )
    session.add(scenario)
    await session.flush()
    project = Project(
        id=uuid.uuid4(), scenario_id=scenario.id, opportunity_id=opp.id, name=project_name
    )
    session.add(project)
    await session.commit()
    return org, user, deal, project


async def _intruder(session: AsyncSession):
    from tests.conftest import seed_org

    _org, user = await seed_org(session)
    await session.commit()
    return user


async def _upload(client: AsyncClient, project_id, name="Lease.pdf", body=b"%PDF body", **data):
    resp = await client.post(
        f"/ui/projects/{project_id}/documents/upload",
        files={"files": (name, body, "application/octet-stream")},
        data={"show": "active", **data},
    )
    assert resp.status_code == 200, resp.text
    return resp


async def _only_doc(session: AsyncSession, project_id) -> Document:
    return (
        await session.execute(select(Document).where(Document.project_id == project_id))
    ).scalar_one()


# ---------------------------------------------------------------------------
# Rows partial
# ---------------------------------------------------------------------------

async def test_rows_partial_filters_by_tab(client: AsyncClient, session: AsyncSession):
    _org, user, _deal, project = await _seed(session)
    _auth(client, user.id)
    await _upload(client, project.id, "Keep.pdf")
    await _upload(client, project.id, "Gone.pdf")
    gone = (
        await session.execute(select(Document).where(Document.filename == "Gone.pdf"))
    ).scalar_one()
    await client.post(
        f"/ui/projects/{project.id}/documents/bulk",
        data={"action": "archive", "ids": [str(gone.id)]},
    )

    active = await client.get(f"/ui/projects/{project.id}/documents/rows")
    assert active.status_code == 200
    assert "Keep" in active.text and "Gone" not in active.text

    archived = await client.get(
        f"/ui/projects/{project.id}/documents/rows", params={"show": "archived"}
    )
    assert archived.status_code == 200
    assert "Gone" in archived.text and "Keep" not in archived.text


async def test_rows_partial_unknown_and_foreign_project_404(
    client: AsyncClient, session: AsyncSession
):
    _org, _user, _deal, project = await _seed(session)
    intruder = await _intruder(session)
    _auth(client, intruder.id)
    assert (await client.get(f"/ui/projects/{uuid.uuid4()}/documents/rows")).status_code == 404
    assert (await client.get(f"/ui/projects/{project.id}/documents/rows")).status_code == 404


# ---------------------------------------------------------------------------
# Stage + move
# ---------------------------------------------------------------------------

async def test_stage_toggle_renames_to_final(client: AsyncClient, session: AsyncSession):
    _org, user, _deal, project = await _seed(session, project_name="Tower")
    _auth(client, user.id)
    await _upload(client, project.id, "Survey.pdf")
    doc = await _only_doc(session, project.id)
    assert doc.stage == DocumentStage.draft

    resp = await client.post(f"/ui/documents/{doc.id}/stage", data={"stage": "final"})
    assert resp.status_code == 200, resp.text
    assert "Tower - Misc - Survey - Final" in resp.text
    await session.refresh(doc)
    assert doc.stage == DocumentStage.final

    # Anything but "final" flips it back to draft.
    resp = await client.post(f"/ui/documents/{doc.id}/stage", data={"stage": "bogus"})
    assert resp.status_code == 200
    await session.refresh(doc)
    assert doc.stage == DocumentStage.draft


async def test_stage_guards(client: AsyncClient, session: AsyncSession):
    _org, user, _deal, project = await _seed(session)
    _auth(client, user.id)
    await _upload(client, project.id)
    doc = await _only_doc(session, project.id)

    # Missing required field -> 422, not 500.
    assert (await client.post(f"/ui/documents/{doc.id}/stage", data={})).status_code == 422
    assert (
        await client.post(f"/ui/documents/{uuid.uuid4()}/stage", data={"stage": "final"})
    ).status_code == 404

    intruder = await _intruder(session)
    _auth(client, intruder.id)
    assert (
        await client.post(f"/ui/documents/{doc.id}/stage", data={"stage": "final"})
    ).status_code == 404
    await session.refresh(doc)
    assert doc.stage == DocumentStage.draft


async def test_move_to_new_task_and_foreign_task_falls_back(
    client: AsyncClient, session: AsyncSession
):
    org, user, _deal, project = await _seed(session, project_name="Tower")
    _auth(client, user.id)
    await _upload(client, project.id, "Lease.pdf")
    doc = await _only_doc(session, project.id)

    resp = await client.post(
        f"/ui/documents/{doc.id}/move", data={"task_choice": "__new__", "new_task": "Leases"}
    )
    assert resp.status_code == 200, resp.text
    assert "Tower - Leases - Lease - Draft" in resp.text
    await session.refresh(doc)
    task = await session.get(DocumentTask, doc.task_id)
    assert task.title == "Leases"

    # A task that belongs to another project is refused -> the doc lands in Misc.
    _o2, _u2, _d2, other_project = await _seed(session)
    foreign = DocumentTask(org_id=org.id, project_id=other_project.id, title="Foreign")
    session.add(foreign)
    await session.commit()
    resp = await client.post(
        f"/ui/documents/{doc.id}/move", data={"task_choice": str(foreign.id)}
    )
    assert resp.status_code == 200
    await session.refresh(doc)
    assert doc.task_id != foreign.id
    assert (await session.get(DocumentTask, doc.task_id)).title == "Misc."


async def test_move_guards(client: AsyncClient, session: AsyncSession):
    _org, user, _deal, project = await _seed(session)
    _auth(client, user.id)
    await _upload(client, project.id)
    doc = await _only_doc(session, project.id)
    assert (await client.post(f"/ui/documents/{doc.id}/move", data={})).status_code == 422
    assert (
        await client.post(f"/ui/documents/{uuid.uuid4()}/move", data={"task_choice": "__misc__"})
    ).status_code == 404
    intruder = await _intruder(session)
    _auth(client, intruder.id)
    assert (
        await client.post(f"/ui/documents/{doc.id}/move", data={"task_choice": "__misc__"})
    ).status_code == 404


# ---------------------------------------------------------------------------
# View / download edge cases
# ---------------------------------------------------------------------------

async def test_view_office_file_without_preview_offers_download(
    client: AsyncClient, session: AsyncSession
):
    _org, user, _deal, project = await _seed(session)
    _auth(client, user.id)
    await _upload(client, project.id, "Budget.xlsx", b"PK xlsx")
    doc = await _only_doc(session, project.id)
    assert doc.preview_status == DocumentPreviewStatus.pending

    resp = await client.get(f"/ui/documents/{doc.id}/view")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert f"/ui/documents/{doc.id}/download" in resp.text


async def test_view_office_file_with_ready_preview_serves_pdf(
    client: AsyncClient, session: AsyncSession
):
    from app.storage.documents import save_document

    _org, user, _deal, project = await _seed(session)
    _auth(client, user.id)
    await _upload(client, project.id, "Memo.docx", b"PK docx")
    doc = await _only_doc(session, project.id)
    preview_key = f"{doc.org_id}/{doc.project_id}/preview.pdf"
    save_document(preview_key, b"%PDF preview")
    doc.preview_key = preview_key
    doc.preview_status = DocumentPreviewStatus.ready
    await session.commit()

    resp = await client.get(f"/ui/documents/{doc.id}/view")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content == b"%PDF preview"


async def test_view_and_download_unknown_or_foreign_404(
    client: AsyncClient, session: AsyncSession
):
    _org, user, _deal, project = await _seed(session)
    _auth(client, user.id)
    await _upload(client, project.id)
    doc = await _only_doc(session, project.id)
    assert (await client.get(f"/ui/documents/{uuid.uuid4()}/view")).status_code == 404
    assert (await client.get(f"/ui/documents/{uuid.uuid4()}/download")).status_code == 404
    intruder = await _intruder(session)
    _auth(client, intruder.id)
    assert (await client.get(f"/ui/documents/{doc.id}/view")).status_code == 404


# ---------------------------------------------------------------------------
# Zip downloads
# ---------------------------------------------------------------------------

async def test_zip_bad_input(client: AsyncClient, session: AsyncSession):
    _org, user, _deal, project = await _seed(session)
    _auth(client, user.id)
    # No selection -> 400.
    assert (await client.get(f"/ui/projects/{project.id}/documents/zip")).status_code == 400
    # A malformed id -> 422.
    assert (
        await client.get(f"/ui/projects/{project.id}/documents/zip", params={"ids": ["nope"]})
    ).status_code == 422
    # A document of another project is not zipped -> 404 (nothing selected survives).
    _o2, user2, _d2, other = await _seed(session)
    _auth(client, user2.id)
    await _upload(client, other.id)
    other_doc = await _only_doc(session, other.id)
    _auth(client, user.id)
    assert (
        await client.get(
            f"/ui/projects/{project.id}/documents/zip", params={"ids": [str(other_doc.id)]}
        )
    ).status_code == 404


async def test_deal_zip_folders_every_project(client: AsyncClient, session: AsyncSession):
    org, user, deal, project = await _seed(session, deal_name="Harbor", project_name="North")
    # A second project under the same deal (own scenario).
    scenario2 = Scenario(
        id=uuid.uuid4(), deal_id=deal.id, name="Alt", version=1, is_active=False,
        project_type=ProjectType.value_add,
    )
    session.add(scenario2)
    await session.flush()
    south = Project(id=uuid.uuid4(), scenario_id=scenario2.id, name="South")
    session.add(south)
    await session.commit()
    _auth(client, user.id)
    await _upload(client, project.id, "a.pdf", b"A")
    await _upload(client, south.id, "b.pdf", b"B", task_choice="__new__", new_task="Title")

    resp = await client.get(f"/ui/deals/{deal.id}/documents/zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert 'filename="Harbor.zip"' in resp.headers["content-disposition"]
    names = zipfile.ZipFile(io.BytesIO(resp.content)).namelist()
    assert any(n.startswith("North/Misc/") for n in names), names
    assert any(n.startswith("South/Title/") for n in names), names


async def test_deal_zip_unknown_and_foreign_404(client: AsyncClient, session: AsyncSession):
    _org, user, deal, _project = await _seed(session)
    _auth(client, user.id)
    assert (await client.get(f"/ui/deals/{uuid.uuid4()}/documents/zip")).status_code == 404
    intruder = await _intruder(session)
    _auth(client, intruder.id)
    assert (await client.get(f"/ui/deals/{deal.id}/documents/zip")).status_code == 404


# ---------------------------------------------------------------------------
# Bulk: move, tasks view, unknown action, foreign ids
# ---------------------------------------------------------------------------

async def test_bulk_move_into_one_new_task_and_render_tasks(
    client: AsyncClient, session: AsyncSession
):
    _org, user, _deal, project = await _seed(session)
    _auth(client, user.id)
    await _upload(client, project.id, "one.pdf")
    await _upload(client, project.id, "two.pdf")
    docs = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalars().all()

    resp = await client.post(
        f"/ui/projects/{project.id}/documents/bulk",
        data={
            "action": "move", "ids": [str(d.id) for d in docs],
            "task_choice": "__new__", "new_task": "Closing", "view": "tasks",
        },
    )
    assert resp.status_code == 200, resp.text
    assert "Closing" in resp.text  # the task list, not the document panel
    project_id = project.id
    session.expire_all()
    docs = (
        await session.execute(select(Document).where(Document.project_id == project_id))
    ).scalars().all()
    task_ids = {d.task_id for d in docs}
    assert len(task_ids) == 1  # one task, not one per document
    assert (await session.get(DocumentTask, task_ids.pop())).title == "Closing"


async def test_bulk_unknown_action_400_and_foreign_ids_ignored(
    client: AsyncClient, session: AsyncSession
):
    _org, user, _deal, project = await _seed(session)
    _o2, user2, _d2, other = await _seed(session)
    _auth(client, user2.id)
    await _upload(client, other.id, "theirs.pdf")
    theirs = await _only_doc(session, other.id)

    _auth(client, user.id)
    bad = await client.post(
        f"/ui/projects/{project.id}/documents/bulk", data={"action": "shred", "ids": []}
    )
    assert bad.status_code == 400
    missing = await client.post(f"/ui/projects/{project.id}/documents/bulk", data={})
    assert missing.status_code == 422

    # Another org's document id sent through my project's bulk delete: untouched.
    resp = await client.post(
        f"/ui/projects/{project.id}/documents/bulk",
        data={"action": "delete", "ids": [str(theirs.id)]},
    )
    assert resp.status_code == 200
    theirs_id = theirs.id
    session.expire_all()
    assert (await session.get(Document, theirs_id)) is not None


# ---------------------------------------------------------------------------
# Task drawer, notes, milestone guard, cross-org upload
# ---------------------------------------------------------------------------

async def _task(session, org, project, title="Diligence", **kw) -> DocumentTask:
    task = DocumentTask(org_id=org.id, project_id=project.id, title=title, **kw)
    session.add(task)
    await session.commit()
    return task


async def test_task_edit_drawer_renders(client: AsyncClient, session: AsyncSession):
    org, user, _deal, project = await _seed(session)
    session.add(Milestone(
        id=uuid.uuid4(), project_id=project.id, milestone_type=MilestoneType.close,
        target_date=date(2026, 1, 1), duration_days=10, sequence_order=1,
    ))
    task = await _task(session, org, project, "Title Report")
    _auth(client, user.id)

    resp = await client.get(f"/ui/tasks/{task.id}/edit")
    assert resp.status_code == 200, resp.text
    assert "Title Report" in resp.text
    assert "Close" in resp.text  # the milestone picker is populated
    assert (await client.get(f"/ui/tasks/{uuid.uuid4()}/edit")).status_code == 404


async def test_task_notes_are_sanitized(client: AsyncClient, session: AsyncSession):
    org, user, _deal, project = await _seed(session)
    task = await _task(session, org, project)
    _auth(client, user.id)

    resp = await client.post(
        f"/ui/tasks/{task.id}/notes",
        data={"notes_html": '<b onclick="x()">Call lender</b><script>alert(1)</script>'},
    )
    assert resp.status_code == 200, resp.text
    await session.refresh(task)
    assert task.notes == "<strong>Call lender</strong>"
    assert "<script>" not in resp.text

    # Clearing the notes stores NULL, not an empty shell.
    resp = await client.post(f"/ui/tasks/{task.id}/notes", data={"notes_html": "<p><br></p>"})
    assert resp.status_code == 200
    await session.refresh(task)
    assert task.notes is None


async def test_task_notes_unknown_and_foreign_404(client: AsyncClient, session: AsyncSession):
    org, _user, _deal, project = await _seed(session)
    task = await _task(session, org, project)
    intruder = await _intruder(session)
    _auth(client, intruder.id)
    assert (
        await client.post(f"/ui/tasks/{uuid.uuid4()}/notes", data={"notes_html": "x"})
    ).status_code == 404
    assert (
        await client.post(f"/ui/tasks/{task.id}/notes", data={"notes_html": "x"})
    ).status_code == 404
    await session.refresh(task)
    assert task.notes is None


async def test_task_update_and_upload_foreign_404(client: AsyncClient, session: AsyncSession):
    org, _user, _deal, project = await _seed(session)
    task = await _task(session, org, project, "Mine")
    intruder = await _intruder(session)
    _auth(client, intruder.id)
    assert (
        await client.post(f"/ui/tasks/{task.id}", data={"title": "Hijacked"})
    ).status_code == 404
    up = await client.post(
        f"/ui/tasks/{task.id}/upload", files={"files": ("x.pdf", b"X", "application/pdf")}
    )
    assert up.status_code == 404
    await session.refresh(task)
    assert task.title == "Mine"
    rows = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalars().all()
    assert rows == []


# ---------------------------------------------------------------------------
# Project shares: list + revoke guards
# ---------------------------------------------------------------------------

async def test_share_list_hides_revoked(client: AsyncClient, session: AsyncSession):
    from app.api.routers.ui_documents import _generate_share_slug

    org, user, _deal, project = await _seed(session)
    live = DocumentShare(org_id=org.id, project_id=project.id, slug=_generate_share_slug(), label="Bank")
    dead = DocumentShare(
        org_id=org.id, project_id=project.id, slug=_generate_share_slug(), label="Old", revoked=True
    )
    session.add_all([live, dead])
    await session.commit()
    _auth(client, user.id)

    resp = await client.get(f"/ui/projects/{project.id}/shares")
    assert resp.status_code == 200
    assert live.slug in resp.text
    assert dead.slug not in resp.text

    intruder = await _intruder(session)
    _auth(client, intruder.id)
    assert (await client.get(f"/ui/projects/{project.id}/shares")).status_code == 404


async def test_share_revoke_unknown_and_foreign_404(client: AsyncClient, session: AsyncSession):
    from app.api.routers.ui_documents import _generate_share_slug

    org, _user, _deal, project = await _seed(session)
    share = DocumentShare(org_id=org.id, project_id=project.id, slug=_generate_share_slug())
    session.add(share)
    await session.commit()
    intruder = await _intruder(session)
    _auth(client, intruder.id)
    assert (await client.post(f"/ui/shares/{uuid.uuid4()}/revoke")).status_code == 404
    assert (await client.post(f"/ui/shares/{share.id}/revoke")).status_code == 404
    await session.refresh(share)
    assert share.revoked is False


# ---------------------------------------------------------------------------
# Deal shares
# ---------------------------------------------------------------------------

async def test_deal_share_create_list_revoke(client: AsyncClient, session: AsyncSession):
    _org, user, deal, _project = await _seed(session)
    _auth(client, user.id)

    empty = await client.get(f"/ui/deals/{deal.id}/deal-shares")
    assert empty.status_code == 200

    created = await client.post(f"/ui/deals/{deal.id}/deal-shares", data={"label": "Lender"})
    assert created.status_code == 200, created.text
    share = (
        await session.execute(select(DealShare).where(DealShare.deal_id == deal.id))
    ).scalar_one()
    assert share.label == "Lender"
    assert share.created_by_user_id == user.id
    assert f"/d/{share.slug}" in created.text

    listed = await client.get(f"/ui/deals/{deal.id}/deal-shares")
    assert f"/d/{share.slug}" in listed.text

    revoked = await client.post(f"/ui/deal-shares/{share.id}/revoke")
    assert revoked.status_code == 200
    assert f"/d/{share.slug}" not in revoked.text
    await session.refresh(share)
    assert share.revoked is True and share.revoked_at is not None
    # The link is dead for guests.
    assert (await client.get(f"/d/{share.slug}")).status_code == 404


async def test_deal_share_guards(client: AsyncClient, session: AsyncSession):
    org, _user, deal, _project = await _seed(session)
    share = DealShare(org_id=org.id, deal_id=deal.id, slug="Zz9Zz9Zz9Z", label="L")
    session.add(share)
    await session.commit()
    intruder = await _intruder(session)
    _auth(client, intruder.id)

    assert (await client.get(f"/ui/deals/{uuid.uuid4()}/deal-shares")).status_code == 404
    assert (await client.get(f"/ui/deals/{deal.id}/deal-shares")).status_code == 404
    assert (
        await client.post(f"/ui/deals/{deal.id}/deal-shares", data={"label": "x"})
    ).status_code == 404
    assert (await client.post(f"/ui/deal-shares/{uuid.uuid4()}/revoke")).status_code == 404
    assert (await client.post(f"/ui/deal-shares/{share.id}/revoke")).status_code == 404
    await session.refresh(share)
    assert share.revoked is False
    count = (
        await session.execute(select(DealShare).where(DealShare.deal_id == deal.id))
    ).scalars().all()
    assert len(count) == 1


async def test_archived_docs_stay_out_of_deal_zip(client: AsyncClient, session: AsyncSession):
    _org, user, deal, project = await _seed(session, deal_name="Z", project_name="P")
    _auth(client, user.id)
    await _upload(client, project.id, "old.pdf", b"OLD")
    doc = await _only_doc(session, project.id)
    await client.post(
        f"/ui/projects/{project.id}/documents/bulk",
        data={"action": "archive", "ids": [str(doc.id)]},
    )
    await session.refresh(doc)
    assert doc.status == DocumentStatus.archived
    resp = await client.get(f"/ui/deals/{deal.id}/documents/zip")
    assert resp.status_code == 200
    assert zipfile.ZipFile(io.BytesIO(resp.content)).namelist() == []
