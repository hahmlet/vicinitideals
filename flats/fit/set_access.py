"""Where a mobile crane can set up on a lot, and can it make every lift
(FOLLOWUPS 145, Steph 2026-11-11).

For one lot with the pod already placed by the screen (the drawing's
building, :mod:`flats.fit.draw`), this answers:

1. **Pads.** Every 28 x 40 ft setup pad (``crane.pad``) that stands on open
   ground -- the lot (and the street right of way where
   ``street_setup_allowed``) less the building -- on a grid, at angles off
   the building's long axis. Setbacks are ignored (Steph).
2. **Access.** The crane is ``crane.body`` wide; its centreline must stay
   half that inside open ground with the building in place (the exit, after
   the pod is up, is the harder trip). A straight drive along the pad's
   length to a street lot line is a measured way in; a way that needs bends
   is unmeasured (the 40 ft turning search, :mod:`flats.fit.turning`, is not
   run here); none is a fail.
3. **Slope.** The fall across the pad from the DEM the screen already reads
   (``grade_of``, :meth:`flats.fit.slope.Terrain.grade`), against
   ``crane.max_pad_slope_pct`` -- unset, so unmeasured.
4. **Radii.** From the pad's axis of rotation: every stack is picked off the
   truck (at the street frontage nearest the crane) and set on a landing spot
   (the open spot whose far corner is nearest); every single piece is picked
   from its stack's landing spot and set where it goes in the pod. A load's
   governing radius is the longer of its pick and its set (ASME B30.5
   5-3.2.1.1(c)), over every piece of it. :class:`Pad` holds them all, so a
   chart can be checked later without the geometry (:func:`check_lifts`).
5. **Lifts.** Per chart: gross load (piece + rigging + hook block +
   deductions) against the chart's capacity at the governing radius, read at
   the next longer listed radius. Pass / fail / unmeasured, the binding lift,
   and slack in pounds and in feet of radius.

Power-line clearance (29 CFR 1926.1408; FOLLOWUPS 144) and the boom's
height over the building are not checked: both are reported unmeasured, so
no lot passes outright in this slice. Nothing here is wired into the screen;
the hook is :func:`flats.ingest.quadfit.slope_checked` (see
``flats/config/set_access.yaml``). Pure geometry and arithmetic: shapely and
numpy, no database, nothing from :mod:`app`.

Coordinates are the lot's working CRS (EPSG:2913, feet).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence

import numpy as np
import shapely
import yaml
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "set_access.yaml"

Status = Literal["pass", "fail", "unmeasured"]
PASS: Status = "pass"
FAIL: Status = "fail"
UNMEASURED: Status = "unmeasured"

#: How far into the street the crane is taken to have arrived: a centreline
#: point at least this far past a street lot line (beyond half the body) is
#: on the street. Long enough for any street, short enough to stay in it.
APRON_FT = 30.0
#: Geometry slack, feet.
EPS = 1e-6
#: Landing candidates tested per vectorised batch, nearest first.
LANDING_BATCH = 512
#: Access answers.
STRAIGHT = "straight"
BENDS = "bends"
NONE = "none"


# --------------------------------------------------------------------------
# Printed figures
# --------------------------------------------------------------------------

_FT_IN = re.compile(r"""^\s*(?:(\d+(?:\.\d+)?)\s*')?\s*(?:(\d+(?:\.\d+)?)\s*")?\s*$""")


def _length(token: str) -> float:
    """``8'1"`` -> 8.083, ``15.5"`` -> 1.292, ``40`` -> 40 (a bare number is
    feet, as Steph prints them)."""
    t = token.strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        return float(t)
    m = _FT_IN.match(t)
    if not m or (m.group(1) is None and m.group(2) is None):
        raise ValueError(f"not a printed length: {token!r}")
    return float(m.group(1) or 0.0) + float(m.group(2) or 0.0) / 12.0


def parse_range(text: str) -> tuple[float, float]:
    """A printed length or length range: ``4'-4'3.5"`` -> (4.0, 4.29)."""
    t = text.strip()
    parts = re.split(r"(?<=['\"\d])\s*-\s*(?=\d)", t)
    if len(parts) == 1:
        v = _length(parts[0])
        return v, v
    if len(parts) != 2:
        raise ValueError(f"not a printed range: {text!r}")
    lo, hi = _length(parts[0]), _length(parts[1])
    return min(lo, hi), max(lo, hi)


def parse_size(text: str | None) -> tuple[tuple[float, float], ...] | None:
    """``40 x 8'1" x 6'1"`` -> ((40, 40), (8.08, 8.08), (6.08, 6.08))."""
    if text is None:
        return None
    t = re.sub(r"\s*ft\s*$", "", str(text).strip())
    return tuple(parse_range(p) for p in re.split(r"\s+x\s+", t))


def parse_weight(text: Any) -> tuple[float, float] | None:
    """``"12,074"`` -> (12074, 12074); ``"711-724"``; ``"~4,100"``; None."""
    if text is None:
        return None
    t = str(text).replace(",", "").replace("~", "").strip()
    parts = [float(p) for p in t.split("-")]
    if len(parts) not in (1, 2):
        raise ValueError(f"not a printed weight: {text!r}")
    return min(parts), max(parts)


# --------------------------------------------------------------------------
# Rules
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Load:
    """One kind of lift: ``count`` identical lifts of ``weight_lb`` (the high
    printed figure, riders included)."""

    key: str
    label: str
    #: ``stack``: truck -> landing spot. ``single``: landing spot -> pod.
    kind: Literal["stack", "single"]
    count: int
    weight_lb: float
    #: Parts with no printed weight: the gross is a lower bound.
    unweighed: tuple[str, ...] = ()
    #: Plan footprint (long, short) where it lands -- stacks only.
    footprint_ft: tuple[float, float] | None = None
    #: The stack a single piece is picked from.
    source: str | None = None
    set_at: str | None = None
    #: The narrowest printed width (cassettes: the inset from each end).
    min_width_ft: float = 0.0


@dataclass(frozen=True, slots=True)
class Chart:
    """One crane configuration's load chart, as printed."""

    key: str
    hook_block_lb: float | None
    deductions_lb: float
    max_pct: float
    #: One column per boom length: ((radius_ft, capacity_lb), ...), radius rising.
    booms: tuple[tuple[tuple[float, float], ...], ...]

    def capacity_at(self, radius_ft: float) -> float | None:
        """Rated capacity at ``radius_ft``, the best boom's NEXT LONGER listed
        radius (never interpolated). 0 past every column's last radius; None
        where the radius is inside every column's first one (the chart says
        nothing)."""
        best: float | None = None
        for rows in self.booms:
            if radius_ft < rows[0][0] - EPS:
                continue
            cap = 0.0
            for r, c in rows:
                if r >= radius_ft - EPS:
                    cap = c
                    break
            best = cap if best is None else max(best, cap)
        return best

    def reach_for(self, gross_lb: float) -> float | None:
        """The longest listed radius at which ``gross_lb`` is still within the
        planning ceiling, over every boom; None where it is nowhere."""
        far: float | None = None
        for rows in self.booms:
            for r, c in rows:
                if c * self.max_pct / 100.0 >= gross_lb - EPS:
                    far = r if far is None else max(far, r)
        return far


@dataclass(frozen=True, slots=True)
class Rules:
    pad_w_ft: float
    pad_l_ft: float
    body_w_ft: float
    body_l_ft: float
    street_setup_allowed: bool
    max_pad_slope_pct: float | None
    rotation_offset_ft: tuple[float, float]
    pad_grid_ft: float
    pads_kept: int
    pad_angle_step_deg: float
    landing_grid_ft: float
    landing_angle_step_deg: float
    homes: int
    truck_offset_ft: float | None
    landing_fallback: str | None
    rigging_lb: float
    verify_weight_over_pct: float
    loads: tuple[Load, ...]
    charts: tuple[Chart, ...]

    def load(self, key: str, kind: str | None = None) -> Load:
        for ld in self.loads:
            if ld.key == key and (kind is None or ld.kind == kind):
                return ld
        raise KeyError(key)

    @property
    def stacks(self) -> tuple[Load, ...]:
        return tuple(ld for ld in self.loads if ld.kind == "stack")

    @property
    def singles(self) -> tuple[Load, ...]:
        return tuple(ld for ld in self.loads if ld.kind == "single")


def _footprint(size: tuple[tuple[float, float], ...]) -> tuple[float, float]:
    """A stack's plan: its two longest dimensions (it may lie either way)."""
    dims = sorted((hi for _, hi in size), reverse=True)
    return dims[0], dims[1]


def _chart(key: str, raw: Mapping[str, Any], default_pct: float) -> Chart:
    booms: list[tuple[tuple[float, float], ...]] = []
    for col in raw.get("booms") or []:
        rows = tuple(sorted((float(r), float(c)) for r, c in col["rows"]))
        if not rows:
            raise ValueError(f"chart {key}: a boom column with no rows")
        for (_, a), (_, b) in zip(rows, rows[1:]):
            if b > a + EPS:
                raise ValueError(f"chart {key}: capacity rises with radius")
        booms.append(rows)
    if not booms:
        raise ValueError(f"chart {key}: no boom columns")
    hook = raw.get("hook_block_lb")
    pct = raw.get("max_pct_of_chart")
    return Chart(
        key=key,
        hook_block_lb=None if hook is None else float(hook),
        deductions_lb=float(sum((raw.get("deductions_lb") or {}).values())),
        max_pct=default_pct if pct is None else float(pct),
        booms=tuple(booms),
    )


def rules_from(raw: Mapping[str, Any]) -> Rules:
    """Parse the printed config (``set_access.yaml``) into figures."""
    crane, search = raw["crane"], raw["search"]
    pad_w, pad_l = (hi for _, hi in parse_size(crane["pad"]) or ())
    rig = raw["rigging"]
    pick = 1 if rig.get("use", "high") == "high" else 0
    rigging = sum(parse_weight(rig[f"{name}_lb"])[pick] for name in rig["per_lift"])  # type: ignore[index]
    lifts = raw.get("lifts") or {}
    default_pct = (
        100.0
        if lifts.get("max_pct_of_chart") is None
        else float(lifts["max_pct_of_chart"])
    )

    stacks_raw: Mapping[str, Any] = raw.get("stacks") or {}
    loads: list[Load] = []
    for key, s in stacks_raw.items():
        size = parse_size(s.get("size"))
        if size is None and s.get("size_like"):
            size = parse_size(stacks_raw[s["size_like"]].get("size"))
        weight = parse_weight(s["weight_lb"])
        total = weight[1] if weight else 0.0
        unweighed: list[str] = [] if weight else [s["label"]]
        for rider in s.get("with") or []:
            each = parse_weight(rider.get("each_lb"))
            if each is None:
                unweighed.append(str(rider["label"]))
            else:
                total += each[1] * int(rider.get("count", 1))
        loads.append(
            Load(
                key=key,
                label=s["label"],
                kind="stack",
                count=int(s.get("count", 1)),
                weight_lb=total,
                unweighed=tuple(unweighed),
                footprint_ft=None if size is None else _footprint(size),
            )
        )
    for key, s in (raw.get("singles") or {}).items():
        size = parse_size(s.get("size"))
        weight = parse_weight(s["weight_lb"])
        min_w = 0.0
        if size is not None and len(size) >= 2:
            min_w = size[1][0]
        if s["from"] not in stacks_raw:
            raise ValueError(f"single {key}: unknown stack {s['from']!r}")
        loads.append(
            Load(
                key=key,
                label=s["label"],
                kind="single",
                count=int(s.get("count", 1)),
                weight_lb=0.0 if weight is None else weight[1],
                unweighed=() if weight else (s["label"],),
                source=s["from"],
                set_at=s["set_at"],
                min_width_ft=min_w,
            )
        )
    off = crane.get("rotation_offset_ft") or {}
    return Rules(
        pad_w_ft=pad_w,
        pad_l_ft=pad_l,
        body_w_ft=float(crane["body"]["width_in"]) / 12.0,
        body_l_ft=float(crane["body"]["length_ft"]),
        street_setup_allowed=bool(crane.get("street_setup_allowed", False)),
        max_pad_slope_pct=None
        if crane.get("max_pad_slope_pct") is None
        else float(crane["max_pad_slope_pct"]),
        rotation_offset_ft=(
            float(off.get("along", 0.0)),
            float(off.get("across", 0.0)),
        ),
        pad_grid_ft=float(search["pad_grid_ft"]),
        pads_kept=int(search["pads_kept"]),
        pad_angle_step_deg=float(search["pad_angle_step_deg"]),
        landing_grid_ft=float(search["landing_grid_ft"]),
        landing_angle_step_deg=float(search["landing_angle_step_deg"]),
        homes=int(raw["pod"]["homes"]),
        truck_offset_ft=(
            None
            if raw["truck"].get("bed_centre_past_lot_line_ft") is None
            else float(raw["truck"]["bed_centre_past_lot_line_ft"])
        ),
        landing_fallback=(raw.get("landing") or {}).get("fallback_when_no_room"),
        rigging_lb=float(rigging),
        verify_weight_over_pct=float(lifts.get("verify_weight_over_pct", 75)),
        loads=tuple(loads),
        charts=tuple(
            _chart(k, v, default_pct) for k, v in (raw.get("charts") or {}).items()
        ),
    )


@lru_cache(maxsize=4)
def load_rules(path: Path = RULES_PATH) -> Rules:
    return rules_from(yaml.safe_load(path.read_text(encoding="utf-8")))


# --------------------------------------------------------------------------
# The pod's pieces
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PodFrame:
    """The drawn building as a frame: centre, long-axis unit vector, size."""

    centre: tuple[float, float]
    axis: tuple[float, float]
    length_ft: float
    depth_ft: float

    def world(self, u: float, v: float) -> tuple[float, float]:
        (cx, cy), (ax, ay) = self.centre, self.axis
        return cx + u * ax - v * ay, cy + u * ay + v * ax

    @property
    def angle_deg(self) -> float:
        return math.degrees(math.atan2(self.axis[1], self.axis[0]))


def pod_frame(building: BaseGeometry) -> PodFrame:
    """The building's minimum rotated rectangle: its long side is the pod's
    length (the long walls, front and back), its short side the depth -- both
    read off the drawing, never assumed."""
    rect = shapely.minimum_rotated_rectangle(building)
    xy = np.asarray(rect.exterior.coords)[:4]
    e1, e2 = xy[1] - xy[0], xy[2] - xy[1]
    a, b = float(np.hypot(*e1)), float(np.hypot(*e2))
    long_vec, length, depth = (e1, a, b) if a >= b else (e2, b, a)
    unit = long_vec / np.hypot(*long_vec)
    c = xy.mean(axis=0)
    return PodFrame(
        (float(c[0]), float(c[1])), (float(unit[0]), float(unit[1])), length, depth
    )


def set_points(frame: PodFrame, load: Load, homes: int) -> list[tuple[float, float]]:
    """Where a single piece's centre may end up, world coordinates. The
    farthest of them from the crane is the piece's set radius."""
    L, D = frame.length_ft, frame.depth_ft
    h = L / homes
    if load.set_at == "long_walls":
        local = [
            (-L / 2 + (i + 0.5) * h, s * D / 2) for i in range(homes) for s in (-1, 1)
        ]
    elif load.set_at == "short_walls":
        local = [(-L / 2 + (i + j) * h, 0.0) for i in range(homes) for j in (0, 1)]
    elif load.set_at == "centreline":
        inset = load.min_width_ft / 2
        local = [(-L / 2 + inset, 0.0), (L / 2 - inset, 0.0)]
    elif load.set_at == "footprint":
        local = [(su * L / 2, sv * D / 2) for su in (-1, 1) for sv in (-1, 1)]
    else:
        raise ValueError(f"{load.key}: unknown set_at {load.set_at!r}")
    return [frame.world(u, v) for u, v in local]


# --------------------------------------------------------------------------
# The site
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Site:
    """One lot with the pod placed: the lot, the drawn building, and the lot
    lines on a street ``(x1, y1, x2, y2)``. ``right_of_way`` is the street
    land a pad may use where ``street_setup_allowed``."""

    lot: BaseGeometry
    building: BaseGeometry
    street: Sequence[tuple[float, float, float, float]]
    right_of_way: BaseGeometry | None = None


def _outward(seg: tuple[float, float, float, float], lot: BaseGeometry) -> np.ndarray:
    x1, y1, x2, y2 = seg
    d = np.array([x2 - x1, y2 - y1], dtype=float)
    n = np.array([-d[1], d[0]]) / max(np.hypot(*d), EPS)
    mid = np.array([(x1 + x2) / 2, (y1 + y2) / 2])
    probe = Point(*(mid + n * 0.5))
    return -n if lot.covers(probe) else n


def _aprons(site: Site, depth: float) -> BaseGeometry:
    """The street just outside each street lot line, ``depth`` deep."""
    parts = []
    for seg in site.street:
        x1, y1, x2, y2 = seg
        if math.hypot(x2 - x1, y2 - y1) < EPS:
            continue
        n = _outward(seg, site.lot) * depth
        parts.append(
            Polygon(
                [(x1, y1), (x2, y2), (x2 + n[0], y2 + n[1]), (x1 + n[0], y1 + n[1])]
            )
        )
    if not parts:
        return Polygon()
    return shapely.union_all(parts).difference(site.lot)


def _rects(
    cx: np.ndarray, cy: np.ndarray, ang: np.ndarray, length: float, width: float
) -> tuple[np.ndarray, np.ndarray]:
    """Rectangles ``length`` along angle ``ang`` (radians) by ``width``,
    centred on (cx, cy), as an array of polygons; and their corners."""
    ux, uy = np.cos(ang), np.sin(ang)
    hl, hw = length / 2, width / 2
    corners = np.stack(
        [
            np.stack(
                [cx + su * hl * ux - sv * hw * uy, cy + su * hl * uy + sv * hw * ux],
                axis=-1,
            )
            for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))
        ],
        axis=1,
    )
    return shapely.polygons(corners), corners


def _grid(geom: BaseGeometry, step: float) -> tuple[np.ndarray, np.ndarray]:
    x0, y0, x1, y1 = geom.bounds
    xs = np.arange(x0 + step / 2, x1, step)
    ys = np.arange(y0 + step / 2, y1, step)
    gx, gy = np.meshgrid(xs, ys)
    return gx.ravel(), gy.ravel()


def _angles(base_deg: float, step_deg: float) -> np.ndarray:
    n = max(1, int(round(180.0 / step_deg)))
    return np.radians(base_deg + np.arange(n) * step_deg)


@dataclass(frozen=True)
class _Spots:
    """Every place one stack footprint fits on open ground."""

    centres: np.ndarray
    corners: np.ndarray


def _landing_spots(
    open_lot: BaseGeometry, fp: tuple[float, float], rules: Rules, base_deg: float
) -> _Spots:
    gx, gy = _grid(open_lot, rules.landing_grid_ft)
    keep_c: list[np.ndarray] = []
    keep_k: list[np.ndarray] = []
    shapely.prepare(open_lot)
    for a in _angles(base_deg, rules.landing_angle_step_deg):
        rects, corners = _rects(gx, gy, np.full(gx.shape, a), fp[0], fp[1])
        ok = shapely.contains(open_lot, rects)
        keep_c.append(np.stack([gx[ok], gy[ok]], axis=-1))
        keep_k.append(corners[ok])
    if not keep_c:
        return _Spots(np.zeros((0, 2)), np.zeros((0, 4, 2)))
    return _Spots(np.concatenate(keep_c), np.concatenate(keep_k))


def _clear_of(pad: np.ndarray, rects: np.ndarray) -> np.ndarray:
    """Which of ``rects`` (N, 4, 2 corners) stand clear of the convex
    ``pad`` (4, 2): a separating axis among the edge normals of each pair.
    Touching is not clear."""

    def normals(c: np.ndarray) -> np.ndarray:
        e = np.stack(
            [c[..., 1, :] - c[..., 0, :], c[..., 2, :] - c[..., 1, :]], axis=-2
        )
        return np.stack([-e[..., 1], e[..., 0]], axis=-1)

    n = len(rects)
    axes = np.concatenate(
        [np.broadcast_to(normals(pad), (n, 2, 2)), normals(rects)], axis=1
    )
    pa = np.einsum("kd,nad->nak", pad, axes)
    pb = np.einsum("nkd,nad->nak", rects, axes)
    gap = (pa.max(-1) < pb.min(-1) - EPS) | (pb.max(-1) < pa.min(-1) - EPS)
    return gap.any(axis=1)


def _land(
    spots: _Spots, cor: np.ndarray, pad: np.ndarray
) -> tuple[float, float] | None:
    """(centre radius, far-corner radius) of the spot off the pad (corners)
    whose far corner is nearest the axis of rotation; None where none is."""
    if len(spots.centres) == 0:
        return None
    far = np.sqrt(((spots.corners - cor) ** 2).sum(axis=-1)).max(axis=1)
    order = np.argsort(far, kind="stable")
    for i in range(0, len(order), LANDING_BATCH):
        idx = order[i : i + LANDING_BATCH]
        clear = _clear_of(pad, spots.corners[idx])
        if clear.any():
            j = idx[int(np.argmax(clear))]
            return float(np.hypot(*(spots.centres[j] - cor))), float(far[j])
    return None


def _truck_ft(site: Site, cor: np.ndarray, offset: float) -> float | None:
    """Radius to the load on the truck: the street lot line point nearest
    the crane, ``offset`` out into the street."""
    best: float | None = None
    for seg in site.street:
        x1, y1, x2, y2 = seg
        p, q = np.array([x1, y1]), np.array([x2, y2])
        d = q - p
        dd = float(d @ d)
        if dd < EPS:
            continue
        t = float(np.clip((cor - p) @ d / dd, 0.0, 1.0))
        foot = p + t * d + _outward(seg, site.lot) * offset
        r = float(np.hypot(*(foot - cor)))
        best = r if best is None else min(best, r)
    return best


# --------------------------------------------------------------------------
# Results
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Reach:
    """One load's radii from one pad."""

    kind: Literal["stack", "single"]
    load: str
    pick_ft: float | None
    set_ft: float | None
    #: The truck's offset past the lot line is unset: ``pick_ft`` is the least
    #: it can be.
    pick_lower_bound: bool = False
    #: Picked straight off the truck (no landing spot; ``landing.fallback``).
    off_truck: bool = False

    @property
    def governing_ft(self) -> float | None:
        if self.pick_ft is None or self.set_ft is None:
            return None
        return max(self.pick_ft, self.set_ft)


@dataclass(frozen=True)
class Pad:
    """One place the crane can set up, and every radius it lifts at."""

    polygon: BaseGeometry
    centre: tuple[float, float]
    angle_deg: float
    access: str
    slope_pct: float | None
    slope: Status
    reach: tuple[Reach, ...]

    @property
    def farthest_ft(self) -> float:
        got = [r.governing_ft for r in self.reach if r.governing_ft is not None]
        return max(got) if got else math.inf

    def envelope(self) -> dict[str, float | None]:
        """Each load's governing radius: what a chart is checked against."""
        return {f"{r.kind}:{r.load}": r.governing_ft for r in self.reach}


@dataclass(frozen=True, slots=True)
class Lift:
    kind: Literal["stack", "single"]
    load: str
    count: int
    gross_lb: float
    gross_lower_bound: bool
    radius_ft: float | None
    radius_lower_bound: bool
    capacity_lb: float | None
    slack_lb: float | None
    radius_slack_ft: float | None
    pct_of_chart: float | None
    verify_weight: bool
    status: Status
    why: str = ""


@dataclass(frozen=True)
class LiftCheck:
    chart: str | None
    status: Status
    lifts: tuple[Lift, ...]
    binding: Lift | None
    why: str = ""


@dataclass(frozen=True)
class Result:
    """The lot's answer: every check's status, the best pad, the pads."""

    status: Status
    checks: dict[str, Status]
    why: list[str]
    best: Pad | None
    best_lifts: LiftCheck | None
    pads: tuple[Pad, ...] = field(default=())


def _worst(statuses: Iterable[Status]) -> Status:
    s = list(statuses)
    if FAIL in s:
        return FAIL
    if UNMEASURED in s:
        return UNMEASURED
    return PASS


# --------------------------------------------------------------------------
# Lifts against a chart
# --------------------------------------------------------------------------


def check_lifts(pad: Pad, rules: Rules, chart: Chart | None) -> LiftCheck:
    """Every load's farthest lift at ``pad`` against ``chart``."""
    if chart is None:
        return LiftCheck(None, UNMEASURED, (), None, "no load chart loaded")
    lifts: list[Lift] = []
    for reach in pad.reach:
        load = rules.load(reach.load, reach.kind)
        gross = (
            load.weight_lb
            + rules.rigging_lb
            + (chart.hook_block_lb or 0.0)
            + chart.deductions_lb
        )
        gross_lb_only = bool(load.unweighed) or chart.hook_block_lb is None
        r = reach.governing_ft
        why: list[str] = []
        if load.unweighed:
            why.append("no weight for " + ", ".join(load.unweighed))
        if chart.hook_block_lb is None:
            why.append("chart gives no hook block weight")
        if r is None:
            lifts.append(
                Lift(
                    reach.kind,
                    load.key,
                    load.count,
                    gross,
                    gross_lb_only,
                    None,
                    False,
                    None,
                    None,
                    None,
                    None,
                    False,
                    UNMEASURED,
                    "; ".join(why + ["no landing spot"]),
                )
            )
            continue
        cap = chart.capacity_at(r)
        if cap is None:
            lifts.append(
                Lift(
                    reach.kind,
                    load.key,
                    load.count,
                    gross,
                    gross_lb_only,
                    r,
                    reach.pick_lower_bound,
                    None,
                    None,
                    None,
                    None,
                    False,
                    UNMEASURED,
                    "; ".join(why + ["inside the chart's least radius"]),
                )
            )
            continue
        allowed = cap * chart.max_pct / 100.0
        far = chart.reach_for(gross)
        pct = None if cap <= 0 else 100.0 * gross / cap
        if allowed < gross - EPS:
            status: Status = FAIL
        elif gross_lb_only or reach.pick_lower_bound:
            status = UNMEASURED
            if reach.pick_lower_bound:
                why.append("truck position past the lot line unset")
        else:
            status = PASS
        lifts.append(
            Lift(
                kind=reach.kind,
                load=load.key,
                count=load.count,
                gross_lb=gross,
                gross_lower_bound=gross_lb_only,
                radius_ft=r,
                radius_lower_bound=reach.pick_lower_bound,
                capacity_lb=cap,
                slack_lb=allowed - gross,
                radius_slack_ft=None if far is None else far - r,
                pct_of_chart=pct,
                verify_weight=pct is not None and pct > rules.verify_weight_over_pct,
                status=status,
                why="; ".join(why),
            )
        )
    status = _worst(lf.status for lf in lifts)
    measured = [lf for lf in lifts if lf.slack_lb is not None]
    binding = min(measured, key=lambda lf: lf.slack_lb) if measured else None  # type: ignore[arg-type,return-value]
    return LiftCheck(chart.key, status, tuple(lifts), binding)


def _lift_rank(check: LiftCheck) -> tuple[int, float, float]:
    """Best first: status, then binding slack (lb), then radius slack (ft)."""
    order = {PASS: 0, UNMEASURED: 1, FAIL: 2}[check.status]
    b = check.binding
    slack = -(b.slack_lb if b and b.slack_lb is not None else -math.inf)
    rslack = -(b.radius_slack_ft if b and b.radius_slack_ft is not None else -math.inf)
    return order, slack, rslack


# --------------------------------------------------------------------------
# The solve
# --------------------------------------------------------------------------


def _access(
    centre: np.ndarray,
    axis: np.ndarray,
    drivable: BaseGeometry,
    street_zone: BaseGeometry,
    reach_ft: float,
) -> str:
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


def solve(
    site: Site,
    rules: Rules | None = None,
    *,
    grade_of: Callable[[BaseGeometry], float | None] | None = None,
) -> Result:
    """Where the crane can set up on ``site`` and whether it makes every lift.

    ``grade_of`` is the fall across a polygon, percent (the screen's
    :meth:`flats.fit.slope.Terrain.grade` ``.pct``); None where it is not
    measured.
    """
    rules = rules or load_rules()
    why: list[str] = []
    checks: dict[str, Status] = {}
    building = site.building
    frame = pod_frame(building)
    if abs(frame.length_ft / rules.homes - round(frame.length_ft / rules.homes)) > 0.5:
        why.append(
            f"drawn pod {frame.length_ft:.1f} ft long is not {rules.homes} whole homes"
        )

    open_lot = site.lot.difference(building)
    pad_ground = open_lot
    drive_ground = site.lot.union(_aprons(site, APRON_FT))
    if rules.street_setup_allowed and site.right_of_way is not None:
        pad_ground = pad_ground.union(site.right_of_way.difference(building))
        drive_ground = drive_ground.union(site.right_of_way)
    drive_ground = drive_ground.difference(building)
    half = rules.body_w_ft / 2
    drivable = drive_ground.buffer(-half + EPS)
    street_zone = _aprons(site, APRON_FT).difference(site.lot.buffer(half + 0.5))
    lot_span = (
        math.hypot(*(np.subtract(site.lot.bounds[2:], site.lot.bounds[:2])))
        + APRON_FT
        + 1.0
    )

    # 1. Pads that stand on open ground.
    gx, gy = _grid(pad_ground, rules.pad_grid_ft)
    shapely.prepare(pad_ground)
    cand: list[tuple[Polygon, np.ndarray, float]] = []
    corners_of: dict[int, np.ndarray] = {}
    for a in _angles(frame.angle_deg, rules.pad_angle_step_deg):
        rects, corners = _rects(
            gx, gy, np.full(gx.shape, a), rules.pad_l_ft, rules.pad_w_ft
        )
        ok = np.flatnonzero(shapely.contains(pad_ground, rects))
        for i in ok:
            corners_of[id(rects[i])] = corners[i]
            cand.append((rects[i], np.array([gx[i], gy[i]]), float(a)))
    if not cand:
        checks["pad_room"] = FAIL
        why.append(
            f"no {rules.pad_w_ft:g} x {rules.pad_l_ft:g} ft pad fits on open ground beside the building"
        )
        return Result(FAIL, checks, why, None, None)
    checks["pad_room"] = PASS

    # 2. Access, 3. slope.
    kept: list[tuple[Polygon, np.ndarray, float, str, float | None, Status]] = []
    access_seen: set[str] = set()
    for poly, centre, a in cand:
        axis = np.array([math.cos(a), math.sin(a)])
        got = _access(centre, axis, drivable, street_zone, lot_span)
        access_seen.add(got)
        if got == NONE:
            continue
        pct = None if grade_of is None else grade_of(poly)
        if pct is None or rules.max_pad_slope_pct is None:
            slope: Status = UNMEASURED
        else:
            slope = PASS if pct <= rules.max_pad_slope_pct + EPS else FAIL
        kept.append((poly, centre, a, got, pct, slope))
    if not kept:
        checks["access"] = FAIL
        why.append(
            f"no pad is reached by a {rules.body_w_ft:.2f} ft path from the street with the building in place"
        )
        return Result(FAIL, checks, why, None, None)
    live = [k for k in kept if k[5] != FAIL]
    if not live:
        checks["access"] = PASS if STRAIGHT in access_seen else UNMEASURED
        checks["slope"] = FAIL
        why.append(f"every reachable pad is steeper than {rules.max_pad_slope_pct}%")
        return Result(FAIL, checks, why, None, None)

    # 4. Radii.
    # Spots per footprint (stacks of one shape share them), and only the
    # pads_kept pads with the shortest radii the landing cannot shorten
    # (truck and set radii) get the landing search.
    by_fp: dict[tuple[float, float], _Spots] = {}
    for s in rules.stacks:
        if s.footprint_ft is not None and s.footprint_ft not in by_fp:
            by_fp[s.footprint_ft] = _landing_spots(
                open_lot, s.footprint_ft, rules, frame.angle_deg
            )
    sets = {s.key: set_points(frame, s, rules.homes) for s in rules.singles}
    offset = rules.truck_offset_ft
    along, across = rules.rotation_offset_ft

    def cor_of(centre: np.ndarray, a: float) -> np.ndarray:
        return (
            centre
            + np.array([math.cos(a), math.sin(a)]) * along
            + np.array([-math.sin(a), math.cos(a)]) * across
        )

    def floor_ft(k: tuple) -> tuple[int, float]:
        cor = cor_of(k[1], k[2])
        far = max(
            math.hypot(x - cor[0], y - cor[1]) for pts in sets.values() for x, y in pts
        )
        truck = _truck_ft(site, cor, offset or 0.0)
        acc = 0 if k[3] == STRAIGHT else 1
        return acc, max(far, truck if truck is not None else 0.0)

    live = sorted(live, key=floor_ft)[: rules.pads_kept]
    pads: list[Pad] = []
    for poly, centre, a, got, pct, slope in live:
        cor = cor_of(centre, a)
        truck = _truck_ft(site, cor, offset or 0.0)
        pad_corners = corners_of[id(poly)]
        reach: list[Reach] = []
        landed: dict[str, tuple[float, float] | None] = {}
        for s in rules.stacks:
            spot = (
                _land(by_fp[s.footprint_ft], cor, pad_corners)
                if s.footprint_ft in by_fp
                else None
            )
            landed[s.key] = spot
            if spot is None and rules.landing_fallback == "truck" and truck is not None:
                reach.append(
                    Reach("stack", s.key, truck, truck, offset is None, off_truck=True)
                )
            elif spot is None:
                reach.append(Reach("stack", s.key, truck, None, offset is None))
            else:
                reach.append(Reach("stack", s.key, truck, spot[0], offset is None))
        for s in rules.singles:
            far_set = max(math.hypot(x - cor[0], y - cor[1]) for x, y in sets[s.key])
            spot = landed.get(s.source or "")
            if spot is None and rules.landing_fallback == "truck" and truck is not None:
                reach.append(
                    Reach(
                        "single", s.key, truck, far_set, offset is None, off_truck=True
                    )
                )
            elif spot is None:
                reach.append(Reach("single", s.key, None, far_set))
            else:
                reach.append(Reach("single", s.key, spot[1], far_set))
        pads.append(
            Pad(
                poly,
                (float(cor[0]), float(cor[1])),
                math.degrees(a),
                got,
                pct,
                slope,
                tuple(reach),
            )
        )

    # 5. Lifts. Every pad under every chart; the best pad is the one whose
    # own checks come out best (access, slope and lifts on the SAME pad),
    # then the most slack on its binding lift, then the shortest farthest
    # lift (the only ranking left with no chart).
    charts: Sequence[Chart | None] = rules.charts or (None,)
    scored = []
    for p in pads:
        for c in charts:
            chk = check_lifts(p, rules, c)
            own = _worst(
                [PASS if p.access == STRAIGHT else UNMEASURED, p.slope, chk.status]
            )
            order = {PASS: 0, UNMEASURED: 1, FAIL: 2}[own]
            scored.append(
                ((order, *_lift_rank(chk), access_rank(p), p.farthest_ft), p, chk)
            )
    scored.sort(key=lambda t: t[0])
    _, best, best_check = scored[0]
    checks["access"] = PASS if best.access == STRAIGHT else UNMEASURED
    if checks["access"] == UNMEASURED:
        why.append(
            "the crane's way in needs bends; the 40 ft turning search is not run (unmeasured)"
        )
    checks["slope"] = best.slope
    if best.slope == UNMEASURED:
        why.append("pad slope limit unset or ground unmeasured")
    checks["lifts"] = best_check.status
    if best_check.why:
        why.append(best_check.why)
    for lf in best_check.lifts:
        if lf.status == FAIL:
            why.append(
                f"{lf.kind} {lf.load} over the chart at {lf.radius_ft:.1f} ft: "
                f"{lf.gross_lb:,.0f} lb on {lf.capacity_lb:,.0f} lb"
            )
        elif lf.status == UNMEASURED and lf.why:
            why.append(f"{lf.kind} {lf.load}: {lf.why}")
    checks["power_lines"] = UNMEASURED
    why.append("overhead power lines not checked (29 CFR 1926.1408; FOLLOWUPS 144)")
    checks["hook_height"] = UNMEASURED
    why.append("boom height over the building not checked")
    return Result(_worst(checks.values()), checks, why, best, best_check, tuple(pads))


def access_rank(pad: Pad) -> int:
    """Straight in first, then a pad on measured flat ground."""
    return (0 if pad.access == STRAIGHT else 1) * 2 + (0 if pad.slope == PASS else 1)


def site_from_drawing(
    lot: BaseGeometry,
    drawing: Mapping[str, Any],
    street: Sequence[tuple[float, float, float, float]],
    right_of_way: BaseGeometry | None = None,
) -> Site | None:
    """A :class:`Site` from the screen's drawing JSON (:meth:`Drawing.to_json`):
    None where the drawing has no building that fits."""
    ring = drawing.get("building")
    if not drawing.get("fits") or not ring or len(ring) < 4:
        return None
    return Site(lot, Polygon(ring), tuple(street), right_of_way)


__all__ = [
    "Chart",
    "Lift",
    "LiftCheck",
    "Load",
    "Pad",
    "PodFrame",
    "Reach",
    "Result",
    "Rules",
    "Site",
    "check_lifts",
    "load_rules",
    "parse_range",
    "parse_size",
    "parse_weight",
    "pod_frame",
    "rules_from",
    "set_points",
    "site_from_drawing",
    "solve",
]
