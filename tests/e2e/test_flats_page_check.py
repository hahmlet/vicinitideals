"""The page check — an encoded number asked of the printed page, in a browser.

Signing compares a number with our text copy of the code, where a number read
off the wrong row or column of a table looks perfectly right. The page check
shows the page as the city prints it, with a box on the cell, and asks whether
it says what we have.

As with the word review, **no answer is recorded here**: an answer is an
attributable human reading and E2E runs against the live instance. Skip drives
the same form and the same HTMX swap and records nothing.

What matters most is that the page image actually draws. A card whose image is
broken still renders its question, and a reviewer answering it would be
answering from the text copy again -- the thing this exists to get away from.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_page_check.py -m e2e -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import wait_for_htmx

pytestmark = pytest.mark.e2e

LAYER = "or/multnomah/gresham"


def _card_key(page: Page) -> tuple[str, str, str, str]:
    card = page.locator("#check-card")
    return tuple(
        card.locator(f"input[name='{name}']").input_value()
        for name in ("zone", "field", "when", "question")
    )


def test_the_index_lists_jurisdictions_and_what_cannot_be_checked_yet(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/check")

    expect(page.get_by_role("heading", name="Page check")).to_be_visible()
    expect(page.get_by_text("Numbers with a printed page")).to_be_visible()
    expect(page.get_by_text("Web-published").first).to_be_visible()
    expect(page.locator(f"a[href='/flats/check/{LAYER}']")).to_be_visible()


def test_the_sidebar_reaches_the_page_check(logged_in_page: Page, base_url: str) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/rules")

    page.get_by_role("link", name="Page check").first.click()

    expect(page).to_have_url(f"{base_url}/flats/check")


def test_a_card_draws_the_printed_page_with_a_box_on_it(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/check/{LAYER}")

    expect(page.get_by_text("Does the page say", exact=False)).to_be_visible()
    image = page.locator(".check-sheet img").first
    expect(image).to_be_visible(timeout=60_000)
    # Rendering a page the server has not drawn before can mean fetching the
    # book first; wait for the image itself, not just its tag.
    page.wait_for_function(
        "img => img.complete && img.naturalWidth > 0", arg=image.element_handle(), timeout=90_000
    )
    expect(page.locator(".check-sheet .check-box").first).to_be_attached()


def test_skip_moves_to_another_question_without_answering(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/check/{LAYER}")
    before = _card_key(page)
    skipped = page.locator("#check-card input[name='skipped']").input_value()

    page.get_by_role("button", name="Skip").click()
    wait_for_htmx(page)

    # Assert on something the old card cannot show: the skip count moved on.
    expect(page.locator("#check-card input[name='skipped']")).to_have_value(str(int(skipped) + 1))
    assert _card_key(page) != before
