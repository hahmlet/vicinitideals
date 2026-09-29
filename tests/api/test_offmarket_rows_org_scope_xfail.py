"""Known leak (not fixed here): GET /ui/opportunities/rows/offmarket is not
org-scoped.

The off-market table lists manually-created opportunities
(``promotion_source == 'manual'``), which are always org-owned, but the query
never applies ``_apply_org_scope`` (the sibling ``/rows/deals`` does). So
org B's off-market tab shows org A's manual opportunities by name. List-route
org scoping is being reworked separately; this strict xfail flips to a pass
(and fails the suite) once that lands, so it gets promoted to a real test.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import seed_opportunity, seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


@pytest.mark.xfail(
    strict=True,
    reason="offmarket rows query has no org scope; list-route scoping owned by another change",
)
async def test_offmarket_rows_hide_other_orgs_manual_opportunities(
    client: AsyncClient, session: AsyncSession
):
    org_a, user_a = await seed_org(session)
    opp = await seed_opportunity(session, org_a, user_a, name="Alpha Secret Offmarket")
    opp.promotion_source = "manual"
    _org_b, user_b = await seed_org(session)
    await session.commit()
    set_client_auth(client, user_b.id)

    resp = await client.get("/ui/opportunities/rows/offmarket", headers={"hx-request": "true"})
    assert resp.status_code == 200
    assert "Alpha Secret Offmarket" not in resp.text
