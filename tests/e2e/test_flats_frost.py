"""Frost depth (FOLLOWUPS 197) in a browser: a lot opened from the Lots page
shows the "Frost depth (footings)" note beside its colour -- the figure, whose
it is and the elevation caveat -- and the JSON report says the same, marked as
never a colour.

Read-only. Skips where no run is loaded. Read at request time from
flats/config/frost_depth.yaml, so no data load is needed after release.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_frost.py -m e2e -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

OUTCOMES = {"found", "silent", "not_read"}
LEVELS = {"city", "county", "state", None}


def test_a_lot_shows_its_frost_note_beside_an_untouched_colour(logged_in_page: Page, base_url: str) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots")
    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")

    first = page.locator("#lot-table tbody tr").first.locator("td a").first
    href = first.get_attribute("href")
    assert href
    first.click()

    block = page.locator("#lot-frost")
    expect(block).to_be_visible()
    expect(block).to_contain_text("Frost depth (footings)")
    expect(block).to_contain_text("never changes the lot")
    expect(block.locator("[data-frost-elevation]")).to_contain_text("Lot elevation is not held.")
    expect(page.locator("#lot-verdict")).to_be_visible()

    county_tlid = href.split("/flats/lots/", 1)[1].split("?", 1)[0]
    report = page.request.get(f"{base_url}/api/flats/lot/{county_tlid}").json()
    note = report["frost"]
    assert note["never_a_colour"] is True
    assert note["outcome"] in OUTCOMES and note["level"] in LEVELS
    expect(block).to_have_attribute("data-frost-outcome", note["outcome"])
    expect(block.locator("[data-frost-words]")).to_contain_text(note["words"][:40])
    if note["inches"] is None:
        # Not read: no figure is claimed for the place; the county's (else the state's) is for reference.
        assert note["words"].startswith("Not resolved:")
    else:
        expect(block.locator("[data-frost-words]")).to_contain_text(f"{note['inches']} in")
        assert note["quote"] and note["cite"]
