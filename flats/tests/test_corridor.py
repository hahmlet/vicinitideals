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
    on_corridor,
    street_name,
)
from flats.ingest.quadfit import OBSERVABLE, lot_from_row, observed_facts
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

    assert front() == 0
    assert front("civic_corridor") == 0
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
