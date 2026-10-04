"""The Unknowns page in a browser: every kind of flag and the colour rule.

**No approval is recorded here.** An approval is Steph's decision, written into
the rule files by the drain, and E2E runs against the live instance. The E2E
user is not the owner, so the page it sees is the read-only one -- which is
also what this checks: a non-owner gets no approve button.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_flags.py -m e2e -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


def test_the_sidebar_reaches_the_unknowns_page(logged_in_page: Page, base_url: str) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/rules")

    page.get_by_role("link", name="Unknowns").first.click()

    expect(page).to_have_url(f"{base_url}/flats/flags")
    expect(page.get_by_role("heading", name="Unknowns")).to_be_visible()


def test_the_page_lists_every_kind_and_the_colour_rule(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/flags")

    expect(page.locator("#flag-rules")).to_be_visible()
    expect(page.get_by_text("The colour rule")).to_be_visible()
    expect(page.locator("[data-flag]").first).to_be_visible()
    assert page.locator("[data-flag]").count() >= 60
    # Waiting kinds sit at the top while any are waiting.
    if int(page.locator("[data-count-proposed]").inner_text()) > 0:
        expect(page.locator("[data-section]").first).to_have_attribute(
            "data-section", "proposed"
        )


def test_a_non_owner_cannot_approve(logged_in_page: Page, base_url: str) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/flags")

    expect(page.get_by_text("read-only for you")).to_be_visible()
    expect(page.locator("[data-approve]")).to_have_count(0)
    expect(page.locator("[data-approve-rules]")).to_have_count(0)


def test_the_unknowns_page_reaches_the_question_queue(logged_in_page: Page, base_url: str) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/flags")

    page.locator("#questions-link").click()

    expect(page).to_have_url(f"{base_url}/flats/flags/questions")
    expect(page.get_by_role("heading", name="Questions")).to_be_visible()
    expect(page.locator('[data-section="waiting"]')).to_be_visible()
    expect(page.locator('[data-section="answered"]')).to_be_visible()
    # The E2E user is not the owner: no answer form.
    expect(page.locator("form[action$='/answer']")).to_have_count(0)
