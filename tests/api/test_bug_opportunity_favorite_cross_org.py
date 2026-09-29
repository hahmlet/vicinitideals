"""Bug: PATCH /ui/opportunities/{opp_id}/favorite had no org check.

Any signed-in user could flip the favourite star on another org's
opportunity by id (the flag lives on the row, so org A saw org B's change).
Another org's opportunity must 404 with nothing written. Unpromoted scraped
listings (org_id NULL) stay open; that path is in
test_ui_deals_pipeline_routes.py.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import seed_opportunity, seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


async def test_other_org_cannot_favorite_opportunity(client: AsyncClient, session: AsyncSession):
    org_a, user_a = await seed_org(session)
    opp = await seed_opportunity(session, org_a, user_a, name="Alpha Opp")
    _org_b, user_b = await seed_org(session)
    await session.commit()
    set_client_auth(client, user_b.id)

    resp = await client.patch(
        f"/ui/opportunities/{opp.id}/favorite", headers={"hx-request": "true"}
    )
    assert resp.status_code == 404
    assert "star-btn" not in resp.text
    await session.refresh(opp)
    assert opp.is_favorited is False
