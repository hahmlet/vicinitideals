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

import re

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


def test_the_unknowns_page_reaches_the_work_queue_and_the_nightly_check(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/flags")

    page.locator("#queue-link").click()
    expect(page).to_have_url(f"{base_url}/flats/flags/queue")
    expect(page.get_by_role("heading", name="Work queue")).to_be_visible()

    page.goto(f"{base_url}/flats/flags")
    page.locator("#report-link").click()
    expect(page).to_have_url(f"{base_url}/flats/flags/report")
    expect(page.get_by_role("heading", name="Nightly check")).to_be_visible()


def test_the_nightly_check_shows_the_room_and_the_pod_height(logged_in_page: Page, base_url: str) -> None:
    """FOLLOWUPS 37(ii): beside the pod width, the report says how close the
    green lots come to each limit and tries the pod taller and lower. A
    report written before the room was kept shows each section empty, never
    an error."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/flags/report")

    expect(page.get_by_role("heading", name="Nightly check")).to_be_visible()
    if page.locator("#report-none").count():
        pytest.skip("no nightly check has run on this instance yet")
    expect(page.get_by_role("heading", name="Room to spare on green lots")).to_be_visible()
    expect(page.get_by_role("heading", name="Pod width")).to_be_visible()
    expect(page.get_by_role("heading", name="Pod height")).to_be_visible()
    rows = page.locator("tr.room-row")
    if rows.count():
        expect(rows.first).to_have_attribute("data-within-10", re.compile(r"^\d+$"))
