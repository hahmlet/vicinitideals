"""Bug: POST /ui/opportunities/{opp_id}/archive had no org check.

Any signed-in user could archive any org's opportunity by id (it also
rewrote ``opp_status`` to ``archived``). Another org's opportunity must be
treated as missing: redirect, nothing written.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import seed_opportunity, seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


async def test_other_org_cannot_archive_opportunity(client: AsyncClient, session: AsyncSession):
    org_a, user_a = await seed_org(session)
    opp = await seed_opportunity(session, org_a, user_a, name="Alpha Opp")
    opp.opp_status = "active"
    _org_b, user_b = await seed_org(session)
    await session.commit()
    set_client_auth(client, user_b.id)

    resp = await client.post(f"/ui/opportunities/{opp.id}/archive")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/opportunities"
    await session.refresh(opp)
    assert opp.archived is False
    assert opp.opp_status == "active"
