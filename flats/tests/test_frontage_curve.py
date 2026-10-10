"""A curve clause measured as ONE angle across the frontage (FOLLOWUPS 63)."""

from __future__ import annotations

import json
import math

import pytest

from flats.geom.frontage_curve import is_unbroken, makes_corner, measure

R = 100.0


def ring_json(points: list[tuple[float, float]], classes: list[str]) -> str:
    n = len(points)
    return json.dumps(
        [[*points[i], *points[(i + 1) % n], classes[i]] for i in range(n)]
    )


def arc_lot(delta: float, n: int, *, inside: bool = True) -> str:
    """A lot whose street frontage is an n-segment polyline on a circle of
    ``delta`` degrees: on the inside of the curve, or on the outside."""
    if inside:
        angles = [180.0 + delta * i / n for i in range(n + 1)]
        arc = [(R * math.cos(math.radians(a)), R * math.sin(math.radians(a))) for a in angles]
        points = [*arc, (0.0, 0.0)]
    else:
        angles = [270.0 + delta / 2 - delta * i / n for i in range(n + 1)]
        arc = [(R * math.cos(math.radians(a)), R * math.sin(math.radians(a))) for a in angles]
        points = [*arc, (0.0, -400.0)]
    return ring_json(points, ["F"] * n + ["R", "R"])


def corner(edges: str, by: str, ceiling: float, **kw: bool) -> bool:
    return makes_corner(
        by,
        ceiling,
        inclusive=kw.get("inclusive", True),
        inside_only=kw.get("inside_only", False),
        edges_json=edges,
    )


def test_a_gentle_multi_bend_curve_is_measured_across_the_whole_curve() -> None:
    # 100 degrees over four lot lines: every bend is 25, so a bend-by-bend test
    # never reaches 135, but the chords from the ends meet at 130 at the apex.
    edges = arc_lot(100.0, 4)
    c = measure(edges)
    assert c is not None and c.inside
    assert c.apex_deg == pytest.approx(130.0, abs=0.5)
    assert c.tangent_deg == pytest.approx(105.0, abs=0.5)
    assert corner(edges, "apex", 135.0, inclusive=False) is True
    assert corner(edges, "tangent", 120.0) is True
    assert corner(edges, "tangent", 120.0, inside_only=True) is True


def test_a_gentler_curve_is_one_street_by_all_three_readings() -> None:
    edges = arc_lot(60.0, 4)
    assert corner(edges, "apex", 135.0, inclusive=False) is False
    assert corner(edges, "tangent", 120.0) is False


def test_the_outside_of_a_curve_is_not_greshams_inside_curve() -> None:
    edges = arc_lot(100.0, 4, inside=False)
    c = measure(edges)
    assert c is not None and not c.inside and c.apex_deg is None
    assert corner(edges, "tangent", 120.0, inside_only=True) is False
    assert corner(edges, "tangent", 120.0) is True  # Portland names no side
    assert corner(edges, "apex", 135.0, inclusive=False) is False  # no foremost point


def test_less_than_excludes_the_ceiling_and_or_less_includes_it() -> None:
    edges = arc_lot(100.0, 4)
    c = measure(edges)
    assert c is not None and c.apex_deg is not None
    assert corner(edges, "apex", c.apex_deg, inclusive=True) is True
    assert corner(edges, "apex", c.apex_deg, inclusive=False) is False


def test_a_sharp_single_turn_reads_the_same_by_every_construction() -> None:
    edges = ring_json([(0, 0), (100, 0), (100, 100), (0, 100)], ["F", "F", "R", "R"])
    c = measure(edges)
    assert c is not None
    assert c.tangent_deg == pytest.approx(90.0) and c.apex_deg == pytest.approx(90.0)


def test_one_name_on_two_runs_parted_by_a_rear_line_is_broken() -> None:
    broken = ring_json(
        [(0, 0), (100, 0), (100, 50), (200, 50), (200, 150), (0, 150)],
        ["F", "R", "R", "F", "R", "R"],
    )
    assert is_unbroken(broken) is False
    assert measure(broken) is None
    one = ring_json([(0, 0), (100, 0), (100, 100), (0, 100)], ["F", "F", "R", "R"])
    assert is_unbroken(one) is True


def test_a_run_that_wraps_past_the_first_edge_is_one_run() -> None:
    wrapped = ring_json([(0, 0), (100, 0), (100, 100), (0, 100)], ["F", "R", "R", "F"])
    assert is_unbroken(wrapped) is True


def test_a_short_piece_with_no_street_edge_joining_it_is_a_second_front() -> None:
    # A through lot: 70 ft on one street, 13 ft on the other end, parted by
    # rear/side lines. The short piece turns off the long one but is no sliver.
    through = ring_json(
        [(0, 0), (70, 0), (70, 100), (13, 100), (0, 100)],
        ["F", "R", "R", "F", "R"],
    )
    assert is_unbroken(through) is False
    pair = ring_json(
        [(0, 0), (80, 0), (80, 100), (14, 100), (0, 105), (0, 20)],
        ["F", "R", "R", "F", "R", "R"],
    )
    assert is_unbroken(pair) is False


def test_a_short_sliver_turning_away_does_not_break_the_run() -> None:
    sliver = ring_json(
        [(0, 0), (100, 0), (100, 100), (10, 100), (0, 100), (0, 10)],
        ["F", "R", "R", "R", "R", "F"],
    )
    assert is_unbroken(sliver) is True
    cut = ring_json(
        [(0, 0), (100, 0), (100, 100), (0, 100), (0, 10)],
        ["F", "F", "R", "R", "F"],
    )
    assert is_unbroken(cut) is True
