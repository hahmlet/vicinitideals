"""Gresham's Corridor districts, where the lot standards do the work.

Six of the seven columns of Table 4.0430 were unencoded -- SC, SC-RJ, CMU,
RTC, CC and MC -- and only CMF had been read. The use table splits them
cleanly: a quadplex is a bare P in SC, SC-RJ and CMU and a bare NP in RTC, CC
and MC, so half the chapter is a RED and the other half is the loosest use
permission left in the city.

For a fortnight it was not a *settled* RED, and this file carried the
correction. Table 4.0420's note 2 governs the region the use cells are quoted
from and is ruled ``unmeasured``, so nothing here could say the NP held, and
RTC, CC and MC were made to carry their whole column of Table 4.0430 rather
than the use gate alone. The note turned out to be CMF's -- both its sentences
name that district -- and it was narrowed on 2026-08-26. The three gates are
settled now and the columns are kept anyway, correct and no longer owed. See
``test_unsettled_gates``.

What binds on the permitted half is not the use and not the setbacks. It is
10,000 square feet of lot and 100 feet of street frontage for anything
residential -- twice what the Downtown asks and two and a half times the DRL
blocks -- against a density floor that puts a ceiling on how big the lot may
be. CMU asks 12 units to the acre, which four units meet only up to about
14,520 sq ft. The district is a window roughly 10,000 to 14,500 sq ft wide,
and neither number says so on its own.

Two readings here are deliberately not encoded, and the tests pin both. SC's
density floor names Townhouses and multi-family and nothing else, and Gresham
defines a Multi-Family Dwelling as five units or more that is expressly not
middle housing -- so a quadplex on one lot is neither and the floor does not
reach it. And SC's height ceiling is ten STOREYS, with no figure in feet
anywhere in the chapter; note 18's 45 feet is stated for townhouses and only
for townhouses. That row is why ``max_height_stories`` exists.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.fields import OPTIONAL_FIELDS, REQUIRED_FIELDS
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import ALTERNATIVES, RuleSet

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
#: Table 4.0430's column order, which every row of it is read against.
CORRIDOR = ("RTC", "SC", "SC-RJ", "CMF", "CMU", "CC", "MC")
#: The Quadplex row reads a bare P in these.
PERMITTED = ("SC", "SC-RJ", "CMU", "CMF")
#: And a bare NP in these.
BARRED = ("RTC", "CC", "MC")
#: The three that state their ceiling in storeys rather than in feet.
COUNTED = ("RTC", "SC", "SC-RJ")


@pytest.fixture(scope="module")
def gresham() -> Layer:
    return load_rules()[GRESHAM]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_chapter_now_holds_every_column_of_its_table(gresham: Layer) -> None:
    assert set(CORRIDOR) <= set(gresham.zones)


def test_the_use_table_splits_the_corridor_in_half(gresham: Layer) -> None:
    """A bare P and a bare NP, with nothing conditional between them."""
    for zone in PERMITTED:
        use = gresham.zones[zone].values["quadplex_allowed"]
        assert use.value is True, zone
        assert use.variants == (), zone
    for zone in BARRED:
        held = gresham.zones[zone]
        assert held.values["quadplex_allowed"].value is False, zone
        assert held.values["quadplex_allowed"].variants == (), zone
        # These three used to carry the use gate and nothing else, then a
        # footnote that turned out to be CMF's made them owe the whole column
        # of Table 4.0430. The note is narrowed and the gates are settled; the
        # column stays, because it was read correctly. See test_unsettled_gates.
        assert set(held.values) > {"quadplex_allowed"}, zone


def test_the_lot_standards_are_what_bind_here(gresham: Layer) -> None:
    """10,000 sq ft and 100 feet of frontage, and the split plat escapes both.

    Note 6 switches the minimum lot size off for lots created for townhouses;
    note 11 drops the frontage to 16 feet, or 25 on a corner with an alley and
    32 without one. Both ride as ``unit_lots`` variants because that is what
    the notes say they turn on.
    """
    for zone in PERMITTED:
        assert gresham.zones[zone].values["min_lot_sqft"].value == 10000, zone
        assert gresham.zones[zone].values["min_frontage_ft"].value == 100, zone
    for zone in ("SC", "SC-RJ", "CMU"):
        area = gresham.zones[zone].values["min_lot_sqft"]
        assert [(v.exempt, v.when) for v in area.variants] == [(True, ("unit_lots",))]
        frontage = gresham.zones[zone].values["min_frontage_ft"]
        assert [(v.value, v.when) for v in frontage.variants] == [
            (16, ("unit_lots",)),
            (32, ("unit_lots", "corner_lot")),
            (25, ("unit_lots", "corner_lot", "abuts_alley")),
        ]


def test_a_density_floor_that_names_two_uses_reaches_neither_of_ours(
    gresham: Layer,
) -> None:
    """SC's cell says "18 for Townhouses; 24 for multi-family" and stops.

    RTC prints the same shape with 20 in place of the 24.

    A quadplex on one lot is not a townhouse and, in Gresham, not multi-family
    either -- that word is defined as five units or more and expressly not
    middle housing. So the floor is encoded as not applying rather than
    borrowed from whichever cell is nearest, which would be a rule the code
    does not state. Split the plat and the building IS a townhouse, and the
    same cell states its floor outright.
    """
    for zone in COUNTED:
        floor = gresham.zones[zone].values["min_density_du_per_acre"]
        assert floor.exempt, zone
        assert [(v.value, v.when) for v in floor.variants] == [(18, ("unit_lots",))]


def test_a_bare_density_floor_does_reach_it(gresham: Layer) -> None:
    """CMU and CMF print a number and name no use, so the number applies.

    Read against the 10,000 sq ft the same table asks, four units fit between
    that floor and roughly 14,520 sq ft -- 4 units on 12 to the acre. Neither
    row says so alone, and the ceiling of 24 never binds on a lot that clears
    the other two.
    """
    for zone in ("CMU", "CMF"):
        floor = gresham.zones[zone].values["min_density_du_per_acre"]
        assert floor.value == 12, zone
        assert not floor.exempt, zone
        assert gresham.zones[zone].values["max_density_du_per_acre"].value == 24, zone
    for zone in ("SC", "SC-RJ"):
        assert gresham.zones[zone].values["max_density_du_per_acre"].value == 60, zone
    # RTC is the one ceiling in the table that is not a number everywhere:
    # unlimited inside the Triangle, 40 per net acre outside it. The
    # Triangle is unmapped here, so the half that can bind is what is held.
    assert gresham.zones["RTC"].values["max_density_du_per_acre"].value == 40
    for zone in ("CC", "MC"):
        assert gresham.zones[zone].values["max_density_du_per_acre"].value == 40, zone
        assert gresham.zones[zone].values["min_density_du_per_acre"].value == 12, zone


def test_a_ceiling_counted_in_storeys_is_encoded_as_a_count(gresham: Layer) -> None:
    """Ten storeys, and no figure in feet anywhere in the chapter.

    Note 18 does state 45 feet, for townhouses and only for townhouses, so
    reading it as the district's ceiling would apply a townhouse standard to a
    quadplex. The storey count is what the cell says.
    """
    for zone in COUNTED:
        held = gresham.zones[zone].values
        assert "max_height_ft" not in held, zone
    assert gresham.zones["SC"].values["max_height_stories"].value == 10
    assert gresham.zones["SC-RJ"].values["max_height_stories"].value == 10
    # RTC prints three figures instead of one: six storeys inside the
    # Stark/Burnside/181st Triangle for exclusively commercial or
    # institutional buildings, four inside it for buildings that include
    # any other use, ten outside it. A building with dwellings is never the
    # six-storey case and the Triangle is a map nothing here reads.
    assert gresham.zones["RTC"].values["max_height_stories"].value == 4
    assert gresham.zones["CMU"].values["max_height_ft"].value == 45
    assert "max_height_stories" not in gresham.zones["CMU"].values


def test_a_storey_count_answers_the_height_requirement(rules: RuleSet) -> None:
    """Otherwise SC owes a number that does not exist.

    ``max_height_ft`` is required and ``max_height_stories`` is not, because
    most codes state feet. The one-directional stand-in is what keeps the
    encoding queue full of work that has not been done rather than work that
    cannot be.
    """
    assert ALTERNATIVES == {"max_height_ft": "max_height_stories"}
    assert "max_height_ft" in REQUIRED_FIELDS
    assert "max_height_stories" in OPTIONAL_FIELDS
    # BARRED is in this loop too. It was not, for a fortnight, because an
    # over-scoped footnote levered those three prohibitions and nothing had
    # encoded the standards behind them -- see test_unsettled_gates.
    for zone in CORRIDOR:
        assert rules.resolve(GRESHAM, zone).missing_required == (), zone


def test_the_residential_setbacks_are_the_same_in_every_permitted_column(
    gresham: Layer,
) -> None:
    """Five front and street-side, none interior, fifteen rear.

    RTC, SC and SC-RJ state them in a Residential sub-cell and CMF and CMU
    state them outright, and the numbers are identical -- which is worth
    pinning, because the two are cited from different lines of the same row.
    """
    for zone in PERMITTED:
        held = gresham.zones[zone].values
        assert held["setback_front_ft"].value == 5, zone
        assert held["setback_side_ft"].value == 0, zone
        assert held["setback_rear_ft"].value == 15, zone
        assert held["setback_street_side_ft"].value == 5, zone
        assert held["setback_front_max_ft"].value == 20, zone


def test_the_corridor_requires_no_parking_at_all(gresham: Layer) -> None:
    """Row K reads None in all seven columns, which is a zero somebody read."""
    for zone in PERMITTED:
        assert gresham.zones[zone].values["parking_min_per_unit"].value == 0, zone


def test_the_new_citations_all_point_at_their_own_sentence(gresham: Layer) -> None:
    ready = readiness_for(gresham, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
