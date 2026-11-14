"""Set access: can the panel truck and a mobile crane reach, set up and lift
the pod on this lot (FOLLOWUPS 145, slice 2, Steph 2026-11-14).

A REPORT, NOT A SCREEN CHECK. Nothing here reaches the colour, a reason
code, a flag or the bound (Steph 2026-11-14: "Don't flag any lots by color
yet"). :func:`report` answers one lot; ``scripts/flats_set_access_sample.py``
runs it over a sample of a finished bridge run.

For one lot with the pod already placed by the screen (the drawing's
building, :mod:`flats.fit.draw`), two cranes from Steph's crane guide
(``flats/config/set_access.yaml``) are tried in a ladder, on-site set-ups
first (Steph 2026-11-14):

1. 28 t Manitex 2892C on site -- lifts over the rear only (180 deg); every
   piece picked one by one off the parked trailer.
2. 45 t National NBT45-2 on site -- 360 deg; lifts each whole trailer load
   off and sets it down where the trailer stood (Steph: "consider the
   location of the truck that backs up as a valid landing spot ... the size
   of the load"), then sets the pieces from the ground. Where no truck spot
   on the lot holds a load, it picks off the parked trailer like the 28 t.
3. The 28 t, then the 45 t, set up in the street in front of the lot, where
   the street's pavement width is recorded and the pad fits in it. These
   carry "power lines not checked" (Steph: overhead lines are another job).

The first that passes is the lot's answer; the ladder stops there. Each
try finds:

* **Pads.** On site: every pad (``crane.pad``) on open ground -- the lot
  less the building -- on a grid at angles off the building's long axis,
  that the crane drives to straight from the street with the building in
  place (bends: unmeasured; none: fail). In the street: the pad along a
  street lot line, its near side at the measured near curb, where the
  recorded pavement width holds the pad's width.
* **Truck spots.** The delivery truck backed straight onto the lot from a
  street lot line, square to it, clear of the building and the pad, the
  load at the back of the trailer; or parked at the measured near curb in
  front of the lot. A spot's plan is the load's (``load_footprint``).
* **Lifts.** Radii from the pad's axis of rotation: each piece picked at
  the far corner of the load on the truck (a piece may lie anywhere in it)
  and set where it goes in the pod; the 45 t's whole loads at the spot's
  centre; the site container off the truck to the open spot nearest the
  crane. Gross load (piece + rigging + chart deductions) against the chart
  read at the next longer listed radius, the best boom column. The 28 t's
  pick and set points must all lie behind the pad's rear end.

What is NOT checked, and is said on every report: overhead power lines,
the pad's slope (no limit printed), the boom's height over the building,
the truck's and crane's turning paths, and the ground under the mats.

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
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry

RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "set_access.yaml"

Status = Literal["pass", "fail", "unmeasured"]
PASS: Status = "pass"
FAIL: Status = "fail"
UNMEASURED: Status = "unmeasured"
#: An attempt the ladder never reached (an earlier one passed).
NOT_TRIED = "not tried"
_ORDER = {PASS: 0, UNMEASURED: 1, FAIL: 2}

#: How far into the street the crane or truck is taken to have arrived: a
#: point this far past a street lot line is on the street.
APRON_FT = 30.0
#: Geometry slack, feet.
EPS = 1e-6
#: Access answers.
STRAIGHT = "straight"
BENDS = "bends"
NONE = "none"
#: The note every plan that uses the street carries (Steph 2026-11-14).
POWER_NOTE = "power lines not checked"
#: What no plan checks (said on every report).
NOT_CHECKED: tuple[str, ...] = (
    "overhead power lines",
    "pad slope (no limit printed)",
    "boom height over the building",
    "truck and crane turning paths",
    "ground under the outrigger mats",
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


def parse_range(text: str) -> tuple[float, float]:
    """A printed length or range: ``4'-4'3.5"`` -> (4.0, 4.29);
    ``37 ft 5 in-38 ft 6 in`` -> (37.42, 38.5)."""
    t = str(text).strip()
    parts = re.split(r"(?<=['\"\dn])\s*-\s*(?=\d)", t)
    if len(parts) == 1:
        v = _length(parts[0])
        return v, v
    if len(parts) != 2:
        raise ValueError(f"not a printed range: {text!r}")
    lo, hi = _length(parts[0]), _length(parts[1])
    return min(lo, hi), max(lo, hi)


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


# --------------------------------------------------------------------------
# Rules
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
    deductions_lb: float
    max_pct: float
    #: ((boom_ft, ((radius_ft, capacity_lb), ...)), ...), radius rising.
    booms: tuple[tuple[float, tuple[tuple[float, float], ...]], ...]

    def read(self, radius_ft: float) -> Reading | None:
        """The rated capacity at ``radius_ft``: the best boom column's NEXT
        LONGER listed radius, never interpolated (guide section 3). 0 past
        every column's last radius; None where the radius is inside every
        column's first one (the chart says nothing)."""
        best: Reading | None = None
        for boom, rows in self.booms:
            if radius_ft < rows[0][0] - EPS:
                continue
            got = Reading(0.0, None, None)
            for r, c in rows:
                if r >= radius_ft - EPS:
                    got = Reading(c, r, boom)
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
            cc = np.array([c for _, c in rows])
            idx = np.searchsorted(rr, radii - EPS, side="left")
            cap = np.where(idx < len(rr), cc[np.minimum(idx, len(rr) - 1)], 0.0)
            cap = np.where(radii >= rr[0] - EPS, cap, np.nan)
            out = np.where(np.isnan(out), cap, np.where(np.isnan(cap), out, np.maximum(out, cap)))
        return out

    def reach_for(self, gross_lb: float) -> float | None:
        """The longest listed radius at which ``gross_lb`` is within the
        planning ceiling, over every boom; None where it is nowhere."""
        far: float | None = None
        for _, rows in self.booms:
            for r, c in rows:
                if c * self.max_pct / 100.0 >= gross_lb - EPS:
                    far = r if far is None else max(far, r)
        return far


@dataclass(frozen=True, slots=True)
class Crane:
    key: str
    label: str
    short: str
    body_w_ft: float
    body_l_ft: float
    pad_w_ft: float
    pad_l_ft: float
    #: ``rear_180`` (lifts over the rear only) or ``full_360``.
    swing: str
    #: Behind the axis, the line every rear-only lift lies past; None = the
    #: pad's rear end (the strictest reading).
    rear_line_ft: float | None
    #: ``off_trailer`` or ``whole_load``.
    method: str
    rotation_offset_ft: tuple[float, float]
    chart: Chart

    @property
    def rear_only(self) -> bool:
        return self.swing == "rear_180"


@dataclass(frozen=True, slots=True)
class Piece:
    key: str
    label: str
    count: int
    weight_lb: float
    set_at: str
    #: Half the printed width: how far a cassette's centre stands in from
    #: the pod's end (0 where no width is printed).
    inset_ft: float = 0.0
    #: The printed plan (long, short), 0 where a side is not printed: on
    #: the truck a piece's centre stands at least half of it in from the
    #: load's edges.
    plan_ft: tuple[float, float] = (0.0, 0.0)


@dataclass(frozen=True, slots=True)
class WholeLoad:
    key: str
    label: str
    stack_lb: float


@dataclass(frozen=True, slots=True)
class Rules:
    cranes: tuple[Crane, ...]
    pieces: tuple[Piece, ...]
    whole_loads: tuple[WholeLoad, ...]
    container_label: str
    container_fp: tuple[float, float]
    container_lb: float
    load_fp: tuple[float, float]
    truck_w_ft: float
    trailer_l_ft: float
    places: tuple[str, ...]
    rig_single_lb: float
    rig_whole_lb: float
    verify_weight_over_pct: float
    homes: int
    pad_grid_ft: float
    pad_angle_step_deg: float
    spot_grid_ft: float
    spot_angle_step_deg: float
    pads_kept: int
    street_step_ft: float

    def crane(self, key: str) -> Crane:
        for c in self.cranes:
            if c.key == key:
                return c
        raise KeyError(key)


def _chart(key: str, raw: Mapping[str, Any], default_pct: float) -> Chart:
    booms: list[tuple[float, tuple[tuple[float, float], ...]]] = []
    for col in raw.get("booms") or []:
        rows = tuple(sorted((float(r), float(c)) for r, c in col["rows"]))
        if not rows:
            raise ValueError(f"chart {key}: a boom column with no rows")
        for (_, a), (_, b) in zip(rows, rows[1:]):
            if b > a + EPS:
                raise ValueError(f"chart {key}: capacity rises with radius")
        booms.append((float(col["boom_ft"]), rows))
    if not booms:
        raise ValueError(f"chart {key}: no boom columns")
    pct = raw.get("max_pct_of_chart")
    return Chart(
        key=key,
        source=str(raw.get("source", "")),
        deductions_lb=float(sum((raw.get("deductions_lb") or {}).values())),
        max_pct=default_pct if pct is None else float(pct),
        booms=tuple(booms),
    )


def _hi(text: Any) -> float:
    got = parse_weight(text)
    if got is None:
        raise ValueError("a printed weight is required here")
    return got[1]


def _plan(size: tuple[tuple[float, float], ...] | None) -> tuple[float, float]:
    """A piece's printed plan (long, short), LOW ends (the least it can be,
    so its centre is taken as near the load's edge as it can stand); 0 for
    a side not printed."""
    if not size:
        return 0.0, 0.0
    dims = sorted((lo for lo, _ in size), reverse=True)
    return dims[0], dims[1] if len(dims) > 1 else 0.0


def _fp(text: str) -> tuple[float, float]:
    """A plan footprint (long, short) from a printed size, high ends."""
    size = parse_size(text)
    if not size or len(size) < 2:
        raise ValueError(f"a plan size needs two dimensions: {text!r}")
    dims = sorted((hi for _, hi in size), reverse=True)
    return dims[0], dims[1]


def rules_from(raw: Mapping[str, Any]) -> Rules:
    """Parse the printed config (``set_access.yaml``) into figures."""
    lifts = raw.get("lifts") or {}
    default_pct = (
        100.0 if lifts.get("max_pct_of_chart") is None else float(lifts["max_pct_of_chart"])
    )
    cranes: list[Crane] = []
    for key in raw["order"]:
        c = raw["cranes"][key]
        pad_w, pad_l = (hi for _, hi in parse_size(c["pad"]) or ())
        off = c.get("rotation_offset_ft") or {}
        rear = c.get("rear_line_from_axis_ft")
        cranes.append(
            Crane(
                key=key,
                label=c["label"],
                short=c["label"].split(" ")[0] + " t",
                body_w_ft=parse_range(c["body"]["width"])[1],
                body_l_ft=parse_range(c["body"]["length"])[1],
                pad_w_ft=pad_w,
                pad_l_ft=pad_l,
                swing=c["swing"],
                rear_line_ft=None if rear is None else float(rear),
                method=c["method"],
                rotation_offset_ft=(float(off.get("along", 0.0)), float(off.get("across", 0.0))),
                chart=_chart(key, c["chart"], default_pct),
            )
        )
    pieces: list[Piece] = []
    for key, p in (raw.get("pieces") or {}).items():
        size = parse_size(p.get("size"))
        inset = size[1][0] / 2 if size is not None and len(size) >= 2 else 0.0
        pieces.append(
            Piece(
                key, p["label"], int(p.get("count", 1)), _hi(p["weight_lb"]), p["set_at"], inset,
                _plan(size),
            )
        )
    rig = raw["rigging"]
    pick = 1 if rig.get("use", "high") == "high" else 0
    whole = sum(parse_weight(v)[pick] for v in rig["whole_load_lb"].values())  # type: ignore[index]
    cont = raw["container"]
    truck = raw["truck"]
    search = raw["search"]
    return Rules(
        cranes=tuple(cranes),
        pieces=tuple(pieces),
        whole_loads=tuple(
            WholeLoad(k, v["label"], _hi(v["stack_lb"])) for k, v in (raw.get("whole_loads") or {}).items()
        ),
        container_label=cont["label"],
        container_fp=_fp(cont["size"]),
        container_lb=_hi(cont["weight_lb"]),
        load_fp=_fp(raw["load_footprint"]),
        truck_w_ft=parse_range(truck["width"])[1],
        trailer_l_ft=float(truck["trailer_length_ft"]),
        places=tuple(truck.get("places") or ("lot", "curb")),
        rig_single_lb=parse_weight(rig["single_pick_lb"])[pick],  # type: ignore[index]
        rig_whole_lb=float(whole),
        verify_weight_over_pct=float(lifts.get("verify_weight_over_pct", 75)),
        homes=int(raw["pod"]["homes"]),
        pad_grid_ft=float(search["pad_grid_ft"]),
        pad_angle_step_deg=float(search["pad_angle_step_deg"]),
        spot_grid_ft=float(search["spot_grid_ft"]),
        spot_angle_step_deg=float(search["spot_angle_step_deg"]),
        pads_kept=int(search["pads_kept"]),
        street_step_ft=float(search["street_step_ft"]),
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


def set_points(frame: PodFrame, piece: Piece, homes: int) -> np.ndarray:
    """Where a piece's centre (the hook) may end up, world coordinates,
    (N, 2). The farthest from the crane is its set radius."""
    L, D = frame.length_ft, frame.depth_ft
    h = L / homes
    long_walls = [(-L / 2 + (i + 0.5) * h, s * D / 2) for i in range(homes) for s in (-1, 1)]
    short_walls = [(-L / 2 + k * h, 0.0) for k in range(homes + 1)]
    if piece.set_at == "long_walls":
        local = long_walls
    elif piece.set_at == "walls":
        local = long_walls + short_walls
    elif piece.set_at == "centreline":
        local = [(-L / 2 + piece.inset_ft, 0.0), (L / 2 - piece.inset_ft, 0.0)]
    elif piece.set_at == "footprint":
        local = [(su * L / 2, sv * D / 2) for su in (-1, 1) for sv in (-1, 1)]
    else:
        raise ValueError(f"{piece.key}: unknown set_at {piece.set_at!r}")
    return np.array([frame.world(u, v) for u, v in local], dtype=float)


# --------------------------------------------------------------------------
# The site
# --------------------------------------------------------------------------

#: Given points on street lot lines (N, 2), the distance from each to its
#: street's near curb and the recorded pavement width there, feet; NaN
#: where nothing measures them (:func:`street_reader`).
StreetReading = Callable[[np.ndarray], tuple[np.ndarray, np.ndarray]]


@dataclass(frozen=True)
class Site:
    """One lot with the pod placed: the lot, the drawn building, the lot
    lines on a street ``(x1, y1, x2, y2)``, and what measures the street in
    front of them (None: no street set-up or curb truck is measured)."""

    lot: BaseGeometry
    building: BaseGeometry
    street: Sequence[tuple[float, float, float, float]]
    street_reading: StreetReading | None = None


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
    corners of what must stay clear of the crane's pad (the truck's way in
    with it), and where each is (``lot`` / ``curb``)."""

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
    """The truck backed straight onto the lot from a street lot line, square
    to it (Steph 2026-11-14, the landing spot): the load's footprint, its
    long side square to the line, the load at the BACK of the trailer, and
    the truck's whole width clear from the street to the far end of the
    load, with the building in place."""
    L, W = rules.load_fp[0], rules.truck_w_ft
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
        # The strip from just outside the lot line to the load's far end.
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


def curb_truck_spots(site: Site, rules: Rules) -> tuple[Spots, bool]:
    """The truck parked at the near curb in front of the lot, parallel to
    the lot line, its load anywhere along the frontage; and whether every
    street lot line's curb was measured."""
    if site.street_reading is None:
        return Spots.empty(), False
    L, W = rules.load_fp[0], rules.truck_w_ft
    out: list[Spots] = []
    measured = True
    for a, d, n, length in _segments(site):
        us = _along(length, rules.spot_grid_ft)
        # The curb under the load's two ends and middle: the farthest of
        # them, so the whole load stands on the pavement.
        pts = np.concatenate([a + np.clip(us + k, 0, length)[:, None] * d for k in (-L / 2, 0.0, L / 2)])
        curb, _ = site.street_reading(pts)
        curb = curb.reshape(3, -1)
        ok = np.isfinite(curb).all(axis=0)
        if not ok.all():
            measured = False
        if not ok.any():
            continue
        off = curb.max(axis=0)[ok]
        centre = a + us[ok][:, None] * d + (off + W / 2)[:, None] * n
        corners = _corners(centre, d, L, W)
        out.append(
            Spots(
                centre, corners, corners, np.full(int(ok.sum()), "curb", dtype=object),
                np.tile(d, (int(ok.sum()), 1)),
            )
        )
    return Spots.join(out), measured


def container_spots(open_ground: BaseGeometry, rules: Rules, base_deg: float) -> Spots:
    """Every place the site container's plan fits on open ground."""
    fp = rules.container_fp
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
    count: int
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


@dataclass(frozen=True)
class Plan:
    """One way to set the pod: where the crane and the truck stand, and
    every lift."""

    crane: str
    setup: Literal["site", "street"]
    pad: BaseGeometry
    axis: tuple[float, float]
    #: The way the crane's rear faces, degrees (rear-only cranes).
    rear_deg: float | None
    access: str
    mode: Literal["whole_load", "off_trailer"]
    truck: Literal["lot", "curb"]
    truck_spot: BaseGeometry
    container_spot: BaseGeometry | None
    lifts: tuple[Lift, ...]
    status: Status
    slope_pct: float | None = None

    @property
    def binding(self) -> Lift | None:
        """The lift nearest its chart (highest percent used); a failing or
        unmeasured lift first."""
        if not self.lifts:
            return None
        return max(
            self.lifts,
            key=lambda lf: (
                _ORDER[lf.status],
                lf.pct_of_chart if lf.pct_of_chart is not None else math.inf,
            ),
        )

    @property
    def uses_street(self) -> bool:
        return self.setup == "street" or self.truck == "curb"

    @property
    def notes(self) -> tuple[str, ...]:
        out = []
        if self.uses_street:
            out.append(POWER_NOTE)
        if self.access == BENDS:
            out.append("the crane's way in needs bends; turning not checked")
        return tuple(out)


@dataclass(frozen=True)
class Attempt:
    crane: str
    setup: Literal["site", "street"]
    status: Status | str
    plan: Plan | None = None
    why: tuple[str, ...] = ()


@dataclass(frozen=True)
class Report:
    """The lot's answer."""

    #: ``28 t`` / ``45 t`` (the crane that works), ``neither`` or ``unmeasured``.
    crane: str
    setup: str | None
    plan: Plan | None
    attempts: tuple[Attempt, ...]
    why: tuple[str, ...]
    not_checked: tuple[str, ...] = NOT_CHECKED
    notes: tuple[str, ...] = field(default=())

    def row(self) -> dict[str, Any]:
        """One flat record for the summary table."""
        p = self.plan
        b = p.binding if p is not None else None
        out: dict[str, Any] = {
            "crane": self.crane,
            "setup": self.setup,
            "mode": p.mode if p else None,
            "truck": p.truck if p else None,
            "binding": b.label if b else None,
            "binding_gross_lb": round(b.gross_lb) if b else None,
            "binding_radius_ft": round(b.radius_ft, 1) if b else None,
            "chart_row_ft": b.row_ft if b else None,
            "chart_boom_ft": b.boom_ft if b else None,
            "chart_capacity_lb": b.capacity_lb if b else None,
            "pct_of_chart": None if b is None or b.pct_of_chart is None else round(b.pct_of_chart, 1),
            "verify_weight": bool(b.verify_weight) if b else False,
            "pad_slope_pct": None if p is None or p.slope_pct is None else round(p.slope_pct, 2),
            "notes": "; ".join(self.notes),
            "why": "; ".join(self.why),
        }
        for a in self.attempts:
            out[f"{a.crane.replace(' ', '')}_{a.setup}"] = a.status
        return out


def _worst(statuses: Iterable[Status]) -> Status:
    s = list(statuses)
    if FAIL in s:
        return FAIL
    if UNMEASURED in s:
        return UNMEASURED
    return PASS


# --------------------------------------------------------------------------
# Lifts
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Kinds:
    """Every lift kind one crane makes in one mode: what, key, label, count,
    gross lb, and how its radius is found."""

    what: tuple[str, ...]
    keys: tuple[str, ...]
    labels: tuple[str, ...]
    counts: tuple[int, ...]
    gross: np.ndarray
    #: ``far`` (picked off the load, at the farthest its centre can stand,
    #: set at ``set_ft``) or ``centre`` (a whole load: at the spot's centre).
    radius: tuple[str, ...]
    set_ft: np.ndarray
    #: How far in from the load's edges (along, across) a piece's centre
    #: stands on the truck: half its printed plan.
    inset: tuple[tuple[float, float], ...]


def _kinds(crane: Crane, rules: Rules, mode: str, set_ft: np.ndarray, container_ft: float) -> _Kinds:
    ded = crane.chart.deductions_lb
    what, keys, labels, counts, gross, how, sets, inset = [], [], [], [], [], [], [], []
    for p, s in zip(rules.pieces, set_ft):
        what.append("piece")
        keys.append(p.key)
        labels.append(p.label)
        counts.append(p.count)
        gross.append(p.weight_lb + rules.rig_single_lb + ded)
        how.append("far")
        sets.append(s)
        inset.append((p.plan_ft[0] / 2, p.plan_ft[1] / 2))
    # The container rides on the truck within the load's plan (its place on
    # the trailer is not printed), picked where its centre can stand
    # farthest, and set on the open spot nearest the crane.
    what.append("container")
    keys.append("site_container")
    labels.append(rules.container_label)
    counts.append(1)
    gross.append(rules.container_lb + rules.rig_single_lb + ded)
    how.append("far")
    sets.append(container_ft)
    inset.append((rules.container_fp[0] / 2, rules.container_fp[1] / 2))
    if mode == "whole_load":
        for w in rules.whole_loads:
            what.append("whole_load")
            keys.append(w.key)
            labels.append(w.label)
            counts.append(1)
            gross.append(w.stack_lb + rules.rig_whole_lb + ded)
            how.append("centre")
            sets.append(0.0)
            inset.append((0.0, 0.0))
    return _Kinds(
        tuple(what), tuple(keys), tuple(labels), tuple(counts), np.array(gross),
        tuple(how), np.array(sets, dtype=float), tuple(inset),
    )


def _radii(
    kinds: _Kinds, sp: Spots, cor: np.ndarray, load_fp: tuple[float, float], truck_w: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(pick, set, governing) radii, (S, K), on truck spots ``sp`` from the
    axis ``cor``."""
    S, K = len(sp), len(kinds.what)
    pick = np.empty((S, K))
    setr = np.empty((S, K))
    centre = np.hypot(*(sp.centres - cor).T)
    for k, how in enumerate(kinds.radius):
        if how == "centre":
            pick[:, k] = centre
            setr[:, k] = centre
        else:
            pick[:, k] = sp.far_ft(cor, load_fp[0], truck_w, kinds.inset[k])
            setr[:, k] = kinds.set_ft[k]
    return pick, setr, np.maximum(pick, setr)


def _score(crane: Crane, kinds: _Kinds, gov: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per spot: worst status order (0 pass, 1 unmeasured, 2 fail) and the
    highest share of the planning ceiling any lift uses."""
    cap = crane.chart.capacities(gov)
    allowed = cap * crane.chart.max_pct / 100.0
    with np.errstate(divide="ignore", invalid="ignore"):
        use = np.where(allowed > 0, kinds.gross[None, :] / allowed, np.inf)
    use = np.where(np.isnan(cap), np.nan, use)
    fail = (use > 1.0 + EPS).any(axis=1)
    unmeas = np.isnan(use).any(axis=1)
    order = np.where(fail, 2, np.where(unmeas, 1, 0))
    worst = np.nanmax(np.where(np.isnan(use), -np.inf, use), axis=1)
    return order, worst


def _lifts_at(crane: Crane, rules: Rules, kinds: _Kinds, pick: np.ndarray, setr: np.ndarray, why: Sequence[str]) -> tuple[Lift, ...]:
    out: list[Lift] = []
    for k in range(len(kinds.what)):
        r = float(max(pick[k], setr[k]))
        gross = float(kinds.gross[k])
        note = why[k]
        if not math.isfinite(r):
            out.append(
                Lift(kinds.what[k], kinds.keys[k], kinds.labels[k], kinds.counts[k], gross,  # type: ignore[arg-type]
                     float(pick[k]), float(setr[k]), r, None, None, None, None, None, False,
                     UNMEASURED, note or "no radius")
            )
            continue
        got = crane.chart.read(r)
        if got is None:
            out.append(
                Lift(kinds.what[k], kinds.keys[k], kinds.labels[k], kinds.counts[k], gross,  # type: ignore[arg-type]
                     float(pick[k]), float(setr[k]), r, None, None, None, None, None, False,
                     UNMEASURED, "inside the chart's least radius")
            )
            continue
        allowed = got.capacity_lb * crane.chart.max_pct / 100.0
        pct = None if got.capacity_lb <= 0 else 100.0 * gross / got.capacity_lb
        status: Status = FAIL if allowed < gross - EPS else PASS
        out.append(
            Lift(
                what=kinds.what[k],  # type: ignore[arg-type]
                key=kinds.keys[k],
                label=kinds.labels[k],
                count=kinds.counts[k],
                gross_lb=gross,
                pick_ft=float(pick[k]),
                set_ft=float(setr[k]),
                radius_ft=r,
                row_ft=got.row_ft,
                boom_ft=got.boom_ft,
                capacity_lb=got.capacity_lb,
                slack_lb=allowed - gross,
                pct_of_chart=pct,
                verify_weight=pct is not None and pct > rules.verify_weight_over_pct,
                status=status,
                why=note if status == FAIL else "",
            )
        )
    return tuple(out)


# --------------------------------------------------------------------------
# One crane, one set-up
# --------------------------------------------------------------------------


@dataclass
class _Lot:
    """What every attempt on one lot shares."""

    site: Site
    rules: Rules
    frame: PodFrame
    sets: list[np.ndarray]
    open_lot: BaseGeometry
    lot_spots: Spots
    curb_spots: Spots
    curb_measured: bool
    containers: Spots
    grade_of: Callable[[BaseGeometry], float | None] | None


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


def _behind(points: np.ndarray, origin: np.ndarray, rear: np.ndarray) -> bool:
    return bool((((points.reshape(-1, 2) - origin) @ rear) >= -EPS).all())


def _rear_origin(crane: Crane, centre: np.ndarray, cor: np.ndarray, rear: np.ndarray) -> np.ndarray:
    if crane.rear_line_ft is None:
        return centre + rear * crane.pad_l_ft / 2
    return cor + rear * crane.rear_line_ft


def _cor(crane: Crane, centre: np.ndarray, u: np.ndarray) -> np.ndarray:
    along, across = crane.rotation_offset_ft
    return centre + u * along + np.array([-u[1], u[0]]) * across


def _best_plan(
    lot: _Lot,
    crane: Crane,
    setup: Literal["site", "street"],
    pads: Sequence[tuple[np.ndarray, np.ndarray, str]],
) -> tuple[Plan | None, list[str]]:
    """The best plan over ``pads`` (centre, unit along the pad, access)."""
    rules = lot.rules
    why: list[str] = []
    trucks = Spots.join(
        [s for s, place in ((lot.lot_spots, "lot"), (lot.curb_spots, "curb")) if place in rules.places]
    )
    if not len(trucks):
        why.append(
            "no place for the delivery truck: none backs onto the lot"
            + ("" if lot.curb_measured else ", and the curb in front is not measured")
        )
        return None, why
    modes = ["off_trailer"] if crane.method == "off_trailer" else ["whole_load", "off_trailer"]
    best: tuple[tuple, Plan] | None = None
    rear_misses = 0
    for centre, u, access in pads:
        cor = _cor(crane, centre, u)
        pad_c = _corners(centre[None], u, crane.pad_l_ft, crane.pad_w_ft)[0]
        set_ft = np.array([float(np.hypot(*(s - cor).T).max()) for s in lot.sets])
        clear = _clear_of(pad_c, trucks.clear)
        if lot.containers is not None and len(lot.containers):
            c_clear = _clear_of(pad_c, lot.containers.corners)
        else:
            c_clear = np.zeros(0, dtype=bool)
        headings = [u, -u] if crane.rear_only else [None]
        for rear in headings:
            ok = clear.copy()
            c_ok = c_clear.copy()
            if rear is not None:
                origin = _rear_origin(crane, centre, cor, rear)
                if not all(_behind(s, origin, rear) for s in lot.sets):
                    rear_misses += 1
                    continue
                ok &= (((trucks.corners - origin) @ rear) >= -EPS).all(axis=1)
                if len(c_ok):
                    c_ok &= (((lot.containers.corners - origin) @ rear) >= -EPS).all(axis=1)
            if not ok.any():
                continue
            sp = trucks.take(ok)
            far = np.sqrt(((sp.corners - cor) ** 2).sum(-1)).max(axis=1)
            if len(c_ok) and c_ok.any():
                cc = lot.containers.take(c_ok)
                cfar = np.hypot(*(cc.centres - cor).T)
                ci = int(np.argmin(cfar))
                c_ft, c_poly = float(cfar[ci]), Polygon(cc.corners[ci])
            else:
                c_ft, c_poly = math.inf, None
            for mode in modes:
                pick_ok = np.ones(len(sp), dtype=bool) if mode == "off_trailer" else sp.place == "lot"
                if not pick_ok.any():
                    continue
                kinds = _kinds(crane, rules, mode, set_ft, c_ft)
                pick, setr, gov = _radii(kinds, sp.take(pick_ok), cor, rules.load_fp, rules.truck_w_ft)
                order, worst = _score(crane, kinds, gov)
                if not math.isfinite(c_ft):
                    order = np.maximum(order, 1)
                street = (sp.place[pick_ok] == "curb").astype(int) + (1 if setup == "street" else 0)
                rank = np.lexsort((far[pick_ok], worst, street, order))
                i = int(rank[0])
                notes = ["" for _ in kinds.what]
                if not math.isfinite(c_ft):
                    notes[kinds.what.index("container")] = "no open spot for the site container near the crane"
                lifts = _lifts_at(crane, rules, kinds, pick[i], setr[i], notes)
                lift_status = _worst(lf.status for lf in lifts)
                own = _worst([lift_status, PASS if access == STRAIGHT else UNMEASURED])
                pad_poly = Polygon(pad_c)
                plan = Plan(
                    crane=crane.short,
                    setup=setup,
                    pad=pad_poly,
                    axis=(float(cor[0]), float(cor[1])),
                    rear_deg=None if rear is None else math.degrees(math.atan2(rear[1], rear[0])),
                    access=access,
                    mode=mode,  # type: ignore[arg-type]
                    truck=str(sp.place[pick_ok][i]),  # type: ignore[arg-type]
                    truck_spot=Polygon(sp.corners[pick_ok][i]),
                    container_spot=c_poly,
                    lifts=lifts,
                    status=own,
                    slope_pct=None,
                )
                key = (
                    _ORDER[own],
                    int(street[i]),
                    modes.index(mode),
                    float(worst[i]) if math.isfinite(worst[i]) else math.inf,
                    float(far[pick_ok][i]),
                )
                if best is None or key < best[0]:
                    best = (key, plan)
    if best is None:
        if rear_misses and crane.rear_only:
            why.append(
                f"no {crane.short} pad has the whole pod and a truck spot behind it (it lifts over the rear only)"
            )
        else:
            why.append("no truck spot is clear of every crane pad")
        return None, why
    plan = best[1]
    if lot.grade_of is not None and setup == "site":
        plan = dataclasses.replace(plan, slope_pct=lot.grade_of(plan.pad))
    return plan, why


def _site_pads(lot: _Lot, crane: Crane) -> tuple[list[tuple[np.ndarray, np.ndarray, str]], list[str]]:
    """On-site pads the crane drives to, best first: straight drives, then
    the shortest farthest set radius; at most ``pads_kept``."""
    site, rules = lot.site, lot.rules
    ground = lot.open_lot
    gx, gy = _grid(ground, rules.pad_grid_ft)
    shapely.prepare(ground)
    cand: list[tuple[float, np.ndarray, np.ndarray]] = []
    allsets = np.concatenate(lot.sets)
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
        return [], [f"no pad is reached by the {crane.short} crane ({crane.body_w_ft:.2f} ft wide) from the street with the building in place"]
    return pads, []


def _street_pads(lot: _Lot, crane: Crane) -> tuple[list[tuple[np.ndarray, np.ndarray, str]], Status, list[str]]:
    """Pads in the street in front of the lot: along a street lot line, the
    near side at the measured near curb, where the recorded pavement width
    holds the pad's width under the pad's two ends and middle."""
    site, rules = lot.site, lot.rules
    if site.street_reading is None:
        return [], UNMEASURED, ["the street in front is not measured (no curb or width data)"]
    pads: list[tuple[np.ndarray, np.ndarray, str]] = []
    narrowest: float | None = None
    any_measured = False
    for a, d, n, length in _segments(site):
        us = _along(length, rules.street_step_ft)
        pts = np.concatenate(
            [a + np.clip(us + k, 0, length)[:, None] * d for k in (-crane.pad_l_ft / 2, 0.0, crane.pad_l_ft / 2)]
        )
        curb, width = site.street_reading(pts)
        curb, width = curb.reshape(3, -1), width.reshape(3, -1)
        ok = np.isfinite(curb).all(axis=0) & np.isfinite(width).all(axis=0)
        if not ok.any():
            continue
        any_measured = True
        w = width.min(axis=0)
        narrowest = float(w[ok].max()) if narrowest is None else max(narrowest, float(w[ok].max()))
        fits = ok & (w >= crane.pad_w_ft - EPS)
        for j in np.flatnonzero(fits):
            off = float(curb[:, j].max())
            centre = a + us[j] * d + n * (off + crane.pad_w_ft / 2)
            pads.append((centre, d.copy(), STRAIGHT))
    if not any_measured:
        return [], UNMEASURED, ["the street's pavement width in front is not recorded"]
    if not pads:
        return [], FAIL, [
            f"the street in front is {narrowest:.0f} ft wide at most; the {crane.short} pad needs {crane.pad_w_ft:g} ft"
        ]
    pads.sort(key=lambda t: float(max(np.hypot(*(s - t[0]).T).max() for s in lot.sets)))
    return pads[: rules.pads_kept], PASS, []


def _attempt(lot: _Lot, crane: Crane, setup: Literal["site", "street"]) -> Attempt:
    if setup == "site":
        pads, why = _site_pads(lot, crane)
        if not pads:
            return Attempt(crane.short, setup, FAIL, None, tuple(why))
    else:
        pads, st, why = _street_pads(lot, crane)
        if not pads:
            return Attempt(crane.short, setup, st, None, tuple(why))
    plan, why2 = _best_plan(lot, crane, setup, pads)
    curb_open = "curb" in lot.rules.places and not lot.curb_measured
    if plan is None:
        status: Status = UNMEASURED if curb_open else FAIL
        if curb_open and not any("not measured" in w for w in why2):
            why2.append("the curb in front is not measured; a truck there might serve")
        return Attempt(crane.short, setup, status, None, tuple(why + why2))
    reasons = list(why + why2)
    for lf in plan.lifts:
        if lf.status == FAIL:
            reasons.append(
                f"{lf.label} over the chart at {lf.radius_ft:.1f} ft "
                f"(read at {lf.row_ft:g} ft): {lf.gross_lb:,.0f} lb on {lf.capacity_lb:,.0f} lb"
                if lf.row_ft is not None
                else f"{lf.label} beyond the chart's longest reach at {lf.radius_ft:.1f} ft"
            )
        elif lf.status == UNMEASURED:
            reasons.append(f"{lf.label}: {lf.why}")
    if plan.access == BENDS:
        reasons.append("the crane's way in needs bends; turning not checked (unmeasured)")
    status = plan.status
    if status == FAIL and curb_open:
        status = UNMEASURED
        reasons.append("the curb in front is not measured; a truck there might be nearer")
    return Attempt(crane.short, setup, status, plan, tuple(reasons))


def report(
    site: Site,
    rules: Rules | None = None,
    *,
    grade_of: Callable[[BaseGeometry], float | None] | None = None,
) -> Report:
    """Which crane works on ``site``, where it sets up, and its binding lift.

    The ladder: every crane on site in ``order``, then every crane in the
    street; it stops at the first that passes. ``grade_of`` is the fall
    across a polygon, percent (the screen's
    :meth:`flats.fit.slope.Terrain.grade` ``.pct``), reported for the chosen
    on-site pad only (no slope limit is printed)."""
    rules = rules or load_rules()
    frame = pod_frame(site.building)
    why: list[str] = []
    if abs(frame.length_ft / rules.homes - round(frame.length_ft / rules.homes)) > 0.5:
        why.append(f"drawn pod {frame.length_ft:.1f} ft long is not {rules.homes} whole homes")
    open_lot = site.lot.difference(site.building)
    curb, curb_measured = curb_truck_spots(site, rules)
    lot = _Lot(
        site=site,
        rules=rules,
        frame=frame,
        sets=[set_points(frame, p, rules.homes) for p in rules.pieces],
        open_lot=open_lot,
        lot_spots=lot_truck_spots(site, rules) if "lot" in rules.places else Spots.empty(),
        curb_spots=curb if "curb" in rules.places else Spots.empty(),
        curb_measured=curb_measured,
        containers=container_spots(open_lot, rules, frame.angle_deg),
        grade_of=grade_of,
    )
    ladder = [(c, "site") for c in rules.cranes] + [(c, "street") for c in rules.cranes]
    attempts: list[Attempt] = []
    won: Attempt | None = None
    for crane, setup in ladder:
        if won is not None:
            attempts.append(Attempt(crane.short, setup, NOT_TRIED))  # type: ignore[arg-type]
            continue
        got = _attempt(lot, crane, setup)  # type: ignore[arg-type]
        attempts.append(got)
        if got.status == PASS:
            won = got
    if won is not None:
        plan = won.plan
        assert plan is not None
        return Report(won.crane, won.setup, plan, tuple(attempts), tuple(why), notes=plan.notes)
    statuses = [a.status for a in attempts]
    answer = "unmeasured" if UNMEASURED in statuses else "neither"
    for a in attempts:
        why.extend(f"{a.crane} {a.setup}: {w}" for w in a.why)
    # The plan shown is the best that came nearest: unmeasured before fail.
    shown = [a for a in attempts if a.plan is not None]
    shown.sort(key=lambda a: _ORDER.get(str(a.status), 3))
    plan = shown[0].plan if shown else None
    return Report(
        answer,
        shown[0].setup if shown else None,
        plan,
        tuple(attempts),
        tuple(why),
        notes=plan.notes if plan else (),
    )


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
    "Chart",
    "Crane",
    "Lift",
    "NOT_CHECKED",
    "NOT_TRIED",
    "POWER_NOTE",
    "Piece",
    "Plan",
    "PodFrame",
    "Reading",
    "Report",
    "Rules",
    "Site",
    "Spots",
    "StreetReading",
    "container_spots",
    "curb_truck_spots",
    "load_rules",
    "lot_truck_spots",
    "parse_range",
    "parse_size",
    "parse_weight",
    "pod_frame",
    "report",
    "rules_from",
    "set_points",
    "site_from_drawing",
    "street_reader",
]
