"""The lot pages in a browser — the county run, lot by lot.

The run is loaded into the live database and these pages are the first thing
that reads it, so what is driven here is the two rules the pages exist to
keep: the verdict the screen can stand behind is printed first and the colour
it would take once the rules are signed beside it, never in its place; and a
lot on the list opens to its own page without losing the run it came from.

Nothing is recorded — the pages are read-only. Where no run has been loaded
the tests skip rather than invent one.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_lots.py -m e2e -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_the_list_counts_the_run_by_verdict_then_by_colour(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots")

    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")

    counts = page.locator("#lot-counts")
    expect(counts).to_be_visible()
    expect(counts.get_by_text("Verdict today")).to_be_visible()
    expect(counts.get_by_text("If signed as read")).to_be_visible()
    text = counts.inner_text()
    assert text.index("Verdict today") < text.index("If signed as read")
    # Four colour buttons, each carrying its count.
    for colour in ("green", "yellow", "unknown", "red"):
        expect(counts.get_by_role("link", name=colour, exact=False)).to_be_visible()


def test_a_green_lot_opens_to_its_page_with_the_verdict_first(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots?colour=green")

    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")
    rows = page.locator("#lot-table tbody tr")
    if page.get_by_text("No lots match.").count():
        pytest.skip("no green lot on this instance")

    first = rows.first.locator("td a").first
    where = first.inner_text()
    first.click()

    expect(page.locator("#lot-verdict")).to_be_visible()
    expect(page.locator("h2")).to_contain_text(where)
    head = page.locator("#lot-verdict").inner_text()
    assert head.index("Verdict today") < head.index("If signed as read")
    # The verdict is the screen's honest word; the colour that got the lot
    # onto the green list is beside it.
    assert "green" in head.split("If signed as read", 1)[1]
    expect(page.locator("#lot-facts")).to_be_visible()
    expect(page.locator("svg polygon").first).to_be_visible()


def test_the_city_filter_narrows_and_offers_that_city_s_zones(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots")

    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")

    page.select_option("select[name=jurisdiction]", "or/multnomah/portland")
    page.get_by_role("button", name="Show").click()

    expect(page.locator("select[name=zone]")).to_be_visible()
    expect(page.locator("select[name=zone] option[value='R5']")).to_have_count(1)
    cities = page.locator("#lot-table tbody tr td:nth-child(3)").all_inner_texts()
    assert cities and set(cities) == {"Portland"}


def test_the_county_copy_is_named_on_both_pages_and_a_warning_is_a_bar(
    logged_in_page: Page, base_url: str
) -> None:
    """The footer is always there, so 'no warning' is a statement; a red or
    amber bar, when shown, sits above the page's own heading."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots")

    footer = page.locator("#county-copy")
    expect(footer).to_be_visible()
    expect(footer).to_contain_text("County map copy:")
    for bar in ("#county-copy-red", "#county-copy-amber"):
        if page.locator(bar).count():
            expect(page.locator(bar)).to_be_visible()
            assert page.locator(bar).bounding_box()["y"] < page.locator("h2").first.bounding_box()["y"]

    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")
    page.locator("#lot-table tbody tr td a").first.click()
    expect(page.locator("#lot-verdict")).to_be_visible()
    expect(page.locator("#county-copy")).to_contain_text("County map copy:")


def test_a_tight_fit_is_a_filter_on_the_list_and_a_row_on_the_lot_page(
    logged_in_page: Page, base_url: str
) -> None:
    """Steph 2026-09-25: a fit within 6 inches either way is green with a
    flag the acquisition review sees -- a box on the list that shows only
    those lots, and a line on the lot page that says the survey decides."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots?colour=green")

    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")
    page.get_by_label("Only tight fits").check()
    page.get_by_role("button", name="Show").click()
    expect(page.get_by_label("Only tight fits")).to_be_checked()
    if page.get_by_text("No lots match.").count():
        pytest.skip("no tight fit in this run")

    row = page.locator("#lot-table tbody tr").first
    expect(row.get_by_text("tight fit").first).to_be_visible()
    row.locator("td a").first.click()
    expect(page.locator("#lot-verdict")).to_be_visible()
    flagged = page.locator("tr[id^='tight-']").first
    expect(flagged).to_be_visible()
    expect(flagged).to_contain_text("survey")
