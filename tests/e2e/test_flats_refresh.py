"""The County copy page in a browser — every dated copy of the county map.

The page is where a person reads what stands between a refreshed copy and the
site showing it. What is driven here is that it reaches the browser from the
menu, names the copy in use, and shows a waiting copy its gate whole — nine
rows, each marked ok or not — with the promote form that Steph's rule
governs. **Nothing is submitted**: promoting a copy on the live site is a
person's act, and the tests never click it.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_refresh.py -m e2e -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

GATE_ROWS = 9


def test_the_menu_reaches_the_page_and_the_copy_in_use_is_named(logged_in_page: Page, base_url: str) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/lots")

    page.get_by_role("link", name="County copy").click()
    page.wait_for_url(f"{base_url}/flats/refresh")

    expect(page.get_by_role("heading", name="The county map copy")).to_be_visible()
    if page.get_by_text("No county map copy has been registered.").count():
        pytest.skip("no county copy registered on this instance")
    # Exactly one copy is in use, and its card says so.
    current = page.locator(".card .badge", has_text="current")
    expect(current).to_have_count(1)
    # The footer under the banner names the same copy; both come from rows.
    expect(page.locator("#county-copy")).to_be_visible()


def test_a_waiting_copy_shows_its_whole_gate_and_is_not_promoted_here(logged_in_page: Page, base_url: str) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/refresh")

    candidates = page.locator(".card", has=page.locator(".badge", has_text="candidate"))
    if not candidates.count():
        pytest.skip("no candidate copy on this instance")

    card = candidates.first
    gate = card.locator("table[id^='gate-'] tbody tr")
    expect(gate).to_have_count(GATE_ROWS)
    tripped = card.locator("table[id^='gate-'] tbody tr[data-tripped='yes']").count()
    form = card.locator("form[id^='promote-']")
    expect(form).to_be_visible()
    if form.get_by_text("Nothing has been loaded from this copy yet").count():
        # Registered, not yet loaded: no button of any kind until the loader runs.
        expect(form.get_by_role("button")).to_have_count(0)
    elif tripped:
        # Steph's rule: a warned gate waits for a person and a written reason.
        expect(form.get_by_text("Not clean:")).to_be_visible()
        expect(form.locator("textarea[name='override']")).to_be_visible()
        expect(form.get_by_role("button", name="Promote over the warning")).to_be_visible()
    else:
        expect(form.get_by_role("button", name="Promote", exact=False)).to_be_visible()
