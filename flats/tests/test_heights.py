"""The height row, and the one exception in this corpus the pod fails.

max_height_ft was the largest single hole in the coverage ledger: missing on
25 zones covering 138,459 lots, and 122,000 of those sat in Portland's four
single-dwelling zones and the three county pockets that borrow the same
chapter. Both ends of Table 110-4's height row were encoded -- RF at 30 and
R2.5 at 35 -- and the four columns between them were not.

Every pod in the catalog is 26 feet, so 30 clears with four feet of slack and
25 does not clear at all. That is the whole reason these numbers are worth
asserting rather than assuming: one of them is a real failure.
"""

from __future__ import annotations

import pytest

from flats.designs.model import load_catalog
from flats.rules.loader import load_rules
from flats.rules.resolver import RuleSet

pytestmark = pytest.mark.unit

PDX = "or/multnomah/portland"
COUNTY = "or/multnomah/_unincorporated"


@pytest.fixture(scope="module")
def rules() -> RuleSet:
    return RuleSet(load_rules())


def test_the_pod_is_shorter_than_every_ceiling_but_one() -> None:
    """Which is what makes the exception worth encoding and the rest worth
    getting right: at 26 feet the margin against 30 is four feet, and a zone
    read one column across would have been read as 35."""
    assert {design.height_ft for design in load_catalog()} == {26.0}


def test_table_110_4_states_one_height_for_five_of_its_six_columns(
    rules: RuleSet,
) -> None:
    """"Maximum Height | 30 ft. | 30 ft. [3] | 30 ft. [3] | 30 ft. [3] |
    30 ft. [3] | 35 ft." against a header reading RF | R20 | R10 | R7 | R5 |
    R2.5. Six cells, six columns, and the four in the middle all read the
    same -- so no way of counting them changes a number.

    Note [3] hangs on four of those cells and is already ruled: additional FAR
    and height may be allowed under 33.110.265.F, which can only raise a
    ceiling.
    """
    assert {
        zone: rules.resolve(PDX, zone).get("max_height_ft")
        for zone in ("RF", "R20", "R10", "R7", "R5", "R2.5")
    } == {"RF": 30, "R20": 30, "R10": 30, "R7": 30, "R5": 30, "R2.5": 35}


def test_every_cell_of_that_row_cites_the_header_that_names_its_column(
    rules: RuleSet,
) -> None:
    """The value alone cannot be checked against a table that prints six
    districts on one physical line."""
    zones = load_rules()[PDX].zones

    for zone in ("RF", "R20", "R10", "R7", "R5", "R2.5"):
        quote = zones[zone].values["max_height_ft"].prov.quote
        assert quote == "or/multnomah/portland/33.110.txt#L435,L454", zone


def test_the_portland_administered_pockets_take_portlands_ceiling(
    rules: RuleSet,
) -> None:
    """R7, R10, R20 and RF in unincorporated Multnomah are governed by PCC
    33.110, and the county's own stored copy prints the table at the same
    lines."""
    assert {
        zone: rules.resolve(COUNTY, zone).get("max_height_ft")
        for zone in ("RF", "R20", "R10", "R7")
    } == {"RF": 30, "R20": 30, "R10": 30, "R7": 30}


def test_the_countys_own_zones_are_five_feet_looser(rules: RuleSet) -> None:
    """LR-7 and RR cite the Multnomah County Code rather than Portland's, and
    both state 35 feet. Reading the pockets' 30 across to them would have
    invented a standard the county does not impose."""
    assert rules.resolve(COUNTY, "LR7").get("max_height_ft") == 35
    assert rules.resolve(COUNTY, "RR").get("max_height_ft") == 35


def test_a_flag_lot_in_lr_7_is_the_one_lot_the_pod_is_too_tall_for(
    rules: RuleSet,
) -> None:
    """MCC 39.4862 exception (4): the ceiling is 25 feet for "a single family,
    duplex or multiplex dwelling on a flag lot or a lot having sole access
    from an accessway, private drive or easement". The pod is a multiplex and
    it is 26 feet, so this is not a margin -- it is a miss.

    Encoded as a variant rather than as the base, because the exception
    reaches flag lots and not the district. The other half of its trigger --
    sole access by accessway, private drive or easement -- is not a fact any
    layer here holds, so a lot reached only by an easement takes 35 and should
    take 25. That direction is recorded in the file; this test holds the half
    that can be seen.
    """
    ordinary = rules.resolve(COUNTY, "LR7")
    flag = rules.resolve(COUNTY, "LR7", ("flag_lot",))

    assert ordinary.get("max_height_ft") == 35
    assert flag.get("max_height_ft") == 25
    assert all(design.height_ft > 25 for design in load_catalog())


GRESHAM = "or/multnomah/gresham"


def test_greshams_largest_district_had_the_only_standard_it_was_missing(
    rules: RuleSet,
) -> None:
    """Ten of this layer's thirteen districts carried a height and LDR-5 did
    not, on 12,854 lots -- the biggest single-field gap left in the ledger
    after Portland's.

    Table 4.0130 H prints 35 ft. against both the Townhouse row and the
    All-other-uses row, so the pod takes the same number whether it is platted
    as one lot or four.
    """
    assert rules.resolve(GRESHAM, "LDR-5").get("max_height_ft") == 35
    assert rules.resolve(GRESHAM, "LDR-5", ("unit_lots",)).get("max_height_ft") == 35


def test_the_cmf_corridor_is_the_one_place_gresham_gets_tighter_off_base(
    rules: RuleSet,
) -> None:
    """Every other CMF standard encodes the base as the stricter reading and
    hangs the corridor relaxation off civic_corridor. Height runs the other
    way: the district allows 45 feet and note 14 sends the NE Glisan and NE
    162nd corridor areas to TLDR's 35.

    Encoded on the fact rather than written across all 665 lots, because
    applying a corridor standard to a district is the error the density ruling
    on this same note refused to make. The fact is assumed unknown, so no CMF
    lot is certified on either number.
    """
    assert rules.resolve(GRESHAM, "CMF").get("max_height_ft") == 45
    assert rules.resolve(GRESHAM, "CMF", ("civic_corridor",)).get("max_height_ft") == 35

    # The variant's number is printed in the residential chapter, not in the
    # note that reaches for it -- note 14 states a reference and no height.
    variant = load_rules()[GRESHAM].zones["CMF"].values["max_height_ft"].variants[0]
    assert variant.prov.quote == "or/multnomah/gresham/4.0100.residential.txt#L330,L332"


def test_gresham_butte_is_ldr_5_by_reference_and_not_by_copy(rules: RuleSet) -> None:
    """4.1312 states the whole district in one sentence -- "the Site
    Development Requirements of LDR-5 shall apply unless modified by this
    section" -- and modifies two things: quadplexes are prohibited, and the
    side yard is 10 feet instead of 5.

    Adopted by reference so every inherited number still cites the Table
    4.0130 cell it was read from. Copying them would have frozen this district
    at whatever LDR-5 said the day someone typed it.
    """
    butte = rules.resolve(GRESHAM, "LDR/GB")
    ldr5 = rules.resolve(GRESHAM, "LDR-5")

    assert butte.get("quadplex_allowed") is False
    assert butte.get("setback_side_ft") == 10 != ldr5.get("setback_side_ft")
    for field in ("max_height_ft", "setback_front_ft", "setback_rear_ft", "min_lot_sqft"):
        assert butte.get(field) == ldr5.get(field), field


FAIRVIEW = "or/multnomah/fairview"


def test_fairviews_height_row_is_read_by_counting_its_cells(rules: RuleSet) -> None:
    """Table 19.30.030.A extracts one cell per line, so nothing but position
    says which district a 35 belongs to. Column order is stated once, at the
    top of the table: R-6, R-7.5, R-10, Townhouse Overlay, Residential Medium.

    Getting the count wrong by one would put RM's 45 on R-10, which is the
    error worth a test.
    """
    assert {
        zone: rules.resolve(FAIRVIEW, zone).get("max_height_ft")
        for zone in ("R-6", "R-7.5", "R-10", "RM")
    } == {"R-6": 35, "R-7.5": 35, "R-10": 35, "RM": 45}


def test_the_village_zones_state_their_own_height_in_prose(rules: RuleSet) -> None:
    """Table 19.30.030.A has no column for either village zone. Both chapters
    say it in a sentence instead -- "buildings within this zone may not exceed
    35 feet in height" -- and that sentence is the citation."""
    for zone, doc in (("VSF", "19.115"), ("VTH", "19.120")):
        held = load_rules()[FAIRVIEW].zones[zone].values["max_height_ft"]
        assert held.value == 35, zone
        assert held.prov.quote.startswith(f"or/multnomah/fairview/{doc}.txt"), zone


def test_the_townhouse_overlay_takes_the_stricter_of_its_two_columns(
    rules: RuleSet,
) -> None:
    """RM/TOZ adopts RM by reference and its note anticipated exactly this:
    "if the overlay turns out to move a standard, that standard belongs here
    as a local value overriding the reference."

    Row 17 gives the Townhouse Overlay column 35 feet and RM 45. The local
    value is the 35 -- stricter, and the one a lot cannot be certified past.
    Everything else in the zone still resolves through RM, because one cell is
    not an answer to which column governs the rest.
    """
    assert rules.resolve(FAIRVIEW, "RM/TOZ").get("max_height_ft") == 35
    assert rules.resolve(FAIRVIEW, "RM").get("max_height_ft") == 45
    assert rules.resolve(FAIRVIEW, "RM/TOZ").get("max_coverage_pct") == rules.resolve(
        FAIRVIEW, "RM"
    ).get("max_coverage_pct")


def test_the_manufactured_home_park_states_no_height_at_all(rules: RuleSet) -> None:
    """19.30.030.A says where that district's standards live -- "all standards
    for the Manufactured Home Park District are located in FMC 19.30.100" --
    and 19.30.100 states a pad size, a density, setbacks, landscaping and a
    roof pitch. No building height.

    Exempt rather than missing: the section was read.
    """
    resolved = rules.resolve(FAIRVIEW, "R/MH")

    assert resolved.get("max_height_ft") is None
    assert "max_height_ft" in resolved.exempted


LAKE_OSWEGO = "or/clackamas/lake-oswego"


def test_lake_oswego_leaves_the_pod_two_feet(rules: RuleSet) -> None:
    """This city splits its districts across three dimensional tables and
    this layer holds one zone from each band. All three print the same base
    height on a flat lot -- 28 feet -- so the pod's 26 clears by two, the
    tightest margin any standard in this corpus leaves it.

    The two rows under Flat Lot are not looser numbers for the same measure.
    "Lot with Sloping Topography" sets a plane 28 ft above the highest natural
    grade and reaches 32 where the ground falls away, and "Footprint, Sloped"
    is 35. Both need a topography this screen does not read, and both only
    ever raise a building.
    """
    assert {
        zone: rules.resolve(LAKE_OSWEGO, zone).get("max_height_ft")
        for zone in ("R-0", "R-3", "R-5", "R-7.5")
    } == {"R-0": 28, "R-3": 28, "R-5": 28, "R-7.5": 28}

    assert all(28 - design.height_ft == 2 for design in load_catalog())


def test_each_lake_oswego_height_cites_the_table_that_governs_its_band(
    rules: RuleSet,
) -> None:
    """Four zones, three tables. Reading one band's cell for another zone is
    the mistake available here, and it is invisible when every number happens
    to agree -- so the citations are asserted, not just the values."""
    zones = load_rules()[LAKE_OSWEGO].zones
    cells = {
        zone: zones[zone].values["max_height_ft"].prov.quote.split("#")[1]
        for zone in ("R-7.5", "R-5", "R-3", "R-0")
    }

    assert cells == {
        "R-7.5": "L205,L207",   # Table 50.04.001-1, first of R-7.5 / R-10 / R-15
        "R-5": "L585,L587",     # Table 50.04.001-3, second of R-6 / R-5 / R-DD
        "R-3": "L1418,L1421",   # Table 50.04.001-11, second of R-W / R-3 / R-2 / R-0
        "R-0": "L1418,L1423",   # the same row, fourth column
    }
