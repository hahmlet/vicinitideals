"""Driveway spacing from intersections and along busy streets (FOLLOWUPS 169).

Many codes hold a new driveway back from street intersections, and space
driveways along collectors and arterials, by the street's class: Tigard
18.920.030.I wants 150 ft from a collector or arterial intersection and 600 ft
between driveways and streets along an arterial; Tualatin Table 75-1 200 ft
from an arterial or collector intersection; Clackamas County 100 ft from an
arterial. The blind read of 2026-11-09 (fg-rate-B, lot 2S110DB01500) found a
Tigard GREEN whose only frontage is Highway 99W, 270 ft from Naeve St: no new
driveway can go in.

The rules, figures as printed and their stored lines, are in
``flats/config/driveway_spacing.yaml`` (that file's header says how a lot is
answered). This module reads them, and answers each lot one of three ways:

* :data:`CLEAR` -- some street frontage has a stretch where an apron meets
  every rule, with the cross street's half right-of-way taken off where the
  code measures from its right-of-way line and every unread cross street
  taken as the strictest class;
* :data:`BLOCKED` -- every frontage is a street whose rule spaces the
  driveway from existing driveways (no map holds them) or is measured short
  of a rule at every placement, centreline to centreline;
* :data:`UNREAD` -- anything else: a frontage whose class no map reads, a
  geometry the intersections cannot be found on, or a placement between the
  two bounds.

Only CLEAR leaves the lot alone. BLOCKED is YELLOW with a flag, never GREEN
and never RED on this ground alone, whether or not a driveway is there today
(:data:`~flats.score.screen.DRIVEWAY_SPACING_BLOCKED`; Steph 2026-11-09,
rulings.yaml ``2026-11-09-busy-road-driveway-spacing-yellow``: "Yellow with flag", call the city or ODOT about
access). UNREAD is YELLOW too
(:data:`~flats.score.screen.DRIVEWAY_SPACING_UNREAD`).

**Street class.** The frontage street's class is read off the jurisdiction's
TSP map along each frontage edge (the busiest reading wins); a cross street's
off a short line laid beside it just past the intersection. On a map matched
by position that draws only some streets, a street with no TSP line abreast
takes the entry's ``unlisted`` class only where Metro types it a local street
and OpenStreetMap calls it residential, as every other reader of these maps
does (Steph 2026-10-09, "yes, when both agree"); otherwise it is unread.

The maps a rule reads that no other rule does (Clackamas County's road
inventory, Tualatin's street classification) are :data:`SPACING_MAPS`, loaded
apart from :data:`flats.geom.street_class.CLASS_MAPS` so that no corner-lot,
dedication or ``local_street`` reading moves with them.

**Industrial streets.** Cornelius's standards space driveways from an
industrial street as from a busy one (pws.2.streets L3-L4, L7-L9), but no map
classes a street industrial. Where an entry holds ``industrial_streets``, a
street the map reads as neither collector nor arterial is held unread
wherever it may be industrial: any of its lines (by name) within
``reach_ft`` of an industrial district on the city's zoning map
(:class:`IndustrialReach`; coordinator 2026-11-10, never a false GREEN).

**Rules the screen cannot weigh** (FOLLOWUPS 178). A class under an entry's
``unread`` holds every frontage on it unread: its code states a rule nothing
measures there (Gresham's arterial queue length, PWS 6.03; Fairview's
collector and arterial spacing, left to a TSP not held; Sherwood's
Neighborhood Route queues). An intersection rule's ``unread_cross`` names the
cross classes beside which the code adds such a rule (Sherwood's standing
queues at a Neighborhood Route, collector or arterial; Fairview's controlled
intersections): a driveway within :data:`UNREAD_CROSS_REACH_FT` of one, by the
rule's basis, is never shown clear, and never fails on that ground alone.

**Every corner held** (an entry's ``corner_unread``). Fairview sends a
driveway near a controlled intersection (four-way stop or signal) to a TSP
not held, and stop signs are not mapped; Steph ruled every corner lot held,
not only corners by a busier street (rulings.yaml
``2026-11-14-fairview-hold-every-corner``). A lot with two street directions
(a corner, or one street bending: either may be one) is never shown clear
there, and never fails on that ground alone.
"""

from __future__ import annotations

import functools
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from flats.geom.corridor import FRONT_REACH_FT
from flats.geom.durham_apron import (
    _PARALLEL_TOL_DEG,
    CURB_RETURN_ALLOWANCE_FT,
    StreetNetwork,
    _bearing,
    _best_clearance_with_allowances,
    chain_junctions,
    frontage_chains,
)
from flats.geom.edges import Edge, bearing_delta
from flats.geom.street_class import (
    CLASS_MAPS,
    ClassMap,
    ClassSpec,
    edge_rank,
)

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "driveway_spacing.yaml"

CLEAR = "clear"
BLOCKED = "blocked"
UNREAD = "unread"

#: The apron a pass is proved for: not a code figure. Two-way driveway
#: minimums here run 15 to 24 ft; 20 ft (cut to the frontage where shorter,
#: a flag lot's pole) is the conservative middle the screen draws its drive at.
PASS_APRON_FT = 20.0
#: Kept off each end of a frontage on the pass bound (Tualatin 75.020(4)(c)'s
#: 5 ft from the property line; elsewhere conservative).
PASS_INSET_FT = 5.0
#: A cross street's class is read on a line laid from this far along it from
#: the intersection ...
CROSS_FROM_FT = 20.0
#: ... to this far, ...
CROSS_TO_FT = 60.0
#: ... this far off its centreline (inside a lot-line reach).
CROSS_OFFSET_FT = 12.0
#: Shortest frontage edge whose class is read.
MIN_READ_EDGE_FT = 10.0
#: How far, by an intersection rule's basis, a cross street of an
#: ``unread_cross`` class holds a driveway unread: not a code figure. The
#: codes that ask it (a standing queue, a controlled intersection's TSP
#: spacing) print no distance; 150 ft is six queued cars, the conservative
#: reach a corner lot's driveway is judged against (FOLLOWUPS 178).
UNREAD_CROSS_REACH_FT = 150.0

BASES = frozenset({"centreline", "right_of_way_line", "curb_return"})


@dataclass(frozen=True)
class FrontageRule:
    """A street class whose driveways are spaced from other driveways."""

    cls: str
    figure_ft: float | None
    cite: str
    quote: str
    quote_also: str = ""


@dataclass(frozen=True)
class IntersectionRule:
    """A driveway on an ``on`` street held ``figure_ft`` from ``cross`` streets."""

    on: frozenset[str]
    cross: frozenset[str]
    figure_ft: float
    basis: str
    cite: str
    quote: str
    quote_also: str = ""
    #: Cross classes beside which the code adds a rule nothing measures
    #: (a standing queue, a TSP figure not held): see the module docstring.
    unread_cross: frozenset[str] = frozenset()
    unread_cite: str = ""
    unread_quote: str = ""


@dataclass(frozen=True)
class Applies:
    """When the rules reach the pod at all (Washington County's middle housing)."""

    when: str
    busy: frozenset[str]
    cite: str
    quote: str
    quote_also: str = ""


@dataclass(frozen=True)
class CornerHold:
    """A code whose corner rule nothing measures, held on every corner lot
    by a ruling (``corner_unread``): see the module docstring."""

    cite: str
    quote: str
    ruling: str


@dataclass(frozen=True)
class IndustrialStreets:
    """Where a code has industrial streets no map classes: the zoning map
    (registry dataset ``zoning``, its polygons of ``city``) whose
    ``zones`` districts make a street within ``reach_ft`` possibly one."""

    zoning: str
    city_field: str
    city: str
    zones: frozenset[str]
    reach_ft: float
    cite: str
    quote: str
    street_quote: str


@dataclass(frozen=True)
class SpacingRules:
    """One jurisdiction's spacing rules (one entry of the config file)."""

    layer: str
    map: str | None
    classes: Mapping[str, str]
    unlisted: str | None
    frontage: Mapping[str, FrontageRule]
    intersections: tuple[IntersectionRule, ...]
    applies: Applies | None = None
    #: The ruling that lets a map serve a place its registry entry does not
    #: (Cornelius reads Washington County's for busy streets only).
    map_ruling: str | None = None
    #: Industrial streets no map classes (Cornelius); None elsewhere.
    industrial: IndustrialStreets | None = None
    #: Classes whose frontage the code holds to a rule nothing measures
    #: (``figure_ft`` None): every frontage on one is unread.
    unread: Mapping[str, FrontageRule] = field(default_factory=dict)
    #: Every corner lot held unread (Fairview); None elsewhere.
    corner_hold: CornerHold | None = None

    def quotes(self) -> list[tuple[str, float | None, str]]:
        """Every ``(quote, printed figure or None, cite)`` the entry holds."""
        out: list[tuple[str, float | None, str]] = []
        for f in self.frontage.values():
            out.append((f.quote, f.figure_ft, f.cite))
            if f.quote_also:
                out.append((f.quote_also, None, f.cite))
        for r in self.intersections:
            out.append((r.quote, r.figure_ft, r.cite))
            if r.quote_also:
                out.append((r.quote_also, None, r.cite))
            if r.unread_cross:
                out.append((r.unread_quote, None, r.unread_cite))
        for u in self.unread.values():
            out.append((u.quote, None, u.cite))
            if u.quote_also:
                out.append((u.quote_also, None, u.cite))
        if self.applies is not None:
            out.append((self.applies.quote, None, self.applies.cite))
            if self.applies.quote_also:
                out.append((self.applies.quote_also, None, self.applies.cite))
        if self.industrial is not None:
            out.append((self.industrial.quote, None, self.industrial.cite))
            out.append((self.industrial.street_quote, None, self.industrial.cite))
        if self.corner_hold is not None:
            out.append((self.corner_hold.quote, None, self.corner_hold.cite))
        return out

    def class_of_rank(self, rank: int | None, spec: ClassSpec | None) -> str | None:
        """The code's word for a map rank; None where the entry names none."""
        if rank is None or spec is None:
            return None
        if spec.unlisted is not None and rank == spec.unlisted and self.unlisted:
            listed = {self.classes.get(v) for v, r in spec.rank.items() if r == rank} - {None}
            return next(iter(listed)) if listed else self.unlisted
        words = {self.classes[v] for v, r in spec.rank.items() if r == rank and v in self.classes}
        return words.pop() if len(words) == 1 else None

    def strictest_cross(self, on: str) -> float:
        """The largest figure a cross street could carry for a frontage class
        (an ``unread_cross`` rule reaching :data:`UNREAD_CROSS_REACH_FT`)."""
        return max(
            (
                max(r.figure_ft, UNREAD_CROSS_REACH_FT if r.unread_cross else 0.0)
                for r in self.intersections
                if on in r.on
            ),
            default=0.0,
        )


def _frontage_rules(raw: Mapping[str, Any] | None) -> dict[str, FrontageRule]:
    return {
        cls: FrontageRule(
            cls,
            None if v.get("figure_ft") is None else float(v["figure_ft"]),
            str(v["cite"]),
            str(v["quote"]),
            str(v.get("quote_also") or ""),
        )
        for cls, v in (raw or {}).items()
    }


def _parse(layer: str, raw: Mapping[str, Any]) -> SpacingRules:
    frontage = _frontage_rules(raw.get("frontage"))
    unread = _frontage_rules(raw.get("unread"))
    if set(frontage) & set(unread):
        raise ValueError(f"{layer}: a class both barred and unread: {sorted(set(frontage) & set(unread))}")
    rules = []
    for v in raw.get("from_intersections") or ():
        basis = str(v["basis"])
        if basis not in BASES:
            raise ValueError(f"{layer}: unknown basis {basis!r}")
        rules.append(
            IntersectionRule(
                frozenset(v["driveway_on"]),
                frozenset(v["cross"]),
                float(v["figure_ft"]),
                basis,
                str(v["cite"]),
                str(v["quote"]),
                str(v.get("quote_also") or ""),
                frozenset(v.get("unread_cross") or ()),
                str(v.get("unread_cite") or ""),
                str(v.get("unread_quote") or ""),
            )
        )
        if rules[-1].unread_cross and not rules[-1].unread_quote:
            raise ValueError(f"{layer}: unread_cross without unread_quote")
    applies = None
    if raw.get("applies"):
        a = raw["applies"]
        applies = Applies(
            str(a["when"]), frozenset(a["busy"]), str(a["cite"]), str(a["quote"]),
            str(a.get("quote_also") or ""),
        )
    industrial = None
    if raw.get("industrial_streets"):
        i = raw["industrial_streets"]
        industrial = IndustrialStreets(
            str(i["zoning"]), str(i["city_field"]), str(i["city"]), frozenset(i["zones"]),
            float(i["reach_ft"]), str(i["cite"]), str(i["quote"]), str(i["street_quote"]),
        )
    corner_hold = None
    if raw.get("corner_unread"):
        c = raw["corner_unread"]
        corner_hold = CornerHold(str(c["cite"]), str(c["quote"]), str(c["ruling"]))
    return SpacingRules(
        layer=layer,
        map=raw.get("map"),
        classes={str(k): str(v) for k, v in (raw.get("classes") or {}).items()},
        unlisted=raw.get("unlisted"),
        frontage=frontage,
        intersections=tuple(rules),
        applies=applies,
        map_ruling=raw.get("map_ruling"),
        industrial=industrial,
        unread=unread,
        corner_hold=corner_hold,
    )


@functools.lru_cache(maxsize=4)
def load_rules(path: Path = CONFIG_PATH) -> dict[str, SpacingRules]:
    """Every jurisdiction's spacing rules, by layer id."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {layer: _parse(layer, v) for layer, v in (raw.get("jurisdictions") or {}).items()}


def rules_for(layer_id: str | None) -> SpacingRules | None:
    """The spacing rules of one layer, None where it holds none."""
    return load_rules().get(layer_id or "")


#: The maps only these rules read (see the module docstring), by registry
#: dataset. Matched by position: neither layer's names match Metro's
#: spelling, and both draw only some streets.
SPACING_MAPS: dict[str, ClassSpec] = {
    # Clackamas County's road inventory ("Functional Class (RIMS)", as of
    # 2024-07-01): county roads only, the classes of Roadway Standards
    # Table 2-1. State highways and city streets are not drawn.
    "street_class_clackamas": ClassSpec(
        field="Class",
        local=frozenset(),
        other=frozenset(),
        rank={"LOCAL": 0, "CONNECTOR": 1, "COLLECTOR": 2, "MINOR ARTERIAL": 3, "MAJOR ARTERIAL": 4},
        unlisted=0,
        access=False,
    ),
    # Tualatin's street classification (Street Explorer layer 83, edited
    # 2024-12): classified streets only, no local street drawn.
    "street_class_tualatin": ClassSpec(
        field="TYPE",
        local=frozenset(),
        other=frozenset(),
        rank={
            "CONNECTOR COMMERCIAL INDUSTRIAL": 1,
            "CONNECTOR DOWNTOWN CORE": 1,
            "MINOR COLLECTOR": 2,
            "MAJOR COLLECTOR": 2,
            "MINOR ARTERIAL": 3,
            "MAJOR ARTERIAL": 3,
        },
        unlisted=0,
        access=False,
    ),
}


def spec_of(key: str | None) -> ClassSpec | None:
    if not key:
        return None
    return SPACING_MAPS.get(key) or CLASS_MAPS.get(key)


def load_maps(sources: Path, rules: Mapping[str, SpacingRules] | None = None) -> dict[str, ClassMap]:
    """The class maps the rules name, by dataset key; one missing from the
    snapshot is left out, and its lots read unread."""
    from flats.geom.street_class import load_class_maps

    specs = {k: s for k in wanted_maps(rules) if (s := spec_of(k)) is not None}
    if not specs:
        return {}
    return {m.key: m for m in load_class_maps(sources, specs=specs)}


def wanted_maps(rules: Mapping[str, SpacingRules] | None = None) -> tuple[str, ...]:
    """The dataset keys of every map a rule names."""
    rules = load_rules() if rules is None else rules
    return tuple(sorted({r.map for r in rules.values() if r.map}))


def missing(sources: Path) -> tuple[str, ...]:
    """The maps a rule names that the acquire snapshot lacks. Without one a
    whole jurisdiction would read unread (YELLOW), so the bridge refuses the
    snapshot instead (as it does Portland's overlays)."""
    from flats.geom.street_class import _dataset_path

    manifest_path = sources / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    wanted = set(wanted_maps()) | {r.industrial.zoning for r in load_rules().values() if r.industrial}
    return tuple(k for k in sorted(wanted) if not _dataset_path(sources, manifest, k).is_file())


@dataclass(frozen=True)
class IndustrialReach:
    """The street lines that may be industrial streets: every line within
    reach of an industrial district, and every line named as one of them.
    ``everywhere`` where no district could be read, so that every street the
    map reads local is held unread."""

    lines: frozenset[int]
    names: frozenset[str]
    everywhere: bool = False

    def may_be(self, network: StreetNetwork | None, idxs: Sequence[int]) -> bool:
        """Whether any of the lines ``idxs`` may be an industrial street;
        True where there are none (the street is not known)."""
        if self.everywhere or network is None or not idxs:
            return True
        return any(
            i in self.lines or bool(network.names[i] and network.names[i] in self.names)
            for i in idxs
        )


#: Held unread everywhere: no zoning read.
NO_INDUSTRIAL_READ = IndustrialReach(frozenset(), frozenset(), everywhere=True)


def industrial_reach(
    network: StreetNetwork | None, polygons: Sequence[Any] | None, reach_ft: float
) -> IndustrialReach:
    """The lines of ``network`` that may be industrial streets, off the
    industrial districts ``polygons``; :data:`NO_INDUSTRIAL_READ` where the
    zoning was not read (``polygons`` None) or there are no lines."""
    if polygons is None or network is None or network.tree is None:
        return NO_INDUSTRIAL_READ
    hit: set[int] = set()
    for poly in polygons:
        hit.update(int(i) for i in network.tree.query(poly, predicate="dwithin", distance=reach_ft))
    return IndustrialReach(frozenset(hit), frozenset(network.names[i] for i in hit if network.names[i]))


def industrial_polygons(sources: Path, layer_id: str, spec: IndustrialStreets) -> list[Any] | None:
    """The polygons of ``spec.city`` on the zoning map that are an industrial
    district, or carry a code the city's layer neither holds nor has ruled
    on (it may be one). None where the map is missing or draws nothing of
    the city: the zoning is unread."""
    import shapely
    from shapely.geometry import shape

    from flats.geom.street_class import _dataset_path
    from flats.ingest.delta import iter_features
    from flats.ingest.normalize import zone_for
    from flats.ingest.sources import load_pipeline
    from flats.rules.loader import load_rules as load_layers

    manifest_path = sources / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    path = _dataset_path(sources, manifest, spec.zoning)
    ds = load_pipeline().datasets.get(spec.zoning)
    layer = load_layers().get(layer_id)
    if not path.is_file() or ds is None or not ds.zone_field or layer is None:
        return None
    city_key = spec.city_field.lower()
    zone_key = ds.zone_field.lower()
    seen = 0
    out: list[Any] = []
    for feature in iter_features(path):
        props = {str(k).lower(): v for k, v in (feature.get("properties") or {}).items()}
        if str(props.get(city_key) or "").strip().lower() != spec.city.lower():
            continue
        seen += 1
        code, held = zone_for(layer, props.get(zone_key))
        if code is None:
            continue
        if held is None and code in layer.zone_rulings:
            continue  # ruled (a county sliver, a pocket): not the city's district
        if held is not None and held not in spec.zones:
            continue
        raw = feature.get("geometry")
        if not raw:
            continue
        geom = shape(raw)
        if geom.is_empty:
            continue
        out.append(geom if geom.is_valid else shapely.make_valid(geom))
    return out if seen else None


def frontage_lines(chain: Sequence[Edge], network: StreetNetwork | None) -> tuple[int, ...]:
    """The street lines one frontage chain is on: per edge, the nearest
    centreline running alongside it within reach (as
    :func:`~flats.geom.durham_apron.chain_junctions` finds them)."""
    if network is None or network.tree is None:
        return ()
    from shapely.geometry import LineString

    out: set[int] = set()
    for e in chain:
        if e.length_ft < MIN_READ_EDGE_FT:
            continue
        line = LineString(((e.x1, e.y1), (e.x2, e.y2)))
        middle = line.interpolate(line.length / 2.0)
        ranked: list[tuple[float, int]] = []
        for raw in network.tree.query(middle, predicate="dwithin", distance=FRONT_REACH_FT):
            idx = int(raw)
            road = network.geoms[idx]
            bearing = _bearing(road, middle)
            if bearing is None or bearing_delta(e.bearing_deg, bearing) > _PARALLEL_TOL_DEG:
                continue
            ranked.append((float(road.distance(middle)), idx))
        if ranked:
            nearest = min(d for d, _ in ranked)
            out.update(i for d, i in ranked if d <= nearest + 1e-6)
    return tuple(sorted(out))


def line_rank(edge: Sequence[float], cmap: ClassMap) -> int | None:
    """One line's class rank on ``cmap``, read as every lot line is
    (:func:`flats.geom.street_class.edge_rank`): None where its sample
    points disagree or any reads nothing."""
    return edge_rank(edge, cmap)


def chain_class(chain: Sequence[Edge], cmap: ClassMap | None, rules: SpacingRules) -> str | None:
    """The code's class of the street one frontage chain is on; None unread."""
    if cmap is None:
        return None
    spec = spec_of(rules.map)
    ranks: list[int] = []
    for e in chain:
        if e.length_ft < MIN_READ_EDGE_FT:
            continue
        rank = line_rank((e.x1, e.y1, e.x2, e.y2), cmap)
        if rank is None:
            return None
        ranks.append(rank)
    if not ranks:
        return None
    return rules.class_of_rank(max(ranks), spec)


def cross_class(
    network: StreetNetwork, others: Sequence[int], point: tuple[float, float],
    cmap: ClassMap | None, rules: SpacingRules, industrial: IndustrialReach | None = None,
) -> str | None:
    """The class of the street meeting the frontage street at ``point``: each
    crossing line read just past the intersection, both ways, the busiest
    reading winning; None where any leg reads nothing, or where it reads
    neither collector nor arterial and may be an industrial street."""
    if cmap is None:
        return None
    from shapely.geometry import Point

    spec = spec_of(rules.map)
    at_point = Point(point)
    ranks: list[int] = []
    for idx in others:
        road = network.geoms[idx]
        length = float(road.length)
        at = float(road.project(at_point))
        for sign in (1.0, -1.0):
            room = (length - at) if sign > 0 else at
            if room < CROSS_FROM_FT + MIN_READ_EDGE_FT:
                continue
            a = at + sign * CROSS_FROM_FT
            b = at + sign * min(CROSS_TO_FT, room)
            pa = road.interpolate(a)
            pb = road.interpolate(b)
            dx, dy = pb.x - pa.x, pb.y - pa.y
            run = math.hypot(dx, dy)
            if run < MIN_READ_EDGE_FT:
                continue
            nx, ny = -dy / run * CROSS_OFFSET_FT, dx / run * CROSS_OFFSET_FT
            rank = line_rank((pa.x + nx, pa.y + ny, pb.x + nx, pb.y + ny), cmap)
            if rank is None:
                return None
            ranks.append(rank)
    if not ranks:
        return None
    got = rules.class_of_rank(max(ranks), spec)
    if (
        got is not None
        and rules.industrial is not None
        and got not in rules.frontage
        and (industrial or NO_INDUSTRIAL_READ).may_be(network, others)
    ):
        return None
    return got


def _allowance(basis: str, half_width: float) -> float:
    if basis == "centreline":
        return 0.0
    if basis == "right_of_way_line":
        return half_width
    return half_width + CURB_RETURN_ALLOWANCE_FT


def chain_answer(
    length: float,
    junctions: Sequence[tuple[float, float, str | None]],
    on: str,
    rules: SpacingRules,
) -> str:
    """One frontage chain of class ``on``, given its intersections as
    ``(station, cross half-width, cross class or None)``."""
    if on in rules.frontage:
        return BLOCKED
    if on in rules.unread:
        return UNREAD
    applying = [r for r in rules.intersections if on in r.on]
    if not applying:
        return CLEAR
    width = min(PASS_APRON_FT, max(length - 2 * PASS_INSET_FT, 0.0))
    inset = PASS_INSET_FT if length >= PASS_APRON_FT + 2 * PASS_INSET_FT else 0.0
    if width <= 0:
        return UNREAD
    passing: list[tuple[float, float]] = []
    failing: list[tuple[float, float]] = []
    for station, half_width, cross in junctions:
        for r in applying:
            if cross is None or cross in r.cross:
                passing.append((station, r.figure_ft + _allowance(r.basis, half_width)))
            if cross is not None and cross in r.cross:
                failing.append((station, r.figure_ft))
            # A rule the code adds beside a busier cross street and nothing
            # measures: never cleared within reach, never failed on.
            if r.unread_cross and (cross is None or cross in r.unread_cross):
                passing.append((station, UNREAD_CROSS_REACH_FT + _allowance(r.basis, half_width)))
    if not passing:
        return CLEAR
    if _best_clearance_with_allowances(length, passing, width, inset=inset) >= 0.0:
        return CLEAR
    # A driveway centreline anywhere on the frontage, measured to the cross
    # street's centreline: short of the figure everywhere is a miss whatever
    # the basis, since the basis distances are shorter still.
    if failing and _best_clearance_with_allowances(length, failing, 0.0) < 0.0:
        return BLOCKED
    return UNREAD


def read_lot(
    edges_json: str | Sequence[Sequence[object]],
    bearings: Sequence[float],
    network: StreetNetwork | None,
    cmap: ClassMap | None,
    rules: SpacingRules,
    half_widths: Mapping[str, float] | None = None,
    industrial: IndustrialReach | None = None,
) -> tuple[str, str]:
    """``(answer, why)`` for one lot: :data:`CLEAR`, :data:`BLOCKED` or
    :data:`UNREAD`, and a short account per frontage. ``industrial`` says
    where streets may be industrial, for an entry that has such streets
    (every local reading unread where it is missing)."""
    chains = frontage_chains(edges_json, bearings)
    if not chains:
        return UNREAD, "no street frontage read"
    classes = [chain_class(c, cmap, rules) for c in chains]
    maybe_industrial: set[int] = set()
    if rules.industrial is not None:
        reach = industrial or NO_INDUSTRIAL_READ
        for i, (chain, cls) in enumerate(zip(chains, classes)):
            if cls is not None and cls not in rules.frontage and reach.may_be(
                network, frontage_lines(chain, network)
            ):
                classes[i] = None
                maybe_industrial.add(i)
    if rules.applies is not None and rules.applies.when == "every_frontage_busy":
        if len(chains) < 2:
            return CLEAR, "one street frontage: the code's spacing does not reach the pod"
        if any(c is not None and c not in rules.applies.busy for c in classes):
            return CLEAR, "a frontage is not a collector or arterial"
        if None in classes:
            return UNREAD, "a frontage's street class is not read"
        return BLOCKED, "every frontage is a collector or arterial: " + ", ".join(sorted(set(classes)))  # type: ignore[arg-type]
    answers: list[str] = []
    why: list[str] = []
    for i, (chain, cls) in enumerate(zip(chains, classes)):
        if cls is None:
            answers.append(UNREAD)
            why.append("may be an industrial street" if i in maybe_industrial else "street class not read")
            continue
        if cls in rules.frontage:
            answers.append(BLOCKED)
            why.append(f"{cls}: driveways spaced from other driveways")
            continue
        if cls in rules.unread:
            answers.append(UNREAD)
            why.append(f"{cls}: the code's rule here is not measured")
            continue
        if not any(cls in r.on for r in rules.intersections):
            answers.append(CLEAR)
            why.append(f"{cls}: no spacing rule")
            continue
        if network is None:
            answers.append(UNREAD)
            why.append(f"{cls}: no street centrelines")
            continue
        length = sum(e.length_ft for e in chain)
        found = chain_junctions(
            chain,
            network,
            PASS_APRON_FT,
            rules.strictest_cross(cls) + CURB_RETURN_ALLOWANCE_FT,
            half_widths,
        )
        if found is None:
            answers.append(UNREAD)
            why.append(f"{cls}: intersections not read")
            continue
        junctions = [
            (j.station, j.half_width_ft, cross_class(network, j.others, j.point, cmap, rules, industrial))
            for j in found
        ]
        got = chain_answer(length, junctions, cls, rules)
        answers.append(got)
        why.append(f"{cls}: {got} ({len(junctions)} intersection(s) in reach)")
    text = "; ".join(why)
    if CLEAR in answers and rules.corner_hold is not None and len(bearings) >= 2:
        # Two street directions: a corner (or a bend that may be one). The
        # code's controlled-intersection rule is not measured; held by ruling.
        return UNREAD, text + f"; corner lot: {rules.corner_hold.cite} (ruling {rules.corner_hold.ruling})"
    if CLEAR in answers:
        return CLEAR, text
    if all(a == BLOCKED for a in answers):
        return BLOCKED, text
    return UNREAD, text


def half_widths_of(row: Mapping[str, Any]) -> dict[str, float]:
    """The measured half-widths a bridge row holds, by street key (as the
    Durham apron reads them)."""
    from flats.geom.street_class import street_key

    out: dict[str, float] = {}
    try:
        width_rows = json.loads(row.get("road_widths_json") or "[]")
    except (TypeError, ValueError):
        return out
    for width_row in width_rows:
        if not isinstance(width_row, (list, tuple)) or len(width_row) < 7:
            continue
        try:
            half = abs(float(width_row[4]))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(half) or not isinstance(width_row[6], list):
            continue
        for name in width_row[6]:
            key = street_key(name)
            if key:
                out[key] = max(out.get(key, 0.0), half)
    return out


__all__ = [
    "BLOCKED",
    "CLEAR",
    "IndustrialReach",
    "IndustrialStreets",
    "SPACING_MAPS",
    "UNREAD",
    "SpacingRules",
    "chain_answer",
    "load_maps",
    "industrial_polygons",
    "industrial_reach",
    "load_rules",
    "missing",
    "read_lot",
    "rules_for",
]
