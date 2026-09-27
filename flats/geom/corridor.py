"""Which lots have a street lot line on a mapped corridor.

Portland sets two standards off a line on a map rather than anything in the
parcel record, and the two are different maps:

* **Map 130-1, Civic Corridors with Required Setbacks** -- 33.130.215.B.1.a:
  "The minimum setback required from a street lot line adjacent to a Civic
  Corridor shown on Map 130-1 is 10 feet." Everywhere else in the commercial
  zones there is no minimum. The city publishes the map as "Civic Corridor
  Setbacks" (BPS zoning code layers, Ordinance 188177): five stretches --
  SW Barbur, SE Division, SE and NE 122nd, SE Stark. Condition
  ``civic_corridor_setback``.
* **Map 120-1 (and 130-3), Civic and Neighborhood Corridors** --
  33.120.225.B: RM2 coverage is 70 percent "on sites that abut a Civic
  Corridor or Neighborhood Corridor shown on Map 120-1", 60 elsewhere. The
  city publishes it as "Civic and Neighborhood Corridors (BPS)", 158 street
  segments. Condition ``civic_corridor``.

**What "adjacent" is.** 33.910 does not define it; it defines a street lot
line ("a lot line, or segment of a lot line, that abuts a street ... can
include front lot lines and side lot lines"). The corridor maps draw the
street, so a street lot line is adjacent to a corridor when it runs along the
corridor's line across the right-of-way: most of the line within
:data:`REACH_FT` of the corridor (the same reach quadfit's s4 uses to call a
lot line a street line at all) and parallel to it within
:data:`PARALLEL_TOL_DEG`. The parallel test is what keeps the side-street
line of a corner lot, which also touches the corridor's line at the corner,
from counting.

**Per line, answered per lot.** Both rules are about one street lot line,
and the rule layer holds a lot-level fact. The lot answers True when ANY of
its street lines is on the corridor. For the setback that is the tighter
side -- 10 ft on every street line of a lot whose one line is on Division --
so an approximation can only cost a lot, never pass one. For RM2 coverage
the fact relaxes, and "a site that abuts" a corridor is exactly a site with
one line on it, so ANY is the rule's own reading.

**Only where the map is.** A condition is answered only on lots of the
layers the map serves (the registry's ``serves``); Gresham's
``civic_corridor`` is Gresham's own corridors, which no map here holds, and
answering it from Portland's map would lift Gresham's caps on nothing. A lot
with no traced edges (quadfit tier ``D``) is left unasked as well.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from flats.geom.edges import PARALLEL_TOL_DEG, bearing_deg, bearing_delta

#: s4's class letter for a street edge.
STREET_CLASS = "F"

#: How far a street lot line may sit from the corridor's drawn line and still
#: be on it -- quadfit's ``street_threshold_ft`` (rules.yaml ``defaults``),
#: the reach within which s4 calls a lot line a street line at all.
REACH_FT = 50.0

#: The share of a street lot line's samples that have to be within reach.
#: Half: a line the corridor's drawn end stops part way along still fronts it.
MIN_SHARE = 0.5

#: Points sampled along each street lot line, ends excluded.
SAMPLES = 9

#: Registry dataset -> the condition its lines answer.
CORRIDOR_MAPS: dict[str, str] = {
    "corridor_setbacks_pdx": "civic_corridor_setback",
    "corridors_pdx": "civic_corridor",
}

#: The facts, in the order they are reported.
CORRIDOR_FACTS: tuple[str, ...] = tuple(sorted(set(CORRIDOR_MAPS.values())))


@dataclass(frozen=True)
class CorridorMap:
    """One corridor map: the condition it answers, where, and its lines."""

    condition: str
    serves: tuple[str, ...]
    lines: tuple[Any, ...]
    tree: Any

    def covers(self, layer_id: str | None) -> bool:
        return bool(layer_id) and any(layer_id == s or layer_id.startswith(f"{s}/") for s in self.serves)

    @classmethod
    def from_lines(cls, condition: str, serves: Iterable[str], lines: Iterable[Any]) -> CorridorMap:
        from shapely.strtree import STRtree

        kept = tuple(g for g in lines if g is not None and not g.is_empty)
        return cls(condition, tuple(serves), kept, STRtree(list(kept)))


def load_maps(sources: Path, pipeline: Any | None = None) -> tuple[CorridorMap, ...]:
    """Every corridor map the snapshot at ``sources`` holds, per the registry.

    A dataset missing from the snapshot is skipped: its condition stays
    unasked, as it was before the map was acquired.
    """
    from shapely.geometry import shape

    from flats.ingest.delta import iter_features
    from flats.ingest.sources import load_pipeline

    pipeline = pipeline or load_pipeline()
    manifest_path = sources / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    out: list[CorridorMap] = []
    for key, condition in CORRIDOR_MAPS.items():
        ds = pipeline.datasets.get(key)
        if ds is None:
            continue
        entry = (manifest.get("datasets") or {}).get(key) or {}
        path = sources / str(entry.get("file") or f"{key}.geojson")
        if not path.is_file():
            continue
        lines = [shape(f["geometry"]) for f in iter_features(path) if f.get("geometry")]
        out.append(CorridorMap.from_lines(condition, ds.serves, lines))
    return tuple(out)


def _along(line: Any, point: Any) -> float:
    """The corridor's bearing where it passes nearest ``point``."""
    d = line.project(point)
    a = line.interpolate(max(0.0, d - 5.0))
    b = line.interpolate(min(line.length, d + 5.0))
    if a.equals(b):
        return 0.0
    return bearing_deg(a.x, a.y, b.x, b.y)


def _abreast(line: Any, point: Any, own: float) -> bool:
    """Whether ``point`` sits across the street from ``line`` and parallel to it.

    Within :data:`REACH_FT`, with its nearest point strictly inside the line
    rather than at a drawn end -- a point past the end is not beside it --
    and the line's bearing there within :data:`PARALLEL_TOL_DEG` of ``own``.
    """
    d = line.project(point)
    if d <= 0.0 or d >= line.length:
        return False
    return line.distance(point) <= REACH_FT and bearing_delta(own, _along(line, point)) <= PARALLEL_TOL_DEG


def on_corridor(edge: Sequence[float], cmap: CorridorMap) -> bool:
    """Whether one street lot line ``(x1, y1, x2, y2)`` runs along a corridor.

    At least :data:`MIN_SHARE` of the line's sample points have to sit
    abreast of some corridor line. A sample may be abreast of a different
    line than its neighbour: a corridor is drawn as many segments, and a lot
    line can span the join.
    """
    from shapely.geometry import LineString, Point

    x1, y1, x2, y2 = (float(v) for v in edge[:4])
    seg = LineString([(x1, y1), (x2, y2)])
    if seg.length <= 0:
        return False
    near = [cmap.lines[int(i)] for i in cmap.tree.query(seg, predicate="dwithin", distance=REACH_FT)]
    if not near:
        return False
    own = bearing_deg(x1, y1, x2, y2)
    hits = 0
    for k in range(1, SAMPLES + 1):
        p = Point(x1 + (x2 - x1) * k / (SAMPLES + 1), y1 + (y2 - y1) * k / (SAMPLES + 1))
        if any(_abreast(line, p, own) for line in near):
            hits += 1
    return hits / SAMPLES >= MIN_SHARE


def observed_corridors(
    edges: Iterable[Sequence[object]], layer_id: str | None, maps: Sequence[CorridorMap]
) -> dict[str, bool]:
    """The corridor facts for one lot, as ``configure`` takes them.

    ``edges`` is s4's ``edges_json`` decoded (``[x1, y1, x2, y2, cls]``). A
    fact is present only for a map that serves the lot's layer, and only
    when the lot has edges: True when any street line is on the corridor,
    else False.
    """
    edges = [e for e in edges]
    if not edges:
        return {}
    street = [e for e in edges if len(e) >= 5 and e[4] == STREET_CLASS]
    out: dict[str, bool] = {}
    for cmap in maps:
        if not cmap.covers(layer_id):
            continue
        hit = any(on_corridor(e, cmap) for e in street)  # type: ignore[arg-type]
        out[cmap.condition] = out.get(cmap.condition, False) or hit
    return out

