"""The tree-mark lifecycle on a lot page, through the browser."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_marking_a_green_lot_turns_it_yellow_and_clearing_restores_green(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots?colour=green")

    if page.get_by_text("No completed run has been loaded").count():
        pytest.skip("no run loaded on this instance")
    if page.get_by_text("No lots match.").count():
        pytest.skip("no unmarked green lot on this instance")

    page.locator("#lot-table tbody tr").first.locator("td a").first.click()
    expect(page.locator("#trees-panel")).to_be_visible()
    note = "E2E tree mark for clearing"
    page.locator("#trees-mark-form textarea[name=note]").fill(note)
    page.locator("#trees-mark-form button[type=submit]").click()

    expect(page.locator("#trees-open-mark")).to_contain_text(note)
    expect(page.locator("#tree-mark-reason")).to_contain_text(note)
    expect(page.locator("#lot-verdict")).to_contain_text("yellow")

    page.locator("#trees-panel form[action$='/clear'] button[type=submit]").click()

    expect(page.locator("#trees-history")).to_contain_text(note)
    expect(page.locator("#trees-open-mark")).to_have_count(0)
    expect(page.locator("#lot-verdict")).to_contain_text("green")
