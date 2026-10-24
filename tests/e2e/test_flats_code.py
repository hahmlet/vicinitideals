"""The code library: shelf to city to section, a citation lit, a search followed."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

CITY = "or/clackamas/tualatin"


def test_reader_walks_from_the_shelf_to_a_cited_line(logged_in_page: Page) -> None:
    page = logged_in_page
    page.goto("/flats")
    page.locator("nav").get_by_role("link", name="Code library").click()
    expect(page.get_by_role("heading", name="Code library")).to_be_visible()

    page.locator(f'tr[data-shelf="{CITY}"]').get_by_role("link").click()
    expect(page.locator('[data-chapter="40-41.residential"]')).to_be_visible()

    page.locator('[data-chapter="40-41.residential"]').get_by_role("link", name="40.300", exact=True).click()
    expect(page.locator("[data-fingerprint]")).to_contain_text("Fingerprint")
    assert page.locator("tr.page").count() >= 1, "a section on a mapped book shows its pages"

    # A citation's fragment lights the line it names and brings it into view.
    read = page.locator("tr.read").first
    line = read.get_attribute("data-line")
    page.goto(f"{page.url.split('#')[0]}#L{line}")
    target = page.locator(f"#L{line}")
    expect(target).to_have_class("read hit")
    expect(target).to_be_in_viewport()
    expect(target.locator(".readers a").first).to_be_visible()

    # Clicking a line number makes that line the citation.
    page.locator("tr[data-line] .n a").nth(2).click()
    expect(page.locator("tr.hit")).to_have_count(1)
    assert page.url.endswith("#L3")


def test_search_reaches_the_line_it_found(logged_in_page: Page) -> None:
    page = logged_in_page
    page.goto(f"/flats/code/{CITY}")
    page.get_by_label("Search this code").fill("cul-de-sac")
    page.get_by_role("button", name="Search").click()
    hits = page.locator("[data-search-results] a")
    expect(hits.first).to_be_visible()
    href = hits.first.get_attribute("href") or ""
    hits.first.click()
    line = href.rsplit("#L", 1)[1]
    expect(page.locator(f"tr.hit#L{line}")).to_be_visible()
    expect(page.locator(f"#L{line} .t")).to_contain_text("cul-de-sac", ignore_case=True)


def test_nested_provisions_are_drawn_indented(logged_in_page: Page) -> None:
    page = logged_in_page
    page.goto(f"/flats/code/{CITY}/31/31.070.txt")
    two = page.locator("tr[data-line] .t", has_text="(2)").first
    a = page.locator("tr[data-line] .t", has_text="(a)").first
    left = lambda el: el.evaluate("e => e.getBoundingClientRect().left + parseFloat(getComputedStyle(e).paddingLeft) + parseFloat(getComputedStyle(e).textIndent)")  # noqa: E731
    assert left(a) > left(two) + 10
    expect(page.locator(".t.history")).to_contain_text("Ord.")
