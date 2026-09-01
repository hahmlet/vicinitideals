"""Villebois, and the largest block of land the screen was dropping.

The Village Zone is one master-planned community on Wilsonville's west side,
and it is 2,508 lots -- more than PDR-3's 1,778 and larger than any other zone
in the city. Until 2026-09-01 the corpus had no entry for it, so those lots were
not red and not green: they never reached the fit stage at all. An unencoded
zone is invisible to a ledger that counts fields, which is the failure this
corpus has now hit twice.

What makes the reading interesting is that Table V-1, the zone's development
standards table, HAS NO ROW FOR A QUADPLEX. Its building types are Commercial,
Hotels, Mixed Use, Multi-Family Dwellings, Row Houses, and "Single-Family
Dwellings and Duplexes". Three other cities in this corpus have cost a day each
arguing which row a four-unit building belongs in. Here nobody has to argue:
4.001(96) defines a Multiple-Family dwelling unit as units on one lot "where ...
the dwelling units are not middle housing", and 4.001(181) puts the quadplex
inside middle housing. Wilsonville has defined the pod out of its own
multi-family row by writing the definition that way.

The route in is 4.125(.23), and Table V-1's own note 21 points at it: "The
standards of Table V-1 for single-family dwellings apply with the following
exceptions", the exception that matters being a 7,000 square foot minimum lot.
So the pod is dimensioned as a house, which is what ORS 197A.420 asks for and
rarely gets stated this plainly.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

WILSONVILLE = "or/clackamas/wilsonville"
CODE = f"{WILSONVILLE}/4.planning.txt"


@pytest.fixture(scope="module")
def wilsonville() -> Layer:
    return load_rules()[WILSONVILLE]


@pytest.fixture(scope="module")
def village(wilsonville: Layer):
    return wilsonville.zones["V"]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


def test_the_zone_exists_and_carries_every_required_field(village) -> None:
    """The point of the exercise: 2,508 lots stop being invisible.

    A zone with no entry is worse than a zone that screens red, because red is
    a finding and absent is nothing. This asserts the gap ledger has no reason
    left to hold V open.
    """
    from flats.rules.fields import REQUIRED_FIELDS

    assert set(REQUIRED_FIELDS) - set(village.values) - set(
        load_rules()[WILSONVILLE].defaults
    ) == set()
    assert village.values["quadplex_allowed"].value is True


def test_the_quadplex_is_not_multi_family_by_definition_not_by_argument(
    store: ProvenanceStore,
) -> None:
    """4.001(96) is the whole answer, and it is one clause long.

    "Dwelling Unit, Multiple-Family: Multiple dwelling units located on a single
    lot where units are not an accessory dwelling unit AND THE DWELLING UNITS
    ARE NOT MIDDLE HOUSING." A quadplex is middle housing under 4.001(181), so
    Table V-1's Multi-Family row -- which would have given the pod a 45-foot
    height and a 15-foot front setback and no minimum lot at all -- is closed
    to it. Wood Village, Troutdale and unincorporated Multnomah each had to be
    decided by counting units against a noun. This one is decided by reading
    one sentence.
    """
    body = store.load(CODE).text
    assert "the dwelling units are not middle housing" in body
    assert "duplexes, triplexes, quadplexes" in body.lower()


def test_the_seven_thousand_comes_from_the_redevelopment_provision(
    village, store: ProvenanceStore
) -> None:
    """Not from Table V-1, which prints 2,250 on the row that governs.

    This is the one figure in the zone written for a quadplex, and it sits four
    thousand lines away from the table it amends. A reader who stopped at Table
    V-1 would screen every Villebois lot at 2,250 square feet and call lots
    green that the code does not reach.
    """
    lot = village.values["min_lot_sqft"]
    assert lot.value == 7000
    assert "4.125(.23)(B)(3)" in lot.prov.cite

    quoted = store.quote(lot.prov.quote)
    assert "The standards of Table V-1 for single-family dwellings apply" in quoted
    assert "quadplexes, four-unit" in quoted
    # Note 21 is what sends a reader from the table to the provision.
    assert "Subsection 4.125(.23) contains special provisions" in quoted


def test_the_dimensions_are_the_single_family_row(village) -> None:
    """Height 35, depth 50, width 35 -- the house row, not the apartment row.

    Pinned as a set because the failure mode is silent: any one of these
    swapped for the Multi-Family row's figure still loads, still validates and
    still screens, and only the lot counts would move.
    """
    got = {k: village.values[k].value for k in
           ("max_height_ft", "min_lot_depth_ft", "min_lot_width_ft",
            "setback_rear_ft", "setback_side_ft", "max_coverage_pct")}
    assert got == {
        "max_height_ft": 35,
        "min_lot_depth_ft": 50,
        "min_lot_width_ft": 35,
        "setback_rear_ft": 5,
        "setback_side_ft": 5,
        "max_coverage_pct": 45,
    }


def test_the_front_setback_takes_the_collector_number_as_its_base(village) -> None:
    """Twenty binds; twelve waits on a street-classification layer.

    Table V-1 prints 12 and note 6 raises it to 20 for "Standard, or Large Lots
    on Collector Avenues". Two conditions and neither is measurable -- the
    street class is in no inventory, and Standard and Large are Pattern Book
    categories. Carried the way Lake Oswego is carried: the number that cannot
    turn a red lot green by mistake is the base.
    """
    front = village.values["setback_front_ft"]
    assert front.value == 20
    assert [(v.value, v.when) for v in front.variants] == [(12, ("local_street",))]

    street_side = village.values["setback_street_side_ft"]
    assert street_side.value == 15
    assert [(v.value, v.when) for v in street_side.variants] == [(5, ("local_street",))]


def test_the_combined_side_yard_bands_at_seventy_feet(village) -> None:
    """Note 15's tightening limb, and the only limb of it that is measurable.

    "On Estate Lots and Large Lots with frontage 70 ft. or wider, the minimum
    combined side yard setbacks shall total 15 ft. with a minimum of 5 ft."
    Five and five is ten; this asks fifteen, so a wide lot loses five feet of
    pod width. The lot category is Pattern Book and unknowable, the frontage is
    not, so the rule is applied to every lot 70 feet or wider whatever its
    category -- over-applying a tightening standard, which is the safe half.

    Note 15's other sentence drops small and medium lots to a zero side yard,
    and is not taken. A loosening conditioned on an unknown is not a loosening.
    """
    total = village.values["setback_side_total_ft"]
    assert total.value == 10
    assert len(total.variants) == 1
    wide = total.variants[0]
    assert wide.value == 15
    assert wide.band is not None
    assert (wide.band.measure, wide.band.at_least) == ("lot_width_ft", 70)
    assert village.values["setback_side_ft"].value == 5


def test_the_twenty_five_percent_open_space_is_refused_with_its_reason(
    village, store: ProvenanceStore
) -> None:
    """The one standard in the Village that could kill the pod outright.

    4.125(.08)(A) asks 25 percent of the area in open space "excluding street
    pavement and surface parking", and then says "Required yard areas shall not
    be counted towards the required open space area". On a 7,000 square foot
    lot that is 1,750 square feet that is not building, not parking, not
    driveway and not yard, on top of a 2,000 square foot pod. Almost nothing in
    Villebois would survive it.

    It is refused on the code's own next sentence -- a multi-phased development
    inside an approved Specific Area Plan is not required to meet the 25 percent
    on its own, and Villebois is exactly that -- and on shape: the screen counts
    yards as open space and (.08) does not, so the number could not be applied
    the way it is written even if it applied.
    """
    note = " ".join((village.notes or "").split())
    assert "NOT ENCODED: 4.125(.08)(A)" in note
    assert "Specific Area Plan" in note
    assert "Required yard areas shall not be counted" in note
    assert "open_space_min_pct" not in village.values

    body = store.load(CODE).text
    assert "individual phases are not required to meet the 25 percent standard" in body
    assert "Required yard areas shall not be counted" in body


def test_the_zone_is_held_at_needs_verification(village) -> None:
    """A review with two named questions, not a green.

    The Pattern Book decides the coverage cap through note 20 and the open
    space question is a reading rather than a citation. Both belong in front of
    a person before any Villebois lot is called buildable, and the honest state
    while they wait is the one that keeps the lots visible and out of green.
    """
    note = " ".join((village.notes or "").split())
    assert "quadfit confidence: needs_verification" in note
    assert "2,508 lots" in note


def test_the_refusals_name_what_the_model_cannot_hold(wilsonville: Layer) -> None:
    """Four of them, and none is a number this corpus could have typed.

    A build-to percentage, a design pattern book, an alley-access rule and a
    set of garage setbacks for a building with no garage. Counted so that the
    refusal ledger carries them rather than the reasoning dying in a comment.

    Each assertion is a phrase from the first 320 characters of its refusal,
    because that is the window the ledger keeps -- a refusal whose reason runs
    past it is recorded but not searchable, which is worth knowing when writing
    one.
    """
    from flats.encode.refusals import refusals

    text = " ".join(r.text for r in refusals(WILSONVILLE))
    assert "Architectural Pattern Book" in text
    assert "Minimum Building Frontage Width" in text
    assert "alley access" in text
    assert "except as determined by the City Engineer" in text
