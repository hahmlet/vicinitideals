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
street, so a street lot line is adjacent to a corridor when the street it
abuts IS the corridor. Asked at points along the line: the street it abuts
is the nearest parallel RLIS centreline within :data:`FRONT_REACH_FT`; that
street is the corridor when a corridor line runs abreast of the point
within :data:`CORRIDOR_REACH_FT` and either carries the same street name or
runs within :data:`COINCIDE_FT` of that centreline. Most of the line's
points have to agree (:data:`MIN_SHARE`). The parallel test keeps the
side-street line of a corner lot from counting.

A fixed distance from the corridor's drawn line does not work, and the
first cut used one: a lot line on SE Division sits 25-55 ft from the drawn
line, one on SW Barbur -- a divided highway -- up to 100 ft, and the lots
one block back start not much further out. The bound on Portland's
commercial and RM2 lots (2026-09-27) found 49 street lines on the five
setback stretches between 50 and 60 ft that a 50 ft reach called off the
corridor, each a false GREEN on the 10 ft setback. Asking which street the
line abuts is what separates the wide street from the next block: the next
block's line abuts its own street first. Without a street network (a
snapshot with no ``rlis_streets``), or where no centreline runs beside the
line, the test falls back to the drawn line within :data:`REACH_FT`.

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
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from flats.geom.edges import PARALLEL_TOL_DEG, bearing_deg, bearing_delta

#: s4's class letter for a street edge.
STREET_CLASS = "F"

#: The fallback with no street network: a street lot line within this of
#: the corridor's drawn line is on it -- quadfit's ``street_threshold_ft``.
REACH_FT = 50.0

#: How far out from a street lot line to look for the street it abuts --
#: s4's own reach for calling a lot line a street line (50 ft to a
#: centreline), with slack for asking at points along the line rather than
#: of the whole line. The first cut looked 120 ft out and found Division and
#: Belmont 105-118 ft beyond lot lines that abut no street there at all.
FRONT_REACH_FT = 60.0

#: How far a corridor's drawn line may sit from the lot line and still be
#: the street the line abuts, once the street is named. Wide enough for
#: Barbur's divided lanes; the name or the coincidence test does the rest.
CORRIDOR_REACH_FT = 150.0

#: A street centreline within this of the corridor's drawn line is the
#: corridor, whatever it is called (ramps, couplets, a renamed segment).
COINCIDE_FT = 30.0

#: The share of a street lot line's sample points that have to agree.
#: Half: a line the corridor's drawn end stops part way along still fronts it.
MIN_SHARE = 0.5

#: Points sampled along each street lot line, ends excluded.
SAMPLES = 9

#: Registry dataset -> the condition its lines answer.
CORRIDOR_MAPS: dict[str, str] = {
    "corridor_setbacks_pdx": "civic_corridor_setback",
    "corridors_pdx": "civic_corridor",
}

#: The street network the lot lines are read against.
STREETS_KEY = "rlis_streets"

#: Only streets this near a corridor are kept in memory.
_STREET_KEEP_FT = CORRIDOR_REACH_FT + FRONT_REACH_FT

#: The facts, in the order they are reported.
CORRIDOR_FACTS: tuple[str, ...] = tuple(sorted(set(CORRIDOR_MAPS.values())))

_WORDS = {"AVENUE": "AVE", "STREET": "ST", "BOULEVARD": "BLVD", "ROAD": "RD", "DRIVE": "DR"}


def street_name(name: object) -> str:
    """A street name spelled one way: upper case, the map's " - CIVIC CORRIDOR"
    tag dropped, long street types shortened. ``""`` for no name."""
    text = str(name or "").upper()
    text = re.split(r"\s*-\s*CIVIC CORRIDOR", text)[0]
    return " ".join(_WORDS.get(w, w) for w in text.split())


@dataclass(frozen=True)
class Lines:
    """Named polylines and their index."""

    lines: tuple[Any, ...]
    names: tuple[str, ...]
    tree: Any

    @classmethod
    def build(cls, lines: Iterable[Any], names: Iterable[object] | None = None) -> Lines:
        from shapely.strtree import STRtree

        geoms = list(lines)
        labels = list(names) if names is not None else [""] * len(geoms)
        kept = [(g, street_name(n)) for g, n in zip(geoms, labels) if g is not None and not g.is_empty]
        return cls(tuple(g for g, _ in kept), tuple(n for _, n in kept), STRtree([g for g, _ in kept]))

    def near(self, geom: Any, distance: float) -> list[int]:
        return [int(i) for i in self.tree.query(geom, predicate="dwithin", distance=distance)]


@dataclass(frozen=True)
class CorridorMap:
    """One corridor map: the condition it answers, where, its lines, and the
    street network its lot lines are read against (``None``: the fallback)."""

    condition: str
    serves: tuple[str, ...]
    corridor: Lines
    streets: Lines | None = None

    def covers(self, layer_id: str | None) -> bool:
        return bool(layer_id) and any(layer_id == s or layer_id.startswith(f"{s}/") for s in self.serves)

    @classmethod
    def from_lines(
        cls,
        condition: str,
        serves: Iterable[str],
        lines: Iterable[Any],
        names: Iterable[object] | None = None,
        streets: Lines | None = None,
    ) -> CorridorMap:
        return cls(condition, tuple(serves), Lines.build(lines, names), streets)


def _dataset_path(sources: Path, manifest: dict[str, Any], key: str) -> Path:
    entry = (manifest.get("datasets") or {}).get(key) or {}
    return sources / str(entry.get("file") or f"{key}.geojson")


def _name_of(props: dict[str, Any]) -> str:
    """A corridor feature's street name (the two maps spell the field two ways)."""
    return str(props.get("StreetName") or props.get("STREETNAME") or "")


def load_maps(sources: Path, pipeline: Any | None = None) -> tuple[CorridorMap, ...]:
    """Every corridor map the snapshot at ``sources`` holds, per the registry.

    A dataset missing from the snapshot is skipped: its condition stays
    unasked, as it was before the map was acquired. The snapshot's RLIS
    streets near any corridor are loaded once and shared.
    """
    from shapely.geometry import shape
    from shapely.ops import unary_union

    from flats.ingest.delta import iter_features
    from flats.ingest.sources import load_pipeline

    pipeline = pipeline or load_pipeline()
    manifest_path = sources / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    found: list[tuple[str, tuple[str, ...], list[Any], list[str]]] = []
    for key, condition in CORRIDOR_MAPS.items():
        ds = pipeline.datasets.get(key)
        path = _dataset_path(sources, manifest, key)
        if ds is None or not path.is_file():
            continue
        feats = [f for f in iter_features(path) if f.get("geometry")]
        geoms = [shape(f["geometry"]) for f in feats]
        names = [_name_of(f.get("properties") or {}) for f in feats]
        found.append((condition, tuple(ds.serves), geoms, names))
    if not found:
        return ()
    streets: Lines | None = None
    path = _dataset_path(sources, manifest, STREETS_KEY)
    if path.is_file():
        zone = unary_union([g for _, _, geoms, _ in found for g in geoms]).buffer(_STREET_KEEP_FT)
        kept: list[Any] = []
        labels: list[str] = []
        for f in iter_features(path):
            if not f.get("geometry"):
                continue
            g = shape(f["geometry"])
            if not g.intersects(zone):
                continue
            p = f.get("properties") or {}
            kept.append(g)
            labels.append(" ".join(str(p.get(k) or "") for k in ("PREFIX", "STREETNAME", "FTYPE")))
        streets = Lines.build(kept, labels)
    return tuple(
        CorridorMap.from_lines(c, serves, geoms, names, streets) for c, serves, geoms, names in found
    )


def _along(line: Any, point: Any) -> float:
    """A line's bearing where it passes nearest ``point``."""
    d = line.project(point)
    a = line.interpolate(max(0.0, d - 5.0))
    b = line.interpolate(min(line.length, d + 5.0))
    if a.equals(b):
        return 0.0
    return bearing_deg(a.x, a.y, b.x, b.y)


def _abreast(line: Any, point: Any, own: float, reach: float) -> bool:
    """Whether ``point`` sits beside ``line``, within ``reach`` and parallel.

    The nearest point has to be strictly inside the line rather than at a
    drawn end -- a point past the end is not beside it -- and the line's
    bearing there within :data:`PARALLEL_TOL_DEG` of ``own``.
    """
    d = line.project(point)
    if d <= 0.0 or d >= line.length:
        return False
    return line.distance(point) <= reach and bearing_delta(own, _along(line, point)) <= PARALLEL_TOL_DEG


def _fronted(point: Any, own: float, streets: Lines) -> int | None:
    """The street a lot line abuts at ``point``: the nearest parallel centreline."""
    best: tuple[float, int] | None = None
    for i in streets.near(point, FRONT_REACH_FT):
        line = streets.lines[i]
        if _abreast(line, point, own, FRONT_REACH_FT):
            d = line.distance(point)
            if best is None or d < best[0]:
                best = (d, i)
    return None if best is None else best[1]


def _on_at(point: Any, own: float, cmap: CorridorMap, near: list[int]) -> bool:
    """Whether the street a lot line abuts at ``point`` is the corridor."""
    corridor = cmap.corridor
    if cmap.streets is None:
        return any(_abreast(corridor.lines[i], point, own, REACH_FT) for i in near)
    s = _fronted(point, own, cmap.streets)
    if s is None:
        # No centreline beside the line here (a curve, a gap in the network,
        # a transit-centre loop): the drawn line decides, as with no network.
        return any(_abreast(corridor.lines[i], point, own, REACH_FT) for i in near)
    street, name = cmap.streets.lines[s], cmap.streets.names[s]
    foot = street.interpolate(street.project(point))
    for i in near:
        line = corridor.lines[i]
        if not _abreast(line, point, own, CORRIDOR_REACH_FT):
            continue
        if (name and name == corridor.names[i]) or line.distance(foot) <= COINCIDE_FT:
            return True
    return False


def on_corridor(edge: Sequence[float], cmap: CorridorMap) -> bool:
    """Whether one street lot line ``(x1, y1, x2, y2)`` abuts a corridor.

    At least :data:`MIN_SHARE` of the line's sample points have to agree. A
    sample may agree with a different corridor line than its neighbour: a
    corridor is drawn as many segments, and a lot line can span the join.
    """
    from shapely.geometry import LineString, Point

    x1, y1, x2, y2 = (float(v) for v in edge[:4])
    seg = LineString([(x1, y1), (x2, y2)])
    if seg.length <= 0:
        return False
    reach = REACH_FT if cmap.streets is None else CORRIDOR_REACH_FT
    near = cmap.corridor.near(seg, reach)
    if not near:
        return False
    own = bearing_deg(x1, y1, x2, y2)
    hits = 0
    for k in range(1, SAMPLES + 1):
        p = Point(x1 + (x2 - x1) * k / (SAMPLES + 1), y1 + (y2 - y1) * k / (SAMPLES + 1))
        if _on_at(p, own, cmap, near):
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

