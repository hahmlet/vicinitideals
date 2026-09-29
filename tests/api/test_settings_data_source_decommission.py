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


async def test_oregon_trigger_button_reaches_the_sweep_route(
    client: AsyncClient,
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 'Trigger Sweep' button posted to /scraper/oregon-elicense/run, which
    has no route (the sweep lives under /api/), so every click answered
    'Invalid API key'. Follow the URL the page renders and expect a queued job."""
    import re
    from unittest.mock import patch

    monkeypatch.setattr(settings, "proxyon_api_key", "", raising=False)
    await _admin(client, session)
    page = await client.get("/settings/scraping-services")
    urls = re.findall(r"fetch\('([^']+)'", page.text)
    oregon = [u for u in urls if "oregon" in u]
    assert oregon == ["/api/scraper/oregon-elicense/run"], urls

    client.headers.pop("X-User-ID", None)  # the browser sends only its cookie
    with patch("app.tasks.oregon_elicense.oregon_elicense_sweep.delay") as delay:
        delay.return_value.id = "oregon-7"
        resp = await client.post(oregon[0])
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "queued"
    delay.assert_called_once_with()
