"""Tests for the enforced document naming scheme + task auto-filing.

Pure helpers run without a DB. The upload/zip plumbing is exercised through the
auth-exempt guest deal routes so it runs on Windows-local Postgres.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui_documents import (
    _build_deal_zip,
    _label_default,
    _safe_component,
    _scheme_name,
)
from app.models.deal import Deal, ProjectType, Scenario
from app.models.document import DealShare, DocumentStage, DocumentTask
from app.models.document import Document
from app.models.project import Project

pytestmark = pytest.mark.asyncio


# ── Pure helpers ─────────────────────────────────────────────────────────────

def test_safe_component_strips_forbidden_chars():
    out = _safe_component('Re/po:rt*?"<>|name.. ')
    for ch in '<>:"/\\|?*':
        assert ch not in out
    assert not out.endswith(".") and not out.endswith(" ")


def test_safe_component_collapses_whitespace():
    assert _safe_component("  a   b\tc  ") == "a b c"


def test_label_default_strips_extension():
    assert _label_default("Rent Roll.pdf") == "Rent Roll"
    assert _label_default("noext") == "noext"


def test_scheme_name_format():
    when = datetime(2026, 6, 24, tzinfo=timezone.utc)
    name = _scheme_name(
        "North Tower", "Financials", "Rent Roll", DocumentStage.draft, when, ".pdf"
    )
    assert name == "North Tower - Financials - Rent Roll - Draft - 06-24-2026.pdf"


def test_scheme_name_final_and_fallbacks():
    when = datetime(2026, 1, 2, tzinfo=timezone.utc)
    name = _scheme_name("", "", "", DocumentStage.final, when, ".png")
    assert name == "Project - Misc. - Document - Final - 01-02-2026.png"


# ── Guest upload plumbing (auth-exempt) ─────────────────────────────────────

@pytest.fixture(autouse=True)
def _doc_storage_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.config.settings.document_storage_path", str(tmp_path), raising=True
    )


async def _seed(session: AsyncSession):
    from app.api.routers.ui_documents import _generate_share_slug
    from tests.conftest import seed_org

    org, user = await seed_org(session)
    deal = Deal(id=uuid.uuid4(), org_id=org.id, name="Tower Deal", created_by_user_id=user.id)
    session.add(deal)
    await session.flush()
    scenario = Scenario(
        id=uuid.uuid4(), deal_id=deal.id, name="North Tower", version=1,
        is_active=True, project_type=ProjectType.value_add,
    )
    session.add(scenario)
    await session.flush()
    project = Project(id=uuid.uuid4(), scenario_id=scenario.id, name="North Tower")
    session.add(project)
    ds = DealShare(
        org_id=org.id, deal_id=deal.id, slug=_generate_share_slug(), label="L"
    )
    session.add(ds)
    await session.commit()
    return org, deal, project, ds


async def test_upload_sets_label_stage_and_creates_task(
    client: AsyncClient, session: AsyncSession
):
    org, deal, project, ds = await _seed(session)
    resp = await client.post(
        f"/d/{ds.slug}/p/{project.id}/upload",
        files={"files": ("raw_name.pdf", b"%PDF data", "application/pdf")},
        data={
            "name_label": "Rent Roll",
            "stage": "final",
            "task_choice": "__new__",
            "new_task": "Leases",
        },
    )
    assert resp.status_code == 200, resp.text

    doc = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalar_one()
    assert doc.filename == "raw_name.pdf"        # original retained
    assert doc.name_label == "Rent Roll"
    assert doc.stage == DocumentStage.final
    # A new 'Leases' task was created and the doc filed into it.
    task = await session.get(DocumentTask, doc.task_id)
    assert task is not None and task.title == "Leases"
    # Scheme name appears in the rendered rows.
    assert "North Tower - Leases - Rent Roll - Final" in resp.text


async def test_upload_defaults_to_misc_task(client: AsyncClient, session: AsyncSession):
    org, deal, project, ds = await _seed(session)
    resp = await client.post(
        f"/d/{ds.slug}/p/{project.id}/upload",
        files={"files": ("x.pdf", b"%PDF", "application/pdf")},
        data={"name_label": "", "stage": "draft", "task_choice": "__misc__"},
    )
    assert resp.status_code == 200, resp.text
    doc = (
        await session.execute(select(Document).where(Document.project_id == project.id))
    ).scalar_one()
    task = await session.get(DocumentTask, doc.task_id)
    assert task is not None and task.title == "Misc."
    assert doc.name_label == "x"                  # defaulted to upload stem


async def test_deal_zip_folders_by_project_and_task(
    client: AsyncClient, session: AsyncSession
):
    org, deal, project, ds = await _seed(session)
    await client.post(
        f"/d/{ds.slug}/p/{project.id}/upload",
        files={"files": ("doc.pdf", b"%PDF body", "application/pdf")},
        data={"name_label": "Survey", "stage": "draft", "task_choice": "__new__",
              "new_task": "Diligence"},
    )
    projects = [project]
    resp = await _build_deal_zip(session, org.id, deal.name, projects)
    body = b"".join([chunk async for chunk in resp.body_iterator])
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        names = zf.namelist()
    assert any(
        n.startswith("North Tower/Diligence/") and n.endswith(".pdf") for n in names
    ), names
