"""Which street lot lines run along a mapped corridor (flats/geom/corridor.py).

Portland's Map 130-1 puts a 10 ft setback on a street lot line adjacent to
one of five Civic Corridors; Map 120-1 lets RM2 cover 70 percent on a site
that abuts a corridor. These tests pin what "adjacent" is -- along the
line, across the right-of-way, parallel -- and where the fact is answered.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import shapely
from shapely.geometry import LineString, mapping

from flats.geom.corridor import (
    CORRIDOR_FACTS,
    REACH_FT,
    CorridorMap,
    Lines,
    load_maps,
    observed_corridors,
    off_corridor,
    off_corridor_lines,
    on_corridor,
    street_name,
)
from flats.geom.edges import Edge, EdgeClass
from flats.geom.envelope import Setbacks
from flats.ingest.quadfit import OBSERVABLE, envelope_for, lot_from_row, observed_facts, setbacks_for
from flats.rules.conditions import CONDITIONS, close_entailed

pytestmark = pytest.mark.unit

PDX = "or/multnomah/portland"
X0, Y0 = 7_650_000.0, 680_000.0

# A 50 x 100 lot, street along the south edge. The street's centreline --
# the line the corridor map draws -- runs 30 ft south of the lot line, the
# middle of a 60 ft right-of-way, and on past both corners.
FRONT = [X0, Y0, X0 + 50, Y0, "F"]
EDGES = [
    FRONT,
    [X0 + 50, Y0, X0 + 50, Y0 + 100, "S"],
    [X0 + 50, Y0 + 100, X0, Y0 + 100, "R"],
    [X0, Y0 + 100, X0, Y0, "S"],
]
ALONG = LineString([(X0 - 500, Y0 - 30), (X0 + 500, Y0 - 30)])


def cmap(*lines: LineString, condition: str = "civic_corridor_setback") -> CorridorMap:
    return CorridorMap.from_lines(condition, [PDX], lines)


def test_the_corridor_facts_are_registered_site_facts_the_bridge_observes() -> None:
    assert CORRIDOR_FACTS == ("civic_corridor", "civic_corridor_setback", "civic_corridor_setback_all_streets")
    for name in CORRIDOR_FACTS:
        assert CONDITIONS[name].kind == "site_fact"
        assert name in OBSERVABLE


def test_a_street_line_across_the_right_of_way_from_the_corridor_is_on_it() -> None:
    assert on_corridor(FRONT, cmap(ALONG))


def test_a_corridor_one_block_over_is_not() -> None:
    far = LineString([(X0 - 500, Y0 - 30 - REACH_FT - 200), (X0 + 500, Y0 - 30 - REACH_FT - 200)])
    assert not on_corridor(FRONT, cmap(far))


def test_the_cross_street_at_the_corner_is_not() -> None:
    # A corridor running north-south past the lot's west corner touches the
    # front line's end within reach but crosses it: the parallel test keeps
    # the corner from counting.
    cross = LineString([(X0 - 30, Y0 - 500), (X0 - 30, Y0 + 500)])
    assert not on_corridor(FRONT, cmap(cross))


def test_a_corridor_that_ends_part_way_along_the_line() -> None:
    # Drawn to the line's midpoint and a little beyond: still on it.
    past_half = LineString([(X0 - 500, Y0 - 30), (X0 + 30, Y0 - 30)])
    assert on_corridor(FRONT, cmap(past_half))
    # Drawn only to its first tenth: not.
    stub = LineString([(X0 - 500, Y0 - 30), (X0 + 5, Y0 - 30)])
    assert not on_corridor(FRONT, cmap(stub))


def test_only_street_lines_count() -> None:
    # A corridor behind the lot, 30 ft past the rear line: the rear line is
    # not a street line, so it never asks.
    behind = LineString([(X0 - 500, Y0 + 130), (X0 + 500, Y0 + 130)])
    assert observed_corridors(EDGES, PDX, [cmap(behind)]) == {"civic_corridor_setback": False}


def test_answered_only_where_the_map_serves_and_only_with_edges() -> None:
    maps = [cmap(ALONG), cmap(ALONG, condition="civic_corridor")]
    assert observed_corridors(EDGES, PDX, maps) == {
        "civic_corridor_setback": True,
        "civic_corridor": True,
    }
    # Gresham's civic_corridor is Gresham's own map: never answered from Portland's.
    assert observed_corridors(EDGES, "or/multnomah/gresham", maps) == {}
    assert observed_corridors([], PDX, maps) == {}


def test_load_maps_reads_the_snapshot_and_skips_what_is_missing(tmp_path: Path) -> None:
    fc = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": mapping(ALONG)}],
    }
    (tmp_path / "corridor_setbacks_pdx.geojson").write_text(json.dumps(fc), encoding="utf-8")
    maps = load_maps(tmp_path)
    assert [m.condition for m in maps] == ["civic_corridor_setback"]
    assert maps[0].covers(PDX) and not maps[0].covers("or/multnomah/gresham")
    assert maps[0].streets is None
    assert on_corridor(FRONT, maps[0])
    # With the snapshot's streets: only those near a corridor are kept.
    far = LineString([(X0 + 90_000, Y0), (X0 + 91_000, Y0)])
    net = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"PREFIX": "SE", "STREETNAME": "DIVISION", "FTYPE": "ST"},
             "geometry": mapping(ALONG)},
            {"type": "Feature", "properties": {"STREETNAME": "ELSEWHERE"}, "geometry": mapping(far)},
        ],
    }
    (tmp_path / "rlis_streets.geojson").write_text(json.dumps(net), encoding="utf-8")
    (with_streets,) = load_maps(tmp_path)
    assert with_streets.streets is not None
    assert with_streets.streets.names == ("SE DIVISION ST",)
    assert on_corridor(FRONT, with_streets)


def _row(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "TLID": "1S2E20AA  -15100",
        "jurisdiction": "portland",
        "zone": "CM2",
        "tier": "A",
        "area_sqft": 5000.0,
        "frontage_ft": 50.0,
        "lot_width_ft": 50.0,
        "lot_depth_ft": 100.0,
        "edges_json": json.dumps(EDGES),
        "front_bearings_json": "[0.0]",
        "fronts_cul_de_sac": False,
        "split_zone": False,
        "ovl_fema_sfha": False,
        "ovl_fema_floodway": False,
        "sewer_main_dist_ft": 12.0,
        "in_sewer_district": None,
        "wkb": shapely.to_wkb(shapely.box(X0 + 5, Y0 + 10, X0 + 45, Y0 + 95)),
    }
    base.update(over)
    return base


def test_the_bridge_asks_only_with_the_maps_in_hand() -> None:
    assert "civic_corridor_setback" not in observed_facts(_row())
    got = observed_facts(_row(), corridors=[cmap(ALONG)])
    assert got["civic_corridor_setback"] is True
    lot = lot_from_row(_row(), corridors=[cmap(ALONG)])
    assert lot.observed["civic_corridor_setback"] is True
    # A Gresham lot on the same line: unasked.
    assert "civic_corridor_setback" not in observed_facts(
        _row(jurisdiction="gresham"), corridors=[cmap(ALONG)]
    )


@pytest.fixture(scope="module")
def pdx_rules():
    from flats.rules.loader import load_rules
    from flats.rules.resolver import RuleSet

    return RuleSet(load_rules())


@pytest.mark.parametrize("zone", ["CM1", "CM2", "CM3", "CE", "CX", "CR"])
def test_the_ten_foot_setback_follows_map_130_1_not_map_120_1(pdx_rules, zone: str) -> None:
    """33.130.215.B.1.a: 10 ft from a street lot line adjacent to a Civic
    Corridor shown on Map 130-1; none elsewhere. A lot on one of Map 120-1's
    158 corridors that is not one of 130-1's five stretches keeps zero."""

    def front(*conditions: str) -> object:
        return pdx_rules.resolve(PDX, zone, conditions=list(conditions)).values["setback_front_ft"].value

    # CR and CM1: "none". CM2 and up: the across-the-street 5 of
    # 33.130.215.B.1.b, the street number on every line the screen cannot
    # show faces no residential zone (see ACROSS below).
    base = 0 if zone in LOW_ZONES else 5
    assert front() == base
    assert front("civic_corridor") == base
    assert front("civic_corridor_setback") == 10


# --- with the street network: which street does the line abut? --------------


def streets(*named: tuple[LineString, str]) -> Lines:
    return Lines.build([g for g, _ in named], [n for _, n in named])


def test_street_names_are_spelled_one_way() -> None:
    assert street_name("SE 122nd AVENUE - CIVIC CORRIDOR") == "SE 122ND AVE"
    assert street_name("SW BARBUR BLVD- CIVIC CORRIDOR") == "SW BARBUR BLVD"
    assert street_name("SE  DIVISION ST ") == "SE DIVISION ST"
    assert street_name(None) == ""


def test_a_wide_street_is_the_corridor_when_the_line_abuts_it_by_name() -> None:
    # Barbur: the corridor's line drawn 90 ft out, past a 50 ft reach; the
    # near carriageway's centreline 40 ft out carries the corridor's name.
    drawn = LineString([(X0 - 500, Y0 - 90), (X0 + 500, Y0 - 90)])
    near_lane = LineString([(X0 - 500, Y0 - 40), (X0 + 500, Y0 - 40)])
    net = streets((near_lane, "SW BARBUR BLVD"))
    on = CorridorMap.from_lines("civic_corridor_setback", [PDX], [drawn], ["SW BARBUR BLVD- CIVIC CORRIDOR"], net)
    assert on_corridor(FRONT, on)
    # The same geometry without the network: the fallback misses it.
    assert not on_corridor(FRONT, cmap(drawn))


def test_the_next_block_abuts_its_own_street_first() -> None:
    # The lot line is 130 ft from Division's drawn line, but the street 30 ft
    # out is SE Clinton: the lot is a block back.
    drawn = LineString([(X0 - 500, Y0 - 130), (X0 + 500, Y0 - 130)])
    clinton = LineString([(X0 - 500, Y0 - 30), (X0 + 500, Y0 - 30)])
    division = LineString([(X0 - 500, Y0 - 130), (X0 + 500, Y0 - 130)])
    net = streets((clinton, "SE CLINTON ST"), (division, "SE DIVISION ST"))
    off = CorridorMap.from_lines("civic_corridor_setback", [PDX], [drawn], ["SE DIVISION ST - CIVIC CORRIDOR"], net)
    assert not on_corridor(FRONT, off)


def test_a_centreline_on_the_drawn_line_is_the_corridor_whatever_its_name() -> None:
    drawn = LineString([(X0 - 500, Y0 - 32), (X0 + 500, Y0 - 32)])
    ramp = LineString([(X0 - 500, Y0 - 30), (X0 + 500, Y0 - 30)])
    net = streets((ramp, "SW CAPITOL HWY-BARBUR BLVD RAMP"))
    on = CorridorMap.from_lines("civic_corridor", [PDX], [drawn], ["SW BARBUR BLVD"], net)
    assert on_corridor(FRONT, on)
    # With no centreline beside it, the drawn line decides as with no network.
    bare = CorridorMap.from_lines("civic_corridor", [PDX], [drawn], ["SW BARBUR BLVD"], streets())
    assert on_corridor(FRONT, bare)


def test_a_street_further_out_than_s4_reaches_is_not_the_one_the_line_abuts() -> None:
    # Belmont's centreline and drawn line both 110 ft out, nothing nearer:
    # the lot line abuts no street there, so it is not on Belmont.
    drawn = LineString([(X0 - 500, Y0 - 110), (X0 + 500, Y0 - 110)])
    net = streets((drawn, "SE BELMONT ST"))
    off = CorridorMap.from_lines("civic_corridor", [PDX], [drawn], ["SE BELMONT ST"], net)
    assert not on_corridor(FRONT, off)


def test_the_setback_map_takes_either_reading_the_coverage_map_only_the_street() -> None:
    # The line abuts a transit-centre loop 12 ft out; Barbur's drawn line is
    # 48 ft out. The street reading says the loop, not Barbur. For the
    # setback a miss is a false GREEN, so the drawn line within reach still
    # counts; for RM2 coverage a false hit is, so it does not.
    drawn = LineString([(X0 - 500, Y0 - 48), (X0 + 500, Y0 - 48)])
    loop = LineString([(X0 - 500, Y0 - 12), (X0 + 500, Y0 - 12)])
    net = streets((loop, "BARBUR TC"))
    names = ["SW BARBUR BLVD"]
    assert on_corridor(FRONT, CorridorMap.from_lines("civic_corridor_setback", [PDX], [drawn], names, net))
    assert not on_corridor(FRONT, CorridorMap.from_lines("civic_corridor", [PDX], [drawn], names, net))


# --- Map 130-1's 20 ft maximum: EVERY street line, never ANY -----------------
#
# 33.130.215.C.1 (33.130.txt L957-L959): "the maximum a building can be set
# back from a street lot line is 10 feet, except on Civic Corridors shown on
# Map 130-1, where the maximum set back is 20 feet." Table 130-2 prints it in
# all six zones (L653-L654). A raised maximum loosens, so it may not ride on
# the ANY-line, read-either-way `civic_corridor_setback`.

EVERY = "civic_corridor_setback_all_streets"
C_ZONES = ("CM1", "CM2", "CM3", "CE", "CX", "CR")
# 33.130.215.B.1.b: "The setbacks do not apply in the CR or CM1 zones".
LOW_ZONES = ("CM1", "CR")

# The same 50 x 100 lot on a corner: its west line is a street line too, on a
# north-south cross street 30 ft out that is not a corridor.
WEST = [X0, Y0 + 100, X0, Y0, "F"]
CORNER = [FRONT, EDGES[1], EDGES[2], WEST]
CROSS = LineString([(X0 - 30, Y0 - 500), (X0 - 30, Y0 + 500)])


def division(*lines: LineString) -> CorridorMap:
    """Map 130-1's Division stretch with the street network in hand."""
    net = streets((ALONG, "SE DIVISION ST"), (CROSS, "SE 82ND AVE"))
    drawn = list(lines) or [ALONG]
    return CorridorMap.from_lines(
        "civic_corridor_setback", [PDX], drawn, ["SE DIVISION ST - CIVIC CORRIDOR"] * len(drawn), net
    )


@pytest.mark.parametrize("zone", C_ZONES)
def test_the_twenty_foot_maximum_follows_every_street_line_not_any(pdx_rules, zone: str) -> None:
    def most(*conditions: str) -> object:
        return pdx_rules.resolve(PDX, zone, conditions=list(conditions)).values["setback_front_max_ft"].value

    assert most() == 10
    # The ANY-line fact tightens the minimum and leaves the maximum at 10.
    assert most("civic_corridor_setback") == 10
    assert most("civic_corridor_setback", EVERY) == 20


@pytest.mark.parametrize("zone", C_ZONES)
def test_the_twenty_is_quoted_from_the_corridor_row_and_the_sentence(zone: str) -> None:
    from flats.rules.loader import load_rules

    value = load_rules()[PDX].zones[zone].values["setback_front_max_ft"]
    (variant,) = value.variants
    assert variant.value == 20
    assert tuple(variant.when) == (EVERY,)
    assert variant.prov.quote == "or/multnomah/portland/33.130.txt#L618,L653-L654,L957-L959"


def test_the_minimum_never_passes_the_maximum_on_a_stretch(pdx_rules) -> None:
    for zone in C_ZONES:
        for conditions in ([], ["civic_corridor_setback"], ["civic_corridor_setback", EVERY]):
            got = pdx_rules.resolve(PDX, zone, conditions=conditions).values
            assert got["setback_front_ft"].value <= got["setback_front_max_ft"].value, (zone, conditions)


def test_an_interior_lot_on_division_has_every_street_line_on_it() -> None:
    assert observed_corridors(EDGES, PDX, [division()]) == {"civic_corridor_setback": True, EVERY: True}


def test_a_corner_lot_with_one_line_on_division_keeps_ten_on_both(pdx_rules) -> None:
    # The per-lot, per-line trap: the rule gives Division's line 20 and the
    # side street 10, and the lot holds one number. ANY says True (the 10 ft
    # minimum on both lines, the tight side); EVERY says False, so the lot's
    # maximum stays 10 -- never 20 on a line the corridor does not touch.
    got = observed_corridors(CORNER, PDX, [division()])
    assert got == {"civic_corridor_setback": True, EVERY: False}
    held = [name for name, value in close_entailed(got).items() if value]
    assert pdx_rules.resolve(PDX, "CM2", conditions=held).values["setback_front_max_ft"].value == 10


def test_the_drawn_line_alone_tightens_but_never_relaxes() -> None:
    # The loop case above: the line abuts a transit-centre loop 12 ft out and
    # Barbur's drawn line is 48 ft out. The minimum takes the drawn line; the
    # maximum's relaxation does not.
    drawn = LineString([(X0 - 500, Y0 - 48), (X0 + 500, Y0 - 48)])
    loop = LineString([(X0 - 500, Y0 - 12), (X0 + 500, Y0 - 12)])
    cm = CorridorMap.from_lines(
        "civic_corridor_setback", [PDX], [drawn], ["SW BARBUR BLVD"], streets((loop, "BARBUR TC"))
    )
    assert observed_corridors(EDGES, PDX, [cm]) == {"civic_corridor_setback": True, EVERY: False}


def test_a_stretch_that_ends_part_way_along_the_line_does_not_relax_it() -> None:
    past_half = LineString([(X0 - 500, Y0 - 30), (X0 + 30, Y0 - 30)])
    got = observed_corridors(EDGES, PDX, [division(past_half)])
    assert got == {"civic_corridor_setback": True, EVERY: False}


def test_without_the_street_network_the_every_line_fact_is_unasked() -> None:
    assert observed_corridors(EDGES, PDX, [cmap(ALONG)]) == {"civic_corridor_setback": True}


def test_every_line_on_a_stretch_is_at_least_one_line_on_it() -> None:
    assert close_entailed({EVERY: True})["civic_corridor_setback"] is True
    assert close_entailed({"civic_corridor_setback": False})[EVERY] is False


# --- the 10 ft minimum PER LINE (FOLLOWUPS 8(d)) ------------------------------
#
# Table 130-2's row is "Street Lot Line abutting selected Civic Corridors":
# one line. The lot-level fact gives 10 to every street line (the tight side,
# kept for every reader without edges); the envelope gives back, line by
# line, a street line read surely OFF every stretch, at the plain "Street Lot
# Line" row -- `setback_street_off_corridor_ft`.

OFF = "setback_street_off_corridor_ft"


def _cut(edges: list, **over: object) -> dict[str, object]:
    return _row(
        edges_json=json.dumps(edges),
        tier="B" if sum(1 for e in edges if e[4] == "F") > 1 else "A",
        lot_wkb=shapely.to_wkb(shapely.box(X0, Y0, X0 + 50, Y0 + 100)),
        **over,
    )


def test_the_side_street_of_a_corner_lot_on_division_is_off_the_stretch() -> None:
    cm = division()
    assert not off_corridor(FRONT, cm)
    assert off_corridor(WEST, cm)
    # Per s4 edge, in order; only street lines are ever off.
    assert off_corridor_lines(CORNER, PDX, [cm]) == (False, False, False, True)
    # Not a layer the map serves, or not a map that tightens: nothing is read.
    assert off_corridor_lines(CORNER, "or/multnomah/gresham", [cm]) == (False,) * 4
    coverage = CorridorMap.from_lines("civic_corridor", [PDX], [ALONG], ["SE DIVISION ST"], cm.streets)
    assert off_corridor_lines(CORNER, PDX, [coverage]) == (False,) * 4


def test_off_is_never_merely_not_on() -> None:
    # A stretch that ends part way along the line: under half its points
    # agree, so the line is not ON -- and not OFF either: it keeps 10.
    short = LineString([(X0 - 500, Y0 - 30), (X0 + 15, Y0 - 30)])
    assert not on_corridor(FRONT, division(short))
    assert not off_corridor(FRONT, division(short))
    # No street network: the drawn line alone can say ON, never OFF --
    # except for a line no stretch is drawn within reach of at all.
    assert not off_corridor(WEST, cmap(ALONG))
    far = LineString([(X0 - 500, Y0 - 400), (X0 + 500, Y0 - 400)])
    assert off_corridor(WEST, cmap(far))
    # A point no centreline explains is not off: the network holds Division
    # alone, and nothing runs beside the west line.
    lone = CorridorMap.from_lines(
        "civic_corridor_setback", [PDX], [ALONG], ["SE DIVISION ST"], streets((ALONG, "SE DIVISION ST"))
    )
    assert not off_corridor(WEST, lone)


@pytest.mark.parametrize("zone", C_ZONES)
def test_the_street_off_the_corridor_is_quoted_from_the_plain_street_row(zone: str) -> None:
    from flats.rules.loader import load_rules

    value = load_rules()[PDX].zones[zone].values[OFF]
    assert not value.variants
    if zone in LOW_ZONES:
        assert value.value == 0
        assert value.prov.quote == "or/multnomah/portland/33.130.txt#L618,L640"
    else:
        # Off the corridor a line can still face an R zone across a local
        # street: the across-the-street row, 5 ft.
        assert value.value == 5
        assert value.prov.quote == "or/multnomah/portland/33.130.txt#L618,L643-L644,L836-L842"


@pytest.mark.parametrize("zone", C_ZONES)
def test_a_corner_lot_on_division_cuts_ten_along_division_and_none_along_the_side_street(
    pdx_rules, zone: str
) -> None:
    lot = lot_from_row(_cut(CORNER), corridors=[division()])
    assert [e.off_corridor for e in lot.edges.edges] == [False, False, False, True]
    held = [name for name, value in close_entailed(lot.observed).items() if value]
    got = pdx_rules.resolve(PDX, zone, conditions=held)
    # The lot-level reading is untouched: every edgeless reader takes 10.
    assert got.values["setback_front_ft"].value == 10
    env = envelope_for(lot, got)
    assert env.source == "flats"
    street = 0 if zone in LOW_ZONES else 5
    assert env.setbacks.front_ft == 10 and env.setbacks.street_off_corridor_ft == street
    # 10 off Division (south), the zone's street number off 82nd (west) --
    # none in CR/CM1, the across-the-street 5 above them while nothing has
    # read across 82nd -- and the 10 ft residential-neighbour yards east and
    # north: 40 x 80, or 35 x 80.
    assert env.sqft == pytest.approx((40 - street) * 80)
    # Without the maps nothing is read per line, and both streets keep 10.
    bare = lot_from_row(_cut(CORNER))
    assert not any(e.off_corridor for e in bare.edges.edges)
    assert envelope_for(bare, got).sqft == pytest.approx(30 * 80)


def test_a_corner_lot_on_two_stretches_keeps_ten_on_both(pdx_rules) -> None:
    # SE Division and SE 122nd: both lines are on a stretch, neither is off.
    net = streets((ALONG, "SE DIVISION ST"), (CROSS, "SE 122ND AVE"))
    cm = CorridorMap.from_lines(
        "civic_corridor_setback",
        [PDX],
        [ALONG, CROSS],
        ["SE DIVISION ST - CIVIC CORRIDOR", "SE 122nd AVENUE - CIVIC CORRIDOR"],
        net,
    )
    lot = lot_from_row(_cut(CORNER), corridors=[cm])
    assert not any(e.off_corridor for e in lot.edges.edges)
    held = [name for name, value in close_entailed(lot.observed).items() if value]
    assert EVERY in held
    env = envelope_for(lot, pdx_rules.resolve(PDX, "CM2", conditions=held))
    assert env.sqft == pytest.approx(30 * 80)


# A real one: taxlot 1S2E10BA 01300, CM2, the corner of SE Division St and SE
# 111th Ave (Oregon State Plane North, ft) -- s4's edges and RLIS
# centrelines, and Map 130-1's Division stretch, as the 2026-09-18 snapshot
# holds them. Division runs along the north line; 111th along the east.
REAL_EDGES = [
    [7676716.8, 676442.7, 7676647.1, 676445.4, "R"],
    [7676647.1, 676445.4, 7676650.0, 676542.8, "R"],
    [7676650.0, 676542.8, 7676718.5, 676540.3, "F"],
    [7676718.5, 676540.3, 7676716.8, 676442.7, "F"],
]
REAL_LOT = shapely.Polygon([(e[0], e[1]) for e in REAL_EDGES])
REAL_STREETS = (
    (LineString([(7676741.8, 676414.7), (7676737.7, 676192.7)]), "SE 111TH AVE"),
    (LineString([(7676743.3, 676489.9), (7676741.8, 676414.7)]), "SE 111TH AVE"),
    (LineString([(7676744.9, 676571.1), (7676743.3, 676489.9)]), "SE 111TH AVE"),
    (LineString([(7676741.8, 676414.7), (7676852.9, 676411.2)]), "SE DIVISION CT"),
    (LineString([(7676743.3, 676489.9), (7676889.8, 676484.4)]), "SE DIVISION ST-DIVISION CT ALY"),
    (LineString([(7676744.9, 676571.1), (7676968.5, 676563.6)]), "SE DIVISION ST"),
    (LineString([(7676516.6, 676593.0), (7676539.9, 676579.9), (7676744.9, 676571.1)]), "SE DIVISION ST"),
    (LineString([(7676516.6, 676593.0), (7676539.9, 676612.0), (7676968.5, 676595.8)]), "SE DIVISION ST"),
    (LineString([(7676397.1, 676584.4), (7676474.6, 676581.6), (7676516.6, 676593.0)]), "SE DIVISION ST"),
    (LineString([(7676522.9, 676792.8), (7676516.6, 676593.0)]), "SE 110TH AVE"),
)
REAL_DIVISION = LineString(
    [(7676397.1, 676597.7), (7676516.6, 676593.0), (7676745.2, 676584.5), (7676968.5, 676576.1)]
)


def test_a_real_corner_on_division_and_111th_cuts_ten_along_division_only(pdx_rules) -> None:
    cm = CorridorMap.from_lines(
        "civic_corridor_setback",
        [PDX],
        [REAL_DIVISION],
        ["SE DIVISION ST - CIVIC CORRIDOR"],
        streets(*REAL_STREETS),
    )
    division_line, avenue_line = REAL_EDGES[2], REAL_EDGES[3]
    assert on_corridor(division_line, cm) and not off_corridor(division_line, cm)
    assert off_corridor(avenue_line, cm) and not on_corridor(avenue_line, cm)
    row = _row(
        TLID="1S2E10BA  -01300",
        edges_json=json.dumps(REAL_EDGES),
        front_bearings_json="[89.01, 177.86]",
        tier="B",
        lot_wkb=shapely.to_wkb(REAL_LOT),
        area_sqft=REAL_LOT.area,
    )
    lot = lot_from_row(row, corridors=[cm])
    assert lot.observed["civic_corridor_setback"] is True
    assert lot.observed[EVERY] is False
    assert [e.off_corridor for e in lot.edges.edges] == [False, False, False, True]
    held = [name for name, value in close_entailed(lot.observed).items() if value]
    got = pdx_rules.resolve(PDX, "CM2", conditions=held)
    env = envelope_for(lot, got).geom
    bare = envelope_for(lot_from_row(row), got).geom
    division_ll = LineString([division_line[:2], division_line[2:4]])
    avenue_ll = LineString([avenue_line[:2], avenue_line[2:4]])
    # Ten feet off Division either way; the 111th Ave line gets five of its
    # ten back -- CM2's across-the-street 5 (33.130.215.B.1.b) stands until
    # something reads what is across 111th.
    assert env.distance(division_ll) == pytest.approx(10, abs=0.2)
    assert bare.distance(avenue_ll) == pytest.approx(10, abs=0.2)
    assert env.distance(avenue_ll) == pytest.approx(5, abs=0.2)
    assert bare.within(env.buffer(0.01))
    # The strip given back: five feet along the 111th line, less the
    # Division yard and the south line's.
    assert env.area - bare.area == pytest.approx(5 * (avenue_ll.length - 20), rel=0.05)


class _Rules:
    def __init__(self, **values: object) -> None:
        self.values, self.exempted = values, ()

    def get(self, name: str) -> object:
        return self.values.get(name)


def test_the_off_corridor_number_stands_in_only_where_no_street_side_number_is_stated() -> None:
    yards = {"setback_front_ft": 10, "setback_side_ft": 5, "setback_rear_ft": 5, OFF: 0}
    assert setbacks_for(_Rules(**yards)).street_off_corridor_ft == 0  # type: ignore[arg-type]
    both = setbacks_for(_Rules(**yards, setback_street_side_ft=8))  # type: ignore[arg-type]
    assert both.street_off_corridor_ft is None

    s = Setbacks(front_ft=10, side_ft=5, rear_ft=5, street_off_corridor_ft=0)

    def edge(cls: EdgeClass, off: bool) -> Edge:
        return Edge(0, 0, 1, 0, 1.0, 90.0, cls, off_corridor=off)

    assert s.for_edge(edge(EdgeClass.front, True)) == 0
    assert s.for_edge(edge(EdgeClass.street_side, True)) == 0
    assert s.for_edge(edge(EdgeClass.front, False)) == 10
    # The flag means nothing off a street line.
    assert s.for_edge(edge(EdgeClass.side, True)) == 5
    assert s.for_edge(edge(EdgeClass.rear, True)) == 5
