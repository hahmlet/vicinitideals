"""A non-admin member cannot delete an org scenario template.

Ruled by Steph 2026-09-29: deleting a template is for org admins only (a
template is shared by the whole org, and deleting the org default also
clears an admin-only setting). Members may still create templates.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org import User
from app.models.scenario_template import ScenarioTemplate
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


async def test_non_admin_cannot_delete_org_default_template(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await seed_org(session)
    admin.is_org_admin = True
    member = User(id=uuid.uuid4(), org_id=org.id, name="Member", is_org_admin=False)
    tmpl = ScenarioTemplate(
        id=uuid.uuid4(),
        org_id=org.id,
        created_by_user_id=admin.id,
        name="Org Standard",
        template_json={},
        created_at=datetime.now(UTC),
    )
    session.add_all([member, tmpl])
    await session.flush()
    org.default_template_id = tmpl.id
    await session.commit()
    set_client_auth(client, member.id)

    resp = await client.post(
        f"/ui/settings/scenario-templates/{tmpl.id}/delete",
        headers={"hx-request": "true"},
    )

    assert resp.status_code == 403
    still_there = (await session.execute(
        select(ScenarioTemplate.id).where(ScenarioTemplate.id == tmpl.id)
    )).scalar_one_or_none()
    assert still_there == tmpl.id
    await session.refresh(org)
    assert org.default_template_id == tmpl.id
