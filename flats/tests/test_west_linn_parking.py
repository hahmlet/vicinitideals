"""The city that regulates parking completely and requires none of it.

West Linn is the sixth city this corpus can dimension and the largest one it
had never read: 6,791 lots here fit the pod, more than anywhere outside
Portland, Gresham and unincorporated Clackamas, and the site-plan generator
drew none of them because a city that has not stated a stall cannot be drawn
on. Chapters 46 and 48 are what every zone chapter has been pointing at all
along — items 7 and 8 of the same list, under "The following standards apply to
all development including permitted uses", in all nine of them.

One question decides most of the reading and West Linn never answers it: is a
quadplex on one lot "multifamily" here? The word carries the stall size, the
parking ceiling and the width of the drive, and it appears nowhere in Chapter 2
Definitions. What Chapter 2 does define is three neighbouring categories, and
the pod is the one that is not either of the others. The tests below pin that
reading, because everything downstream of it moves ten feet if it is wrong.

The second reading worth pinning is the stall. 46.150(A)(1) states three sizes
in four sentences, and the third — nine by twenty — fires only "when
multifamily parking stalls back onto a driveway, as opposed to a drive aisle
within a parking lot". Which branch the pod takes is not a judgement about the
code; it is a fact about the drawing, and s6s draws a side lane and a court
aisle as separate pavement.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

WEST_LINN = "or/clackamas/west-linn"
PARKING = "or/clackamas/west-linn/46.parking.txt"
ACCESS = "or/clackamas/west-linn/48.access.txt"
DEFINITIONS = "or/clackamas/west-linn/02.definitions.txt"


@pytest.fixture(scope="module")
def west_linn() -> Layer:
    return load_rules()[WEST_LINN]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _text(store: ProvenanceStore, doc: str) -> str:
    return store.load(doc).text


def test_the_city_requires_no_parking_and_still_caps_it(west_linn: Layer) -> None:
    """Fairview's shape and Wilsonville's, arrived at a third way.

    Fairview prints "There is no minimum off-street parking requirements" and
    Wilsonville's table says "No Limit". West Linn says nothing at all: Ord.
    1754 repealed CDC 46.080, Computation of Required Parking Spaces, and CDC
    46.100, Parking Requirements for Unlisted Uses, and left the heading
    OFF-STREET PARKING SPACE REQUIREMENTS standing over a subsection headed
    "Maximum parking". The requirement is gone and no sentence announces it.

    The maximum is real, though, which makes West Linn the third layer in the
    corpus carrying a parking ceiling rather than an `exempt`. It does not bind
    -- 2.0 per unit is eight stalls, the preferred marketability tier exactly
    -- and recording it is still the point, because `exempt: true` would claim
    the city has no ceiling and it has one.
    """
    minimum = west_linn.defaults["parking_min_per_unit"]
    assert minimum.value == 0
    assert not minimum.exempt

    ceiling = west_linn.defaults["parking_max_per_unit"]
    assert ceiling.value == 2
    assert not ceiling.exempt


def test_no_zone_chapter_states_a_parking_quantity(store: ProvenanceStore) -> None:
    """The absence claim, checked rather than asserted.

    A zero that rests on two repealed sections is only honest if nothing else
    in the corpus imposes a number. Every zone chapter is searched, not just
    the parking one -- a minimum hiding in a dimensional table would make the
    zero above a false GREEN on every lot in the city.
    """
    for chapter in ("08.r-40", "09.r-20", "10.r-15", "11.r-10", "12.r-7",
                    "13.r-5", "14.r-4.5", "15.r-3", "16.r-2.1"):
        text = _text(store, f"or/clackamas/west-linn/{chapter}.txt").lower()
        for line in text.splitlines():
            if "parking" not in line:
                continue
            assert not any(
                word in line for word in ("minimum", "required", "per unit", "spaces per")
            ), f"{chapter}: {line.strip()[:120]}"


def test_the_repealed_sections_are_the_ones_the_zero_rests_on(
    store: ProvenanceStore,
) -> None:
    text = _text(store, PARKING)
    lines = text.splitlines()

    assert lines[126].startswith("46.080 COMPUTATION OF REQUIRED PARKING SPACES")
    assert lines[128].startswith("Repealed by Ord. 1754.")
    assert lines[130].startswith("46.090 OFF-STREET PARKING SPACE REQUIREMENTS")
    assert lines[132].startswith("A. Maximum parking.")
    assert lines[161].startswith("46.100 PARKING REQUIREMENTS FOR UNLISTED USES")
    assert lines[163].startswith("Repealed by Ord. 1754.")


def test_the_definitions_never_say_multifamily_and_say_quadplex_three_ways(
    store: ProvenanceStore,
) -> None:
    """The load-bearing absence, and it is an absence in the definitions.

    "Multifamily" carries the stall size in 46.150(A)(1), the ceiling row in
    46.090(A) and the 24-foot service drive in 48.030(E). Chapter 2 defines
    every other term this corpus needed from West Linn and does not define that
    one -- the word appears nowhere in the chapter.

    What it does define is a quadplex on one lot, single-family attached ON
    SEPARATE LOTS, and single-family detached. The pod on an undivided lot is
    the first, which is neither of the other two, so the multifamily rules are
    the ones it takes -- by elimination, which is a weaker argument than a
    definition and is the only one the code offers.
    """
    definitions = _text(store, DEFINITIONS)
    assert "multifamily" not in definitions.lower()
    assert "multi-family" not in definitions.lower()

    lines = definitions.splitlines()
    assert lines[799].startswith("Quadplex residential units. Four attached or detached")
    assert "on a lot or parcel in any configuration" in lines[799]
    assert lines[946].startswith("Single-family attached residential units.")
    assert "on separate lots or parcels" in lines[946]


def test_chapter_46_sets_the_two_categories_against_each_other(
    store: ProvenanceStore,
) -> None:
    """The confirmation, so the reading above is not left as an inference.

    Chapter 46 twice draws the line the definitions imply: (A)(6) excepts
    "single-family attached and detached residences" from its striping rule,
    and (A)(8) requires them to pave and then separately requires "All parking
    for multifamily residential development" to pave. Two categories, named
    side by side in one sentence, which is what makes multifamily the residual
    residential class rather than a five-units-and-up one.
    """
    lines = _text(store, PARKING).splitlines()
    assert lines[240].startswith("6. Except for single-family attached and detached residences")
    assert "single-family attached and detached residences" in lines[244]
    assert "All parking for multifamily residential development" in lines[244]


def test_the_stall_is_nine_by_eighteen_and_not_nine_by_twenty(
    west_linn: Layer, store: ProvenanceStore
) -> None:
    """Two feet of depth, decided by the drawing rather than by the code.

    46.150(A)(1) states a compact stall of 8 x 16, requires half the spaces to
    be 9 x 18, and then states a third size: "When multifamily parking stalls
    back onto a driveway, as opposed to a drive aisle within a parking lot, the
    stalls shall be nine feet by 20 feet." Multifamily is settled, so the whole
    clause turns on the contrast, and the contrast is about the layout.

    s6s draws a side driveway and, separately, a rear court of 90-degree stalls
    served by its own aisle -- it counts the two as separate pavement. Stalls
    there back onto a drive aisle within a parking lot, the branch the sentence
    excludes. West Linn's own text expects that court: (A)(6) makes a
    multifamily development sign "all interior drives and access aisles", and
    (A)(11) speaks of "the boundaries of a parking lot".

    Nine by eighteen rather than eight by sixteen for the ordinary reason --
    half the stalls must be the larger size, so the larger size is what a court
    is dimensioned to.
    """
    assert west_linn.defaults["parking_stall_width_ft"].value == 9
    assert west_linn.defaults["parking_stall_depth_ft"].value == 18

    stall = _text(store, PARKING).splitlines()[230]
    assert "eight feet in width and 16 feet in length" in stall
    assert "nine feet in width and 18 feet in length" in stall
    assert "as opposed to a drive aisle within a parking lot" in stall


def test_the_aisle_is_the_figure_the_table_prints_at_ninety_degrees(
    west_linn: Layer, store: ProvenanceStore
) -> None:
    """One number for both directions, because only one question was asked.

    Figure 2 is indexed by angle and by how the car enters -- DRIVE-IN or
    BACK-IN -- and not by which way traffic runs, so there is no one-way row to
    read and no two-way row either. Both stall-width columns print 23.0 at 90
    degrees drive-in, so the aisle does not move with the stall.

    Drive-in rather than the 22.0 printed for back-in: a car that drives in
    leaves in reverse and needs the wider aisle to do it, and nothing in the
    catalog obliges a resident to back into a stall. It is also the larger of
    the two, which is the direction this corpus errs in when a reading could go
    either way.
    """
    assert west_linn.defaults["parking_aisle_one_way_ft"].value == 23
    assert west_linn.defaults["parking_aisle_two_way_ft"].value == 23

    row = _text(store, PARKING).splitlines()[382]
    assert row.split()[:3] == ["90°", "DRIVE-IN", "23.0'"]


def test_the_service_drive_is_the_multifamily_figure_not_the_single_family_one(
    west_linn: Layer, store: ProvenanceStore
) -> None:
    """Where the multifamily reading costs ten feet, and it costs them here.

    48.030 states two driveway standards for residential development and the
    definitions decide between them. (B)(2): "Two to four single-family
    residential homes shall provide a driveway with 14- to 20-foot-wide paved
    or all-weather surface." (E): "Access and/or service drives for multifamily
    dwellings ... 1. With a minimum of 24-foot width when accommodating two-way
    traffic; or 2. With a minimum of 15-foot width when accommodating one-way
    traffic."

    Twenty-four is the one that binds, because a single side lane into a rear
    court carries traffic both ways unless a loop is drawn and no loop fits
    beside a 56-foot pod. That is four feet more than Happy Valley's 20, which
    was the widest in this corpus until now, and twice the 12-foot design lane
    an unread city falls back to. If the land is ever divided first the pod
    becomes single-family attached and the 14 is the figure -- which is a
    reason to know which plat is being screened, not a reason to encode the
    looser number now.
    """
    assert west_linn.defaults["driveway_min_width_two_way_ft"].value == 24
    assert west_linn.defaults["driveway_min_width_one_way_ft"].value == 15

    lines = _text(store, ACCESS).splitlines()
    assert lines[128].startswith("E. Access and/or service drives for multifamily dwellings")
    assert "minimum of 24-foot width when accommodating two-way traffic" in lines[130]
    # The branch not taken, pinned so that a future reader can see it was read.
    assert "Two to four single-family residential homes" in lines[110]
    assert "14- to 20-foot-wide" in lines[110]


def test_west_linn_states_both_ends_of_its_curb_cut(
    west_linn: Layer, store: ProvenanceStore
) -> None:
    """The floor is the unusual half.

    Most cities in this corpus cap an approach and let it shrink to nothing.
    48.060 states 16 feet minimum and 36 feet maximum, flatly, with no use, no
    zone and no street attached -- so a pod here cannot economise its opening
    down to a single-car width to buy back side yard.
    """
    assert west_linn.defaults["driveway_approach_min_width_ft"].value == 16
    assert west_linn.defaults["driveway_approach_max_width_ft"].value == 36

    lines = _text(store, ACCESS).splitlines()
    assert lines[174].startswith("A. Minimum curb cut width shall be 16 feet.")
    assert lines[176].startswith("B. Maximum curb cut width shall be 36 feet")


def test_the_four_standards_this_model_cannot_hold_are_still_refused(
    west_linn: Layer,
) -> None:
    """Ten values encoded against four refusals, in one layer, in one reading.

    The refusal ledger counts these by marker and the count is asserted
    elsewhere; what is pinned here is that each one names what it is refusing,
    because a refusal whose subject is not written down is a sentence nobody
    can revisit. All four are shapes rather than gaps -- the standards exist
    and are perfectly clear, and no field in the registry can carry them.

    Five rows rather than four: the layer already carried one before this
    reading, on the 0.30 floor under its floor area ratios.
    """
    from flats.encode.refusals import refusals

    mine = [
        r for r in refusals() if r.kind == "comments" and "west-linn" in r.where
    ]
    assert len(mine) == 5, [r.text[:60] for r in mine]
    subjects = " ".join(r.text.lower() for r in mine)
    assert "curb cut spacing" in subjects
    assert "alley" in subjects
    assert "grade" in subjects
    assert "clearance" in subjects
