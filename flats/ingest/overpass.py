"""OpenStreetMap through the Overpass API: the map of what land is used for.

Steph ruled on 2026-10-06 that institutional land -- schools, hospitals,
municipal sites, parks, utilities, airports, rail, malls -- is RED and never
scanned (:mod:`flats.geom.institutional`). None of the three counties
publishes one layer that says so: Washington's roll marks public land, the
other two rolls do not, and Metro's ORCA holds parks and school land only.
OpenStreetMap does, tagged by hand across the whole state, so the acquire
stage takes an extract of it like any other source: a dated file in the
working CRS, hashed, with a manifest entry.

**The query.** A dataset of kind ``overpass`` declares the selector lines of
an Overpass QL union (``query``), each with ``{bbox}`` where the box goes,
and the box itself (``bbox_4326``, west/south/east/north like every other
dataset). :func:`compose` wraps them into one request that returns every
element with its geometry (``out geom``).

**The shapes.** A node is a point. A closed way is a polygon unless its tags
say it is a line (a railway track that loops is still a track). An open way
is a line. A multipolygon relation is assembled from its member ways --
outer rings polygonised, inner rings cut out -- and any other relation (a
route, a site) is skipped and counted: its members carry their own tags when
they matter. Coordinates arrive in degrees and are written in the working
CRS.

**What it refuses.** Overpass answers a query that ran out of time or memory
with HTTP 200, a partial result and a ``remark``; a file written from it
would read as the whole map. A remark raises, and the dataset is ``failed``.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Iterator, Mapping

#: Tags whose value makes a closed way a line rather than an area.
LINE_TAGS: dict[str, frozenset[str]] = {
    "railway": frozenset({"rail", "light_rail", "subway", "tram", "narrow_gauge", "monorail"}),
}

#: Relation types that describe an area and are assembled from their rings.
AREA_RELATIONS = frozenset({"multipolygon", "boundary"})


class OverpassError(Exception):
    """The server's answer is not the whole extract."""


def compose(selectors: str, bbox_4326: tuple[float, float, float, float], timeout_s: int = 600) -> str:
    """The Overpass QL for ``selectors`` (one statement a line, ``{bbox}`` in
    each) inside the box ``(west, south, east, north)``."""
    west, south, east, north = bbox_4326
    box = f"{south},{west},{north},{east}"
    lines = [ln.strip() for ln in selectors.strip().splitlines() if ln.strip()]
    if not lines or any("{bbox}" not in ln for ln in lines):
        raise ValueError("every selector line must say where the box goes: {bbox}")
    body = "\n".join("  " + ln.replace("{bbox}", box) for ln in lines)
    return f"[out:json][timeout:{timeout_s}];\n(\n{body}\n);\nout geom;"


def check(doc: Mapping[str, Any]) -> None:
    """Raise unless ``doc`` is a complete answer."""
    remark = str(doc.get("remark") or "")
    if remark:
        raise OverpassError(f"the server cut the answer short: {remark[:300]}")
    if not isinstance(doc.get("elements"), list):
        raise OverpassError("the answer holds no element list")


def _is_line(tags: Mapping[str, str]) -> bool:
    if tags.get("area") == "yes":
        return False
    return any(tags.get(k) in values for k, values in LINE_TAGS.items())


def _coords(points: Iterable[Mapping[str, Any]] | None) -> list[tuple[float, float]]:
    return [(float(p["lon"]), float(p["lat"])) for p in (points or []) if p]


def _rings(members: Iterable[Mapping[str, Any]], role: str) -> Any:
    """The polygons the member ways of ``role`` close into."""
    import shapely
    from shapely.ops import polygonize, unary_union

    lines = [
        shapely.LineString(c)
        for m in members
        if m.get("type") == "way" and (m.get("role") or "outer") == role
        for c in [_coords(m.get("geometry"))]
        if len(c) >= 2
    ]
    if not lines:
        return None
    polys = list(polygonize(unary_union(lines)))
    return unary_union(polys) if polys else None


def shape_of(element: Mapping[str, Any]) -> Any:
    """The element's geometry in degrees (shapely), or None when it has none."""
    import shapely

    kind = element.get("type")
    tags = element.get("tags") or {}
    if kind == "node":
        if "lon" not in element or "lat" not in element:
            return None
        return shapely.Point(float(element["lon"]), float(element["lat"]))
    if kind == "way":
        c = _coords(element.get("geometry"))
        if len(c) < 2:
            return None
        closed = len(c) >= 4 and c[0] == c[-1]
        if closed and not _is_line(tags):
            poly = shapely.Polygon(c)
            return poly if poly.is_valid else shapely.make_valid(poly)
        return shapely.LineString(c)
    if kind == "relation" and tags.get("type") in AREA_RELATIONS:
        members = element.get("members") or []
        outer = _rings(members, "outer")
        if outer is None or outer.is_empty:
            return None
        inner = _rings(members, "inner")
        return outer.difference(inner) if inner is not None and not inner.is_empty else outer
    return None


def features(
    elements: Iterable[Mapping[str, Any]],
    keep: Iterable[str],
    to_working: Callable[[Any], Any],
    skipped: dict[str, int] | None = None,
) -> Iterator[dict[str, Any]]:
    """GeoJSON features in the working CRS, one per element with a shape.

    ``keep`` names the tags copied onto the feature; ``osm`` is always
    written (``way/123``) so a reading can be traced back to the element.
    ``skipped`` counts what had no shape, by element type.
    """
    import shapely

    keep = tuple(keep)
    for el in elements:
        geom = shape_of(el)
        if geom is None or geom.is_empty:
            if skipped is not None:
                key = f"{el.get('type')}:{(el.get('tags') or {}).get('type', '')}".rstrip(":")
                skipped[key] = skipped.get(key, 0) + 1
            continue
        tags = el.get("tags") or {}
        props: dict[str, Any] = {"osm": f"{el.get('type')}/{el.get('id')}"}
        props.update({k: tags[k] for k in keep if k in tags})
        yield {
            "type": "Feature",
            "properties": props,
            "geometry": shapely.geometry.mapping(to_working(geom)),
        }


def reprojector(srid: int) -> Callable[[Any], Any]:
    """Degrees (lon/lat) to ``srid``, for a shapely geometry."""
    import shapely
    from pyproj import Transformer

    t = Transformer.from_crs(4326, srid, always_xy=True)

    def to(geom: Any) -> Any:
        return shapely.transform(geom, lambda xy: _stack(t.transform(xy[:, 0], xy[:, 1])))

    return to


def _stack(xy: tuple[Any, Any]) -> Any:
    import numpy as np

    return np.column_stack(xy)


__all__ = ["AREA_RELATIONS", "LINE_TAGS", "OverpassError", "check", "compose", "features", "reprojector", "shape_of"]
