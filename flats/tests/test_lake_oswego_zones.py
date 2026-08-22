"""Six zones a quadplex is permitted in that nothing was screening.

Lake Oswego's use table is ten residential columns wide and the
"Dwelling, quadplex" row is ``P`` in every one of them. The layer carried
four: R-0, R-3, R-5 and R-7.5. R-15, R-10, R-6, R-DD, R-W and R-2 were not in
the funnel at all, and nothing in the system said so -- the coverage ledger
reports zones that are missing a required *field*, and a zone nobody encoded
has no fields to be missing. A gap the size of six zones was invisible because
it was a gap in the list of zones rather than in any zone.

So the first test here is the one that would have caught it: read the use
table, take the columns it prints, and require a zone for each column the pod
is permitted in. It is written against the document rather than against a
hand-typed list, because a hand-typed list is the thing that was wrong.
"""

from __future__ import annotations

import pytest

from flats.encode.qualified import qualified
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

LAYER = "or/clackamas/lake-oswego"
USE_TABLE = "or/clackamas/lake-oswego/50.03.002.use-table.txt"

#: The residential column heads of Table 50.03.002-1, L123-L132, in the order
#: the document prints them. Every later table in LOC 50.04 is a slice of this
#: order, which is what makes a cell's position name its zone.
COLUMNS = (
    "R-15",
    "R-10",
    "R-7.5",
    "R-6",
    "R-5",
    "R-DD",
    "R-W",
    "R-3",
    "R-2",
    "R-0",
)

#: The four the layer carried before 2026-08-21, and the six it did not.
PORTED = ("R-0", "R-3", "R-5", "R-7.5")
ADDED = ("R-15", "R-10", "R-6", "R-DD", "R-W", "R-2")


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


@pytest.fixture(scope="module")
def use_table() -> list[str]:
    return ProvenanceStore().load(USE_TABLE).text.splitlines()


# --- the check that was missing ----------------------------------------------


def test_the_use_table_prints_ten_residential_columns(use_table: list[str]) -> None:
    """Read off the document, not typed from memory. The column heads carry
    their own footnote markers -- "R-3 [3]", "R-0 [3] [4]" -- so the zone name
    is the head with its markers stripped."""
    heads = [line.strip().split(" [")[0] for line in use_table[122:132]]

    assert tuple(heads) == COLUMNS


def test_a_quadplex_is_permitted_by_right_in_every_one_of_them(
    use_table: list[str],
) -> None:
    """L193 is the "Dwelling, quadplex" row and L194-L203 are its cells. Ten
    columns, ten P's, no conditional use and no footnote anywhere on the row."""
    assert use_table[192].strip() == "Dwelling, quadplex"
    assert [line.strip() for line in use_table[193:203]] == ["P"] * 10


def test_and_the_layer_now_carries_a_zone_for_each(rules: RuleSet) -> None:
    """The test that would have found the gap. It compares the encoded zones
    against the table rather than against a list somebody kept up to date,
    because the list nobody kept up to date is what went wrong."""
    encoded = set(rules.layers[LAYER].zones)

    assert set(COLUMNS) <= encoded, sorted(set(COLUMNS) - encoded)
    assert set(PORTED) | set(ADDED) == set(COLUMNS)


def test_nothing_the_six_pulled_in_is_left_unread() -> None:
    """Encoding R-2 put Table 50.04.001-13 inside a quoted region for the first
    time, and the note under it was unread. An unread note over an encoded
    value blocks, which is the gate doing its job; it is ruled now."""
    blocked = [q for q in qualified(LAYER) if q.blocking]

    assert blocked == []


# --- what the six say --------------------------------------------------------


def test_the_waterway_zone_is_the_one_the_pod_cannot_have(rules: RuleSet) -> None:
    """R-W is the loosest zone in the corpus on every standard but one. No
    setbacks at all, no coverage limit, 7,000 sq ft of lot -- and a height
    ceiling of 25 ft measured from the Oswego Lake surface elevation, against
    a pod that is 26 ft tall. It screens RED on height while clearing
    everything else, and while the zone was missing that was invisible."""
    whole = rules.resolve(LAYER, "R-W", lot={"lot_sqft": 9000})
    values = whole.values

    assert values["max_height_ft"].value == 25
    assert values["max_coverage_pct"].value == 100
    for field in ("setback_front_ft", "setback_side_ft", "setback_rear_ft"):
        assert values[field].value == 0, field


def test_the_three_low_density_zones_step_their_height_up(rules: RuleSet) -> None:
    """Table 50.04.001-1 is the only table in the city that gives three
    different flat-lot heights, and R-15 -- the zone with the most land -- gets
    the loosest envelope in Lake Oswego."""
    heights = {
        zone: rules.resolve(LAYER, zone, lot={"lot_sqft": 20000})
        .values["max_height_ft"]
        .value
        for zone in ("R-7.5", "R-10", "R-15")
    }

    assert heights == {"R-7.5": 28, "R-10": 30, "R-15": 35}


def test_and_pay_for_it_in_land(rules: RuleSet) -> None:
    """The other direction of the same table. R-15 asks for twice the lot R-7.5
    does and 80 ft of width, so the height it hands back is not free."""
    lots = {
        zone: (
            rules.resolve(LAYER, zone).values["min_lot_sqft"].value,
            rules.resolve(LAYER, zone).values["min_lot_width_ft"].value,
        )
        for zone in ("R-7.5", "R-10", "R-15")
    }

    assert lots == {"R-7.5": (7500, 50), "R-10": (10000, 65), "R-15": (15000, 80)}


def test_r6_coverage_is_banded_on_the_lot_and_not_on_a_guess(
    rules: RuleSet,
) -> None:
    """Table 50.04.001-8 is the only two-axis coverage table in the corpus:
    five lot-size rows against nine height columns. The lot-size axis is a
    measurement, so it is banded; the height axis is collapsed to the ">27'"
    column, the one figure in each row that holds however tall the building
    turns out to be.

    The bands meet exactly. 7,000 belongs to the first, 7,001 to the second,
    and the base is the residual row rather than a safe-looking default."""
    banded = {
        sqft: rules.resolve(LAYER, "R-6", lot={"lot_sqft": sqft})
        .values["max_coverage_pct"]
        .value
        for sqft in (6999, 7000, 7001, 8500, 8501, 10000, 11500, 11501)
    }

    assert banded == {
        6999: 35,
        7000: 35,
        7001: 33,
        8500: 33,
        8501: 30,
        10000: 30,
        11500: 27,
        11501: 25,
    }


def test_an_unmeasured_lot_does_not_fall_through_to_that_base(
    rules: RuleSet,
) -> None:
    """25 percent is the >11,500 row, not a default. A lot nobody measured is
    reported ambiguous and routed to UNKNOWN rather than handed the figure
    written for the largest lots in the zone."""
    effective = rules.resolve(LAYER, "R-6").values["max_coverage_pct"]

    assert effective.ambiguous == (
        "lot_sqft:<=7000",
        "lot_sqft:>10000-11500",
        "lot_sqft:>7000-8500",
        "lot_sqft:>8500-10000",
    )


def test_the_downtown_zone_states_one_setback_for_everything(
    rules: RuleSet,
) -> None:
    """R-DD is the only residential zone in the city with no setback table.
    LOC 50.04.001.2.e.iii(1)(a) states one figure for the whole zone and every
    setback field carries it."""
    values = rules.resolve(LAYER, "R-DD", lot={"lot_sqft": 9000}).values

    for field in (
        "setback_front_ft",
        "setback_side_ft",
        "setback_rear_ft",
        "setback_street_side_ft",
    ):
        assert values[field].value == 10, field
    assert values["max_coverage_pct"].value == 45  # Table 50.04.001-9, Middle Housing


def test_the_split_plat_path_needs_the_land_one_house_would(
    rules: RuleSet,
) -> None:
    """The townhouse half of the density note, now encoded for every zone whose
    table prints a minimum for a townhouse project. Four 1,500 sq ft townhouse
    lots come to 6,000; the code asks for the area one single-family dwelling
    would need on the same land, which is 15,000 in R-15 and 3,375 in R-3."""
    floors = {"R-15": 15000, "R-10": 10000, "R-6": 6000, "R-DD": 5000, "R-W": 3375}

    for zone, floor in floors.items():
        under = rules.resolve(
            LAYER, zone, ("unit_lots",), lot={"lot_sqft": floor - 1}
        )
        at = rules.resolve(LAYER, zone, ("unit_lots",), lot={"lot_sqft": floor})

        assert under.values["quadplex_allowed"].value is False, zone
        assert at.values["quadplex_allowed"].value is True, zone


def test_r3_gained_the_band_its_own_ruling_said_it_could_not_have(
    rules: RuleSet,
) -> None:
    """The ruling on Table 50.04.001-11 note 3 declined the townhouse half
    because the row it points at looked like five cells across four columns.
    It is four zone cells and a comment cell -- "No min. for PD" -- which is
    the shape every other row in the table has. R-3's cell is the second,
    3,375; R-2's and R-0's read "No min." and take no band."""
    under = rules.resolve(LAYER, "R-3", ("unit_lots",), lot={"lot_sqft": 3374})
    at = rules.resolve(LAYER, "R-3", ("unit_lots",), lot={"lot_sqft": 3375})

    assert under.values["quadplex_allowed"].value is False
    assert at.values["quadplex_allowed"].value is True
    for zone in ("R-2", "R-0"):
        loose = rules.resolve(LAYER, zone, ("unit_lots",), lot={"lot_sqft": 1500})
        assert loose.values["quadplex_allowed"].value is True, zone
