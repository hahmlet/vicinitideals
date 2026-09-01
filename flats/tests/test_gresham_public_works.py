"""The first engineering manual this corpus holds.

Gresham's Development Code says "Clear Vision Area" eleven times and never once
says how big one is. Both halves of Section 9.0200 end on the same sentence --
*"The dimensions of the clear vision area and exceptions are described in the
Public Works Standards (6.04)"* -- and until 2026-09-01 that was where the trail
stopped. The layer's reading note said so in as many words, and said that
fetching the manual was the work the note was asking for.

It is a document class the corpus had never taken in. A city code is published
by a codifier, in chapters, with section numbers; an engineering manual is
published by the public works department, in one 359-page PDF of pavement
sections and sidewalk ramps, and it is adopted by reference rather than by
ordinance. Neither the readiness ladder nor the fetch triage had any reason to
look for one, because nothing in a zoning code's own numbering points at it.

What matters is that it **answers in words**. Clackamas County's Drawing P100
is the other outcome: a citation chain that runs to its end and terminates in a
CAD picture, where the only readable dimension was in the title block. Gresham's
Standard Details 618A and 618B are the same kind of picture and carry the same
widths -- but §6.03 states them in prose first, so the drawings are not declared
and nothing is read off a drawing.

Two things came out of the reading. One value: a citywide 9-foot minimum
driveway approach width, which happens to equal what the site-plan generator had
already been assuming for every city, so it moves no lot and replaces an
assumption with a citation. And three refusals, all of them about WHERE a
driveway may meet the street rather than how wide the pod is -- street
classification, curb returns, corner lots. Those need data this screen does not
have, and they are the kind of constraint that moves a driveway to the other
frontage rather than ending a project.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
PWS = f"{GRESHAM}/pws.6.03-6.04.txt"


@pytest.fixture(scope="module")
def gresham() -> Layer:
    return load_rules()[GRESHAM]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def test_the_manual_is_declared_and_sliced_to_the_two_sections(
    gresham: Layer, store: ProvenanceStore
) -> None:
    """359 pages, narrowed to the 128 lines the code points at.

    A `code:` entry with no `end:` has swallowed a weekly events calendar in
    this corpus before. Here the risk is duller and larger: without the slice
    the store would hold three megabytes of trench backfill and water main
    specifications, and every quote into it would be unreadable.
    """
    declared = {doc.id: doc for doc in gresham.code}
    assert "pws.6.03-6.04" in declared
    doc = declared["pws.6.03-6.04"]
    assert doc.start == "6.03 DRIVEWAYS"
    assert doc.end == "6.05 SIDEWALKS"
    # Layout mode cannot find either heading -- it fractures the section number
    # away from its title across a hundred columns of padding.
    assert doc.extraction == "plain"
    assert store.exists(PWS)

    text = store.load(PWS).text
    assert text.startswith("6.03 DRIVEWAYS")
    assert "6.04 CLEAR VISION AREAS" in text
    assert "6.05 SIDEWALKS" not in text
    # Small enough to read, big enough to be both sections.
    assert 100 < len(text.splitlines()) < 200


def test_the_approach_minimum_is_the_one_value_the_manual_supplies(
    gresham: Layer, store: ProvenanceStore
) -> None:
    """"All driveway approach widths shall be a minimum of 9 feet wide."

    Unconditional, citywide, one sentence. The Development Code prints two
    other nines and neither is this: 7.0420(B)(2)(c)(vi) is the sixth condition
    on a compacted-gravel driveway and 7.0420(B)(2)(d)(iii) is inside the
    Hillside overlay. Holding the approach -- the cut at the property line, a
    public-works dimension -- apart from the driveway itself is what makes room
    for this one to land without disturbing either of those refusals.
    """
    value = gresham.defaults["driveway_approach_min_width_ft"]
    assert value.value == 9
    assert "Public Works Standards 6.03" in value.prov.cite
    assert "public-works-standards" in value.prov.url
    assert "minimum of 9 feet wide" in store.quote(value.prov.quote).replace(
        "d riveway", "driveway"
    )


def test_the_cut_is_pinned_between_the_two_public_works_numbers(
    gresham: Layer,
) -> None:
    """Nine from the manual, ten from the code, and they do not fight.

    GDC 7.0420(B)(2)(b)(ii) caps the combined approach width on a parent lot at
    ten feet for a building with no garage. The manual's floor is nine. So this
    pod meets the street through an opening between 9 and 10 feet and widens
    behind the property line -- a window one foot wide, and satisfiable.

    The manual's own residential ceiling is 24 feet (30 for a three-car garage)
    and its multifamily ceiling is 36. Both are looser than the Development
    Code's middle-housing figure, so neither displaces it. A city may write a
    number twice; the stricter one is the one that binds.
    """
    lo = gresham.defaults["driveway_approach_min_width_ft"].value
    hi = gresham.defaults["driveway_approach_max_width_ft"].value
    assert lo == 9 and hi == 10
    assert lo <= hi, "a floor above the ceiling would fail every Gresham lot"


def test_the_clear_vision_refusal_no_longer_rests_on_a_missing_document(
    gresham: Layer, store: ProvenanceStore
) -> None:
    """The refusal survived the fetch, and changed its reason.

    Before: "there is no number to encode." After: the numbers are on file --
    20 feet for a middle housing driveway, 40 at a street intersection -- and
    the reason is that a triangle cut across a corner is not an inset from a
    line. Writing 40 into a corner setback would take a diagonal off the whole
    street side of the lot.

    This is the difference the ledgers exist to make visible. A refusal that
    says "we cannot reach the document" is a queue item. A refusal that says
    "we read it and the value model cannot hold this shape" is a decision.
    """
    note = " ".join((gresham.notes or "").split())
    assert "9.0200" in note
    assert "Driveways for Detached and Middle Housing Sites 20" in note
    assert "no number to encode" not in note
    assert "corpus does not hold" not in note

    # The two sentences the note is reading, still where it says they are.
    body = store.load(PWS).text
    assert "Driveways for Detached and Middle" in body
    assert "No driveway or off-street parking area shall be located in the Clear" in body
    assert "Street Intersections (Including Railroads) 40" in body


def test_the_manual_adds_three_refusals_about_where_a_driveway_may_go(
    gresham: Layer,
) -> None:
    """None of them is a dimension of the building, and that is the pattern.

    Table 6.03 keys a driveway's distance from a curb return to the functional
    class of the street it fronts. The prose bans a new driveway within 100
    feet of a Major or Standard Arterial curb return. Note 2 pushes a corner
    lot's driveway to within 7 feet of the interior property line when the
    frontage is under 75 feet. Every one of them needs something about the
    street or the corner, and the inventory holds parcels.
    """
    from flats.encode.refusals import refusals

    text = " ".join(r.text for r in refusals(GRESHAM))
    assert "Table 6.03" in text
    assert "Major or Standard Arterial" in text
    assert "Corner lot driveways" in text
    assert "Clear Vision Areas" in text


def test_the_width_limb_of_the_corner_rule_could_never_have_bound(
    gresham: Layer,
) -> None:
    """Note 2's other half caps a corner driveway at 24 feet.

    Worth pinning because it is the cheap half of a refusal: the placement limb
    needs corner data, but the width limb is simply slack. This layer already
    carries a 10-foot ceiling from the Development Code, so a 24-foot limit
    from the manual has nothing to do. If the middle-housing approach width
    ever loosens past 24, this test goes red and the refusal has to be reopened
    as a real constraint rather than a recorded one.
    """
    assert gresham.defaults["driveway_approach_max_width_ft"].value <= 24
