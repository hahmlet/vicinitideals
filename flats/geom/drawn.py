"""Whether a lot lies inside an area a layer traced itself (``drawn_areas``).

Some codes switch a use on inside a boundary they draw within a zone and
publish only as a picture. Tualatin's Residential Sub-District is ten blocks
of Comprehensive Plan Map 10-3 (TDC 58.200(2)(a)), and housing is permitted
in the CC zone there and nowhere else; the city's GIS has no layer for the
blocks. The layer traces the area into a GeoJSON file
(:class:`flats.rules.model.DrawnArea`) and this module answers the fact for
each lot of the zones the area names. The same holds for a boundary a city
publishes apart from its zoning (West Linn's Willamette Historic District)
and for one the code draws in words along a named street (Gresham's "land
lying north of Marine Drive").

**The answer is the share of the lot inside.** At least
:data:`INSIDE_SHARE` of the lot's area inside is True; at most
:data:`OUTSIDE_SHARE` is False; anything between is a lot the line cuts
through, and is left unanswered -- the lot screens UNKNOWN on the fact
exactly as if nothing had been traced. A tracing built from the taxlots the
map draws (Tualatin's is) puts every lot the map puts in a block wholly
inside and every other lot wholly outside; the band is for a lot split or
merged since the map was drawn.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from flats.rules.loader import AREAS_ROOT

#: At least this share of the lot inside the area is inside.
INSIDE_SHARE = 0.9
#: At most this share inside is outside.
OUTSIDE_SHARE = 0.1


@lru_cache(maxsize=None)
def load_area(file: str) -> Any:
    """The traced area in ``file`` (under ``flats/config/areas``) as one
    shapely geometry in EPSG:2913, every feature unioned."""
    from shapely.geometry import shape
    from shapely.ops import unary_union

    data = json.loads((AREAS_ROOT / file).read_text(encoding="utf-8"))
    return unary_union([shape(f["geometry"]).buffer(0) for f in data["features"]])


def share_inside(lot_geom: Any, area: Any) -> float | None:
    """The share of ``lot_geom``'s area inside ``area``; None for a lot with
    no area to share."""
    if lot_geom is None or lot_geom.is_empty or lot_geom.area <= 0:
        return None
    lot = lot_geom if lot_geom.is_valid else lot_geom.buffer(0)
    return lot.intersection(area).area / lot.area


def observed_drawn(lot_geom: Any, area: Any) -> bool | None:
    """Whether the lot lies inside ``area``: True, False, or None where the
    boundary cuts through it (or the lot has no shape)."""
    share = share_inside(lot_geom, area)
    if share is None:
        return None
    if share >= INSIDE_SHARE:
        return True
    if share <= OUTSIDE_SHARE:
        return False
    return None


#: A lot is shrunk this far before it is asked whether it touches a traced
#: permit area, so a shared lot line is not a touch (quadfit's s5o does the
#: same for every overlay flag).
TOUCH_SHRINK_FT = 0.5


@lru_cache(maxsize=None)
def load_edged_area(file: str) -> Any:
    """The traced area in ``file`` with each feature grown by its own
    ``EDGE_FT`` property, as one prepared shapely geometry in EPSG:2913.

    A boundary traced off a printed map is only as sharp as the line the
    map draws it with; ``EDGE_FT`` is that width on the ground, stated per
    feature in the file, and a lot within it is read as touching. A feature
    taken from a published layer states 0.
    """
    import shapely
    from shapely.geometry import shape

    data = json.loads((AREAS_ROOT / file).read_text(encoding="utf-8"))
    parts = []
    for f in data["features"]:
        geom = shape(f["geometry"]).buffer(0)
        edge = float((f.get("properties") or {}).get("EDGE_FT") or 0.0)
        parts.append(geom.buffer(edge) if edge > 0 else geom)
    area = shapely.union_all(parts)
    shapely.prepare(area)
    return area


def touches_area(lot_geom: Any, area: Any) -> bool:
    """Whether any of the lot, less a :data:`TOUCH_SHRINK_FT` rim, lies in
    ``area``. False for a lot with no shape: nothing was measured."""
    if lot_geom is None or lot_geom.is_empty:
        return False
    lot = lot_geom if lot_geom.is_valid else lot_geom.buffer(0)
    inner = lot.buffer(-TOUCH_SHRINK_FT)
    if inner.is_empty:
        inner = lot
    return bool(area.intersects(inner))


@lru_cache(maxsize=None)
def edge_ft(file: str) -> float:
    """The widest ``EDGE_FT`` any feature of the traced area in ``file``
    states: how far off the tracing's line can be, on the ground."""
    data = json.loads((AREAS_ROOT / file).read_text(encoding="utf-8"))
    return max((float((f.get("properties") or {}).get("EDGE_FT") or 0.0) for f in data["features"]), default=0.0)


@lru_cache(maxsize=None)
def load_core_area(file: str) -> Any:
    """The traced area in ``file`` less a rim :func:`edge_ft` wide: the
    ground that is inside it wherever in its drawn line the true edge runs.
    One prepared geometry; the features are unioned first, so two that
    share an edge lose no rim along it."""
    import shapely

    core = load_area(file).buffer(-edge_ft(file))
    shapely.prepare(core)
    return core


def reaches_past_edge(lot_geom: Any, file: str) -> bool:
    """Whether the traced area in ``file`` is on this lot by more than its
    own drawn line could explain (:func:`edge_ft`, 14 ft for a 1 pt line
    on a 1:12,000 sheet). True when either holds:

    * the area reaches further into the lot than that width -- the lot,
      inset by it, still meets the traced area;
    * the lot reaches further into the area than that width -- the lot
      (less the :data:`TOUCH_SHRINK_FT` rim) meets :func:`load_core_area`.

    False for an overlap that is everywhere within that width of both the
    lot's line and the area's: a strip along a shared line, which a tracing
    cannot tell from its own error. Two tests because each alone misses a
    case: a lot too narrow to survive the inset lying wholly inside the
    area, and a corridor of the area too thin to survive the erosion
    crossing the middle of a lot. False for a lot with no shape."""
    if lot_geom is None or lot_geom.is_empty:
        return False
    lot = lot_geom if lot_geom.is_valid else lot_geom.buffer(0)
    edge = edge_ft(file)
    if edge <= 0:
        return touches_area(lot, load_area(file))
    core = load_core_area(file)
    if not core.is_empty and touches_area(lot, core):
        return True
    inner = lot.buffer(-edge)
    return bool(not inner.is_empty and load_area(file).intersects(inner))
