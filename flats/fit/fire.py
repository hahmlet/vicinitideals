"""How far a fire hose walks from the street to the farthest wall (FOLLOWUPS 28).

OFC 2022 503.1.1 wants the fire apparatus road "within 150 feet of all
portions of the exterior wall of the first story of the building as measured
by an approved route around the exterior of the building". On a lot whose
street is the only such road, that is a distance from the street to the far
side of the building, walked: across the right-of-way, onto the lot over a
street lot line, and round the walls to the point farthest from it.

:func:`route_ft` measures it for one plan, and the number it returns is the
length of a route that EXISTS, never a shortcut no hose could take -- so it
is at least the shortest route, and a lot it clears is cleared. Everything
it leaves out can only lengthen it:

* the hose stays on the lot once it leaves the street (a neighbour's yard is
  nobody's approved route), entering only over a street lot line;
* it goes round the building, never through it, and reaches a wall point by
  way of a corner -- the wall facing the street, reached straight on, is
  never the farthest point, so nothing is lost there;
* the truck stands on the street's own pavement, and the hose is measured
  from :data:`CURB_START_FT` out from the near curb, never past the street's
  middle (Steph 2026-10-05, "stricter": a lane of parked cars between the
  truck and the curb; FOLLOWUPS 29). Where a curb line or a pavement width
  is published (:mod:`flats.geom.curbs`), the curb is where it says. Where
  none is, the street is taken as the narrowest a truck may use (OFC
  503.2.1, 20 ft; Steph 2026-10-05, "assume narrow"): its curb
  :data:`HALF_ROAD_FT` off the centreline, and the hose measured from the
  middle (:func:`hose_offsets`);
* the street lot line is walked at :data:`SOURCE_STEP_FT` points, and from the
  points of it nearest each building corner, not every point of it.

The shortest route is found on a visibility graph: the street points, the
lot's inward corners (:func:`_bends`; a route bends only at one) and the
building's, joined where the straight line between two of them stays on the
lot and off the building.
None where no route reaches the building at all -- an answer nobody measured,
which the screen holds out of GREEN rather than pass.
"""

from __future__ import annotations

import heapq
import math
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Sequence

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

if TYPE_CHECKING:
    from flats.geom.curbs import StreetEdges

#: Half the narrowest fire apparatus road (OFC 503.2.1, 20 ft unobstructed).
HALF_ROAD_FT = 10.0
#: How far out from the near curb the hose is measured from: "Hose pull
#: measurements begin at a point in the street located 10 feet from the edge
#: of the curb" (Colton, Roseville, Riverside County and others; Steph
#: 2026-10-05 chose it over the curb itself, the stricter of the two).
CURB_START_FT = 10.0
#: The two readings :func:`hose_offsets` gives: the one the screen holds
#: (``strict``), and the hose measured from the curb itself (``curb``), which
#: only says whether a lot the strict reading fails would clear at the curb.
READINGS = ("strict", "curb")
#: A street lot line point farther than this from every road a truck can use
#: is not on one: quadfit s4 calls a lot line a street's only within 50 ft of
#: its centreline (``street_threshold_ft``), and a line it called a street
#: for a road the truck may not take (an unnamed drive) is no place for the
#: hose to come on -- the straight line from it to some far road is not a
#: route anyone walks.
MAX_GAP_FT = 50.0
#: RLIS STREETS TYPE codes a fire truck can stand on: highway, arterials,
#: collectors, local streets and NAMED private roads (1700, built to street
#: standard and signed off by the fire district with the subdivision); and
#: the same classes where a streetcar or MAX line runs in the street (5301
#: Grand, MLK, Broadway; 5401 Jefferson; 5451 NW 10th/11th, Moody; 5500;
#: 5501 SW 5th/6th, Yamhill, Morrison) -- streets cars and trucks drive.
#: Not freeways or ramps (11xx, x21-x23, x71), alleys (1600), unnamed drives
#: (1800), unimproved roads (2000: Leif Erikson Drive), 5402 (Tilikum
#: Crossing and Harbor Viaduct, transit only, beside two streets), forest
#: roads (9000), trails and unclassed lines -- a road left out can only send
#: the truck to a farther one.
TRUCK_TYPES: frozenset[int] = frozenset(
    {1200, 1300, 1400, 1450, 1500, 1550, 1560, 1700, 5301, 5401, 5451, 5500, 5501}
)
#: How often the street lot line is sampled for where the hose comes on.
SOURCE_STEP_FT = 5.0
#: Slack on "stays on the lot": a lot line traced to the tenth of a foot, and a
#: building the fit may stand a cell past it (``Drawn.fits`` False).
ON_LOT_FT = 1.0
#: How far inside the walls a line has to pass to be going THROUGH the
#: building rather than along it.
WALL_FT = 0.05
#: A lot traced with more corners than this is simplified first; a route's
#: length moves by less than the tolerance, and a few points of a hundred-
#: corner lot are not where a hose bends.
MAX_LOT_CORNERS = 120
SIMPLIFY_FT = 0.5


def street_offsets(
    points: np.ndarray, centrelines: shapely.STRtree | None, geoms: Sequence[BaseGeometry]
) -> np.ndarray:
    """How far past each street lot line point the truck stands: the distance
    to the nearest centreline of a road it can use, less :data:`HALF_ROAD_FT`,
    never below zero; infinite past :data:`MAX_GAP_FT`. Zero for every point
    where no centreline is held -- the lot line itself, which is a SHORTER
    offset than the real one: callers that cannot supply centrelines get a
    measure that may clear a lot it should not, and only the tests do that."""
    if centrelines is None or not len(geoms) or not len(points):
        return np.zeros(len(points))
    pts = shapely.points(points)
    idx = centrelines.nearest(pts)
    gap = shapely.distance(pts, np.asarray(geoms, dtype=object)[idx])
    return np.where(gap > MAX_GAP_FT, math.inf, np.maximum(gap - HALF_ROAD_FT, 0.0))


def load_truck_roads(path: Path) -> tuple[shapely.STRtree, np.ndarray]:
    """quadfit s1's street centrelines a truck can stand on
    (:data:`TRUCK_TYPES`), indexed: what :func:`street_offsets` reads."""
    import pandas as pd

    frame = pd.read_parquet(path, columns=["type", "alley", "wkb"])
    kind = pd.to_numeric(frame["type"], errors="coerce")
    keep = kind.isin(TRUCK_TYPES) & ~frame["alley"].fillna(False).astype(bool)
    geoms = shapely.from_wkb(frame.loc[keep, "wkb"].to_numpy())
    return shapely.STRtree(geoms), geoms


def _sources(lines: Sequence[tuple[float, float, float, float]]) -> np.ndarray:
    out: list[tuple[float, float]] = []
    for x1, y1, x2, y2 in lines:
        n = max(1, math.ceil(math.hypot(x2 - x1, y2 - y1) / SOURCE_STEP_FT))
        out.extend((x1 + (x2 - x1) * k / n, y1 + (y2 - y1) * k / n) for k in range(n + 1))
    return np.asarray(out, dtype=float).reshape(-1, 2)


def _feet(lines: Sequence[tuple[float, float, float, float]], nodes: np.ndarray) -> np.ndarray:
    """The point of each street line nearest each node."""
    out: list[tuple[float, float]] = []
    for x1, y1, x2, y2 in lines:
        dx, dy = x2 - x1, y2 - y1
        span = dx * dx + dy * dy
        for x, y in nodes:
            t = 0.0 if span == 0 else min(1.0, max(0.0, ((x - x1) * dx + (y - y1) * dy) / span))
            out.append((x1 + t * dx, y1 + t * dy))
    return np.asarray(out, dtype=float).reshape(-1, 2)


def _corners(geom: BaseGeometry) -> np.ndarray:
    polys = getattr(geom, "geoms", [geom])
    pts: list[tuple[float, float]] = []
    for p in polys:
        for ring in (p.exterior, *p.interiors):
            pts.extend(tuple(c[:2]) for c in list(ring.coords)[:-1])
    return np.asarray(pts, dtype=float).reshape(-1, 2)


def _bends(geom: BaseGeometry) -> np.ndarray:
    """The lot's corners a shortest route can bend at: the ones that point
    INTO the lot (an L's inside corner, the foot of a flag's pole), and every
    corner of a hole. A corner pointing out of the lot is never on a
    shortest route, so a rectangle lot adds none."""
    polys = getattr(geom, "geoms", [geom])
    pts: list[tuple[float, float]] = []
    for p in polys:
        ring = np.asarray(p.exterior.coords, dtype=float)[:-1, :2]
        if len(ring) >= 3:
            turn = 1.0 if shapely.is_ccw(p.exterior) else -1.0
            prev, nxt = np.roll(ring, 1, axis=0), np.roll(ring, -1, axis=0)
            a, b = ring - prev, nxt - ring
            cross = (a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) * turn
            pts.extend(map(tuple, ring[cross < 0]))
        for hole in p.interiors:
            pts.extend(tuple(c[:2]) for c in list(hole.coords)[:-1])
    return np.asarray(pts, dtype=float).reshape(-1, 2)


def _open(a: np.ndarray, b: np.ndarray, lot: BaseGeometry, inside: BaseGeometry) -> np.ndarray:
    """Which of the straight lines a[i] -> b[i] a hose can lie along."""
    if not len(a):
        return np.zeros(0, dtype=bool)
    segs = shapely.linestrings(np.stack([a, b], axis=1))
    return shapely.covers(lot, segs) & ~shapely.intersects(segs, inside)


def route_ft(
    building: BaseGeometry,
    lot: BaseGeometry,
    streets: Sequence[tuple[float, float, float, float]],
    offset: Callable[[np.ndarray], np.ndarray] | None = None,
) -> float | None:
    """The length of a route from the street to the farthest point of the
    building's walls (module docstring), or None where no route reaches it.

    ``streets`` are the lot's street lot lines; ``offset`` maps an (n, 2)
    array of points on them to how far past each the truck stands
    (:func:`street_offsets`), zero where not given.
    """
    if building is None or building.is_empty or lot is None or lot.is_empty or not streets:
        return None
    if len(_corners(lot)) > MAX_LOT_CORNERS:
        lot = lot.simplify(SIMPLIFY_FT, preserve_topology=True)
    walls = np.asarray(building.exterior.coords, dtype=float)[:-1, :2]
    nodes = np.vstack([walls, _bends(lot)])
    k = len(walls)
    free = lot.buffer(ON_LOT_FT)
    inside = building.buffer(-WALL_FT)
    shapely.prepare(free)
    shapely.prepare(inside)

    starts = np.vstack([_sources(streets), _feet(streets, walls)])
    base = offset(starts) if offset is not None else np.zeros(len(starts))
    # Every street point to every node it sees.
    si, ni = np.meshgrid(np.arange(len(starts)), np.arange(len(nodes)), indexing="ij")
    si, ni = si.ravel(), ni.ravel()
    seen = _open(starts[si], nodes[ni], free, inside)
    reach = np.full(len(nodes), math.inf)
    if seen.any():
        cost = base[si[seen]] + np.hypot(*(starts[si[seen]] - nodes[ni[seen]]).T)
        np.minimum.at(reach, ni[seen], cost)
    # Node to node, once each way.
    ai, bi = np.triu_indices(len(nodes), k=1)
    linked = _open(nodes[ai], nodes[bi], free, inside)
    adj: list[list[tuple[int, float]]] = [[] for _ in nodes]
    for a, b in zip(ai[linked], bi[linked]):
        d = float(math.hypot(*(nodes[a] - nodes[b])))
        adj[a].append((b, d))
        adj[b].append((a, d))
    heap = [(float(d), i) for i, d in enumerate(reach) if math.isfinite(d)]
    heapq.heapify(heap)
    done = np.zeros(len(nodes), dtype=bool)
    while heap:
        d, i = heapq.heappop(heap)
        if done[i]:
            continue
        done[i] = True
        for j, w in adj[i]:
            if d + w < reach[j]:
                reach[j] = d + w
                heapq.heappush(heap, (reach[j], j))
    corner = reach[:k]
    if not np.isfinite(corner).any():
        return None
    # Round the walls: the farthest point of each wall, reached from
    # whichever of its two corners is nearer by the route.
    far = 0.0
    for i in range(k):
        g1, g2 = corner[i], corner[(i + 1) % k]
        side = float(math.hypot(*(walls[(i + 1) % k] - walls[i])))
        if not (math.isfinite(g1) or math.isfinite(g2)):
            return None
        if abs(g1 - g2) <= side:
            far = max(far, (g1 + g2 + side) / 2.0)
        else:
            far = max(far, min(g1, g2) + side)
    return far


def hose_offsets(
    points: np.ndarray,
    centrelines: shapely.STRtree | None,
    geoms: Sequence[BaseGeometry],
    edges: StreetEdges | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """How far past each street lot line point the hose starts, read two
    ways: (strict, curb).

    Strict: :data:`CURB_START_FT` out from the near curb, capped at the
    street's middle (the centreline); curb: at the near curb. Where
    ``edges`` place no curb (or there are no ``edges``), the street is the
    narrowest a truck may use (Steph 2026-10-05, "assume narrow" until a
    width is measured): its curb :data:`HALF_ROAD_FT` off the centreline,
    where :func:`street_offsets` stands the truck, so the strict start is
    the middle. A curb placed by a width alone never puts the strict start
    nearer the lot than that curb (:mod:`flats.geom.curbs`). Infinite past
    :data:`MAX_GAP_FT`, zero where no centreline is held, as
    :func:`street_offsets`.
    """
    old = street_offsets(points, centrelines, geoms)
    if centrelines is None or not len(geoms) or not len(points):
        return old, old.copy()
    from flats.geom.curbs import Source

    pts = shapely.points(points)
    lines = np.asarray(geoms, dtype=object)[centrelines.nearest(pts)]
    feet = shapely.get_coordinates(shapely.shortest_line(pts, lines)).reshape(-1, 2, 2)[:, 1]
    gap = shapely.distance(pts, lines)
    if edges is None:
        src = np.full(len(points), Source.none, dtype=np.int8)
        near = old
    else:
        near, src = edges.near(np.asarray(points, dtype=float), feet, lines)
        near = np.where(src == Source.none, old, near)
    strict = np.minimum(near + CURB_START_FT, gap)
    strict = np.where(src == Source.width, np.maximum(strict, old), strict)
    curb = np.minimum(near, gap)
    far = ~np.isfinite(old)
    return np.where(far, math.inf, strict), np.where(far, math.inf, curb)


def point_offset(
    centrelines: shapely.STRtree | None,
    geoms: Sequence[BaseGeometry],
    edges: StreetEdges | None = None,
    *,
    reading: str = "strict",
) -> Callable[[np.ndarray], np.ndarray]:
    """:func:`hose_offsets` bound to one street index, as :func:`route_ft`
    takes it: the ``reading`` of :data:`READINGS` asked for."""
    if reading not in READINGS:
        raise ValueError(f"reading must be one of {READINGS}, not {reading!r}")
    pick = READINGS.index(reading)
    return lambda pts: hose_offsets(pts, centrelines, geoms, edges)[pick]


def reachable(
    lines: Sequence[tuple[float, float, float, float]],
    offset: Callable[[np.ndarray], np.ndarray] | None = None,
) -> tuple[tuple[float, float, float, float], ...]:
    """The street lines a truck can come in over: those with a point the
    truck can stand off (a finite offset). Every line where no offset is
    given."""
    if offset is None:
        return tuple(lines)
    return tuple(line for line in lines if np.isfinite(offset(_sources([line]))).any())


__all__ = [
    "CURB_START_FT",
    "HALF_ROAD_FT",
    "MAX_GAP_FT",
    "READINGS",
    "TRUCK_TYPES",
    "hose_offsets",
    "load_truck_roads",
    "point_offset",
    "reachable",
    "route_ft",
    "street_offsets",
]
