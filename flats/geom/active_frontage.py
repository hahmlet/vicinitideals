"""Whether a Beaverton Downtown lot fronts a street of the Active Frontage
Design Map.

Beaverton BDC 70.20.10.6.D.1 holds "building facades fronting on streets
identified in Figure 70.20.10.6.2" to the Active Ground Floor Design rules,
and exempts every other facade. A Type A frontage takes the Non-residential
design (D.2), whose S1.a asks a ground floor at least 16 ft floor to floor
(70.20.10.txt#L377-L378); a Type B frontage may take that or the
Residential design (D.3), whose S2.c asks at least 12 ft (#L415). Areas C
and D are named tax lots (D.4): Area C must assign a Type A frontage on the
site at development; Area D gets one only when the future extension of SW
Millikan Way is dedicated.

The city publishes the figure only as a picture (BDC Chapter 70, PDF page
612, printed DD-77), so the layer traces it:
``flats/config/areas/or/washington/beaverton/active-frontage-design.geojson``
holds every RLIS centreline near a mapped frontage, cut into runs typed
``a`` (Type A), ``b`` (Type B), ``doubt`` (the figure draws something
beside it too faint to type) or ``none``, plus three lines the figure draws
where RLIS carries no street (``drawn_only``; the file's ``source`` says
how). A lot line takes the type of the centreline run it abuts, read as
:mod:`flats.geom.active_use` reads Hillsboro's: at
:data:`~flats.geom.corridor.SAMPLES` points, the nearest parallel centreline
within :data:`~flats.geom.corridor.FRONT_REACH_FT`.

**The answers, per Beaverton lot** (:data:`ON_MAP`, :data:`TYPE_A`):

* both False -- every street line is clear: no point of it beside a mapped,
  ``doubt`` or unexplained stretch, and no point within :data:`DOUBT_FT` of
  a mapped or ``doubt`` line; and the lot's outline lies beyond
  :data:`DOUBT_FT` of every one. A lot whose lines and outline lie beyond
  :data:`CLEAR_FT` of every marked line is clear without being read.
* ``ON_MAP`` True -- every street line is on a mapped street (at least
  :data:`~flats.geom.corridor.MIN_SHARE` of its points beside an ``a`` or
  ``b`` run); ``TYPE_A`` True with it when any of those lines is Type A.
  The pod's ground floor misses both 12 and 16, so this lot fails.
* neither -- out of GREEN -- otherwise: a mapped street and an unmapped
  one, a line part way along a mapped stretch or near a traced end, a
  ``doubt`` run, a street line no centreline explains near a mapped line,
  a lot with no street lines near one, or an Area D tax lot.

An Area C tax lot is answered ``ON_MAP`` and ``TYPE_A`` True (D.4.a).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from flats.geom.corridor import FRONT_REACH_FT, MIN_SHARE, SAMPLES, STREET_CLASS, Lines, _fronted
from flats.geom.edges import bearing_deg
from flats.rules.loader import AREAS_ROOT

#: The facts this map answers.
ON_MAP = "beaverton_active_frontage"
TYPE_A = "beaverton_type_a_frontage"
FACTS = (ON_MAP, TYPE_A)
#: The layer it serves.
SERVES = "or/washington/beaverton"
#: The traced figure, under ``flats/config/areas``.
TRACED = "or/washington/beaverton/active-frontage-design.geojson"

A, B, DOUBT, NONE = "a", "b", "doubt", "none"
TYPES = frozenset({A, B, DOUBT, NONE})
MAPPED = frozenset({A, B})
#: The kinds a lot must stand clear of to be answered off the map.
MARKED = frozenset({A, B, DOUBT})

#: How near a traced mapped (or ``doubt``) line a lot line or outline may
#: come and still be read as off the map: the trace's own uncertainty. The
#: figure was registered to RLIS at about 4.9 ft a pixel; a road there is 5
#: to 12 pixels wide, so the registration may sit up to half a road (about
#: 30 ft) off, and a typed run starts or stops within one 20 ft cut of where
#: the drawn line does. A lot within this of a mapped line's end, or across
#: from it, is held.
DOUBT_FT = 60.0
#: How far a lot must lie from every marked line to be answered off the map
#: without reading its lines: twice the reach a lot line is read at.
CLEAR_FT = 2 * FRONT_REACH_FT

#: 70.20.10.6.D.4.a, the Area C tax lots: a Type A frontage is assigned at
#: development (70.20.10.txt#L493-L494).
AREA_C = frozenset({"1S110CC00400", "1S110CC01300", "1S110CC01303"})
#: 70.20.10.6.D.4.b, the Area D tax lots: Type A on the future SW Millikan
#: Way extension once dedicated (70.20.10.txt#L495-L496), a street not yet
#: drawn, so these are held.
AREA_D = frozenset(
    {"1S110CD00900", "1S110CD01300", "1S110CD00790", "1S110CD01301", "1S115BB00203", "1S115BB00200"}
)

OFF = {ON_MAP: False, TYPE_A: False}


@dataclass(frozen=True)
class ActiveFrontage:
    """The traced centreline runs, the type of each, and the marked lines."""

    streets: Lines
    types: tuple[str, ...]
    #: Every ``a``/``b`` line, the drawn-only ones too.
    mapped: tuple[Any, ...]
    #: Every ``a``/``b``/``doubt`` line, the drawn-only ones too.
    marked: tuple[Any, ...]

    @classmethod
    def build(
        cls,
        lines: Iterable[Any],
        names: Iterable[str],
        types: Iterable[str],
        drawn_only: Iterable[bool] | None = None,
    ) -> ActiveFrontage:
        from shapely.ops import unary_union

        geoms, labels, kinds = list(lines), list(names), list(types)
        only = list(drawn_only) if drawn_only is not None else [False] * len(geoms)
        unknown = sorted(set(kinds) - TYPES)
        if unknown:
            raise ValueError(f"unknown frontage type(s): {unknown}")
        if not (len(geoms) == len(labels) == len(kinds) == len(only)):
            raise ValueError("every traced line needs a name and a frontage type")
        bad = sorted({k for k, o in zip(kinds, only) if o and k not in MAPPED})
        if bad:
            raise ValueError(f"a drawn-only line must be Type A or B, not {bad}")
        kept = [
            (g, n, k, o) for g, n, k, o in zip(geoms, labels, kinds, only) if g is not None and not g.is_empty
        ]
        on_street = [(g, n, k) for g, n, k, o in kept if not o]
        streets = Lines.build([g for g, _, _ in on_street], [n for _, n, _ in on_street])
        mapped = tuple(g for g, _, k, _ in kept if k in MAPPED)
        marked = tuple(g for g, _, k, _ in kept if k in MARKED)
        # The unions answer the distance questions in one call each.
        return cls(
            streets,
            tuple(k for _, _, k in on_street),
            (unary_union(mapped),) if mapped else (),
            (unary_union(marked),) if marked else (),
        )

    def _near_marked(self, geom: Any, distance: float) -> bool:
        return any(geom.distance(g) <= distance for g in self.marked)

    def _points(self, edge: Sequence[object]) -> list[str | None]:
        """What each sample point of one street line abuts: the run's type,
        ``doubt`` for a ``none`` run within :data:`DOUBT_FT` of a marked
        line, None where no centreline runs beside it."""
        from shapely.geometry import Point

        x1, y1, x2, y2 = (float(v) for v in edge[:4])  # type: ignore[arg-type]
        if x1 == x2 and y1 == y2:
            return []
        own = bearing_deg(x1, y1, x2, y2)
        out: list[str | None] = []
        for k in range(1, SAMPLES + 1):
            p = Point(x1 + (x2 - x1) * k / (SAMPLES + 1), y1 + (y2 - y1) * k / (SAMPLES + 1))
            s = _fronted(p, own, self.streets)
            kind = None if s is None else self.types[s]
            if kind == NONE and self._near_marked(p, DOUBT_FT):
                kind = DOUBT
            out.append(kind)
        return out

    def line_kind(self, edge: Sequence[object]) -> str:
        """One street line read whole: ``a`` or ``b`` when at least
        :data:`MIN_SHARE` of its points abut that mapped type (``a`` when
        Type A has the share or more of the mapped points), ``none`` when
        every point abuts a clear ``none`` run, ``doubt`` otherwise."""
        from shapely.geometry import LineString

        line = LineString([(float(edge[0]), float(edge[1])), (float(edge[2]), float(edge[3]))])  # type: ignore[arg-type]
        if not self._near_marked(line, CLEAR_FT):
            return NONE
        pts = self._points(edge)
        if not pts:
            return DOUBT
        on = [k for k in pts if k in MAPPED]
        if len(on) / SAMPLES >= MIN_SHARE:
            return A if on.count(A) / len(on) >= MIN_SHARE else B
        if all(k == NONE for k in pts) and not self._near_marked(line, DOUBT_FT):
            return NONE
        return DOUBT

    def facts(self, edges: Sequence[Sequence[object]], outline: Any = None) -> dict[str, bool]:
        """The answers for one lot's s4 edges and outline (see the module
        docstring); ``{}`` where unanswered."""
        street = [e for e in edges if len(e) >= 5 and e[4] == STREET_CLASS]
        if not street:
            if outline is not None and not self._near_marked(outline, CLEAR_FT):
                return dict(OFF)
            return {}
        kinds = [self.line_kind(e) for e in street]
        if all(k in MAPPED for k in kinds):
            return {ON_MAP: True, TYPE_A: A in kinds}
        if all(k == NONE for k in kinds):
            if outline is not None and self._near_marked(outline, DOUBT_FT):
                return {}
            return dict(OFF)
        return {}


@lru_cache(maxsize=None)
def load_active_frontage(file: str = TRACED) -> ActiveFrontage:
    """The traced figure in ``file`` (under ``flats/config/areas``)."""
    from shapely.geometry import shape

    data = json.loads((AREAS_ROOT / file).read_text(encoding="utf-8"))
    feats = [f for f in data["features"] if f.get("geometry")]
    return ActiveFrontage.build(
        (shape(f["geometry"]) for f in feats),
        (str(f["properties"].get("name") or "") for f in feats),
        (str(f["properties"]["frontage"]) for f in feats),
        (bool(f["properties"].get("drawn_only")) for f in feats),
    )


def observed_active_frontage(
    edges: Sequence[Sequence[object]] | None,
    layer_id: str | None,
    lot: object = None,
    tlid: object = None,
) -> dict[str, bool]:
    """The Active Frontage answers for a lot on Beaverton's layer (see the
    module docstring); ``{}`` off it or where the lot cannot be read."""
    if layer_id != SERVES:
        return {}
    key = "".join(str(tlid or "").split()).upper()
    if key in AREA_C:
        return {ON_MAP: True, TYPE_A: True}
    if key in AREA_D:
        return {}
    traced = load_active_frontage()
    outline = _outline(lot)
    if edges:
        return traced.facts(edges, outline)
    if outline is not None and not traced._near_marked(outline, CLEAR_FT):
        return dict(OFF)
    return {}


def _outline(lot: object) -> Any:
    """The lot's polygon from WKB bytes (or a shapely geometry), else None."""
    if lot is None:
        return None
    if hasattr(lot, "distance"):
        return lot
    if isinstance(lot, (bytes, bytearray, memoryview)):
        from shapely import wkb

        try:
            return wkb.loads(bytes(lot))
        except Exception:  # noqa: BLE001 -- an unreadable outline answers nothing
            return None
    return None
