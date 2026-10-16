"""Hostile input on the FLATS routes answers 200, 404 or 422 -- never a 500.

Each URL here once reached the database with a value it cannot hold (an
integer or numeric overflow, a NUL byte) and came back as an uncaught
DBAPIError. A valid request's answer is untouched: these only pin the status.
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api.test_ui_flats_lots import _login, _seed

pytestmark = pytest.mark.asyncio

LONG = "x" * 5000

URLS = [
    "/flats/lots?page=99999999999999999999",
    "/flats/lots?ppu=1&ppu_max=1e999",
    "/flats/lots?q=%00",
    "/flats/lots/multnomah/%00",
    "/api/flats/lookup?q=%00",
    "/flats/lots?page=-1",
    "/flats/lots?page=nan",
    "/flats/lots?page=1e3",
    "/flats/lots?page=100001",
    "/flats/lots?run=99999999999999999999",
    "/flats/lots?run=-5",
    "/flats/lots?ppu=1&ppu_max=-1",
    "/flats/lots?ppu=1&ppu_max=NaN",
    "/flats/lots?ppu=1&ppu_max=Infinity",
    "/flats/lots?ppu=1&ppu_max=1e-999",
    "/flats/lots?ppu=1&ppu_max=99999999999999999999999999999999",
    "/flats/lots?pod=1e999&road=1e999",
    "/flats/lots?pod=-1&road=-1",
    "/flats/lots?pod=NaN&road=NaN",
    "/flats/lots?jurisdiction=%00&zone=%00&design=%00&colour=%00&sort=%00",
    "/flats/lots?q=%25&zone=%5F",
    "/flats/lots?q=%F0%9F%8F%A0%E2%80%AE%C3%A9",
    "/flats/lots?q=%EF%BF%BD",
    f"/flats/lots?q={LONG}",
    f"/flats/lots?ppu=1&ppu_max={LONG}",
    f"/flats/lots?jurisdiction={LONG}&zone={LONG}",
    "/flats/lots/%00/%00",
    "/flats/lots/multnomah/%E2%82%AC%F0%9F%8F%A0",
    f"/flats/lots/multnomah/{LONG}",
    "/flats/lots/multnomah/1S2E08BA%20%20-09500?pod=1e999&road=1e999",
    "/flats/lots/multnomah/1S2E08BA%20%20-09500?run=99999999999999999999",
    "/api/flats/lookup?q=%25",
    "/api/flats/lookup?q=%5C",
    "/api/flats/lookup?q=%F0%9F%8F%A0",
    f"/api/flats/lookup?q={LONG}",
    "/api/flats/lot/multnomah/%00",
    "/api/flats/lot/%00/%00",
    f"/api/flats/lot/multnomah/{LONG}",
    "/api/flats/rulings?county=%00&city=%00&zone=%00&tlid=%00",
    f"/api/flats/rulings?tlid={LONG}",
]


@pytest.mark.parametrize("url", URLS)
async def test_hostile_input_never_answers_500(client: AsyncClient, session: AsyncSession, url: str):
    await _login(client, session)
    await _seed(session)

    response = await client.get(url)

    assert response.status_code in (200, 404, 422), (url, response.status_code)
