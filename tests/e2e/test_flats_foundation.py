"""The foundation model (FOLLOWUPS 209) in a browser: a GREEN lot opens to a
"Foundation (not a screen check)" panel marked as having no effect on the
colour, with a cost range per method, the steps at the doors, the standing note
and a fold of per-door and cost-line tables; the colour block is untouched; and
the JSON report carries the same block with money as strings and the
"if a mapped building had a basement" figure kept out of the total.

Read-only. Skips where no run is loaded, or the first green lot has no measured
record on the copy in use (``scripts/flats_foundation.py load``).

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_foundation.py -m e2e -v
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_a_green_lot_shows_its_foundation_beside_its_colour(logged_in_page: Page, base_url: str) -> None:
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

    panel = page.locator("#lot-foundation")
    expect(panel).to_be_visible()
    expect(panel).to_contain_text("Foundation (not a screen check)")
    expect(panel.locator("[data-foundation-no-colour]")).to_contain_text("No effect on the colour")
    status = panel.get_attribute("data-foundation-status")
    if status == "not_measured":
        pytest.skip("no foundation record loaded for this lot on the copy in use")
    assert status in ("priced", "needs_remeasuring")
    # The colour block is still there.
    expect(page.locator("#lot-verdict")).to_be_visible()

    county_tlid = href.split("/flats/lots/", 1)[1].split("?", 1)[0]
    report = page.request.get(f"{base_url}/api/flats/lot/{county_tlid}").json()
    f = report["foundation"]
    assert f["status"] == status and f["never_a_colour"] is True and f["settings_version"]

    if status == "needs_remeasuring":
        expect(panel.locator("[data-foundation-remeasure]")).to_contain_text("Needs re-measuring")
        assert "$" not in panel.inner_text()
        return

    methods = panel.locator("[data-foundation-method]")
    assert methods.count() >= 1
    expect(methods.first).to_contain_text("$")
    expect(panel.locator("[data-foundation-steps]").first).to_contain_text("Steps at the 8 doors:")
    expect(panel.locator("[data-foundation-note]")).to_contain_text("not a budget")
    expect(panel.locator("[data-foundation-old]")).to_contain_text("Mapped buildings under the pod")

    # The fold opens to the per-door and cost-line tables.
    fold = panel.locator("[data-foundation-detail]")
    fold.locator("summary").click()
    expect(fold.locator("[data-foundation-doors]").first).to_be_visible()
    expect(fold.locator("[data-foundation-cost-lines]").first).to_be_visible()

    # Money is a string in the report; the old-building figure is never in a total.
    assert [m["method"] for m in f["methods"]] == [
        methods.nth(i).get_attribute("data-foundation-method") for i in range(methods.count())
    ]
    for m in f["methods"]:
        assert isinstance(m["cost_low"], str) and isinstance(m["cost_high"], str)
        assert Decimal(m["cost_low"]) <= Decimal(m["cost_high"])
    assert f["old_buildings"]["in_total"] is False
