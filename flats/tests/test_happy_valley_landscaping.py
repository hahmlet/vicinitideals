"""The loudest cross-reference in the corpus was about somebody else's site.

Every residential table in Happy Valley's Chapter 16.22 prints the same row
against every district: "Shared outdoor recreation areas | 400 sq. ft./unit
provided in accordance with Section 16.42.080". Four units at 400 is 1,600
square feet of recreation tract, on lots that are often 7,000 — a standard that
would bind harder than anything else in the file. Eleven mentions, eight of
them standing beside a number this screen already uses, which made 16.42.080
the top of the whole 1,465-reference queue.

The chapter was unfetched, so nobody had read the first sentence of it:
"The standards of this section apply to subdivisions of 30 or more units."

That is the encoding worth having. Not a rule — the absence of one, established
rather than assumed, which is the difference between a GREEN somebody may act
on and a GREEN nobody checked.

Reading it surfaced the standard in the same chapter that *does* reach a
fourplex, and had been missed by the same silence. 16.42.030(B)(1) asks 20
percent of the lot in landscaping, naming "fourplexes" in the row, and
16.42.020's exemption list — which excuses quadplexes from six of that
section's subsections — does not include (B). Nine zones now carry it.

And the field it is encoded in was, until this pass, read by nothing. Portland,
Fairview and Wood Village had all encoded min_landscaped_pct; screen.py never
looked at it. Portland asks 30 percent in RM1. That test lives next door in
test_screen.py; this file is about the city that made it visible.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

HAPPY_VALLEY = "or/clackamas/happy-valley"

#: The zones that state the standard themselves. R20CC is deliberately absent:
#: it is not a zone in LDC 16.22 at all and carries R-20 by reference.
ZONES = ("R40", "R20", "R15", "R10", "R8.5", "R7", "R5", "MURS")


@pytest.fixture(scope="module")
def happy_valley() -> Layer:
    return load_rules()[HAPPY_VALLEY]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


# -- the standard that does reach a fourplex --------------------------------


def test_every_zone_is_held_to_the_citywide_landscaping_share(
    happy_valley: Layer,
) -> None:
    """One sentence in a design-standards chapter, nine zones deep.

    Nothing about this is in the district tables, which is why an encoding
    pass that reads 16.22 and stops finds no trace of it."""
    for zone in ZONES:
        held = happy_valley.zones[zone].values.get("min_landscaped_pct")
        assert held is not None, f"{zone} states no landscaping share"
        assert held.value == 20, zone


def test_the_zone_that_is_not_a_zone_inherits_it_with_the_rest(
    happy_valley: Layer,
) -> None:
    """R20CC carries R-20 whole rather than a hand copy of six numbers, so a
    standard added to R-20 arrives here without anybody remembering to."""
    like = happy_valley.zones["R20CC"].like
    assert like is not None
    assert like.zone == "R20"
    assert happy_valley.zones["R20CC"].values == {}


def test_the_row_names_this_building_and_the_quote_shows_it(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    """16.42.030(B) states the share by housing type, and a quadplex is not
    read across from the multifamily row: (B)(2) is "five or more units", and
    four is not five. (B)(1) names fourplexes outright."""
    text = store.quote(happy_valley.zones["R7"].values["min_landscaped_pct"].prov.quote)
    assert "fourplexes: 20%" in text
    assert "five or more units" not in text


def test_the_exemption_list_is_the_reason_it_binds(store: ProvenanceStore) -> None:
    """16.42.020 excuses quadplexes from six subsections of 16.42.030 by
    letter. (B) is not among them, and a code that names its exceptions is
    saying the rest applies."""
    text = store.load(f"{HAPPY_VALLEY}/16.42.landscaping.txt").text
    line = next(l for l in text.splitlines() if "are not subject to Section 16.42.030" in l)
    assert "quadplexes" in line
    assert "(D), (F), (G), (H), (J) and (K)" in line
    assert "(B)" not in line


# -- the standard that does not ---------------------------------------------


def test_the_recreation_area_row_is_not_encoded_anywhere(happy_valley: Layer) -> None:
    """Sixteen hundred square feet the tables appear to demand of a fourplex
    and do not. Encoding it would have been the expensive kind of wrong: a
    false RED on every lot in the city under about a fifth of an acre."""
    for zone in ZONES:
        assert "open_space_min_pct" not in happy_valley.zones[zone].values, zone


def test_and_the_layer_says_why_rather_than_leaving_it_to_be_rediscovered(
    happy_valley: Layer,
) -> None:
    """The reference is settled, not missing. Once 16.42 is in the store the
    crossrefs queue stops asking about it and the reason would vanish with the
    question, so it lives in the notes a reviewer reads."""
    assert "16.42.080" in happy_valley.notes
    assert "30 or more units" in happy_valley.notes


def test_the_chapter_it_turns_on_is_in_the_store(store: ProvenanceStore) -> None:
    """A ruling from an unread chapter is a guess. This one is quotable."""
    text = store.load(f"{HAPPY_VALLEY}/16.42.landscaping.txt").text
    assert "The standards of this section apply to subdivisions of 30 or more units." in text


# -- the subtraction three standards defer to -------------------------------


def test_the_net_acre_citation_points_at_the_calculation_not_the_glossary(
    happy_valley: Layer,
) -> None:
    """16.12 defines a net acre as "one acre of developable land, as calculated
    pursuant to Section 16.63.020(F)" — a glossary entry that names the
    quantity and answers no question a screen can ask. Every measured_on in
    this layer used to stop there, with 16.63 unfetched."""
    held = happy_valley.zones["R7"].values["max_density_du_per_acre"]
    assert held.measured_on == "net_developable_area"
    assert "16.63.020(F)(1)" in (held.measured_on_cite or "")
    assert "16.63.land-divisions.txt" in (held.measured_on_quote or "")


def test_and_the_quote_is_the_list_of_what_comes_off(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    """Public facilities, right-of-way, the two overlays, and easement land the
    Planning Official finds similar. This is the survey a lot's own area only
    bounds, which is why these checks settle one half and defer the other."""
    held = happy_valley.zones["R7"].values["max_density_du_per_acre"]
    text = store.quote(held.measured_on_quote)
    assert "Constrained land includes" in text
    assert "Public and private right-of-way" in text
    assert "Steep Slopes Development Overlay Zone in Chapter 16.32" in text
    assert "Natural Resources Overlay Zone in Chapter 16.34" in text
