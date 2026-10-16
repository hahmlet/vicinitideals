"""Road land a lot gives up, or the extra yard it keeps, to reach a set
distance from the street's centre line -- and how far that takes its
building line back.

Seven codes in the screen's reach write the same idea two ways:

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
  underlying zone" (25 / 30 / 40 ft by named street); Tigard 18.210.030.A.1:
  "Where the ultimate right-of-way width, as shown in the Transportation
  System Plan, is wider than the current right-of-way width, required
  setbacks are measured from the ultimate right-of-way width" -- the TSP
  leaves the widths to Title 18, so half the widest right-of-way of Table
  18.910.1 for the street's class (27 / 29 / 48 / 64 ft).

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
whose street -- or each of its two streets -- is read with a class on
another line of the same lot takes the busiest class read for them
(:func:`_lot_ranks`); a piece with no name, or with any street read on no
other line of the lot, stays at the worst case.

**What is not.** A line no centreline reaches is *unmeasured* and gives up the
whole distance (the lot line on the centre line). A line whose class or
name is unread takes the deepest distance the zone states
(:meth:`Rule.deepest`). A street that is not public (RLIS TYPE 1700 / 1800,
a private road or drive) takes nothing: the codes widen public streets
(Tigard's chapter: "the term 'streets' shall mean 'public streets'",
18.910.020.E; a private street's design is "established by the City
Engineer", 18.910.030.T.1).

**The land on both sides.** Oregon City's table keys the row to the plan
designation of the land beside the street too, the wider where the two sides
differ. Nothing maps the designation; the lot's zone and the zones the rays
across the street found stand in for it (:meth:`Rule.standin`,
:data:`DESIGNATIONS`; Steph 2026-10-14, FOLLOWUPS 82), and a line where any
of that is unread keeps the widest row.

The distances are the rules' (``row_to_centerline_*``); this module holds
only how a class rank or a street name picks one.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

from flats.geom.corridor import (
    COINCIDE_FT,
    CORRIDOR_REACH_FT,
    FRONT_REACH_FT,
    SAMPLES,
    STREET_CLASS,
    _abreast,
    _fronted,
)
from flats.geom.street_class import (
    CLASS_MAPS,
    PRIVATE_RANK,
    ClassMap,
    _rank_at,
    _samples,
    edge_rank,
    street_key,
)

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
    "or/washington/tigard",
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

#: True where the class and named values are the printed WHOLE right-of-way
#: width (Oregon City Table 16.12.016, Tigard Table 18.910.1 and River
#: Terrace Boulevard's 110 feet): half of each is the distance.
WIDTH_FIELD = "row_to_centerline_stated_as_width"

#: The distance by the street's class AND the plan designation of the land
#: beside it (Oregon City Table 16.12.016), rows ``[class / designation,
#: feet]`` (:func:`_designation_rows`). Read only through the stand-in
#: (:meth:`Rule.standin`); the class fields hold each class's widest row.
DESIGNATION_FIELD = "row_to_centerline_by_designation"

#: Every field this module reads.
FIELDS: tuple[str, ...] = (
    *CLASS_FIELDS.values(), NAMED_FIELD, OTHER_FIELD, CLASS_BY_FIELD, WIDTH_FIELD, DESIGNATION_FIELD,
)

#: ``row_to_centerline_class_by`` -> each zone the city maps, spelled as its
#: layer screens it, -> the designation row of ``row_to_centerline_by_
#: designation`` the zone's land is read as (Steph 2026-10-14, FOLLOWUPS 82:
#: "use the measured zone across the street as a stand-in for the land-use
#: designation on that side"). A zone left out maps to no row, and a line
#: facing it keeps the widest.
#:
#: Oregon City: Table 17.06.030, "CITY LAND USE CLASSIFICATIONS", gives each
#: plan classification its zones (17.zoning.txt#L3988-L4007): low, medium and
#: high density residential R-10, R-8, R-6, R-5, R-3.5, R-2; general
#: commercial C; mixed-use downtown MUD, WFDD; mixed-use corridor NC, HC,
#: MUC-1, MUC-2; mixed-use employment MUE (all on 16.12.016's "Mixed Use,
#: Commercial or Public/Quasi Public" row); industrial CI, GI. Its I zone is
#: Public/Quasi-Public in the table but 17.39.010 calls it "consistent with
#: the public/quasi-public and park designations", and the street table has
#: no park row: I is left out.
DESIGNATIONS: dict[str, dict[str, str]] = {
    "oregon_city": {
        **dict.fromkeys(("R-10", "R-8", "R-6", "R-5", "R-3.5", "R-2"), "residential"),
        **dict.fromkeys(("C", "MUD", "WFDD", "NC", "HC", "MUC-1", "MUC-2", "MUE"), "commercial"),
        **dict.fromkeys(("CI", "GI"), "industrial"),
    },
}

#: ``row_to_centerline_class_by`` -> the registry dataset whose map ranks it.
CLASS_BY_MAP: dict[str, str] = {
    "washington_county": "street_class_washington",
    "sherwood": "street_class_sherwood",
    "oregon_city": "street_class_oregon_city",
    "tigard": "street_class_tigard",
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
    # Table 18.910.1 rows: Arterial, Collector, Neighborhood Route, Local.
    # The TSP's Principal Arterial (99W, Barbur Blvd) takes the Arterial row,
    # the only one the table prints for it; a Freeway has no row (unread). A
    # street the city calls PRIVATE and Metro public takes the Local row.
    "street_class_tigard": {
        PRIVATE_RANK: "local",
        0: "local",
        1: "neighborhood_route",
        2: "collector",
        3: "arterial",
        4: "arterial",
    },
}

#: Which layers each class map is read for. A county-zoned pocket inside a
#: city reads the county's own map, as its code does (the county TSP draws its
#: classified roads countywide).
READS: dict[str, tuple[str, ...]] = {
    "street_class_washington": ("or/washington",),
    "street_class_oregon_city": ("or/clackamas/oregon-city",),
    "street_class_sherwood": ("or/washington/sherwood",),
    "street_class_tigard": ("or/washington/tigard",),
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


def read_line(
    edge: Sequence[float], cmap: ClassMap, through_private: bool = False
) -> tuple[float | None, bool, tuple[str, ...] | None]:
    """:func:`half_width_ft` and the names of the streets the line may be on
    (:func:`street_key`), None where some point has no street within reach.

    ``through_private`` measures a line on a private road as on any street
    (the public flag still says private), for a city map that calls the
    street public (:func:`measure`)."""
    got = _samples(edge)
    if got is None:
        return None, True, None
    points, own = got
    widths: list[float] = []
    names: set[str] = set()
    public = True
    for p in points:
        s = _fronted(p, own, cmap.streets)
        if s is None:
            continue
        if cmap.types[s] in PRIVATE_TYPES:
            if not through_private:
                return None, False, None
            public = False
        widths.append(float(cmap.streets.lines[s].distance(p)))
        names.add(street_key(cmap.streets.names[s]))
    if len(widths) >= MIN_MEASURED:
        return min(widths), public, tuple(sorted(names))
    width, near_public, near_names = _nearest(points, cmap, through_private)
    return width, public and near_public, near_names


def _nearest(
    points: Sequence[Any], cmap: ClassMap, through_private: bool = False
) -> tuple[float | None, bool, tuple[str, ...] | None]:
    """The reading for a line no centreline runs beside (a stub, a curve):
    the distance to the nearest centreline of any bearing within reach of
    EVERY sample point. It can only be shorter than the distance to the
    street the lot truly abuts, so the strip it asks for is never short. Every
    street within reach of a point counts as one the line may be on, so a
    named distance is never missed. None where some point has no centreline
    within reach."""
    widths: list[float] = []
    names: set[str] = set()
    public = True
    for p in points:
        near = cmap.streets.near(p, FRONT_REACH_FT)
        if not near:
            return None, public, None
        s = min(near, key=lambda i: cmap.streets.lines[i].distance(p))
        if cmap.types[s] in PRIVATE_TYPES:
            if not through_private:
                return None, False, None
            public = False
        names.update(street_key(cmap.streets.names[i]) for i in near)
        d = float(cmap.streets.lines[s].distance(p))
        if cmap.osm is not None:
            # A street Metro's file lacks may run closer: OpenStreetMap's roads
            # can only bring the reading in, never push it out.
            d = min([d, *(float(cmap.osm.lines[i].distance(p)) for i in cmap.osm.near(p, FRONT_REACH_FT))])
        widths.append(d)
    return min(widths), public, tuple(sorted(names))


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
    # A city map naming its private streets: Metro's "private" alone gives up
    # nothing only where that map agrees (:func:`_private_reading`).
    named = {m.key: m for m in ranked if m.by_name}
    for key in _name_matched(layer_id):
        for i, (e, (_, public, _)) in enumerate(zip(lines, reads)):
            if public:
                continue
            width, _, names = read_line(e, cmap, through_private=True)  # type: ignore[arg-type]
            got, city_width = _private_reading(e, cmap, named.get(key))
            if got == "private":
                continue
            reads[i] = (width if city_width is None else city_width, True, names)
            ranks.setdefault(key, [None] * len(lines))[i] = None if got == "unread" else got  # type: ignore[assignment]
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


def _name_matched(layer_id: str | None) -> list[str]:
    """The maps read for ``layer_id`` that name their streets (Tigard's), loaded
    or not: a private street there needs that map's agreement."""
    return [
        key
        for key, places in READS.items()
        if key in CLASS_MAPS
        and CLASS_MAPS[key].name_field is not None
        and bool(layer_id)
        and any(layer_id == s or layer_id.startswith(f"{s}/") for s in places)
    ]


def _private_reading(
    edge: Sequence[Any], streets: ClassMap, cmap: ClassMap | None
) -> tuple[str | int, float | None]:
    """What a city map that names its streets says of a lot line Metro puts
    on a private road or drive, and the half-width to take if it calls the
    street public.

    Read at the sample points on the private road (every point, where none
    has a centreline beside it): a city line runs along the line there where
    it runs beside such a point -- abreast and parallel -- within
    :data:`~flats.geom.corridor.CORRIDOR_REACH_FT` carrying the private
    road's name, or within :data:`~flats.geom.corridor.FRONT_REACH_FT`
    whatever its name. A public street the private drive meets end-on (an
    arterial at a mall entrance) is not beside it. A corner piece beside no
    centreline also takes a public street within reach that the city
    classes, by name (it is on that street's corner).

    ``"private"`` -- the line gives up nothing -- where no city line runs
    along it, or every one that does is private. A public classed line along
    it gives its rank (the busiest one): the city calls the street public,
    its row applies, and the half-width is measured to that city line at the
    private points (Metro's centreline at any public ones), not to the
    private drive's. An unranked line (a Freeway, an "Other") or no map
    loaded: ``"unread"``, the deepest distance (Steph's two-source rule,
    2026-10-09: the permissive answer needs both maps)."""
    if cmap is None:
        return "unread", None
    got = _samples(edge)  # type: ignore[arg-type]
    if got is None:
        return "unread", None
    points, own = got
    private: list[tuple[Any, str, int | None]] = []
    public_widths: list[float] = []
    for p in points:
        s = _fronted(p, own, streets.streets)
        if s is None:
            continue
        if streets.types[s] in PRIVATE_TYPES:
            private.append((p, street_key(streets.streets.names[s]), s))
        else:
            public_widths.append(float(streets.streets.lines[s].distance(p)))
    along: dict[int, list[tuple[Any, int | None]]] = {}
    if not private:
        # A corner cut-off or curve piece no centreline runs beside: it may be
        # on any street within reach. A public one the city classes -- its
        # line of the same name within reach of every point -- gives its row,
        # measured to that line (the piece is on that street's corner).
        private = [(p, "", None) for p in points]
        public_names: set[str] = set()
        for p in points:
            public_names.update(
                street_key(streets.streets.names[j])
                for j in streets.streets.near(p, FRONT_REACH_FT)
                if streets.types[j] not in PRIVATE_TYPES
            )
        public_names.discard("")
        for i in cmap.lines.near(points[0], FRONT_REACH_FT):
            line = cmap.lines.lines[i]
            if street_key(cmap.lines.names[i]) in public_names and all(
                line.distance(p) <= FRONT_REACH_FT for p in points
            ):
                along[i] = [(p, None) for p in points]
    for p, name, s in private:
        for i in cmap.lines.near(p, CORRIDOR_REACH_FT):
            line = cmap.lines.lines[i]
            named = bool(name) and street_key(cmap.lines.names[i]) == name
            if _abreast(line, p, own, CORRIDOR_REACH_FT if named else FRONT_REACH_FT):
                along.setdefault(i, []).append((p, s))
    ranks = [cmap.ranks[i] for i in along]
    if any(r is None for r in ranks):
        return "unread", None
    public = [i for i in along if cmap.ranks[i] != PRIVATE_RANK]
    if not public:
        return "private", None
    widths = list(public_widths)
    for i in public:
        line = cmap.lines.lines[i]
        for p, s in along[i]:
            d = float(line.distance(p))
            if s is not None:
                # The city's line drawn on the private road itself (the same
                # road, a few feet apart): the nearer of the two centrelines.
                drive = streets.streets.lines[s]
                if float(line.distance(drive.interpolate(drive.project(p)))) <= COINCIDE_FT:
                    d = min(d, float(drive.distance(p)))
            widths.append(d)
    return max(cmap.ranks[i] for i in public), min(widths)  # type: ignore[type-var]


def _lot_ranks(
    lines: Sequence[Sequence[Any]], names: Sequence[tuple[str, ...] | None], cmap: ClassMap
) -> list[int | None]:
    """Each street line's class rank on ``cmap``: :func:`edge_rank`, or, for a
    line it leaves unread, the busiest rank read for that line's street(s)
    on the lot's other lines.

    A corner cut-off or a short curve piece has no TSP line abreast at some
    sample point, so its own reading fails; left unread it takes the zone's
    deepest distance (61 ft on a Sherwood local street). Where every street
    the piece may be on (one, or the two of a corner) is read with a class on
    another line of the same lot, the piece takes the busiest class read for
    any of them there and on the piece's own sample points -- the rank only
    rises with the distance on every map here, so it is never shallower than
    either street it may be on (the deeper of the two, coordinator ruling
    2026-10-14). A piece with no name, or with any street read on no other
    line of this lot, stays unread: the worst case."""
    own = [edge_rank(e, cmap) for e in lines]  # type: ignore[arg-type]
    by_name: dict[str, int] = {}
    for rank, got in zip(own, names):
        if rank is not None and got is not None and len(got) == 1:
            by_name[got[0]] = max(rank, by_name.get(got[0], rank))
    out: list[int | None] = []
    for e, rank, got in zip(lines, own, names):
        if rank is None and got and all(n in by_name for n in got):
            seen = [r for r in _point_ranks(e, cmap) if r is not None]
            rank = max([by_name[n] for n in got] + seen)
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
    #: class -> designation -> distance (``row_to_centerline_by_designation``),
    #: halved like ``classes`` where the code states widths.
    by_designation: Mapping[str, Mapping[str, float]] = dataclasses.field(default_factory=dict)

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

    def standin(
        self,
        classes: Mapping[str, str | None],
        own_zone: str | None,
        across: Sequence[str] | None,
    ) -> float | None:
        """The distance one street line must reach with the land on each side
        read from its ZONE, or None where that cannot be read.

        Oregon City's Table 16.12.016 row turns on "the comprehensive plan
        designation of the adjacent properties", the wider row where the two
        sides differ (16.12.streets.txt#L327-L332). Nothing maps the plan
        designation; Steph ruled 2026-10-14 (FOLLOWUPS 82) that the measured
        zone stands in for it -- the lot's own, and every zone the rays across
        the street found (``across``) -- through Table 17.06.030
        (:data:`DESIGNATIONS`). The answer is the widest row among the sides.
        None -- and so the widest row of the class (:meth:`required`) --
        where the class is unread or has no designation rows, where nothing is
        known of the land across, and where any side's zone maps to no row.
        A code that lists streets by name has no stand-in."""
        if not self.by_designation or self.named or own_zone is None or not across:
            return None
        bucket = classes.get(CLASS_BY_MAP.get(self.class_by or "", ""))
        rows = self.by_designation.get(bucket) if bucket is not None else None
        if not rows:
            return None
        names = DESIGNATIONS.get(self.class_by or "", {})
        sides = [names.get(z) for z in (own_zone, *across)]
        if any(d is None or d not in rows for d in sides):
            return None
        return max(rows[d] for d in sides if d is not None)

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
    if rules.get(WIDTH_FIELD) is True:
        named = [(n, ft / 2.0) for n, ft in named]
    other = _number(rules.get(OTHER_FIELD))
    if not classes and not named and other is None:
        return None
    by = rules.get(CLASS_BY_FIELD)
    rows = _designation_rows(rules.get(DESIGNATION_FIELD))
    if rules.get(WIDTH_FIELD) is True:
        rows = {c: {d: n / 2.0 for d, n in got.items()} for c, got in rows.items()}
    return Rule(
        classes=classes,
        class_by=by if isinstance(by, str) else None,
        named=tuple(named),
        other=other,
        by_designation=rows,
    )


def _designation_rows(table: object) -> dict[str, dict[str, float]]:
    """``row_to_centerline_by_designation`` as class -> designation -> feet.
    A row is ``[class / designation, feet]``, the class spelled as the code
    prints it (``minor arterial``) and keyed as :data:`CLASS_FIELDS` keys it;
    a row whose class is not one of those, or that does not split in two, is
    not read."""
    out: dict[str, dict[str, float]] = {}
    if not isinstance(table, (list, tuple)):
        return out
    for entry in table:
        if not isinstance(entry, (list, tuple)) or len(entry) != 2:
            continue
        ft = _number(entry[1])
        parts = [p.strip().lower() for p in str(entry[0]).split("/")]
        if ft is None or len(parts) != 2:
            continue
        cls = parts[0].replace(" ", "_")
        if cls in CLASS_FIELDS and parts[1]:
            out.setdefault(cls, {})[parts[1]] = ft
    return out


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
    "DESIGNATIONS",
    "DESIGNATION_FIELD",
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
