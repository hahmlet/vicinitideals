"""Regression: POST /ui/admin/backfill-listing-buckets had no permission check.

Any signed-in user -- including a read-only member of any organization --
could trigger a write that re-classifies every unbucketed listing in every
organization. It is a site-admin tool (``/ui/admin/``), so it now uses the
same gate as the other site-admin settings routes (``_require_settings_owner``:
``User.is_admin``, 404 otherwise).
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity
from app.models.org import User
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


async def test_non_site_admin_cannot_run_listing_bucket_backfill(
    client: AsyncClient, session: AsyncSession
) -> None:
    org_a, _user_a = await seed_org(session)
    org_b, _user_b = await seed_org(session)
    # An org admin of org B -- but not a site admin.
    org_admin_b = User(id=uuid.uuid4(), org_id=org_b.id, name="Org Admin B", is_org_admin=True)
    member_b = User(id=uuid.uuid4(), org_id=org_b.id, name="Member B")
    listing_a = Opportunity(
        id=uuid.uuid4(),
        org_id=org_a.id,
        source="crexi",
        source_id=uuid.uuid4().hex,
        source_url="https://crexi.example/a",
        county="Lane",
    )
    session.add_all([org_admin_b, member_b, listing_a])
    await session.commit()

    for caller in (member_b, org_admin_b):
        set_client_auth(client, caller.id)
        resp = await client.post("/ui/admin/backfill-listing-buckets")
        assert resp.status_code == 404, caller.name

    await session.refresh(listing_a)
    assert listing_a.priority_bucket is None
