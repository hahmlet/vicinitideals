"""What stands on the lot (FOLLOWUPS 125) in a browser: the Lots page's
"What stands there" filter narrows the list, and the lot it opens says the
same label -- beside the colour, never changing it.

Read-only. Skips where no run is loaded, or no occupancy build has been
loaded onto the copy in use (``scripts/flats_lot_occupancy.py load``).

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_occupancy.py -m e2e -v
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_the_filter_is_offered_with_every_label(logged_in_page: Page, base_url: str) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots")
    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")

    picker = page.locator("#occupancy-filter")
    expect(picker).to_be_visible()
    values = picker.locator("option").evaluate_all("els => els.map(e => e.value)")
    assert values == ["", "vacant", "teardown", "house", "larger", "unclear"]


def test_a_filtered_lot_opens_to_the_same_label_and_its_colour_is_untouched(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots")
    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")

    page.locator("#occupancy-filter").select_option("vacant")
    page.get_by_role("button", name="Show").click()
    page.wait_for_url(re.compile(r"occupancy=vacant"))
    expect(page.locator("#occupancy-filter")).to_have_value("vacant")
    if page.get_by_text("No lots match.").count():
        pytest.skip("no occupancy build loaded on the copy in use")

    first = page.locator("#lot-table tbody tr").first.locator("td a").first
    href = first.get_attribute("href")
    assert href
    first.click()

    block = page.locator("#lot-occupancy")
    expect(block).to_be_visible()
    expect(block.locator("[data-occupancy]")).to_have_attribute("data-occupancy", "vacant")
    expect(block).to_contain_text("never changes the lot")
    # The colour block is still there and says what it said without the label.
    expect(page.locator("#lot-verdict")).to_be_visible()

    # The JSON report carries the same label, marked as never a colour.
    county_tlid = href.split("/flats/lots/", 1)[1].split("?", 1)[0]
    report = page.request.get(f"{base_url}/api/flats/lot/{county_tlid}").json()
    assert report["occupancy"]["label"] == "vacant"
    assert report["occupancy"]["never_a_colour"] is True
