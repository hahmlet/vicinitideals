"""Fetch triage in a browser — the queue that decides what to go and read.

Every other ledger in this project counts things we have. This one counts the
books we do not, and it has always ranked them by what they are written
*beside*: a reference in the margin of a setback table is worth the lots in
that table. That is one of the two ways a chapter reaches our numbers. The
other is being handed a *word* every one of those numbers is measured in,
which a code says once, in prose, nowhere near a value — and a chapter reached
that way stands beside nothing, so every figure the card printed for it was
zero. Portland's Chapter 33.930, Measurements, settles how height is measured
on 95% of the city and sat 69th of 75.

So what is driven here is that the top of the queue explains itself. A chapter
that jumps to first place for a reason nobody can see on the card is worse than
one sitting quietly at the bottom.

**No ruling is recorded.** A ruling is an attributable human decision spliced
into the corpus and this runs against the live instance; inventing one would
put a reading nobody did on the record.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_triage.py -m e2e -v
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

#: Where a word-reached chapter still leads the queue. Portland's 33.930 was
#: the finding, and fetching it is what took Portland off this list — a queue
#: that empties is the point of it. Unincorporated Multnomah runs on the same
#: Title 33 and has not been fetched: 33.930 is still first there, handed
#: *building height* on 2,480 lots and written beside nothing.
HANDED = "or/multnomah/_unincorporated"

#: A city the screen does not cover. Lake Oswego is switched off -- an
#: owner decision about the Mountain Park PUD -- and its chapters sit
#: fourth and fifth in the whole corpus queue on lots nothing will score.
UNSCREENED = "or/clackamas/lake-oswego"


def test_the_queue_opens_on_one_card_under_a_mode_line(
    logged_in_page: Page, base_url: str
) -> None:
    """One reference, one decision. A screen that opened on a list would be
    the ledger this queue was built to stop being."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/triage")

    expect(page.locator("#triage-card")).to_be_visible()
    expect(page.locator("#triage-card h3")).to_be_visible()


def test_the_chapter_at_the_top_says_what_put_it_there(
    logged_in_page: Page, base_url: str
) -> None:
    """The card carrying the word route has to name the words and the lots.

    Unincorporated Multnomah leads with 33.930, which is written beside no
    standard at all, so the rest of the card reads "no standards written near
    it" and every count on it is zero. Without this block the first thing a
    reviewer sees is a chapter at the head of the queue with nothing on it to
    justify being there.
    """
    page = logged_in_page
    page.goto(f"{base_url}/flats/triage?layer={HANDED}")

    card = page.locator("#triage-card")
    expect(card).to_be_visible()
    if not card.get_by_text("Words this code hands it").count():
        pytest.skip("no chapter here is reached through a word on this card")

    expect(card.get_by_text("Words this code hands it")).to_be_visible()
    expect(card.get_by_text("settled here", exact=False)).to_be_visible()
    expect(card.get_by_text("hold a standard measured in", exact=False)).to_be_visible()


def test_a_card_for_land_nobody_screens_says_so_before_the_evidence(
    logged_in_page: Page, base_url: str
) -> None:
    """A fifth of this queue is chapters for cities that are switched off.

    They are in it deliberately -- the rank is on lots at stake and hiding
    them would mean re-ranking by something nobody can see -- and the terminal
    has marked them since the queue was built. The screen did not, so nine of
    the first twenty-five cards read as ordinary work while fetching them
    changes no verdict at all.
    """
    page = logged_in_page
    page.goto(f"{base_url}/flats/triage?layer={UNSCREENED}")

    card = page.locator("#triage-card")
    expect(card).to_be_visible()
    expect(card.get_by_text("is not screened", exact=False).first).to_be_visible()
    expect(
        card.get_by_text("Nothing here is scored against a lot", exact=False).first
    ).to_be_visible()


def test_a_layer_nobody_has_is_an_empty_queue_and_not_an_error(
    logged_in_page: Page, base_url: str
) -> None:
    """The filter is a query parameter, so it is whatever the browser sends."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/triage?layer=or/clackamas/lake-oswead")

    expect(page.locator("#triage-card")).to_contain_text("Nothing left in this queue")
