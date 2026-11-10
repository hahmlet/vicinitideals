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
"""

from __future__ import annotations

import functools
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from flats.geom.durham_apron import (
    CURB_RETURN_ALLOWANCE_FT,
    StreetNetwork,
    _best_clearance_with_allowances,
    chain_junctions,
    frontage_chains,
)
from flats.geom.edges import Edge
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


@dataclass(frozen=True)
class Applies:
    """When the rules reach the pod at all (Washington County's middle housing)."""

    when: str
    busy: frozenset[str]
    cite: str
    quote: str
    quote_also: str = ""


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
        if self.applies is not None:
            out.append((self.applies.quote, None, self.applies.cite))
            if self.applies.quote_also:
                out.append((self.applies.quote_also, None, self.applies.cite))
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
        """The largest figure a cross street could carry for a frontage class."""
        return max((r.figure_ft for r in self.intersections if on in r.on), default=0.0)


def _parse(layer: str, raw: Mapping[str, Any]) -> SpacingRules:
    frontage = {
        cls: FrontageRule(
            cls,
            None if v.get("figure_ft") is None else float(v["figure_ft"]),
            str(v["cite"]),
            str(v["quote"]),
            str(v.get("quote_also") or ""),
        )
        for cls, v in (raw.get("frontage") or {}).items()
    }
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
            )
        )
    applies = None
    if raw.get("applies"):
        a = raw["applies"]
        applies = Applies(
            str(a["when"]), frozenset(a["busy"]), str(a["cite"]), str(a["quote"]),
            str(a.get("quote_also") or ""),
        )
    return SpacingRules(
        layer=layer,
        map=raw.get("map"),
        classes={str(k): str(v) for k, v in (raw.get("classes") or {}).items()},
        unlisted=raw.get("unlisted"),
        frontage=frontage,
        intersections=tuple(rules),
        applies=applies,
        map_ruling=raw.get("map_ruling"),
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
    return tuple(k for k in wanted_maps() if not _dataset_path(sources, manifest, k).is_file())


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
    cmap: ClassMap | None, rules: SpacingRules,
) -> str | None:
    """The class of the street meeting the frontage street at ``point``: each
    crossing line read just past the intersection, both ways, the busiest
    reading winning; None where any leg reads nothing."""
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
    return rules.class_of_rank(max(ranks), spec)


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
) -> tuple[str, str]:
    """``(answer, why)`` for one lot: :data:`CLEAR`, :data:`BLOCKED` or
    :data:`UNREAD`, and a short account per frontage."""
    chains = frontage_chains(edges_json, bearings)
    if not chains:
        return UNREAD, "no street frontage read"
    classes = [chain_class(c, cmap, rules) for c in chains]
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
    for chain, cls in zip(chains, classes):
        if cls is None:
            answers.append(UNREAD)
            why.append("street class not read")
            continue
        if cls in rules.frontage:
            answers.append(BLOCKED)
            why.append(f"{cls}: driveways spaced from other driveways")
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
            (j.station, j.half_width_ft, cross_class(network, j.others, j.point, cmap, rules))
            for j in found
        ]
        got = chain_answer(length, junctions, cls, rules)
        answers.append(got)
        why.append(f"{cls}: {got} ({len(junctions)} intersection(s) in reach)")
    text = "; ".join(why)
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
    "SPACING_MAPS",
    "UNREAD",
    "SpacingRules",
    "chain_answer",
    "load_maps",
    "load_rules",
    "missing",
    "read_lot",
    "rules_for",
]
