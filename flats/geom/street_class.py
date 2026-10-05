"""Whether a lot's streets are local streets, read off a city's TSP map.

The registry has carried ``local_street`` since Lake Oswego's street-side
yard was encoded, and nothing answered it: street-side setbacks, driveway
aprons and Villebois's front yard are all written per street class, and the
corpus took the stricter number everywhere and named the fact as the lot's
open question. On 2026-10-04 that question sat on 13,748 Milwaukie answers
and 4,186 in Wilsonville. Both cities publish the map (``street_class_*`` in
``flats/config/pipeline.yaml``).

A city's Transportation System Plan classifies its streets, and some cities
publish that map. This module reads one, per lot, and answers the fact.

**Which street a lot line is on.** The same reading as the corridor maps
(:mod:`flats.geom.corridor`): at points along each street lot line, the
street the line abuts is the nearest parallel RLIS centreline within
:data:`~flats.geom.corridor.FRONT_REACH_FT`, and that street's class is the
class of the TSP line abreast of the point that coincides with it (within
:data:`~flats.geom.corridor.COINCIDE_FT`) or carries its name. A point with
no centreline beside it, or with no TSP line on its street, or with TSP
lines that disagree, is unread.

**Local is the permissive answer, so it needs two sources.** A TSP map can
be newer than the plan in force -- Milwaukie's carries the 2023-25 update
the planning commission recommended on 2026-01-28 -- and a street the new
plan moves from collector to local would pass a lot against the local
number the code does not yet give it. So a point is local only where the
TSP map says local AND Metro's own street file types the street a minor
residential street (RLIS TYPE :data:`RLIS_LOCAL`). A point the TSP map
calls a collector or an arterial is not local, whatever RLIS says: that is
the stricter answer and the base every encoding already uses.

**Every street line, answered per lot.** The rules are about the street a
lot line, a driveway or a front yard is on, and the registry holds one
lot-level fact. True only when every point on every street line is local;
False only when every point is a collector or an arterial; otherwise --
a corner of a local and a collector street, a line nobody could place --
the fact is left unasked and the stricter number stays with its question.

**Only where the map is.** A lot of a layer no map serves is left unasked:
Hillsboro uses the fact for two different street lists ("local or
Collector" for density, "arterial and collector" for use), and no reading
of one map answers both.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from flats.geom.corridor import (
    COINCIDE_FT,
    CORRIDOR_REACH_FT,
    FRONT_REACH_FT,
    SAMPLES,
    STREET_CLASS,
    STREETS_KEY,
    Lines,
    _abreast,
    _dataset_path,
    _fronted,
)
from flats.geom.edges import bearing_deg

#: The fact this module answers.
LOCAL_STREET = "local_street"

#: RLIS TYPE codes Metro gives a minor residential street: 1500, and the
#: two unclassified Clackamas variants (named and unnamed, no addresses).
RLIS_LOCAL: frozenset[int] = frozenset({1500, 1550, 1560})


@dataclass(frozen=True)
class ClassSpec:
    """How one city's TSP map spells its classes.

    ``local`` and ``other`` are the field's values verbatim; anything else
    (a proposed street, a blank, a class the code's wording does not settle)
    reads as unknown.
    """

    field: str
    local: frozenset[str]
    other: frozenset[str]


#: Registry dataset -> how its classes read.
CLASS_MAPS: dict[str, ClassSpec] = {
    # MMC 12.16.040.E.3: "local or neighborhood streets" against "collector
    # or arterial streets". Neighborhood Routes is not taken as local: the
    # code says "neighborhood streets", the TSP class is a route, and the
    # wider apron is the safe side of that doubt.
    "street_class_milwaukie": ClassSpec(
        field="RoadwayClassification",
        local=frozenset({"Local Street"}),
        other=frozenset(
            {
                "Collector",
                "Arterial",
                "Local Access Arterial",
                "Multimodal Travel Priority Arterial",
                "Through Movement Priority Arterial",
            }
        ),
    ),
    # Villebois Table V-1 note 6: "on Collector Avenues" the front yard is
    # 20 and the street side 15. An arterial is not a local street either.
    "street_class_wilsonville": ClassSpec(
        field="Functional_Class",
        local=frozenset({"Local Street"}),
        other=frozenset({"Collector", "Minor Arterial", "Major Arterial"}),
    ),
}


@dataclass(frozen=True)
class ClassMap:
    """One city's TSP map: where it serves, its lines and their classes
    (``"local"``, ``"other"`` or ``""``), and the RLIS streets beside them
    with their TYPE."""

    serves: tuple[str, ...]
    lines: Lines
    kinds: tuple[str, ...]
    streets: Lines
    types: tuple[int | None, ...]

    def covers(self, layer_id: str | None) -> bool:
        return bool(layer_id) and any(layer_id == s or layer_id.startswith(f"{s}/") for s in self.serves)


def class_kind(value: object, spec: ClassSpec) -> str:
    """``"local"``, ``"other"`` or ``""`` for one TSP class value."""
    text = str(value or "").strip()
    if text in spec.local:
        return "local"
    if text in spec.other:
        return "other"
    return ""


def _street_label(props: dict[str, Any]) -> str:
    return " ".join(str(props.get(k) or "") for k in ("PREFIX", "STREETNAME", "FTYPE"))


def _type_of(props: dict[str, Any]) -> int | None:
    try:
        return int(props.get("TYPE"))
    except (TypeError, ValueError):
        return None


def build(
    serves: Iterable[str],
    lines: Sequence[Any],
    kinds: Sequence[str],
    names: Sequence[object],
    streets: Sequence[Any],
    street_names: Sequence[object],
    types: Sequence[int | None],
) -> ClassMap:
    """A class map from its parts (what :func:`load_class_maps` reads, and
    what a test draws)."""
    keep = [i for i, g in enumerate(lines) if g is not None and not g.is_empty]
    held = Lines.build([lines[i] for i in keep], [names[i] for i in keep])
    road = [i for i, g in enumerate(streets) if g is not None and not g.is_empty]
    return ClassMap(
        serves=tuple(serves),
        lines=held,
        kinds=tuple(kinds[i] for i in keep),
        streets=Lines.build([streets[i] for i in road], [street_names[i] for i in road]),
        types=tuple(types[i] for i in road),
    )


def load_class_maps(sources: Path, pipeline: Any | None = None) -> tuple[ClassMap, ...]:
    """Every TSP class map the snapshot at ``sources`` holds, per the registry.

    A dataset missing from the snapshot is skipped and its cities' lots stay
    unasked. The snapshot's RLIS streets near each map are loaded with it.
    """
    from shapely.geometry import shape
    from shapely.ops import unary_union

    from flats.ingest.delta import iter_features
    from flats.ingest.sources import load_pipeline

    pipeline = pipeline or load_pipeline()
    manifest_path = sources / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    roads_path = _dataset_path(sources, manifest, STREETS_KEY)
    if not roads_path.is_file():
        return ()
    out: list[ClassMap] = []
    for key, spec in CLASS_MAPS.items():
        ds = pipeline.datasets.get(key)
        path = _dataset_path(sources, manifest, key)
        if ds is None or not path.is_file():
            continue
        feats = [f for f in iter_features(path) if f.get("geometry")]
        geoms = [shape(f["geometry"]) for f in feats]
        props = [f.get("properties") or {} for f in feats]
        if not geoms:
            continue
        zone = unary_union(geoms).buffer(CORRIDOR_REACH_FT + FRONT_REACH_FT)
        roads, labels, types = [], [], []
        for f in iter_features(roads_path):
            if not f.get("geometry"):
                continue
            g = shape(f["geometry"])
            if not g.intersects(zone):
                continue
            p = f.get("properties") or {}
            roads.append(g)
            labels.append(_street_label(p))
            types.append(_type_of(p))
        out.append(
            build(
                ds.serves,
                geoms,
                [class_kind(p.get(spec.field), spec) for p in props],
                [_street_label(p) for p in props],
                roads,
                labels,
                types,
            )
        )
    return tuple(out)


def _kind_at(point: Any, own: float, cmap: ClassMap) -> str:
    """The class of the street a lot line abuts at ``point``: ``"local"``,
    ``"other"`` or ``""`` (unread)."""
    s = _fronted(point, own, cmap.streets)
    if s is None:
        return ""
    street, name = cmap.streets.lines[s], cmap.streets.names[s]
    foot = street.interpolate(street.project(point))
    found: set[str] = set()
    for i in cmap.lines.near(point, CORRIDOR_REACH_FT):
        line = cmap.lines.lines[i]
        if not _abreast(line, point, own, CORRIDOR_REACH_FT):
            continue
        if (name and name == cmap.lines.names[i]) or line.distance(foot) <= COINCIDE_FT:
            found.add(cmap.kinds[i])
    if len(found) != 1:
        return ""
    (kind,) = found
    if kind == "local" and cmap.types[s] not in RLIS_LOCAL:
        return ""
    return kind


def edge_class(edge: Sequence[float], cmap: ClassMap) -> str:
    """One street lot line ``(x1, y1, x2, y2)``: ``"local"`` when every
    sample point is, ``"other"`` when every one is, else ``""``."""
    from shapely.geometry import LineString, Point

    x1, y1, x2, y2 = (float(v) for v in edge[:4])
    if LineString([(x1, y1), (x2, y2)]).length <= 0:
        return ""
    own = bearing_deg(x1, y1, x2, y2)
    kinds = {
        _kind_at(Point(x1 + (x2 - x1) * k / (SAMPLES + 1), y1 + (y2 - y1) * k / (SAMPLES + 1)), own, cmap)
        for k in range(1, SAMPLES + 1)
    }
    return kinds.pop() if len(kinds) == 1 else ""


def observed_local_street(
    edges: Iterable[Sequence[object]], layer_id: str | None, maps: Sequence[ClassMap]
) -> dict[str, bool]:
    """The ``local_street`` fact for one lot, as ``configure`` takes it.

    ``edges`` is s4's ``edges_json`` decoded (``[x1, y1, x2, y2, cls]``).
    Present only where a map serves the lot's layer and the lot has street
    lines: True when every street line is local, False when every one is a
    collector or an arterial, absent otherwise.
    """
    street = [e for e in edges if len(e) >= 5 and e[4] == STREET_CLASS]
    serving = [m for m in maps if m.covers(layer_id)]
    if not street or not serving:
        return {}
    kinds = {edge_class(e, m) for e in street for m in serving}  # type: ignore[arg-type]
    if kinds == {"local"}:
        return {LOCAL_STREET: True}
    if kinds == {"other"}:
        return {LOCAL_STREET: False}
    return {}


__all__ = [
    "CLASS_MAPS",
    "LOCAL_STREET",
    "RLIS_LOCAL",
    "ClassMap",
    "ClassSpec",
    "build",
    "class_kind",
    "edge_class",
    "load_class_maps",
    "observed_local_street",
]
