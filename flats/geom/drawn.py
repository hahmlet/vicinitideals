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
