"""Tests for document list sorting + filtering (extension, upload date range).

Exercises the shared `_load_docs` query builder directly (no auth) and the
guest rows endpoint (auth-exempt), so both run on Windows-local Postgres.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui_documents import (
    _distinct_exts,
    _doc_query,
    _generate_share_slug,
    _load_docs,
)
from app.models.deal import Deal, ProjectType, Scenario
from app.models.document import Document, DocumentShare
from app.models.opportunity import Opportunity
from app.models.project import Project

pytestmark = pytest.mark.asyncio


async def _seed_project(session: AsyncSession):
    from tests.conftest import seed_opportunity, seed_org

    org, user = await seed_org(session)
    opp: Opportunity = await seed_opportunity(session, org, user)
    deal = Deal(id=uuid.uuid4(), org_id=org.id, name="Filter Deal", created_by_user_id=user.id)
    session.add(deal)
    await session.flush()
    scenario = Scenario(
        id=uuid.uuid4(), deal_id=deal.id, created_by_user_id=user.id,
        name="Base", version=1, is_active=True, project_type=ProjectType.value_add,
    )
    session.add(scenario)
    await session.flush()
    project = Project(id=uuid.uuid4(), scenario_id=scenario.id, opportunity_id=opp.id, name="FP")
    session.add(project)
    await session.commit()
    return project, org


def _doc(org, project, name, size, when):
    return Document(
        org_id=org.id, project_id=project.id, filename=name, size_bytes=size,
        sha256=name, storage_key=name,
        created_at=datetime(when[0], when[1], when[2], tzinfo=timezone.utc),
    )


async def _seed_docs(session, org, project):
    session.add_all([
        _doc(org, project, "alpha.pdf", 300, (2026, 1, 10)),
        _doc(org, project, "beta.PDF", 100, (2026, 3, 5)),
        _doc(org, project, "gamma.jpg", 200, (2026, 2, 20)),
    ])
    await session.commit()


async def test_sort_by_name(client: AsyncClient, session: AsyncSession):
    project, org = await _seed_project(session)
    await _seed_docs(session, org, project)
    asc = await _load_docs(session, org.id, project.id, "active", _doc_query(sort="name", direction="asc"))
    assert [d.filename for d in asc] == ["alpha.pdf", "beta.PDF", "gamma.jpg"]
    desc = await _load_docs(session, org.id, project.id, "active", _doc_query(sort="name", direction="desc"))
    assert [d.filename for d in desc] == ["gamma.jpg", "beta.PDF", "alpha.pdf"]


async def test_sort_by_size(client: AsyncClient, session: AsyncSession):
    project, org = await _seed_project(session)
    await _seed_docs(session, org, project)
    asc = await _load_docs(session, org.id, project.id, "active", _doc_query(sort="size", direction="asc"))
    assert [d.size_bytes for d in asc] == [100, 200, 300]


async def test_sort_by_date_desc_default(client: AsyncClient, session: AsyncSession):
    project, org = await _seed_project(session)
    await _seed_docs(session, org, project)
    docs = await _load_docs(session, org.id, project.id, "active", _doc_query())
    assert [d.filename for d in docs] == ["beta.PDF", "gamma.jpg", "alpha.pdf"]


async def test_filter_by_extension_case_insensitive(client: AsyncClient, session: AsyncSession):
    project, org = await _seed_project(session)
    await _seed_docs(session, org, project)
    pdfs = await _load_docs(session, org.id, project.id, "active", _doc_query(ext="pdf"))
    # Matches both alpha.pdf and beta.PDF regardless of case.
    assert {d.filename for d in pdfs} == {"alpha.pdf", "beta.PDF"}


async def test_filter_by_date_range(client: AsyncClient, session: AsyncSession):
    project, org = await _seed_project(session)
    await _seed_docs(session, org, project)
    # Inclusive window Feb 1 .. Feb 28 → only gamma.jpg (Feb 20).
    in_feb = await _load_docs(
        session, org.id, project.id, "active",
        _doc_query(date_from="2026-02-01", date_to="2026-02-28"),
    )
    assert [d.filename for d in in_feb] == ["gamma.jpg"]


async def test_distinct_exts(client: AsyncClient, session: AsyncSession):
    project, org = await _seed_project(session)
    await _seed_docs(session, org, project)
    assert await _distinct_exts(session, org.id, project.id) == [".jpg", ".pdf"]


async def test_guest_rows_endpoint_sorts(client: AsyncClient, session: AsyncSession):
    project, org = await _seed_project(session)
    await _seed_docs(session, org, project)
    share = DocumentShare(
        org_id=org.id, project_id=project.id, label="L", slug=_generate_share_slug(),
    )
    session.add(share)
    await session.commit()

    resp = await client.get(f"/share/{share.slug}/rows?sort=name&direction=asc")
    assert resp.status_code == 200, resp.text
    body = resp.text
    # alpha appears before gamma in name-ascending order.
    assert body.index("alpha.pdf") < body.index("gamma.jpg")
    # Filter dropdown reflects available extensions.
    assert "All types" in body
