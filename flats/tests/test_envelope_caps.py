"""The setback strips take exactly the ground within each line's setback.

Until 2026-11-09 each strip was the line buffered with square caps, which
ran a full setback past each end. At an inward bend in a lot line that took a
sliver up to a setback deep beyond the bend (Tigard 2S103BA00137: a 4.5 deg
front bend, the building pushed to 21.08 ft against a 20 ft front maximum,
a false RED). The strip is now the band either side of the line closed by a
half-disc round each end: every point within the setback of the line and,
by a few hundredths of a foot, no more.

Two promises, checked on every shape below over a grid of points:

* never a false GREEN: no point of the envelope is nearer any line than its
  setback (:func:`_assert_legal`);
* no overrun: a point the envelope gives up is within its setback of some
  line, give or take the arc's sag (:func:`_assert_tight`).
"""

from __future__ import annotations

import math

import pytest

shapely = pytest.importorskip("shapely")

from shapely.geometry import LineString, Point, Polygon  # noqa: E402

from flats.geom import EdgeClass, Setbacks, Tier, buildable  # noqa: E402
from flats.geom.edges import Edge, LotEdges, bearing_deg  # noqa: E402
from flats.geom.envelope import ARC_SPLITS, _strip  # noqa: E402

pytestmark = pytest.mark.unit

#: How far past the setback a chorded half-disc may reach, per foot of setback.
SAG = 1 / math.cos(math.pi / ARC_SPLITS / 2) - 1
#: Floating-point slack on a distance.
EPS = 1e-6
#: Grid step for the point checks, in feet.
STEP = 0.5


def _edges(ring, classes, tier=Tier.clean) -> LotEdges:
    out = []
    for (x1, y1), (x2, y2), cls in zip(ring, ring[1:] + ring[:1], classes, strict=True):
        out.append(
            Edge(
                x1=x1,
                y1=y1,
                x2=x2,
                y2=y2,
                length_ft=math.hypot(x2 - x1, y2 - y1),
                bearing_deg=bearing_deg(x1, y1, x2, y2),
                cls=cls,
            )
        )
    fronts = [e for e in out if e.cls in (EdgeClass.front, EdgeClass.street_side)]
    return LotEdges(
        tier=tier,
        edges=tuple(out),
        front_bearings=(fronts[0].bearing_deg,),
        frontage_ft=sum(e.length_ft for e in fronts),
        convexity=1.0,
    )


def _required(lot: LotEdges, setbacks: Setbacks):
    return [
        (LineString([(e.x1, e.y1), (e.x2, e.y2)]), setbacks.for_edge(e)) for e in lot.edges
    ]


def _grid(poly):
    x0, y0, x1, y1 = poly.bounds
    nx, ny = int((x1 - x0) / STEP) + 1, int((y1 - y0) / STEP) + 1
    pts = shapely.points([(x0 + i * STEP, y0 + j * STEP) for i in range(nx) for j in range(ny)])
    return pts[shapely.contains(poly, pts)]


def _assert_legal(env, lot: LotEdges, setbacks: Setbacks) -> None:
    pts = list(_grid(env)) + [Point(c) for p in env.geoms for c in p.exterior.coords]
    for line, d in _required(lot, setbacks):
        near = [p for p in pts if line.distance(p) < d - EPS]
        assert not near, f"{len(near)} envelope points inside a {d} ft setback, e.g. {near[0]}"


def _assert_tight(env, ring, lot: LotEdges, setbacks: Setbacks) -> None:
    taken = _grid(Polygon(ring).difference(env.buffer(EPS)))
    req = _required(lot, setbacks)
    far = [p for p in taken if all(line.distance(p) > d * (1 + SAG) + EPS for line, d in req)]
    assert not far, f"{len(far)} points taken beyond every setback, e.g. {far[0]}"


def _old(ring, lot: LotEdges, setbacks: Setbacks):
    """The square-capped construction this replaced, for comparison."""
    strips = [
        line.buffer(d, cap_style="square", join_style="mitre")
        for line, d in _required(lot, setbacks)
        if d > 0
    ]
    return Polygon(ring).difference(shapely.union_all(strips))


def _check(ring, classes, setbacks, tier=Tier.clean):
    lot = _edges(ring, classes, tier)
    env = buildable(Polygon(ring), lot, setbacks, min_part_sqft=0.0)
    _assert_legal(env, lot, setbacks)
    _assert_tight(env, ring, lot, setbacks)
    old = _old(ring, lot, setbacks)
    # The new strips sit inside the old square caps: the envelope never
    # shrinks, it only gives back what the caps over-took.
    assert old.difference(env).area < 1e-6
    return env, old


# --- the strip ------------------------------------------------------------


@pytest.mark.parametrize(
    ("seg", "d"), [((0, 0, 40, 0), 20), ((3, -7, 3, 50), 5), ((1, 2, 31, 17), 12.5)]
)
def test_a_strip_holds_every_point_within_the_setback_and_no_more(seg, d) -> None:
    strip = _strip(*seg, d)
    line = LineString([seg[:2], seg[2:]])
    assert strip.is_valid
    pts = _grid(shapely.box(*line.bounds).buffer(d + 2))
    dist = shapely.distance(line, pts)
    inside = shapely.intersects(strip, pts)
    assert inside[dist <= d - EPS].all()  # never short of the setback
    assert (dist[inside] <= d * (1 + SAG) + EPS).all()  # never past the sag
    # ...and inside what the square cap took.
    square = line.buffer(d, cap_style="square", join_style="mitre")
    assert strip.difference(square).area < 1e-6
    # The cap is round: a point beside the line's end, past it, that the
    # square cap took is left now.
    x1, y1, x2, y2 = seg
    length = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    corner = Point(x2 + 0.9 * d * (ux - uy), y2 + 0.9 * d * (uy + ux))
    assert square.contains(corner) and not strip.contains(corner)


def test_a_point_lot_line_is_a_disc() -> None:
    disc = _strip(5, 5, 5, 5, 10)
    assert disc.is_valid
    assert disc.area == pytest.approx(math.pi * 100, rel=2 * SAG + 1e-3)


# --- lots -----------------------------------------------------------------

F, S, R = EdgeClass.front, EdgeClass.side, EdgeClass.rear
SB = Setbacks(front_ft=20, side_ft=5, rear_ft=15)
BEND = math.radians(4.5)


def _bent_front(sign: int):
    """A front of 37.8 ft then 78.3 ft, bent 4.5 deg; 120 ft deep.

    ``sign`` +1 bends the second leg away from the lot (an inward, reflex
    bend: the lot's angle at the bend is 184.5 deg), -1 toward it (outward,
    175.5 deg)."""
    bx = 37.8
    ex, ey = bx + 78.3 * math.cos(BEND), -sign * 78.3 * math.sin(BEND)
    return [(0.0, 0.0), (bx, 0.0), (ex, ey), (ex, 120.0), (0.0, 120.0)], [F, F, S, R, S]


def test_an_inward_front_bend_gives_back_the_sliver_past_the_bend() -> None:
    # Tigard 2S103BA00137's shape: the square cap of the short leg ran 20 ft
    # past the bend, up to 1.5 ft deeper than the long leg's setback.
    ring, classes = _bent_front(+1)
    env, old = _check(ring, classes, SB)
    assert env.difference(old).area > 10  # ~17 ft long, ~1.5 ft deep
    # 19.9 ft off the short leg's line and 10 ft past the bend: 22.3 ft from
    # the bend, 20.6 ft from the long leg. Legal; the old cap took it.
    p = Point(37.8 + 10, 19.9)
    assert env.contains(p) and not old.contains(p)
    # The old envelope stood up to 1.5 ft further off the long leg than its
    # setback; the new one comes within the setback (plus sag) of the bend.
    long_leg = LineString(ring[1:3])
    near_bend = shapely.box(37.8, 0, 60, 40)
    worst = max(long_leg.distance(Point(c)) for c in old.intersection(near_bend).exterior.coords)
    assert worst > 21.0
    assert env.distance(Point(ring[1])) == pytest.approx(20.0, abs=20 * SAG + 1e-3)


def test_an_outward_front_bend_is_unchanged() -> None:
    # The square cap past an outward bend falls inside the other leg's strip:
    # the old shape was right, and the new one is the same.
    ring, classes = _bent_front(-1)
    env, old = _check(ring, classes, SB)
    assert env.symmetric_difference(old).area < 0.05


def test_a_straight_front_in_two_pieces_is_one_line() -> None:
    ring = [(0.0, 0.0), (40.0, 0.0), (100.0, 0.0), (100.0, 120.0), (0.0, 120.0)]
    env, old = _check(ring, [F, F, S, R, S], SB)
    assert env.symmetric_difference(old).area < 1e-6
    assert env.bounds == pytest.approx((5.0, 20.0, 95.0, 105.0))


def test_a_rectangle_is_what_it_was() -> None:
    # Right-angled corners: the square caps fell outside the lot or inside
    # the neighbour's strip. Nothing moves.
    ring = [(0.0, 0.0), (60.0, 0.0), (60.0, 100.0), (0.0, 100.0)]
    env, old = _check(ring, [F, S, R, S], Setbacks(front_ft=10, side_ft=5, rear_ft=5))
    assert env.area == pytest.approx(50 * 85)
    assert env.symmetric_difference(old).area < 1e-6


@pytest.mark.parametrize("angle", [30.0, 45.0, 60.0, 75.0])
def test_an_acute_corner_lot_keeps_both_street_setbacks(angle) -> None:
    # A corner lot whose two streets meet at a sharp angle: front 20 ft,
    # street side 10 ft. The tip is ground within both, and none comes back.
    a = math.radians(angle)
    far_side = (150.0 * math.cos(a), 150.0 * math.sin(a))
    ring = [(0.0, 0.0), (150.0, 0.0), (150.0, far_side[1]), far_side]
    sb = Setbacks(front_ft=20, side_ft=5, rear_ft=15, street_side_ft=10)
    env, old = _check(ring, [F, S, R, EdgeClass.street_side], sb, tier=Tier.corner)
    # At the tip nothing moves. (The street side's far end meets the rear
    # obtusely, where the square cap did over-take; _check holds that legal.)
    tip = Point(0, 0).buffer(90)
    assert env.symmetric_difference(old).intersection(tip).area < 0.05


def test_an_obtuse_front_corner_gives_back_what_the_cap_over_took() -> None:
    # A front meeting a side line at 120 deg, 20 ft against 5 ft: the front's
    # square cap ran 20 ft along the side yard. Ground beyond 5 ft of the
    # side line and 20 ft of the front line is the building's.
    ring = [(0.0, 0.0), (80.0, 0.0), (110.0, 51.96), (110.0, 120.0), (0.0, 120.0)]
    env, old = _check(ring, [F, S, S, R, S], SB)
    assert env.area > old.area + 1.0


def test_a_rear_with_an_inward_notch_keeps_every_setback() -> None:
    ring = [
        (0.0, 0.0),
        (90.0, 0.0),
        (90.0, 110.0),
        (55.0, 110.0),
        (50.0, 100.0),
        (40.0, 100.0),
        (35.0, 110.0),
        (0.0, 110.0),
    ]
    _check(ring, [F, S, R, R, R, R, R, S], SB)
