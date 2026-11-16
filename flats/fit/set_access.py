"""Set access: which crane can set the pod on this lot, and how (FOLLOWUPS
145, slices 3-4b, Steph 2026-11-14/15).

A REPORT, NOT A SCREEN CHECK. Nothing here reaches the colour, a reason
code, a flag or the bound (Steph 2026-11-14: "Don't flag any lots by color
yet"). :func:`report` answers one lot; ``scripts/flats_set_access_sample.py``
runs it over a sample of a finished bridge run.

For one lot with the pod already placed by the screen (the drawing's
building, :mod:`flats.fit.draw`), Steph's site viability rule (crane spec
S3e section 5, ``flats/config/set_access.yaml``) is followed in order; the
first step that passes is the answer:

1. **IC-80 one face.** The owned Broderson IC-80-3H carry-deck crane drives
   up beside the building and sets every piece from one long face, front or
   back. Checked: a working strip ~10 ft wide along the whole face with the
   outrigger footprint at the crane line (centre 7 ft off the face) on open
   ground in the lot; LEVEL ONLY AT THE SET-UP SPOTS (slice 4, spec 3.9):
   the ground under each spot's outrigger footprint within ~3%, a lift set
   only from such spots; swing room 12 ft beyond each wall end inside the
   lot; trees (a canopy map, where one is read) clear of the swing room,
   the working ground and any carry path; each trailer load parked on the
   lot, or IN THE STREET along the frontage (placed from the street lot
   line and centreline, the curb ignored), so every piece on it is within
   the IC-80's reach of a crane spot that also sets it -- or else picked
   at the trailer and CARRIED on rubber to a set-up spot (spec 3.7 at
   9985b64: cassettes flat and crosswise on a ~27 ft path, walls upright
   on a 6 ft 6 in path, walls flat only behind ``walls_flat_crosswise``;
   the route's fall costs ~3 chart points per 1%); a way in 6 ft 6 in
   wide, 9 ft 6 in at turns; and every lift
   within 75% of the chart and the hook height it needs.
2. **IC-80 both faces.** The same with a strip on both long faces; far
   walls are then set from their own face.
3. **45 t on site, then 45 t in the street** (the hired NBT45-2, slice 2's
   solver retuned to spec section 4): a 28 x 42 ft pad the truck drives to
   straight, or a street pad where the recorded pavement width holds it;
   every piece within ~80 ft; each whole trailer load lifted off and landed
   where the trailer stood (Steph 2026-11-14), within ~35 ft (wall stacks) or
   ~50 ft (cassette stacks) of the crane; the pad level within 1%.
4. **Not viable** where every step fails; **unmeasured** where none passes
   and one could not be decided.

Overhead power lines are NOT checked, for either crane (Steph 2026-11-14: a
later job). Every set-up says "power lines not checked". The other things
no plan checks are listed in :data:`NOT_CHECKED` on every report.

Pure geometry and arithmetic: shapely and numpy, no database, nothing from
:mod:`app`. Coordinates are the lot's working CRS (EPSG:2913, feet).
"""

from __future__ import annotations

import dataclasses
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

import numpy as np
import shapely
import yaml
from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry

RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "set_access.yaml"

Status = Literal["pass", "fail", "unmeasured"]
PASS: Status = "pass"
FAIL: Status = "fail"
UNMEASURED: Status = "unmeasured"
#: A step the ladder never reached (an earlier one passed).
NOT_TRIED = "not tried"
_ORDER = {PASS: 0, UNMEASURED: 1, FAIL: 2}

#: How far into the street the crane or truck is taken to have arrived: a
#: point this far past a street lot line is on the street.
APRON_FT = 30.0
#: Geometry slack, feet.
EPS = 1e-6
#: 45 t access answers.
STRAIGHT = "straight"
BENDS = "bends"
NONE = "none"
#: Said on every set-up, both cranes (Steph 2026-11-14).
POWER_NOTE = "power lines not checked"
#: Spec 3.10 at 9985b64 (1926.1411(a): a crane travelling with a load is
#: lifting, so 1926.1408 applies): reported where a plan carries or uses a
#: street trailer, never checked (FLATS holds no power-line data).
CARRY_POWER_NOTE = (
    "a loaded carry is a lift (spec 3.10, OSHA 1926.1411(a)): boom, rigging and load {ft:g} ft from any power "
    "line, or 10 ft with the utility's <=50 kV confirmation, so no loaded carry under a line unless the "
    "utility de-energises and grounds it: power lines not checked"
)
STREET_POWER_NOTE = (
    "street trailer: with a power line on the lot's side of the street, no pick off a trailer under it and no "
    "loaded carry under it (spec 3.10); it then needs (1) the truck onto the lot, parked clear of the line, "
    "(2) the line on the far side of the street or in a rear easement, the trailer at the near kerb, (3) the "
    "wire a phone or cable line (not a power line, 1926.1401), or (4) the utility de-energising and grounding "
    "it (covered only still counts as live): power lines not checked"
)
#: What no plan checks (said on every report).
NOT_CHECKED: tuple[str, ...] = (
    "overhead power lines (both cranes)",
    "ground firm and drained; what the mats bear",
    "trees, where no canopy map is read (a canopy map shows crowns, not trunks or heights)",
    "the ground between the IC-80's set-up spots (firm and drivable for the empty crane)",
    "a carried load's sweep on a turn; the carry distance and time on the cargo deck",
    "a carry route firm and even (spec 3.7: no ruts over ~1 in, no bumps or kerbs over ~2 in; mats or gravel "
    "where soft); which way along it the load faces (taken downhill)",
    "where the street may be closed for the trailer or the IC-80 (street-use permit)",
    "room in the street for the IC-80 beside a street trailer (it picks there on rubber)",
    "how close the IC-80's pads may stand to the new slab edge (FOLLOWUPS 220)",
    "the wall rigging (not designed, FOLLOWUPS 215; taken as 400 lb unless a wall-gear case is named)",
    "other buildings and walls on the lot",
    "whether the IC-80's way in bears ~17,600 lb",
    "the 45 t's and the trailer's turning paths",
)

#: The answers, in the viability order (spec section 5).
IC80_ONE = "IC-80 one face"
IC80_BOTH = "IC-80 both faces"
T45_SITE = "45 t on site"
T45_STREET = "45 t in the street"
#: The 45 t's street set-up where the width (or the curb the truck stands
#: at) is estimated off the right-of-way (FOLLOWUPS 145 part B).
T45_STREET_EST = "45 t in the street (width estimated)"
#: A delivery-truck spot at a curb placed off an estimated width.
CURB_EST = "curb (est)"
NOT_VIABLE = "not viable"
UNMEASURED_ANSWER = "unmeasured"

#: Step keys, in order.
STEPS: tuple[str, ...] = (
    "ic80_front",
    "ic80_back",
    "ic80_both",
    "45t_site",
    "45t_street",
)


# --------------------------------------------------------------------------
# Printed figures
# --------------------------------------------------------------------------

_FT_IN = re.compile(r"""^\s*(?:(\d+(?:\.\d+)?)\s*')?\s*(?:(\d+(?:\.\d+)?)\s*")?\s*$""")
_FT_IN_WORDS = re.compile(
    r"^\s*(?:(\d+(?:\.\d+)?)\s*ft)?\s*(?:(\d+(?:\.\d+)?)\s*in)?\s*$"
)


def _length(token: str) -> float:
    """One printed length, feet: ``40`` (bare = feet), ``8'1"``, ``15.5"``,
    ``8 ft 6 in``, ``100.3 in``."""
    t = token.strip().replace("~", "")
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        return float(t)
    for pattern in (_FT_IN, _FT_IN_WORDS):
        m = pattern.match(t)
        if m and (m.group(1) is not None or m.group(2) is not None):
            return float(m.group(1) or 0.0) + float(m.group(2) or 0.0) / 12.0
    raise ValueError(f"not a printed length: {token!r}")


def parse_range(text: Any) -> tuple[float, float]:
    """A printed length or range: ``4'-4'3.5"`` -> (4.0, 4.29);
    ``5 ft 4 in-5 ft 11 in`` -> (5.33, 5.92); ``~10`` -> (10, 10)."""
    t = str(text).strip()
    parts = re.split(r"(?<=['\"\dn])\s*-\s*(?=[\d~])", t)
    if len(parts) == 1:
        v = _length(parts[0])
        return v, v
    if len(parts) != 2:
        raise ValueError(f"not a printed range: {text!r}")
    lo, hi = _length(parts[0]), _length(parts[1])
    return min(lo, hi), max(lo, hi)


def _hi_len(text: Any) -> float:
    return parse_range(text)[1]


def parse_size(text: str | None) -> tuple[tuple[float, float], ...] | None:
    """``25 x 8 ft 6 in`` -> ((25, 25), (8.5, 8.5)); None for None."""
    if text is None:
        return None
    t = re.sub(r"\s*ft\s*$", "", str(text).strip())
    return tuple(parse_range(p) for p in re.split(r"\s+x\s+", t))


def parse_weight(text: Any) -> tuple[float, float] | None:
    """``"12,074"`` -> (12074, 12074); ``"556-723"``; ``"~4,100"``; None."""
    if text is None:
        return None
    t = str(text).replace(",", "").replace("~", "").strip()
    parts = [float(p) for p in t.split("-")]
    if len(parts) not in (1, 2):
        raise ValueError(f"not a printed weight: {text!r}")
    return min(parts), max(parts)


def _hi(text: Any) -> float:
    got = parse_weight(text)
    if got is None:
        raise ValueError("a printed weight is required here")
    return got[1]


# --------------------------------------------------------------------------
# Charts
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Reading:
    """What a chart says at one radius: the row read and its capacity."""

    capacity_lb: float
    row_ft: float | None
    boom_ft: float | None


@dataclass(frozen=True, slots=True)
class Chart:
    """One crane configuration's load chart, as printed."""

    key: str
    source: str
    #: Taken off every figure (a stowed extension or jib).
    deductions_lb: float
    max_pct: float
    #: ((boom_ft, ((radius_ft, capacity_lb), ...)), ...), radius rising.
    booms: tuple[tuple[float, tuple[tuple[float, float], ...]], ...]

    def read(self, radius_ft: float) -> Reading | None:
        """The rated capacity at ``radius_ft``: the best boom column's NEXT
        LONGER listed radius, never interpolated, less the deductions. 0 past
        every column's last radius; None where the radius is inside every
        column's first one (the chart says nothing)."""
        best: Reading | None = None
        for boom, rows in self.booms:
            if radius_ft < rows[0][0] - EPS:
                continue
            got = Reading(0.0, None, None)
            for r, c in rows:
                if r >= radius_ft - EPS:
                    got = Reading(max(c - self.deductions_lb, 0.0), r, boom)
                    break
            if best is None or got.capacity_lb > best.capacity_lb:
                best = got
        return best

    def capacity_at(self, radius_ft: float) -> float | None:
        got = self.read(radius_ft)
        return None if got is None else got.capacity_lb

    def capacities(self, radii: np.ndarray) -> np.ndarray:
        """:meth:`capacity_at` over an array; NaN where the chart says
        nothing."""
        radii = np.asarray(radii, dtype=float)
        out = np.full(radii.shape, np.nan)
        for _, rows in self.booms:
            rr = np.array([r for r, _ in rows])
            cc = np.maximum(np.array([c for _, c in rows]) - self.deductions_lb, 0.0)
            idx = np.searchsorted(rr, radii - EPS, side="left")
            cap = np.where(idx < len(rr), cc[np.minimum(idx, len(rr) - 1)], 0.0)
            cap = np.where(radii >= rr[0] - EPS, cap, np.nan)
            out = np.where(np.isnan(out), cap, np.where(np.isnan(cap), out, np.maximum(out, cap)))
        return out

    def radii(self) -> list[float]:
        return sorted({r for _, rows in self.booms for r, _ in rows})

    def reach_for(self, gross_lb: float, ok: Callable[[float], bool] | None = None) -> float | None:
        """The longest listed radius out to which ``gross_lb`` stays within
        the planning line at every listed radius (and ``ok``); None where it
        is nowhere."""
        far: float | None = None
        for r in self.radii():
            cap = self.capacity_at(r)
            if cap is None:
                continue
            if cap * self.max_pct / 100.0 >= gross_lb - EPS and (ok is None or ok(r)):
                far = r
            elif far is not None:
                break
        return far


def _chart(key: str, source: str, booms_raw: Sequence[Mapping[str, Any]], deduct: float, pct: float) -> Chart:
    booms: list[tuple[float, tuple[tuple[float, float], ...]]] = []
    for col in booms_raw:
        rows = tuple(sorted((float(r), float(c)) for r, c in col["rows"]))
        if not rows:
            raise ValueError(f"chart {key}: a boom column with no rows")
        for (_, a), (_, b) in zip(rows, rows[1:]):
            if b > a + EPS:
                raise ValueError(f"chart {key}: capacity rises with radius")
        booms.append((float(col["boom_ft"]), rows))
    if not booms:
        raise ValueError(f"chart {key}: no boom columns")
    return Chart(key=key, source=source, deductions_lb=deduct, max_pct=pct, booms=tuple(booms))


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Piece:
    key: str
    label: str
    count: int | None
    weight_lb: float
    #: front_wall / back_wall / end_wall / party_wall / centreline.
    place: str
    #: The IC-80 stands ``along_ft`` along the face from the piece's line.
    points_at_crane: bool
    #: The hook height the piece needs, feet.
    hook_ft: float
    #: wall / cassette / bundle.
    group: str
    #: Half the printed width: how far a centreline piece's centre stands in
    #: from the pod's end (0 where no width is printed).
    inset_ft: float = 0.0
    #: The printed plan (long, short), LOW ends; 0 where not printed.
    plan_ft: tuple[float, float] = (0.0, 0.0)
    #: The trailer load(s) it rides (spec 3.4's "Load" column).
    loads: tuple[int, ...] = (1,)
    #: The printed short side, HIGH end (a cassette carried flat sweeps
    #: this wide); 0 where not printed.
    short_hi_ft: float = 0.0


@dataclass(frozen=True, slots=True)
class WholeLoad:
    key: str
    label: str
    stack_lb: float
    length_ft: float
    landing_ft: tuple[float, float]
    within_ft: float


@dataclass(frozen=True, slots=True)
class IC80:
    """The Broderson IC-80-3H, as printed in spec section 3."""

    label: str
    body_w_ft: float
    weight_lb: float
    out_w_ft: float
    out_l_ft: float
    route_w_ft: float
    route_turn_w_ft: float
    hook_lb: float
    rigging_lb: float
    #: Set lifts: 360 deg on outriggers, the extension up (rows to 40 ft).
    set_chart: Chart
    #: Carrying: over the front on rubber, the extension taken off (rows to
    #: 30 ft).
    carry_chart: Chart
    #: The same rows on the 360 deg on-rubber column: read where the route
    #: falls across more than ``carry_cross_pct`` (spec 3.7).
    carry_chart_360: Chart
    stowed_deduct_lb: float
    #: Hook height table, with the extension up: radii and heights.
    hook_radii: tuple[float, ...]
    hook_heights: tuple[float | None, ...]
    min_radius_ft: float
    off_face_ft: float
    along_ft: float
    strip_w_ft: float
    swing_ft: float
    #: The fall across one set-up spot's pads (spec 3.9, ~3%).
    level_pct: float
    carry_radius_ft: Mapping[str, float]
    container_sling_lb: float
    container_within_ft: float
    #: Steph 2026-11-14: the IC-80 may stand in the street for the
    #: container lift (that lift only).
    container_street: bool = False
    #: The walls' rigging (spec 3.6: "The wall rigging is not designed");
    #: None = ``rigging_lb``. The sample runs each of ``wall_gear_lb``.
    wall_rigging_lb: float | None = None
    wall_gear_lb: Mapping[str, float] = field(default_factory=dict)
    #: Slice 4b (spec 3.7 at 9985b64): walls carried flat and crosswise
    #: hang on FOLLOWUPS 215(a); off by default.
    carry_walls_flat: bool = False
    #: The share of the chart a carried load loses per 1% downhill fall of
    #: its route (spec 3.7; the crane agent 2026-11-15: "usable chart =
    #: chart x (1 - 0.03 x downhill %)").
    carry_slope_per_pct: float = 0.03
    #: Past this cross fall the 360 deg on-rubber column is read (spec 3.7:
    #: "At ~3% the wall carry uses up the +-2 deg straight-ahead allowance").
    carry_cross_pct: float = 3.0
    #: Carry path widths (spec 3.7): an upright wall edge-on, and a panel
    #: flat and crosswise.
    carry_w_ft: float = 6.5
    carry_cross_w_ft: float = 27.0
    #: Spec 3.10: carrying under a line needs this clearance (reported,
    #: never checked).
    carry_power_ft: float = 20.0

    def rigging_for(self, piece: Piece) -> float:
        if piece.group == "wall" and self.wall_rigging_lb is not None:
            return self.wall_rigging_lb
        return self.rigging_lb

    def hook_at(self, radius_ft: float) -> float | None:
        """Hook height at ``radius_ft``: the next longer listed radius's (the
        lower hook); None inside the first or past the last listed radius."""
        if radius_ft < self.hook_radii[0] - EPS:
            return None
        for r, h in zip(self.hook_radii, self.hook_heights):
            if r >= radius_ft - EPS:
                return h
        return None

    def reach(self, gross_lb: float, hook_needed_ft: float) -> float | None:
        """The longest radius out to which a set lift of ``gross_lb`` stays
        within the planning line and the hook still reaches
        ``hook_needed_ft``."""

        def hook_ok(r: float) -> bool:
            h = self.hook_at(r)
            return r >= self.min_radius_ft - EPS and h is not None and h >= hook_needed_ft - EPS

        far: float | None = None
        for r in self.set_chart.radii():
            if r < self.min_radius_ft - EPS:
                continue
            cap = self.set_chart.capacity_at(r) or 0.0
            if cap * self.set_chart.max_pct / 100.0 >= gross_lb - EPS and hook_ok(r):
                far = r
            else:
                break
        return far

    def pick_reach(self, gross_lb: float) -> float | None:
        """The longest radius out to which a pick of ``gross_lb`` off the
        trailer stays within the planning line, from the least radius. Spec
        3.4: "a piece only has to clear the rest of its stack ..., so hook
        height does not limit the pick off the trailer"."""
        return self.set_chart.reach_for(gross_lb, lambda r: r >= self.min_radius_ft - EPS)

    @property
    def outer_ft(self) -> float:
        """How far off the face the working ground reaches: the strip, or
        the outrigger footprint at the crane line if wider."""
        return max(self.strip_w_ft, self.off_face_ft + self.out_w_ft / 2)


@dataclass(frozen=True, slots=True)
class Crane45:
    """The hired 45 t National NBT45-2, as printed in spec section 4."""

    label: str
    short: str
    body_w_ft: float
    pad_w_ft: float
    pad_l_ft: float
    rotation_offset_ft: tuple[float, float]
    ball_lb: float
    rigging_lb: float
    #: Whole loads: the lifting frame and the spreader (the hook is added by
    #: :meth:`whole_gross`).
    whole_rigging_lb: float
    max_piece_radius_ft: float
    level_pct: float
    chart: Chart
    single_line_lb: float = math.inf
    block_lb: float = 0.0
    container_sling_lb: float = 0.0

    def whole_gross(self, stack_lb: float) -> float:
        """Spec 4.5: stack + frame + spreader + the hook: the ball, or the
        one-sheave block where that is over the single-line limit."""
        with_ball = stack_lb + self.whole_rigging_lb + self.ball_lb
        if with_ball > self.single_line_lb + EPS:
            return stack_lb + self.whole_rigging_lb + self.block_lb
        return with_ball


@dataclass(frozen=True, slots=True)
class Rules:
    ic80: IC80
    t45: Crane45
    pieces: tuple[Piece, ...]
    whole_loads: tuple[WholeLoad, ...]
    container_label: str
    container_fp: tuple[float, float]
    container_lb: float
    deck_l_ft: float
    truck_w_ft: float
    places: tuple[str, ...]
    max_pct: float
    homes: int
    pad_grid_ft: float
    pad_angle_step_deg: float
    spot_grid_ft: float
    spot_angle_step_deg: float
    pads_kept: int
    pads_graded: int
    street_step_ft: float
    crane_step_ft: float
    deck_step_ft: float
    #: Where the IC-80's trailer may stand (slice 4): ``lot`` / ``street``.
    ic80_places: tuple[str, ...] = ("lot", "street")

    def piece(self, key: str) -> Piece:
        for p in self.pieces:
            if p.key == key:
                return p
        raise KeyError(key)


def _plan(size: tuple[tuple[float, float], ...] | None) -> tuple[float, float]:
    """A piece's printed plan (long, short), LOW ends (the least it can be,
    so its centre may stand as near the deck's edge as it can); 0 for a side
    not printed."""
    if not size:
        return 0.0, 0.0
    dims = sorted((lo for lo, _ in size), reverse=True)
    return dims[0], dims[1] if len(dims) > 1 else 0.0


def _fp(text: str) -> tuple[float, float]:
    """A plan footprint (long, short) from a printed size, HIGH ends."""
    size = parse_size(text)
    if not size or len(size) < 2:
        raise ValueError(f"a plan size needs two dimensions: {text!r}")
    dims = sorted((hi for _, hi in size), reverse=True)
    return dims[0], dims[1]


def _ic80(raw: Mapping[str, Any], pct: float) -> IC80:
    ch = raw["chart"]
    cols = list(ch["columns"])
    rows = [list(r) for r in ch["rows"]]
    stowed = float(ch["extension_stowed_deduct_lb"])
    ext_from = float(ch["extension_rows_from_ft"])

    def column(name: str, max_r: float | None) -> list[list[float]]:
        j = cols.index(name) + 1
        return [[r[0], r[j]] for r in rows if max_r is None or r[0] < max_r - EPS]

    src = str(ch.get("source", ""))
    set_chart = _chart("ic80_set", src, [{"boom_ft": 40, "rows": column(raw["set_column"], None)}], 0.0, pct)
    # Carrying: no load on the extension; taken off, so only the main
    # boom's rows (below the extension rows) and no deduction.
    carry_chart = _chart("ic80_carry", src, [{"boom_ft": 30, "rows": column(raw["carry_column"], ext_from)}], 0.0, pct)
    carry_360 = _chart("ic80_carry_360", src, [{"boom_ft": 30, "rows": column(raw["carry_column_cross"], ext_from)}],
                       0.0, pct)
    hook = raw["hook_height_ft"]
    out = raw["outriggers"]
    site = raw["site"]
    carry = raw["carry"]
    return IC80(
        label=raw["label"],
        body_w_ft=_hi_len(raw["body"]["width"]),
        weight_lb=_hi(raw["weight_lb"]),
        out_w_ft=_hi_len(out["spread"]),
        out_l_ft=2 * max(_hi_len(out["ahead"]), _hi_len(out["behind"])),
        route_w_ft=_hi_len(site["route_width"]),
        route_turn_w_ft=_hi_len(site["route_width_at_turns"]),
        hook_lb=float(raw["hook_lb"]),
        rigging_lb=_hi(raw["rigging_lb"]),
        set_chart=set_chart,
        carry_chart=carry_chart,
        carry_chart_360=carry_360,
        stowed_deduct_lb=stowed,
        hook_radii=tuple(float(r) for r in hook["radius"]),
        hook_heights=tuple(None if h is None else float(h) for h in hook["with_extension_40"]),
        min_radius_ft=_hi_len(raw["min_radius_ft"]["with_extension"]),
        off_face_ft=_hi_len(raw["centre_off_face_ft"]),
        along_ft=_hi_len(raw["along_from_piece_line_ft"]),
        strip_w_ft=_hi_len(site["strip_width_ft"]),
        swing_ft=_hi_len(site["swing_beyond_end_ft"]),
        level_pct=_hi_len(raw["pad_level_pct"]),
        carry_radius_ft={k: _hi_len(v) for k, v in carry["hook_radius_ft"].items()},
        carry_walls_flat=bool(carry.get("walls_flat_crosswise", False)),
        carry_slope_per_pct=float(carry["slope_chart_lost_per_pct"]),
        carry_cross_pct=_hi_len(carry["cross_fall_pct"]),
        carry_w_ft=_hi_len(carry["path_width"]),
        carry_cross_w_ft=_hi_len(carry["path_width_crosswise"]),
        carry_power_ft=float(re.match(r"\s*(\d+(?:\.\d+)?)", str(carry["power_line_clearance_ft"])).group(1)),  # type: ignore[union-attr]
        container_sling_lb=_hi(raw["container"]["sling_lb"]),
        container_within_ft=_hi_len(raw["container"]["within_ft"]),
        container_street=bool(raw["container"].get("street_allowed", False)),
        wall_gear_lb={k: float(v) for k, v in (raw.get("wall_gear_lb") or {}).items()},
    )


def _t45(raw: Mapping[str, Any], pct: float) -> Crane45:
    pad_w, pad_l = (hi for _, hi in parse_size(raw["pad"]) or ())
    off = raw.get("rotation_offset_ft") or {}
    deduct = sum(_hi(v) for v in (raw.get("deductions_lb") or {}).values())
    ch = raw["chart"]
    return Crane45(
        label=raw["label"],
        short="45 t",
        body_w_ft=_hi_len(raw["body"]["width"]),
        pad_w_ft=pad_w,
        pad_l_ft=pad_l,
        rotation_offset_ft=(float(off.get("along", 0.0)), float(off.get("across", 0.0))),
        ball_lb=float(raw["ball_lb"]),
        rigging_lb=_hi(raw["rigging_lb"]),
        whole_rigging_lb=float(sum(_hi(v) for v in raw["whole_load_rigging_lb"].values())),
        max_piece_radius_ft=_hi_len(raw["max_piece_radius_ft"]),
        level_pct=float(raw["level_pct"]),
        chart=_chart("nbt45", str(ch.get("source", "")), ch["booms"], deduct, pct),
        single_line_lb=_hi(raw["single_line_lb"]),
        block_lb=float(raw["block_1_sheave_lb"]),
        container_sling_lb=_hi(raw["container_sling_lb"]),
    )


def rules_from(raw: Mapping[str, Any]) -> Rules:
    """Parse the printed config (``set_access.yaml``) into figures."""
    pct = float((raw.get("lifts") or {}).get("max_pct_of_chart") or 100.0)
    ic80 = _ic80(raw["ic80"], pct)
    needed = {k: _hi_len(v) for k, v in raw["ic80"]["hook_needed_ft"].items()}
    highest = max(needed.values())
    pieces: list[Piece] = []
    for key, p in (raw.get("pieces") or {}).items():
        size = parse_size(p.get("size"))
        inset = size[1][0] / 2 if size is not None and len(size) >= 2 else 0.0
        hook = p.get("hook")
        pieces.append(
            Piece(
                key=key,
                label=p["label"],
                count=None if p.get("count") is None else int(p["count"]),
                weight_lb=_hi(p["weight_lb"]),
                place=p["place"],
                points_at_crane=bool(p.get("points_at_crane", False)),
                hook_ft=highest if hook is None else needed[hook],
                group=p["group"],
                inset_ft=inset,
                plan_ft=_plan(size),
                loads=tuple(int(n) for n in (p.get("loads") or (1,))),
                short_hi_ft=sorted((hi for _, hi in size), reverse=True)[1] if size and len(size) >= 2 else 0.0,
            )
        )
    cont = raw["container"]
    truck = raw["truck"]
    search = raw["search"]
    return Rules(
        ic80=ic80,
        t45=_t45(raw["nbt45"], pct),
        pieces=tuple(pieces),
        whole_loads=tuple(
            WholeLoad(
                k, v["label"], _hi(v["stack_lb"]), _hi_len(v["length_ft"]), _fp(v["landing"]), _hi_len(v["within_ft"])
            )
            for k, v in (raw.get("whole_loads") or {}).items()
        ),
        container_label=cont["label"],
        container_fp=_fp(cont["size"]),
        container_lb=_hi(cont["weight_lb"]),
        deck_l_ft=float(truck["trailer_length_ft"]),
        truck_w_ft=_hi_len(truck["width"]),
        places=tuple(truck.get("places") or ("lot", "curb")),
        max_pct=pct,
        homes=int(raw["pod"]["homes"]),
        pad_grid_ft=float(search["pad_grid_ft"]),
        pad_angle_step_deg=float(search["pad_angle_step_deg"]),
        spot_grid_ft=float(search["spot_grid_ft"]),
        spot_angle_step_deg=float(search["spot_angle_step_deg"]),
        pads_kept=int(search["pads_kept"]),
        pads_graded=int(search["pads_graded"]),
        street_step_ft=float(search["street_step_ft"]),
        crane_step_ft=float(search["crane_step_ft"]),
        deck_step_ft=float(search["deck_step_ft"]),
        ic80_places=tuple(truck.get("ic80_places") or ("lot", "street")),
    )


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> Rules:
    return rules_from(yaml.safe_load(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
# The pod's pieces
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PodFrame:
    """The drawn building as a frame: centre, long-axis unit vector, size.
    Local ``u`` runs along the long axis, ``v`` across it."""

    centre: tuple[float, float]
    axis: tuple[float, float]
    length_ft: float
    depth_ft: float

    def world(self, u: float, v: float) -> tuple[float, float]:
        (cx, cy), (ax, ay) = self.centre, self.axis
        return cx + u * ax - v * ay, cy + u * ay + v * ax

    def worlds(self, uv: np.ndarray) -> np.ndarray:
        uv = np.asarray(uv, dtype=float).reshape(-1, 2)
        (cx, cy), (ax, ay) = self.centre, self.axis
        return np.stack([cx + uv[:, 0] * ax - uv[:, 1] * ay, cy + uv[:, 0] * ay + uv[:, 1] * ax], axis=-1)

    def rect(self, u0: float, u1: float, v0: float, v1: float) -> Polygon:
        """A local box as a world polygon."""
        return Polygon(self.worlds(np.array([(u0, v0), (u1, v0), (u1, v1), (u0, v1)])))

    @property
    def angle_deg(self) -> float:
        return math.degrees(math.atan2(self.axis[1], self.axis[0]))


def pod_frame(building: BaseGeometry) -> PodFrame:
    """The building's minimum rotated rectangle: its long side is the pod's
    length (the long walls), its short side the depth -- read off the
    drawing, never assumed."""
    rect = shapely.minimum_rotated_rectangle(building)
    xy = np.asarray(rect.exterior.coords)[:4]
    e1, e2 = xy[1] - xy[0], xy[2] - xy[1]
    a, b = float(np.hypot(*e1)), float(np.hypot(*e2))
    long_vec, length, depth = (e1, a, b) if a >= b else (e2, b, a)
    unit = long_vec / np.hypot(*long_vec)
    c = xy.mean(axis=0)
    return PodFrame((float(c[0]), float(c[1])), (float(unit[0]), float(unit[1])), length, depth)


def local_points(frame: PodFrame, piece: Piece, homes: int, front: int) -> np.ndarray:
    """Where each of a piece's instances is set (its centre), pod-local
    ``(u, v)``, (N, 2). ``front`` is the side (+1 / -1) of the front long
    face; 0 = not known, and the front and back walls are then taken on
    both long faces."""
    L, D = frame.length_ft, frame.depth_ft
    h = L / homes
    homes_u = [-L / 2 + (i + 0.5) * h for i in range(homes)]
    if piece.place in ("front_wall", "back_wall"):
        sides = (1, -1) if front == 0 else ((front,) if piece.place == "front_wall" else (-front,))
        local = [(u, s * D / 2) for u in homes_u for s in sides]
    elif piece.place == "end_wall":
        local = [(-L / 2, 0.0), (L / 2, 0.0)]
    elif piece.place == "party_wall":
        local = [(-L / 2 + k * h, 0.0) for k in range(1, homes)]
    elif piece.place == "centreline":
        local = [(-L / 2 + piece.inset_ft, 0.0), (0.0, 0.0), (L / 2 - piece.inset_ft, 0.0)]
    else:
        raise ValueError(f"{piece.key}: unknown place {piece.place!r}")
    return np.array(local, dtype=float)


def set_points(frame: PodFrame, piece: Piece, homes: int, front: int = 0) -> np.ndarray:
    """:func:`local_points` in world coordinates."""
    return frame.worlds(local_points(frame, piece, homes, front))


# --------------------------------------------------------------------------
# The site
# --------------------------------------------------------------------------

#: Given points on street lot lines (N, 2), the distance from each to its
#: street's near curb and the recorded pavement width there, feet; NaN
#: where nothing measures them (:func:`street_reader`). A reader may add a
#: third array, where each width came from (``measured:<dataset>``,
#: ``estimated:<basis>``, "" where none: :func:`flats.geom.street_width.reader`);
#: without it every width read is taken as measured.
StreetReading = Callable[[np.ndarray], tuple[np.ndarray, ...]]
#: The label of a width estimated off the right-of-way (FOLLOWUPS 145 part
#: B), alone or as ``estimated:<basis>`` naming the street standard (or the
#: stated default) it rests on.
WIDTH_ESTIMATED = "estimated"


def is_estimated(src: Any) -> np.ndarray:
    """Whether each width source label is an estimate."""
    arr = np.asarray(src, dtype=object)
    out = np.zeros(arr.shape, dtype=bool)
    for i, s in np.ndenumerate(arr):
        out[i] = str(s).startswith(WIDTH_ESTIMATED)
    return out
#: Given points on street lot lines (N, 2), the distance from each to its
#: street's centreline, feet; NaN where no centreline is held near
#: (:func:`centre_reader`).
CentreReading = Callable[[np.ndarray], np.ndarray]


@dataclass(frozen=True)
class Trees:
    """Tree canopy read off a public map round one lot (slice 4): the crown
    cover as polygons (working CRS), whether the map covers the lot and
    its street, and the map's name and date."""

    canopy: BaseGeometry
    covered: bool = True
    source: str = "canopy map"


@dataclass(frozen=True)
class Site:
    """One lot with the pod placed: the lot, the drawn building, the lot
    lines on a street ``(x1, y1, x2, y2)``, what measures the street in
    front of them (None: no street set-up or curb truck is measured), and
    any other obstacle held as geometry (other buildings). ``street_centre``
    places the IC-80's street trailer (slice 4); ``trees`` is the canopy
    (None: trees are not checked)."""

    lot: BaseGeometry
    building: BaseGeometry
    street: Sequence[tuple[float, float, float, float]]
    street_reading: StreetReading | None = None
    obstacles: BaseGeometry | None = None
    street_centre: CentreReading | None = None
    trees: Trees | None = None


def _outward(seg: tuple[float, float, float, float], lot: BaseGeometry) -> np.ndarray:
    x1, y1, x2, y2 = seg
    d = np.array([x2 - x1, y2 - y1], dtype=float)
    n = np.array([-d[1], d[0]]) / max(float(np.hypot(*d)), EPS)
    mid = np.array([(x1 + x2) / 2, (y1 + y2) / 2])
    probe = Point(*(mid + n * 0.5))
    return -n if lot.covers(probe) else n


def _segments(site: Site) -> list[tuple[np.ndarray, np.ndarray, np.ndarray, float]]:
    """Each street lot line as (start, unit along, unit OUTWARD, length)."""
    out = []
    for seg in site.street:
        x1, y1, x2, y2 = seg
        length = math.hypot(x2 - x1, y2 - y1)
        if length < EPS:
            continue
        d = np.array([x2 - x1, y2 - y1]) / length
        out.append((np.array([x1, y1], dtype=float), d, _outward(seg, site.lot), length))
    return out


def _aprons(site: Site, depth: float) -> BaseGeometry:
    """The street just outside each street lot line, ``depth`` deep."""
    parts = []
    for a, d, n, length in _segments(site):
        b = a + d * length
        parts.append(Polygon([tuple(a), tuple(b), tuple(b + n * depth), tuple(a + n * depth)]))
    if not parts:
        return Polygon()
    return shapely.union_all(parts).difference(site.lot)


def _corners(c: np.ndarray, u: np.ndarray, length: float, width: float) -> np.ndarray:
    """Rectangles ``length`` along unit vectors ``u`` (N, 2) by ``width``,
    centred on ``c`` (N, 2): corners (N, 4, 2)."""
    c = np.asarray(c, dtype=float).reshape(-1, 2)
    u = np.broadcast_to(np.asarray(u, dtype=float).reshape(-1, 2), c.shape)
    p = np.stack([-u[:, 1], u[:, 0]], axis=-1)
    hl, hw = length / 2, width / 2
    return np.stack(
        [c + su * hl * u + sv * hw * p for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))], axis=1
    )


def _polys(corners: np.ndarray) -> np.ndarray:
    return shapely.polygons(corners)


def _grid(geom: BaseGeometry, step: float) -> tuple[np.ndarray, np.ndarray]:
    x0, y0, x1, y1 = geom.bounds
    xs = np.arange(x0 + step / 2, x1, step)
    ys = np.arange(y0 + step / 2, y1, step)
    gx, gy = np.meshgrid(xs, ys)
    return gx.ravel(), gy.ravel()


def _angles(base_deg: float, step_deg: float) -> np.ndarray:
    n = max(1, int(round(180.0 / step_deg)))
    return np.radians(base_deg + np.arange(n) * step_deg)


def _clear_of(pad: np.ndarray, rects: np.ndarray) -> np.ndarray:
    """Which of ``rects`` (N, 4, 2 corners) stand clear of the convex
    ``pad`` (4, 2): a separating axis among the edge normals of each pair.
    Touching is not clear."""

    def normals(c: np.ndarray) -> np.ndarray:
        e = np.stack([c[..., 1, :] - c[..., 0, :], c[..., 2, :] - c[..., 1, :]], axis=-2)
        return np.stack([-e[..., 1], e[..., 0]], axis=-1)

    n = len(rects)
    if n == 0:
        return np.zeros(0, dtype=bool)
    axes = np.concatenate([np.broadcast_to(normals(pad), (n, 2, 2)), normals(rects)], axis=1)
    pa = np.einsum("kd,nad->nak", pad, axes)
    pb = np.einsum("nkd,nad->nak", rects, axes)
    gap = (pa.max(-1) < pb.min(-1) - EPS) | (pb.max(-1) < pa.min(-1) - EPS)
    return gap.any(axis=1)


@dataclass(frozen=True)
class Spots:
    """Places a footprint stands: centres (N, 2), corners (N, 4, 2), the
    corners of what must stay clear of the crane (the truck's way in with
    it), and where each is (``lot`` / ``curb``)."""

    centres: np.ndarray
    corners: np.ndarray
    clear: np.ndarray
    place: np.ndarray
    #: Unit vector along each footprint's long side (N, 2).
    axis: np.ndarray

    @classmethod
    def empty(cls) -> Spots:
        z = np.zeros((0, 4, 2))
        return cls(np.zeros((0, 2)), z, z, np.zeros(0, dtype=object), np.zeros((0, 2)))

    def __len__(self) -> int:
        return len(self.centres)

    def take(self, keep: np.ndarray) -> Spots:
        return Spots(
            self.centres[keep], self.corners[keep], self.clear[keep], self.place[keep], self.axis[keep]
        )

    def far_ft(self, cor: np.ndarray, long_ft: float, short_ft: float, inset: tuple[float, float]) -> np.ndarray:
        """The farthest a piece's centre can stand from ``cor`` on each
        footprint (``long_ft`` x ``short_ft``), the piece ``inset`` (along,
        across) in from the edges."""
        hl = max(long_ft / 2 - inset[0], 0.0)
        hw = max(short_ft / 2 - inset[1], 0.0)
        u = self.axis
        p = np.stack([-u[:, 1], u[:, 0]], axis=-1)
        rel = self.centres - cor
        a = np.abs((rel * u).sum(-1)) + hl
        b = np.abs((rel * p).sum(-1)) + hw
        return np.hypot(a, b)

    def places_on(self, long_ft: float, short_ft: float, inset: tuple[float, float], step: float) -> np.ndarray:
        """Where a piece's centre may stand on each footprint, sampled:
        (N, Q, 2). Every place is a possibility (where a piece rides is not
        printed)."""
        hl = max(long_ft / 2 - inset[0], 0.0)
        hw = max(short_ft / 2 - inset[1], 0.0)
        al = np.linspace(-hl, hl, max(2, int(math.ceil(2 * hl / step)) + 1)) if hl > EPS else np.zeros(1)
        be = np.array([-hw, hw]) if hw > EPS else np.zeros(1)
        A, B = (m.ravel() for m in np.meshgrid(al, be))
        u = self.axis
        p = np.stack([-u[:, 1], u[:, 0]], axis=-1)
        return self.centres[:, None, :] + A[None, :, None] * u[:, None, :] + B[None, :, None] * p[:, None, :]

    @staticmethod
    def join(parts: Sequence[Spots]) -> Spots:
        parts = [p for p in parts if len(p)]
        if not parts:
            return Spots.empty()
        return Spots(
            np.concatenate([p.centres for p in parts]),
            np.concatenate([p.corners for p in parts]),
            np.concatenate([p.clear for p in parts]),
            np.concatenate([p.place for p in parts]),
            np.concatenate([p.axis for p in parts]),
        )


def lot_truck_spots(site: Site, rules: Rules) -> Spots:
    """The trailer backed straight onto the lot from a street lot line,
    square to it (Steph 2026-11-14, the landing spot): its whole 53 ft deck
    on the lot, and the truck's width clear from the street to the deck's
    far end, with the building in place."""
    L, W = rules.deck_l_ft, rules.truck_w_ft
    g = rules.spot_grid_ft
    ground = site.lot.union(_aprons(site, APRON_FT)).difference(site.building)
    shapely.prepare(ground)
    xy = shapely.get_coordinates(site.lot)
    out: list[Spots] = []
    for a, d, n, length in _segments(site):
        inward = -n
        deep = float(((xy - a) @ inward).max())
        us = np.arange(W / 2, length - W / 2 + EPS, g) if length >= W else np.zeros(0)
        vs = np.arange(L / 2, deep - L / 2 + EPS, g)
        if not len(us) or not len(vs):
            continue
        uu, vv = (m.ravel() for m in np.meshgrid(us, vs))
        base = a + uu[:, None] * d
        centre = base + vv[:, None] * inward
        far = vv + L / 2
        strip = _strips(base, inward, -1.0, far, W)
        ok = shapely.contains(ground, _polys(strip))
        if not ok.any():
            continue
        clear = _strips(base[ok], inward, -APRON_FT, far[ok], W)
        out.append(
            Spots(
                centre[ok],
                _corners(centre[ok], inward, L, W),
                clear,
                np.full(int(ok.sum()), "lot", dtype=object),
                np.tile(inward, (int(ok.sum()), 1)),
            )
        )
    return Spots.join(out)


def _strips(base: np.ndarray, inward: np.ndarray, v0: float, v1: np.ndarray, width: float) -> np.ndarray:
    """Rectangles square to a lot line from depth ``v0`` to ``v1`` (N,),
    ``width`` wide, centred on ``base`` points of the line: corners."""
    v1 = np.asarray(v1, dtype=float)
    p = np.array([-inward[1], inward[0]])
    hw = width / 2
    a0 = base + v0 * inward
    a1 = base + v1[:, None] * inward
    return np.stack([a0 - hw * p, a1 - hw * p, a1 + hw * p, a0 + hw * p], axis=1)


def _along(length: float, step: float) -> np.ndarray:
    """Distances along a line every ``step``, both ends included."""
    us = np.arange(0.0, length + EPS, step)
    if not len(us) or us[-1] < length - EPS:
        us = np.append(us, length)
    return us


def _street_read(site: Site, pts: np.ndarray, estimates: bool) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(curb, width, source) at ``pts`` off ``site.street_reading``; the
    estimated ones dropped unless ``estimates``."""
    assert site.street_reading is not None
    got = site.street_reading(pts)
    curb, width = np.asarray(got[0], dtype=float).copy(), np.asarray(got[1], dtype=float).copy()
    if len(got) > 2:
        src = np.asarray(got[2], dtype=object)
    else:
        src = np.where(np.isfinite(width), "measured", "").astype(object)
    if not estimates:
        est = is_estimated(src)
        curb[est], width[est] = np.nan, np.nan
        src = np.where(est, "", src).astype(object)
    return curb, width, src


def _on_street(site: Site, pts: np.ndarray) -> np.ndarray:
    """Whether a truck centreline is held near each point: a point past
    every centreline's reach is not in front of a street, so nothing is
    left unmeasured there (it is no place for a truck)."""
    if site.street_centre is None:
        return np.ones(len(pts), dtype=bool)
    return np.isfinite(np.asarray(site.street_centre(pts), dtype=float))


def curb_truck_spots(site: Site, rules: Rules, *, estimates: bool = False) -> tuple[Spots, bool]:
    """The trailer parked at the near curb in front of the lot, parallel to
    the lot line, its deck centred anywhere along the frontage; and whether
    the curb was measured at every point of a street lot line that is in
    front of a street (:func:`_on_street`). ``estimates`` takes curbs placed
    off an estimated width too (the 45 t's street set-up only); those spots
    are ``curb (est)``."""
    if site.street_reading is None:
        return Spots.empty(), False
    L, W = rules.deck_l_ft, rules.truck_w_ft
    out: list[Spots] = []
    measured = True
    for a, d, n, length in _segments(site):
        us = _along(length, rules.spot_grid_ft)
        # The curb under the deck's two ends and middle: the farthest of
        # them, so the whole deck stands on the pavement.
        pts = np.concatenate([a + np.clip(us + k, 0, length)[:, None] * d for k in (-L / 2, 0.0, L / 2)])
        curb, width, src = _street_read(site, pts, estimates)
        # An estimated street narrower than the truck is read, and holds no
        # truck: no spot, and not an unread curb.
        narrow = is_estimated(src) & (width < W)
        unread = (~np.isfinite(curb) & ~narrow & _on_street(site, pts)).reshape(3, -1)
        curb = np.where(narrow, np.nan, curb)
        curb, src = curb.reshape(3, -1), src.reshape(3, -1)
        ok = np.isfinite(curb).all(axis=0)
        if unread.any():
            measured = False
        if not ok.any():
            continue
        off = curb.max(axis=0)[ok]
        centre = a + us[ok][:, None] * d + (off + W / 2)[:, None] * n
        corners = _corners(centre, d, L, W)
        est = is_estimated(src).any(axis=0)[ok]
        out.append(
            Spots(
                centre, corners, corners, np.where(est, CURB_EST, "curb").astype(object),
                np.tile(d, (int(ok.sum()), 1)),
            )
        )
    return Spots.join(out), measured


def street_truck_spots(site: Site, rules: Rules) -> tuple[Spots, bool]:
    """The IC-80's trailer IN THE STREET along the frontage (slice 4, Steph
    2026-11-14), parallel to each street lot line, centred anywhere along
    it, its far side at the street's centreline (the farthest it stands on
    the near half: the cautious place to pick from). No curb is read
    ("ignore the curb"). Returns the spots whose place is measured, and
    whether every frontage's centreline was read."""
    if site.street_centre is None:
        return Spots.empty(), False
    L, W = rules.deck_l_ft, rules.truck_w_ft
    out: list[Spots] = []
    measured = True
    for a, d, n, length in _segments(site):
        us = _along(length, rules.spot_grid_ft)
        pts = np.concatenate([a + np.clip(us + k, 0, length)[:, None] * d for k in (-L / 2, 0.0, L / 2)])
        gap = np.asarray(site.street_centre(pts), dtype=float).reshape(3, -1)
        ok = np.isfinite(gap).all(axis=0)
        if not ok.all():
            measured = False
        if not ok.any():
            continue
        off = np.maximum(gap.max(axis=0)[ok] - W / 2, W / 2)
        centre = a + us[ok][:, None] * d + off[:, None] * n
        corners = _corners(centre, d, L, W)
        out.append(
            Spots(centre, corners, corners, np.full(int(ok.sum()), "street", dtype=object), np.tile(d, (int(ok.sum()), 1)))
        )
    return Spots.join(out), measured


def container_spots(open_ground: BaseGeometry, rules: Rules, base_deg: float) -> Spots:
    """Every place the site container's plan fits on open ground."""
    fp = rules.container_fp
    if open_ground.is_empty:
        return Spots.empty()
    gx, gy = _grid(open_ground, rules.spot_grid_ft)
    if not len(gx):
        return Spots.empty()
    shapely.prepare(open_ground)
    parts = []
    c = np.stack([gx, gy], axis=-1)
    for ang in _angles(base_deg, rules.spot_angle_step_deg):
        u = np.array([math.cos(ang), math.sin(ang)])
        corners = _corners(c, u, fp[0], fp[1])
        ok = shapely.contains(open_ground, _polys(corners))
        parts.append(
            Spots(
                c[ok], corners[ok], corners[ok], np.full(int(ok.sum()), "lot", dtype=object),
                np.tile(u, (int(ok.sum()), 1)),
            )
        )
    return Spots.join(parts)


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Lift:
    """One kind of lift on one plan: its farthest radius against the chart."""

    what: Literal["piece", "whole_load", "container"]
    key: str
    label: str
    count: int | None
    gross_lb: float
    pick_ft: float
    set_ft: float
    radius_ft: float
    #: The chart row read (the next longer listed radius) and its boom.
    row_ft: float | None
    boom_ft: float | None
    capacity_lb: float | None
    slack_lb: float | None
    pct_of_chart: float | None
    verify_weight: bool
    status: Status
    why: str = ""
    #: IC-80 walls and bundles where the trailer is out of reach: carried.
    carried: bool = False


@dataclass(frozen=True, slots=True)
class Check:
    """One item of a step's site check (spec section 5)."""

    name: str
    status: Status
    detail: str = ""


def _binding(lifts: Sequence[Lift]) -> Lift | None:
    """The lift nearest its chart (highest percent used); a failing or
    unmeasured lift first."""
    if not lifts:
        return None
    return max(
        lifts,
        key=lambda lf: (
            _ORDER[lf.status],
            lf.pct_of_chart if lf.pct_of_chart is not None else math.inf,
        ),
    )


@dataclass(frozen=True)
class IC80Plan:
    """The IC-80 working from one or both long faces."""

    faces: tuple[str, ...]
    checks: tuple[Check, ...]
    lifts: tuple[Lift, ...]
    status: Status
    working: BaseGeometry
    truck: str | None = None
    truck_spot: BaseGeometry | None = None
    #: The steepest fall across the pads of a set-up spot used, %.
    pad_grade_pct: float | None = None
    #: The heaviest wall rigging every wall lift of this plan holds within
    #: the planning line (spec 3.6), lb.
    rigging_limit_lb: float | None = None
    container: Check | None = None
    crane: str = "IC-80"
    setup: str = "site"
    #: Every piece's set lift alone (from the crane spot nearest its place),
    #: before the trailer's pick radius is added.
    sets: tuple[Lift, ...] = ()
    #: Where each trailer load parks (``lot`` / ``street``, `` (carried)``
    #: where a kind is picked there and carried), by load number.
    trailer_spots: Mapping[int, str] = field(default_factory=dict)
    #: How each wall load is stacked (DECISIONS S-wallstack): the walls set
    #: first on top.
    stack: str | None = None
    #: The status with the canopy left out (what trees cost, slice 4).
    bare_status: Status | None = None
    extra_notes: tuple[str, ...] = ()

    @property
    def way(self) -> str | None:
        """How the IC-80 works: ``lot`` (every load picked straight off a
        trailer on the lot), ``street``, ``lot and street``, each with
        `` + carry`` where any kind is picked at the trailer and carried."""
        if not self.trailer_spots:
            return None
        text = " ".join(self.trailer_spots.values())
        where = [w for w in ("lot", "street") if w in text]
        return " and ".join(where) + (" + carry" if "carried" in text else "")

    @property
    def binding(self) -> Lift | None:
        return _binding(self.lifts)

    @property
    def binding_check(self) -> str:
        """The check that decides the step: the first failing, else the
        first unmeasured, else the hardest lift."""
        for want in (FAIL, UNMEASURED):
            for c in self.checks:
                if c.status == want:
                    return c.name
        b = self.binding
        return f"lifts: {b.label}" if b else "lifts"

    @property
    def notes(self) -> tuple[str, ...]:
        return (POWER_NOTE, *self.extra_notes)


@dataclass(frozen=True)
class Plan:
    """The 45 t: where the crane and the truck stand, and every lift."""

    crane: str
    setup: Literal["site", "street"]
    pad: BaseGeometry
    axis: tuple[float, float]
    access: str
    mode: Literal["whole_load", "off_trailer"]
    truck: Literal["lot", "curb"]
    truck_spot: BaseGeometry
    container_spot: BaseGeometry | None
    lifts: tuple[Lift, ...]
    status: Status
    slope_pct: float | None = None
    level: Status = UNMEASURED
    #: Where the street's width under the pad (and the curb the truck
    #: stands at) came from: ``measured:<dataset>``, ``estimated`` where
    #: either rests on an estimate (FOLLOWUPS 145 part B); None on site with
    #: no curb truck.
    width_source: str | None = None

    @property
    def binding(self) -> Lift | None:
        return _binding(self.lifts)

    @property
    def binding_check(self) -> str:
        if self.access != STRAIGHT:
            return "access"
        b = self.binding
        if b is not None and b.status != PASS:
            return f"lifts: {b.label}"
        if self.level != PASS:
            return "level"
        return f"lifts: {b.label}" if b else "lifts"

    @property
    def notes(self) -> tuple[str, ...]:
        out = [POWER_NOTE]
        if self.access == BENDS:
            out.append("the crane's way in needs bends; turning not checked")
        return tuple(out)


@dataclass(frozen=True)
class Attempt:
    step: str
    status: Status | str
    plan: IC80Plan | Plan | None = None
    why: tuple[str, ...] = ()


@dataclass(frozen=True)
class Report:
    """The lot's answer."""

    #: ``IC-80 one face (front)`` / ``IC-80 one face (back)`` / ``IC-80 both
    #: faces`` / ``45 t on site`` / ``45 t in the street`` / ``not viable`` /
    #: ``unmeasured``.
    result: str
    face: str | None
    plan: IC80Plan | Plan | None
    attempts: tuple[Attempt, ...]
    #: Why every step before the answer did not pass (all steps, where none
    #: did).
    why: tuple[str, ...]
    not_checked: tuple[str, ...] = NOT_CHECKED
    notes: tuple[str, ...] = field(default=())
    #: The answer with the canopy left out (slice 4: what trees cost).
    result_no_trees: str | None = None

    def row(self) -> dict[str, Any]:
        """One flat record for the summary table."""
        p = self.plan
        b = p.binding if p is not None else None
        out: dict[str, Any] = {
            "result": self.result,
            "face": self.face,
            "crane": p.crane if p else None,
            "setup": p.setup if p else None,
            # IC-80: where each trailer load parks ("1 curb, 2 lot, ..."); the 45 t: its one spot.
            "truck": (
                ", ".join(f"{n} {w}" for n, w in p.trailer_spots.items())
                if p is not None and getattr(p, "trailer_spots", None) else (p.truck if p else None)
            ),
            "mode": getattr(p, "mode", None),
            "binding_check": p.binding_check if p else None,
            "hardest_lift": b.label if b else None,
            "hardest_gross_lb": round(b.gross_lb) if b else None,
            "hardest_radius_ft": round(b.radius_ft, 1) if b and math.isfinite(b.radius_ft) else None,
            "chart_row_ft": b.row_ft if b else None,
            "chart_capacity_lb": b.capacity_lb if b else None,
            "pct_of_chart": None if b is None or b.pct_of_chart is None else round(b.pct_of_chart, 1),
            "rigging_limit_lb": None
            if not isinstance(p, IC80Plan) or p.rigging_limit_lb is None
            else round(p.rigging_limit_lb),
            "grade_pct": _round(p.pad_grade_pct if isinstance(p, IC80Plan) else getattr(p, "slope_pct", None)),
            "ic80_way": p.way if isinstance(p, IC80Plan) else None,
            "trees": next((c.status for c in p.checks if c.name == "trees"), None) if isinstance(p, IC80Plan) else None,
            "result_no_trees": self.result_no_trees,
            "container": None if not isinstance(p, IC80Plan) or p.container is None else p.container.status,
            "stack": p.stack if isinstance(p, IC80Plan) else None,
            # FOLLOWUPS 145 part B: measured:<dataset> or estimated.
            "width_source": p.width_source if isinstance(p, Plan) else None,
            "notes": "; ".join(self.notes),
            "why": "; ".join(self.why),
        }
        for a in self.attempts:
            out[a.step] = a.status
            if a.step == "45t_street":
                out["45t_street_width"] = a.plan.width_source if isinstance(a.plan, Plan) else None
            if isinstance(a.plan, IC80Plan):
                out[f"{a.step}_checks"] = ", ".join(c.name for c in a.plan.checks if c.status != PASS)
                out[f"{a.step}_way"] = a.plan.way
        return out


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 2)


def _worst(statuses: Iterable[Status]) -> Status:
    s = list(statuses)
    if FAIL in s:
        return FAIL
    if UNMEASURED in s:
        return UNMEASURED
    return PASS


def _best(statuses: Iterable[Status]) -> Status:
    s = list(statuses)
    if PASS in s:
        return PASS
    if UNMEASURED in s:
        return UNMEASURED
    return FAIL


def _lift(
    chart: Chart, what: str, key: str, label: str, count: int | None, gross: float, pick: float, setr: float,
    verify_over: float, *, max_r: float | None = None, extra_fail: str = "", why_unmeasured: str = "",
    carried: bool = False,
) -> Lift:
    """One lift read off ``chart`` at max(pick, set)."""
    r = float(max(pick, setr))
    if not math.isfinite(r):
        return Lift(what, key, label, count, gross, pick, setr, r, None, None, None, None, None, False,  # type: ignore[arg-type]
                    UNMEASURED if why_unmeasured else FAIL, why_unmeasured or extra_fail or "no place to set it from",
                    carried)
    got = chart.read(r)
    if got is None:
        return Lift(what, key, label, count, gross, pick, setr, r, None, None, None, None, None, False,  # type: ignore[arg-type]
                    UNMEASURED, "inside the chart's least radius", carried)
    allowed = got.capacity_lb * chart.max_pct / 100.0
    pct = None if got.capacity_lb <= 0 else 100.0 * gross / got.capacity_lb
    why = ""
    status: Status = PASS
    if allowed < gross - EPS:
        status = FAIL
        why = (
            f"over the {chart.max_pct:g}% planning line at {r:.1f} ft (read at {got.row_ft:g} ft): "
            f"{gross:,.0f} lb on {got.capacity_lb:,.0f} lb, a critical lift"
            if got.row_ft is not None
            else f"beyond the chart's longest reach at {r:.1f} ft"
        )
    elif max_r is not None and r > max_r + EPS:
        status = FAIL
        why = f"{r:.1f} ft out, past the {max_r:g} ft the spec allows"
    elif extra_fail:
        status = FAIL
        why = extra_fail
    elif why_unmeasured:
        status = UNMEASURED
        why = why_unmeasured
    return Lift(
        what=what,  # type: ignore[arg-type]
        key=key,
        label=label,
        count=count,
        gross_lb=gross,
        pick_ft=float(pick),
        set_ft=float(setr),
        radius_ft=r,
        row_ft=got.row_ft,
        boom_ft=got.boom_ft,
        capacity_lb=got.capacity_lb,
        slack_lb=allowed - gross,
        pct_of_chart=pct,
        verify_weight=pct is not None and pct > verify_over,
        status=status,
        why=why,
        carried=carried,
    )


# --------------------------------------------------------------------------
# What every step on one lot shares
# --------------------------------------------------------------------------


@dataclass
class _Lot:
    site: Site
    rules: Rules
    frame: PodFrame
    #: The front long face's side (+1 / -1), 0 where it cannot be told.
    front: int
    open_lot: BaseGeometry
    lot_spots: Spots
    curb_spots: Spots
    curb_measured: bool
    grade_of: Callable[[BaseGeometry], float | None] | None
    #: The curb truck spots and their measured flag with estimated widths
    #: filled in (the 45 t's street set-up only; FOLLOWUPS 145 part B).
    curb_spots_est: Spots | None = None
    curb_measured_est: bool | None = None
    #: The IC-80's street trailer spots (slice 4) and whether every
    #: frontage's centreline was read.
    street_spots: Spots = field(default_factory=Spots.empty)
    street_measured: bool = False
    #: Per-lot memo (pad grades, carry paths).
    memo: dict = field(default_factory=dict)


def _front(site: Site, frame: PodFrame) -> int:
    """The long face nearer a street lot line (+1 / -1); 0 where there is
    no street line or both faces are as near (within 1 ft)."""
    if not site.street:
        return 0
    streets = shapely.union_all([LineString([(x1, y1), (x2, y2)]) for x1, y1, x2, y2 in site.street])
    d = {s: Point(*frame.world(0.0, s * frame.depth_ft / 2)).distance(streets) for s in (1, -1)}
    if abs(d[1] - d[-1]) < 1.0:
        return 0
    return 1 if d[1] < d[-1] else -1


def _face_name(side: int, front: int) -> str:
    if front == 0:
        return "long face 1" if side == 1 else "long face 2"
    return "front" if side == front else "back"


# --------------------------------------------------------------------------
# Step 1-2: the IC-80 from one or both long faces
# --------------------------------------------------------------------------


def _ic80_ground(frame: PodFrame, ic: IC80, sides: Sequence[int]) -> dict[str, BaseGeometry]:
    """The IC-80's working ground for ``sides``: the strip, the outrigger
    footprint along the crane line, and the swing room beyond each end."""
    L, D = frame.length_ft, frame.depth_ft
    strips, bands = [], []
    for s in sides:
        v0, v1 = sorted((s * D / 2, s * (D / 2 + ic.strip_w_ft)))
        strips.append(frame.rect(-L / 2, L / 2, v0, v1))
        c = D / 2 + ic.off_face_ft
        b0, b1 = sorted((s * (c - ic.out_w_ft / 2), s * (c + ic.out_w_ft / 2)))
        h = ic.out_l_ft / 2
        bands.append(frame.rect(-L / 2 - h, L / 2 + h, b0, b1))
    lo = min([-D / 2] + [s * (D / 2 + ic.outer_ft) for s in sides])
    hi = max([D / 2] + [s * (D / 2 + ic.outer_ft) for s in sides])
    swing = shapely.union_all(
        [frame.rect(-L / 2 - ic.swing_ft, -L / 2, lo, hi), frame.rect(L / 2, L / 2 + ic.swing_ft, lo, hi)]
    )
    return {"strip": shapely.union_all(strips), "outriggers": shapely.union_all(bands), "swing": swing}


def _crane_line(
    frame: PodFrame, ic: IC80, sides: Sequence[int], step: float, extra_u: Iterable[float] = ()
) -> tuple[np.ndarray, np.ndarray]:
    """IC-80 crane spots (centre of rotation) along each active face, world
    (M, 2), and their local ``u`` (M,): every ``step`` along the face, plus
    ``extra_u`` (the exact spots a piece's least radius or along-offset
    asks for, so the grid never pushes a reading to the next row)."""
    L, D = frame.length_ft, frame.depth_ft
    us = np.arange(-L / 2, L / 2 + EPS, step)
    if us[-1] < L / 2 - EPS:
        us = np.append(us, L / 2)
    extra = np.array([u for u in extra_u if -L / 2 - EPS <= u <= L / 2 + EPS], dtype=float)
    us = np.unique(np.round(np.concatenate([us, extra]), 6))
    uv = np.concatenate([np.stack([us, np.full(len(us), s * (D / 2 + ic.off_face_ft))], axis=-1) for s in sides])
    return frame.worlds(uv), uv[:, 0]


def _covered(ground: BaseGeometry, geom: BaseGeometry) -> bool:
    return bool(ground.buffer(1e-6).covers(geom))


def _set_radius(S: np.ndarray, su: np.ndarray, P: np.ndarray, pu: np.ndarray, ic: IC80, points: bool) -> tuple[float, np.ndarray]:
    """The farthest set radius over the instances ``P`` (each set from its
    nearest allowed crane spot), and per spot the distance matrix (M, nP)
    with disallowed pairs at inf."""
    d = np.hypot(S[:, None, 0] - P[None, :, 0], S[:, None, 1] - P[None, :, 1])
    ok = d >= ic.min_radius_ft - EPS
    if points:
        ok &= np.abs(su[:, None] - pu[None, :]) >= ic.along_ft - EPS
    d = np.where(ok, d, np.inf)
    return float(d.min(axis=0).max()), d


def _way(
    lot: _Lot, S: np.ndarray, width: float, *, goal: BaseGeometry | None = None, trees: bool = False,
    avoid: BaseGeometry | None = None,
) -> tuple[Status, str]:
    """A way for the IC-80, ``width`` wide, between the crane spots ``S``
    and the street (``goal`` None) or ``goal`` (ground beside a trailer on
    the lot): 9 ft 6 in (or ``width``, if wider) all the way, where any
    turn fits, passes; from the street, a straight run in ``width`` wide to
    ground that wide passes; a narrower way only is unmeasured (whether its
    turns fit is not checked); none fails. ``trees``: the canopy is an
    obstacle too; ``avoid``: more ground taken out (the trailer's deck).
    Memoised per lot."""
    canopy = lot.site.trees.canopy if trees and lot.site.trees is not None else None
    if canopy is not None and canopy.is_empty:
        canopy = None
    key = ("way", S.tobytes(), round(width, 3), None if goal is None else goal.wkb, canopy is not None,
           None if avoid is None else avoid.wkb)
    if key not in lot.memo:
        lot.memo[key] = _way_uncached(lot, S, width, goal, canopy, avoid)
    return lot.memo[key]


def _way_uncached(
    lot: _Lot, S: np.ndarray, width: float, goal: BaseGeometry | None, canopy: BaseGeometry | None,
    avoid: BaseGeometry | None,
) -> tuple[Status, str]:
    site, ic = lot.site, lot.rules.ic80
    turn = max(ic.route_turn_w_ft, width)
    aprons = _aprons(site, APRON_FT)
    obst = site.building if site.obstacles is None else site.building.union(site.obstacles)
    if canopy is not None:
        obst = obst.union(canopy)
    if avoid is not None:
        obst = obst.union(avoid)
    drivable = site.lot.union(aprons).difference(obst)
    zone = aprons.difference(site.lot.buffer(turn / 2 + 0.5)) if goal is None else goal
    wide = drivable.buffer(-turn / 2 + EPS)
    narrow = drivable.buffer(-width / 2 + EPS)
    line_pts = shapely.points(S)

    def component(geom: BaseGeometry) -> BaseGeometry | None:
        parts = [p for p in shapely.get_parts(geom) if shapely.intersects(p, line_pts).any()]
        return shapely.union_all(parts) if parts else None

    wide_part = component(wide)
    if wide_part is not None and wide_part.intersects(zone):
        return PASS, f"{turn:.1f} ft wide " + ("from the street" if goal is None else "from the trailer")
    if wide_part is not None and goal is None:
        # A straight run in from the street, square to a street lot line,
        # ``width`` wide, reaching ground where the crane can turn.
        for a, d, n, length in _segments(site):
            for t in _along(length, 2.0):
                # Inside the street far enough that the eroded ground holds it.
                start = a + d * t + n * (APRON_FT - turn / 2 - 1.0)
                ray = LineString([tuple(start), tuple(start - n * (APRON_FT + 400.0))])
                inside = ray.intersection(narrow)
                for piece in shapely.get_parts(inside):
                    if piece.distance(Point(*start)) < 1e-3 and piece.intersects(wide_part):
                        return PASS, f"straight in {width:.1f} ft wide, turning on open ground"
    narrow_part = component(narrow)
    if narrow_part is not None and narrow_part.intersects(zone):
        return UNMEASURED, f"a way {width:.1f} ft wide exists; whether its turns are {turn:.1f} ft wide is not checked"
    where = "from the street" if goal is None else "from beside the trailer"
    return FAIL, f"no way {width:.1f} ft wide {where} to the crane line"


def _ic80_route(lot: _Lot, ground: dict[str, BaseGeometry], S: np.ndarray) -> Check:
    """The IC-80's way from the street to the crane line, empty, boom
    stowed (trees do not stop it: it stands 7 ft 3 in): 9 ft 6 in wide all
    the way, or a straight run in 6 ft 6 in wide; else unmeasured where a
    6 ft 6 in way exists."""
    if not lot.site.street:
        return Check("route", UNMEASURED, "no street lot line traced")
    st, why = _way(lot, S, lot.rules.ic80.route_w_ft)
    return Check("route", st, why)


def _pad_levels(lot: _Lot, S: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Slice 4 (spec 3.9, "Level applies to the crane, not the strip"):
    per crane spot, the fall across its outrigger footprint (the four pads'
    ground; NaN where not read) and its class: 0 within ~3%, 1 not read, 2
    steeper. Memoised per lot (one face's spots serve every plan)."""
    ic = lot.rules.ic80
    g = np.full(len(S), np.nan)
    if lot.grade_of is not None and len(S):
        memo = lot.memo.setdefault("pads", {})
        rects = _corners(S, np.array(lot.frame.axis), ic.out_l_ft, ic.out_w_ft)
        for i, (x, y) in enumerate(S):
            k = (round(float(x), 2), round(float(y), 2))
            if k not in memo:
                v = lot.grade_of(Polygon(rects[i]))
                memo[k] = math.nan if v is None else float(v)
            g[i] = memo[k]
    cls = np.where(np.isnan(g), 1, np.where(g <= ic.level_pct + EPS, 0, 2))
    return g, cls


def _carry_fall(lot: _Lot, S: np.ndarray, goal: BaseGeometry | None, width: float) -> tuple[float | None, str]:
    """The fall of a carry path, %: the plane fitted to the lot ground on a
    ``width`` corridor along the shortest line from the crane spots to the
    trailer's deck, or to the street lot lines (0 where it does not cross
    the lot; None, with why, where it is not read)."""
    site = lot.site
    if lot.grade_of is None:
        return None, "the carry path's fall is not read (no elevation model)"
    if goal is None:
        if not site.street:
            return None, "no street lot line traced"
        goal = shapely.union_all([LineString([(x1, y1), (x2, y2)]) for x1, y1, x2, y2 in site.street])
    key = ("carry_fall", S.tobytes(), goal.wkb, round(width, 3))
    if key not in lot.memo:
        line = shapely.shortest_line(shapely.multipoints(S), goal)
        corridor = line.buffer(width / 2, cap_style="flat").intersection(site.lot) if line.length > EPS else Polygon()
        if corridor.is_empty or corridor.area < 1.0:
            lot.memo[key] = (0.0, "the carry path does not cross the lot")
        else:
            g = lot.grade_of(corridor)
            lot.memo[key] = (None, "the carry path's fall is not read") if g is None else (float(g), "")
    return lot.memo[key]


def _carry_slope(lot: _Lot, hook: Sequence[Piece], flat: bool, g: float | None, why: str) -> tuple[Status, str]:
    """Spec 3.7, carrying on a real site [est]: the usable chart is the
    chart x (1 - 0.03 x the downhill fall %) (the fall of the fitted plane
    taken as downhill with the load ahead, and as across the route too:
    past ~3% across, the 360 deg on-rubber column is read). Every hook
    piece must stay within the planning line on the usable chart."""
    ic, rules = lot.rules.ic80, lot.rules
    if g is None:
        return UNMEASURED, why
    if g <= EPS:
        return PASS, why or "the carry path is level"
    cross = g > ic.carry_cross_pct + EPS
    worst: tuple[float, Piece] | None = None
    for p in hook:
        lf = _ic80_carry_lift(ic, rules, p, None, flat=flat, across=cross)  # type: ignore[arg-type]
        keep = 1.0 - ic.carry_slope_per_pct * g
        use = math.inf if lf.pct_of_chart is None or keep <= EPS else lf.pct_of_chart / keep
        if worst is None or use > worst[0]:
            worst = (use, p)
    assert worst is not None
    use, p = worst
    col = "the 360 deg column" if cross else "over the front"
    if use <= rules.max_pct + EPS:
        return PASS, f"the carry path falls {g:.2f}%: {p.label} at {use:.0f}% of the usable chart ({col})"
    return FAIL, (f"the carry path falls {g:.2f}%: {p.label} would be at {use:.0f}% of the usable chart ({col}, "
                  f"{100 * ic.carry_slope_per_pct:g}% of it lost per 1%), over the {rules.max_pct:g}% planning line")


def _panel_points(lot: _Lot, S: np.ndarray, r: float) -> np.ndarray:
    """Where a panel carried crosswise hangs with the crane at each set-up
    spot of ``S``: ``r`` ft out from the spot, away from the building (the
    crane backs in with the load ahead of it, then turns the panel to its
    line, spec 3.7)."""
    if not len(S):
        return S
    pts = shapely.points(S)
    near = shapely.get_coordinates(shapely.shortest_line(pts, lot.site.building))[1::2]
    d = S - near
    n = np.linalg.norm(d, axis=1, keepdims=True)
    return S + np.where(n > EPS, d / np.maximum(n, EPS), 0.0) * r


def _carry(lot: _Lot, S: np.ndarray, carried: Sequence[Piece], deck: Polygon | None) -> tuple[Status, Status, str]:
    """How a load's carried kinds get from the trailer (on the lot: its
    ``deck``; in the street: None) to a set-up spot among ``S`` (slice 4b,
    spec 3.7 at 9985b64). Pieces on the hook ride on rubber over the front:
    cassettes flat and crosswise on a ~27 ft path; walls upright, edge-on,
    on a 6 ft 6 in path, or (``carry_walls_flat``) flat and crosswise like a
    cassette, the better of the two; the route's fall within what the
    chart has left (:func:`_carry_slope`). Bundles ride the cargo deck and
    need the way in only. Firm and even are not read (NOT_CHECKED).
    Returns (status with no tree read, status with the canopy as an
    obstacle, detail)."""
    ic, rules = lot.rules.ic80, lot.rules
    goal = None if deck is None else deck.buffer(max(ic.carry_radius_ft.values()))
    hook = [p for p in carried if p.group != "bundle"]
    bundles = [p for p in carried if p.group == "bundle"]
    bare: list[Status] = []
    treed: list[Status] = []
    parts: list[str] = []
    trees = lot.site.trees is not None and lot.site.trees.covered
    if hook:
        cassettes = any(p.group == "cassette" for p in hook)
        walls = [p for p in hook if p.group != "cassette"]
        ways: list[bool] = []
        if all(_ic80_carry_lift(ic, rules, p, None).status == PASS for p in walls):  # type: ignore[arg-type]
            ways.append(False)  # walls upright (cassettes always flat, crosswise)
        if walls and ic.carry_walls_flat:
            ways.append(True)
        tried: list[tuple[tuple, Status, Status, list[str]]] = []
        for flat in ways:
            cross = flat or cassettes
            width = ic.carry_cross_w_ft if cross else ic.carry_w_ft
            # A crosswise panel rides ~11-12 ft ahead of the crane: it is
            # carried to where it hangs with the crane at a set-up spot,
            # backed in with the load away from the building.
            to = _panel_points(lot, S, max(
                _ic80_carry_lift(ic, rules, p, None, flat=flat).radius_ft for p in hook)) if cross else S  # type: ignore[arg-type]
            st, why = _way(lot, to, width, goal=goal, avoid=deck)
            st_t, why_t = _way(lot, to, width, goal=goal, avoid=deck, trees=True) if trees else (st, why)
            how = ", ".join(([f"walls {'flat, crosswise' if flat else 'upright'}"] if walls else [])
                            + (["cassettes flat, crosswise"] if cassettes else []))
            ps = [f"carried {how}, path {width:g} ft wide: {why}"]
            if st_t != st:
                ps.append(f"with the canopy: {why_t}")
            g, g_why = _carry_fall(lot, S, deck, width)
            lv, lv_why = _carry_slope(lot, hook, flat, g, g_why)
            ps.append(lv_why)
            b, t = _worst([st, lv]), _worst([st_t, lv])
            tried.append(((_ORDER[t], _ORDER[b]), b, t, ps))
        if not tried:
            bare.append(FAIL)
            treed.append(FAIL)
            parts.append("a wall carried upright is over the planning line (spec 3.7)")
        else:
            _, b, t, ps = min(tried, key=lambda x: x[0])
            bare.append(b)
            treed.append(t)
            parts.extend(ps)
    if bundles:
        st, why = _way(lot, S, ic.route_w_ft, goal=goal, avoid=deck)
        bare.append(st)
        treed.append(st)
        parts.append(f"bundles on the cargo deck: {why}")
    return _worst(bare), _worst(treed), "; ".join(parts)


def _ic80_container(lot: _Lot, working: BaseGeometry, deck: Polygon | None, place: str | None) -> Check:
    """Spec 3.8, reported beside the answer (not a viability item): the
    container lifted off the trailer within ~10 ft of the IC-80's centre and
    set within ~10 ft of it, on open ground off the strip, wherever on the
    deck it rides."""
    rules = lot.rules
    ic = rules.ic80
    if deck is None:
        return Check("container", UNMEASURED, "no trailer spot")
    gross = rules.container_lb + ic.container_sling_lb + ic.hook_lb
    stowed = dataclasses.replace(ic.set_chart, deductions_lb=ic.stowed_deduct_lb)
    reach = stowed.reach_for(gross)
    if reach is None:
        return Check("container", FAIL, f"{gross:,.0f} lb is over the planning line at every radius")
    reach = min(reach, ic.container_within_ft)
    xy = np.asarray(deck.exterior.coords)[:4]
    e = xy[1] - xy[0]
    u = e / max(float(np.hypot(*e)), EPS)
    sp = Spots(xy.mean(axis=0)[None], xy[None], xy[None], np.array([place], dtype=object), u[None])
    Q = sp.places_on(rules.deck_l_ft, rules.truck_w_ft, (rules.container_fp[0] / 2, rules.container_fp[1] / 2), rules.deck_step_ft)[0]
    stand = lot.open_lot.difference(deck)
    street = False
    if ic.container_street and lot.site.street:
        # Steph 2026-11-14: the IC-80 may step into the street for this one
        # lift (power lines not checked).
        stand = stand.union(_aprons(lot.site, APRON_FT).difference(deck))
        street = True
    gx, gy = _grid(stand, rules.spot_grid_ft)
    C0 = np.stack([gx, gy], axis=-1)
    near = (np.hypot(*(C0[:, None, :] - Q[None, :, :]).transpose(2, 0, 1)) <= reach + EPS).any(axis=1)
    C0 = C0[near]
    if not len(C0):
        return Check("container", FAIL, f"no crane spot on the lot within {reach:g} ft of the container on the truck")
    rects = _corners(C0, np.array(lot.frame.axis), ic.out_l_ft, ic.out_w_ft)
    shapely.prepare(stand)
    fits = shapely.contains(stand, _polys(rects))
    C0, rects = C0[fits], rects[fits]
    if not len(C0):
        return Check("container", FAIL, f"no room for the IC-80's outriggers within {reach:g} ft of the container on the truck")
    put = container_spots(lot.open_lot.difference(working).difference(deck), rules, lot.frame.angle_deg)
    ok_spot = np.zeros(len(C0), dtype=bool)
    if len(put):
        tree = shapely.STRtree(shapely.points(put.centres))
        for i in range(len(C0)):
            idx = tree.query(Point(*C0[i]), predicate="dwithin", distance=reach)
            if len(idx) and _clear_of(rects[i], put.corners[idx]).any():
                ok_spot[i] = True
    dq = np.hypot(*(C0[:, None, :] - Q[None, :, :]).transpose(2, 0, 1))
    served = ((dq <= reach + EPS) & ok_spot[:, None]).any(axis=0)
    if served.all():
        on_lot = shapely.covers(lot.open_lot.buffer(EPS), shapely.polygons(rects))
        need_street = street and not (
            ((dq <= reach + EPS) & (ok_spot & on_lot)[:, None]).any(axis=0).all()
        )
        where = " (the IC-80 in the street for this lift; power lines not checked)" if need_street else ""
        return Check("container", PASS, f"lifted and set within {reach:g} ft{where}")
    return Check(
        "container", FAIL,
        f"{int((~served).sum())} of {len(served)} places it may ride on the truck have no crane spot within "
        f"{reach:g} ft with an open spot beside it",
    )


@dataclass(frozen=True)
class _LoadPick:
    """Where one trailer load parks and how its pieces reach the crane."""

    #: The best status with no tree read (over every place), and the
    #: chosen place's status with the canopy as an obstacle.
    status: Status
    treed: Status
    detail: str
    #: ``lot`` / ``street``, plus `` (carried)`` where any kind is carried;
    #: None where no place serves.
    place: str | None
    deck: Polygon | None
    picks: Mapping[str, float]
    carried: frozenset[str]


#: At most this many trailer spots on the lot get a carry path worked out
#: per load (the best by fewest kinds carried, then shortest pick).
_LOT_CARRY_TRIES = 6


def _ic80_load(
    lot: _Lot, S: np.ndarray, masks: dict[str, np.ndarray], reach: dict[str, float], trucks: Spots,
    kinds: Sequence[Piece], no_carry: Mapping[str, str], street_open: bool,
) -> _LoadPick:
    """One trailer load. A spot serves where every piece of ``kinds``,
    anywhere on the deck, is within its pick reach of a crane spot that
    also sets it (spec 3.5); a kind that is not may be picked at the
    trailer and carried (spec 3.7, slice 4), unless ``no_carry`` names why
    it cannot be. The trailer may also stand in the street at a place not
    measured, every kind then carried. Best: no tree in the way, then the
    best status, then the fewest kinds carried, then on the lot before the
    street ("trailer on site is preferred"), then the shortest farthest
    pick."""
    rules, ic = lot.rules, lot.rules.ic80
    # The kinds that cannot be carried first; each later kind is only
    # worked out on the spots every earlier such kind left standing.
    kinds = sorted(kinds, key=lambda p: p.key not in no_carry)
    by_key = {p.key: p for p in kinds}
    ok: dict[str, np.ndarray] = {}
    picks: dict[str, np.ndarray] = {}
    live = np.ones(len(trucks), dtype=bool)
    first_short: Piece | None = None
    seen: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}
    for p in kinds:
        if p.key not in reach:
            ok[p.key], picks[p.key] = np.zeros(len(trucks), dtype=bool), np.full(len(trucks), np.inf)
        else:
            inset = (p.plan_ft[0] / 2, p.plan_ft[1] / 2)
            key = (inset, reach[p.key], masks[p.key].tobytes(), live.tobytes())
            if key not in seen:
                good = np.zeros(len(trucks), dtype=bool)
                pick = np.full(len(trucks), np.inf)
                Sm = S[masks[p.key]].astype(np.float32)
                idx = np.flatnonzero(live)
                if len(Sm) and len(idx):
                    Q = trucks.take(idx).places_on(rules.deck_l_ft, rules.truck_w_ft, inset, rules.deck_step_ft)
                    for i0 in range(0, len(idx), 128):
                        q = Q[i0 : i0 + 128].astype(np.float32)
                        d = np.sqrt(((q[:, :, None, :] - Sm[None, None, :, :]) ** 2).sum(-1))
                        d = np.where((d >= ic.min_radius_ft - EPS) & (d <= reach[p.key] + EPS), d, np.inf)
                        best = d.min(axis=2)
                        pick[idx[i0 : i0 + 128]] = best.max(axis=1)
                        good[idx[i0 : i0 + 128]] = np.isfinite(best).all(axis=1)
                seen[key] = (good, pick)
            ok[p.key], picks[p.key] = seen[key]
        if p.key in no_carry:
            live = live & ok[p.key]
            if not live.any() and first_short is None:
                first_short = p
    n = len(trucks)
    must = [p.key for p in kinds if p.key in no_carry]
    must_ok = np.all([ok[k] for k in must], axis=0) if must and n else np.ones(n, dtype=bool)
    if picks and n:
        worst = np.array([np.where(ok[k], picks[k], 0.0) for k in picks]).max(axis=0)
        short = np.array([~ok[k] for k in picks]).sum(axis=0)
    else:
        worst = short = np.zeros(n)
    lot_first = (trucks.place != "lot").astype(int) if n else np.zeros(0, dtype=int)
    options: list[tuple[tuple, _LoadPick]] = []
    idx = np.flatnonzero(must_ok)
    order = idx[np.lexsort((worst[idx], lot_first[idx], short[idx]))] if len(idx) else idx
    lot_tries = 0
    street_seen: dict[frozenset[str], tuple[Status, Status, str]] = {}
    for i in order:
        place = str(trucks.place[i])
        carried = frozenset(k for k in picks if not ok[k][i])
        if carried and place == "lot" and lot_tries >= _LOT_CARRY_TRIES:
            continue
        if carried and place != "lot" and carried in street_seen:
            continue  # the same carry from the street; the first had the shorter picks
        deck = Polygon(trucks.corners[i])
        got = {k: float(picks[k][i]) for k in picks if ok[k][i]}
        if not carried:
            options.append(((0, 0, 0, int(lot_first[i]), float(worst[i])),
                            _LoadPick(PASS, PASS, f"at the {place}, every piece within reach", place, deck, got, carried)))
            break  # spots are in order: this is the best
        if place == "lot":
            lot_tries += 1
            st, st_t, why = _carry(lot, S, [by_key[k] for k in sorted(carried)], deck)
        else:
            if carried not in street_seen:
                street_seen[carried] = _carry(lot, S, [by_key[k] for k in sorted(carried)], None)
            st, st_t, why = street_seen[carried]
        names = ", ".join(by_key[k].label.lower() for k in sorted(carried))
        options.append((
            (_ORDER[st_t], _ORDER[st], len(carried), int(lot_first[i]), float(worst[i])),
            _LoadPick(st, st_t, f"at the {place}, {names} picked there and carried: {why}", f"{place} (carried)", deck,
                      got, carried),
        ))
    if "street" in rules.ic80_places and lot.site.street and not any(p.key in no_carry for p in kinds):
        # The trailer in the street at a place not measured: every kind is
        # picked at the trailer and carried.
        carried = frozenset(by_key)
        st, st_t, why = _carry(lot, S, kinds, None)
        # Where it stands is not read, so never better than unmeasured.
        st, st_t = _worst([st, UNMEASURED]), _worst([st_t, UNMEASURED])
        why += "; where the trailer stands is not measured"
        options.append((
            (_ORDER[st_t], _ORDER[st], len(carried), 1, math.inf),
            _LoadPick(st, st_t, f"in the street, every piece picked there and carried: {why}", "street (carried)", None,
                      {}, carried),
        ))
    if options:
        best = min(options, key=lambda o: o[0])[1]
        bare = _best(o[1].status for o in options)
        if _ORDER[bare] < _ORDER[best.status]:
            best = dataclasses.replace(best, status=bare)
        if street_open and FAIL in (best.status, best.treed):
            # A street trailer at a place not measured might still serve.
            best = dataclasses.replace(
                best, status=_best([best.status, UNMEASURED]), treed=_best([best.treed, UNMEASURED]),
                detail=best.detail + "; the street trailer's place is not measured (no street centreline held)",
            )
        return best
    st = UNMEASURED if street_open else FAIL
    if not n:
        return _LoadPick(
            st, st, "no place for the trailer clear of the working ground and within the IC-80's reach"
            + ("; the street trailer's place is not measured (no street centreline held)" if street_open else ""),
            None, None, {}, frozenset(),
        )
    short_p = first_short or next((by_key[k] for k in must), None)
    why = no_carry.get(short_p.key, "") if short_p is not None else ""
    return _LoadPick(
        st, st,
        "no trailer spot has every piece that cannot be carried within the IC-80's reach; "
        f"the first short: {short_p.label if short_p else 'a piece'}" + (f" ({why})" if why else "")
        + ("; the street trailer's place is not measured (no street centreline held)" if street_open else ""),
        None, None, {}, frozenset(),
    )


@dataclass(frozen=True, slots=True)
class TwoParks:
    """Both faces (slice 3c, Steph 2026-11-14, option A): a wall load is
    stacked back walls on top, end and party walls in the middle, front
    walls at the bottom (DECISIONS S-wallstack, FOLLOWUPS 223). The trailer
    parks at the back first and the IC-80 sets the back walls, then the end
    and party walls, from the back face; the trailer then moves once to the
    front and the IC-80 sets the front walls from the front face."""

    first: np.ndarray  # crane spots on the face the trailer parks at first
    then: np.ndarray  # crane spots on the other face
    first_name: str
    then_name: str


@dataclass(frozen=True)
class _Trailer:
    """Every load's park: the worst load's status (no tree read), the loads
    a tree stops, the detail, each load's (place, deck), each kind's pick
    radius (the farthest over its loads), the kinds carried, the loads
    that moved."""

    status: Status
    tree_loads: tuple[int, ...]
    detail: str
    spots: Mapping[int, tuple[str, Polygon | None]]
    picks: Mapping[str, float]
    carried: frozenset[str]
    moved: frozenset[int]


def _ic80_trailer(
    lot: _Lot, S: np.ndarray, masks: dict[str, np.ndarray], reach: dict[str, float], working: BaseGeometry,
    no_carry: Mapping[str, str], two: TwoParks | None = None,
) -> _Trailer:
    """Where each trailer load parks. Steph 2026-11-14: "the empty trailer
    leaves before the new full trailer arrives", so each of the four loads
    takes whichever spot suits it, one after another: on the lot or in the
    street (slice 4). One spot serves the whole of a load, except a wall
    load on both faces (``two``), which may park at the first face and then
    move once to the other."""
    rules = lot.rules
    parts = [s for s, place in ((lot.lot_spots, "lot"), (lot.street_spots, "street")) if place in rules.ic80_places]
    trucks = Spots.join(parts)
    if len(trucks):
        clear = ~shapely.intersects(_polys(trucks.clear), working) & ~shapely.intersects(_polys(trucks.corners), working)
        trucks = trucks.take(clear)
    if len(trucks):
        far_r = max(reach.values()) if reach else 0.0
        centre_d = shapely.distance(shapely.points(trucks.centres), shapely.multipoints(S))
        trucks = trucks.take(centre_d <= far_r + rules.deck_l_ft / 2 + EPS)
    street_open = "street" in rules.ic80_places and bool(lot.site.street) and not lot.street_measured
    loads = sorted({n for p in rules.pieces for n in p.loads})
    statuses: list[Status] = []
    tree_loads: list[int] = []
    details: list[str] = []
    spots: dict[int, tuple[str, Polygon | None]] = {}
    picks: dict[str, float] = {}
    carried: set[str] = set()
    moved: set[int] = set()
    for n in loads:
        kinds = [p for p in rules.pieces if n in p.loads and p.key in reach]
        if not kinds:
            continue
        got = _ic80_load(lot, S, masks, reach, trucks, kinds, no_carry, street_open)
        detail = got.detail
        spot = (got.place, got.deck) if got.place is not None else None
        st, st_t, carry, pk = got.status, got.treed, got.carried, dict(got.picks)
        fronts = [p for p in kinds if p.place == "front_wall"]
        rest = [p for p in kinds if p.place != "front_wall"]
        if two is not None and (st != PASS or st_t != PASS) and fronts and rest:
            # Option A: park at the first face for the back walls, the end
            # and party walls; then move once for the front walls.
            first = {k: m & two.first for k, m in masks.items()}
            then = {k: m & two.then for k, m in masks.items()}
            g1 = _ic80_load(lot, S, first, reach, trucks, rest, no_carry, street_open)
            g2 = _ic80_load(lot, S, then, reach, trucks, fronts, no_carry, street_open)
            st12, t12 = _worst([g1.status, g2.status]), _worst([g1.treed, g2.treed])
            if (_ORDER[t12], _ORDER[st12], len(g1.carried | g2.carried)) < (_ORDER[st_t], _ORDER[st], len(carry)):
                st, st_t, carry, pk = st12, t12, g1.carried | g2.carried, {**g1.picks, **g2.picks}
                detail = (
                    f"parked at the {two.first_name} for the {two.first_name} walls, end and party walls: {g1.detail}; "
                    f"then moved once to the {two.then_name} for the {two.then_name} walls: {g2.detail}"
                )
                spot = (
                    f"{g1.place or 'none'} at the {two.first_name}, then {g2.place or 'none'} at the {two.then_name}",
                    g1.deck,
                ) if g1.place is not None or g2.place is not None else None
                moved.add(n)
        statuses.append(st)
        if _ORDER[st_t] > _ORDER[st]:
            tree_loads.append(n)
        details.append(f"load {n}: {detail}")
        if spot is not None:
            spots[n] = spot
        for k, r in pk.items():
            picks[k] = max(picks.get(k, 0.0), r)
        carried |= carry
    if not statuses:
        return _Trailer(FAIL, (), "no piece can be set", {}, {}, frozenset(), frozenset())
    return _Trailer(_worst(statuses), tuple(tree_loads), "; ".join(details), spots, picks, frozenset(carried),
                    frozenset(moved))


_FrontSets = tuple[list[Lift], dict[str, np.ndarray], dict[str, float], dict[str, float]]


def _ic80_sets(lot: _Lot, S: np.ndarray, su: np.ndarray, fronts: Sequence[int]) -> list[_FrontSets]:
    """Per "front" reading: every piece's set lift from the crane spots
    ``S`` (spec 3.4-3.5), the spots that set each kind, each kind's pick
    reach off the trailer, and each kind's set radius."""
    rules, ic, frame = lot.rules, lot.rules.ic80, lot.frame
    out: list[_FrontSets] = []
    for f in fronts:
        lifts: list[Lift] = []
        masks: dict[str, np.ndarray] = {}
        picks_r: dict[str, float] = {}
        sets: dict[str, float] = {}
        for p in rules.pieces:
            gross = p.weight_lb + ic.rigging_for(p) + ic.hook_lb
            uv = local_points(frame, p, rules.homes, f)
            P = frame.worlds(uv)
            if len(S):
                r_set, d = _set_radius(S, su, P, uv[:, 0], ic, p.points_at_crane)
            else:
                r_set, d = math.inf, np.zeros((0, len(P)))
            R = ic.reach(gross, p.hook_ft)
            sets[p.key] = r_set
            if R is not None:
                masks[p.key] = (d <= R + EPS).any(axis=1)
                picks_r[p.key] = ic.pick_reach(gross) or R
            lifts.append(_ic80_set_lift(ic, rules, p, gross, r_set, R))
        out.append((lifts, masks, picks_r, sets))
    return out


def ic80_plan(lot: _Lot, sides: Sequence[int]) -> IC80Plan:
    """The IC-80 working from the long face(s) ``sides`` (spec section 5,
    step 1 for one face, step 2 for both)."""
    rules, ic, frame, site = lot.rules, lot.rules.ic80, lot.frame, lot.site
    faces = tuple(_face_name(s, lot.front) for s in sides)
    ground = _ic80_ground(frame, ic, sides)
    working = ground["strip"].union(ground["outriggers"])
    obst = site.obstacles
    checks: list[Check] = []

    def on_lot(name: str, geom: BaseGeometry, what: str) -> Check:
        if not _covered(lot.open_lot, geom):
            off = geom.difference(lot.open_lot).area
            return Check(name, FAIL, f"{what} runs {off:,.0f} sq ft off the lot or into the building")
        if obst is not None and geom.intersects(obst):
            return Check(name, FAIL, f"{what} meets another building")
        return Check(name, PASS, what)

    checks.append(on_lot("working strip", ground["strip"], f"{ic.strip_w_ft:g} ft strip along the whole face"))
    checks.append(
        on_lot(
            "outriggers", ground["outriggers"],
            f"outriggers {ic.out_w_ft:.1f} ft wide at {ic.off_face_ft:g} ft off the face (to {ic.off_face_ft + ic.out_w_ft / 2:.1f} ft)",
        )
    )
    swing = ground["swing"]
    if not _covered(site.lot, swing):
        checks.append(Check("swing room", FAIL, f"less than {ic.swing_ft:g} ft beyond a wall end inside the lot"))
    elif obst is not None and swing.intersects(obst):
        checks.append(Check("swing room", FAIL, "another building stands in the swing room"))
    else:
        checks.append(Check("swing room", PASS, f"{ic.swing_ft:g} ft beyond each end, inside the lot"))

    # The crane spots: every step along the face, plus the exact spots a
    # piece's least radius or along-offset asks for.
    fronts = (lot.front,) if lot.front != 0 else (1, -1)
    extra: list[float] = []
    for f in fronts:
        for p in rules.pieces:
            for pu, pv in local_points(frame, p, rules.homes, f):
                for s in sides:
                    dv = abs(s * (frame.depth_ft / 2 + ic.off_face_ft) - pv)
                    du = math.sqrt(max(ic.min_radius_ft**2 - dv**2, 0.0))
                    if p.points_at_crane:
                        du = max(du, ic.along_ft)
                    extra.extend((pu - du, pu + du))
    S_all, su_all = _crane_line(frame, ic, sides, rules.crane_step_ft, extra)
    side_all = np.repeat(np.asarray(sides), len(S_all) // max(len(sides), 1))

    # Level (slice 4, spec 3.9: "Level applies to the crane, not the
    # strip"): only the set-up spots used, each across its own pads. The
    # spots within ~3% first; then those not read (unmeasured); then all.
    grades, cls = _pad_levels(lot, S_all)
    chosen: tuple[np.ndarray, Status, list[_FrontSets]] | None = None
    tried: dict[bytes, list[_FrontSets]] = {}
    for mask, st in ((cls == 0, PASS), (cls <= 1, UNMEASURED), (np.ones(len(S_all), dtype=bool), FAIL)):
        if not mask.any() or mask.tobytes() in tried:
            continue
        got = _ic80_sets(lot, S_all[mask], su_all[mask], fronts)
        tried[mask.tobytes()] = got
        if all(lf.status == PASS for lifts, *_ in got for lf in lifts):
            chosen = (mask, st, got)
            break
    if chosen is None:
        mask = np.ones(len(S_all), dtype=bool)
        st = PASS if (cls == 0).all() else FAIL if (cls == 2).any() else UNMEASURED
        chosen = (mask, st, tried.get(mask.tobytes()) or _ic80_sets(lot, S_all, su_all, fronts))
    use, level_st, lifts_by_front = chosen
    S, side_of = S_all[use], side_all[use]
    used = grades[use]
    pad_grade = float(np.nanmax(used)) if np.isfinite(used).any() else None
    if lot.grade_of is None:
        checks.append(Check("level", UNMEASURED, "no elevation model read"))
    elif level_st == PASS:
        checks.append(Check(
            "level", PASS,
            f"every set-up spot used is within {ic.level_pct:g}% across its pads"
            + (f" (steepest {pad_grade:.2f}%)" if pad_grade is not None else ""),
        ))
    elif level_st == UNMEASURED:
        checks.append(Check(
            "level", UNMEASURED,
            f"{int((cls[use] == 1).sum())} set-up spots needed have pads the elevation model does not cover",
        ))
    else:
        steep = float(np.nanmax(grades[cls == 2])) if (cls == 2).any() else math.nan
        checks.append(Check(
            "level", FAIL,
            f"{int((cls == 2).sum())} of {len(cls)} set-up spots fall more than {ic.level_pct:g}% across their pads "
            f"(steepest {steep:.2f}%), and every piece needs one",
        ))

    # Each "front" reading is tried with the trailer; where the front is not
    # known, the worse governs (the heavier walls may be the far ones).
    results = []
    for f, (lifts, masks, reach, _sets) in zip(fronts, lifts_by_front):
        two = (
            TwoParks(side_of == -f, side_of == f, _face_name(-f, lot.front), _face_name(f, lot.front))
            if len(sides) == 2 else None
        )
        carry_lifts: dict[str, Lift] = {}
        no_carry: dict[str, str] = {}
        for lf in lifts:
            p = rules.piece(lf.key)
            carry_lifts[p.key] = cl = _ic80_carry_lift(ic, rules, p, lf)
            if cl.status != PASS and p.group == "wall" and ic.carry_walls_flat:
                carry_lifts[p.key] = cl = _ic80_carry_lift(ic, rules, p, lf, flat=True)
            if cl.status != PASS:
                no_carry[p.key] = f"carried: {cl.why}"
        tr = _ic80_trailer(lot, S, masks, reach, working, no_carry, two)
        final: list[Lift] = []
        for lf in lifts:
            p = rules.piece(lf.key)
            if lf.status != PASS:
                final.append(lf)
            elif lf.key in tr.carried:
                # The carry (on rubber) and the set (on outriggers): the
                # harder of the two governs.
                cl = carry_lifts[lf.key]
                final.append(max((cl, dataclasses.replace(lf, carried=True)),
                                 key=lambda x: (_ORDER[x.status], x.pct_of_chart or 0.0)))
            elif lf.key in tr.picks and math.isfinite(tr.picks[lf.key]):
                final.append(
                    _lift(ic.set_chart, "piece", p.key, p.label, p.count, lf.gross_lb, tr.picks[lf.key], lf.set_ft,
                          rules.max_pct)
                )
            else:
                final.append(lf)
        walls = [lf for lf in final if rules.piece(lf.key).group == "wall" and lf.capacity_lb and not lf.carried]
        limit = (
            min(lf.capacity_lb * rules.max_pct / 100.0 - rules.piece(lf.key).weight_lb - ic.hook_lb for lf in walls)  # type: ignore[operator]
            if walls else None
        )
        lift_status = _worst(lf.status for lf in final)
        hardest = max((lf.pct_of_chart or 0.0) for lf in final) if final else 0.0
        stack = _stack_order(lot, sides, f, set(tr.moved))
        results.append((tr, final, limit, lift_status, lifts, hardest, stack))
    results.sort(key=lambda r: (_ORDER[_worst([r[0].status, r[3]])], bool(r[0].tree_loads), r[5]), reverse=True)
    tr, final, limit, lift_status, set_lifts, _, stack = results[0]
    checks.append(Check("trailer", tr.status, tr.detail))
    checks.append(_ic80_route(lot, ground, S if len(S) else S_all))
    bad = [lf for lf in final if lf.status != PASS]
    checks.append(
        Check(
            "lifts", lift_status,
            "; ".join(f"{lf.label}: {lf.why}" for lf in bad) if bad else f"every lift within {rules.max_pct:g}% of the chart",
        )
    )
    bare = _worst(c.status for c in checks)
    trees = site.trees
    if trees is not None:
        if not trees.covered:
            checks.append(Check("trees", UNMEASURED, f"the {trees.source} does not cover the lot"))
        else:
            over = 0.0 if trees.canopy.is_empty else trees.canopy.intersection(working.union(swing)).area
            if over > 1.0:
                checks.append(Check(
                    "trees", FAIL,
                    f"canopy over {over:,.0f} sq ft of the working ground or swing room ({trees.source}; "
                    "no height read, so any canopy blocks)",
                ))
            elif tr.tree_loads:
                checks.append(Check(
                    "trees", FAIL,
                    "canopy on every carry path of load " + " and ".join(str(n) for n in tr.tree_loads)
                    + f" ({trees.source}; no height read, so any canopy blocks)",
                ))
            else:
                checks.append(Check("trees", PASS, "no canopy in the working ground, swing room or carry path"))
    first = tr.spots.get(min(tr.spots)) if tr.spots else None
    load1 = tr.spots.get(1)
    carried_any = any(lf.carried for lf in final)
    return IC80Plan(
        faces=faces,
        checks=tuple(checks),
        lifts=tuple(final),
        status=_worst(c.status for c in checks),
        working=working,
        truck=first[0] if first else None,
        truck_spot=first[1] if first else None,
        trailer_spots={k: v[0] for k, v in sorted(tr.spots.items())},
        pad_grade_pct=pad_grade,
        rigging_limit_lb=limit,
        sets=tuple(set_lifts),
        container=_ic80_container(lot, working.union(swing), load1[1] if load1 else None,
                                  load1[0] if load1 else None),
        stack=stack,
        setup="site",
        bare_status=bare,
        extra_notes=(
            ((CARRY_POWER_NOTE.format(ft=ic.carry_power_ft),) if carried_any else ())
            + ((STREET_POWER_NOTE,) if any(v[0].startswith("street") for v in tr.spots.values()) else ())
        ),
    )


def _stack_order(lot: _Lot, sides: Sequence[int], f: int, moved: set[int]) -> str:
    """The wall-load stack (spec 3.5, DECISIONS S-wallstack: "far-face
    walls on top", FOLLOWUPS 223). One face: the far face's walls on top,
    so from the back the stack is flipped (front walls on top). Both faces:
    the trailer parks at the back first, so the back walls are on top."""
    if len(sides) == 2:
        top, bottom = _face_name(-f, lot.front), _face_name(f, lot.front)
    else:
        top, bottom = _face_name(-sides[0], lot.front), _face_name(sides[0], lot.front)
    text = f"{top} walls on top, end and party walls in the middle, {bottom} walls at the bottom"
    if moved:
        text += f"; the trailer moves once, {top} to {bottom} (load{'s' if len(moved) > 1 else ''} " + \
            " and ".join(str(n) for n in sorted(moved)) + ")"
    return text


def with_wall_gear(rules: Rules, case: str) -> Rules:
    """``rules`` with the walls lifted on the ``ic80.wall_gear_lb`` case
    (``light`` / ``heavy``)."""
    return dataclasses.replace(rules, ic80=dataclasses.replace(rules.ic80, wall_rigging_lb=rules.ic80.wall_gear_lb[case]))


def _ic80_set_lift(ic: IC80, rules: Rules, p: Piece, gross: float, r_set: float, R: float | None) -> Lift:
    if not math.isfinite(r_set):
        return Lift("piece", p.key, p.label, p.count, gross, math.nan, r_set, r_set, None, None, None, None, None,
                    False, FAIL, "no crane spot on the face can set it")
    hook = ic.hook_at(r_set)
    short = "" if hook is not None and hook >= p.hook_ft - EPS else (
        f"the hook reaches {hook:g} ft at {r_set:.1f} ft; it needs {p.hook_ft:g} ft"
        if hook is not None else f"no hook height is printed at {r_set:.1f} ft"
    )
    return _lift(ic.set_chart, "piece", p.key, p.label, p.count, gross, 0.0, r_set, rules.max_pct, extra_fail=short)


def with_carry(rules: Rules, *, walls_flat: bool | None = None) -> Rules:
    """``rules`` with the slice-4b carry switch set (None keeps the
    config's): ``walls_flat`` = walls may be carried flat and crosswise
    (spec 3.7, hanging on FOLLOWUPS 215(a))."""
    ic = rules.ic80
    return dataclasses.replace(rules, ic80=dataclasses.replace(
        ic, carry_walls_flat=ic.carry_walls_flat if walls_flat is None else walls_flat,
    ))


def _ic80_carry_lift(ic: IC80, rules: Rules, p: Piece, set_lift: Lift, *, flat: bool = False,
                     across: bool = False) -> Lift:
    """A piece carried straight ahead over the front, on rubber, the
    extension off (spec 3.7 at 9985b64), read on the carry chart at the
    spec's hook radius: a cassette flat and crosswise (10.8-11.1 ft for
    64-72 in wide, 12.1 ft for the 96 in FULL4; lengthwise, the spec's
    no, is not tried); a wall upright and edge-on (18.1 / 20.2 ft), or
    flat and crosswise where ``flat`` (12.1 ft). ``across``: the 360 deg
    column (the route falls across). A bundle rides the cargo deck. The
    path is the trailer check's; the set itself is the set lift's."""
    if p.group == "bundle":
        return dataclasses.replace(set_lift, carried=True, why="rides the cargo deck")
    if p.group == "cassette":
        w = p.short_hi_ft
        key = "cassette_crosswise" if w <= 6.0 + EPS else "cassette_crosswise_96_in" if w <= 8.0 + EPS else ""
        if not key:
            return _lift(ic.carry_chart, "piece", p.key, p.label + " (carried)", p.count, 0.0, math.inf, 0.0,
                         rules.max_pct, carried=True, extra_fail=f"no carry radius printed for a {w:g} ft wide panel")
    elif flat:
        key = "wall_flat_crosswise"
    else:
        key = "wall_24_ft" if p.plan_ft[0] >= 24 - EPS else "wall_20_ft"
    r = ic.carry_radius_ft[key]
    gross = p.weight_lb + ic.rigging_for(p) + ic.hook_lb
    return _lift(ic.carry_chart_360 if across else ic.carry_chart, "piece", p.key, p.label + " (carried)", p.count,
                 gross, r, 0.0, rules.max_pct, carried=True)


# --------------------------------------------------------------------------
# Step 3: the 45 t on site, then in the street (slice 2, retuned to spec 4)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Kinds:
    """Every lift kind the 45 t makes in one mode: what, key, label, count,
    gross lb, how its radius is found, and the farthest it may be."""

    what: tuple[str, ...]
    keys: tuple[str, ...]
    labels: tuple[str, ...]
    counts: tuple[int | None, ...]
    gross: np.ndarray
    #: ``far`` (picked off the deck where its centre stands farthest, set at
    #: ``set_ft``) or ``stack`` (a whole load: lifted and landed where it
    #: rode, at the farthest its centre can stand).
    radius: tuple[str, ...]
    set_ft: np.ndarray
    inset: tuple[tuple[float, float], ...]
    max_r: np.ndarray


def _kinds45(crane: Crane45, rules: Rules, mode: str, set_ft: np.ndarray, container_ft: float) -> _Kinds:
    what, keys, labels, counts, gross, how, sets, inset, cap = [], [], [], [], [], [], [], [], []
    hook = crane.ball_lb
    for p, s in zip(rules.pieces, set_ft):
        what.append("piece")
        keys.append(p.key)
        labels.append(p.label)
        counts.append(p.count)
        gross.append(p.weight_lb + crane.rigging_lb + hook)
        how.append("far")
        sets.append(s)
        inset.append((p.plan_ft[0] / 2, p.plan_ft[1] / 2))
        cap.append(crane.max_piece_radius_ft)
    # Spec 4.5: "Site container (load 1) | ~4,600 lb [est] | ~5,600 lb";
    # "The container is taken with ~300 lb of slings [est]", and the ball.
    what.append("container")
    keys.append("site_container")
    labels.append(rules.container_label)
    counts.append(1)
    gross.append(rules.container_lb + crane.container_sling_lb + hook)
    how.append("far")
    sets.append(container_ft)
    inset.append((rules.container_fp[0] / 2, rules.container_fp[1] / 2))
    cap.append(crane.max_piece_radius_ft)
    if mode == "whole_load":
        for w in rules.whole_loads:
            what.append("whole_load")
            keys.append(w.key)
            labels.append(w.label)
            counts.append(1)
            gross.append(crane.whole_gross(w.stack_lb))
            how.append("stack")
            sets.append(0.0)
            inset.append((w.length_ft / 2, rules.truck_w_ft / 2))
            cap.append(w.within_ft)
    return _Kinds(
        tuple(what), tuple(keys), tuple(labels), tuple(counts), np.array(gross),
        tuple(how), np.array(sets, dtype=float), tuple(inset), np.array(cap, dtype=float),
    )


def _radii(kinds: _Kinds, sp: Spots, cor: np.ndarray, rules: Rules) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(pick, set, governing) radii, (S, K), on truck spots ``sp`` from the
    axis ``cor``."""
    S, K = len(sp), len(kinds.what)
    pick = np.empty((S, K))
    setr = np.empty((S, K))
    for k, how in enumerate(kinds.radius):
        far = sp.far_ft(cor, rules.deck_l_ft, rules.truck_w_ft, kinds.inset[k])
        pick[:, k] = far
        setr[:, k] = far if how == "stack" else kinds.set_ft[k]
    return pick, setr, np.maximum(pick, setr)


def _score(crane: Crane45, kinds: _Kinds, gov: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per spot: worst status order (0 pass, 1 unmeasured, 2 fail) and the
    highest share of the planning line any lift uses."""
    cap = crane.chart.capacities(gov)
    cap = np.where(gov > kinds.max_r[None, :] + EPS, 0.0, cap)
    allowed = cap * crane.chart.max_pct / 100.0
    with np.errstate(divide="ignore", invalid="ignore"):
        use = np.where(allowed > 0, kinds.gross[None, :] / allowed, np.inf)
    use = np.where(np.isnan(cap), np.nan, use)
    fail = (use > 1.0 + EPS).any(axis=1)
    unmeas = np.isnan(use).any(axis=1)
    order = np.where(fail, 2, np.where(unmeas, 1, 0))
    worst = np.nanmax(np.where(np.isnan(use), -np.inf, use), axis=1)
    return order, worst


def _lifts45(crane: Crane45, rules: Rules, kinds: _Kinds, pick: np.ndarray, setr: np.ndarray, why: Sequence[str]) -> tuple[Lift, ...]:
    return tuple(
        _lift(
            crane.chart, kinds.what[k], kinds.keys[k], kinds.labels[k], kinds.counts[k], float(kinds.gross[k]),
            float(pick[k]), float(setr[k]), rules.max_pct, max_r=float(kinds.max_r[k]),
            why_unmeasured=why[k],
        )
        for k in range(len(kinds.what))
    )


def _access(centre: np.ndarray, axis: np.ndarray, drivable: BaseGeometry, street_zone: BaseGeometry, reach_ft: float) -> str:
    """How the crane's centreline gets from the pad to the street."""
    c = Point(*centre)
    parts = [p for p in shapely.get_parts(drivable) if p.distance(c) < 1e-3]
    if not parts:
        return NONE
    part = parts[0]
    for sign in (1.0, -1.0):
        end = centre + sign * axis * reach_ft
        ray = LineString([tuple(centre), tuple(end)]).intersection(part)
        for piece in shapely.get_parts(ray):
            if piece.distance(c) < 1e-3 and piece.intersects(street_zone):
                return STRAIGHT
    return BENDS if part.intersects(street_zone) else NONE


def _cor(crane: Crane45, centre: np.ndarray, u: np.ndarray) -> np.ndarray:
    along, across = crane.rotation_offset_ft
    return centre + u * along + np.array([-u[1], u[0]]) * across


def _landings(lot: _Lot, trucks: Spots) -> dict[str, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]:
    """Per whole load, on each trailer spot: the stack's two farthest
    places (the deck's ends less half the stack), and whether the landing
    area fits on open ground there: (plus centre, plus fits, minus centre,
    minus fits)."""
    rules = lot.rules
    ground = lot.open_lot
    shapely.prepare(ground)
    out = {}
    for w in rules.whole_loads:
        h = max(rules.deck_l_ft / 2 - w.length_ft / 2, 0.0)
        got = []
        for sign in (1.0, -1.0):
            c = trucks.centres + sign * h * trucks.axis
            corners = _corners(c, trucks.axis, w.landing_ft[0], w.landing_ft[1])
            got.extend([c, shapely.contains(ground, _polys(corners))])
        out[w.key] = tuple(got)  # type: ignore[assignment]
    return out


def _plans45(
    lot: _Lot, crane: Crane45, setup: Literal["site", "street"], pads: Sequence[tuple[np.ndarray, np.ndarray, str]],
    sets: list[np.ndarray], containers: Spots,
) -> tuple[list[Plan], list[str]]:
    """The best plan on each pad in ``pads`` (centre, unit along the pad,
    access), best first."""
    rules = lot.rules
    why: list[str] = []
    curb_spots, curb_measured = _curbs_for(lot, setup)
    trucks = Spots.join(
        [s for s, place in ((lot.lot_spots, "lot"), (curb_spots, "curb")) if place in rules.places]
    )
    if not len(trucks):
        why.append(
            "no place for the delivery truck: none backs onto the lot"
            + ("" if curb_measured else ", and the curb in front is not measured")
        )
        return [], why
    land = _landings(lot, trucks)
    best: dict[int, tuple[tuple, Plan]] = {}
    for pi, pad in enumerate(pads):
        centre, u, access = pad[0], pad[1], pad[2]
        pad_source = pad[3] if len(pad) > 3 else None
        cor = _cor(crane, centre, u)
        pad_c = _corners(centre[None], u, crane.pad_l_ft, crane.pad_w_ft)[0]
        set_ft = np.array([float(np.hypot(*(s - cor).T).max()) for s in sets])
        ok = _clear_of(pad_c, trucks.clear)
        if not ok.any():
            continue
        sp = trucks.take(ok)
        far = np.sqrt(((sp.corners - cor) ** 2).sum(-1)).max(axis=1)
        if len(containers):
            c_ok = _clear_of(pad_c, containers.corners)
        else:
            c_ok = np.zeros(0, dtype=bool)
        if c_ok.any():
            cc = containers.take(c_ok)
            cfar = np.hypot(*(cc.centres - cor).T)
            ci = int(np.argmin(cfar))
            c_ft, c_poly = float(cfar[ci]), Polygon(cc.corners[ci])
        else:
            c_ft, c_poly = math.inf, None
        # Whole loads land where the trailer stood, on the lot only, the
        # landing area on open ground clear of the pad.
        wl_ok = sp.place == "lot"
        for w in rules.whole_loads:
            pc, pf, mc, mf = (a[ok] for a in land[w.key])
            plus_far = np.hypot(*(pc - cor).T) >= np.hypot(*(mc - cor).T)
            c = np.where(plus_far[:, None], pc, mc)
            fits = np.where(plus_far, pf, mf)
            rects = _corners(c, sp.axis, w.landing_ft[0], w.landing_ft[1])
            wl_ok = wl_ok & fits & _clear_of(pad_c, rects)
        for mode in ("whole_load", "off_trailer"):
            pick_ok = np.ones(len(sp), dtype=bool) if mode == "off_trailer" else wl_ok
            if not pick_ok.any():
                continue
            kinds = _kinds45(crane, rules, mode, set_ft, c_ft)
            sub = sp.take(pick_ok)
            pick, setr, gov = _radii(kinds, sub, cor, rules)
            order, worst = _score(crane, kinds, gov)
            if not math.isfinite(c_ft):
                order = np.maximum(order, 1)
            street = np.array([str(q).startswith("curb") for q in sub.place], dtype=int) + (1 if setup == "street" else 0)
            rank = np.lexsort((far[pick_ok], worst, street, order))
            i = int(rank[0])
            notes = ["" for _ in kinds.what]
            if not math.isfinite(c_ft):
                notes[kinds.what.index("container")] = "no open spot for the site container near the crane"
            lifts = _lifts45(crane, rules, kinds, pick[i], setr[i], notes)
            own = _worst([_worst(lf.status for lf in lifts), PASS if access == STRAIGHT else UNMEASURED])
            plan = Plan(
                crane=crane.short,
                setup=setup,
                pad=Polygon(pad_c),
                axis=(float(cor[0]), float(cor[1])),
                access=access,
                mode=mode,  # type: ignore[arg-type]
                truck=str(sub.place[i]),  # type: ignore[arg-type]
                truck_spot=Polygon(sub.corners[i]),
                container_spot=c_poly,
                lifts=lifts,
                status=own,
                width_source=_width_source(pad_source, str(sub.place[i])),
            )
            key = (
                _ORDER[own],
                int(street[i]),
                ("whole_load", "off_trailer").index(mode),
                float(worst[i]) if math.isfinite(worst[i]) else math.inf,
                float(far[pick_ok][i]),
            )
            if pi not in best or key < best[pi][0]:
                best[pi] = (key, plan)
    if not best:
        why.append("no truck spot is clear of every crane pad")
        return [], why
    return [p for _, p in sorted(best.values(), key=lambda t: t[0])], why


def _curbs_for(lot: _Lot, setup: str) -> tuple[Spots, bool]:
    """The curb truck spots a set-up may use: measured only on site; with
    estimates filled in for the street set-up (FOLLOWUPS 145 part B)."""
    if setup == "street" and lot.curb_spots_est is not None:
        return lot.curb_spots_est, bool(lot.curb_measured_est)
    return lot.curb_spots, lot.curb_measured


def _width_source(pad_source: str | None, truck_place: str) -> str | None:
    """A plan's width label: estimated where the pad's width or the truck's
    curb rests on an estimate, else the pad's measured source."""
    if pad_source is not None and pad_source.startswith(WIDTH_ESTIMATED):
        return pad_source
    if truck_place == CURB_EST:
        return WIDTH_ESTIMATED
    return pad_source


def _site_pads(lot: _Lot, crane: Crane45, sets: list[np.ndarray]) -> tuple[list[tuple[np.ndarray, np.ndarray, str]], list[str]]:
    """On-site pads the 45 t drives to, best first: straight drives, then
    the shortest farthest set radius; at most ``pads_kept``."""
    site, rules = lot.site, lot.rules
    ground = lot.open_lot
    gx, gy = _grid(ground, rules.pad_grid_ft)
    shapely.prepare(ground)
    cand: list[tuple[float, np.ndarray, np.ndarray]] = []
    allsets = np.concatenate(sets)
    for ang in _angles(lot.frame.angle_deg, rules.pad_angle_step_deg):
        u = np.array([math.cos(ang), math.sin(ang)])
        c = np.stack([gx, gy], axis=-1)
        corners = _corners(c, u, crane.pad_l_ft, crane.pad_w_ft)
        ok = np.flatnonzero(shapely.contains(ground, _polys(corners)))
        if not len(ok):
            continue
        far = np.sqrt(((allsets[None, :, :] - c[ok][:, None, :]) ** 2).sum(-1)).max(axis=1)
        cand.extend((float(f), c[i], u) for f, i in zip(far, ok))
    if not cand:
        return [], [f"no {crane.pad_w_ft:g} x {crane.pad_l_ft:g} ft pad fits on open ground beside the building"]
    cand.sort(key=lambda t: t[0])
    half = crane.body_w_ft / 2
    aprons = _aprons(site, APRON_FT)
    drivable = site.lot.union(aprons).difference(site.building).buffer(-half + EPS)
    street_zone = aprons.difference(site.lot.buffer(half + 0.5))
    span = math.hypot(*(np.subtract(site.lot.bounds[2:], site.lot.bounds[:2]))) + APRON_FT + 1.0
    straight: list[tuple[np.ndarray, np.ndarray, str]] = []
    bends: list[tuple[np.ndarray, np.ndarray, str]] = []
    for _, c, u in cand:
        got = _access(c, u, drivable, street_zone, span)
        if got == STRAIGHT:
            straight.append((c, u, got))
            if len(straight) >= rules.pads_kept:
                break
        elif got == BENDS and len(bends) < rules.pads_kept:
            bends.append((c, u, got))
    pads = (straight + bends)[: rules.pads_kept]
    if not pads:
        return [], [f"no pad is reached by the {crane.short} truck ({crane.body_w_ft:.2f} ft wide) from the street with the building in place"]
    return pads, []


def _est_label(src: np.ndarray, width: np.ndarray, flag: np.ndarray) -> str:
    """The estimate label of a pad's three readings: the narrowest
    estimated one's (it names the standard the width came from)."""
    i = int(np.argmin(np.where(flag, width, np.inf)))
    return str(src[i]) or WIDTH_ESTIMATED


def _basis(label: str) -> str:
    """What an estimate label rests on (``estimated:<basis>``)."""
    return label.partition(":")[2]


def _street_pads(lot: _Lot, crane: Crane45, sets: list[np.ndarray]) -> tuple[list[tuple[np.ndarray, np.ndarray, str, str]], Status, list[str]]:
    """Pads in the street in front of the lot: along a street lot line, the
    near side at the near curb, where the pavement width holds the pad's
    width under the pad's two ends and middle. Each pad carries where its
    width came from; a measured pad is always tried before an estimated
    one (FOLLOWUPS 145 part B)."""
    site, rules = lot.site, lot.rules
    if site.street_reading is None:
        return [], UNMEASURED, ["the street in front is not measured (no curb or width data)"]
    pads: list[tuple[np.ndarray, np.ndarray, str, str]] = []
    narrowest: float | None = None
    narrowest_est = ""
    any_measured = False
    for a, d, n, length in _segments(site):
        us = _along(length, rules.street_step_ft)
        pts = np.concatenate(
            [a + np.clip(us + k, 0, length)[:, None] * d for k in (-crane.pad_l_ft / 2, 0.0, crane.pad_l_ft / 2)]
        )
        curb, width, src = _street_read(site, pts, estimates=True)
        curb, width, src = curb.reshape(3, -1), width.reshape(3, -1), src.reshape(3, -1)
        ok = np.isfinite(curb).all(axis=0) & np.isfinite(width).all(axis=0)
        if not ok.any():
            continue
        any_measured = True
        w = width.min(axis=0)
        flag = is_estimated(src)
        est = flag.any(axis=0)
        top = int(np.flatnonzero(ok)[np.argmax(w[ok])])
        if narrowest is None or float(w[top]) > narrowest:
            narrowest = float(w[top])
            narrowest_est = _est_label(src[:, top], width[:, top], flag[:, top]) if est[top] else ""
        fits = ok & (w >= crane.pad_w_ft - EPS)
        for j in np.flatnonzero(fits):
            off = float(curb[:, j].max())
            centre = a + us[j] * d + n * (off + crane.pad_w_ft / 2)
            source = _est_label(src[:, j], width[:, j], flag[:, j]) if est[j] else str(src[1, j])
            pads.append((centre, d.copy(), STRAIGHT, source))
    if not any_measured:
        return [], UNMEASURED, ["the street's pavement width in front is not recorded"]
    if not pads:
        basis = _basis(narrowest_est)
        how = f" (estimated off the right-of-way{': ' + basis if basis else ''})" if narrowest_est else ""
        return [], FAIL, [
            f"the street in front is {narrowest:.0f} ft wide at most{how}; the {crane.short} pad needs {crane.pad_w_ft:g} ft"
        ]
    pads.sort(key=lambda t: (t[3].startswith(WIDTH_ESTIMATED), float(max(np.hypot(*(s - t[0]).T).max() for s in sets))))
    return pads[: rules.pads_kept], PASS, []


def _attempt45(lot: _Lot, setup: Literal["site", "street"], sets: list[np.ndarray], containers: Spots) -> Attempt:
    crane = lot.rules.t45
    step = f"45t_{setup}"
    if setup == "site":
        pads, why = _site_pads(lot, crane, sets)
        if not pads:
            return Attempt(step, FAIL, None, tuple(why))
    else:
        pads, st, why = _street_pads(lot, crane, sets)
        if not pads:
            return Attempt(step, st, None, tuple(why))
    plans, why2 = _plans45(lot, crane, setup, pads, sets, containers)
    curb_open = "curb" in lot.rules.places and not _curbs_for(lot, setup)[1]
    if not plans:
        status: Status = UNMEASURED if curb_open else FAIL
        if curb_open and not any("not measured" in w for w in why2):
            why2.append("the curb in front is not measured; a truck there might serve")
        return Attempt(step, status, None, tuple(why + why2))
    plan = _level45(lot, crane, plans)
    reasons = list(why + why2)
    for lf in plan.lifts:
        if lf.status != PASS:
            reasons.append(f"{lf.label}: {lf.why}")
    if plan.access == BENDS:
        reasons.append("the crane's way in needs bends; turning not checked (unmeasured)")
    if plan.level != PASS and plan.status != FAIL:
        reasons.append(
            "the pad's fall is not read" if plan.slope_pct is None
            else f"the best pads fall more than {crane.level_pct:g}% (this one {plan.slope_pct:.2f}%)"
        )
    status = _worst([plan.status, plan.level])
    if status == FAIL and curb_open:
        status = UNMEASURED
        reasons.append("the curb in front is not measured; a truck there might be nearer")
    return Attempt(step, status, plan, tuple(reasons))


def _level45(lot: _Lot, crane: Crane45, plans: list[Plan]) -> Plan:
    """The best plan whose pad is level within the spec's 1% (4.6), among
    the best ``pads_graded`` that pass otherwise; the best plan, marked,
    where none is graded level."""
    first = plans[0]
    if lot.grade_of is None:
        return dataclasses.replace(first, level=UNMEASURED)
    graded: Plan | None = None
    for plan in [p for p in plans if p.status == PASS][: lot.rules.pads_graded] or plans[:1]:
        g = lot.grade_of(plan.pad)
        got = dataclasses.replace(
            plan, slope_pct=g, level=UNMEASURED if g is None else (PASS if g <= crane.level_pct + EPS else FAIL)
        )
        if got.level == PASS:
            return got
        if graded is None:
            graded = got
    return graded if graded is not None else first


# --------------------------------------------------------------------------
# The ladder
# --------------------------------------------------------------------------


def _ic80_attempt(lot: _Lot, sides: Sequence[int], step: str) -> Attempt:
    plan = ic80_plan(lot, sides)
    why = tuple(f"{c.name}: {c.detail}" for c in plan.checks if c.status != PASS)
    return Attempt(step, plan.status, plan, why)


def report(
    site: Site,
    rules: Rules | None = None,
    *,
    grade_of: Callable[[BaseGeometry], float | None] | None = None,
) -> Report:
    """Which crane sets the pod on ``site``, and how (spec section 5).

    ``grade_of`` is the fall across a polygon, percent (the screen's
    :meth:`flats.fit.slope.Terrain.grade` ``.pct``): each IC-80 set-up
    spot's pads ~3%, the 45 t's pad 1%. Without it, level is unmeasured
    and no step passes on it."""
    rules = rules or load_rules()
    frame = pod_frame(site.building)
    why: list[str] = []
    if abs(frame.length_ft / rules.homes - round(frame.length_ft / rules.homes)) > 0.5:
        why.append(f"drawn pod {frame.length_ft:.1f} ft long is not {rules.homes} whole homes")
    open_lot = site.lot.difference(site.building)
    if site.obstacles is not None:
        open_lot = open_lot.difference(site.obstacles)
    curb, curb_measured = curb_truck_spots(site, rules)
    front = _front(site, frame)
    lot = _Lot(
        site=site,
        rules=rules,
        frame=frame,
        front=front,
        open_lot=open_lot,
        lot_spots=lot_truck_spots(site, rules) if "lot" in rules.places else Spots.empty(),
        curb_spots=curb if "curb" in rules.places else Spots.empty(),
        curb_measured=curb_measured,
        grade_of=grade_of,
    )
    if "curb" in rules.places:
        lot.curb_spots_est, lot.curb_measured_est = curb_truck_spots(site, rules, estimates=True)
    if "street" in rules.ic80_places:
        lot.street_spots, lot.street_measured = street_truck_spots(site, rules)
    sides = (front, -front) if front else (1, -1)
    attempts: list[Attempt] = []
    won: Attempt | None = None
    # Step 1: one long face, the front first (spec 3.5: "Front is the
    # default"); both faces are reported.
    for s, step in zip(sides, ("ic80_front", "ic80_back")):
        got = _ic80_attempt(lot, (s,), step)
        attempts.append(got)
        if got.status == PASS and won is None:
            won = got
    later: list[tuple[str, Callable[[], Attempt]]] = [
        ("ic80_both", lambda: _ic80_attempt(lot, sides, "ic80_both")),
    ]
    sets45 = [set_points(frame, p, rules.homes, 0) for p in rules.pieces]
    holder: dict[str, Spots] = {}

    def containers() -> Spots:
        if "c" not in holder:
            holder["c"] = container_spots(open_lot, rules, frame.angle_deg)
        return holder["c"]

    later.append(("45t_site", lambda: _attempt45(lot, "site", sets45, containers())))
    later.append(("45t_street", lambda: _attempt45(lot, "street", sets45, containers())))
    for step, run in later:
        if won is not None:
            attempts.append(Attempt(step, NOT_TRIED))
            continue
        got = run()
        attempts.append(got)
        if got.status == PASS:
            won = got
    for a in attempts:
        if a is won:
            break
        if a.status in (FAIL, UNMEASURED):
            why.extend(f"{_step_words(a.step, front)}: {w}" for w in a.why)
    # The answer with the canopy left out: the first step that passes bare
    # (trees only ever add a fail, so it is at or before the real answer).
    bare = [(a, a.plan.bare_status if isinstance(a.plan, IC80Plan) and a.plan.bare_status else a.status)
            for a in attempts if a.status != NOT_TRIED]
    won_bare = next((a for a, st in bare if st == PASS), None)
    no_trees = _result_of(won_bare) if won_bare is not None else (
        UNMEASURED_ANSWER if any(st == UNMEASURED for _, st in bare) else NOT_VIABLE
    )
    if won is not None:
        plan = won.plan
        assert plan is not None
        face = plan.faces[0] if won.step in ("ic80_front", "ic80_back") else None  # type: ignore[union-attr]
        return Report(_result_of(won), face, plan, tuple(attempts), tuple(why), notes=plan.notes,
                      result_no_trees=no_trees)
    statuses = [a.status for a in attempts]
    answer = UNMEASURED_ANSWER if UNMEASURED in statuses else NOT_VIABLE
    shown = [a for a in attempts if a.plan is not None]
    shown.sort(key=lambda a: _ORDER.get(str(a.status), 3))
    plan = shown[0].plan if shown else None
    return Report(answer, None, plan, tuple(attempts), tuple(why), notes=plan.notes if plan else (POWER_NOTE,),
                  result_no_trees=no_trees)


def _result_of(a: Attempt) -> str:
    if a.step in ("ic80_front", "ic80_back"):
        return f"{IC80_ONE} ({a.plan.faces[0]})"  # type: ignore[union-attr]
    if a.step == "45t_street" and isinstance(a.plan, Plan) and str(a.plan.width_source or "").startswith(WIDTH_ESTIMATED):
        return T45_STREET_EST
    return {"ic80_both": IC80_BOTH, "45t_site": T45_SITE}.get(a.step, T45_STREET)


def _step_words(step: str, front: int) -> str:
    a, b = ("front", "back") if front else ("long face 1", "long face 2")
    return {
        "ic80_front": f"IC-80 one face ({a})",
        "ic80_back": f"IC-80 one face ({b})",
        "ic80_both": IC80_BOTH,
        "45t_site": T45_SITE,
        "45t_street": T45_STREET,
    }[step]


def site_from_drawing(
    lot: BaseGeometry,
    drawing: Mapping[str, Any],
    street: Sequence[tuple[float, float, float, float]],
    street_reading: StreetReading | None = None,
) -> Site | None:
    """A :class:`Site` from the screen's drawing JSON (:meth:`Drawing.to_json`):
    None where the drawing has no building that fits."""
    ring = drawing.get("building")
    if not drawing.get("fits") or not ring or len(ring) < 4:
        return None
    return Site(lot, Polygon(ring), tuple(street), street_reading)


def centre_reader(centrelines: np.ndarray, max_gap_ft: float) -> CentreReading:
    """A :data:`CentreReading`: each point's distance to its nearest street
    centreline (:func:`flats.fit.fire.truck_lines`); NaN past
    ``max_gap_ft``."""
    tree = shapely.STRtree(centrelines) if len(centrelines) else None

    def read(points: np.ndarray) -> np.ndarray:
        pts = np.asarray(points, dtype=float).reshape(-1, 2)
        out = np.full(len(pts), np.nan)
        if tree is None or not len(pts):
            return out
        geoms = shapely.points(pts)
        idx = tree.nearest(geoms)
        gap = shapely.distance(geoms, centrelines[idx])
        live = gap <= max_gap_ft
        out[live] = gap[live]
        return out

    return read


def street_reader(edges: Any, centrelines: np.ndarray, max_gap_ft: float) -> StreetReading:
    """A :data:`StreetReading` from the screen's own street data: the near
    curb (:meth:`flats.geom.curbs.StreetEdges.near`) and the recorded
    pavement width (:meth:`flats.geom.curbs.StreetEdges.width_beside`) at
    the foot of each point's nearest truck centreline
    (:func:`flats.fit.fire.truck_lines`). NaN past ``max_gap_ft`` from any
    centreline or where neither is recorded."""
    tree = shapely.STRtree(centrelines)

    def read(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        pts = np.asarray(points, dtype=float).reshape(-1, 2)
        n = len(pts)
        curb = np.full(n, np.nan)
        width = np.full(n, np.nan)
        if not n or edges is None or not len(centrelines):
            return curb, width
        geoms = shapely.points(pts)
        idx = tree.nearest(geoms)
        lines = centrelines[idx]
        feet = shapely.get_coordinates(
            shapely.line_interpolate_point(lines, shapely.line_locate_point(lines, geoms))
        )
        gap = np.hypot(*(feet - pts).T)
        near, _ = edges.near(pts, feet, lines)
        wide = edges.width_beside(feet, lines)
        live = gap <= max_gap_ft
        curb[live] = near[live]
        width[live] = wide[live]
        return curb, width

    return read


__all__ = [
    "Attempt",
    "CentreReading",
    "Chart",
    "Check",
    "Crane45",
    "IC80",
    "IC80Plan",
    "IC80_BOTH",
    "IC80_ONE",
    "Lift",
    "NOT_CHECKED",
    "NOT_TRIED",
    "NOT_VIABLE",
    "POWER_NOTE",
    "Piece",
    "Plan",
    "PodFrame",
    "Reading",
    "Report",
    "Rules",
    "STEPS",
    "Site",
    "Spots",
    "StreetReading",
    "T45_SITE",
    "T45_STREET",
    "T45_STREET_EST",
    "WIDTH_ESTIMATED",
    "is_estimated",
    "Trees",
    "UNMEASURED_ANSWER",
    "box",
    "container_spots",
    "curb_truck_spots",
    "ic80_plan",
    "load_rules",
    "local_points",
    "lot_truck_spots",
    "parse_range",
    "parse_size",
    "parse_weight",
    "pod_frame",
    "report",
    "rules_from",
    "set_points",
    "centre_reader",
    "site_from_drawing",
    "street_reader",
    "street_truck_spots",
    "with_carry",
]
