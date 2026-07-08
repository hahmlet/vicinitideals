"""Builder '+ Add Project' button visibility matches the server-side cap.

Regression: server allows 8 projects per deal (create_deal_project rejects
at >= 8) but the template gated the button at 5, so deals with 5-7 projects
had no way to add another even though the server would accept it.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.deal import Scenario, ProjectType
from app.models.project import Project


pytestmark = pytest.mark.asyncio

ADD_PROJECT_BUTTON = "+ Add Project"


async def _seed_deal_with_projects(
    session: AsyncSession, n_projects: int
) -> tuple[Scenario, Project, uuid.UUID]:
    """Seed org/user/opportunity/deal_model and n_projects projects."""
    from tests.conftest import seed_org, seed_opportunity
    from app.models.deal import Deal

    org, user = await seed_org(session)
    opp = await seed_opportunity(session, org, user)

    top_deal = Deal(
        id=uuid.uuid4(),
        org_id=org.id,
        name="Add Project Cap Test",
        created_by_user_id=user.id,
    )
    session.add(top_deal)
    await session.flush()

    deal_model = Scenario(
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

    first_project = None
    for i in range(n_projects):
        project = Project(
            id=uuid.uuid4(),
            scenario_id=deal_model.id,
            opportunity_id=opp.id,
            name=f"Project {i + 1}",
        )
        session.add(project)
        if first_project is None:
            first_project = project
    await session.commit()
    return deal_model, first_project, user.id


async def _get_builder(
    client: AsyncClient, deal_model: Scenario, project: Project, user_id
) -> str:
    from tests.conftest import set_client_auth

    set_client_auth(client, user_id)
    resp = await client.get(
        f"/models/{deal_model.id}/builder?project={project.id}",
        follow_redirects=False,
    )
    assert resp.status_code == 200, resp.text
    return resp.text


async def test_add_project_button_visible_with_seven_projects(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    deal_model, project, user_id = await _seed_deal_with_projects(session, 7)
    html = await _get_builder(client, deal_model, project, user_id)
    assert ADD_PROJECT_BUTTON in html, (
        "button must stay visible below the server cap of 8 projects"
    )


async def test_add_project_button_hidden_at_eight_projects(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    deal_model, project, user_id = await _seed_deal_with_projects(session, 8)
    html = await _get_builder(client, deal_model, project, user_id)
    assert ADD_PROJECT_BUTTON not in html, (
        "button must hide once the server cap of 8 projects is reached"
    )
