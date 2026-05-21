"""Builder route canonicalizes URL to always include ?project=.

Without project in URL, HX-Current-URL header on form posts/deletes
omits it, so `_active_project_from_request` returns None and JSONB
mutations (e.g. unit-mix delete) silently no-op. Route must redirect
bare /builder hits to a URL with the active project appended.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import COOKIE_NAME, create_session_token
from app.models.deal import DealModel, ProjectType
from app.models.opportunity import Opportunity
from app.models.project import Project


pytestmark = pytest.mark.asyncio


async def _auth(client: AsyncClient, user_id) -> None:
    client.cookies.set(COOKIE_NAME, create_session_token(user_id))


async def _seed_minimal(session: AsyncSession) -> tuple[DealModel, Project, uuid.UUID]:
    """Seed org/user/opportunity/deal_model/project — minimal fields only."""
    from tests.conftest import seed_org, seed_opportunity
    from app.models.deal import Deal

    org, user = await seed_org(session)
    opp: Opportunity = await seed_opportunity(session, org, user)

    top_deal = Deal(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Builder Redirect Test",
        created_by_user_id=user.id,
    )
    session.add(top_deal)
    await session.flush()

    deal_model = DealModel(
        id=uuid.uuid4(),
        deal_id=top_deal.id,
        created_by_user_id=user.id,
        name="Base Case",
        version=1,
        is_active=True,
        project_type=ProjectType.value_add,
    )
    session.add(deal_model)
    await session.flush()

    project = Project(
        id=uuid.uuid4(),
        scenario_id=deal_model.id,
        opportunity_id=opp.id,
        name="Default Project",
    )
    session.add(project)
    await session.commit()
    return deal_model, project, user.id


async def test_builder_redirects_to_include_project_param(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    deal_model, project, user_id = await _seed_minimal(session)
    await _auth(client, user_id)

    resp = await client.get(
        f"/models/{deal_model.id}/builder?module=property",
        follow_redirects=False,
    )

    assert resp.status_code == 302, resp.text
    location = resp.headers["location"]
    assert f"project={project.id}" in location, (
        f"redirect missing project={project.id}: {location}"
    )
    assert "module=property" in location


async def test_builder_no_redirect_for_underwriting_view(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    deal_model, _project, user_id = await _seed_minimal(session)
    await _auth(client, user_id)

    resp = await client.get(
        f"/models/{deal_model.id}/builder?view=underwriting",
        follow_redirects=False,
    )

    # underwriting view renders directly without project redirect
    assert resp.status_code == 200, resp.text


async def test_builder_no_redirect_when_project_already_present(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    deal_model, project, user_id = await _seed_minimal(session)
    await _auth(client, user_id)

    resp = await client.get(
        f"/models/{deal_model.id}/builder?module=property&project={project.id}",
        follow_redirects=False,
    )

    assert resp.status_code == 200, resp.text
