"""FD5 pass 2: what the placed building would stand on (report only).

The pure measures behind ``scripts/flats_fd5_pass2.py``, the foundation
research's pass 2 requests (FOLLOWUPS 199; Factory-Sim FD5). Nothing here is
read by a screen, a fit, a colour or a page: it measures the drawn 80 x 25 ft
footprint of a live GREEN lot against

* the existing building footprints (Metro RLIS Building Footprint Database,
  the layer the lot occupancy label is built on, :mod:`flats.ingest.occupancy`):
  how much of the placed footprint stands on an existing building, and how far
  it is from the nearest one when it stands on none;
* mapped artificial fill (DOGAMI O-12-02 unit ``Aaf``): whether the footprint
  touches it, and the share;
* the street lot lines: which 80 ft face is the street-side face, how far it
  stands from the street and how far it is turned from the street's direction.

Every geometry is a shapely geometry in Oregon North international feet
(EPSG:2913), the lot table's projection.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

from flats.ingest.occupancy import MIN_PIECE_SHARE, MIN_STRUCTURE_SQFT

#: The overlap bands the hand-off asks for (FD5 item 1).
OVERLAP_BANDS = ("none", "under 25%", "25% and over", "not held")
OVERLAP_CUT = 0.25
#: An overlap under this many square feet is a drawing sliver (the footprint
#: layer's line work and the lot fit's rounding), not a building under the pod.
SLIVER_SQFT = 1.0
#: The year-built bands the hand-off asks for.
YEAR_BANDS = ("before 1940", "1940-1959", "1960 on", "not held")
#: How far the nearest building anywhere (a neighbour's included) is looked for.
NEAR_ANY_FT = 300.0
#: A lot with no footprint at all within this distance is read as outside the
#: footprint layer's coverage, never as "no building".
COVERAGE_FT = 1500.0

#: The DOGAMI O-12-02 unit codes that mean artificial fill (``MAP_UNIT_L``):
#: "Aaf", "Artificial fill" -- "Man-made deposits of mixed gravel, sand, silt,
#: clay, and other debris" (O-12-02 report). Its ``Qf`` is debris-flow fans,
#: natural ground, and is not fill.
FILL_UNITS = frozenset({"Aaf"})
#: The share of the footprint the fill map must cover for "no fill" to stand.
FULL_COVER = 0.999


def overlap_band(share: float | None) -> str:
    """The hand-off's band for a share of the placed footprint standing on an
    existing building; ``None`` is "not held" (no footprint data)."""
    if share is None:
        return "not held"
    if share <= 0:
        return "none"
    return "under 25%" if share < OVERLAP_CUT else "25% and over"


def year_band(year: Any) -> str:
    """The hand-off's year-built band; a blank or zero year is "not held"."""
    try:
        y = int(float(year))
    except (TypeError, ValueError):
        return "not held"
    if y <= 0:
        return "not held"
    if y < 1940:
        return "before 1940"
    return "1940-1959" if y < 1960 else "1960 on"


def counted_on_lot(lot: Any, footprint: Any) -> Any | None:
    """The piece of ``footprint`` that counts as a building on ``lot`` by the
    occupancy label's own rule (:func:`flats.ingest.occupancy.pieces_by_lot`):
    at least 200 sq ft and at least 20% of the footprint. ``None`` otherwise."""
    import shapely

    whole = float(shapely.area(footprint))
    if whole < MIN_STRUCTURE_SQFT:
        return None
    piece = footprint if shapely.contains(lot, footprint) else shapely.intersection(lot, footprint)
    area = float(shapely.area(piece))
    if area >= MIN_STRUCTURE_SQFT and area >= MIN_PIECE_SHARE * whole:
        return piece
    return None


def stand_on(
    fp: Any,
    lot: Any,
    near: Sequence[Any],
    near_any: Sequence[Any] = (),
) -> dict[str, Any]:
    """What the placed footprint ``fp`` stands on among existing buildings.

    ``near`` are the footprints that touch ``lot`` (any size); ``near_any``
    those within :data:`NEAR_ANY_FT` of ``fp`` (neighbours' included). The
    overlap counts every footprint, a shed or a neighbour's wall drifting over
    the line included: the pod would stand on it all the same. The distance is
    to the nearest building that counts on the lot (:func:`counted_on_lot`),
    and is left blank where the footprint overlaps one or the lot has none.
    """
    import shapely

    area = float(shapely.area(fp))
    hits = [g for g in near if shapely.intersects(fp, g)]
    over = 0.0
    if hits:
        over = float(shapely.area(shapely.intersection(fp, shapely.union_all(hits))))
    if over < SLIVER_SQFT:
        over = 0.0
    pieces = [p for p in (counted_on_lot(lot, g) for g in near) if p is not None]
    gap = None
    if over == 0.0 and pieces:
        gap = min(float(shapely.distance(fp, p)) for p in pieces)
    gap_any = min((float(shapely.distance(fp, g)) for g in near_any), default=None)
    if over > 0:
        gap_any = 0.0
    share = over / area if area > 0 else None
    return {
        "bldg_on_lot_n": len(pieces),
        "bldg_on_lot_sqft": round(sum(float(shapely.area(p)) for p in pieces), 1),
        "bldg_overlap_sqft": round(over, 1),
        "bldg_overlap_share": None if share is None else round(share, 4),
        "bldg_overlap_band": overlap_band(share),
        "bldg_gap_ft": None if gap is None else round(gap, 1),
        "bldg_gap_any_ft": None if gap_any is None else round(gap_any, 1),
    }


def fill_measure(fp: Any, fill: Sequence[Any], extent: Sequence[Any]) -> dict[str, Any]:
    """Mapped artificial fill under the footprint.

    ``fill`` are the fill polygons near ``fp``, ``extent`` the map's unit
    polygons near it (any unit: the map's coverage). Where the map covers no
    part of the footprint the answer is "not mapped" (None), never "no fill".
    """
    import shapely

    area = float(shapely.area(fp))
    covered = 0.0
    if extent:
        covered = float(shapely.area(shapely.intersection(fp, shapely.union_all(list(extent)))))
    cover = covered / area if area > 0 else 0.0
    if cover <= 0:
        return {"fill_map_cover": 0.0, "fill_touches": None, "fill_share": None, "fill_dist_ft": None}
    hit = [g for g in fill if shapely.intersects(fp, g)]
    on = float(shapely.area(shapely.intersection(fp, shapely.union_all(hit)))) if hit else 0.0
    dist = min((float(shapely.distance(fp, g)) for g in fill), default=None)
    # A footprint the map covers only in part and shows no fill on is
    # unanswered (the unmapped part may hold fill), never "no fill".
    touches: bool | None = True if on > 0 else (False if cover >= FULL_COVER else None)
    return {
        "fill_map_cover": round(min(cover, 1.0), 4),
        "fill_touches": touches,
        "fill_share": round(on / area, 4),
        "fill_dist_ft": None if dist is None else round(dist, 1),
    }


Seg = tuple[float, float, float, float]


def _bearing(x1: float, y1: float, x2: float, y2: float) -> float:
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0


def _turn(a: float, b: float) -> float:
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _seg_dist(x: float, y: float, s: Seg) -> float:
    x1, y1, x2, y2 = s
    dx, dy = x2 - x1, y2 - y1
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / ll))
    return math.hypot(x - (x1 + t * dx), y - (y1 + t * dy))


def front_face(fl: tuple[float, float], fr: tuple[float, float], bl: tuple[float, float],
               br: tuple[float, float], streets: Iterable[Seg]) -> dict[str, Any]:
    """The street-side 80 ft face of a drawn footprint, named by
    :func:`flats.ingest.fd2.frame` (``fl``-``fr`` the face nearer a street
    lot line, ``bl``-``br`` the far face): how far each face's middle stands
    from the nearest street lot line, and how far the face is turned from
    that line's direction (0 = parallel to the street, 90 = end-on)."""
    segs = [s for s in streets]
    if not segs:
        return {"front_face_street_ft": None, "back_face_street_ft": None, "front_face_turn_deg": None}
    fm = ((fl[0] + fr[0]) / 2, (fl[1] + fr[1]) / 2)
    bm = ((bl[0] + br[0]) / 2, (bl[1] + br[1]) / 2)
    near = min(segs, key=lambda s: _seg_dist(fm[0], fm[1], s))
    return {
        "front_face_street_ft": round(_seg_dist(fm[0], fm[1], near), 1),
        "back_face_street_ft": round(min(_seg_dist(bm[0], bm[1], s) for s in segs), 1),
        "front_face_turn_deg": round(_turn(_bearing(*fl, *fr), _bearing(*near)), 1),
    }
