"""s5's setback strips take exactly the ground within each line's setback.

The 2026-11-09 port of FLATS' envelope fix (flats/tests/test_envelope_caps.py):
square caps ran each strip a full setback past its ends and, at an inward bend
in a front line, took a sliver up to ~1.5 ft deeper than the setback (Tigard
2S103BA00137, a 4.5 deg front bend: 37.8 ft then 78.3 ft). Two promises:

* never short of a setback: no envelope point is nearer a line than its
  setback (no false GREEN);
* only grows back: the new envelope holds the old one, and what it still
  gives up is within a setback of some line (give or take the arc's sag).
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("shapely")

import shapely  # noqa: E402
from shapely.geometry import LineString, Point, Polygon  # noqa: E402

pytestmark = pytest.mark.unit

SETBACKS = {"F": 20.0, "S": 5.0, "R": 15.0, "A": 15.0}
STEP = 0.5
EPS = 1e-6


def _sag():
    from s5_envelope import ARC_SPLITS

    return 1 / math.cos(math.pi / ARC_SPLITS / 2) - 1


def _tigard(sign: int):
    """Front of 37.8 ft then 78.3 ft bent 4.5 deg; 120 ft deep. ``sign`` +1
    bends the second leg away from the lot (inward, reflex), -1 toward it."""
    bend = math.radians(4.5)
    bx = 37.8
    ex, ey = bx + 78.3 * math.cos(bend), -sign * 78.3 * math.sin(bend)
    ring = [(0.0, 0.0), (bx, 0.0), (ex, ey), (ex, 120.0), (0.0, 120.0)]
    classes = ["F", "F", "S", "R", "S"]
    edges = [[*a, *b, c] for a, b, c in zip(ring, ring[1:] + ring[:1], classes, strict=True)]
    return ring, edges


def _grid(poly):
    x0, y0, x1, y1 = poly.bounds
    pts = shapely.points(
        [
            (x0 + i * STEP, y0 + j * STEP)
            for i in range(int((x1 - x0) / STEP) + 1)
            for j in range(int((y1 - y0) / STEP) + 1)
        ]
    )
    return pts[shapely.contains(poly, pts)]


def _old(ring, edges):
    strips = [
        LineString([(x1, y1), (x2, y2)]).buffer(SETBACKS[c], cap_style="square", join_style="mitre")
        for x1, y1, x2, y2, c in edges
    ]
    return Polygon(ring).difference(shapely.union_all(strips))


def _check(ring, edges):
    from s5_envelope import build_envelope

    env = build_envelope(Polygon(ring), edges, SETBACKS, "A")
    lines = [(LineString([(x1, y1), (x2, y2)]), SETBACKS[c]) for x1, y1, x2, y2, c in edges]
    # Never short of a setback.
    pts = list(_grid(env)) + [Point(c) for p in env.geoms for c in p.exterior.coords]
    for line, d in lines:
        assert not [p for p in pts if line.distance(p) < d - EPS]
    # Only grows back, and no further than the legal area.
    old = _old(ring, edges)
    assert old.difference(env).area < 1e-6
    taken = _grid(Polygon(ring).difference(env.buffer(EPS)))
    sag = _sag()
    assert not [p for p in taken if all(ln.distance(p) > d * (1 + sag) + EPS for ln, d in lines)]
    return env, old


def test_the_tigard_inward_bend_gives_back_the_sliver_past_the_bend():
    ring, edges = _tigard(+1)
    env, old = _check(ring, edges)
    assert env.difference(old).area > 10
    # 19.9 ft off the short leg, 10 ft past the bend: 22.3 ft from the bend,
    # 20.6 ft from the long leg. Legal; the square cap took it.
    p = Point(47.8, 19.9)
    assert env.contains(p) and not old.contains(p)
    assert env.distance(Point(ring[1])) == pytest.approx(20.0, abs=20 * _sag() + 1e-3)


def test_an_outward_bend_and_a_rectangle_are_what_they_were():
    ring, edges = _tigard(-1)
    env, old = _check(ring, edges)
    assert env.symmetric_difference(old).area < 0.05
    rect = [(0.0, 0.0), (60.0, 0.0), (60.0, 100.0), (0.0, 100.0)]
    r_edges = [[0, 0, 60, 0, "F"], [60, 0, 60, 100, "S"], [60, 100, 0, 100, "R"], [0, 100, 0, 0, "S"]]
    env, old = _check(rect, r_edges)
    assert env.area == pytest.approx(50 * 65)
    assert env.symmetric_difference(old).area < 1e-6
