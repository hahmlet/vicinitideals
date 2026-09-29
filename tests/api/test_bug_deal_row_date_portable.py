"""Bug: the deals list (GET /ui/deals/rows, POST /ui/deals/{id}/archive) and
the deal page formatted dates with ``strftime('%b %-d, %Y')``. ``%-d`` is a
glibc extension; on Windows it raises ValueError, so both routes 500'd for
any deal in the local test run. They now use the portable
``ui_helpers._fmt_day`` like the rest of the UI.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ui_deals_pipeline import _build_deal_row
from app.models.deal import Deal
from tests.conftest import seed_org, set_client_auth


def test_deal_row_date_is_portable() -> None:
    deal = Deal(id=uuid.uuid4(), org_id=uuid.uuid4(), name="Dated")
    deal.created_at = datetime(2026, 9, 8, tzinfo=timezone.utc)
    deal.scenarios = []
    assert _build_deal_row(deal)["last_updated_fmt"] == "Sep 8, 2026"


@pytest.mark.asyncio
async def test_deals_rows_renders_on_every_platform(client: AsyncClient, session: AsyncSession):
    org, user = await seed_org(session)
    session.add(Deal(id=uuid.uuid4(), org_id=org.id, name="Portable Deal", created_by_user_id=user.id))
    await session.commit()
    set_client_auth(client, user.id)

    resp = await client.get("/ui/deals/rows", headers={"hx-request": "true"})
    assert resp.status_code == 200
    assert "Portable Deal" in resp.text
