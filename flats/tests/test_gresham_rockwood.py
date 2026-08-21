"""Gresham's loudest unfetched reference, and it was about somebody else again.

Table 4.0430 does not state a street setback for RTC, SC or SC-RJ. It states
"Setbacks at Street: See Section 7.0512.A.2" and sends the reader to a chapter
nobody had fetched -- six binding references, the top of this jurisdiction's
cross-reference queue, standing beside numbers the screen already uses.

The answer is in the second thing 7.0502 says. Subsection (A) lists the uses
the design district reaches; subsection (B) lists the exceptions, and the first
line of it is "Single detached dwellings, duplexes, triplexes, and quadplexes
(for these developments, see Section 7.0420)". A quadplex is named. The 5-foot
minimum and 20-foot maximum already encoded from Table 4.0430's Residential
sub-cell are this building's street setbacks in SC and SC-RJ, and 7.0512 never
had anything to say about it.

That is the second time a queue-topping reference has resolved this way --
Happy Valley's 400 square feet of shared recreation area per unit turned out to
apply to subdivisions of thirty or more. Both are worth the fetch anyway. An
absence established is a different thing from an absence assumed, and the queue
cannot tell them apart until somebody reads the chapter.

What 7.0512 does reach is the split plat: 7.0502(A) names Townhouses. And there
the numbers are genuinely unscreenable -- inside the Rockwood triangle the
street setback depends on which street the lot fronts, outside it on the
district -- so a unit-lot design would need a street name and a boundary
nothing measures. That is recorded rather than encoded, which is the whole
point of recording it.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
ROCKWOOD = f"{GRESHAM}/7.0500.rockwood-design.txt"

#: The three corridor districts whose street setbacks Table 4.0430 defers.
DEFERRED = ("RTC", "SC", "SC-RJ")


@pytest.fixture(scope="module")
def gresham() -> Layer:
    return load_rules()[GRESHAM]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def test_the_chapter_the_table_defers_to_is_in_the_store(
    store: ProvenanceStore,
) -> None:
    """A ruling from an unread chapter is a guess. This one is quotable."""
    text = store.load(ROCKWOOD).text
    assert "7.0512" in text
    assert "ROCKWOOD DESIGN DISTRICT DESIGN GUIDELINES AND STANDARDS" in text


def test_a_quadplex_is_named_in_the_exception_list(store: ProvenanceStore) -> None:
    """7.0502(B), first line. The building this screen places is one of four
    types the design district explicitly does not reach."""
    text = store.load(ROCKWOOD).text
    line = next(
        l
        for l in text.splitlines()
        if "Single detached dwellings, duplexes, triplexes, and quadplexes" in l
    )
    assert "7.0420" in line
    exceptions = next(
        l for l in text.splitlines() if "do not apply to:" in l
    )
    assert "7.0501-7.0512" in exceptions


def test_and_the_design_standards_it_is_sent_to_instead_are_held(
    gresham: Layer, store: ProvenanceStore
) -> None:
    """The exception is not a hole. It routes a quadplex to 7.0420, which is
    in the store already -- fetched for the middle-housing design standards."""
    assert "7.0400.middle-housing-design" in {doc.id for doc in gresham.code}
    text = store.load(f"{GRESHAM}/7.0400.middle-housing-design.txt").text
    assert "DESIGN STANDARDS FOR SINGLE DETACHED DWELLINGS, DUPLEXES," in text


def test_so_the_encoded_street_setbacks_stand(gresham: Layer) -> None:
    """Five feet minimum, twenty maximum, from Table 4.0430's Residential
    sub-cell. If 7.0512 had reached this building these would have been wrong
    in both directions at once for any lot inside the Rockwood triangle."""
    for zone in ("SC", "SC-RJ"):
        values = gresham.zones[zone].values
        assert values["setback_front_ft"].value == 5, zone
        assert values["setback_front_max_ft"].value == 20, zone
        assert values["setback_street_side_ft"].value == 5, zone
        assert "4.0400.corridor.txt" in values["setback_front_ft"].prov.quote, zone


def test_the_numbers_that_would_have_applied_are_four_bands_not_one(
    store: ProvenanceStore,
) -> None:
    """Why a unit-lot variant is not encoded from this chapter.

    Inside the triangle the standard is by street and outside it by district,
    and the two disagree in both directions: a lot on Stark may stand no more
    than 5 feet back where the outside-the-triangle rule allows 20, and a lot
    on Burnside must stand at least 10 where the outside rule asks 5. There is
    no single conservative number -- taking the largest minimum and the
    smallest maximum builds an envelope of 10 to 5 feet, which no lot has.
    """
    lines = store.load(ROCKWOOD).text.splitlines()
    inside = next(
        n
        for n, l in enumerate(lines)
        if "INSIDE THE TRIANGLE: When abutting a street" in l
    )
    window = "\n".join(lines[inside : inside + 20])
    assert "Stark St." in window
    assert "Burnside St." in window

    outside = next(
        n
        for n, l in enumerate(lines)
        if "OUTSIDE THE TRIANGLE: When abutting a street" in l
    )
    tables = "\n".join(lines[outside : outside + 30])
    assert "Multi-Family and Townhouse Style" in tables
    for zone in DEFERRED:
        assert zone in tables, zone


def test_the_layer_says_why_rather_than_leaving_it_to_be_rediscovered(
    gresham: Layer,
) -> None:
    """Once 7.0500 is in the store the cross-reference queue stops asking about
    7.0512, and the reason would vanish with the question."""
    assert "7.0512" in gresham.notes
    assert "7.0502(B)" in gresham.notes
    assert "Rockwood triangle" in gresham.notes
