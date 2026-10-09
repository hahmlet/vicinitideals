"""Whether a lot's streets are local streets, read off a city's TSP map.

The registry has carried ``local_street`` since Lake Oswego's street-side
yard was encoded, and nothing answered it: street-side setbacks, driveway
aprons and Villebois's front yard are all written per street class, and the
corpus took the stricter number everywhere and named the fact as the lot's
open question. On 2026-10-04 that question sat on 13,748 Milwaukie answers
and 4,186 in Wilsonville. Both cities publish the map (``street_class_*`` in
``flats/config/pipeline.yaml``); Wilsonville's answers only False, because
the Villebois yards follow the master plan's street classes, not the TSP's
(see :data:`CLASS_MAPS`).

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

**Which street a corner lot's driveway uses** (``corner_access_street:
lowest_class``, FOLLOWUPS 41(i)). The same map ranks each street line
(:func:`edge_rank`, carried as :attr:`flats.geom.edges.Edge.street_rank`).
Until 2026-10-05 the screen read ``lowest_class`` as the side street for
want of a measurement (Steph, 2026-10-02). Steph ruled 2026-10-05: where one
street is quiet and the other busy, the building faces the busy street and
the driveway comes off the quiet side street. Where the code's own front --
the shorter line, say -- is the quiet street, the side street is the busy
one and the code sends the driveway to the front instead
(:func:`measured_access`). A rank can only take the side-street lane away,
never give one, so the ranking needs no second source: a TSP map's "Local
Street" ranks below its "Collector" even where the code reads "local" off
another plan (Villebois).

**A map that draws only the classified streets** (Washington County's TSP
layer: neighbourhood routes and up, no local streets) ranks the street it
does not draw as :attr:`ClassSpec.unlisted` -- but only where Metro types
that street a minor residential one (:data:`RLIS_LOCAL`) and OpenStreetMap
calls it residential too (:data:`OSM_LOCAL`). An absence is not a reading,
so it takes two sources; where they differ, or either is silent, the street
stays unranked and the lot yellow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

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
from flats.geom.edges import BEARING_CLUSTER_TOL_DEG, EdgeClass, LotEdges, bearing_deg, bearing_delta

if TYPE_CHECKING:
    from flats.rules.resolver import ZoneResolution

#: The fact this module answers.
LOCAL_STREET = "local_street"

#: RLIS TYPE codes Metro gives a minor residential street: 1500, and the
#: two unclassified Clackamas variants (named and unnamed, no addresses).
RLIS_LOCAL: frozenset[int] = frozenset({1500, 1550, 1560})

#: The registry dataset holding OpenStreetMap's roads, with ``fclass``.
OSM_ROADS_KEY = "osm_roads"

#: OpenStreetMap ``fclass`` values that call a street residential. ``service``
#: (driveway, aisle, alley) never counts, and ``unclassified`` is a step
#: busier than residential in OpenStreetMap's own order.
OSM_LOCAL: frozenset[str] = frozenset({"residential", "living_street"})


@dataclass(frozen=True)
class ClassSpec:
    """How one city's TSP map spells its classes.

    ``local`` and ``other`` are the field's values verbatim, for the
    ``local_street`` fact; anything else (a proposed street, a blank, a class
    the code's wording does not settle) reads as unknown. ``rank`` orders
    the classes for the lowest-class access rule, 0 the lowest: an order
    within this one map, never compared with another city's. A value it
    leaves out (a proposed street, an unlabelled code) ranks nothing.

    A map that only ranks leaves ``local`` and ``other`` empty, and answers
    no ``local_street``.

    ``unlisted`` is the rank of a street the map does not draw at all, for
    a map that draws only its classified streets; None (every other map):
    an undrawn street is unread.
    """

    field: str
    local: frozenset[str]
    other: frozenset[str]
    rank: Mapping[str, int] = dataclass_field(default_factory=dict)
    unlisted: int | None = None


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
        # MMC 12.16.040.E.3 "the street with the lowest classification":
        # Neighborhood Routes is the TSP's class between the two. (Which
        # side of "local or neighborhood streets" it falls on is another
        # question, and local_street leaves it unanswered.)
        rank={
            "Local Street": 0,
            "Neighborhood Routes": 1,
            "Collector": 2,
            "Arterial": 3,
            "Local Access Arterial": 3,
            "Multimodal Travel Priority Arterial": 3,
            "Through Movement Priority Arterial": 3,
        },
    ),
    # Villebois Table V-1 note 6: "on Collector Avenues" the front yard is
    # 20 and the street side 15. The Collector Avenues are the Villebois
    # Village Master Plan's (Figure 7 Street Plan, 2013), not the TSP's, and
    # the master plan draws a Minor Collector on dozens of streets the TSP
    # map calls Local Street. So the TSP map answers only False here -- a TSP
    # collector or arterial is no local street on either map -- and never
    # True: a TSP local in Villebois may still be a Collector Avenue, and
    # reading it as local would pass a lot at 12 ft that the plan holds at 20.
    "street_class_wilsonville": ClassSpec(
        field="Functional_Class",
        local=frozenset(),
        other=frozenset({"Collector", "Minor Arterial", "Major Arterial"}),
        # PWS 201.2.23(f) "a lower classification street" reads the TSP's
        # classes, and a rank only ever takes a side-street lane away.
        rank={"Local Street": 0, "Collector": 1, "Minor Arterial": 2, "Major Arterial": 3},
    ),
    # The maps below only rank, for ``corner_access_street: lowest_class``
    # (FOLLOWUPS 41(i)); no code of theirs asks local_street.
    #
    # OCMC 16.12.035.H: "access shall be provided from and limited to the
    # road with the lowest classification in the transportation system
    # plan". The two "Unclassified" values (out of the city; "In Area, but
    # not a valid street") rank nothing.
    "street_class_oregon_city": ClassSpec(
        field="FunctionalClass",
        local=frozenset(),
        other=frozenset(),
        rank={
            "Local": 0,
            "Collector": 1,
            "Minor Arterial": 2,
            "Major Arterial": 3,
            "Expressway": 4,
            "Freeway": 4,
        },
    ),
    # CDC 48.025(B)(5): "access shall be provided first from the street
    # with the lowest classification. For example, access shall be provided
    # from a local street before a collector or arterial street." CITYCLASS
    # codes, read off the service's legend: 9 Local, 7 Neighborhood Route,
    # 6 Collector, 5 Minor Arterial, 3 Major Arterial, 1 and 99 Freeway.
    # 11 Alley (the alley rule answers), 20 Misc and 10 (no legend entry)
    # rank nothing.
    "street_class_west_linn": ClassSpec(
        field="CITYCLASS",
        local=frozenset(),
        other=frozenset(),
        rank={"9": 0, "7": 1, "6": 2, "5": 3, "3": 4, "1": 5, "99": 5},
    ),
    # FMC 19.162.020(5): "access shall be provided first from the street
    # with the lowest classification". Fairview's map calls many private
    # roads Local, which ranks them lowest -- the street a driveway may
    # use anyway (the private-drive ruling, 2026-09-30).
    "street_class_fairview": ClassSpec(
        field="FClassification",
        local=frozenset(),
        other=frozenset(),
        rank={
            "Local": 0,
            "Neighborhood Collector": 1,
            "Major Collector": 2,
            "Minor Arterial": 3,
            "Major Arterial": 4,
            "Interstate": 5,
        },
    ),
    # BDC 60.05.60.2 S13.b.1: "lots shall access the street with the lowest
    # functional classification per the city's adopted Transportation
    # System Plan". FUNC_CLASS codes (the layer's own domain): 9 Local,
    # 7 Neighborhood Route, 5 Collector, 3 Arterial, 2 Principal Arterial,
    # 1 Freeway; 4, 6, 8 are Proposed and 10 is NA, and rank nothing.
    "street_class_beaverton": ClassSpec(
        field="FUNC_CLASS",
        local=frozenset(),
        other=frozenset(),
        rank={"9": 0, "7": 1, "5": 2, "3": 3, "2": 4, "1": 5},
    ),
    # Washington County CDC 501-8.5 B is a gate per class, not a "lowest
    # class" sentence, and it comes to the same street: a collector takes
    # direct access only from "commercial, industrial and institutional
    # uses with 150 feet or more of frontage" (B(3)), an arterial only from
    # a collector or another arterial (B(4)), a neighbourhood route only
    # from a use with 70 ft of frontage (B(2)). The county's map draws its
    # classified roads only -- FClass2 5 Neighborhood Route, 4 Collector,
    # 3 Arterial, 2 Principal Arterial, 1 Freeway; 30, 40, 50 Proposed rank
    # nothing -- so a street it leaves out is a local street, where Metro
    # agrees (``unlisted``).
    "street_class_washington": ClassSpec(
        field="FClass2",
        local=frozenset(),
        other=frozenset(),
        rank={"5": 1, "4": 2, "3": 3, "2": 4, "1": 5},
        unlisted=0,
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
    #: Each line's class rank (:attr:`ClassSpec.rank`); None where unranked.
    ranks: tuple[int | None, ...] = ()
    #: :attr:`ClassSpec.unlisted`.
    unlisted: int | None = None
    #: OpenStreetMap's roads and each one's ``fclass``; None where the
    #: snapshot holds none. A street the map leaves out ranks as
    #: :attr:`unlisted` only where these agree with Metro (:func:`_osm_agrees`).
    osm: Lines | None = None
    osm_classes: tuple[str, ...] = ()

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


def class_rank(value: object, spec: ClassSpec) -> int | None:
    """One TSP class value's rank, or None where the spec ranks it not."""
    return spec.rank.get(str(value or "").strip())


def _street_label(props: dict[str, Any]) -> str:
    """``PREFIX STREETNAME FTYPE``; "" where a layer names no street (West
    Linn's), so the line is matched by where it runs, never by an empty
    name."""
    return " ".join(str(props[k]).strip() for k in ("PREFIX", "STREETNAME", "FTYPE") if props.get(k))


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
    ranks: Sequence[int | None] = (),
    unlisted: int | None = None,
    osm: Sequence[Any] = (),
    osm_classes: Sequence[str] = (),
) -> ClassMap:
    """A class map from its parts (what :func:`load_class_maps` reads, and
    what a test draws). ``ranks`` defaults to none; ``osm`` is
    OpenStreetMap's roads, each with its ``fclass`` in ``osm_classes``."""
    keep = [i for i, g in enumerate(lines) if g is not None and not g.is_empty]
    held = Lines.build([lines[i] for i in keep], [names[i] for i in keep])
    road = [i for i, g in enumerate(streets) if g is not None and not g.is_empty]
    osm_ix = [i for i, g in enumerate(osm) if g is not None and not g.is_empty]
    osm_kept = [osm[i] for i in osm_ix]
    ranked = list(ranks) if ranks else [None] * len(lines)
    return ClassMap(
        serves=tuple(serves),
        lines=held,
        kinds=tuple(kinds[i] for i in keep),
        streets=Lines.build([streets[i] for i in road], [street_names[i] for i in road]),
        types=tuple(types[i] for i in road),
        ranks=tuple(ranked[i] for i in keep),
        unlisted=unlisted,
        osm=Lines.build(osm_kept) if osm_kept else None,
        osm_classes=tuple(osm_classes[i] for i in osm_ix),
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
    osm_lines: list[Any] | None = None
    osm_classes: list[str] = []
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
            # A map that draws only its classified streets ranks the streets
            # it leaves out, and those are the ones far from a classified
            # road, so it keeps Metro's whole file (FOLLOWUPS 60).
            if spec.unlisted is None and not g.intersects(zone):
                continue
            p = f.get("properties") or {}
            roads.append(g)
            labels.append(_street_label(p))
            types.append(_type_of(p))
        if spec.unlisted is not None and osm_lines is None:
            osm_lines = []
            osm_path = _dataset_path(sources, manifest, OSM_ROADS_KEY)
            if osm_path.is_file():
                for f in iter_features(osm_path):
                    if f.get("geometry"):
                        osm_lines.append(shape(f["geometry"]))
                        osm_classes.append(str((f.get("properties") or {}).get("fclass") or ""))
        out.append(
            build(
                ds.serves,
                geoms,
                [class_kind(p.get(spec.field), spec) for p in props],
                [_street_label(p) for p in props],
                roads,
                labels,
                types,
                [class_rank(p.get(spec.field), spec) for p in props],
                spec.unlisted,
                osm_lines if spec.unlisted is not None and osm_lines else (),
                osm_classes,
            )
        )
    return tuple(out)


def _beside(point: Any, own: float, cmap: ClassMap) -> tuple[int | None, list[int]]:
    """The RLIS street a lot line abuts at ``point`` (None where none runs
    beside it) and the TSP lines on that street abreast of the point."""
    s = _fronted(point, own, cmap.streets)
    if s is None:
        return None, []
    street, name = cmap.streets.lines[s], cmap.streets.names[s]
    foot = street.interpolate(street.project(point))
    found: list[int] = []
    for i in cmap.lines.near(point, CORRIDOR_REACH_FT):
        line = cmap.lines.lines[i]
        if not _abreast(line, point, own, CORRIDOR_REACH_FT):
            continue
        if (name and name == cmap.lines.names[i]) or line.distance(foot) <= COINCIDE_FT:
            found.append(i)
    return s, found


def _kind_at(point: Any, own: float, cmap: ClassMap) -> str:
    """The class of the street a lot line abuts at ``point``: ``"local"``,
    ``"other"`` or ``""`` (unread)."""
    s, lines = _beside(point, own, cmap)
    found = {cmap.kinds[i] for i in lines}
    if s is None or len(found) != 1:
        return ""
    (kind,) = found
    if kind == "local" and cmap.types[s] not in RLIS_LOCAL:
        return ""
    return kind


def _osm_agrees(point: Any, own: float, s: int, cmap: ClassMap) -> bool:
    """Whether OpenStreetMap also calls the RLIS street ``s`` residential at
    ``point``: some OpenStreetMap road runs abreast of the lot line on that
    street, and every one that does is residential. A busier class there, a
    street with no OpenStreetMap road, or a snapshot without the roads is not
    agreement. ``service`` roads are ignored and never agree on their own."""
    if cmap.osm is None:
        return False
    foot = cmap.streets.lines[s].interpolate(cmap.streets.lines[s].project(point))
    found: set[str] = set()
    for i in cmap.osm.near(point, CORRIDOR_REACH_FT):
        line = cmap.osm.lines[i]
        if line.distance(foot) <= COINCIDE_FT and _abreast(line, point, own, CORRIDOR_REACH_FT):
            found.add(cmap.osm_classes[i])
    found.discard("service")
    return bool(found) and found <= OSM_LOCAL


def _rank_at(point: Any, own: float, cmap: ClassMap) -> int | None:
    """The rank of the street a lot line abuts at ``point``; None where no
    TSP line on it is abreast, or the lines there disagree.

    On a map of the classified streets only (:attr:`ClassMap.unlisted`), a
    street with no TSP line abreast ranks as the undrawn class only where
    Metro types it local AND OpenStreetMap calls it residential (Steph
    2026-10-09: "yes, when both agree"); otherwise it stays unread."""
    s, lines = _beside(point, own, cmap)
    if not lines and s is not None and cmap.unlisted is not None:
        if cmap.types[s] in RLIS_LOCAL and _osm_agrees(point, own, s, cmap):
            return cmap.unlisted
        return None
    found = {cmap.ranks[i] for i in lines}
    if len(found) != 1:
        return None
    return next(iter(found))


def _samples(edge: Sequence[float]) -> tuple[list[Any], float] | None:
    from shapely.geometry import Point

    x1, y1, x2, y2 = (float(v) for v in edge[:4])
    if x1 == x2 and y1 == y2:
        return None
    k = SAMPLES + 1
    points = [Point(x1 + (x2 - x1) * i / k, y1 + (y2 - y1) * i / k) for i in range(1, k)]
    return points, bearing_deg(x1, y1, x2, y2)


def edge_rank(edge: Sequence[float], cmap: ClassMap) -> int | None:
    """One street lot line's class rank, where every sample point reads the
    same one; None otherwise."""
    got = _samples(edge)
    if got is None:
        return None
    points, own = got
    ranks = {_rank_at(p, own, cmap) for p in points}
    return ranks.pop() if len(ranks) == 1 else None


def street_ranks(
    edges: Iterable[Sequence[object]], layer_id: str | None, maps: Sequence[ClassMap]
) -> list[int | None]:
    """:func:`edge_rank` for every s4 edge (``[x1, y1, x2, y2, cls]``), None
    on a line that is not a street or that no map serving the layer reads.
    Two maps serving one layer must agree."""
    serving = [m for m in maps if m.covers(layer_id)]
    out: list[int | None] = []
    for e in edges:
        if not serving or len(e) < 5 or e[4] != STREET_CLASS:
            out.append(None)
            continue
        got = {edge_rank(e, m) for m in serving}  # type: ignore[arg-type]
        out.append(got.pop() if len(got) == 1 else None)
    return out


#: The value :func:`measured_access` puts in ``corner_access_street`` where
#: the code's lowest-class rule, measured, sends the driveway to the front:
#: not one of the field's choices, so nothing reads it as a side street
#: (:data:`flats.score.paper.SIDE_STREET_ACCESS`).
FRONT_ACCESS = "front"


def measured_access(
    rules: "ZoneResolution", edges: LotEdges | None, front: float | None
) -> "ZoneResolution":
    """``rules`` for one named-front plan of a corner lot, with
    ``corner_access_street: lowest_class`` read off the street ranks.

    Where every line on the named front ranks below every line on the side
    street, the lowest-class street is the front and the driveway comes off
    it: the value becomes :data:`FRONT_ACCESS`, the code's own
    ``lowest_class`` kept as ``shadowed``. Everywhere else -- no front
    named, a rank missing on either street, the front the busier or the two
    the same -- ``rules`` comes back unchanged and the side street serves,
    as Steph ruled 2026-10-02.
    """
    import dataclasses

    held = rules.values.get("corner_access_street")
    if front is None or edges is None or held is None or held.value != "lowest_class":
        return rules
    here = [
        e.street_rank
        for e in edges.edges
        if e.cls is EdgeClass.front and bearing_delta(e.bearing_deg, front) <= BEARING_CLUSTER_TOL_DEG
    ]
    side = [e.street_rank for e in edges.edges if e.cls is EdgeClass.street_side]
    if not here or not side or None in here or None in side:
        return rules
    if max(here) >= min(side):  # type: ignore[type-var]
        return rules
    values = dict(rules.values)
    values["corner_access_street"] = dataclasses.replace(held, value=FRONT_ACCESS, shadowed=held.value)
    return dataclasses.replace(rules, values=values)


def unknown_access(
    rules: "ZoneResolution", edges: LotEdges | None, front: float | None
) -> "ZoneResolution | None":
    """The other reading of a ``lowest_class`` corner plan, or ``None``.

    Where the code sends the driveway to the lowest-class street and a street
    line on either the named front or the side street has no rank,
    :func:`measured_access` assumes the side street serves. Nothing says that
    is true: the unmeasured fact takes its worst case (FOLLOWUPS 49(c), Steph
    2026-10-08), so the caller also screens ``rules`` with the driveway off
    the front, which this returns, and keeps the worse of the two.
    """
    import dataclasses

    held = rules.values.get("corner_access_street")
    if front is None or edges is None or held is None or held.value != "lowest_class":
        return None
    here = [
        e.street_rank
        for e in edges.edges
        if e.cls is EdgeClass.front and bearing_delta(e.bearing_deg, front) <= BEARING_CLUSTER_TOL_DEG
    ]
    side = [e.street_rank for e in edges.edges if e.cls is EdgeClass.street_side]
    if not here or not side or (None not in here and None not in side):
        return None
    values = dict(rules.values)
    values["corner_access_street"] = dataclasses.replace(held, value=FRONT_ACCESS, shadowed=held.value)
    return dataclasses.replace(rules, values=values)


def access_record(
    rules: "ZoneResolution", plan_rules: "ZoneResolution", edges: LotEdges | None, front: float | None
) -> dict[str, object]:
    """Which street one plan of a corner lot takes its driveway from, and why.

    ``rules`` is the zone as resolved, ``plan_rules`` the same after
    :func:`measured_access`. Recorded per plan because the drawing holds no
    driveway line (FOLLOWUPS 49(c)): ``rule`` is the code's own value,
    ``access`` the street the screen charged (``front`` or ``side``),
    ``why`` how it came to that, and the street ranks it read.
    """
    held = rules.values.get("corner_access_street")
    rule = None if held is None else held.value
    got = plan_rules.values.get("corner_access_street")
    served = "front" if got is not None and got.value == FRONT_ACCESS else "side"
    here: list[int | None] = []
    side: list[int | None] = []
    if edges is not None and front is not None:
        here = [
            e.street_rank
            for e in edges.edges
            if e.cls is EdgeClass.front
            and bearing_delta(e.bearing_deg, front) <= BEARING_CLUSTER_TOL_DEG
        ]
    if edges is not None:
        side = [e.street_rank for e in edges.edges if e.cls is EdgeClass.street_side]
    if rule != "lowest_class":
        why = "code_names_street" if rule is not None else "unread"
    elif front is None:
        why = "no_front_named"
    elif not here or not side:
        why = "no_street_line"
    elif None in here or None in side:
        why = "rank_missing"
    elif served == "front":
        why = "front_quieter"
    else:
        why = "side_quieter_or_equal"
    return {
        "front_deg": None if front is None else round(front, 2),
        "rule": rule,
        "access": served,
        "why": why,
        "front_ranks": here,
        "side_ranks": side,
    }


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
    "FRONT_ACCESS",
    "LOCAL_STREET",
    "RLIS_LOCAL",
    "ClassMap",
    "ClassSpec",
    "access_record",
    "build",
    "class_kind",
    "class_rank",
    "edge_class",
    "edge_rank",
    "load_class_maps",
    "measured_access",
    "observed_local_street",
    "street_ranks",
    "unknown_access",
]
