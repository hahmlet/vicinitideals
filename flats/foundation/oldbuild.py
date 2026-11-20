"""MEASURE layer: walls over a building that stands today (FD6 section 5.8, step 1).

An old house may have had a basement; once it is pulled down the hole is
backfilled, and backfill is not ground a footing may sit on (FD7). Whether a
basement was there is not known, so this layer only measures where the pod's
walls and floor would lie over one:

* each building outline (in the model frame: x 0..80 along the street face,
  y 0..25 front to back) is grown by ``grow_ft`` with square corners -- the old
  hole was dug wider than the basement;
* each of the seven wall lines is cut by the grown outline into **stretches**:
  length, and whether a stretch reaches a pod corner (there the wall would
  overhang rather than bridge);
* the pod floor over the grown outline (sq ft).

Pure geometry, no price: :mod:`flats.foundation.infill` prices it. The building
outlines and their years are the ones FD5 pass 2 used (RLIS footprints,
``YEAR_BUILT``); the caller turns them into model coordinates
(:meth:`flats.foundation.frame.Frame.model`).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from flats.foundation.measure import OldBuilding, Stretch, wall_lines
from flats.foundation.settings import Settings


@dataclass(frozen=True, slots=True)
class Outline:
    """One footprint in model coordinates: its exterior ring(s) and its id and year."""

    rings: tuple[tuple[tuple[float, float], ...], ...]
    bldg_id: str | None = None
    year_built: int | None = None


def _pod(s: Settings) -> Any:
    import shapely

    return shapely.box(0.0, 0.0, s.length_ft, s.width_ft)


def _corners(s: Settings) -> tuple[tuple[float, float], ...]:
    return ((0.0, 0.0), (s.length_ft, 0.0), (0.0, s.width_ft), (s.length_ft, s.width_ft))


def _pieces(geom: Any) -> Iterable[Any]:
    """The line pieces of an intersection (points and empties dropped)."""
    if geom.is_empty:
        return
    if geom.geom_type == "LineString":
        yield geom
    elif hasattr(geom, "geoms"):
        for g in geom.geoms:
            yield from _pieces(g)


def polygon_of(outline: Outline) -> Any:
    import shapely

    polys = [shapely.Polygon(r) for r in outline.rings if len(r) >= 3]
    g = shapely.union_all([p if p.is_valid else shapely.make_valid(p) for p in polys]) if polys else shapely.Polygon()
    return g


def measure_one(outline: Outline, s: Settings) -> OldBuilding | None:
    """One building's stretches and floor over the pod, or None when its grown
    outline does not reach the pod."""
    import shapely

    poly = polygon_of(outline)
    if poly.is_empty:
        return None
    grown = shapely.buffer(poly, s.grow_ft, join_style="mitre")
    pod = _pod(s)
    if not shapely.intersects(grown, pod):
        return None
    corners = _corners(s)
    stretches = []
    for wl in wall_lines(s):
        line = shapely.LineString([(wl.x0, wl.y0), (wl.x1, wl.y1)])
        for piece in _pieces(shapely.intersection(line, grown)):
            if piece.length <= 0:
                continue
            (ax, ay), (bx, by) = piece.coords[0], piece.coords[-1]
            corner = any(
                min(abs(ax - cx) + abs(ay - cy), abs(bx - cx) + abs(by - cy)) <= s.corner_within_ft for cx, cy in corners
            )
            stretches.append(Stretch(wl.name, wl.kind, ax, ay, bx, by, float(piece.length), corner))
    floor = float(shapely.area(shapely.intersection(grown, pod)))
    if not stretches and floor <= 0:
        return None
    return OldBuilding(
        bldg_id=outline.bldg_id,
        year_built=outline.year_built,
        area_sf=float(shapely.area(poly)),
        floor_sf=floor,
        stretches=tuple(stretches),
    )


def measure_all(outlines: Sequence[Outline], s: Settings) -> tuple[OldBuilding, ...]:
    """Every building whose grown outline reaches the pod, in the order given."""
    out = []
    for o in outlines:
        b = measure_one(o, s)
        if b is not None:
            out.append(b)
    return tuple(out)


def model_outlines(frame: Any, geoms: Sequence[Any], props: Sequence[dict[str, Any]], s: Settings) -> list[Outline]:
    """World footprints (EPSG:2913 shapely polygons) and their RLIS properties ->
    model-frame outlines for one lot's pod."""
    import numpy as np

    out = []
    for g, p in zip(geoms, props, strict=True):
        polys = list(g.geoms) if hasattr(g, "geoms") else [g]
        rings = []
        for poly in polys:
            if poly.geom_type != "Polygon" or poly.is_empty:
                continue
            xy = np.asarray(poly.exterior.coords, dtype=float)
            mx = frame.model(xy, s.length_ft, s.width_ft, s.box_ft)
            rings.append(tuple((float(a), float(b)) for a, b in mx))
        if not rings:
            continue
        year = p.get("YEAR_BUILT")
        try:
            y = int(year) if year is not None else None
        except (TypeError, ValueError):
            y = None
        bid = p.get("BLDG_ID")
        out.append(Outline(tuple(rings), None if bid in (None, "") else str(bid), y if y and y > 0 else None))
    return out
