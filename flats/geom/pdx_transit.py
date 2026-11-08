"""Which of a Portland lot's lines front a transit street, off the city's map.

Four of the Centers Main Street overlay's rules (33.415.200, 300.B, 330.B,
and 340's windows with 200) turn on a *transit street*: "a street that is
classified in the Transportation System Plan as: A Major Transit Priority
Street, Transit Access Street, or Community Transit Street; or A Regional
Transitway not also classified as a Regional Trafficway" (33.910). Until
2026-11-08 the screen took every street as one, the worst case. The city
publishes the classification -- Portland Maps
``Public/Transportation_System_Plan/MapServer/3``, "Transit Classifications"
-- and two files under ``flats/config/areas`` hold it:

* :data:`TRACED` -- every segment classed MTP, TA, RT or RTMTP (7,417,
  fetched 2026-10-22; the layer has no CT rows). Regional Transitways that
  are also Regional Trafficways, or entirely underground, are kept: a line
  too many is a flag too many, never a false GREEN.
* :data:`UNCLASSIFIED` -- the segments the layer gives no class (``UNK``, or
  blank; 210, fetched 2026-11-08). A line beside one may be on a transit
  street.

The layer census of 2026-11-08 (``UNCLASSIFIED``'s ``source.note``) counts
exactly the 7,417 transit segments the first file holds, so a street the
two files leave out is one the plan classes Local Service Transit, No
Transit Class, or does not draw: by 33.910's own words, not a transit street.

**A street lot line, at points along it** (:data:`~flats.geom.corridor.SAMPLES`,
ends excluded), reads:

* :data:`TRANSIT` where a transit segment runs abreast of the point, parallel
  and within :data:`~flats.geom.corridor.FRONT_REACH_FT` (the street the line
  abuts, :func:`flats.geom.corridor._fronted`);
* :data:`CLEAR` where no segment of either file lies within :data:`CLEAR_FT`
  of the point at a bearing closer than :data:`CROSS_DEG` to the line's own --
  a segment crossing it more steeply is the cross street at a corner, which
  this line does not front;
* :data:`MAYBE` otherwise.

A line is TRANSIT where at least :data:`~flats.geom.corridor.MIN_SHARE` of its
points are, CLEAR only where every point is, and MAYBE otherwise; a street
(one of :func:`flats.fit.frontage.street_chains`) is TRANSIT where any of its
lines is, CLEAR where every one is. A lot line the lot's edges do not call a
street line, with a segment of either file abreast of it within
``FRONT_REACH_FT``, may be a street line nothing drew: the lot is then never
read as fronting no transit street.

**Within 100 ft** (33.415.300.B) is read on the drawn building (the houses the
section bars), or the lot where nothing is drawn: clear where it lies beyond
:data:`BAN_CLEAR_FT` of every segment of either file -- 100 ft past the widest
a street can sit from its centreline (``CORRIDOR_REACH_FT``) -- and within,
short of that, wherever a street line of the lot reads TRANSIT.

**Only Portland.** The map is the city's plan; the unincorporated pockets the
city's zoning answers (:data:`flats.geom.pdx_overlays.ANSWERS`) and a lot off
the map's extent are not read (:func:`read` gives None), and every street
there is still taken as a transit street.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from flats.geom.corridor import CORRIDOR_REACH_FT, FRONT_REACH_FT, MIN_SHARE, SAMPLES, Lines, _along, _fronted
from flats.geom.edges import bearing_delta
from flats.rules.loader import AREAS_ROOT

#: The held layer, under ``flats/config/areas``.
TRACED = "or/multnomah/portland/transit-streets.geojson"
UNCLASSIFIED = "or/multnomah/portland/transit-streets-unclassified.geojson"
#: The map's source, said on the flags.
SOURCE = "the city's Transportation System Plan transit classification map (Portland Maps, fetched 2026-10-22)"

#: The one jurisdiction the map reads (the bridge's ``jurisdiction``).
SERVES = "portland"

TRANSIT = "transit"
CLEAR = "clear"
MAYBE = "maybe"

#: How far from a point of a street lot line a segment still may be the
#: street the line abuts: the corridor maps' reach, wide enough for Barbur's
#: divided lanes.
CLEAR_FT = CORRIDOR_REACH_FT
#: A segment crossing a lot line at more than this is a cross street.
CROSS_DEG = 60.0
#: 33.415.300.B's 100 ft, from the street's edge, read from its centreline.
BAN_FT = 100.0
BAN_CLEAR_FT = BAN_FT + CORRIDOR_REACH_FT

#: The layer's ``Transit`` codes, as the plan names them.
CLASS_WORDS = {
    "MTP": "Major Transit Priority Street",
    "TA": "Transit Access Street",
    "CT": "Community Transit Street",
    "RT": "Regional Transitway",
    "RTMTP": "Regional Transitway / Major Transit Priority Street",
}


@dataclass(frozen=True)
class TransitMap:
    """The transit segments, the unclassified ones, and both together."""

    transit: Lines
    words: tuple[str, ...]
    unclassified: Lines
    every: Lines
    bounds: tuple[float, float, float, float]

    @classmethod
    def build(
        cls, transit: Iterable[tuple[Any, str, str]], unclassified: Iterable[Any] = ()
    ) -> TransitMap:
        """``transit`` as (line, street name, Transit code)."""
        rows = [(g, n, c) for g, n, c in _parts3(transit)]
        loose = [g for g in _parts(unclassified)]
        every = [g for g, _, _ in rows] + loose
        import shapely

        box = shapely.total_bounds(every) if every else (0.0, 0.0, 0.0, 0.0)
        return cls(
            Lines.build([g for g, _, _ in rows], [n for _, n, _ in rows]),
            tuple(f"{n or 'an unnamed street'} ({CLASS_WORDS.get(c, c)})" for _, n, c in rows),
            Lines.build(loose),
            Lines.build(every),
            tuple(float(v) for v in box),  # type: ignore[arg-type]
        )

    def covers(self, geom: Any) -> bool:
        """Whether ``geom`` lies within the map's extent."""
        x0, y0, x1, y1 = geom.bounds
        bx0, by0, bx1, by1 = self.bounds
        return x0 >= bx0 and y0 >= by0 and x1 <= bx1 and y1 <= by1

    def point(self, p: Any, own: float, *, street: bool = True) -> tuple[str, int | None]:
        """One sample point of a lot line of bearing ``own``: its reading and
        the transit segment it fronts. ``street`` False reads a line the
        edges do not call a street line: MAYBE where a segment of either file
        is abreast of it, CLEAR otherwise."""
        s = _fronted(p, own, self.transit)
        if s is not None:
            return (TRANSIT if street else MAYBE), s
        if _fronted(p, own, self.unclassified) is not None:
            return MAYBE, None
        if not street:
            return CLEAR, None
        for i in self.every.near(p, CLEAR_FT):
            if bearing_delta(own, _along(self.every.lines[i], p)) < CROSS_DEG:
                return MAYBE, None
        return CLEAR, None

    def line(self, edge: Any, *, street: bool = True) -> tuple[str, frozenset[int]]:
        """One lot line (an :class:`flats.geom.edges.Edge`): its reading and
        the transit segments it fronts."""
        from shapely.geometry import Point

        x1, y1, x2, y2 = float(edge.x1), float(edge.y1), float(edge.x2), float(edge.y2)
        if x1 == x2 and y1 == y2:
            return CLEAR, frozenset()
        own = float(edge.bearing_deg)
        got = [
            self.point(
                Point(x1 + (x2 - x1) * k / (SAMPLES + 1), y1 + (y2 - y1) * k / (SAMPLES + 1)),
                own,
                street=street,
            )
            for k in range(1, SAMPLES + 1)
        ]
        hits = frozenset(s for r, s in got if r == TRANSIT and s is not None)
        if sum(r == TRANSIT for r, _ in got) / SAMPLES >= MIN_SHARE:
            return TRANSIT, hits
        if all(r == CLEAR for r, _ in got):
            return CLEAR, frozenset()
        return MAYBE, frozenset()

    def clear_of(self, geom: Any, distance: float) -> bool:
        """Whether ``geom`` lies beyond ``distance`` of every segment."""
        return not self.every.near(geom, distance)


@dataclass(frozen=True)
class Frontage:
    """What the map says of one lot."""

    #: 33.415.200's "frontage on a transit street": TRANSIT, CLEAR or MAYBE.
    fronts: str
    #: Each street of :func:`flats.fit.frontage.street_chains`, in order.
    streets: tuple[str, ...]
    #: 33.415.300.B's "within 100 feet of a transit street".
    near: str
    #: The transit streets the lot fronts, as the plan names them.
    names: tuple[str, ...] = ()

    def words(self) -> str:
        """The reading said in a clause, for a flag's source."""
        if self.fronts == TRANSIT:
            return f"the lot fronts {', '.join(self.names)} on {SOURCE}"
        if self.near == CLEAR:
            return f"no transit street lies within {BAN_FT:.0f} ft of the lot on {SOURCE}"
        return f"{SOURCE} does not settle every street of the lot, so each unsettled one is taken as one"


def _parts(geoms: Iterable[Any]) -> Iterable[Any]:
    for g in geoms:
        if g is None or g.is_empty:
            continue
        yield from (getattr(g, "geoms", None) or (g,))


def _parts3(rows: Iterable[tuple[Any, str, str]]) -> Iterable[tuple[Any, str, str]]:
    for g, n, c in rows:
        for part in _parts((g,)):
            yield part, n, c


@lru_cache(maxsize=None)
def load(traced: str = TRACED, unclassified: str = UNCLASSIFIED) -> TransitMap:
    """The two held files (under ``flats/config/areas``)."""
    from shapely.geometry import shape

    def feats(file: str) -> list[dict[str, Any]]:
        data = json.loads((AREAS_ROOT / file).read_text(encoding="utf-8"))
        return [f for f in data["features"] if f.get("geometry")]

    return TransitMap.build(
        (
            (shape(f["geometry"]), str(f["properties"].get("StreetName") or ""), str(f["properties"].get("Transit") or ""))
            for f in feats(traced)
        ),
        (shape(f["geometry"]) for f in feats(unclassified)),
    )


def read(tm: TransitMap | None, lot: Any, edges: Any, building: Any | None = None) -> Frontage | None:
    """The map's reading for one lot (EPSG:2913) and its edges; None where
    the map does not reach it (no map, no lot, off its extent): every street
    is then taken as a transit street."""
    if tm is None or lot is None or lot.is_empty or not tm.covers(lot):
        return None
    from flats.fit.frontage import street_chains

    chains = street_chains(edges) if edges is not None else ()
    in_chain = {id(e) for chain in chains for e in chain}
    streets: list[str] = []
    fronted: set[int] = set()
    for chain in chains:
        got = [tm.line(e) for e in chain]
        for _, hits in got:
            fronted |= hits
        kinds = {r for r, _ in got}
        streets.append(TRANSIT if TRANSIT in kinds else CLEAR if kinds == {CLEAR} else MAYBE)
    others = [e for e in getattr(edges, "edges", ()) if id(e) not in in_chain]
    hidden = any(tm.line(e, street=False)[0] != CLEAR for e in others)
    outline = building if building is not None and not building.is_empty else lot
    far = tm.clear_of(outline, BAN_CLEAR_FT)
    lot_far = tm.clear_of(lot, BAN_CLEAR_FT)
    if lot_far:
        streets = [CLEAR] * len(streets)
    if TRANSIT in streets:
        fronts = TRANSIT
    elif lot_far or (chains and set(streets) == {CLEAR} and not hidden):
        fronts = CLEAR
    else:
        fronts = MAYBE
    near = CLEAR if far else TRANSIT if fronts == TRANSIT else MAYBE
    names = tuple(sorted({tm.words[i] for i in fronted}))
    return Frontage(fronts, tuple(streets), near, names)


__all__ = [
    "BAN_CLEAR_FT",
    "CLEAR",
    "CLEAR_FT",
    "CROSS_DEG",
    "Frontage",
    "MAYBE",
    "SERVES",
    "TRANSIT",
    "TRACED",
    "TransitMap",
    "UNCLASSIFIED",
    "load",
    "read",
]
