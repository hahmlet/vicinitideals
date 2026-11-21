"""Whether a Gresham Downtown lot fronts a street where GDC 4.1121 requires
first-floor commercial uses.

GDC 4.1121(A): "In the following locations, a minimum of 75 percent of a
building's ground-floor floor area within 40 feet of the right-of-way shall
have Commercial uses or Civic uses that generate a significant number of
customer visits":

1. the north side of E Powell Boulevard, between NW Miller Avenue and NE
   Roberts Avenue;
2. N Main Avenue between E Powell Boulevard and NE 4th Street;
3. NE 3rd Street between N Main Avenue and NE Hood Avenue, and the north side
   of NE 3rd Street between NE Hood Avenue and NE Kelly Avenue
   (flats/provenance/docs/or/multnomah/gresham/4/4.1121.txt#L1-L6).

The code names the stretches in words, so the layer types the RLIS
centrelines by them: ``flats/config/areas/or/multnomah/gresham/
downtown-first-floor-uses.geojson`` holds every centreline of the traced
Downtown street-type map (:mod:`flats.geom.street_types`), each typed
``both`` (either side of the street), ``north`` (its north side only) or
``none``. A lot line reads the centreline it abuts as
:mod:`flats.geom.active_use` reads Hillsboro's: at
:data:`~flats.geom.corridor.SAMPLES` points, the nearest parallel centreline
within :data:`~flats.geom.corridor.FRONT_REACH_FT`.

**The answer, per lot of the Downtown zones** (:data:`CONDITION`):

* True where any sample point of any street line abuts a ``both`` stretch,
  or a ``north`` stretch from its north side -- the strict reading: the rule
  holds the lot from any of its frontage, since the pod's ground floor is all
  homes;
* else unanswered (out of GREEN) where a street line no traced centreline
  explains lies within :data:`CLEAR_FT` of a marked stretch;
* else False.

The pod is four homes, so the share asked is never met; whether any of the
building stands within 40 ft of that right-of-way is not measured. The rule
file holds a lot that answers True YELLOW (``ground_floor_commercial_min_pct``,
FOLLOWUPS 203), never GREEN.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from flats.geom.corridor import FRONT_REACH_FT, SAMPLES, STREET_CLASS, Lines, _fronted
from flats.geom.edges import bearing_deg
from flats.rules.loader import AREAS_ROOT

#: The fact this map answers.
CONDITION = "gresham_first_floor_uses_street"
#: The layer it serves and the zones it is asked of: the Downtown Plan
#: District's sub-districts (Map 4.1110), whose chapter 4.1121 is.
SERVES = "or/multnomah/gresham"
ZONES = frozenset({"DCC", "DTM", "DMU", "DEM", "DCL", "DRL-1", "DRL-2"})
#: The typed centrelines, under ``flats/config/areas``.
TRACED = "or/multnomah/gresham/downtown-first-floor-uses.geojson"

BOTH, NORTH, NONE = "both", "north", "none"
KINDS = frozenset({BOTH, NORTH, NONE})
MARKED = frozenset({BOTH, NORTH})

#: How far a street line no centreline explains may lie from every marked
#: stretch and still be read as not on one: twice the reach a lot line is
#: read at, as :data:`flats.geom.active_use.CLEAR_FT`.
CLEAR_FT = 2 * FRONT_REACH_FT


def _north_of(line: Any, point: Any) -> bool:
    """Whether ``point`` lies on the north side of the east-west ``line``:
    left of it, walked eastward."""
    at = line.project(point)
    a = line.interpolate(max(at - 1.0, 0.0))
    b = line.interpolate(min(at + 1.0, line.length))
    dx, dy = b.x - a.x, b.y - a.y
    if dx < 0:
        dx, dy = -dx, -dy
    q = line.interpolate(at)
    return dx * (point.y - q.y) - dy * (point.x - q.x) > 0


@dataclass(frozen=True)
class FirstFloorUses:
    """The typed centrelines."""

    streets: Lines
    kinds: tuple[str, ...]
    #: The marked stretches alone, for the clearance test.
    marked: tuple[Any, ...]

    @classmethod
    def build(cls, lines: Iterable[Any], names: Iterable[str], kinds: Iterable[str]) -> FirstFloorUses:
        geoms, labels, types = list(lines), list(names), list(kinds)
        unknown = sorted(set(types) - KINDS)
        if unknown:
            raise ValueError(f"unknown first-floor kind(s): {unknown}")
        if not (len(geoms) == len(labels) == len(types)):
            raise ValueError("every line needs a name and a first-floor kind")
        streets = Lines.build(geoms, labels)
        kept = [(g, k) for g, k in zip(geoms, types) if g is not None and not g.is_empty]
        return cls(
            streets,
            tuple(k for _, k in kept),
            tuple(g for g, k in kept if k in MARKED),
        )

    def _points(self, edge: Sequence[object]) -> list[bool | None]:
        """Per sample point of one street line: True on a marked stretch
        (from the side it binds), False on any other traced centreline, None
        where no centreline explains it."""
        from shapely.geometry import Point

        x1, y1, x2, y2 = (float(v) for v in edge[:4])  # type: ignore[arg-type]
        if x1 == x2 and y1 == y2:
            return []
        own = bearing_deg(x1, y1, x2, y2)
        out: list[bool | None] = []
        for k in range(1, SAMPLES + 1):
            p = Point(x1 + (x2 - x1) * k / (SAMPLES + 1), y1 + (y2 - y1) * k / (SAMPLES + 1))
            s = _fronted(p, own, self.streets)
            if s is None:
                out.append(None)
                continue
            kind = self.kinds[s]
            out.append(kind == BOTH or (kind == NORTH and _north_of(self.streets.lines[s], p)))
        return out

    def answer(self, edges: Sequence[Sequence[object]]) -> bool | None:
        """:data:`CONDITION` for one lot's s4 edges (see the module
        docstring); None where it cannot say."""
        street = [e for e in edges if len(e) >= 5 and e[4] == STREET_CLASS]
        if not street:
            return None
        read = [self._points(e) for e in street]
        if any(pt is True for pts in read for pt in pts):
            return True
        from shapely.geometry import LineString

        for e, pts in zip(street, read):
            if any(pt is not None for pt in pts):
                continue
            line = LineString([(float(e[0]), float(e[1])), (float(e[2]), float(e[3]))])  # type: ignore[arg-type]
            if not self.clear_of(line):
                return None
        return False

    def clear_of(self, geom: Any) -> bool:
        """Whether ``geom`` lies beyond :data:`CLEAR_FT` of every marked stretch."""
        return all(geom.distance(g) > CLEAR_FT for g in self.marked)


@lru_cache(maxsize=None)
def load_first_floor_uses(file: str = TRACED) -> FirstFloorUses:
    """The typed centrelines in ``file`` (under ``flats/config/areas``)."""
    from shapely.geometry import shape

    data = json.loads((AREAS_ROOT / file).read_text(encoding="utf-8"))
    feats = [f for f in data["features"] if f.get("geometry")]
    return FirstFloorUses.build(
        (shape(f["geometry"]) for f in feats),
        (str(f["properties"].get("name") or "") for f in feats),
        (str(f["properties"]["first_floor"]) for f in feats),
    )


def observed_first_floor_uses(
    edges: Sequence[Sequence[object]], layer_id: str | None, zone: object
) -> dict[str, bool]:
    """``{CONDITION: answer}`` for a lot of :data:`ZONES` on Gresham's layer
    with edges, where the typed centrelines answer it; ``{}`` otherwise."""
    if layer_id != SERVES or zone is None or str(zone) not in ZONES or not edges:
        return {}
    got = load_first_floor_uses().answer(edges)
    return {} if got is None else {CONDITION: got}
