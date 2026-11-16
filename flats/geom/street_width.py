"""The street's pavement width in front of a lot, for the crane report only
(FOLLOWUPS 145, Steph 2026-11-15: "A: use the real width data where it
exists. B: estimate the rest, always labelled as estimated").

REPORT ONLY. :mod:`flats.fit.set_access` reads this for the hired 45 t's
street set-up (and the delivery truck at the curb beside it); nothing here
reaches a lot's colour, and the fire hose keeps reading
:mod:`flats.geom.curbs` exactly as before (its four sources, its refusal of
a snapshot that lacks one). Every reading carries where it came from:
``measured:<dataset>`` or :data:`ESTIMATED`.

**Measured** (part A), in the acquire snapshot (``flats/config/pipeline.yaml``):

* **width attributes on a line down the street** -- Portland PBOT
  ``PaveWidth``, Multnomah County ``RoadWidth``, Wilsonville ``Width`` (the
  three the fire hose reads), Washington County ``Width_Rd`` (county roads)
  and Tualatin ``Pav_Width``: read beside the centreline's foot the way
  :meth:`flats.geom.curbs.StreetEdges.width_beside` reads them, the near curb
  half the width off the centreline less its margin, or Portland's drawn
  curb where one is crossed (:meth:`~flats.geom.curbs.StreetEdges.near`);
* **paved shapes** -- Hillsboro's Roadway polygons (public and private
  streets; the parking lots are not fetched): a cut square to the centreline
  at the foot, across the shape, the touching pieces joined, the run that
  holds the centreline taken;
* **edge-of-pavement lines** -- Oregon City's: the same cut, the nearest
  edge crossed either side of the centreline; a width only where BOTH are
  found.

A cut is read at the foot and :data:`ALONG_FT` either way along the
centreline, and the narrowest of those read is the street's there (one of
the two ends may be unread, never the middle): a cut that strays into a
cross street at a corner is long, and the next cut along is not. A cut that
runs out of its :data:`CUT_HALF_FT` on a side (the shape or the edges never
close), is wider than :data:`MAX_PAVE_FT`, or holds the centreline far off
its middle (:func:`_centred`: a parking area or a missing edge on one side)
is unread. Where two sources read the same point, the narrowest governs.

**Estimated** (part B), where nothing measures the point: the right-of-way
-- the gap between the PRIVATE lots either side of the centreline, read
square to it from the foot (the taxlot fabric, as
:mod:`flats.fit.fire_roads` reads it for the fire road widths) -- less a
sidewalk and planter allowance on each side (``street_width`` in
``flats/config/set_access.yaml``, by place: a street standard read in the
place's code, else a stated default marked [est]), then no wider than a
held street-class standard (``cap_ft``). The near curb is the allowance in
from the lot's side of the right-of-way. Unestimated where the right-of-way
does not close within :data:`flats.fit.fire_roads.RAY_FT` on a side (no
facing lot: a park, the edge of the map), where the foot stands on a lot,
where the centreline bends more than :data:`CURVE_DEG` within
:data:`CURVE_RUN_FT` (a curve, a cul-de-sac bulb, a corner), where it is far
off the gap's middle, or where the allowance would leave under
:data:`flats.geom.curbs.MIN_WIDTH_FT` of pavement (a lane with no
sidewalks: the allowance does not describe it).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import shapely
import yaml
from shapely.geometry.base import BaseGeometry

from flats.geom import curbs
from flats.geom.curbs import MIN_WIDTH_FT, StreetEdges, _bearing

#: Line datasets holding a pavement width -> the width field (ft): the fire
#: hose's three and the crane report's two more.
ATTRIBUTE_KEYS: dict[str, str] = {
    **curbs.WIDTH_KEYS,
    "pave_width_washington": "Width_Rd",
    "pave_width_tualatin": "Pav_Width",
}
#: Polygon datasets of paved street shapes.
POLYGON_KEYS: tuple[str, ...] = ("roadway_hillsboro",)
#: Line datasets of pavement edges, not tagged left or right.
EDGE_KEYS: tuple[str, ...] = ("pave_edge_oregon_city",)
#: Every dataset this module reads.
KEYS: tuple[str, ...] = (*curbs.CURB_KEYS, *ATTRIBUTE_KEYS, *POLYGON_KEYS, *EDGE_KEYS)

#: The label of a width read off the right-of-way (part B).
ESTIMATED = "estimated"
#: The prefix of a width read off a source (part A): ``measured:<dataset>``.
MEASURED = "measured"

#: How far either side of the centreline a cut across a shape or the edge
#: lines is read.
CUT_HALF_FT = 60.0
#: A pavement read wider than this is a cut that ran into something else
#: (a cross street, a plaza): unread.
MAX_PAVE_FT = 80.0
#: Cuts are read at the foot and this far either way along the centreline.
ALONG_FT = 10.0
#: Pieces of a cut closer than this are one run (two shapes that touch).
JOIN_FT = 0.5
#: How far the centreline may sit off the middle of what a cut reads, feet
#: or share of the width (the larger): RLIS's centreline strays up to 3.3 ft
#: from the pavement's middle on 95 in 100 Portland points
#: (:data:`flats.geom.curbs.WIDTH_MARGIN_FT`); farther is a cut that took in
#: something on one side.
CENTRE_TOL_FT = 8.0
CENTRE_TOL_SHARE = 0.25
#: A centreline that turns more than this within :data:`CURVE_RUN_FT`
#: either side of the foot is a curve: its right-of-way is not read.
CURVE_DEG = 20.0
CURVE_RUN_FT = 20.0

#: The register of allowances and caps.
CONFIG = Path(__file__).resolve().parents[1] / "config" / "set_access.yaml"


# --------------------------------------------------------------------------
# The estimate's register
# --------------------------------------------------------------------------


#: A right-of-way read within this of a standard section's printed width (or
#: of either end of its printed range) takes that section's pavement. The
#: taxlot fabric places a lot line to about a foot, and the printed
#: sections step by 2 ft or more, so a foot either way reads one width as
#: one section and never as its neighbour.
SECTION_TOL_FT = 1.0
#: Feet in a metre, for a standard printed in metres (Multnomah County).
FT_PER_M = 1.0 / 0.3048
#: The basis of an estimate taken off the stated default.
DEFAULT_BASIS = "no street standard read"


@dataclass(frozen=True)
class Section:
    """One street cross-section a standard prints: its right-of-way (one
    width, or a printed range ``row_lo``-``row_hi``) and its pavement
    (curb to curb; a printed range keeps both ends). The estimate takes
    ``pave_lo``, the narrower end (the cautious pick)."""

    name: str
    row_lo: float
    row_hi: float
    pave_lo: float
    pave_hi: float
    #: Whether the place's derived allowance reads this section (not a
    #: plan district's widened right-of-way, ``row_add``).
    derive: bool = True
    #: An ordinary local street (not a neighbourhood route, ``class:
    #: neighbourhood_route``): what ``unmatched_strip: local_street_strip``
    #: derives the allowance from.
    local: bool = True

    @property
    def tied(self) -> bool:
        """One right-of-way printed with one pavement."""
        return self.row_lo == self.row_hi and self.pave_lo == self.pave_hi


@dataclass(frozen=True)
class EstimateRules:
    """``street_width`` of ``set_access.yaml``: per place, the sidewalk and
    planter allowance taken off EACH side of the right-of-way, the widest
    the estimate may read, and the street cross-sections its standard ties
    to a right-of-way width (``sections``). ``labels`` name where each came
    from (``allowance_ft:<key>``, ``sections:<key>``)."""

    allowance_ft: Mapping[str, float]
    cap_ft: Mapping[str, float] = field(default_factory=dict)
    cites: Mapping[str, str] = field(default_factory=dict)
    sections: Mapping[str, tuple[Section, ...]] = field(default_factory=dict)
    labels: Mapping[str, str] = field(default_factory=dict)

    def _lookup(self, table: Mapping[str, Any], layer: str | None) -> tuple[str | None, Any]:
        path = (layer or "").strip("/")
        while path:
            if path in table:
                return path, table[path]
            path = path.rpartition("/")[0]
        return ("default", table["default"]) if "default" in table else (None, None)

    def allowance(self, layer: str | None) -> float:
        _, v = self._lookup(self.allowance_ft, layer)
        if v is None:
            raise KeyError("street_width.allowance_ft has no default")
        return float(v)

    def cap(self, layer: str | None) -> float | None:
        _, v = self._lookup(self.cap_ft, layer)
        return None if v is None else float(v)

    def allowance_cite(self, layer: str | None) -> str:
        key, _ = self._lookup(self.allowance_ft, layer)
        return self.cites.get(f"allowance_ft:{key}", "")

    def allowance_basis(self, layer: str | None) -> str:
        """What an allowance estimate rests on, for its label: the standard
        (or the stated default) and the allowance a side."""
        key, v = self._lookup(self.allowance_ft, layer)
        label = self.labels.get(f"allowance_ft:{key}")
        if label is None:
            label = DEFAULT_BASIS if key == "default" else str(key)
        est = " [est]" if self.cites.get(f"allowance_ft:{key}", "").startswith("[est]") else ""
        return f"{label}, {round(float(v), 1):g} ft a side{est}"

    def section_pave(self, layer: str | None, row: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """For each right-of-way width: the pavement of the place's standard
        section it matches (the narrowest where several do) and that
        section's label; NaN and "" where none matches."""
        row = np.asarray(row, dtype=float)
        pave = np.full(row.shape, np.nan)
        basis = np.full(row.shape, "", dtype=object)
        key, secs = self._lookup(self.sections, layer)
        if not secs:
            return pave, basis
        std = self.labels.get(f"sections:{key}", str(key))
        for s in secs:
            hit = (row >= s.row_lo - SECTION_TOL_FT) & (row <= s.row_hi + SECTION_TOL_FT) & ~(pave <= s.pave_lo)
            pave[hit], basis[hit] = s.pave_lo, f"{std}, {s.name}"
        return pave, basis


def _span(value: Any, unit: float, where: str) -> tuple[float, float]:
    """A printed figure: a number, or a range "lo-hi", in the place's unit."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) * unit, float(value) * unit
    parts = str(value).replace("–", "-").split("-")
    try:
        nums = [float(p.strip()) for p in parts if p.strip()]
    except ValueError as exc:
        raise ValueError(f"{where}: {value!r} is not a figure") from exc
    if len(nums) not in (1, 2):
        raise ValueError(f"{where}: {value!r} is not a figure")
    return min(nums) * unit, max(nums) * unit


def _figure(entry: Mapping[str, Any], unit: float, where: str) -> float:
    """An allowance or cap: ``value`` (a printed range takes its wider end,
    the cautious one for an allowance), or ``pieces`` summed (each piece's
    wider end)."""
    if entry.get("pieces") is not None:
        return sum(_span(p, unit, where)[1] for p in entry["pieces"])
    if entry.get("value") is not None:
        return _span(entry["value"], unit, where)[1]
    raise ValueError(f"{where}: no value")


def _unit(entry: Mapping[str, Any], where: str) -> float:
    unit = str(entry.get("unit") or "ft")
    if unit not in ("ft", "m"):
        raise ValueError(f"{where}: unit {unit!r}")
    return FT_PER_M if unit == "m" else 1.0


#: How a place's allowance is derived from its sections where it prints none
#: (``street_width.unmatched_strip``): the widest strip a side of every tied
#: section, or of its ordinary local-street sections only (Steph's answer
#: pending, 2026-11-16; widest_strip until then).
STRIP_RULES = ("widest_strip", "local_street_strip")
#: The section classes a row may name (``class:``); absent is ``local``.
SECTION_CLASSES = ("local", "neighbourhood_route")


def rules_from(raw: Mapping[str, Any]) -> EstimateRules:
    """Parse ``street_width``: every figure needs a ``cite``, and every one
    not marked [est] a stored ``quote``. A place with ``sections`` and no
    allowance of its own takes the widest strip a side of its tied sections
    (right-of-way less pavement, halved: the cautious one); with no cap of
    its own, its widest printed pavement. ``unmatched_strip:
    local_street_strip`` derives the strip from the ordinary local-street
    sections only (every tied section where a place marks none local)."""
    sw = raw.get("street_width") or {}
    strip = str(sw.get("unmatched_strip") or STRIP_RULES[0])
    if strip not in STRIP_RULES:
        raise ValueError(f"street_width.unmatched_strip: {strip!r} (one of {', '.join(STRIP_RULES)})")
    tables: dict[str, dict[str, float]] = {"allowance_ft": {}, "cap_ft": {}}
    cites: dict[str, str] = {}
    labels: dict[str, str] = {}
    for name, table in tables.items():
        for key, entry in (sw.get(name) or {}).items():
            where = f"street_width.{name}.{key}"
            if not isinstance(entry, Mapping) or (entry.get("value") is None and entry.get("pieces") is None):
                raise ValueError(f"{where}: no value")
            cite = str(entry.get("cite") or "").strip()
            if not cite:
                raise ValueError(f"{where}: no cite")
            if not cite.startswith("[est]") and not entry.get("quote"):
                raise ValueError(f"{where}: not [est] and no stored quote")
            table[str(key)] = _figure(entry, _unit(entry, where), where)
            cites[f"{name}:{key}"] = cite
            if entry.get("label"):
                labels[f"{name}:{key}"] = str(entry["label"])
    sections: dict[str, tuple[Section, ...]] = {}
    for key, place in (sw.get("sections") or {}).items():
        where = f"street_width.sections.{key}"
        if not isinstance(place, Mapping) or not place.get("standard") or not place.get("rows"):
            raise ValueError(f"{where}: needs a standard and rows")
        unit = _unit(place, where)
        secs = []
        for i, row in enumerate(place["rows"]):
            w = f"{where}.rows[{i}]"
            if not row.get("name") or row.get("row") is None or row.get("pave") is None:
                raise ValueError(f"{w}: needs a name, a row and a pave")
            if not row.get("quote"):
                raise ValueError(f"{w}: no stored quote")
            add = float(row.get("row_add") or 0.0) * unit
            r_lo, r_hi = _span(row["row"], unit, w)
            p_lo, p_hi = _span(row["pave"], unit, w)
            cls = str(row.get("class") or SECTION_CLASSES[0])
            if cls not in SECTION_CLASSES:
                raise ValueError(f"{w}: class {cls!r} (one of {', '.join(SECTION_CLASSES)})")
            secs.append(
                Section(str(row["name"]), r_lo + add, r_hi + add, p_lo, p_hi, derive=not add, local=cls == "local")
            )
        k = str(key)
        sections[k] = tuple(secs)
        std = str(place.get("label") or place["standard"])
        labels[f"sections:{k}"] = std
        tied = [s for s in secs if s.tied and s.derive]
        which = "tied sections"
        if strip == "local_street_strip" and any(s.local for s in tied):
            tied, which = [s for s in tied if s.local], "tied local-street sections"
        if k not in tables["allowance_ft"] and tied:
            tables["allowance_ft"][k] = max((s.row_lo - s.pave_lo) / 2.0 for s in tied)
            cites[f"allowance_ft:{k}"] = f"derived: the widest strip a side of the {which} of {place['standard']}"
            labels[f"allowance_ft:{k}"] = std
        if k not in tables["cap_ft"]:
            tables["cap_ft"][k] = max(s.pave_hi for s in secs)
            cites[f"cap_ft:{k}"] = f"derived: the widest pavement printed in {place['standard']}"
    if "default" not in tables["allowance_ft"]:
        raise ValueError("street_width.allowance_ft needs a default")
    return EstimateRules(tables["allowance_ft"], tables["cap_ft"], cites, sections, labels)


def load_rules(path: Path = CONFIG) -> EstimateRules:
    return rules_from(yaml.safe_load(path.read_text(encoding="utf-8")))


def is_estimated(src: Any) -> np.ndarray:
    """Whether each source label is an estimate (``estimated`` or
    ``estimated:<basis>``)."""
    arr = np.asarray(src, dtype=object)
    out = np.zeros(arr.shape, dtype=bool)
    for i, s in np.ndenumerate(arr):
        out[i] = str(s).startswith(ESTIMATED)
    return out


# --------------------------------------------------------------------------
# Cuts across the street
# --------------------------------------------------------------------------


def _centred(lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """Whether the centreline (t = 0) sits near the middle of [lo, hi]."""
    width = hi - lo
    return np.abs(hi + lo) <= np.maximum(CENTRE_TOL_FT, CENTRE_TOL_SHARE * width)


def _frames(feet: np.ndarray, lines: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """For each foot (N, 2) on its centreline ``lines[i]``: the three cut
    centres (3, N, 2) at the foot and :data:`ALONG_FT` either way along the
    line, and each one's unit normal (3, N, 2); and whether the line bends
    more than :data:`CURVE_DEG` round the foot (N,)."""
    pts = shapely.points(feet)
    at = shapely.line_locate_point(lines, pts)
    length = shapely.length(lines)
    centres, normals = [], []
    for k in (0.0, -ALONG_FT, ALONG_FT):
        c = shapely.line_interpolate_point(lines, np.clip(at + k, 0.0, length))
        deg = np.radians(_bearing(lines, c))
        centres.append(shapely.get_coordinates(c))
        normals.append(np.stack([-np.sin(deg), np.cos(deg)], axis=-1))
    a = shapely.line_interpolate_point(lines, np.clip(at - CURVE_RUN_FT, 0.0, length))
    b = shapely.line_interpolate_point(lines, np.clip(at + CURVE_RUN_FT, 0.0, length))
    turn = np.abs(_bearing(lines, a) - _bearing(lines, b)) % 180.0
    turn = np.minimum(turn, 180.0 - turn)
    return np.stack(centres), np.stack(normals), turn > CURVE_DEG


def _cuts(c: np.ndarray, n: np.ndarray, half: float) -> np.ndarray:
    return shapely.linestrings(np.stack([c - n * half, c + n * half], axis=1))


def _t(c: np.ndarray, n: np.ndarray, xy: np.ndarray) -> np.ndarray:
    return ((xy - c) * n).sum(-1)


def polygon_runs(c: np.ndarray, n: np.ndarray, tree: Any, polys: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Across the paved shapes: for each cut centre ``c`` (M, 2) and normal
    ``n``, the run of pavement holding the centreline, as (lo, hi) along
    the normal from the centre; NaN where unread (module docstring)."""
    m = len(c)
    lo, hi = np.full(m, np.nan), np.full(m, np.nan)
    if tree is None or not m:
        return lo, hi
    cuts = _cuts(c, n, CUT_HALF_FT)
    ci, pi = tree.query(cuts, predicate="intersects")
    if not len(ci):
        return lo, hi
    pieces: dict[int, list[tuple[float, float]]] = {}
    inter = shapely.intersection(cuts[ci], polys[pi])
    for i, g in zip(ci, inter):
        for part in shapely.get_parts(g):
            xy = shapely.get_coordinates(part)
            if len(xy) < 2:
                continue
            t = _t(c[i], n[i], xy)
            pieces.setdefault(int(i), []).append((float(t.min()), float(t.max())))
    edge = CUT_HALF_FT - JOIN_FT
    for i, runs in pieces.items():
        runs.sort()
        merged: list[list[float]] = []
        for a, b in runs:
            if merged and a <= merged[-1][1] + JOIN_FT:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        for a, b in merged:
            if a <= JOIN_FT and b >= -JOIN_FT:
                if a > -edge and b < edge:
                    lo[i], hi[i] = a, b
                break
    return lo, hi


def edge_runs(c: np.ndarray, n: np.ndarray, tree: Any, lines: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Between the edge lines: for each cut, the nearest edge crossed on
    either side of the centreline (lo < 0 < hi); NaN where either side
    finds none within :data:`CUT_HALF_FT`."""
    m = len(c)
    lo, hi = np.full(m, -np.inf), np.full(m, np.inf)
    if tree is None or not m:
        return np.full(m, np.nan), np.full(m, np.nan)
    cuts = _cuts(c, n, CUT_HALF_FT)
    ci, li = tree.query(cuts, predicate="intersects")
    if len(ci):
        inter = shapely.intersection(cuts[ci], lines[li])
        for i, g in zip(ci, inter):
            xy = shapely.get_coordinates(g)
            if not len(xy):
                continue
            t = _t(c[i], n[i], xy)
            pos, neg = t[t > 0], t[t < 0]
            if len(pos):
                hi[i] = min(hi[i], float(pos.min()))
            if len(neg):
                lo[i] = max(lo[i], float(neg.max()))
    bad = ~np.isfinite(lo) | ~np.isfinite(hi)
    lo[bad], hi[bad] = np.nan, np.nan
    return lo, hi


def row_runs(c: np.ndarray, n: np.ndarray, tree: Any, lots: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The right-of-way: for each cut, how far along the normal either way
    the first private lot is entered (lo < 0 < hi); NaN where a side finds
    none within :data:`flats.fit.fire_roads.RAY_FT` or the centre stands on
    a lot (:data:`flats.fit.fire_roads.ON_LOT_FT`)."""
    from flats.fit.fire_roads import ON_LOT_FT, RAY_FT, _first_hit

    m = len(c)
    lo, hi = np.full(m, np.nan), np.full(m, np.nan)
    if tree is None or not m:
        return lo, hi
    left = _first_hit(c, n, RAY_FT, tree, lots)
    right = _first_hit(c, -n, RAY_FT, tree, lots)
    on, _ = tree.query(shapely.points(c), predicate="dwithin", distance=ON_LOT_FT)
    ok = np.isfinite(left) & np.isfinite(right)
    if len(on):
        ok[np.unique(on)] = False
    lo[ok], hi[ok] = -right[ok], left[ok]
    return lo, hi


def _read3(lo: np.ndarray, hi: np.ndarray, n_pts: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Three cuts per point (foot, then either way along): the narrowest
    width read where the foot's cut and at least one more are read, and the
    foot cut's (lo, hi)."""
    lo, hi = lo.reshape(3, n_pts), hi.reshape(3, n_pts)
    w = hi - lo
    ok = np.isfinite(w) & _centred(np.nan_to_num(lo), np.nan_to_num(hi)) & (w <= MAX_PAVE_FT)
    w = np.where(ok, w, np.nan)
    keep = ok[0] & (ok.sum(axis=0) >= 2)
    width = np.where(keep, np.nanmin(np.where(ok, w, np.inf), axis=0), np.nan)
    return width, np.where(keep, lo[0], np.nan), np.where(keep, hi[0], np.nan)


def _near_from_run(side: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> np.ndarray:
    """How far a point at ``side`` (its t on the foot's cut) is from the
    run's edge on its own side."""
    edge = np.where(side >= 0, hi, lo)
    return np.maximum(np.abs(side) - np.abs(edge), 0.0)


# --------------------------------------------------------------------------
# The widths
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class StreetWidths:
    """Every width source of the crane report, indexed, and the taxlot
    fabric for the estimate."""

    #: Drawn curbs and every attribute width in one (the near curb).
    combined: StreetEdges | None = None
    #: Each attribute dataset on its own (which one read a width).
    by_key: Mapping[str, StreetEdges] = field(default_factory=dict)
    polys: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=object))
    poly_key: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=object))
    edges: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=object))
    edge_key: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=object))
    #: The private lots of the taxlot fabric (no right-of-way, no water).
    lots: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=object))
    rules: EstimateRules | None = None
    #: The datasets read, for the run's record.
    keys: tuple[str, ...] = ()
    _poly_tree: Any = field(init=False, repr=False, compare=False, default=None)
    _edge_tree: Any = field(init=False, repr=False, compare=False, default=None)
    _lot_tree: Any = field(init=False, repr=False, compare=False, default=None)

    def __post_init__(self) -> None:
        for name, geoms in (("_poly_tree", self.polys), ("_edge_tree", self.edges), ("_lot_tree", self.lots)):
            if len(geoms):
                object.__setattr__(self, name, shapely.STRtree(geoms))

    def read(
        self, points: np.ndarray, feet: np.ndarray, lines: Sequence[BaseGeometry], layer: str | None = None,
        *, estimate: bool = True,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """For points on street lot lines and the feet of their centrelines
        (``lines[i]``): the distance to the near curb, the pavement width,
        and where it came from (``measured:<dataset>``, :data:`ESTIMATED`,
        or "" where nothing reads it). ``layer`` is the lot's jurisdiction,
        for the estimate's allowance."""
        pts = np.asarray(points, dtype=float).reshape(-1, 2)
        feet = np.asarray(feet, dtype=float).reshape(-1, 2)
        lines = np.asarray(lines, dtype=object)
        n = len(pts)
        curb, width = np.full(n, np.nan), np.full(n, np.nan)
        src = np.full(n, "", dtype=object)
        if not n:
            return curb, width, src
        # Attribute widths: the narrowest, its dataset, the near curb as the
        # fire hose reads it (a drawn curb, or half the width off the line).
        if self.combined is not None:
            near, _ = self.combined.near(pts, feet, lines)
            for key, edges in self.by_key.items():
                w = edges.width_beside(feet, lines)
                take = np.isfinite(w) & ~(w >= width)
                width[take], src[take], curb[take] = w[take], f"{MEASURED}:{key}", near[take]
        need_cuts = self._poly_tree is not None or self._edge_tree is not None or (
            estimate and self._lot_tree is not None and self.rules is not None
        )
        if not need_cuts:
            return curb, width, src
        c3, n3, curved = _frames(feet, lines)
        c, nn = c3.reshape(-1, 2), n3.reshape(-1, 2)
        side = _t(c3[0], n3[0], pts)
        for tree, geoms, keys, runs in (
            (self._poly_tree, self.polys, self.poly_key, polygon_runs),
            (self._edge_tree, self.edges, self.edge_key, edge_runs),
        ):
            if tree is None:
                continue
            lo, hi = runs(c, nn, tree, geoms)
            w, lo0, hi0 = _read3(lo, hi, n)
            take = np.isfinite(w) & ~(w >= width)
            if take.any():
                label = f"{MEASURED}:{keys[0]}" if len(set(keys)) == 1 else MEASURED
                width[take], src[take] = w[take], label
                curb[take] = _near_from_run(side[take], lo0[take], hi0[take])
        if estimate and self._lot_tree is not None and self.rules is not None:
            open_ = ~np.isfinite(width) & ~curved
            if open_.any():
                lo, hi = row_runs(c, nn, self._lot_tree, self.lots)
                row, lo0, hi0 = _read3(lo, hi, n)
                allow = self.rules.allowance(layer)
                est = row - 2.0 * allow
                off = np.full(n, allow)
                basis = np.full(n, self.rules.allowance_basis(layer), dtype=object)
                # A right-of-way the place's standard ties to a section
                # takes that section's pavement, centred in it.
                pave, named = self.rules.section_pave(layer, row)
                hit = np.isfinite(pave)
                est[hit], basis[hit], off[hit] = pave[hit], named[hit], (row[hit] - pave[hit]) / 2.0
                cap = self.rules.cap(layer)
                if cap is not None:
                    est = np.minimum(est, cap)
                take = open_ & np.isfinite(est) & (est >= MIN_WIDTH_FT)
                width[take] = est[take]
                for i in np.flatnonzero(take):
                    src[i] = f"{ESTIMATED}:{basis[i]}"
                curb[take] = _near_from_run(side[take], lo0[take], hi0[take]) + off[take]
        return curb, width, src


def reader(
    widths: StreetWidths, centrelines: np.ndarray, max_gap_ft: float, layer: str | None = None,
    *, estimate: bool = True, tree: Any = None,
) -> Callable[[np.ndarray], tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """A :data:`flats.fit.set_access.StreetReading` for one lot (``layer``
    its jurisdiction): (curb, width, source) at each point on a street lot
    line, read at the foot of its nearest truck centreline
    (:func:`flats.fit.fire.truck_lines`); NaN and "" past ``max_gap_ft``.
    ``tree`` is the centrelines' STRtree where the caller holds one."""
    if tree is None and len(centrelines):
        tree = shapely.STRtree(centrelines)

    def read(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        pts = np.asarray(points, dtype=float).reshape(-1, 2)
        n = len(pts)
        curb, width = np.full(n, np.nan), np.full(n, np.nan)
        src = np.full(n, "", dtype=object)
        if not n or tree is None:
            return curb, width, src
        geoms = shapely.points(pts)
        idx = tree.nearest(geoms)
        lines = centrelines[idx]
        feet = shapely.get_coordinates(shapely.line_interpolate_point(lines, shapely.line_locate_point(lines, geoms)))
        gap = np.hypot(*(feet - pts).T)
        live = np.flatnonzero(gap <= max_gap_ft)
        if len(live):
            c, w, s = widths.read(pts[live], feet[live], lines[live], layer, estimate=estimate)
            curb[live], width[live], src[live] = c, w, s
        return curb, width, src

    return read


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def _find(snapshots: Sequence[Path], key: str) -> Path | None:
    for s in snapshots:
        path = curbs._dataset_path(s, curbs._manifest(s), key)
        if path.is_file():
            return path
    return None


def load(
    snapshots: Sequence[Path], fabric: Path | None = None, rules: EstimateRules | None = None,
) -> StreetWidths:
    """Every source of :data:`KEYS` found in ``snapshots`` (the first that
    holds a dataset gives it), and the private lots of ``fabric`` (quadfit
    s1's whole taxlot file; None: nothing is estimated)."""
    from shapely.geometry import shape

    from flats.ingest.delta import iter_features

    keys: list[str] = []
    curb_geoms: list[BaseGeometry] = []
    for key in curbs.CURB_KEYS:
        path = _find(snapshots, key)
        if path is None:
            continue
        keys.append(key)
        for f in iter_features(path):
            props = f.get("properties") or {}
            if f.get("geometry") and str(props.get("CurbStyle") or "") not in curbs.SKIP_STYLES:
                curb_geoms.append(shape(f["geometry"]))
    every: list[tuple[BaseGeometry, float]] = []
    by_key: dict[str, StreetEdges] = {}
    for key, fld in ATTRIBUTE_KEYS.items():
        path = _find(snapshots, key)
        if path is None:
            continue
        keys.append(key)
        got = []
        for f in iter_features(path):
            w = (f.get("properties") or {}).get(fld)
            if f.get("geometry") and isinstance(w, (int, float)) and math.isfinite(w):
                got.append((shape(f["geometry"]), float(w)))
        by_key[key] = StreetEdges.build((), got, (key,))
        every.extend(got)
    shapes: dict[str, list[BaseGeometry]] = {}
    for group in (POLYGON_KEYS, EDGE_KEYS):
        for key in group:
            path = _find(snapshots, key)
            if path is None:
                continue
            keys.append(key)
            shapes[key] = [shape(f["geometry"]) for f in iter_features(path) if f.get("geometry")]

    def stack(group: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
        g = [x for k in group for x in shapes.get(k, [])]
        k = [k for k in group for _ in shapes.get(k, [])]
        return np.asarray(g, dtype=object), np.asarray(k, dtype=object)

    polys, poly_key = stack(POLYGON_KEYS)
    edges, edge_key = stack(EDGE_KEYS)
    lots = np.zeros(0, dtype=object)
    if fabric is not None:
        import pandas as pd

        from flats.ingest.normalize import NOT_A_TAXLOT_RE

        frame = pd.read_parquet(fabric, columns=["TLID", "wkb"])
        private = ~frame["TLID"].astype(str).str.contains(NOT_A_TAXLOT_RE.pattern, regex=True).to_numpy()
        lots = shapely.from_wkb(frame.loc[private, "wkb"].to_numpy())
        keys.append(f"fabric:{fabric.name}")
    combined = StreetEdges.build(curb_geoms, every, tuple(keys)) if (curb_geoms or every) else None
    return StreetWidths(
        combined=combined, by_key=by_key, polys=polys, poly_key=poly_key, edges=edges, edge_key=edge_key,
        lots=lots, rules=rules if rules is not None else (load_rules() if fabric is not None else None),
        keys=tuple(keys),
    )


__all__ = [
    "ALONG_FT",
    "ATTRIBUTE_KEYS",
    "CUT_HALF_FT",
    "EDGE_KEYS",
    "ESTIMATED",
    "EstimateRules",
    "FT_PER_M",
    "SECTION_CLASSES",
    "SECTION_TOL_FT",
    "STRIP_RULES",
    "Section",
    "KEYS",
    "MAX_PAVE_FT",
    "MEASURED",
    "POLYGON_KEYS",
    "StreetWidths",
    "edge_runs",
    "is_estimated",
    "load",
    "load_rules",
    "polygon_runs",
    "reader",
    "row_runs",
    "rules_from",
]
