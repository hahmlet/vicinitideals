"""A ceiling the code does not impose, and one it does that nobody wrote down.

West Linn states lot coverage and floor area ratio in the same block of every
zone chapter, and states them differently zone to zone. In R-40 the coverage
applies to everything but a cottage cluster. In R-3 it "does not apply to
duplexes, triplexes, quadplexes, townhouses or cottage clusters" — which is
every building this system screens for. In R-10 and R-7 the FAR row prints
0.45, and then prints a second row underneath it: "Duplex, triplex, and
quadplex 0.60".

The file had all three of those backwards. Four zones carried a coverage
percentage the code does not put on this building, which costs lots that should
pass. Two zones carried no FAR at all against a standard that does bind, which
passes lots that should not — and that is the direction that matters, because a
GREEN is a claim somebody may act on.

None of it was hidden. Every one of those zones already carried a note saying
what the code said: "Max lot coverage does NOT apply to quadplexes (CDC
13.070)", "max FAR 0.60 for duplex/triplex/quadplex". The notes came across in
the quadfit import and the values did not, and nothing in the system compares
the two. So this file pins the values, not the prose.

The last test is about the check that should have caught the fourth error and
could not. R-10 allows 35 percent coverage and a 35 ft building, and the
coverage value cited the height line. The quote resolved, the line printed 35,
and every rung of the readiness ladder passed a citation pointing at a sentence
about something else.
"""

from __future__ import annotations

import pytest

from flats.encode.readiness import cites_a_different_unit, readiness_for
from flats.provenance.store import ProvenanceStore
from flats.rules.loader import load_rules
from flats.rules.model import Layer

pytestmark = pytest.mark.unit

WEST_LINN = "or/clackamas/west-linn"

#: Zone -> the FAR that binds a quadplex there. ``None`` means the row exempts
#: this building by name; absent from the mapping means the chapter prints no
#: floor area ratio at all, which is true of exactly one zone.
FAR = {
    "R-40": 0.45,
    "R-20": 0.45,
    "R-10": 0.60,
    "R-7": 0.60,
    "R-5": None,
    "R-4.5": None,
    "R-3": None,
    "R-2.1": None,
}
#: The four zones whose coverage row names quadplexes among the exempt.
UNCOVERED = ("R-5", "R-4.5", "R-3", "R-2.1")


@pytest.fixture(scope="module")
def west_linn() -> Layer:
    return load_rules()[WEST_LINN]


@pytest.fixture(scope="module")
def store() -> ProvenanceStore:
    return ProvenanceStore()


# -- the ceiling the code does not impose -----------------------------------


def test_a_standard_that_names_this_building_as_exempt_is_not_a_ceiling(
    west_linn: Layer,
) -> None:
    for zone in UNCOVERED:
        held = west_linn.zones[zone].values["max_coverage_pct"]
        assert held.exempt, zone
        assert held.value is None, zone


def test_and_the_zones_that_do_impose_it_still_do(west_linn: Layer) -> None:
    """The exemption is written per zone and reading it across would be the
    same error pointing the other way. R-40 exempts cottage clusters and
    nobody else."""
    for zone, pct in (("R-40", 25), ("R-20", 25), ("R-15", 30), ("R-10", 35), ("R-7", 35)):
        held = west_linn.zones[zone].values["max_coverage_pct"]
        assert not held.exempt, zone
        assert held.value == pct, zone


def test_the_exemption_is_quoted_and_not_asserted(
    west_linn: Layer, store: ProvenanceStore
) -> None:
    for zone in UNCOVERED:
        text = store.quote(west_linn.zones[zone].values["max_coverage_pct"].prov.quote)
        assert "quadplexes" in text, zone
        # "cover" rather than "coverage": R-2.1 prints "Maximum lot cover does
        # not apply", missing the last three letters, and a test demanding the
        # word the other three use would fail on a correct citation.
        assert "does not apply" in text, zone


# -- the ceiling it does impose ---------------------------------------------


def test_the_floor_area_ratio_a_quadplex_is_held_to(west_linn: Layer) -> None:
    for zone, ratio in FAR.items():
        held = west_linn.zones[zone].values.get("max_far")
        assert held is not None, f"{zone} states a FAR row and carries no value"
        if ratio is None:
            assert held.exempt, zone
        else:
            assert held.value == ratio, zone


def test_the_zone_whose_chapter_prints_no_such_row_carries_no_such_value(
    west_linn: Layer,
) -> None:
    """R-15 is the one chapter with no floor area ratio in it. An `exempt`
    there would claim the code says something it does not say."""
    assert "max_far" not in west_linn.zones["R-15"].values


def test_the_second_row_is_the_one_that_binds(
    west_linn: Layer, store: ProvenanceStore
) -> None:
    """0.45 is printed first and 0.60 below it, and the pod is the second row.
    Citing the first would be a number off the same table and the wrong one."""
    for zone in ("R-10", "R-7"):
        text = store.quote(west_linn.zones[zone].values["max_far"].prov.quote)
        assert "Duplex, triplex, and quadplex" in text, zone
        assert "0.60" in text, zone


def test_what_the_ratio_costs_a_lot(west_linn: Layer) -> None:
    """Two thousand and sixteen square feet on two floors. At 0.60 that wants
    a 6,720 sq ft lot, which is under R-10's own minimum and over plenty of
    the lots this screen actually reads."""
    floor_area = 56 * 36 * 2
    needed = floor_area / west_linn.zones["R-10"].values["max_far"].value

    assert round(needed) == 6720


def test_the_encoding_agrees_with_the_note_beside_it(west_linn: Layer) -> None:
    """The whole class of error in one assertion. Every one of these zones
    described the right rule in prose while carrying the wrong value, and the
    prose is the part nothing checks."""
    assert "does NOT apply to quadplexes" in (west_linn.zones["R-5"].notes or "")
    assert west_linn.zones["R-5"].values["max_coverage_pct"].exempt

    assert "0.60" in (west_linn.zones["R-7"].notes or "")
    assert west_linn.zones["R-7"].values["max_far"].value == 0.60


def test_west_linn_still_reads_clean(west_linn: Layer) -> None:
    ready = readiness_for(west_linn, store=ProvenanceStore())

    assert not ready.misquoted
    assert not ready.no_evidence
    assert not ready.unquoted


# -- the check that could not see it ----------------------------------------


def test_a_height_is_not_a_percentage(west_linn: Layer, store: ProvenanceStore) -> None:
    """R-10 allows 35 percent coverage and a 35 ft building. The coverage
    value cited the height line, the line printed 35, and every check passed.
    """
    assert cites_a_different_unit("35 ft", "max_coverage_pct", 35)
    assert cites_a_different_unit("Maximum building height 35 ft", "max_coverage_pct", 35)
    assert cites_a_different_unit("50%", "setback_front_ft", 50)

    coverage = west_linn.zones["R-10"].values["max_coverage_pct"]
    height = west_linn.zones["R-10"].values["max_height_ft"]
    assert coverage.prov.quote != height.prov.quote
    assert store.quote(coverage.prov.quote).strip() == "35%"


def test_a_bare_number_still_evidences_anything() -> None:
    """Which is why this check is narrow. Four jurisdictions publish tables
    with the unit in the column header and bare digits in the cells, and a
    check that wanted a unit on the line would refuse all of them."""
    assert not cites_a_different_unit("35", "max_coverage_pct", 35)
    assert not cites_a_different_unit("b. Slope of plane (degrees) 45", "max_coverage_pct", 45)


def test_a_line_that_states_it_both_ways_is_not_a_misquote() -> None:
    """Codes do print "35% (35 ft)" shapes, and one right printing is enough
    — the claim is that the line never says it, not that it once says it
    wrongly."""
    assert not cites_a_different_unit("Coverage 35 ft of frontage, 35%", "max_coverage_pct", 35)


def test_it_says_nothing_about_a_number_the_line_does_not_print() -> None:
    """A separate rung's job, and answering it here would report one fault as
    two."""
    assert not cites_a_different_unit("40 ft", "max_coverage_pct", 35)


def test_only_the_kinds_that_share_a_number_space_are_checked() -> None:
    """A count, a ratio and an enum have no unit to disagree with. Guessing at
    one would cost more than the error it caught."""
    assert not cites_a_different_unit("4 units", "max_units", 4)
    assert not cites_a_different_unit("0.60", "max_far", 0.60)


# -- the two chapters every table points at ---------------------------------


def test_the_sidewall_chapter_reaches_this_building(store: ProvenanceStore) -> None:
    """Every dimensional table in all nine chapters ends "the sidewall
    provisions of Chapter 43 CDC shall apply", and the obvious reading — a
    chapter titled Single-Family Residential — is the wrong one. The city
    defines single-family attached as two or more units side by side on
    separate lots, "further defined as a duplex, triplex, or quadplex", which
    is this pod in the unit-lot configuration.
    """
    applies = store.quote(f"{WEST_LINN}/43.sidewall.txt#L23")
    assert "single-family attached and detached" in applies

    meaning = store.quote(f"{WEST_LINN}/02.definitions.txt#L947")
    assert "attached side by side" in meaning
    assert "quadplex" in meaning


def test_what_it_asks_for_is_not_a_dimension(store: ProvenanceStore) -> None:
    """Which is why no value cites it. It divides a wall into planes; it does
    not move the wall. The pod's side elevation is 936 sq ft against a 700 sq
    ft trigger, so this is a real standard that the value model cannot hold —
    written into the layer's notes rather than encoded as a setback nobody
    could find on the page."""
    standard = store.quote(f"{WEST_LINN}/43.sidewall.txt#L33")
    assert "distinct planes of 700 square feet or less" in standard

    # 36 ft deep, 26 ft to the roof: the side elevation clears the trigger by
    # a third, so the chapter reaches this building rather than passing over it.
    assert 36 * 26 > 700

    exemptions = store.quote(f"{WEST_LINN}/43.sidewall.txt#L39,L49")
    assert "20 feet or more from the side lot line" in exemptions
    assert "22 feet as measured from grade" in exemptions


def test_the_steep_lot_chapter_only_ever_loosens(store: ProvenanceStore) -> None:
    """Nineteen mentions across nine chapters, ten beside a number this screen
    uses, and it was the loudest unread reference in the county. It grants a
    three-foot garage setback on a 25 percent slope and holds everything else
    to the zone, and it lets a building on a slope exceed the zone's height.
    Nothing in it is a new ceiling, so nothing cites it."""
    trigger = store.quote(f"{WEST_LINN}/41.steep-lots.txt#L43")
    assert "average slope of a building site is 25 percent or greater" in trigger

    relief = store.quote(f"{WEST_LINN}/41.steep-lots.txt#L45")
    assert "front yard setback for the garage shall be three feet" in relief
    assert "All structures other than the garage shall meet the setback requirement of the underlying zone" in relief

    height = store.quote(f"{WEST_LINN}/41.steep-lots.txt#L55")
    assert "Exceptions to the maximum building height standards" in height


def test_the_ratio_is_the_one_the_screen_computes(store: ProvenanceStore) -> None:
    """A ratio is only a number until the code says what it divides. West Linn
    defines FAR as habitable floor area over lot area and works the example,
    which is what the screen computes — footprint times storeys over lot. Had
    it counted ground floor only, or included the garages it names as
    excluded, the same 0.60 would be a different standard."""
    meaning = store.quote(f"{WEST_LINN}/02.definitions.txt#L440")

    assert "percentage of the total lot size that can be built as habitable space" in meaning
    assert "10,000 X 0.45 = 4,500" in meaning
    assert "does not include or apply to attached garages" in meaning
