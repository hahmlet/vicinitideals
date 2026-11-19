"""A yard is measured from the lot line, not from the edge that stands for it.

FOLLOWUPS 205. The edges the bridge reads are quadfit s4's: the lot's ring
simplified at 1.5 ft, so a curved or kinked lot line is one straight chord.
The setback strips were cut from the chords. Where the true line bows into
the lot, the envelope then came up to the setback of the CHORD and stood
that much nearer the line itself: Portland 1S3E06BD -09500 (R7, a curved
front) was GREEN with 13.7 ft of a 15 ft front yard, Beaverton 1S117CD00900
with 9.4 ft of 10.

Each strip is now widened by how far the lot's own line runs inside its
chord (:func:`flats.geom.envelope._sag`), read off the lot's unsimplified
ring. A straight line, or one that bows outward, is untouched.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

shapely = pytest.importorskip("shapely")

from shapely.geometry import LineString, Polygon  # noqa: E402

from flats.geom import EdgeClass, Setbacks, Tier, buildable  # noqa: E402
from flats.geom.edges import Edge, LotEdges, bearing_deg  # noqa: E402
from flats.geom.envelope import SMOOTH_FT, _rings, _sag  # noqa: E402

pytestmark = pytest.mark.unit

EPS = 1e-6
#: State-plane-sized coordinates, as the bridge's are.
X0, Y0 = 7_650_000.0, 680_000.0
YARDS = Setbacks(front_ft=15, side_ft=5, rear_ft=5)

#: A 60 x 110 lot whose front line bows a foot INTO the lot (a cul-de-sac
#: bulb, a curve on the street). Simplified at 1.5 ft it is a rectangle.
BOWED_FRONT = [(0, 0), (20, 0.8), (30, 1.0), (40, 0.8), (60, 0)]
REST = [(60, 110), (0, 110)]
CORNERS = [(0, 0), (60, 0), (60, 110), (0, 110)]
CLASSES = [EdgeClass.front, EdgeClass.side, EdgeClass.rear, EdgeClass.side]


def _at(points, dx=X0, dy=Y0):
    return [(x + dx, y + dy) for x, y in points]


def _edge(a, b, cls) -> Edge:
    (x1, y1), (x2, y2) = a, b
    return Edge(
        x1=x1,
        y1=y1,
        x2=x2,
        y2=y2,
        length_ft=math.hypot(x2 - x1, y2 - y1),
        bearing_deg=bearing_deg(x1, y1, x2, y2),
        cls=cls,
    )


def _lot_edges(corners, classes=CLASSES, tier=Tier.clean) -> LotEdges:
    edges = tuple(
        _edge(a, b, cls)
        for a, b, cls in zip(corners, corners[1:] + corners[:1], classes, strict=True)
    )
    fronts = [e for e in edges if e.cls is EdgeClass.front]
    return LotEdges(
        tier=tier,
        edges=edges,
        frontage_ft=sum(e.length_ft for e in fronts),
        front_bearings=tuple(e.bearing_deg for e in fronts),
        convexity=1.0,
    )


def test_the_front_yard_is_kept_from_the_lot_line_not_from_the_chord() -> None:
    """The test that would have caught it: no point of the envelope is nearer
    the true front line than the front setback."""
    lot = Polygon(_at(BOWED_FRONT + REST))
    true_front = LineString(_at(BOWED_FRONT))
    env = buildable(lot, _lot_edges(_at(CORNERS)), YARDS)
    assert not env.is_empty
    assert env.distance(true_front) >= 15 - EPS
    # ...and it gives up no more than the bow: a foot of depth, nothing else.
    assert env.bounds[1] == pytest.approx(Y0 + 16.0, abs=0.05)
    assert env.bounds[0] == pytest.approx(X0 + 5.0, abs=EPS)
    assert env.bounds[2] == pytest.approx(X0 + 55.0, abs=EPS)
    assert env.bounds[3] == pytest.approx(Y0 + 105.0, abs=EPS)


def test_the_chord_alone_was_a_foot_short() -> None:
    """What the screen did: the same edges on the simplified lot come up to
    15 ft of the chord, which is 14 ft from the lot line."""
    env = buildable(Polygon(_at(CORNERS)), _lot_edges(_at(CORNERS)), YARDS)
    assert env.bounds[1] == pytest.approx(Y0 + 15.0, abs=EPS)
    assert env.distance(LineString(_at(BOWED_FRONT))) == pytest.approx(14.0, abs=0.01)


def test_the_bow_is_read_exactly_and_either_way_round_the_ring() -> None:
    ring = _at(BOWED_FRONT + REST)
    (a, b) = _at([(0, 0), (60, 0)])
    for points in (ring, ring[::-1]):
        rings = _rings(Polygon(points))
        assert _sag(rings, *a, *b) == pytest.approx(1.0, abs=1e-6)
        assert _sag(rings, *b, *a) == pytest.approx(1.0, abs=1e-6)


def test_a_line_as_drawn_and_a_line_that_bows_outward_take_nothing() -> None:
    square = _rings(Polygon(_at(CORNERS)))
    for a, b in zip(_at(CORNERS), _at(CORNERS[1:] + CORNERS[:1]), strict=True):
        assert _sag(square, *a, *b) == 0.0
    outward = [(0, 0), (20, -0.8), (30, -1.0), (40, -0.8), (60, 0)]
    lot = Polygon(_at(outward + REST))
    (a, b) = _at([(0, 0), (60, 0)])
    assert _sag(_rings(lot), *a, *b) == 0.0
    # The chord is then nearer the building than the line: 15 ft of it holds.
    env = buildable(lot, _lot_edges(_at(CORNERS)), YARDS)
    assert env.bounds[1] == pytest.approx(Y0 + 15.0, abs=EPS)
    assert env.distance(LineString(_at(outward))) >= 15 - EPS


def test_a_rectangle_keeps_the_envelope_it_always_had() -> None:
    env = buildable(Polygon(_at(CORNERS)), _lot_edges(_at(CORNERS)), YARDS)
    assert env.area == pytest.approx((60 - 10) * (110 - 20), rel=1e-9)


def test_an_edge_s4_split_between_vertices_is_read_too() -> None:
    """s4 cuts a chord where the neighbour changes: the two halves end on the
    chord, a foot off the lot's ring, and each still answers for the bow."""
    lot = Polygon(_at(BOWED_FRONT + REST))
    rings = _rings(lot)
    a, mid, b = _at([(0, 0), (30, 0), (60, 0)])
    assert _sag(rings, *a, *mid) == pytest.approx(1.0, abs=0.01)
    assert _sag(rings, *mid, *b) == pytest.approx(1.0, abs=0.01)
    assert _sag(rings, *b, *mid) == pytest.approx(1.0, abs=0.01)
    corners = _at([(0, 0), (30, 0), (60, 0), (60, 110), (0, 110)])
    env = buildable(lot, _lot_edges(corners, [EdgeClass.front, *CLASSES]), YARDS)
    assert env.distance(LineString(_at(BOWED_FRONT))) >= 15 - EPS


def test_a_side_line_that_kinks_inward_is_widened_on_that_side_only() -> None:
    kinked = [(0, 0), (60, 0), (60, 110), (0, 110), (0.7, 55)]
    lot = Polygon(_at(kinked))
    env = buildable(lot, _lot_edges(_at(CORNERS)), YARDS)
    side = LineString(_at([(0, 110), (0.7, 55), (0, 0)]))
    assert env.distance(side) >= 5 - EPS
    assert env.bounds[0] == pytest.approx(X0 + 5.7, abs=0.01)
    assert env.bounds[1] == pytest.approx(Y0 + 15.0, abs=EPS)
    assert env.bounds[2] == pytest.approx(X0 + 55.0, abs=EPS)


def test_an_edge_that_is_not_on_the_lot_takes_the_whole_tolerance() -> None:
    rings = _rings(Polygon(_at(CORNERS)))
    assert _sag(rings, X0 + 500, Y0 + 500, X0 + 600, Y0 + 500) == SMOOTH_FT
    assert _sag(rings, X0, Y0, X0, Y0) == 0.0  # no length, no strip to widen


def test_the_tolerance_is_s4s_own() -> None:
    """The edges are quadfit's, simplified at its tolerance; the fallback may
    not be smaller than that."""
    rules = Path(__file__).resolve().parents[2] / "Lot Analysis" / "quadfit" / "config" / "rules.yaml"
    if not rules.exists():
        pytest.skip("quadfit's rules.yaml is not in this checkout")
    found = re.search(r"^\s*simplify_tolerance_ft:\s*([\d.]+)", rules.read_text(encoding="utf-8"), re.M)
    assert found is not None
    assert float(found.group(1)) <= SMOOTH_FT
