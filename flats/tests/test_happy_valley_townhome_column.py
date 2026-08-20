"""The column beside the one that was read.

Every residential table in Happy Valley's Chapter 16.22 states its standards
twice: once for the row a quadplex is named in, and once for a townhome. The
July port read the first and not the second, and the second is looser in four
standards at once:

    Lot size (minimum and maximum density): ... quadplex ...   40,000 sq. ft.
    Lot size (minimum): Townhome                                1,500 sq. ft.

Four townhomes need 6,000 square feet in R-40. The file held them to 40,000 --
a lot this city permits the building on, screened RED for missing a standard it
is not held to, in a zone whose own table says so one row down. The same is
true of lot width (the townhome is exempt), street frontage (twenty feet
against a hundred) and the interior side yard (zero along the party wall).

All four are conditioned on `unit_lots`, because that is what a townhome is
here: the table gives it a lot minimum of its own, which only means something
if each unit has a lot. The pod's current catalog entry is platted on one lot,
so none of these fire today. They are correct anyway, and the day a unit-lot
design enters the catalog they are the difference between a screen that finds
Happy Valley's densest land and one that does not.

The fifth correction runs the other way, and is the one that would have hurt.
The note over all three use tables reads "Applies to a parent lot. Duplexes,
triplexes, quadplexes, and cottage clusters are not permitted on a child lot
(i.e., previously subdivided lot from a middle housing land division)". That
qualifies the *permission*: on a child lot this building is not smaller, it is
forbidden. Nothing in the file said so, and those lots screened GREEN.
"""

from __future__ import annotations

import pytest

from flats.provenance.store import ProvenanceStore
from flats.rules.conditions import condition
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

HAPPY_VALLEY = "or/clackamas/happy-valley"

#: The eight zones whose use table carries the child-lot note.
ZONES = ("R40", "R20", "R15", "R10", "R8.5", "R7", "R5", "MURS")

#: The seven that state a lot minimum in square feet, and what it was.
QUADPLEX_MINIMUM = {
    "R40": 40000,
    "R20": 20000,
    "R15": 15000,
    "R10": 10000,
    "R8.5": 8500,
    "R7": 7000,
    "R5": 7000,
    "MURS": 7000,
}

#: Four dwellings at the 1,500 sq ft the townhome row prints.
DWELLINGS = 4


@pytest.fixture(scope="module")
def happy_valley() -> Layer:
    return load_rules()[HAPPY_VALLEY]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


# -- the lot minimum ---------------------------------------------------------


def test_the_townhome_row_is_a_path_to_a_legal_four_unit_building(
    happy_valley: Layer,
) -> None:
    for zone in ZONES:
        held = happy_valley.zones[zone].values["min_lot_sqft"]
        assert held.value == QUADPLEX_MINIMUM[zone], zone
        variant = next(v for v in held.variants if v.when == ("unit_lots",))
        assert variant.per_dwelling == 1500, zone
        assert variant.value == 1500 * DWELLINGS, zone


def test_the_file_states_the_figure_the_table_prints(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    """6,000 appears nowhere in this code. The YAML carries 1,500 and the
    loader multiplies, so the citation check still compares the cited line
    against the number a reader will find on it."""
    for zone in ZONES:
        variant = next(
            v for v in happy_valley.zones[zone].values["min_lot_sqft"].variants
            if v.when == ("unit_lots",)
        )
        text = store.quote(variant.prov.quote)
        # Two printings of the same row: the older documents spell "1,500 sq.
        # ft." and R-5 and MUR-S abbreviate to "1,500 sf".
        assert "1,500 s" in text, zone
        assert "6,000" not in text, zone


def test_the_zone_that_stated_no_minimum_at_all_now_does(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    """MUR-S carried no lot minimum. Most of its column reads "Variable" --
    width, depth, frontage and coverage really are set case by case through a
    master plan -- but the quadplex lot size is not one of them, and a missing
    required standard is a check that never runs."""
    held = happy_valley.zones["MURS"].values["min_lot_sqft"]
    assert held.value == 7000
    assert "7,000 sf" in store.quote(held.prov.quote)


# -- the other three ---------------------------------------------------------


def test_a_townhome_is_exempt_from_lot_width_rather_than_held_to_less(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    for zone in ("R40", "R20", "R15", "R10", "R8.5", "R7", "R5"):
        variant = next(
            v for v in happy_valley.zones[zone].values["min_lot_width_ft"].variants
            if v.when == ("unit_lots",)
        )
        assert variant.exempt, zone
        assert variant.value is None, zone
        assert "exempt from the lot width" in store.quote(variant.prov.quote), zone


def test_street_frontage_is_stated_in_four_zones_that_carried_none(
    happy_valley: Layer,
) -> None:
    """R-10, R-8.5, R-7 and R-5 print a street frontage minimum and the file
    tested nothing against it."""
    for zone, feet in (("R10", 50), ("R8.5", 50), ("R7", 50), ("R5", 40)):
        assert happy_valley.zones[zone].values["min_frontage_ft"].value == feet, zone


def test_and_every_zone_carries_the_twenty_feet_a_townhome_needs(
    happy_valley: Layer,
) -> None:
    for zone in ("R40", "R20", "R15", "R10", "R8.5", "R7", "R5"):
        variant = next(
            v for v in happy_valley.zones[zone].values["min_frontage_ft"].variants
            if v.when == ("unit_lots",)
        )
        assert variant.value == 20, zone


def test_the_party_wall_zero_reaches_every_zone_whose_table_prints_it(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    """Three zones carried it and five did not, from tables that print the same
    `5/0` cell and hang the same footnote off it."""
    for zone in ZONES:
        variant = next(
            v for v in happy_valley.zones[zone].values["setback_side_ft"].variants
            if v.value == 0
        )
        assert variant.when == ("attached_wall", "unit_lots"), zone
        assert "reduced to zero" in store.quote(variant.prov.quote), zone


def test_lot_depth_is_carried_where_the_code_states_it(happy_valley: Layer) -> None:
    """An optional field, which is why four zones could state a depth and
    encode none: nothing in the ledger asks for a standard most Oregon codes
    do not have."""
    for zone, feet in (("R40", 200), ("R20", 100), ("R15", 90), ("R10", 80),
                       ("R8.5", 70), ("R7", 70), ("R5", 60)):
        assert happy_valley.zones[zone].values["min_lot_depth_ft"].value == feet, zone


# -- the permission ----------------------------------------------------------


def test_a_child_lot_of_a_middle_housing_division_is_not_a_site_for_this(
    happy_valley: Layer, store: ProvenanceStore
) -> None:
    for zone in ZONES:
        held = happy_valley.zones[zone].values["quadplex_allowed"]
        assert held.value is True, zone
        variant = next(v for v in held.variants if v.when == ("middle_housing_child_lot",))
        assert variant.value is False, zone
        assert "not permitted on a child lot" in store.quote(variant.prov.quote), zone


def test_the_fact_is_answered_by_assumption_rather_than_left_open() -> None:
    """Assumed false on purpose. Middle housing land divisions date from 2022
    and are a small share of any county's lots; holding a whole jurisdiction at
    UNKNOWN for a condition almost none of them have would cost more than it
    protects, and the answer is in the plat record rather than out of reach.
    An assumed answer still comes back as FACT_ASSUMED."""
    fact = condition("middle_housing_child_lot")
    assert fact.kind == "site_fact"
    assert fact.assume is False
    assert fact.evidence
