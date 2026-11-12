"""Glass on every non-street wall, and no window within 3 ft of a side or rear
lot line (FOLLOWUPS 186; Steph 2026-11-12, rulings.yaml
2026-11-12-gresham-glass-each-facade).

Gresham 7.0420(I)(2) asks 5 percent clear glass of each facade that does not
face a street; ORSC Table R302.1 allows no opening in a wall under 3 ft from a
side or rear lot line. A plan whose end wall stands that close is moved where
the fit allows, else it is RED.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from shapely.geometry import box

from flats.encode.load import load_trusted
from flats.geom.edges import Edge, EdgeClass
from flats.ingest.wall_openings import RAY_REACH_FT, gap_ft, wall_opening_gap
from flats.score.flags import Colour
from flats.score.relief import NO_ZONING_RELIEF
from flats.score.screen import CHECK_FIELD, WALL_OPENINGS, WALL_OPENINGS_DRAWN, _MEASURED_FLAG
from flats.score.slack import Verdict
from flats.tests.test_round2_rulings import F, R, S, _edges, check, facts, rules, run

pytestmark = pytest.mark.unit

GRESHAM = "or/multnomah/gresham"
GLASS = {"facade_glass_other_pct": 5, "wall_opening_min_ft": 3}
#: Gresham 7.0420's opening list, as the corpus holds it (LDR-GB has no block).
ZONES_7_0420 = (
    "LDR-5", "LDR-7", "TR", "TLDR", "MDR-12", "MDR-24", "OFR", "LDR-PV", "MDR-PV", "HDR-PV",
    "VLDR-SW", "LDR-SW", "CMF", "CMU", "SC", "SC-RJ", "DCC", "DMU", "DTM", "DRL-1", "DRL-2",
)


def codes(result) -> set[str]:
    return {f.code for f in result.flags}


# --- the screen ---------------------------------------------------------------


def test_the_check_reads_the_glass_field_and_no_relief_reaches_it() -> None:
    # The threshold is the building code's distance, stated for every zone, so
    # a bind cites R302.1 and an unmeasured check is never "not encoded".
    assert CHECK_FIELD[WALL_OPENINGS] == "wall_opening_min_ft"
    assert _MEASURED_FLAG[WALL_OPENINGS_DRAWN] == "MEASURE-WALL-OPENINGS"
    assert WALL_OPENINGS in NO_ZONING_RELIEF


def test_an_end_wall_under_3_ft_from_a_side_line_is_red() -> None:
    lot = facts(wall_opening_gap_ft=1.18, wall_opening_tried=True)
    assert run(lot, rules()).colour is Colour.green
    got = run(lot, rules(**GLASS))
    assert check(got, WALL_OPENINGS).verdict is Verdict.fails
    assert got.colour is Colour.red


def test_a_wall_3_ft_off_the_line_may_have_windows() -> None:
    got = run(facts(wall_opening_gap_ft=3.0, wall_opening_tried=True), rules(**GLASS))
    assert check(got, WALL_OPENINGS).verdict is Verdict.passes
    assert got.colour is Colour.green


def test_tried_with_nothing_drawn_is_held_never_passed() -> None:
    got = run(facts(wall_opening_tried=True), rules(**GLASS))
    assert check(got, WALL_OPENINGS) is None
    assert "MEASURE-WALL-OPENINGS" in codes(got)
    assert got.colour is not Colour.green


def test_nobody_measuring_leaves_the_check_unrun() -> None:
    got = run(facts(), rules(**GLASS))
    assert check(got, WALL_OPENINGS) is None
    assert WALL_OPENINGS in got.unchecked
    assert "MEASURE-WALL-OPENINGS" not in codes(got)


def test_a_zone_asking_no_glass_on_other_walls_is_not_read() -> None:
    lot = facts(wall_opening_gap_ft=0.0, wall_opening_tried=True)
    got = run(lot, rules(wall_opening_min_ft=3))
    assert check(got, WALL_OPENINGS) is None
    assert WALL_OPENINGS not in got.unchecked
    assert got.colour is Colour.green


# --- the measure --------------------------------------------------------------

LOT = [(0, 0, 100, 0, F), (100, 0, 100, 140, S), (100, 140, 0, 140, R), (0, 140, 0, 0, S)]


def _ring(geom) -> list[list[float]]:
    return [list(p) for p in geom.exterior.coords]


def test_an_end_wall_flush_with_a_side_line_measures_nought() -> None:
    edges = _edges(LOT, [0.0])
    assert gap_ft(_ring(box(0, 5, 80, 35)), edges.edges) == 0.0
    assert gap_ft(_ring(box(3, 5, 83, 35)), edges.edges) == 3.0
    # 1.18 ft off the right-hand line, the rel7 example's distance.
    assert gap_ft(_ring(box(18.82, 5, 98.82, 35)), edges.edges) == pytest.approx(1.18)


def test_a_wall_facing_the_street_is_not_measured_to_its_line() -> None:
    # At a zero front setback the front wall is on the street line: the code
    # measures it to the street's centre line.
    edges = _edges(LOT, [0.0])
    assert gap_ft(_ring(box(10, 0, 90, 30)), edges.edges) == 10.0


def test_a_line_square_to_the_wall_is_not_what_it_is_measured_to() -> None:
    # The side line runs on past the end of the back wall: the back wall's
    # rays never meet it, the end wall's do.
    edges = _edges(LOT, [0.0])
    assert gap_ft(_ring(box(10, 5, 90, 35)), edges.edges) == 10.0


def test_a_building_over_the_line_by_a_cell_reads_nought() -> None:
    edges = _edges(LOT, [0.0])
    assert gap_ft(_ring(box(-0.3, 5, 79.7, 35)), edges.edges) == 0.0


def test_an_alley_vouched_for_its_whole_length_is_a_public_way() -> None:
    def lot(cover):
        return (
            Edge(x1=0, y1=0, x2=100, y2=0, length_ft=100, bearing_deg=90.0, cls=EdgeClass.front),
            Edge(x1=100, y1=0, x2=100, y2=140, length_ft=140, bearing_deg=0.0, cls=EdgeClass.side,
                 alley=True, cover=cover),
            Edge(x1=100, y1=140, x2=0, y2=140, length_ft=100, bearing_deg=90.0, cls=EdgeClass.rear),
            Edge(x1=0, y1=140, x2=0, y2=0, length_ft=140, bearing_deg=0.0, cls=EdgeClass.side),
        )

    ring = _ring(box(19, 5, 99, 35))
    assert gap_ft(ring, lot("1111")) == 19.0
    assert gap_ft(ring, lot(None)) == 19.0
    # Partly a neighbour's line, or never measured: read as a neighbour's.
    assert gap_ft(ring, lot("1100")) == 1.0
    assert gap_ft(ring, lot("")) == 1.0


def test_a_through_lot_end_renamed_rear_is_still_a_street() -> None:
    through = [(0, 0, 100, 0, F), (100, 0, 100, 40, S), (100, 40, 0, 40, R), (0, 40, 0, 0, S)]
    edges = _edges(through, [0.0])
    ring = _ring(box(10, 8, 90, 38))
    assert gap_ft(ring, edges.edges) == 2.0
    street = Edge(x1=100, y1=40, x2=0, y2=40, length_ft=100, bearing_deg=90.0, cls=EdgeClass.front)
    assert gap_ft(ring, edges.edges, (street,)) == 10.0


def test_nothing_drawn_measures_nothing_and_far_walls_read_the_reach() -> None:
    edges = _edges(LOT, [0.0])
    s = SimpleNamespace(drawing={"fits": False}, lot=SimpleNamespace(edges=edges))
    assert wall_opening_gap(s) is None
    wide = [(0, 0, 400, 0, F), (400, 0, 400, 400, S), (400, 400, 0, 400, R), (0, 400, 0, 0, S)]
    assert gap_ft(_ring(box(160, 0, 240, 30)), _edges(wide, [0.0]).edges) == RAY_REACH_FT


# --- the encoding -------------------------------------------------------------


@pytest.fixture(scope="module")
def corpus():
    return load_trusted(strict=False).rules


@pytest.mark.parametrize("zone", ZONES_7_0420)
def test_every_7_0420_zone_asks_glass_on_each_other_facade(corpus, zone) -> None:
    got = corpus.resolve(GRESHAM, zone)
    assert got.get("facade_glass_other_pct") == 5
    assert got.get("wall_opening_min_ft") == 3


@pytest.mark.parametrize("zone", ["RTC", "CC"])
def test_a_zone_off_the_7_0420_list_asks_none(corpus, zone) -> None:
    assert corpus.resolve(GRESHAM, zone).get("facade_glass_other_pct") is None


# --- FOLLOWUPS 187: the other places that put glass on a non-street wall ----------


def test_a_window_count_on_every_elevation_reads_the_same_as_a_share() -> None:
    lot = facts(wall_opening_gap_ft=1.18, wall_opening_tried=True)
    got = run(lot, rules(window_spacing_ft=15, wall_opening_min_ft=3))
    assert check(got, WALL_OPENINGS).verdict is Verdict.fails
    assert got.colour is Colour.red


@pytest.mark.parametrize("zone", ["DEM", "DCL", "CNTH", "CNTM", "CNRM"])
def test_gresham_downtown_and_civic_ask_it_of_the_townhouse_path_only(corpus, zone) -> None:
    # 4.1152 S9(b) and 4.1252 S13(b) sit under the Townhouse heading; the
    # one-lot quadplex is excepted (4.1102(C)) or NP (Table 4.1220(A)).
    assert corpus.resolve(GRESHAM, zone, ("unit_lots",)).get("facade_glass_other_pct") == 5
    assert corpus.resolve(GRESHAM, zone).get("facade_glass_other_pct") is None


BEAVERTON = "or/washington/beaverton"
#: BDC 10.25's Commercial and Multiple Use districts outside Downtown (70.05.15.7
#: exempts Downtown from 60.05) that allow the pod: OI-WS, C-WS and SC-E refuse
#: it and carry the use row alone.
BEAVERTON_C_MU = (
    "NS", "CS", "CC", "GC", "CM-CS", "CM-HDR", "RC-E", "TC-MU", "TC-HDR", "SC-MU", "SC-HDR",
    "SC-S",
)


@pytest.mark.parametrize("zone", BEAVERTON_C_MU)
def test_beaverton_commercial_and_multiple_use_zones_ask_30(corpus, zone) -> None:
    assert corpus.resolve(BEAVERTON, zone).get("facade_glass_other_pct") == 30


@pytest.mark.parametrize("zone", ["RC-BC", "RC-OT", "RC-MU", "RC-DT", "MR", "RMA"])
def test_beaverton_downtown_and_residential_zones_do_not(corpus, zone) -> None:
    assert corpus.resolve(BEAVERTON, zone).get("facade_glass_other_pct") is None


OREGON_CITY = "or/clackamas/oregon-city"


@pytest.mark.parametrize("zone", ["R-10", "R-8", "R-6", "R-5", "R-3.5", "R-2"])
def test_oregon_city_counts_windows_in_the_concept_plan_areas_only(corpus, zone) -> None:
    for area in ("oregon_city_south_end", "oregon_city_park_place"):
        assert corpus.resolve(OREGON_CITY, zone, (area,)).get("window_spacing_ft") == 15
    outside = corpus.resolve(OREGON_CITY, zone)
    assert outside.get("window_spacing_ft") is None
    # A variant, so a lot the boundary cuts is an open question, not outside.
    assert "oregon_city_south_end" in outside.levers


HILLSBORO = "or/washington/hillsboro"
SOUTH_HILLSBORO_ZONES = ("R-10", "R-8.5", "R-7", "R-6", "R-4.5", "MR-1", "MR-2", "MR-3", "MU-VTC")


@pytest.mark.parametrize("zone", SOUTH_HILLSBORO_ZONES)
def test_south_hillsboro_asks_8_of_each_side_inside_the_plan_district(corpus, zone) -> None:
    inside = corpus.resolve(HILLSBORO, zone, ("south_hillsboro_plan_district",))
    assert inside.get("facade_glass_other_pct") == 8
    assert corpus.resolve(HILLSBORO, zone).get("facade_glass_other_pct") is None


def test_the_south_hillsboro_area_is_the_city_plan_area_for_its_base_zones(corpus) -> None:
    from flats.geom.drawn import load_area
    from flats.rules.conditions import DRAWN_CONDITIONS

    assert "south_hillsboro_plan_district" in DRAWN_CONDITIONS
    (area,) = [
        a for a in corpus.layers[HILLSBORO].drawn_areas.values()
        if a.condition == "south_hillsboro_plan_district"
    ]
    assert set(area.zones) == set(SOUTH_HILLSBORO_ZONES)
    assert load_area(area.file).area > 0


def test_gladstone_asks_it_of_c2_in_the_town_center(corpus) -> None:
    inside = corpus.resolve("or/clackamas/gladstone", "C2", ("gladstone_town_center",))
    assert inside.get("facade_glass_other_pct") == 40
    outside = corpus.resolve("or/clackamas/gladstone", "C2")
    assert outside.get("facade_glass_other_pct") is None
    assert "gladstone_town_center" in outside.levers


def test_the_building_code_line_is_stated_for_every_zone(corpus) -> None:
    assert corpus.resolve("or/multnomah/portland", "R5").get("wall_opening_min_ft") == 3


# --- the bridge ---------------------------------------------------------------


def _screened(corpus, wide: float, deep: float, zone: str):
    import shapely

    from flats.designs.model import load_catalog
    from flats.ingest.quadfit import lot_from_row, screen_lot
    from flats.score import relief, slack
    from flats.tests.test_fire import X0, Y0, bridge_row

    edges = [
        [X0, Y0, X0 + wide, Y0, "F"],
        [X0 + wide, Y0, X0 + wide, Y0 + deep, "S"],
        [X0 + wide, Y0 + deep, X0, Y0 + deep, "R"],
        [X0, Y0 + deep, X0, Y0, "S"],
    ]
    whole = shapely.to_wkb(box(X0, Y0, X0 + wide, Y0 + deep))
    row = bridge_row(
        TLID="1S3E99AA  -99999", jurisdiction="gresham", zone=zone, area_sqft=wide * deep,
        lot_depth_ft=deep, frontage_ft=wide, lot_width_ft=wide, edges_json=json.dumps(edges),
        wkb=whole, lot_wkb=whole,
    )
    lot = lot_from_row(row, corpus.layers)
    (s,) = screen_lot(
        lot, [load_catalog().latest("pod80x30")], rules=corpus, policy=slack.load_policy(),
        relief=relief.load_policy(), step_deg=30.0,
    )
    return s


def test_the_bridge_moves_the_pod_off_the_side_line_where_the_lot_allows(corpus) -> None:
    # SC has no side setback: the drawing stands the pod in the street corner,
    # its end wall on the side line, and the lot is wide enough to slide it.
    s = _screened(corpus, 120.0, 160.0, "SC")
    assert s.facts.wall_opening_tried
    assert s.facts.wall_opening_gap_ft is not None and s.facts.wall_opening_gap_ft >= 3.0
    assert check(s.signed, WALL_OPENINGS).verdict is Verdict.passes
    assert s.signed.colour is Colour.green


def test_the_bridge_reads_red_where_no_placement_clears_3_ft(corpus) -> None:
    # 93 ft: the 80 ft pod and its 12 ft lane leave a foot to share.
    s = _screened(corpus, 93.0, 140.0, "SC")
    assert s.facts.wall_opening_gap_ft is not None and s.facts.wall_opening_gap_ft < 3.0
    assert WALL_OPENINGS in {c.check for c in s.signed.binds}
    assert s.signed.colour is Colour.red
    assert s.screening.colour is not Colour.green


def test_a_zone_off_the_list_keeps_its_corner_placement(corpus) -> None:
    s = _screened(corpus, 93.0, 140.0, "RTC")
    assert not s.facts.wall_opening_tried
    assert check(s.signed, WALL_OPENINGS) is None
