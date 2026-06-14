"""Settings pages reflect the parcel/LoopNet decommission.

- /settings/scraping-services no longer lists the retired LoopNet scrapers; it
  still lists the live Crexi + Oregon eLicense services.
- /settings/data-sources (the county-GIS reference-layer catalog) is removed
  entirely along with its route — the whole parcel-screening data layer is gone.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from tests.conftest import seed_org, set_client_auth

pytestmark = pytest.mark.asyncio


async def _admin(client: AsyncClient, session: AsyncSession):
    org, user = await seed_org(session)
    user.is_admin = True
    session.add(user)
    await session.commit()
    set_client_auth(client, user.id)
    return user


async def test_scraping_services_drops_loopnet_keeps_crexi(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # No ProxyOn key → residential snapshot returns "Not Configured" without network.
    monkeypatch.setattr(settings, "proxyon_api_key", "", raising=False)
    await _admin(client, session)

    resp = await client.get("/settings/scraping-services")
    assert resp.status_code == 200
    assert "Crexi Ingest" in resp.text
    assert "Oregon eLicense" in resp.text
    # The decommissioned LoopNet scrapers must not appear.
    assert "LoopNet" not in resp.text


async def test_data_sources_route_removed(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    # Admin user → not auth-gated; a 404 means the route itself is gone.
    await _admin(client, session)
    resp = await client.get("/settings/data-sources", follow_redirects=False)
    assert resp.status_code == 404
