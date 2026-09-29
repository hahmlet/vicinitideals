"""Open question (xfail): a non-admin member can delete the org-default template.

``set-org-default`` is admin-only, and ``User.is_org_admin=False`` is
documented as "read-only org access", yet POST
/ui/settings/scenario-templates/{id}/delete has no admin check: any member
can delete any template in their org -- including the org default, which
also clears the org's default pointer (an admin-only setting). Members may
legitimately create templates (Save as Template has no admin check), so the
intended rule for deleting is a product decision: admin-only, creator-or-
admin, or anyone. This test pins the narrowest reading -- a non-admin must
not be able to delete the template that is the ORG default -- and is
strict-xfail until that is decided.
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


@pytest.mark.xfail(
    strict=True,
    reason="Product decision pending: who may delete an org scenario template",
)
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
