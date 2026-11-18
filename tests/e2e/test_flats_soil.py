"""The USDA soil survey under the lot (FOLLOWUPS 196) in a browser: a GREEN
lot opens to a "Soil (USDA survey)" block with the farm-scale caveat, every map
unit with its identifiers and its source, and the colour block untouched.

Read-only. Skips where no run is loaded, or no soil build has been loaded
onto the copy in use (``scripts/flats_lot_soil.py load``).

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_soil.py -m e2e -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_a_green_lot_says_its_soil_beside_its_colour(logged_in_page: Page, base_url: str) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots?colour=green")
    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")
    if page.get_by_text("No lots match.").count():
        pytest.skip("no green lots on the run shown")

    first = page.locator("#lot-table tbody tr").first.locator("td a").first
    href = first.get_attribute("href")
    assert href
    first.click()

    block = page.locator("#lot-soil")
    expect(block).to_be_visible()
    expect(block).to_contain_text("Soil (USDA survey)")
    if "not measured yet" in block.inner_text():
        pytest.skip("no soil build loaded on the copy in use")
    expect(block).to_contain_text("farm-field scale")
    expect(block).to_contain_text("never changes the lot")
    expect(block).to_contain_text("USDA Natural Resources Conservation Service (NRCS) soil survey, SSURGO")
    expect(block.locator("[data-soil-dominant]")).to_have_count(1)
    expect(block.locator("[data-soil-technical]").first).to_contain_text("mukey")
    expect(block.locator("[data-wet-season]").first).to_be_visible()
    # The colour block is still there.
    expect(page.locator("#lot-verdict")).to_be_visible()

    # The JSON report carries the same note, marked as never a colour.
    county_tlid = href.split("/flats/lots/", 1)[1].split("?", 1)[0]
    report = page.request.get(f"{base_url}/api/flats/lot/{county_tlid}").json()
    soil = report["soil"]
    assert soil["never_a_colour"] is True
    dominant = soil["dominant"]
    assert dominant["mukey"] and dominant["areasymbol"] and dominant["saverest"]
    assert dominant["mukey"] == block.locator("[data-soil-dominant]").get_attribute("data-soil-dominant")
    assert abs(sum(u["area_sqft"] for u in soil["units"]) + soil["uncovered_sqft"] - soil["lot_area_sqft"]) < 1
    assert soil["source_name"].startswith("USDA Natural Resources Conservation Service")
