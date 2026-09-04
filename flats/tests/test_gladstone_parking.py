"""The city that requires almost no parking and regulates all of it.

Gladstone is the eighth city this corpus can dimension, and the reason it was
not the first is a ruling that got the question wrong. A crossref note stood in
this layer for weeks saying Chapter 17.48 need not be fetched, because the state
caps middle-housing parking at one space per unit and "this chapter can only
bind at or below the figure already screened against". Every word of that is
about HOW MANY. A parking chapter also says how big a stall is, how wide the
drive between two rows of them has to be, and how far back from the property
line the first one may sit. None of those is capped by anything, and 2,371 lots
sat undrawable behind an argument that never mentioned them.

The chapter states the split itself, in 17.48.010: parking "is not required
within" the Town Center boundary, a quarter mile of it, or half a mile of
McLoughlin Boulevard -- and then, in the next breath, "Any off-street parking
provided within these and other areas within the city must meet the standards of
this chapter." Required and regulated are two different questions and Gladstone
answers them in adjacent sentences.

What it holds is the widest stall in this corpus at nine and a half feet, a 24
foot aisle, a five-foot parking setback measured from any property line, and no
ceiling at all. And it settles "is a quadplex multi-household?" by counting, two
days after Troutdale settled the same word the same way: a multi-household
dwelling here is "designed for occupancy by five or more households".
"""

from __future__ import annotations

import pytest

from flats.encode.refusals import refusals
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import DWELLINGS
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

GLADSTONE = "or/clackamas/gladstone"
PARKING = "or/clackamas/gladstone/17.48.parking.txt"
DEFINITIONS = "or/clackamas/gladstone/17.06.definitions.txt"


@pytest.fixture(scope="module")
def gladstone() -> Layer:
    return load_rules()[GLADSTONE]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def _lines(store: ProvenanceStore, doc: str) -> list[str]:
    return store.load(doc).text.splitlines()


def test_a_waiver_of_the_requirement_is_not_a_waiver_of_the_standards(
    store: ProvenanceStore,
) -> None:
    """17.48.010, and the sentence that makes the old ruling wrong.

    The mandate exception is real and it is large -- three areas, one of them
    half a mile either side of a highway through a city four square miles in
    size. It waives the requirement to build parking. Subsection (3) then says
    what happens to the parking somebody builds anyway, which is everything
    this layer now encodes.
    """
    lines = _lines(store, PARKING)

    assert lines[18].startswith("17.48.010 Applicability.")
    assert lines[20] == (
        "Off-street parking and loading standards shall apply to all development "
        "permits, except:"
    )
    assert lines[22] == "(1) Off-street parking is not required within:"
    assert "Gladstone Town Center boundary" in lines[24]
    assert "One-quarter-mile" in lines[26]
    assert "One-half-mile of McLoughlin Boulevard" in lines[28]

    # The half the ruling never reached.
    assert "must meet the standards of this chapter" in lines[32]
    assert "at the discretion of the property owner" in lines[32]


def test_a_quadplex_is_not_multi_household_here_and_the_code_says_so_with_a_number(
    store: ProvenanceStore,
) -> None:
    """17.06.141, counted rather than argued -- the second city in three days.

    Nothing turns on it for the space count: Table 1 asks one per dwelling unit
    of row (b) and one per dwelling unit of row (c), so the pod pays four either
    way. It turns on it for the bicycle standards, which are written for
    "multi-household residential" and would miss this building entirely if a
    parenthetical did not put it back.
    """
    lines = _lines(store, DEFINITIONS)

    assert lines[556].startswith("17.06.141 Dwelling, multi-household.")
    assert "designed for occupancy by five or more households" in lines[558]

    assert lines[586].startswith("17.06.145 Dwelling, four-household or quadplex.")
    assert "four attached or detached dwelling units on a single lot" in lines[588]

    assert DWELLINGS == 4


def test_the_pod_takes_the_named_row_and_the_row_has_no_ceiling(
    gladstone: Layer, store: ProvenanceStore
) -> None:
    """Table 1(1)(b), which names a quadplex and then declines to cap it.

    `exempt` and not absence: the chapter builds the whole maximum apparatus --
    a Zone A and a Zone B defined for the purpose, five kinds of space exempt
    from the maxima, a rule for developments that already exceed one and a
    variance path out of one -- and points none of it at this row.
    """
    lines = _lines(store, PARKING)

    assert lines[171] == "Duplex, Triplex, Quadplex, Townhouse, Cottage"
    assert lines[172] == "1 space per dwelling unit"
    # The Zone A cell is two paragraphs; Zone B is the third line.
    assert lines[173] == "Min: None"
    assert lines[174] == "Max: None"
    assert lines[175] == "Not Applicable"

    assert gladstone.defaults["parking_min_per_unit"].value == 1
    assert gladstone.defaults["parking_max_per_unit"].exempt is True

    # The apparatus that makes the empty column a reading.
    assert "Zone A shall include those areas identified in GMC Section" in lines[118]
    assert "exempt from the maximum parking ratios" in lines[120]


def test_nine_and_a_half_feet_is_the_widest_stall_in_the_corpus(
    gladstone: Layer, store: ProvenanceStore
) -> None:
    """Table 2, 90 degrees. Half a foot wider than anyone else asks.

    Four stalls across a rear court is two feet of lot width Gladstone charges
    and no other city here does. Pinned as a corpus-wide superlative rather
    than as a number, because the thing worth knowing is that a lot which
    passes here would pass anywhere -- which is what makes encoding the
    dimensions the safe half of the design-review doubt.
    """
    lines = _lines(store, PARKING)
    assert lines[484].split() == ["Parking", "Angle", "Stall", "Width", "Stall", "Depth", "Aisle", "Width"]
    assert lines[487].split() == ["90°", "9.5'", "18.0'", "24.0'"]

    assert gladstone.defaults["parking_stall_width_ft"].value == 9.5
    assert gladstone.defaults["parking_stall_depth_ft"].value == 18

    widest = {
        layer_id: layer.defaults["parking_stall_width_ft"].value
        for layer_id, layer in load_rules().items()
        if "parking_stall_width_ft" in layer.defaults
    }
    assert [k for k, v in widest.items() if v == max(widest.values())] == [GLADSTONE]


def test_the_aisle_is_one_figure_and_a_court_needs_sixty_feet(
    gladstone: Layer,
) -> None:
    """24 feet, stated once and not split by direction.

    So a one-way rear court is dimensioned off the two-way number the way
    Fairview's, West Linn's and Troutdale's are. A stall row, its aisle and a
    second stall row come to sixty feet of depth before any driveway reaches
    them -- one foot less than Troutdale, three more than Gresham.
    """
    assert gladstone.defaults["parking_aisle_one_way_ft"].value == 24
    assert gladstone.defaults["parking_aisle_two_way_ft"].value == 24

    depth = gladstone.defaults["parking_stall_depth_ft"].value
    aisle = gladstone.defaults["parking_aisle_two_way_ft"].value
    assert depth + aisle + depth == 60


def test_the_parking_setback_is_swallowed_by_every_setback_the_zones_state(
    gladstone: Layer, store: ProvenanceStore
) -> None:
    """17.48.040(2)(e), five feet off the property line, spelled not typed.

    The corpus holds the street half because that is the only half it has a
    field for. This pins why the missing half is inert rather than convenient:
    every side and rear setback in both zones is already larger than five. The
    day a Gladstone zone states a side yard under five, the refusal in the
    layer starts costing something and this test is where it will be noticed.
    """
    lines = _lines(store, PARKING)
    assert "set back a minimum of five feet from the property line" in lines[465]
    assert "curb at least four inches high" in lines[465]

    assert gladstone.defaults["parking_street_setback_ft"].value == 5

    for name, zone in gladstone.zones.items():
        for field in ("setback_side_ft", "setback_rear_ft", "setback_front_ft"):
            value = zone.values.get(field)
            if value is None or value.value is None:
                continue
            assert float(value.value) >= 5, (
                f"{name}.{field} is {value.value}, under the five feet a curb "
                "owes the property line -- the side/rear half of 17.48.040(2)(e) "
                "is refused in this layer and would now be binding"
            )


def test_the_forward_access_rule_stops_one_stall_short_of_this_building(
    gladstone: Layer, store: ProvenanceStore
) -> None:
    """17.48.040(2)(d): "groups of MORE THAN four parking spaces".

    Gresham asks every development for forward egress. Gladstone asks it of
    five stalls and up, and the pod owes exactly four -- one space per dwelling
    unit, four dwelling units. The arithmetic is pinned rather than the prose
    because it is one stall from binding, and the marketability tiers seat a
    fifth at 1.5 per unit.
    """
    lines = _lines(store, PARKING)
    assert lines[463].startswith("(d) Groups of more than four parking spaces")
    assert "no backing movements" in lines[463]

    owed = gladstone.defaults["parking_min_per_unit"].value * DWELLINGS
    assert owed == 4
    assert not owed > 4


def test_gladstone_states_no_driveway_width_and_no_curb_cut_ceiling(
    gladstone: Layer,
) -> None:
    """Read and absent, which is a different claim from unread.

    Chapter 17.48 uses the word "driveway" five times and never to give one a
    width; neither dimensional chapter states one either. So a pod here is
    drawn with the design lane and nothing narrows it at the street -- unlike
    Gresham, where a 10 ft approach ceiling is the binding constraint on
    reaching a rear court at all.
    """
    for absent in (
        "driveway_min_width_one_way_ft",
        "driveway_min_width_two_way_ft",
        "driveway_approach_min_width_ft",
        "driveway_approach_max_width_ft",
        "parking_area_max_frontage_pct",
        "parking_front_prohibited",
        "open_space_min_pct",
        "open_space_min_sqft",
    ):
        assert absent not in gladstone.defaults


def test_the_chapter_refused_one_standard_for_every_number_it_gave_up() -> None:
    """Seven values encoded and seven refused, out of one chapter.

    Gladstone had no comment refusals at all before 17.48 was read, and for a
    fortnight every one of them was from it. Counted here as well as in the
    corpus-wide census so that a refusal quietly deleted from this layer fails
    a test named after this city rather than one named after arithmetic.

    The eighth arrived on 2026-09-03 from a different chapter -- 17.25.110,
    which hands a parcel containing a Habitat Conservation Area zero front,
    rear and side setbacks, refused because the only HCA boundary this screen
    has is a regional proxy and a proxy may take ground away but not hand it
    back. It is excluded from the seven rather than folded into them, because
    the sentence this test is making is about ONE chapter's exchange rate --
    seven numbers out, seven readings declined -- and a total that drifts with
    every unrelated reading stops making it. The total is pinned on the line
    below so deleting the eighth still fails here and not only in the census.
    """
    mine = [r for r in refusals() if r.kind == "comments" and r.where == GLADSTONE]
    parking = [r for r in mine if "17.25" not in r.text]
    assert len(parking) == 7
    assert len(mine) == 8
    assert len(load_rules()[GLADSTONE].defaults) == 7
