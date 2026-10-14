"""Road land a lot gives up, or the extra yard it keeps, to reach a set
distance from the street's centre line -- and how far that takes its
building line back.

Six codes in the screen's reach write the same idea two ways:

* **Dedication** -- the lot hands over the strip before its first building
  permit and its yards run from the new line. Washington County CDC 302-2.14
  C(1) (and 303 to 307, 375, 390): "Local street: 25 feet to centerline;
  Neighborhood route: 30 feet to centerline; Collector: 37 feet to
  centerline; Arterial: 45 feet to centerline", nothing where the road is
  already built to the county's final width. Oregon City 16.12.011.B: middle
  housing "shall provide any necessary dedications ... as identified in the
  transportation system plan and this chapter", to the right-of-way of Table
  16.12.016 for the street's class.
* **Added setback** -- the lot keeps the strip but may not build on it.
  Sherwood 16.106.030 D: "Additional setbacks shall be measured at right
  angles from the centerline of the street" (26 / 32 / 32 / 37 / 61 ft by
  class); King City 16.80.060 A: the yard "shall be increased by the amount
  of right-of-way, measured from the street centerline, necessary" (33 / 30
  / 25 ft by named street); Milwaukie 19.501.2.A: "the minimum distance from
  the center line of the right-of-way to the closest point of any building is
  the distance listed in Table 19.501.2.A plus the yard requirement of the
  underlying zone" (25 / 30 / 40 ft by named street).

Both come to the same line on the ground: the building stands the zone's
yard back from a line the stated distance off the centre line, or the yard
back from the lot line where the street is already that wide. So one
arithmetic serves both forms: the strip is the stated distance less the
measured half-width, never below zero, added to the line's setback
(:meth:`flats.geom.envelope.Setbacks.for_edge`). The forms differ in whether
the lot's AREA shrinks (a dedication) or not; the screen counts area before
either (WashCo 302-7.1 A), which is the permissive side for a dedication
and is named in FOLLOWUPS 77.

**What is measured** (:func:`measure`, once per lot in the bridge). For each
street lot line: the distance to the street's centre line (Metro's RLIS
file) at the nine sample points the class rank is read at, the narrowest one
kept; the street's NAME there (for a code that lists streets by name); and
the street's CLASS on every TSP map a code here reads by class
(:data:`READS`). Where fewer than :data:`MIN_MEASURED` points have a
centreline running beside them (a stub, a curve), the nearest centreline of
any bearing within reach of every point is read instead -- never farther than
the street truly abutted -- and every street within reach counts as a name
the line might be on.

A short piece whose own class reading fails (a corner cut-off, a curve) but
whose one street is read with a class on another line of the same lot takes
the busiest class read for it (:func:`_lot_ranks`); a piece on two streets
or an unread one stays at the worst case.

**What is not.** A line no centreline reaches is *unmeasured* and gives up the
whole distance (the lot line on the centre line). A line whose class or
name is unread takes the deepest distance the zone states
(:meth:`Rule.deepest`). A street that is not public (RLIS TYPE 1700 / 1800,
a private road or drive) takes nothing.

The distances are the rules' (``row_to_centerline_*``); this module holds
only how a class rank or a street name picks one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

from flats.geom.corridor import FRONT_REACH_FT, SAMPLES, STREET_CLASS, _fronted
from flats.geom.street_class import ClassMap, _rank_at, _samples, edge_rank

if TYPE_CHECKING:
    from flats.rules.resolver import ZoneResolution

#: Layers whose lots are measured: every layer a zone with the distances can
#: reach, its own or through a pocket of another layer's zoning (Beaverton's
#: and Hillsboro's county land, King City's "(WC)" districts, the Milwaukie
#: R-MD lots the Clackamas roll still calls unincorporated). A test holds it
#: to the rules (`test_every_layer_a_dedication_reaches_is_measured`).
LAYERS: tuple[str, ...] = (
    "or/washington/_unincorporated",
    "or/washington/beaverton",
    "or/washington/hillsboro",
    "or/washington/king-city",
    "or/washington/sherwood",
    "or/clackamas/oregon-city",
    "or/clackamas/milwaukie",
    "or/clackamas/_unincorporated",
)

#: The class-distance fields, by the class name each code prints. A code
#: states the ones its own table holds; a class it does not state is read as
#: unread (the deepest distance), never as none.
CLASS_FIELDS: dict[str, str] = {
    "local": "row_to_centerline_local_ft",
    "neighborhood_route": "row_to_centerline_neighborhood_route_ft",
    "collector": "row_to_centerline_collector_ft",
    "arterial": "row_to_centerline_arterial_ft",
    "minor_arterial": "row_to_centerline_minor_arterial_ft",
    "major_arterial": "row_to_centerline_major_arterial_ft",
    "principal_arterial": "row_to_centerline_principal_arterial_ft",
}

#: The distances listed by street name (King City, Milwaukie).
NAMED_FIELD = "row_to_centerline_named_ft"

#: The distance for a street the named list leaves out, where the code states
#: one (King City's "All other city streets").
OTHER_FIELD = "row_to_centerline_other_ft"

#: Whose TSP map ranks the classes the code reads.
CLASS_BY_FIELD = "row_to_centerline_class_by"

#: True where the class values are the printed WHOLE right-of-way width
#: (Oregon City Table 16.12.016): half of each is the distance.
WIDTH_FIELD = "row_to_centerline_stated_as_width"

#: Every field this module reads.
FIELDS: tuple[str, ...] = (*CLASS_FIELDS.values(), NAMED_FIELD, OTHER_FIELD, CLASS_BY_FIELD, WIDTH_FIELD)

#: ``row_to_centerline_class_by`` -> the registry dataset whose map ranks it.
CLASS_BY_MAP: dict[str, str] = {
    "washington_county": "street_class_washington",
    "sherwood": "street_class_sherwood",
    "oregon_city": "street_class_oregon_city",
}

#: Each map's rank (:attr:`flats.geom.street_class.ClassSpec.rank`) -> the
#: class name its code's distance table uses. A rank left out (Oregon City's
#: Expressway and Freeway, which Table 16.12.016 has no row for) is unread.
BUCKETS: dict[str, dict[int, str]] = {
    # CDC 302-2.14 C(1) lists Local, Neighborhood route, Collector and
    # Arterial; the county map's Principal Arterial and Freeway are arterials
    # in that list.
    "street_class_washington": {
        0: "local",
        1: "neighborhood_route",
        2: "collector",
        3: "arterial",
        4: "arterial",
        5: "arterial",
    },
    # Table 16.12.016 rows: Major Arterial, Minor Arterial, Collector, Local.
    "street_class_oregon_city": {0: "local", 1: "collector", 2: "minor_arterial", 3: "major_arterial"},
    # 16.106.030 D: Principle Arterial (99W), Arterial, Collector,
    # Neighborhood Route, Local.
    "street_class_sherwood": {
        0: "local",
        1: "neighborhood_route",
        2: "collector",
        3: "arterial",
        4: "principal_arterial",
    },
}

#: Which layers each class map is read for. A county-zoned pocket inside a
#: city reads the county's own map, as its code does (the county TSP draws its
#: classified roads countywide).
READS: dict[str, tuple[str, ...]] = {
    "street_class_washington": ("or/washington",),
    "street_class_oregon_city": ("or/clackamas/oregon-city",),
    "street_class_sherwood": ("or/washington/sherwood",),
}

#: A layer no class map serves whose lots a dedication reaches through a
#: pocket, and the map whose streets reach them: the Milwaukie R-MD lots at
#: the city's edge.
STREETS_FROM: dict[str, str] = {"or/clackamas/_unincorporated": "street_class_milwaukie"}

#: A street Metro types as a private road or drive is not a public street.
PRIVATE_TYPES: frozenset[int] = frozenset({1700, 1800})

#: Fewest sample points (of :data:`SAMPLES`) that must have a centreline
#: beside them for a line to count as measured.
MIN_MEASURED = SAMPLES // 2 + 1

#: How a code spells a street type, and how Metro's file does.
_TYPES: dict[str, str] = {
    "AVENUE": "AVE",
    "BOULEVARD": "BLVD",
    "COURT": "CT",
    "DRIVE": "DR",
    "HIGHWAY": "HWY",
    "LANE": "LN",
    "PARKWAY": "PKWY",
    "PLACE": "PL",
    "ROAD": "RD",
    "STREET": "ST",
    "TERRACE": "TER",
}
_DIRECTIONS = frozenset({"N", "S", "E", "W", "NE", "NW", "SE", "SW"})


def street_key(label: object) -> str:
    """A street's name as both a code and Metro's file can be compared on:
    upper case, directions dropped, the street type abbreviated, anything in
    brackets (a code's "(55th Ave. to Stanley Ave.)") left out."""
    text = re.sub(r"\([^)]*\)", " ", str(label or "")).upper().replace(".", " ")
    words = [_TYPES.get(w, w) for w in text.split()]
    while words and words[0] in _DIRECTIONS:
        words = words[1:]
    while words and words[-1] in _DIRECTIONS:
        words = words[:-1]
    return " ".join(words)


def applies(layer_id: str | None) -> bool:
    """Whether ``layer_id``'s lots are measured."""
    return bool(layer_id) and any(layer_id == s or layer_id.startswith(f"{s}/") for s in LAYERS)


def _streets_for(layer_id: str | None, maps: Sequence[ClassMap]) -> ClassMap | None:
    """The map whose RLIS streets the half-width is read off: the county map,
    which keeps Metro's whole file, for a Washington County layer; the map
    :data:`STREETS_FROM` names; else the first map serving the layer. None
    where none is loaded: every line is then unmeasured (the worst case)."""
    by_key = {m.key: m for m in maps}
    if layer_id and layer_id.startswith("or/washington/") and "street_class_washington" in by_key:
        return by_key["street_class_washington"]
    if layer_id in STREETS_FROM and STREETS_FROM[layer_id] in by_key:
        return by_key[STREETS_FROM[layer_id]]
    serving = [m for m in maps if m.covers(layer_id)]
    return serving[0] if serving else None


def half_width_ft(edge: Sequence[float], cmap: ClassMap) -> tuple[float | None, bool]:
    """One street lot line's measured half-width, and whether the street is public.

    The smallest centreline distance over the sample points that have a
    street beside them, or the :func:`_nearest` reading where fewer than
    :data:`MIN_MEASURED` do (None where even that finds nothing). The street
    is public unless a point abuts a private road or drive.
    """
    width, public, _ = read_line(edge, cmap)
    return width, public


def read_line(edge: Sequence[float], cmap: ClassMap) -> tuple[float | None, bool, tuple[str, ...] | None]:
    """:func:`half_width_ft` and the names of the streets the line may be on
    (:func:`street_key`), None where some point has no street within reach."""
    got = _samples(edge)
    if got is None:
        return None, True, None
    points, own = got
    widths: list[float] = []
    names: set[str] = set()
    for p in points:
        s = _fronted(p, own, cmap.streets)
        if s is None:
            continue
        if cmap.types[s] in PRIVATE_TYPES:
            return None, False, None
        widths.append(float(cmap.streets.lines[s].distance(p)))
        names.add(street_key(cmap.streets.names[s]))
    if len(widths) >= MIN_MEASURED:
        return min(widths), True, tuple(sorted(names))
    return _nearest(points, cmap)


def _nearest(points: Sequence[Any], cmap: ClassMap) -> tuple[float | None, bool, tuple[str, ...] | None]:
    """The reading for a line no centreline runs beside (a stub, a curve):
    the distance to the nearest centreline of any bearing within reach of
    EVERY sample point. It can only be shorter than the distance to the
    street the lot truly abuts, so the strip it asks for is never short. Every
    street within reach of a point counts as one the line may be on, so a
    named distance is never missed. None where some point has no centreline
    within reach."""
    widths: list[float] = []
    names: set[str] = set()
    for p in points:
        near = cmap.streets.near(p, FRONT_REACH_FT)
        if not near:
            return None, True, None
        s = min(near, key=lambda i: cmap.streets.lines[i].distance(p))
        if cmap.types[s] in PRIVATE_TYPES:
            return None, False, None
        names.update(street_key(cmap.streets.names[i]) for i in near)
        d = float(cmap.streets.lines[s].distance(p))
        if cmap.osm is not None:
            # A street Metro's file lacks may run closer: OpenStreetMap's roads
            # can only bring the reading in, never push it out.
            d = min([d, *(float(cmap.osm.lines[i].distance(p)) for i in cmap.osm.near(p, FRONT_REACH_FT))])
        widths.append(d)
    return min(widths), True, tuple(sorted(names))


def _reads(cmap: ClassMap, layer_id: str | None) -> bool:
    places = READS.get(cmap.key, ())
    return bool(layer_id) and any(layer_id == s or layer_id.startswith(f"{s}/") for s in places)


def measure(edges: Iterable[Sequence[Any]], layer_id: str | None, maps: Sequence[ClassMap]) -> list[list[Any]]:
    """Every street line of one lot, as ``[x1, y1, x2, y2, half_width_ft,
    public, names, classes]`` -- the half-width None where unmeasured, the
    names None where unread, ``classes`` the class name on each map read for
    the layer (``{map key: class or None}``). Empty where no map gives the
    streets."""
    cmap = _streets_for(layer_id, maps)
    if cmap is None:
        return []
    ranked = [m for m in maps if _reads(m, layer_id)]
    lines = [e for e in edges if len(e) >= 5 and e[4] == STREET_CLASS]
    reads = [read_line(e, cmap) for e in lines]  # type: ignore[arg-type]
    ranks = {m.key: _lot_ranks(lines, [names for _, _, names in reads], m) for m in ranked}
    out: list[list[Any]] = []
    for i, (e, (width, public, names)) in enumerate(zip(lines, reads)):
        classes: dict[str, str | None] = {}
        for m in ranked:
            rank = ranks[m.key][i]
            classes[m.key] = None if rank is None else BUCKETS.get(m.key, {}).get(rank)
        out.append(
            [
                *(round(float(v), 3) for v in e[:4]),
                None if width is None else round(width, 3),
                public,
                None if names is None else list(names),
                classes,
            ]
        )
    return out


def _lot_ranks(
    lines: Sequence[Sequence[Any]], names: Sequence[tuple[str, ...] | None], cmap: ClassMap
) -> list[int | None]:
    """Each street line's class rank on ``cmap``: :func:`edge_rank`, or, for a
    line it leaves unread, the busiest rank read for that line's one street
    on the lot's other lines.

    A corner cut-off or a short curve piece has no TSP line abreast at some
    sample point, so its own reading fails; left unread it takes the zone's
    deepest distance (61 ft on a Sherwood local street). Where the piece is
    on ONE named street and that street is read with a class on another line
    of the same lot, the piece takes the busiest class read for it there and
    on the piece's own sample points -- the rank only rises with the
    distance on every map here, so it is never shallower than the street it
    is on. A piece with no name, with two names (it may be on either
    street), or whose name is read on no other line of this lot stays
    unread: the worst case (coordinator ruling 2026-10-14)."""
    own = [edge_rank(e, cmap) for e in lines]  # type: ignore[arg-type]
    by_name: dict[str, int] = {}
    for rank, got in zip(own, names):
        if rank is not None and got is not None and len(got) == 1:
            by_name[got[0]] = max(rank, by_name.get(got[0], rank))
    out: list[int | None] = []
    for e, rank, got in zip(lines, own, names):
        if rank is None and got is not None and len(got) == 1 and got[0] in by_name:
            seen = [r for r in _point_ranks(e, cmap) if r is not None]
            rank = max([by_name[got[0]], *seen])
        out.append(rank)
    return out


def _point_ranks(edge: Sequence[Any], cmap: ClassMap) -> list[int | None]:
    got = _samples(edge)  # type: ignore[arg-type]
    if got is None:
        return []
    points, own = got
    return [_rank_at(p, own, cmap) for p in points]


def key(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float, float]:
    """The coordinates a measured line is looked up by."""
    return (round(float(x1), 3), round(float(y1), 3), round(float(x2), 3), round(float(y2), 3))


def _number(v: object) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return float(v)


@dataclass(frozen=True)
class Rule:
    """One zone's distances to centre line: by class (read off the map
    ``class_by`` names), by street name, and for a street the name list
    leaves out."""

    classes: Mapping[str, float]
    class_by: str | None
    named: tuple[tuple[str, float], ...]
    other: float | None

    def deepest(self) -> float:
        """The deepest distance the zone states: what an unread line takes."""
        return max([*self.classes.values(), *(ft for _, ft in self.named), *([self.other] if self.other is not None else [])])

    def _by_class(self, classes: Mapping[str, str | None]) -> float:
        bucket = classes.get(CLASS_BY_MAP.get(self.class_by or "", ""))
        if bucket is None or bucket not in self.classes:
            return max(self.classes.values())
        return self.classes[bucket]

    def required(self, names: Sequence[str] | None, classes: Mapping[str, str | None]) -> float:
        """The distance one street line must reach.

        A street the name list holds takes its listed distance (the deepest,
        where the code lists one street twice for two stretches: the stretch
        is not read). Any other street takes its class's distance, or the
        unlisted distance, or none. An unread name, where names decide, and
        an unread class, where classes do, take :meth:`deepest`.
        """
        if self.named and names is None:
            return self.deepest()
        if not self.named:
            return self._by_class(classes) if self.classes else (self.other or 0.0)
        listed = dict(self._listed())
        got = []
        for n in names or ():
            if n in listed:
                got.append(listed[n])
            elif self.classes:
                got.append(self._by_class(classes))
            else:
                got.append(self.other or 0.0)
        if not got:
            got.append(self._by_class(classes) if self.classes else (self.other or 0.0))
        return max(got)

    def _listed(self) -> list[tuple[str, float]]:
        best: dict[str, float] = {}
        for n, ft in self.named:
            best[n] = max(ft, best.get(n, 0.0))
        return list(best.items())


def rule_of(rules: "ZoneResolution") -> Rule | None:
    """The zone's :class:`Rule`, or None where it states no distance."""
    classes = {c: n for c, f in CLASS_FIELDS.items() if (n := _number(rules.get(f))) is not None}
    if rules.get(WIDTH_FIELD) is True:
        classes = {c: n / 2.0 for c, n in classes.items()}
    named: list[tuple[str, float]] = []
    table = rules.get(NAMED_FIELD)
    if isinstance(table, (list, tuple)):
        for entry in table:
            ft = _number(entry[1]) if isinstance(entry, (list, tuple)) and len(entry) == 2 else None
            if ft is not None:
                named.append((street_key(entry[0]), ft))
    other = _number(rules.get(OTHER_FIELD))
    if not classes and not named and other is None:
        return None
    by = rules.get(CLASS_BY_FIELD)
    return Rule(classes=classes, class_by=by if isinstance(by, str) else None, named=tuple(named), other=other)


def depth_ft(required: float, half_width: float | None) -> float:
    """The strip a lot gives up on one street line: the shortfall, never
    below zero, and the whole distance where the half-width is unmeasured."""
    if half_width is None:
        return required
    return max(0.0, required - half_width)


__all__ = [
    "BUCKETS",
    "CLASS_BY_FIELD",
    "CLASS_BY_MAP",
    "CLASS_FIELDS",
    "FIELDS",
    "LAYERS",
    "MIN_MEASURED",
    "NAMED_FIELD",
    "OTHER_FIELD",
    "PRIVATE_TYPES",
    "READS",
    "STREETS_FROM",
    "WIDTH_FIELD",
    "Rule",
    "applies",
    "depth_ft",
    "half_width_ft",
    "key",
    "measure",
    "read_line",
    "rule_of",
    "street_key",
]
