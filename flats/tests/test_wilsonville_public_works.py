"""The aisle is not in the manual either.

Wilsonville dimensions a parking space in its DEFINITIONS section -- 9 by 18 --
and states no drive aisle anywhere in Chapter 4. On 2026-08-31 the site-plan
generator was allowed to draw the city to an assumed 24-foot aisle and grade
those lots green, on the reasoning that ORS 197A.400 lets a city apply only
clear and objective standards to housing and a width nobody wrote down is not
one. About 140 green lots rest on that.

The one thing that could have overturned it was the Wilsonville Public Works
Standards, which Section 4.113(.14)D.4.c.ii names by title. It was fetched on
2026-09-01 and it does not overturn it. Two hundred and twenty-four pages, the
word "aisle" seven times, and all seven in the same subsection about a CLEAR
drive aisle -- the throat at the mouth of a parking lot where no stall may sit.
That is a distance back from the sidewalk, not a width between two rows of
parked cars.

What the manual does hold is a 12-foot one-way and 20-foot two-way access
driveway minimum, and a 50-foot residential setback from the nearest
intersection. A 20-foot two-way minimum is the size of number that moves lots.
Neither is encoded, and the reason is the route: Chapter 4 sends this building
to the manual in one doubly-conditional sentence -- more than one frontage, and
all of those frontages collectors or arterials -- and the inventory does not
know what class of street any lot fronts.

These tests pin the reading so that if anybody ever wires street classification
into the screen, the numbers waiting for it are already on file with citations.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import CONFIG_ROOT, load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

WILSONVILLE = "or/clackamas/wilsonville"
PWS = f"{WILSONVILLE}/pws.201.2.23.txt"
CODE = f"{WILSONVILLE}/4.planning.txt"


@pytest.fixture(scope="module")
def wilsonville() -> Layer:
    return load_rules()[WILSONVILLE]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def test_the_manual_is_declared_and_sliced_past_its_own_index(
    wilsonville: Layer, store: ProvenanceStore
) -> None:
    """`nth: 2`, because a 224-page manual lists every section number first.

    Slicing on the first "201.2.23 Driveways" would store a single line of the
    table of contents -- the failure mode the slicer calls out rather than
    accepts, and the reason the marker has an occurrence number at all.
    """
    declared = {doc.id: doc for doc in wilsonville.code}
    assert "pws.201.2.23" in declared
    doc = declared["pws.201.2.23"]
    assert doc.nth == 2
    assert doc.extraction == "plain"
    assert store.exists(PWS)

    text = store.load(PWS).text
    assert text.startswith("201.2.23 Driveways")
    assert "201.2.24" not in text
    # The subsection, not the manual.
    assert 100 < len(text.splitlines()) < 200


def test_the_only_aisle_in_the_manual_is_a_queue_not_a_width(
    store: ProvenanceStore,
) -> None:
    """201.2.23(m) is about where the first stall may sit.

    "A clear drive aisle, containing no parking spaces or intersecting drive
    aisles, shall be provided at all parking lot access driveways ... within 50
    feet of the back of sidewalk". A throat, measured along the driveway. The
    dimension the corpus is missing is the one between two rows of parked cars,
    and no sentence in this manual states it.
    """
    body = store.load(PWS).text
    assert "clear drive\naisle, containing no parking spaces" in body
    assert "Within 50 feet of the back of sidewalk" in body
    # A drawing is named, and it is the Clackamas P100 outcome: RD-1105 is a
    # raster scan with no text layer, so nothing is read off it.
    assert "Detail No. RD-1105" in body
    # The width this test exists to say is absent.
    for phrase in ("aisle width", "aisle shall be a minimum width",
                   "minimum aisle"):
        assert phrase not in body


def test_the_two_numbers_the_manual_holds_are_recorded_not_encoded(
    wilsonville: Layer, store: ProvenanceStore
) -> None:
    """A 20-foot two-way driveway would move lots if it reached them.

    Happy Valley's 20-foot drive is the only driveway figure in this corpus
    that has ever taken a lot away. This one is the same number, and it stays
    out of the layer because of the route rather than the reading -- which is
    exactly the kind of decision that has to be written down where the next
    reader will find it, or it gets re-litigated every six months.
    """
    body = store.load(PWS).text
    assert "minimum width of 12 feet for one-way traffic and 20" in body
    assert "minimum of 50 feet" in body

    assert "driveway_min_width_one_way_ft" not in wilsonville.defaults
    assert "driveway_min_width_two_way_ft" not in wilsonville.defaults
    assert "parking_aisle_two_way_ft" not in wilsonville.defaults

    # The reading lives in a comment beside the refusal it belongs to, which
    # is where this layer keeps its parking reasoning, so the test reads the
    # file rather than the model.
    source = (CONFIG_ROOT / "or" / "clackamas" / "wilsonville.yaml").read_text(
        encoding="utf-8"
    )
    assert "201.2.23(l)" in source
    assert "doubly conditional" in source
    assert "RD-1105" in source


def test_the_code_opens_exactly_one_route_to_the_manual(
    store: ProvenanceStore,
) -> None:
    """And it is conditioned on two things about the streets, not the lot.

    4.113(.14)D.4.c is prefaced "lots or parcels with more than one frontage
    must comply with the following", and c.ii narrows again to frontages "only
    on collectors and/or arterial streets". The same pair of sentences is
    printed twice in the chapter, once for triplexes and quadplexes and once
    for cluster housing; the quadplex copy is the one this layer reads.

    An absence claim needs a whole-document search, so this counts. Six other
    mentions of the Public Works Standards in Chapter 4 are grading,
    stormwater, low impact development and right-of-way construction -- none of
    them reaches a driveway on a private lot.
    """
    chapter = store.load(CODE).text
    routes = chapter.count("access standards in the Wilsonville Public W")
    assert routes == 2, "one for quadplexes, one for cluster housing"
    assert chapter.count("frontages only on collectors and/or arterial streets") == 2
    # If the manual governed every private driveway, this carve-out would be
    # redundant. A code does not except what it already covers.
    assert "more than one frontage must comply with the" in chapter


def test_the_manual_makes_its_own_driveway_width_discretionary(
    store: ProvenanceStore,
) -> None:
    """201.2.23(j), and it is why the assumption is not in tension with it.

    "The City's authorized representative shall make the final determination of
    maximum driveway width on a case-by-case basis." That is discretion, and
    ORS 197A.400 keeps discretion off housing. So even on the narrow class of
    lot the route reaches, the manual's width rule is not a clear and objective
    standard this screen could apply if it wanted to.
    """
    body = store.load(PWS).text
    assert "final determination of\nmaximum driveway width on a case-by-case basis" in body
