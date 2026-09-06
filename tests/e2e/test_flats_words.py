"""The word review — the queue underneath signing, in a browser.

Signing asks whether a number matches the sentence it was taken from. This asks
the question beneath it: whether the sentence measures what we think it
measures. Four codes in this corpus give four incompatible tests for *corner
lot* and seven subtract seven different lists from a *net acre*, so a number
read perfectly can still be the wrong number — and finding that out after three
hundred signatures means signing some of them again.

Deliberately **no ruling is recorded here.** A ruling is an attributable human
decision spliced into the corpus, and E2E runs against the live instance —
inventing one would put a reading nobody did on the record. The skip path
exercises the same form, the same HTMX swap and the same filter round-trip, and
records nothing, so that is what is driven.

Run:
    $env:E2E_BASE_URL="https://viciniti.deals"
    uv run pytest tests/e2e/test_flats_words.py -m e2e -v
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.helpers import wait_for_htmx

pytestmark = pytest.mark.e2e

STANDINGS = ("unread", "silent", "defined")


def _card_heading(page: Page) -> str:
    """Which word is on screen, as the reviewer sees it named."""
    return page.locator("#word-card h3").inner_text().strip()


def test_the_landing_page_lets_you_pick_the_day_s_standing(
    logged_in_page: Page, base_url: str
) -> None:
    """Three standings, and they are three different jobs: go and fetch a book
    nobody has opened, decide what a silent code lets us assume, compare a
    definition to how we measure."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/words")

    for title in ("No glossary read", "The code is quiet", "Defined here"):
        expect(page.get_by_text(title, exact=False).first).to_be_visible()

    # And each says what rests on it, or picking a standing is guessing.
    expect(page.get_by_text("resting on them", exact=False).first).to_be_visible()


@pytest.mark.parametrize("standing", STANDINGS)
def test_a_standing_opens_under_a_mode_line(
    logged_in_page: Page, base_url: str, standing: str
) -> None:
    """"I am doing X today and there are Y of them" has to be readable before
    anything is clicked. An empty standing is a real state — the queue still
    has to say which one it is."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/words/{standing}")

    expect(page.get_by_text("To check", exact=False).first).to_be_visible()
    expect(page.locator("#word-card")).to_be_visible()
    expect(page.get_by_text("resting on them", exact=False).first).to_be_visible()


def test_a_card_says_what_it_costs_to_get_the_word_wrong(
    logged_in_page: Page, base_url: str
) -> None:
    """The reason the card is in front of anybody is not that the word is
    interesting. It is that these numbers are measured in it."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/words/defined")

    card = page.locator("#word-card")
    if "Nothing left in this queue" in card.inner_text():
        pytest.skip("the defined queue is empty")

    expect(page.get_by_text("Our numbers measured in this word").first).to_be_visible()
    expect(page.get_by_text("measured in it", exact=False).first).to_be_visible()



def test_a_silent_word_shows_where_the_code_sends_the_reader(
    logged_in_page: Page, base_url: str
) -> None:
    """A silence is not the end of the answer. Portland's definitions chapter
    runs to 296 entries and defines neither *lot width* nor *building height*;
    its own text points at Chapter 33.930, Measurements, for both. The card
    shows that sentence, so the ruling is one click and a chapter number rather
    than a hunt through ten documents."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/words/silent?layer=or/multnomah/portland")

    card = page.locator("#word-card")
    if "Nothing left in this queue" in card.inner_text():
        pytest.skip("Portland's silent words have all been ruled")

    expect(page.get_by_text("How this code writes it").first).to_be_visible()

@pytest.mark.parametrize("standing", ("silent", "defined"))
def test_each_standing_offers_only_the_answers_to_its_own_question(
    logged_in_page: Page, base_url: str, standing: str
) -> None:
    """"Means what we assumed" is not an answer anybody can give about a
    glossary nobody has opened."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/words/{standing}")

    card = page.locator("#word-card")
    if "Nothing left in this queue" in card.inner_text():
        pytest.skip(f"the {standing} queue is empty")

    answers = card.locator("input[name='outcome']")
    count = answers.count()
    assert count, "a card with no answers is not a decision"
    assert count <= 5, "one short row, never the union of all three standings"


def test_skipping_swaps_the_next_word_in_without_a_page_load(
    logged_in_page: Page, base_url: str
) -> None:
    """The card is swapped in place. A navigation here would lose the filters
    and cost a mental recalibration on every card."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/words/defined")

    card = page.locator("#word-card")
    if "Nothing left in this queue" in card.inner_text():
        pytest.skip("the defined queue is empty")

    first = _card_heading(page)
    url_before = page.url

    page.get_by_role("button", name=re.compile("Can.t tell yet")).click()
    wait_for_htmx(page)

    assert page.url == url_before, "the queue does not navigate"
    assert _card_heading(page) != first, "it moved on"
    expect(page.get_by_text("1 skipped", exact=False).first).to_be_visible()


def test_a_filter_survives_the_next_word(
    logged_in_page: Page, base_url: str
) -> None:
    """Filters are how a reviewer scopes a session — one city at a time is the
    only way this queue makes sense, because the whole finding is that the same
    word means different things in different books."""
    page = logged_in_page
    page.goto(f"{base_url}/flats/words/defined?layer=or/multnomah/gresham")

    card = page.locator("#word-card")
    if "Nothing left in this queue" in card.inner_text():
        pytest.skip("Gresham's defined queue is empty — nothing to carry")

    page.get_by_role("button", name=re.compile("Can.t tell yet")).click()
    wait_for_htmx(page)

    held = page.locator("#word-card input[name='layer']").input_value()
    assert held == "or/multnomah/gresham"


def test_a_standing_nobody_named_goes_back_to_the_menu(
    logged_in_page: Page, base_url: str
) -> None:
    page = logged_in_page
    page.goto(f"{base_url}/flats/words/everything")

    assert page.url.rstrip("/").endswith("/flats/words")


def test_every_review_screen_is_one_click_from_anywhere(
    logged_in_page: Page, base_url: str
) -> None:
    """A queue nobody can navigate to is not shipped.

    Three of these lived for weeks at URLs typed by hand — fetch triage, the
    gaps ledger and this queue were reachable only from inside another page,
    which for a reviewer who lands on the dashboard is the same as not
    existing.
    """
    page = logged_in_page
    page.goto(f"{base_url}/flats")

    for name in ("Words", "Reading", "Fetch triage", "Not encoded", "Hand-off"):
        expect(page.locator(".sidebar").get_by_role("link", name=name).first).to_be_visible()

    page.locator(".sidebar").get_by_role("link", name="Words").first.click()
    page.wait_for_load_state("domcontentloaded")
    assert page.url.rstrip("/").endswith("/flats/words")
