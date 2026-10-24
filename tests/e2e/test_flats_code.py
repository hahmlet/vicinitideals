"""The code library: shelf to city to section, a citation lit, a search followed."""

from __future__ import annotations

import re

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

    # 40.300's cited lines are in Table 40-3, drawn as a table. A citation's
    # fragment lights the cell holding its line and brings it into view, and
    # opens the printed lines so the line itself is lit too.
    cell = page.locator(".code-table .read:has(.readers)").first
    expect(cell).to_be_visible()
    line = (cell.get_attribute("data-lines") or "").split()[0]
    page.goto(f"{page.url.split('#')[0]}#L{line}")
    lit = page.locator(f'.code-table [data-lines~="{line}"]').first
    expect(lit).to_have_class(re.compile(r"\bhit\b"))
    expect(lit).to_be_in_viewport()
    target = page.locator(f"#L{line}")
    expect(target).to_have_class("read hit")
    expect(target).to_be_visible()
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


def test_a_table_docling_misread_is_drawn_from_the_printed_rules(logged_in_page: Page) -> None:
    # Page 303: Docling's reading was refused; the table cut along the
    # printed rules passed the same checks and is drawn, its line lit.
    page = logged_in_page
    page.goto(f"/flats/code/{CITY}/40/40.300.txt#L100")
    expect(page.locator(".code-table")).to_have_count(4)
    block = page.locator('tr.table-block[data-table="98-116"]')
    expect(block.locator(".table-note")).to_contain_text("cut along the printed rules")
    expect(block.locator('[data-lines~="100"]').first).to_be_visible()
    expect(page.locator(".table-held")).to_have_count(0)


def test_a_footnote_mark_leads_to_its_note(logged_in_page: Page) -> None:
    page = logged_in_page
    page.goto(f"/flats/code/{CITY}/58/58.200.txt")
    mark = page.locator(".code-table sup.mark a").first
    expect(mark).to_be_visible()
    mark.click()
    note = page.locator("tr.hit")
    expect(note).to_have_count(1)
    expect(note.locator(".t")).to_contain_text("New drive-through")
    expect(note.locator(".note-back a").first).to_be_visible()
