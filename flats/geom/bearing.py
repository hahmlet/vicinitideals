"""Yards drawn toward a compass direction: Clackamas ZDO 1005.02(L).

Every other setback in this corpus belongs to a CLASS of lot line -- front,
side, rear -- and the class is what the edge classifier names. 1005.02(L) does
not. It separates a building in the HDR, SHD and RCHDR districts from the lot
line on its NORTH by "a 60-degree angle line from the top of the structure to
the natural ground elevation north", and from the lines on its EAST and WEST by
a 15-degree one ("Separation = b x .267 (tan 15 degrees)", which is what says
the angle is off the vertical). South owes nothing. Table 315-4 then answers
those districts' side and rear yards with "See 1005.02(L)", so the yard a line
owes is a property of which way it faces, not of what it is called.

**The cut is exact.** A building point ``p`` meets the north separation when
the ground from ``p`` to ``N`` feet north of it is all on the lot: the lot
eroded by the segment ``(0, N north)``. That erosion is the lot less, for
every boundary segment ``s``, the parallelogram ``s`` swept ``N`` feet SOUTH
-- a north line loses a strip ``N`` deep, a line facing north-east loses
``N cos(angle)``, an east line loses nothing to it. "Diagonals by component"
and "curves segment by segment" are therefore not special cases: a diagonal
is one segment whose sweep has that depth, and a curve is the polyline the
taxlot fabric stores, swept one segment at a time. East-west is the same
with the segment ``(-EW east, +EW east)``.

**North is both norths.** The working CRS is EPSG:2913, whose grid north
differs from true north by the meridian convergence (about 1.5 degrees in
Clackamas County). The code does not say which; the cut takes both, which is
never looser than either.

**Relief, read on the line that owes it.**

* 1005.02(L)(1)(a): the north separation "may include intervening streets
  plus 15 feet into the property" north of the street. A line on a public
  road owes ``N - 15`` and the road's own width is not measured, so it is
  counted as nothing (never larger than the legal envelope).
* 1005.02(L)(3): the east-west separation applies "except when abutting a
  public, County or state road". A line on a public road owes none of it.
* (1)(b) and (1)(c) (the neighbour's parking area, an easement) are facts
  about the lot next door nothing measures, and are not taken.

**What it does not hold.** "Natural ground elevation north": the line is
drawn to the ground, so a lot falling to the north owes more and one rising
owes less. Flat ground is assumed.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from functools import lru_cache

import shapely
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry

from flats.geom.edges import Edge, EdgeClass

#: How near a taxlot segment must lie to a classified edge to take that edge's
#: road. :func:`flats.geom.edges._segments` simplifies the ring at one foot.
_ON_EDGE_FT = 1.5


@lru_cache(maxsize=1)
def _to_lonlat():  # pragma: no cover - trivial
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:2913", "EPSG:4326", always_xy=True)


@lru_cache(maxsize=1)
def _to_grid():  # pragma: no cover - trivial
    from pyproj import Transformer

    return Transformer.from_crs("EPSG:4326", "EPSG:2913", always_xy=True)


def true_north_deg(x: float, y: float) -> float:
    """The grid azimuth of true north at ``(x, y)`` in EPSG:2913, in degrees
    clockwise from grid north. Positive west of the projection's central
    meridian (120.5 W), which is all of the Portland region: the meridians
    lean in toward it going north."""
    lon, lat = _to_lonlat().transform(x, y)
    nx, ny = _to_grid().transform(lon, lat + 0.01)
    return math.degrees(math.atan2(nx - x, ny - y))


def _segments(geom: BaseGeometry) -> list[tuple[float, float, float, float]]:
    out: list[tuple[float, float, float, float]] = []
    for poly in shapely.get_parts(geom):
        if poly.geom_type != "Polygon":
            continue
        for ring in (poly.exterior, *poly.interiors):
            xy = list(ring.coords)
            out.extend(
                (x1, y1, x2, y2)
                for (x1, y1), (x2, y2) in zip(xy, xy[1:])
                if (x1, y1) != (x2, y2)
            )
    return out


def _on_road(seg: tuple[float, float, float, float], roads: Sequence[LineString]) -> bool:
    x1, y1, x2, y2 = seg
    a, b = shapely.points([(x1, y1), (x2, y2)])
    return any(r.distance(a) <= _ON_EDGE_FT and r.distance(b) <= _ON_EDGE_FT for r in roads)


def _swept(seg: tuple[float, float, float, float], ax: float, ay: float, bx: float, by: float) -> Polygon | None:
    """``seg`` swept from offset ``a`` to offset ``b``; None where that has
    no area (a line parallel to the sweep)."""
    x1, y1, x2, y2 = seg
    poly = Polygon(
        [(x1 + ax, y1 + ay), (x2 + ax, y2 + ay), (x2 + bx, y2 + by), (x1 + bx, y1 + by)]
    )
    return poly if abs(poly.area) > 1e-6 else None


def bearing_cut(
    lot: BaseGeometry,
    edges: Sequence[Edge],
    *,
    north_ft: float,
    east_west_ft: float,
    street_credit_ft: float = 0.0,
    true_north: float | None = None,
) -> BaseGeometry | None:
    """The ground 1005.02(L) keeps a building off, as one geometry to take
    from the lot; None where neither distance is owed.

    ``edges`` are the lot's classified lines: a segment of the taxlot ring
    lying along a street edge with ``public_road`` set takes the road's
    relief. With no edges every segment owes the full distances.
    ``true_north`` is :func:`true_north_deg` at the lot; None sweeps grid
    north alone.
    """
    if lot is None or lot.is_empty or (north_ft <= 0 and east_west_ft <= 0):
        return None
    roads = [
        LineString([(e.x1, e.y1), (e.x2, e.y2)])
        for e in edges
        if e.public_road and e.cls in (EdgeClass.front, EdgeClass.street_side)
    ]
    norths = {0.0} if true_north is None else {0.0, round(float(true_north), 6)}
    pieces: list[Polygon] = []
    for seg in _segments(lot):
        road = bool(roads) and _on_road(seg, roads)
        n = max(0.0, north_ft - street_credit_ft) if road else north_ft
        ew = 0.0 if road else east_west_ft
        for az in norths:
            r = math.radians(az)
            # North and east as unit vectors in the grid.
            nx, ny = math.sin(r), math.cos(r)
            ex, ey = math.cos(r), -math.sin(r)
            if n > 0:
                # Every line swept n feet SOUTH: the ground within n feet
                # south of a lot line has that line within n feet north.
                got = _swept(seg, 0.0, 0.0, -n * nx, -n * ny)
                if got is not None:
                    pieces.append(got)
            if ew > 0:
                got = _swept(seg, -ew * ex, -ew * ey, ew * ex, ew * ey)
                if got is not None:
                    pieces.append(got)
    if not pieces:
        return None
    return shapely.union_all([p.buffer(0) for p in pieces])
