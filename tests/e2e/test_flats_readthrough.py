"""The document read-through keeps local drafts and submits a complete review."""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError

pytestmark = pytest.mark.e2e


def test_readthrough_keyboard_draft_and_submission(logged_in_page: Page) -> None:
    page = logged_in_page
    page.goto("/flats/check/readthrough")
    hrefs = [
        row.get_by_role("link", name="Read document").get_attribute("href")
        for row in page.locator("tr[data-document]").all()
        if int(row.get_attribute("data-page-count") or "0") >= 2
    ]
    chosen = None
    # The shelf is alphabetical, and its head is amendments and street chapters
    # with no encoded rule on them (2026-10-30: the first five all had none, so
    # the test skipped). Walk far enough down to reach a zone chapter. The first
    # page may build the sheet caches cold, hence the long first wait.
    for href in hrefs[:40]:
        page.goto(href)
        page.locator("[data-read-page]").first.wait_for(timeout=90_000)
        try:
            page.wait_for_function(
                "() => { const img = document.querySelector('.readthrough-image img'); return img && img.complete && img.naturalWidth > 0; }",
                timeout=5000,
            )
        except PlaywrightTimeoutError:
            continue
        if page.locator(".check-box-encoded").count():
            chosen = page
            break
    if not hrefs:
        pytest.skip("The live corpus has no mapped multi-page printed document.")

    if chosen is None:
        pytest.skip("The live corpus has no mapped, multi-page printed document with encoded rules.")

    sections = page.locator("[data-read-page]")
    first = page.locator("#current-page").inner_text()
    page.locator("#current-page").click()
    page.keyboard.press("ArrowDown")
    page.wait_for_function(
        "(initial) => document.querySelector('#current-page').textContent !== initial",
        arg=first,
    )
    assert sections.count() >= 2
    page.locator("#comment-text").fill("Check whether the next subsection has a missing condition.")
    page.get_by_role("button", name="Add comment").click()
    assert "missing condition" in page.locator("#draft-comments").inner_text()
    saved = page.evaluate(
        "() => localStorage.getItem(document.querySelector('#readthrough-form').dataset.storageKey)"
    )
    assert json.loads(saved)["comments"][0]["text"].startswith("Check whether")

    sections.last.scroll_into_view_if_needed()
    page.locator('[name="read_confirmed"]').check()
    page.get_by_role("button", name="Submit read-through").click()
    page.locator("[data-submitted]").wait_for()
    assert page.evaluate(
        "() => localStorage.getItem(document.querySelector('#readthrough-form').dataset.storageKey)"
    ) is None
