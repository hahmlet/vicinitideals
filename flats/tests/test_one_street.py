"""Whether every street edge of a lot lies on one street (FOLLOWUPS 63)."""

from __future__ import annotations

import json

import shapely

from flats.geom.one_street import one_street_flags, street_midpoints

#: A 50 x 100 lot with a street along its south and west lines.
CORNER = [
    [0, 0, 50, 0, "F"],
    [50, 0, 50, 100, "R"],
    [50, 100, 0, 100, "R"],
    [0, 100, 0, 0, "F"],
]
SOUTH = shapely.LineString([(-20, -10), (80, -10)])
WEST = shapely.LineString([(-10, -20), (-10, 120)])


def flags(edges, names, ftypes=None, alleys=None, lines=None):
    lines = lines or [SOUTH, WEST][: len(names)]
    return one_street_flags(
        [json.dumps(edges)],
        names,
        ftypes or ["ST"] * len(names),
        alleys or [False] * len(names),
        lines,
    )


def test_two_named_streets_are_a_corner() -> None:
    assert flags(CORNER, ["MAIN", "OAK"]) == [False]


def test_one_name_on_both_edges_is_one_street() -> None:
    assert flags(CORNER, ["MAIN", "MAIN"]) == [True]


def test_the_same_name_with_a_different_type_is_another_street() -> None:
    assert flags(CORNER, ["MAIN", "MAIN"], ["ST", "CT"]) == [False]


def test_a_nameless_line_in_reach_keeps_the_corner_reading() -> None:
    assert flags(CORNER, ["MAIN", ""]) == [False]
    assert flags(CORNER, ["MAIN", None]) == [False]


def test_an_alley_is_not_a_street() -> None:
    assert flags(CORNER, ["MAIN", "OAK"], alleys=[False, True]) == [None]


def test_an_edge_with_no_line_in_reach_measures_nothing() -> None:
    far = shapely.LineString([(-20, -500), (80, -500)])
    assert flags(CORNER, ["MAIN", "MAIN"], lines=[SOUTH, far]) == [None]


def test_a_lot_with_no_street_edge_measures_nothing() -> None:
    inland = [[*e[:4], "R"] for e in CORNER]
    assert flags(inland, ["MAIN", "MAIN"]) == [None]


def test_a_short_sliver_turning_away_is_not_a_second_frontage() -> None:
    bend = [
        [0, 0, 100, 0, "F"],
        [100, 0, 100, 100, "R"],
        [100, 100, 0, 100, "R"],
        [0, 100, 0, 10, "R"],
        [0, 10, 0, 0, "F"],
    ]
    assert len(street_midpoints(json.dumps(bend))) == 1
    # A long second street edge is kept.
    assert len(street_midpoints(json.dumps(CORNER))) == 2
    # And a sliver the same direction as the main edge is kept.
    inline = [[0, 0, 40, 0, "F"], [40, 0, 50, 0, "F"], [50, 0, 50, 100, "R"], [50, 100, 0, 100, "R"], [0, 100, 0, 0, "R"]]
    assert len(street_midpoints(json.dumps(inline))) == 2
