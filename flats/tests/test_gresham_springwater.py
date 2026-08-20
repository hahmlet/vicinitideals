"""Gresham's Springwater plan district, where the lot has to be big.

LDR-SW and THR-SW were encoded in July and VLDR-SW, RTI-SW and IND-SW were
not. The two industrial columns are a settled RED -- Table 4.1520 reads NP on
every residential row -- and the one that is open is open on the largest lot
standards in the corpus: 10,000 square feet of area, 75 feet of width at the
building line, 100 feet of depth and 50 feet of street frontage, all four
asked at once and all four doubled on a corner or close to it.

What makes that readable rather than merely large is the row above them. Row B
prints None against "All Uses" in this column, so VLDR-SW is the one district
in Gresham that permits a quadplex and asks no minimum density of it at all.
Everywhere else in the city a density floor quietly caps how big the lot may
be; here nothing does, and the standards run one way only.

The two districts encoded in July were missing rows of their own -- LDR-SW had
no density, no garage setback and no alley column -- and those are closed here
because they come off the same two tables.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
#: The three columns of Tables 4.1507/4.1508, in the order they are printed.
RESIDENTIAL = ("VLDR-SW", "LDR-SW", "THR-SW")
#: The two industrial sub-districts added here, both settled on the use table.
BARRED = ("RTI-SW", "IND-SW")
UNITS = 4
ACRE = 43560


@pytest.fixture(scope="module")
def gresham() -> Layer:
    return load_rules()[GRESHAM]


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_chapter_now_holds_the_districts_that_were_missing(
    gresham: Layer,
) -> None:
    assert set(RESIDENTIAL) <= set(gresham.zones)
    assert set(BARRED) <= set(gresham.zones)


def test_two_use_tables_and_two_answers(gresham: Layer) -> None:
    """P in the two low-density columns, NP in the high-density one and in both
    industrial ones.

    THR-SW is the odd column: Springwater's HIGH density sub-district refuses a
    quadplex outright and permits townhouses, which is the reverse of the
    reading most of this corpus supports.
    """
    assert gresham.zones["VLDR-SW"].values["quadplex_allowed"].value is True
    assert gresham.zones["LDR-SW"].values["quadplex_allowed"].value is True
    assert gresham.zones["THR-SW"].values["quadplex_allowed"].value is False
    for zone in BARRED:
        held = gresham.zones[zone]
        assert held.values["quadplex_allowed"].value is False, zone
        assert held.values["quadplex_allowed"].variants == (), zone
        assert set(held.values) == {"quadplex_allowed"}, zone


def test_four_lot_standards_are_asked_at_once_and_all_four_are_large(
    gresham: Layer,
) -> None:
    """Area, width, depth and frontage, each the biggest in the corpus.

    A screen that checks area alone passes a 10,000 sq ft lot that is 60 feet
    wide, and this district refuses it on width. All four have to run.
    """
    held = gresham.zones["VLDR-SW"].values
    assert held["min_lot_sqft"].value == 10000
    assert held["min_lot_width_ft"].value == 75
    assert held["min_lot_depth_ft"].value == 100
    assert held["min_frontage_ft"].value == 50
    ldr = gresham.zones["LDR-SW"].values
    assert (
        ldr["min_lot_sqft"].value,
        ldr["min_lot_width_ft"].value,
        ldr["min_lot_depth_ft"].value,
        ldr["min_frontage_ft"].value,
    ) == (5000, 45, 80, 35)


def test_a_corner_lot_is_asked_for_more_here_not_less(gresham: Layer) -> None:
    """100 feet of width and 75 of frontage, against 75 and 50 inside a block."""
    width = gresham.zones["VLDR-SW"].values["min_lot_width_ft"]
    frontage = gresham.zones["VLDR-SW"].values["min_frontage_ft"]
    assert [(v.value, v.when) for v in width.variants if v.when == ("corner_lot",)] == [
        (100, ("corner_lot",))
    ]
    assert [
        (v.value, v.when) for v in frontage.variants if v.when == ("corner_lot",)
    ] == [(75, ("corner_lot",))]


def test_the_one_district_that_asks_no_density_of_a_quadplex(
    gresham: Layer,
) -> None:
    """Row B reads None against All Uses, and row C reads None against ours.

    Both ends open. That is worth stating rather than leaving blank, because
    every other permitting district in Gresham states a floor, and a floor is
    what turns into a maximum lot size once the unit count is fixed. Here
    nothing does -- the four large lot standards are the whole of it.
    """
    held = gresham.zones["VLDR-SW"].values
    assert held["min_density_du_per_acre"].exempt
    assert held["max_density_du_per_acre"].exempt
    assert [
        (v.value, v.when) for v in held["max_density_du_per_acre"].variants
    ] == [(14.4, ("unit_lots",))]
    # And the split plat is not the escape it usually is: 14.4 to the acre puts
    # four units above about 12,100 sq ft, while the lot row already asked
    # 10,000 -- a window rather than a way out.
    assert round(UNITS / 14.4 * ACRE) == 12100


def test_the_district_encoded_in_july_was_missing_its_density(
    gresham: Layer,
) -> None:
    """LDR-SW's 5.8 floor is a maximum lot size of about 30,000 sq ft.

    It went unread for four months while the district screened on setbacks and
    lot size alone.
    """
    floor = gresham.zones["LDR-SW"].values["min_density_du_per_acre"]
    assert floor.value == 5.8
    assert round(UNITS / 5.8 * ACRE) == 30041
    ceiling = gresham.zones["LDR-SW"].values["max_density_du_per_acre"]
    assert ceiling.exempt
    assert [(v.value, v.when) for v in ceiling.variants] == [(25, ("unit_lots",))]


def test_both_springwater_denominators_are_the_long_lists(gresham: Layer) -> None:
    """Article 3 names VLDR-SW and LDR-SW in the LDR group, so both subtract
    the overlays, the easements, the flag pole and the access easement rather
    than the shorter list every district outside the group takes."""
    for zone in ("VLDR-SW", "LDR-SW"):
        for field in ("min_density_du_per_acre", "max_density_du_per_acre"):
            held = gresham.zones[zone].values[field]
            assert held.measured_on == "net_developable_area", (zone, field)
            assert "for the LDR group" in held.measured_on_cite, (zone, field)
            assert "outside" not in held.measured_on_cite, (zone, field)


def test_the_deepest_garage_setback_in_the_corpus(gresham: Layer) -> None:
    """25 feet, and the street side matches it.

    Five feet more than anywhere else in Gresham, and the street-side wall is
    20 where the Townhouse row of the same table asks 8 -- so the split plat
    moves three of the five setbacks here, not one.
    """
    held = gresham.zones["VLDR-SW"].values
    assert held["setback_garage_entrance_ft"].value == 25
    assert held["setback_street_side_ft"].value == 20
    assert held["setback_front_ft"].value == 20
    assert held["setback_rear_ft"].value == 20
    moved = {
        f: [(v.value, v.when) for v in held[f].variants if "unit_lots" in v.when]
        for f in (
            "setback_garage_entrance_ft",
            "setback_street_side_ft",
            "setback_side_ft",
        )
    }
    assert moved == {
        "setback_garage_entrance_ft": [(20, ("unit_lots",))],
        "setback_street_side_ft": [(8, ("unit_lots",))],
        "setback_side_ft": [(0, ("unit_lots", "attached_wall"))],
    }


def test_the_party_wall_relief_is_not_stated_for_the_pod_on_one_lot(
    gresham: Layer,
) -> None:
    """The Common Wall column reads N/A on the All Other Uses row.

    The Townhouse row above it reads 0, and Pleasant Valley gives a quadplex on
    one lot the same 0. Springwater does not, so the interior side setback here
    stays 5 feet unless the plat is split -- and the variant says so by naming
    both facts rather than one.
    """
    side = gresham.zones["VLDR-SW"].values["setback_side_ft"]
    assert side.value == 5
    assert [v.when for v in side.variants] == [("unit_lots", "attached_wall")]
    # Pleasant Valley, same city, same building, same column: 0 on the wall
    # alone.
    other = gresham.zones["MDR-PV"].values["setback_side_ft"]
    assert [v.when for v in other.variants] == [("attached_wall",)]


def test_the_alley_column_of_the_rear_is_read_in_both_districts(
    rules: RuleSet,
) -> None:
    """20 feet down to 8 in VLDR-SW, 15 down to 8 in LDR-SW.

    LDR-SW's was encoded without it in July, so an alley lot screened against
    the deeper number for four months.
    """
    for zone, base in (("VLDR-SW", 20), ("LDR-SW", 15)):
        assert rules.resolve(GRESHAM, zone).values["setback_rear_ft"].value == base
        with_alley = rules.resolve(GRESHAM, zone, ("abuts_alley",))
        assert with_alley.values["setback_rear_ft"].value == 8, zone


def test_the_tightest_floor_area_ratio_in_the_corpus(gresham: Layer) -> None:
    """0.7, against 1.0 in the district next door."""
    far = gresham.zones["VLDR-SW"].values["max_far"]
    assert far.value == 0.7
    assert [(v.exempt, v.when) for v in far.variants] == [(True, ("unit_lots",))]
    assert gresham.zones["LDR-SW"].values["max_far"].value == 1.0


def test_every_springwater_district_owes_nothing_more(rules: RuleSet) -> None:
    for zone in (*RESIDENTIAL, *BARRED):
        assert rules.resolve(GRESHAM, zone).missing_required == (), zone


def test_the_new_citations_all_point_at_their_own_sentence(gresham: Layer) -> None:
    ready = readiness_for(gresham, store=ProvenanceStore())
    assert ready.no_evidence == ()
    assert ready.misquoted == ()
