"""Frost depth (FOLLOWUPS 197): the lot report and the lot page carry the frost
note for the lot's place from flats/config/frost_depth.yaml -- the figure, whose
it is, the printed quote and the elevation caveat -- and no colour, verdict or
check moves (it is read at request time; nothing is loaded)."""

from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import pytest

from tests.api.test_ui_flats_lots import _login, _seed

pytestmark = pytest.mark.asyncio

PORTLAND = "1S2E08BA  -09500"
MILWAUKIE = "11E25AB  -00300"


async def test_the_report_carries_the_frost_note_and_never_a_colour(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _seed(session)

    report = (await client.get(f"/api/flats/lot/multnomah/{PORTLAND}")).json()
    note = report["frost"]
    assert note["never_a_colour"] is True
    assert (note["outcome"], note["level"], note["kind"], note["inches"]) == ("found", "city", "practice", 12)
    assert note["quote"] == "Soil frost depth is 12 inches."
    assert note["state"]["inches"] == 12 and note["state"]["below_ft"] == 2500
    assert "Lot elevation is not held." in note["elevation_words"]
    # Colour and verdict come from the screen as before.
    assert report["colour"] and report["verdict"]

    silent = (await client.get(f"/api/flats/lot/clackamas/{MILWAUKIE}")).json()["frost"]
    assert (silent["outcome"], silent["level"], silent["inches"]) == ("silent", "county", 12)
    assert "Flagged county level." in silent["words"]


async def test_the_lot_page_says_the_frost_note(client: AsyncClient, session: AsyncSession):
    await _login(client, session)
    await _seed(session)

    page = await client.get(f"/flats/lots/multnomah/{PORTLAND.replace(' ', '%20')}")
    assert page.status_code == 200
    block = page.text.split('id="lot-frost"', 1)[1].split('id="net-land', 1)[0]
    assert 'data-frost-outcome="found" data-frost-level="city"' in block
    assert "Frost depth (footings)" in block
    assert "<strong>12 in</strong>" in block
    assert "Soil frost depth is 12 inches." in block
    assert "Lot elevation is not held." in block
    assert "never changes the lot&#39;s colour" in block or "never changes the lot's colour" in block

    other = await client.get(f"/flats/lots/clackamas/{MILWAUKIE.replace(' ', '%20')}")
    block = other.text.split('id="lot-frost"', 1)[1].split('id="net-land', 1)[0]
    assert 'data-frost-outcome="silent" data-frost-level="county"' in block
    assert "what was read" in block
