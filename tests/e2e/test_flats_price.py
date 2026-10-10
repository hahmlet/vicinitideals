"""Price per home in a browser: the Lots-page filter and the lot-page label.

The price is a label, never a screen: nothing here changes a lot's colour.
Nothing is recorded -- the pages are read-only. Where no run is loaded the
tests skip.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_price.py -m e2e -v
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

_DOLLARS = re.compile(r"\$([\d,]+)")


def _skip_if_empty(page: Page) -> None:
    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")
    if page.get_by_text("No lots match.").count():
        pytest.skip("no lots match on this instance")


def _per_home(cell_text: str) -> int | None:
    found = _DOLLARS.search(cell_text)
    return int(found.group(1).replace(",", "")) if found else None


def test_every_lot_row_carries_a_price_per_home_and_the_filter_defaults_to_30000(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots?colour=green")
    _skip_if_empty(page)

    expect(page.get_by_role("columnheader", name="Price per home")).to_be_visible()
    expect(page.locator("#ppu-max")).to_have_value("30000")
    expect(page.locator("#ppu-on")).not_to_be_checked()
    cells = page.locator("#lot-table tbody tr td.ppu-cell")
    assert cells.count() == page.locator("#lot-table tbody tr").count()
    for i in range(cells.count()):
        text = cells.nth(i).inner_text()
        assert _per_home(text) is not None or "no price" in text or "under 1 pod" in text


def test_the_filter_keeps_only_lots_at_or_under_the_ceiling_and_never_hides_no_price(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots?colour=green")
    _skip_if_empty(page)

    page.locator("#ppu-on").check()
    page.locator("#ppu-max").fill("30000")
    page.get_by_role("button", name="Show").click()

    expect(page.locator("#ppu-on")).to_be_checked()
    _skip_if_empty(page)
    cells = page.locator("#lot-table tbody tr td.ppu-cell")
    for i in range(cells.count()):
        got = _per_home(cells.nth(i).inner_text())
        assert got is None or got <= 30_000, cells.nth(i).inner_text()

    # A lower ceiling can only narrow the answer; the colour filter is still green.
    page.locator("#ppu-max").fill("15000")
    page.get_by_role("button", name="Show").click()
    expect(page.locator("#ppu-max")).to_have_value("15000")
    if not page.get_by_text("No lots match.").count():
        cells = page.locator("#lot-table tbody tr td.ppu-cell")
        for i in range(cells.count()):
            got = _per_home(cells.nth(i).inner_text())
            assert got is None or got <= 15_000, cells.nth(i).inner_text()
        badges = page.locator("#lot-table tbody tr td .badge-green")
        assert badges.count() >= 1


def test_a_priced_lot_opens_to_a_label_with_its_source_and_as_of(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots?colour=green&ppu=1&ppu_max=30000&sort=ppu")
    _skip_if_empty(page)

    cells = page.locator("#lot-table tbody tr td.ppu-cell")
    target = None
    for i in range(cells.count()):
        if _per_home(cells.nth(i).inner_text()) is not None:
            target = i
            break
    if target is None:
        pytest.skip("no priced green lot at or under the default on this instance")
    shown = _per_home(cells.nth(target).inner_text())
    page.locator("#lot-table tbody tr").nth(target).locator("td a").first.click()

    block = page.locator("#lot-price")
    expect(block).to_be_visible()
    expect(page.locator("#lot-price-text")).to_contain_text(f"${shown:,}")
    expect(page.locator("#lot-price-source")).to_contain_text("County real market value")
    expect(page.locator("#lot-price-asof")).to_contain_text("RLIS")
    # The colour the lot has is still on the page, beside the verdict.
    expect(page.locator("#lot-verdict")).to_contain_text("green")
