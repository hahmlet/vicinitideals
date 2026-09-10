"""Reading queues — the four screens over the uncited ledger, in a browser.

What these check is the thing the whole surface exists for: a reviewer opens
one queue, is told what they are doing and how many of them there are, and
moves through cards without the page reloading or the filters resetting. If
the mode line goes missing or a card swap turns into a navigation, the queue
is back to being a list.

Deliberately **no ruling is recorded here.** A ruling is an attributable human
decision spliced into the corpus, and E2E runs against the live instance --
inventing one would put a reading nobody did on the record. The skip path
exercises the same form, the same HTMX swap and the same filter round-trip,
and records nothing, so that is what is driven.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_reading.py -m e2e -v
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import wait_for_htmx

pytestmark = pytest.mark.e2e

QUEUES = ("missed", "condition", "chapter", "nofield")


def _card_heading(page: Page) -> str:
    """Which section is on screen, as the reviewer sees it named."""
    return page.locator("#reading-card h3").inner_text().strip()


def _has_card(page: Page) -> bool:
    """Is there a card on screen at all, or has the queue run out?

    A queue emptying is the outcome the whole surface is for, so no test here
    may treat it as a failure. It is asked structurally -- the empty state
    renders no heading and no form -- rather than by matching its wording,
    which is prose and will be rewritten.
    """
    return page.locator("#reading-card h3").count() > 0


def test_the_landing_page_lets_you_pick_the_day_s_mode(
    logged_in_page: Page, base_url: str
) -> None:
    """The first decision of the day is not about a card. It is 'what kind of
    reading am I doing', and it wants four names and four sizes."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/reading")

    for title in ("Missed standards", "Conditions", "Unopened chapters", "No field for it"):
        expect(page.get_by_text(title, exact=False).first).to_be_visible()

    # And each one says how much work it is, or picking is guessing.
    body = page.locator("body").inner_text()
    assert len(re.findall(r"\d[\d,]*\s+lines?", body)) >= 4


@pytest.mark.parametrize("queue", QUEUES)
def test_a_queue_opens_on_a_card_under_a_mode_line(
    logged_in_page: Page, base_url: str, queue: str
) -> None:
    """"I am doing X today and there are Y of them" has to be readable before
    anything is clicked."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/reading/{queue}")

    expect(page.get_by_text("To check", exact=False).first).to_be_visible()
    expect(page.locator("#reading-card")).to_be_visible()
    expect(page.locator("text=lines behind them").first).to_be_visible()


@pytest.mark.parametrize("queue", QUEUES)
def test_each_queue_offers_only_the_answers_to_its_own_question(
    logged_in_page: Page, base_url: str, queue: str
) -> None:
    """The keying of the vocabulary is the design. A screen showing every
    outcome anybody ever needed is a screen where the reviewer re-reads the
    vocabulary before every card."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/reading/{queue}")

    if not _has_card(page):
        pytest.skip(f"the {queue} queue is fully ruled — no card to offer answers on")

    labels = page.locator("#reading-card input[name='outcome']")
    count = labels.count()
    assert count, "a card with no answers is not a decision"
    # Whatever the queue, one short row -- never the union of all four.
    assert count <= 5


def test_skipping_swaps_the_next_card_in_without_a_page_load(
    logged_in_page: Page, base_url: str
) -> None:
    """The card is swapped in place. A navigation here would lose the filters
    and cost a mental recalibration on every card."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/reading/missed")
    first = _card_heading(page)
    url_before = page.url

    page.get_by_role("button", name=re.compile("Can.t tell yet")).click()
    wait_for_htmx(page)

    assert page.url == url_before, "the queue does not navigate"
    # What proves the swap is that the count of skips came back changed, and it
    # is asserted on rather than on a heading because a queue worked down to its
    # last card is this project succeeding, not a regression: skipping the only
    # card leaves the empty state, which is a correct answer and carries no h3.
    # Either shape says the same thing, and neither can be true of the old DOM
    # (before the click the card prints its remaining count with no skip
    # clause), so a slow swap cannot pass this by accident.
    expect(page.locator("#reading-card")).to_contain_text(
        re.compile(r"1 skipped|Skipped past 1", re.I)
    )
    if _has_card(page):
        assert _card_heading(page) != first, "it moved on"


def test_a_filter_survives_the_next_card(
    logged_in_page: Page, base_url: str
) -> None:
    """Filters are how a reviewer scopes a session -- one city, one standard.
    Losing them on the first ruling makes the whole queue unworkable."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/reading/missed?layer=or/multnomah/gresham")

    expect(page.locator("#reading-card")).to_be_visible()
    if not _has_card(page):
        pytest.skip("Gresham's missed queue is empty — nothing to carry")

    page.get_by_role("button", name=re.compile("Can.t tell yet")).click()
    wait_for_htmx(page)

    # The filter has to survive on the URL whether or not a card is left, and
    # that half is checked unconditionally -- an emptied queue is not licence
    # for the screen to drop the scope the reviewer chose.
    assert "layer=or/multnomah/gresham" in page.url, "the filter fell off the URL"
    # The other half rides on the card's own form, so it needs a card. One card
    # left is a real corpus state, not a broken filter.
    if not _has_card(page):
        pytest.skip("Gresham's missed queue held one card — nothing left to carry it on")

    held = page.locator("#reading-card input[name='layer']").input_value()
    assert held == "or/multnomah/gresham"


def test_a_queue_nobody_named_goes_back_to_the_menu(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/reading/everything")

    assert page.url.rstrip("/").endswith("/flats/reading")


# --- where the day's reading goes -------------------------------------------


def test_the_hand_off_is_reachable_and_carries_the_work_ordered(
    logged_in_page: Page, base_url: str
) -> None:
    """A day of reading is only worth doing if it becomes a day of encoding.

    Five of the answers a card can take are not decisions, they are orders --
    encode this, open that chapter, we need a field -- and each was recorded in
    the queue that asked the question. The hand-off is where they are collected
    into something an encoder can pick up, so it has to be findable without
    knowing the URL.
    """
    page = logged_in_page
    page.goto(f"{base_url}/flats/reading")

    page.get_by_role("link", name="Hand-off").first.click()
    page.wait_for_load_state("domcontentloaded")

    assert "/flats/feedback" in page.url
    expect(page.get_by_role("heading", name="Work ordered")).to_be_visible()
    # Both hand-offs named on one page, each copyable on its own. The problems
    # block itself is only drawn when something is open, so what is pinned here
    # is the framing rather than the presence of today's items.
    expect(
        page.get_by_text("Everything a day of review produced", exact=False).first
    ).to_be_visible()
