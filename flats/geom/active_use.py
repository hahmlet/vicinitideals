"""Whether a South Hillsboro lot has frontage on an Active Use Street.

Hillsboro CDC 12.65.850 holds "all development on lots with frontage on an
Active Use Street" (850.B) to a minimum property line coverage along that
frontage -- 75% on an Active Use 1 Street, 70% on an Active Use 2 Street
(Table 12.65.850-1) -- among other design standards. 12.65.030.B designates
the streets, and its Figure 12.65.930-A draws them, as an illustration of
their "street type and location" (030.B.2): the final street is set at the
PUD. Steph 2026-11-04 (rulings.yaml
``2026-11-04-south-hillsboro-active-use-streets-traced``): trace the
figure, and flag every lot on a traced street, a lot that passes staying
GREEN with the flag.

The city publishes the figure only as a picture (PDF page 889, printed
CDC12.65:65), so the layer traces it:
``flats/config/areas/or/washington/hillsboro/active-use-streets.geojson``
holds every RLIS centreline around the Town Center and Village Center Core
Areas, each typed ``au1``, ``au2`` or ``none`` as the figure draws it (the
file's ``source`` says how). A lot line takes the type of the centreline it
abuts, read as :mod:`flats.geom.street_types` reads Gresham's: at
:data:`~flats.geom.corridor.SAMPLES` points, the nearest parallel
centreline within :data:`~flats.geom.corridor.FRONT_REACH_FT`; a line is of
a type when at least :data:`~flats.geom.corridor.MIN_SHARE` of its points
agree on it.

**The answers, per Hillsboro lot with street lines:**

* :data:`TOUCHES` -- True where any point of any street line abuts a
  traced Active Use Street, else False. It carries only the
  illustrative-map flag, below the yellow line, so it is read the liberal
  way.
* :data:`ACTIVE_USE_1` / :data:`ACTIVE_USE_2` -- both False where the lot
  touches none; ``ACTIVE_USE_1`` True (and ``ACTIVE_USE_2`` False) where
  every street line is on an Active Use 1 Street, and the other way round
  for Active Use 2; both unanswered -- out of GREEN -- otherwise: a corner
  of an Active Use Street and an ordinary one, of two Active Use types, or a
  line only partly beside one. The coverage is owed on the Active Use
  frontage alone, and the rules hold one share for every street line, so
  the mixed lot is held rather than measured (coordinator 2026-11-04).

A street line no traced centreline explains, within :data:`CLEAR_FT` of
an Active Use line, may be on one: the lot is left unanswered. A lot with
no street lines is answered from its outline: False where it lies beyond
:data:`CLEAR_FT` of every traced Active Use line, unanswered otherwise.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from flats.geom.corridor import FRONT_REACH_FT, MIN_SHARE, SAMPLES, STREET_CLASS, Lines, _fronted
from flats.geom.edges import bearing_deg
from flats.rules.loader import AREAS_ROOT

#: The facts this map answers.
TOUCHES = "hillsboro_active_use_street"
ACTIVE_USE_1 = "hillsboro_active_use_1"
ACTIVE_USE_2 = "hillsboro_active_use_2"
FACTS = (TOUCHES, ACTIVE_USE_1, ACTIVE_USE_2)
#: The layer it serves.
SERVES = "or/washington/hillsboro"
#: The traced figure, under ``flats/config/areas``.
TRACED = "or/washington/hillsboro/active-use-streets.geojson"

AU1, AU2, NONE = "au1", "au2", "none"
TYPES = frozenset({AU1, AU2, NONE})
ACTIVE = frozenset({AU1, AU2})

#: How far a lot's outline may lie from every traced Active Use line and
#: still be read, without street lines, as having no frontage on one: twice
#: the reach a lot line is read at, so a lot across even a wide street from
#: one is never answered False from its outline.
CLEAR_FT = 2 * FRONT_REACH_FT


@dataclass(frozen=True)
class ActiveUse:
    """The traced centrelines and the Active Use type of each."""

    streets: Lines
    types: tuple[str, ...]
    #: The traced Active Use lines alone, for the outline test.
    active: tuple[Any, ...]

    @classmethod
    def build(cls, lines: Iterable[Any], names: Iterable[str], types: Iterable[str]) -> ActiveUse:
        geoms, labels, kinds = list(lines), list(names), list(types)
        unknown = sorted(set(kinds) - TYPES)
        if unknown:
            raise ValueError(f"unknown Active Use type(s): {unknown}")
        if not (len(geoms) == len(labels) == len(kinds)):
            raise ValueError("every traced line needs a name and an Active Use type")
        streets = Lines.build(geoms, labels)
        kept = [(g, k) for g, k in zip(geoms, kinds) if g is not None and not g.is_empty]
        return cls(
            streets,
            tuple(k for _, k in kept),
            tuple(g for g, k in kept if k in ACTIVE),
        )

    def _points(self, edge: Sequence[object]) -> list[str | None]:
        """The type of the centreline each sample point of one street line
        abuts, None where none."""
        from shapely.geometry import Point

        x1, y1, x2, y2 = (float(v) for v in edge[:4])  # type: ignore[arg-type]
        if x1 == x2 and y1 == y2:
            return []
        own = bearing_deg(x1, y1, x2, y2)
        out: list[str | None] = []
        for k in range(1, SAMPLES + 1):
            p = Point(x1 + (x2 - x1) * k / (SAMPLES + 1), y1 + (y2 - y1) * k / (SAMPLES + 1))
            s = _fronted(p, own, self.streets)
            out.append(None if s is None else self.types[s])
        return out

    def edge_type(self, edge: Sequence[object]) -> str | None:
        """The Active Use type of one street line: the type of the
        centreline it abuts at :data:`MIN_SHARE` or more of its sample
        points, else None."""
        seen = Counter(k for k in self._points(edge) if k is not None)
        if not seen:
            return None
        kind, hits = seen.most_common(1)[0]
        return kind if hits / SAMPLES >= MIN_SHARE else None

    def facts(self, edges: Sequence[Sequence[object]]) -> dict[str, bool]:
        """The answers for one lot's s4 edges (see the module docstring);
        ``{}`` where the lot has no street line."""
        street = [e for e in edges if len(e) >= 5 and e[4] == STREET_CLASS]
        if not street:
            return {}
        if self._far(street):
            return {TOUCHES: False, ACTIVE_USE_1: False, ACTIVE_USE_2: False}
        read = [self._points(e) for e in street]
        touches = any(k in ACTIVE for pts in read for k in pts)
        if not touches:
            from shapely.geometry import LineString

            for e, pts in zip(street, read):
                if any(k is not None for k in pts):
                    continue
                # A street line no traced centreline explains, near an
                # Active Use line: it may be on one, so nothing is answered.
                line = LineString([(float(e[0]), float(e[1])), (float(e[2]), float(e[3]))])  # type: ignore[arg-type]
                if not self.clear_of(line):
                    return {}
            return {TOUCHES: False, ACTIVE_USE_1: False, ACTIVE_USE_2: False}
        kinds = {self.edge_type(e) for e in street}
        if kinds == {AU1}:
            return {TOUCHES: True, ACTIVE_USE_1: True, ACTIVE_USE_2: False}
        if kinds == {AU2}:
            return {TOUCHES: True, ACTIVE_USE_1: False, ACTIVE_USE_2: True}
        return {TOUCHES: True}

    def _far(self, street: Sequence[Sequence[object]]) -> bool:
        """Whether every street line lies outside the traced Active Use
        lines' box, grown by :data:`CLEAR_FT` -- the quick answer for the
        lots nowhere near South Hillsboro's cores."""
        if not self.active:
            return True
        x0 = min(g.bounds[0] for g in self.active) - CLEAR_FT
        y0 = min(g.bounds[1] for g in self.active) - CLEAR_FT
        x1 = max(g.bounds[2] for g in self.active) + CLEAR_FT
        y1 = max(g.bounds[3] for g in self.active) + CLEAR_FT
        xs = [float(v) for e in street for v in (e[0], e[2])]  # type: ignore[arg-type]
        ys = [float(v) for e in street for v in (e[1], e[3])]  # type: ignore[arg-type]
        return max(xs) < x0 or min(xs) > x1 or max(ys) < y0 or min(ys) > y1

    def clear_of(self, outline: Any) -> bool:
        """Whether a lot's outline lies beyond :data:`CLEAR_FT` of every
        traced Active Use line."""
        return all(outline.distance(g) > CLEAR_FT for g in self.active)


@lru_cache(maxsize=None)
def load_active_use(file: str = TRACED) -> ActiveUse:
    """The traced figure in ``file`` (under ``flats/config/areas``)."""
    from shapely.geometry import shape

    data = json.loads((AREAS_ROOT / file).read_text(encoding="utf-8"))
    feats = [f for f in data["features"] if f.get("geometry")]
    return ActiveUse.build(
        (shape(f["geometry"]) for f in feats),
        (str(f["properties"].get("name") or "") for f in feats),
        (str(f["properties"]["active_use"]) for f in feats),
    )


def observed_active_use(
    edges: Sequence[Sequence[object]] | None, layer_id: str | None, lot: object = None
) -> dict[str, bool]:
    """The Active Use answers for a lot on Hillsboro's layer (see the
    module docstring); ``{}`` off it or where the lot cannot be read."""
    if layer_id != SERVES:
        return {}
    traced = load_active_use()
    if edges:
        got = traced.facts(edges)
        if got:
            return got
    outline = _outline(lot)
    if outline is not None and traced.clear_of(outline):
        return {TOUCHES: False, ACTIVE_USE_1: False, ACTIVE_USE_2: False}
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
