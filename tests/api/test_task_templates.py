"""Tests for org default-task templates (seeded onto new projects)."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Deal, ProjectType, Scenario
from app.models.document import DocumentTask, DocumentTaskStatus, DocumentTaskTemplate
from app.models.opportunity import Opportunity
from app.models.project import Project
from app.services.document_task_seeding import seed_default_tasks

pytestmark = pytest.mark.asyncio


async def _auth(client: AsyncClient, user_id) -> None:
    from tests.conftest import set_client_auth

    set_client_auth(client, user_id)


async def _seed_org_deal_project(session: AsyncSession):
    from tests.conftest import seed_opportunity, seed_org

    org, user = await seed_org(session)
    opp: Opportunity = await seed_opportunity(session, org, user)
    deal = Deal(id=uuid.uuid4(), org_id=org.id, name="TT Deal", created_by_user_id=user.id)
    session.add(deal)
    await session.flush()
    scenario = Scenario(
        id=uuid.uuid4(), deal_id=deal.id, created_by_user_id=user.id,
        name="Base", version=1, is_active=True, project_type=ProjectType.value_add,
    )
    session.add(scenario)
    await session.flush()
    project = Project(id=uuid.uuid4(), scenario_id=scenario.id, opportunity_id=opp.id, name="P")
    session.add(project)
    await session.commit()
    return org, user, deal, project, opp


def _add_templates(session, org, titles):
    for i, t in enumerate(titles):
        session.add(DocumentTaskTemplate(org_id=org.id, title=t, sort_order=i))


# ── seed helper (no auth) ────────────────────────────────────────────────────

async def test_seed_creates_one_task_per_template(client: AsyncClient, session: AsyncSession):
    org, _user, _deal, project, _opp = await _seed_org_deal_project(session)
    _add_templates(session, org, ["Tenant Leases", "Survey", "Title"])
    await session.commit()

    count = await seed_default_tasks(session, org.id, project.id)
    await session.commit()
    assert count == 3
    rows = (
        await session.execute(select(DocumentTask).where(DocumentTask.project_id == project.id))
    ).scalars().all()
    assert {r.title for r in rows} == {"Tenant Leases", "Survey", "Title"}
    assert all(r.status == DocumentTaskStatus.pending for r in rows)


async def test_seed_noop_without_templates(client: AsyncClient, session: AsyncSession):
    org, _user, _deal, project, _opp = await _seed_org_deal_project(session)
    count = await seed_default_tasks(session, org.id, project.id)
    await session.commit()
    assert count == 0
    rows = (
        await session.execute(select(DocumentTask).where(DocumentTask.project_id == project.id))
    ).scalars().all()
    assert rows == []


async def test_scenario_factory_seeds_new_project(client: AsyncClient, session: AsyncSession):
    """Creating a scenario via the canonical factory seeds the org's templates."""
    from app.services.scenario_factory import create_scenario

    org, user, deal, _project, opp = await _seed_org_deal_project(session)
    _add_templates(session, org, ["Default A", "Default B"])
    await session.commit()

    scenario, project, _inputs = await create_scenario(
        session=session,
        deal_id=deal.id,
        deal_type=ProjectType.acquisition,
        user_id=user.id,
        org_id=org.id,
        opportunity_id=opp.id,
    )
    await session.commit()
    assert project is not None
    rows = (
        await session.execute(select(DocumentTask).where(DocumentTask.project_id == project.id))
    ).scalars().all()
    assert {r.title for r in rows} == {"Default A", "Default B"}


# ── settings CRUD (auth — CI/LAN) ────────────────────────────────────────────

async def test_settings_create_and_delete(client: AsyncClient, session: AsyncSession):
    org, user, _deal, _project, _opp = await _seed_org_deal_project(session)
    await _auth(client, user.id)

    created = await client.post("/ui/settings/task-templates", data={"title": "Estoppels"})
    assert created.status_code == 200, created.text
    assert "Estoppels" in created.text
    row = (
        await session.execute(select(DocumentTaskTemplate).where(DocumentTaskTemplate.org_id == org.id))
    ).scalar_one()

    deleted = await client.post(f"/ui/settings/task-templates/{row.id}/delete")
    assert deleted.status_code == 200
    remaining = (
        await session.execute(select(DocumentTaskTemplate).where(DocumentTaskTemplate.org_id == org.id))
    ).scalars().all()
    assert remaining == []
