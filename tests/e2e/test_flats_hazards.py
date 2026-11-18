"""Mapped ground hazards (FOLLOWUPS 198) in a browser: a lot opened from the Lots
page shows the "Ground hazards (mapped)" block beside its colour -- the notes
when a build is loaded, "not measured yet" before -- and the JSON report says
the same, marked as never a colour.

Read-only. Skips where no run is loaded.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_hazards.py -m e2e -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

STATUSES = {"not_loaded", "outside", "superseded", "not_mapped", "mapped_low", "mapped", "none_found", "found"}


def test_a_lot_shows_its_hazard_notes_beside_an_untouched_colour(logged_in_page: Page, base_url: str) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots")
    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")

    first = page.locator("#lot-table tbody tr").first.locator("td a").first
    href = first.get_attribute("href")
    assert href
    first.click()

    block = page.locator("#lot-hazards")
    expect(block).to_be_visible()
    expect(block).to_contain_text("Ground hazards (mapped)")
    expect(page.locator("#lot-verdict")).to_be_visible()

    county_tlid = href.split("/flats/lots/", 1)[1].split("?", 1)[0]
    report = page.request.get(f"{base_url}/api/flats/lot/{county_tlid}").json()
    note = report["hazards"]
    assert note["never_a_colour"] is True
    assert [g["hazard"] for g in note["groups"]] == ["landslide", "liquefaction", "flood"]
    layers = [x for g in note["groups"] for x in g["layers"]]
    assert {x["status"] for x in layers} <= STATUSES

    if not note["measured"]:
        expect(block).to_contain_text("not measured yet")
        return
    # A build is loaded: every shown layer is on the page with its state, the
    # DOGAMI caveat once, and nothing unread is called "no hazard".
    expect(block.locator("[data-hazard-caveat]")).to_contain_text("site-specific")
    for group in note["groups"]:
        for layer in group["shown"]:
            expect(block.locator(f'[data-layer="{layer["layer"]}"]')).to_have_attribute("data-status", layer["status"])
            if layer["status"] == "not_loaded":
                expect(block.locator(f'[data-layer="{layer["layer"]}"]')).to_contain_text("Not loaded yet")
