"""Regression: renaming an org's slug to one another org already uses 500'd.

POST /settings/organization wrote the slug straight to the unique
``organizations.slug`` column, so a taken slug raised an IntegrityError (a
server error page). Onboarding already checks for a taken slug; the settings
route now does the same and answers 400, leaving both orgs unchanged.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


async def test_taken_slug_is_refused_not_500(client: AsyncClient, session: AsyncSession) -> None:
    org_a, _user_a = await seed_org(session)
    org_b, admin_b = await seed_org(session)
    admin_b.is_org_admin = True
    await session.commit()
    a_slug, b_slug, b_name = org_a.slug, org_b.slug, org_b.name
    set_client_auth(client, admin_b.id)

    resp = await client.post(
        "/settings/organization", data={"org_name": "Renamed", "org_slug": a_slug}
    )

    assert resp.status_code == 400
    assert "already taken" in resp.text
    await session.refresh(org_a)
    await session.refresh(org_b)
    assert org_a.slug == a_slug
    assert (org_b.slug, org_b.name) == (b_slug, b_name)


async def test_keeping_own_slug_is_not_a_collision(
    client: AsyncClient, session: AsyncSession
) -> None:
    org, admin = await seed_org(session)
    admin.is_org_admin = True
    await session.commit()
    set_client_auth(client, admin.id)

    resp = await client.post(
        "/settings/organization", data={"org_name": "Same Slug", "org_slug": org.slug}
    )
    assert resp.status_code == 303
    await session.refresh(org)
    assert org.name == "Same Slug"
