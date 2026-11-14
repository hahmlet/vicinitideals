"""Where the screen stood the building, drawn back on the lot (FOLLOWUPS 5).

The fit answers with a margin, not a site plan: the deepest rectangle of the
width the parking asks that the envelope holds, at the best of every angle
tried. That is enough to call a lot, and not enough to show anyone why. This
module turns the same search into four shapes on the lot's own coordinates
(EPSG:2913, feet) that the lot page can draw over the outline:

* ``room`` -- the window the search found: as wide as the building and its
  lane (or the court, where the court is wider), and as deep as the building
  plus what the court needs past the envelope's rear edge. Where the lot
  fits nothing that deep, the deepest window it has at that width, so a
  failing lot shows the room it does have.
* ``building`` -- the pod's footprint at the street end of the room.
* ``lane`` -- the drive beside the building, from the street to the court,
  where one is charged (none where an alley or a side street feeds the
  court).
* ``court`` -- the parking behind the building, the gap off the wall
  included, across the room's width. It may run past the room's back: the
  envelope has had the rear yard taken off, and the court is allowed into
  it (:func:`flats.score.screen._court_beyond_rear`). On a failing lot it
  runs past the lot's line, which is the shortfall made visible.

**A drawing, not a site plan.** The room is the one the search found, the
street end is the end nearer the lot's front lines, and the lane is drawn on
one flank; quadfit's s6s chooses among placements and this does not. Where
the stalls stand in a column along a side alley
(:attr:`flats.fit.rectangle.Fit.column`) the court is drawn behind the
building at the column's depth, as a strip along the alley's side of the
room (``column_across_ft``, ``alley_lines``); where the alley's side is not
given, across the room's whole width -- every place the column could stand.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Iterable, Sequence

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry.base import BaseGeometry

from flats.designs.model import Orientation
from flats.fit.raster import Grid, cells_for
from flats.fit.rectangle import Fit, Fitter
from flats.geom.edges import PARALLEL_TOL_DEG

#: Coordinates are stored to a tenth of a foot: finer than a county lot line
#: is good to, coarse enough to keep a lot's drawing a few hundred bytes.
#: The envelope is simplified to this before it is stored.
SIMPLIFY_FT = 0.5
#: The front lines are sampled this often to find the street end.
STREET_STEP_FT = 2.0
#: Windows compared per grid, evenly spaced over every one that fits: a
#: big lot has hundreds of thousands, and the one nearest the street is
#: found about as well among a few thousand.
MAX_CANDIDATES = 4000
#: How far past the room a side drive's pavement is drawn each way: longer
#: than any lot is wide, so the lot polygon is what ends it.
SIDE_DRIVE_REACH_FT = 5000.0


@dataclass(frozen=True, slots=True)
class Drawing:
    """The shapes one fit is drawn as, in the lot's coordinates."""

    room: BaseGeometry
    building: BaseGeometry | None
    lane: BaseGeometry | None
    court: BaseGeometry | None
    #: The room holds the building and the court's excess: the fit passed.
    fits: bool
    #: What the plan PAVES, where the caller said how wide the court's
    #: pavement is (``paved_across_ft``): the lane from the room's street end
    #: past the standoff to the aisle, and the stalls and aisle behind the
    #: standoff, as wide as they are rather than the room's whole width. One
    #: shape per legal way to stand the row: against the lane where there is
    #: one, else at either side of the room. The standoff off the rear wall is
    #: not pavement. Where the court is reached across a side yard
    #: (``side_drive``) the drive's line is not drawn, so the one shape paves
    #: the court's whole depth band from lot line to lot line: every place
    #: the drive could run, and more. Empty where not asked. Read by the
    #: outdoor-area shape test (FOLLOWUPS 7(b)), never by the page.
    paved: tuple[BaseGeometry, ...] = ()
    #: The stalls and aisle alone, one shape per :attr:`paved` shape: the
    #: same row without the lane that reaches it, and on a side-fed court the
    #: court's depth band across the room only (where the drive meets it is
    #: not known, and the drive is not parking). Read by the parking share of
    #: each street frontage (:mod:`flats.fit.frontage`), never by the page.
    rows: tuple[BaseGeometry, ...] = ()
    #: The room is short of the plan by no more than the fit's tolerance
    #: (``short_ft``): a fit the screen passed tight, drawn where it stands.
    tight: bool = False

    def to_json(self, envelope: BaseGeometry | None = None) -> dict:
        """Rings of ``[x, y]`` pairs, rounded, for the lot page.

        ``envelope`` is the ground searched, stored beside the plan so the
        page draws the yards the lot lost as well as what stands in them.
        """
        out: dict = {"fits": self.fits, "room": _ring(self.room)}
        if self.tight:
            out["tight"] = True
        for name in ("building", "lane", "court"):
            geom = getattr(self, name)
            out[name] = None if geom is None else _ring(geom)
        if envelope is not None and not envelope.is_empty:
            simple = envelope.simplify(SIMPLIFY_FT, preserve_topology=True)
            out["envelope"] = [
                _coords(p.exterior.coords)
                for p in shapely.get_parts(simple)
                if p.geom_type == "Polygon" and not p.is_empty
            ]
        return out


def _coords(coords: Iterable[tuple[float, ...]]) -> list[list[float]]:
    return [[round(x, 1), round(y, 1)] for x, y, *_ in coords]


def _ring(geom: BaseGeometry) -> list[list[float]]:
    return _coords(geom.exterior.coords)


def _grids_at(fitter: Fitter, angle_deg: float | None) -> list[Grid]:
    if angle_deg is None:
        return []
    return [g for g in fitter.grids if math.isclose(g.angle_deg, angle_deg, abs_tol=1e-6)]


def _local(points: np.ndarray, grid: Grid) -> np.ndarray:
    """World points into the grid's unrotated frame."""
    t = math.radians(-grid.angle_deg)
    ox, oy = grid.origin
    dx, dy = points[:, 0] - ox, points[:, 1] - oy
    return np.column_stack(
        (ox + dx * math.cos(t) - dy * math.sin(t), oy + dx * math.sin(t) + dy * math.cos(t))
    )


def _along(lines: Iterable[tuple[float, float, float, float]]) -> np.ndarray:
    """Points every :data:`STREET_STEP_FT` along the front lines, ends included."""
    out: list[np.ndarray] = []
    for x1, y1, x2, y2 in lines:
        n = max(1, math.ceil(math.hypot(x2 - x1, y2 - y1) / STREET_STEP_FT))
        t = np.linspace(0.0, 1.0, n + 1)
        out.append(np.column_stack((x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)))
    return np.concatenate(out) if out else np.empty((0, 2))


def _street_groups(lines: Iterable[tuple[float, float, float, float]]) -> list[np.ndarray]:
    """The front lines' points (:func:`_along`), one array per street
    direction: lines whose bearings (either way along) lie within
    :data:`flats.geom.edges.PARALLEL_TOL_DEG` of each other are one street.

    A corner lot's two fronts are two groups; an interior lot's front, or a
    through lot's two parallel fronts, one. :func:`_place` adds the
    building's distance to each group to break the tie between windows that
    stand equally near *a* street: on a corner every window flush with
    either street ties at nought, and which one won used to be the grid's
    scan order -- so turning the fit angle half a turn (rel4, the entrance
    the code requires facing a front) moved corner buildings off the side
    street (1N1E29DD  -05600, rel4 move-read finding 3).
    """
    groups: list[tuple[float, list[tuple[float, float, float, float]]]] = []
    for line in lines:
        x1, y1, x2, y2 = line
        if math.hypot(x2 - x1, y2 - y1) <= 0:
            continue
        b = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0
        for g in groups:
            d = abs(b - g[0]) % 180.0
            if min(d, 180.0 - d) <= PARALLEL_TOL_DEG:
                g[1].append(line)
                break
        else:
            groups.append((b, [line]))
    return [_along(g[1]) for g in groups]


def _near_tie(d: np.ndarray, res: float) -> np.ndarray:
    """``d`` with every distance within one cell (``res``) of the nearest
    read as the nearest: a fit stood a hair off the street's bearing (rel4's
    179.94 degrees on a lot whose front runs at 180) puts one end of a flush
    row of windows a tenth of a foot nearer the street than the other, and
    that tenth -- not the side street -- used to pick the window
    (1N1E29DD  -05600, rel4 move-read finding 3). Within the cell the tie
    goes to :func:`_spread`."""
    finite = d[np.isfinite(d)]
    if not len(finite):
        return d
    m = float(finite.min())
    return np.where(d <= m + res + 1e-9, m, d)


def _pick_near(held: list[tuple], res: float) -> tuple | None:
    """Of ``held`` -- keys ``(distance, spread, ...)`` with the placement
    last -- the one with the least ``(spread, ...)`` among those within one
    cell (``res``) of the nearest distance: the grid-wide tie
    :func:`_near_tie` makes within one scan, made across every grid, end
    of the window and flank."""
    if not held:
        return None
    m = min(k[0] for k in held)
    near = [k for k in held if k[0] <= m + res + 1e-9]
    return min(near, key=lambda k: k[1:-1])


def _spread(
    x0: np.ndarray, y0: np.ndarray, x1: np.ndarray, y1: np.ndarray,
    groups: Sequence[np.ndarray],
) -> np.ndarray:
    """The boxes' summed distance to each street direction
    (:func:`_street_groups`); nought everywhere with fewer than two."""
    out = np.zeros(len(x0))
    if len(groups) < 2:
        return out
    for g in groups:
        out += _box_distance(x0, y0, x1, y1, g)
    return out


#: Largest box-by-point array :func:`_box_distance` builds at once (about
#: 16 MB of float64 per temporary).
BOX_DISTANCE_BLOCK_CELLS = 2_000_000


def _box_distance(
    x0: np.ndarray, y0: np.ndarray, x1: np.ndarray, y1: np.ndarray, pts: np.ndarray
) -> np.ndarray:
    """Distance from each box to the nearest of ``pts`` (0 where one is inside).

    Worked in blocks of boxes so the box-by-point arrays stay under
    :data:`BOX_DISTANCE_BLOCK_CELLS` elements: the frontmost search hands in
    every hit on a big lot, and one array for all of them killed a 6.5 acre
    lot's worker for memory (2S102BD00100, FOLLOWUPS 147). Same answer.
    """
    px, py = pts[None, :, 0], pts[None, :, 1]
    out = np.empty(len(x0), dtype=float)
    step = max(1, BOX_DISTANCE_BLOCK_CELLS // max(1, len(pts)))
    for s in range(0, len(x0), step):
        e = s + step
        dx = np.maximum(np.maximum(x0[s:e, None] - px, 0.0), px - x1[s:e, None])
        dy = np.maximum(np.maximum(y0[s:e, None] - py, 0.0), py - y1[s:e, None])
        out[s:e] = np.hypot(dx, dy).min(axis=1)
    return out


#: Feet the court must come nearer a yard line than the building, over a
#: stretch of that line at least this long, before it is read as standing
#: between them (:func:`court_between`): drawings round to 0.1 ft, and a
#: court beside the building starts at the building's own face.
COURT_BETWEEN_TOL_FT = 1.0


def court_between(
    building: BaseGeometry,
    court: BaseGeometry,
    lines: Iterable[tuple[float, float, float, float]],
    tol: float = COURT_BETWEEN_TOL_FT,
) -> bool:
    """Whether ``court`` stands between ``building`` and one of ``lines``
    (Steph 2026-11-08, rulings.yaml
    ``2026-11-08-no-front-yard-parking-silent-codes``).

    For each line the building and court are read in the line's own frame --
    along it, and out from it into the lot -- over the stretch of the line
    both of them face. The court stands between where, over that stretch, it
    comes nearer the line than the building does by more than ``tol``. A
    court behind the building, or beside it at the same face, does not; a
    court in front of it does, and so does a court behind it where the line
    behind is a street the code makes a front too (a through lot's far end).
    Which lines count is the caller's (:func:`flats.ingest.quadfit.
    court_yard_lines`); this is the geometry alone.
    """
    from shapely.geometry import box

    for x1, y1, x2, y2 in lines:
        length = math.hypot(x2 - x1, y2 - y1)
        if length <= tol:
            continue
        turn = -math.degrees(math.atan2(y2 - y1, x2 - x1))

        def framed(shape: BaseGeometry) -> BaseGeometry:
            return affinity.rotate(
                affinity.translate(shape, -x1, -y1), turn, origin=(0.0, 0.0)
            )

        b, c = framed(building), framed(court)
        if b.centroid.y < 0:
            b = affinity.scale(b, 1.0, -1.0, origin=(0.0, 0.0))
            c = affinity.scale(c, 1.0, -1.0, origin=(0.0, 0.0))
        lo = max(b.bounds[0], c.bounds[0], 0.0)
        hi = min(b.bounds[2], c.bounds[2], length)
        if hi - lo <= tol:
            continue
        window = box(lo, -1e7, hi, 1e7)
        bw, cw = b.intersection(window), c.intersection(window)
        if bw.is_empty or cw.is_empty:
            continue
        if cw.bounds[1] < bw.bounds[1] - tol:
            return True
    return False


def _lines_local(
    lines: Iterable[tuple[float, float, float, float]], grid: Grid
) -> np.ndarray:
    """``lines`` into the grid's unrotated frame, one ``(x1, y1, x2, y2)`` row each."""
    got = np.asarray(list(lines), dtype=float).reshape(-1, 4)
    if not len(got):
        return got
    a = _local(got[:, :2], grid)
    b = _local(got[:, 2:], grid)
    return np.column_stack((a, b))


def _floor_at(
    x0: np.ndarray,
    y0: np.ndarray,
    x1: np.ndarray,
    y1: np.ndarray,
    at: np.ndarray,
    p: tuple[float, float],
    u: tuple[float, float],
    n: tuple[np.ndarray, np.ndarray],
) -> np.ndarray:
    """How near the line each box comes at ``at`` along it: the least
    distance out (along ``n``) of the box's cross-section there. The boxes
    are axis-aligned in this frame; the line through ``p`` runs along the
    unit ``u``, and ``n`` is each box's own unit normal into the lot."""
    px, py = p
    ux, uy = u
    nx, ny = n
    ax = px + at * ux
    ay = py + at * uy
    with np.errstate(divide="ignore", invalid="ignore"):
        tx0, tx1 = (x0 - ax) / nx, (x1 - ax) / nx
        ty0, ty1 = (y0 - ay) / ny, (y1 - ay) / ny
    low_x = np.where(np.abs(nx) > 1e-12, np.minimum(tx0, tx1), -np.inf)
    low_y = np.where(np.abs(ny) > 1e-12, np.minimum(ty0, ty1), -np.inf)
    return np.maximum(low_x, low_y)


def _between_boxes(
    building: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    court: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    lines: np.ndarray,
    tol: float = COURT_BETWEEN_TOL_FT,
) -> np.ndarray:
    """:func:`court_between` for many axis-aligned building and court boxes
    at once, ``lines`` in the same frame (:func:`_lines_local`).

    A box seen from a line is a turned rectangle; how near it comes over a
    stretch of the line is its nearest edge, a convex function along the
    line, so its least over the stretch is at its nearest corner held to
    the stretch, read there across the box (:func:`_floor_at`).
    """
    bx0, by0, bx1, by1 = building
    cx0, cy0, cx1, cy1 = court
    out = np.zeros(len(bx0), dtype=bool)
    bxs = np.column_stack((bx0, bx1, bx1, bx0))
    bys = np.column_stack((by0, by0, by1, by1))
    cxs = np.column_stack((cx0, cx1, cx1, cx0))
    cys = np.column_stack((cy0, cy0, cy1, cy1))
    for px, py, qx, qy in lines:
        length = math.hypot(qx - px, qy - py)
        if length <= tol:
            continue
        ux, uy = (qx - px) / length, (qy - py) / length
        bu = (bxs - px) * ux + (bys - py) * uy
        cu = (cxs - px) * ux + (cys - py) * uy
        bn = (bxs - px) * -uy + (bys - py) * ux
        cn = (cxs - px) * -uy + (cys - py) * ux
        # Into the lot is the building's side of the line.
        side = np.where(bn.mean(axis=1) < 0, -1.0, 1.0)
        bn, cn = bn * side[:, None], cn * side[:, None]
        n = (-uy * side, ux * side)
        lo = np.maximum(np.maximum(bu.min(axis=1), cu.min(axis=1)), 0.0)
        hi = np.minimum(np.minimum(bu.max(axis=1), cu.max(axis=1)), length)
        live = hi - lo > tol
        if not live.any():
            continue
        rows = np.arange(len(bx0))
        b_at = np.clip(bu[rows, bn.argmin(axis=1)], lo, hi)
        c_at = np.clip(cu[rows, cn.argmin(axis=1)], lo, hi)
        b_floor = _floor_at(bx0, by0, bx1, by1, b_at, (px, py), (ux, uy), n)
        c_floor = _floor_at(cx0, cy0, cx1, cy1, c_at, (px, py), (ux, uy), n)
        out |= live & (c_floor < b_floor - tol)
    return out


@dataclass(frozen=True, slots=True)
class _Court:
    """The court as :func:`draw` stands it in a window, for
    :func:`_court_boxes`: behind the building (``depth_ft``, run
    ``overlap_ft`` into the side yard) or beside it (``beside_band_ft`` by
    ``beside_len_ft``). ``across_ft`` is the fit's width."""

    across_ft: float
    depth_ft: float = 0.0
    overlap_ft: float = 0.0
    beside_band_ft: float = 0.0
    beside_len_ft: float = 0.0


def _court_boxes(
    wx0: np.ndarray,
    wy0: np.ndarray,
    wy1: np.ndarray,
    *,
    low: bool,
    left: bool,
    across_b: float,
    deep_b: float,
    court: _Court,
) -> tuple[tuple[np.ndarray, ...], tuple[np.ndarray, ...]] | None:
    """The building and the court each window stands, as :func:`draw` draws
    them, in the grid's frame; None where the plan draws no court."""
    face = wy0 if low else wy1
    sign = 1.0 if low else -1.0
    bx0 = wx0 if left else wx0 + court.across_ft - across_b
    if court.beside_band_ft > 0:
        lx0 = bx0 + across_b if left else bx0 - court.beside_band_ft
        a, b = 0.0, court.beside_len_ft
        cx0, cx1 = lx0, lx0 + court.beside_band_ft
    elif court.depth_ft > 0:
        a, b = deep_b, deep_b + court.depth_ft
        cx0, cx1 = wx0 - court.overlap_ft, wx0 + court.across_ft
    else:
        return None
    ya, yb = face + sign * a, face + sign * b
    ba, bb = face, face + sign * deep_b
    return (
        (bx0, np.minimum(ba, bb), bx0 + across_b, np.maximum(ba, bb)),
        (cx0, np.minimum(ya, yb), cx1, np.maximum(ya, yb)),
    )


def _yard_bad(
    wx0: np.ndarray,
    wy0: np.ndarray,
    wy1: np.ndarray,
    *,
    low: bool,
    left: bool,
    across_b: float,
    deep_b: float,
    court: _Court | None,
    yard: np.ndarray,
) -> np.ndarray:
    """Which windows stand the court between the building and a yard line."""
    if court is None or not len(yard):
        return np.zeros(len(wx0), dtype=bool)
    got = _court_boxes(
        wx0, wy0, wy1, low=low, left=left, across_b=across_b, deep_b=deep_b, court=court
    )
    if got is None:
        return np.zeros(len(wx0), dtype=bool)
    return _between_boxes(got[0], got[1], yard)


#: How much shorter than the row the covered stretch behind a court may be
#: and still serve it: the half-foot :func:`flats.geom.alley.usable_run_ft`
#: walks the stretch at, and the fit's own cell.
STRETCH_TOL_FT = 0.5


@dataclass(frozen=True, slots=True)
class AlleyStretch:
    """Where a rear alley that runs only PART of the rear line serves as the
    court's aisle (Steph 2026-09-28, rulings.yaml ``2026-09-28-partial-alley``:
    *"we can use the portion the alley abuts for our travel lane only if the
    lane is actually long enough"*; FOLLOWUPS 3(c)).

    The row of stalls backs straight out into the alley, so the court has to
    stand against the covered stretch: its far edge -- the one away from the
    building -- within ``reach_ft`` of the stretch, and at least ``row_ft``
    of covered stretch (less :data:`STRETCH_TOL_FT`) along that edge.
    ``lines`` are the covered stretches in the lot's coordinates and
    ``chain`` the run each belongs to: stretches that meet across a bend are
    one run, as :func:`flats.geom.alley.usable_run_ft` walks them."""

    lines: tuple[tuple[float, float, float, float], ...]
    chain: tuple[int, ...]
    row_ft: float
    reach_ft: float

    @classmethod
    def of(
        cls,
        runs: Sequence[Sequence[tuple[float, float, float, float]]],
        row_ft: float,
        reach_ft: float,
        join_ft: float = STRETCH_TOL_FT,
    ) -> "AlleyStretch | None":
        """From :func:`flats.geom.alley.rear_cover_runs`; None where no
        stretch is on record."""
        lines: list[tuple[float, float, float, float]] = []
        chain: list[int] = []
        run = -1
        for line in runs:
            prev: tuple[float, float] | None = None
            for x1, y1, x2, y2 in line:
                if math.hypot(x2 - x1, y2 - y1) <= 0:
                    continue
                if prev is None or math.hypot(x1 - prev[0], y1 - prev[1]) > join_ft:
                    run += 1
                lines.append((float(x1), float(y1), float(x2), float(y2)))
                chain.append(run)
                prev = (x2, y2)
        if not lines:
            return None
        return cls(tuple(lines), tuple(chain), float(row_ft), float(reach_ft))


def _clipped(
    x0: np.ndarray, x1: np.ndarray, y0: np.ndarray, y1: np.ndarray, seg: np.ndarray
) -> np.ndarray:
    """Length of the segment ``seg`` (``x1, y1, x2, y2``) inside each box,
    Liang-Barsky over many boxes at once."""
    sx, sy, ex, ey = (float(v) for v in seg)
    dx, dy = ex - sx, ey - sy
    t0 = np.zeros(len(x0))
    t1 = np.ones(len(x0))
    ok = np.ones(len(x0), dtype=bool)
    for p, q in ((-dx, sx - x0), (dx, x1 - sx), (-dy, sy - y0), (dy, y1 - sy)):
        if abs(p) < 1e-12:
            ok &= q >= 0
            continue
        t = q / p
        if p < 0:
            t0 = np.maximum(t0, t)
        else:
            t1 = np.minimum(t1, t)
    return np.where(ok, np.maximum(0.0, t1 - t0), 0.0) * math.hypot(dx, dy)


def _on_stretch(
    cx0: np.ndarray, cx1: np.ndarray, far: np.ndarray, stretch: AlleyStretch, segs: np.ndarray
) -> np.ndarray:
    """Which courts (``cx0..cx1`` across, far edge at ``far``, in a frame
    where the court's depth runs along ``y``) stand against a covered run
    at least as long as the row (:class:`AlleyStretch`). ``segs`` are the
    stretch's lines in that frame."""
    lo, hi = far - stretch.reach_ft, far + stretch.reach_ft
    runs: dict[int, np.ndarray] = {}
    for k, seg in enumerate(segs):
        got = _clipped(cx0, cx1, lo, hi, seg)
        c = stretch.chain[k]
        runs[c] = got if c not in runs else runs[c] + got
    if not runs:
        return np.zeros(len(cx0), dtype=bool)
    best = np.max(np.vstack(list(runs.values())), axis=0)
    return best >= stretch.row_ft - STRETCH_TOL_FT


def _stretch_bad(
    wx0: np.ndarray,
    wy0: np.ndarray,
    wy1: np.ndarray,
    *,
    low: bool,
    left: bool,
    across_b: float,
    deep_b: float,
    court: _Court | None,
    stretch: AlleyStretch | None,
    segs: np.ndarray,
) -> np.ndarray:
    """Which windows stand a court the partial alley feeds anywhere but
    against its covered stretch (:class:`AlleyStretch`)."""
    if stretch is None or court is None or court.beside_band_ft > 0 or court.depth_ft <= 0:
        return np.zeros(len(wx0), dtype=bool)
    got = _court_boxes(
        wx0, wy0, wy1, low=low, left=left, across_b=across_b, deep_b=deep_b, court=court
    )
    if got is None:
        return np.zeros(len(wx0), dtype=bool)
    cx0, cy0, cx1, cy1 = got[1]
    return ~_on_stretch(cx0, cx1, cy1 if low else cy0, stretch, segs)


def court_on_stretch(
    building: BaseGeometry, court: BaseGeometry, stretch: AlleyStretch
) -> bool:
    """Whether a drawn ``court`` stands against the covered stretch of a
    partial rear alley (:class:`AlleyStretch`), read in the court's own
    frame: the axis that parts it from ``building`` is its depth, and its
    far edge the one away from the building. A court that is not a
    rectangle is read on its bounds in that frame."""
    ring = list(court.exterior.coords)
    if len(ring) < 4:
        return False
    (ax, ay), (bx, by) = ring[0][:2], ring[1][:2]
    turn = -math.degrees(math.atan2(by - ay, bx - ax))
    c = affinity.rotate(court, turn, origin=(0.0, 0.0))
    b = affinity.rotate(building, turn, origin=(0.0, 0.0))
    t = math.radians(turn)
    cos, sin = math.cos(t), math.sin(t)
    raw = np.asarray(stretch.lines, dtype=float).reshape(-1, 4)
    segs = np.column_stack(
        (
            raw[:, 0] * cos - raw[:, 1] * sin,
            raw[:, 0] * sin + raw[:, 1] * cos,
            raw[:, 2] * cos - raw[:, 3] * sin,
            raw[:, 2] * sin + raw[:, 3] * cos,
        )
    )
    cb, bb = c.bounds, b.bounds

    def overlap(i: int) -> float:
        return min(cb[i + 2], bb[i + 2]) - max(cb[i], bb[i])

    if overlap(1) > overlap(0):
        # The two stand side by side along x: x is the depth. Swap the axes.
        cb = (cb[1], cb[0], cb[3], cb[2])
        bb = (bb[1], bb[0], bb[3], bb[2])
        segs = segs[:, [1, 0, 3, 2]]
    far = cb[3] if (cb[1] + cb[3]) >= (bb[1] + bb[3]) else cb[1]
    got = _on_stretch(
        np.asarray([cb[0]]), np.asarray([cb[2]]), np.asarray([far]), stretch, segs
    )
    return bool(got[0])


def stretch_window(
    fitter: Fitter,
    fit: Fit,
    *,
    width_ft: float,
    depth_ft: float,
    court_depth_ft: float,
    court_beyond_ft: float,
    stretch: AlleyStretch,
    court_overlap_ft: float = 0.0,
) -> bool:
    """Whether any window the fitter holds, at ANY of its angles, stands
    the fit's plan with its court against the covered stretch
    (:class:`AlleyStretch`; FOLLOWUPS 3(c)). The same windows
    :func:`draw` places in -- the room ``fit.across_ft`` wide, the building
    plus the court's charge deep, the court's run past it on the court's
    ground -- every one of them, not thinned. Where none does, the partial
    alley is no aisle for this plan and the court keeps its own
    (:func:`flats.ingest.quadfit._screen_on`)."""
    if fit.across_ft is None or court_depth_ft <= 0:
        return False
    if fit.orientation is Orientation.depth_facing:
        deep_b = width_ft
    else:
        deep_b = depth_ft
    over = max(0.0, court_depth_ft - max(court_beyond_ft, 0.0))
    for grid in fitter.grids:
        res = grid.res
        w_cells = cells_for(fit.across_ft, res)
        need = cells_for(deep_b + max(court_beyond_ft, 0.0), res)
        masks = fitter.court_masks(grid, need, w_cells, over)
        if masks is None:
            continue
        segs = _lines_local(stretch.lines, grid)
        for low in (True, False):
            hits = np.argwhere(masks[0 if low else 1])
            if not len(hits):
                continue
            wx0 = grid.minx + hits[:, 1] * res
            wy0 = grid.miny + hits[:, 0] * res
            if low:
                far = wy0 + deep_b + court_depth_ft
            else:
                far = wy0 + need * res - deep_b - court_depth_ft
            if _on_stretch(
                wx0 - court_overlap_ft, wx0 + fit.across_ft, far, stretch, segs
            ).any():
                return True
    return False


def _column_side(
    alley_lines: Iterable[tuple[float, float, float, float]],
    grid: Grid,
    x0: float,
    x1: float,
    across_ft: float,
) -> tuple[float, float] | None:
    """The strip ``across_ft`` wide at the side of ``[x0, x1]`` (the court's
    span in the grid's frame) nearer the side alley's lines: where a column
    of stalls along the alley stands (FOLLOWUPS 5). ``None`` where there is
    no column, no alley line, or the column fills the span."""
    if across_ft <= 0 or across_ft >= x1 - x0:
        return None
    local = _lines_local(alley_lines, grid)
    if not len(local):
        return None
    mid = (local[:, 0] + local[:, 2]) / 2.0
    weight = np.hypot(local[:, 2] - local[:, 0], local[:, 3] - local[:, 1])
    ax = float(np.average(mid, weights=weight)) if weight.sum() > 0 else float(mid.mean())
    if ax <= (x0 + x1) / 2.0:
        return x0, x0 + across_ft
    return x1 - across_ft, x1


@dataclass(frozen=True, slots=True)
class _Placed:
    grid: Grid
    row: int
    col: int
    d_cells: int
    #: The street is at the window's low-``y`` end.
    low: bool
    #: The building stands at the window's low-``x`` side, the lane beyond it.
    left: bool


def _place(
    grids: Sequence[Grid],
    d_cells: int,
    w_cells: int,
    *,
    across_b: float,
    deep_b: float,
    street: np.ndarray,
    fitter: Fitter | None = None,
    over_ft: float = 0.0,
    lane_outside: bool = False,
    court: _Court | None = None,
    yard: Iterable[tuple[float, float, float, float]] = (),
    yard_moves: bool = True,
    stretch: AlleyStretch | None = None,
    groups: Sequence[np.ndarray] = (),
) -> _Placed | None:
    """The window of this size, and the way round, that puts the building
    nearest the street.

    Every window that fits is a candidate, each four ways (street at either
    end, lane on either side); the one whose building is nearest the front
    lines wins; between windows equally near, the one nearest every street
    direction in ``groups`` (:func:`_street_groups`: a corner building in
    the corner), then the court's distance from them the other way -- the
    parking stands behind, not in front. Without front lines, the
    first window, street at its low end.

    ``over_ft`` is how far the court runs past the window's far end; with
    the ``fitter`` that holds the court's ground, a window and a way round
    count only where that run lands on it (FOLLOWUPS 33) -- the court the
    fit passed, not one drawn off the lot.

    ``yard`` is the lines whose yard the court may not stand in (Steph
    2026-11-08; :func:`flats.ingest.quadfit.court_yard_lines`) and ``court``
    the court the plan draws: a window whose court stands between its
    building and one of them (:func:`_between_boxes`) is taken only where no
    other way stands the plan, so the drawing still shows where it would go
    and the caller reads it (:func:`court_between`). ``stretch`` likewise: a
    window whose court a partial rear alley feeds but that does not stand it
    against the covered stretch (:class:`AlleyStretch`) is taken only where
    no other way stands the plan. ``yard_moves`` False
    takes a clear window only as near the street as the nearest at all --
    the same window turned round, the court on the building's other flank:
    a court whose way in the drawing does not place (beside the building, fed
    across a side yard, along an alley) is not moved back from the street.
    """
    yard = tuple(yard)
    bests: list[tuple[float, float, float, _Placed]] = []
    fallbacks: list[tuple[float, float, float, _Placed]] = []
    for grid in grids:
        if fitter is not None:
            masks = fitter.court_masks(grid, d_cells, w_cells, over_ft)
        else:
            w = grid._windows(d_cells, w_cells)
            masks = None if w is None else (w == d_cells * w_cells,) * 2
        if masks is None:
            continue
        # Street at the low end, the court past the high end; and the other way.
        ways = {True: masks[0], False: masks[1]}
        hits = np.argwhere(masks[0] | masks[1])
        if not len(hits):
            continue
        if not len(street):
            low = bool(masks[0][hits[0][0], hits[0][1]])
            return _Placed(grid, int(hits[0][0]), int(hits[0][1]), d_cells, low, True)
        if len(hits) > MAX_CANDIDATES:
            hits = hits[np.linspace(0, len(hits) - 1, MAX_CANDIDATES).astype(int)]
        pts = _local(street, grid)
        gpts = [_local(g, grid) for g in groups]
        yard_local = _lines_local(yard, grid) if court is not None else np.empty((0, 4))
        segs = _lines_local(stretch.lines, grid) if stretch is not None else np.empty((0, 4))
        res = grid.res
        wx0 = grid.minx + hits[:, 1] * res
        wy0 = grid.miny + hits[:, 0] * res
        wx1 = wx0 + w_cells * res
        wy1 = wy0 + d_cells * res
        for low in (True, False):
            way = ways[low][hits[:, 0], hits[:, 1]]
            if not way.any():
                continue
            by0, by1 = (wy0, wy0 + deep_b) if low else (wy1 - deep_b, wy1)
            cy0, cy1 = (by1, wy1) if low else (wy0, by0)
            court_ft = _box_distance(wx0, cy0, wx1, cy1, pts)
            for left in ((False,) if lane_outside else (True, False)):
                bx0, bx1 = (wx0, wx0 + across_b) if left else (wx1 - across_b, wx1)
                building = np.where(way, _box_distance(bx0, by0, bx1, by1, pts), np.inf)
                spread = _spread(bx0, by0, bx1, by1, gpts)
                bad = _yard_bad(
                    wx0, wy0, wy1, low=low, left=left, across_b=across_b, deep_b=deep_b,
                    court=court, yard=yard_local,
                ) | _stretch_bad(
                    wx0, wy0, wy1, low=low, left=left, across_b=across_b, deep_b=deep_b,
                    court=court, stretch=stretch, segs=segs,
                )
                for clear in (True, False):
                    ranked = np.where(bad, np.inf, building) if clear else building
                    ranked = _near_tie(ranked, res)
                    i = int(np.lexsort((-court_ft, spread, ranked))[0])
                    if not math.isfinite(float(ranked[i])):
                        continue
                    key = (float(building[i]), float(spread[i]), -float(court_ft[i]))
                    hit = hits[i]
                    got = (*key, _Placed(grid, int(hit[0]), int(hit[1]), d_cells, low, left))
                    (bests if clear else fallbacks).append(got)
    cell = max((g.res for g in grids), default=0.0)
    best = _pick_near(bests, cell)
    fallback = _pick_near(fallbacks, cell)
    if (
        # A court the partial alley feeds is reached from the alley: moving
        # the plan back toward it is how it reaches the stretch.
        not yard_moves
        and stretch is None
        and best is not None
        and fallback is not None
        and best[0] > fallback[0] + (grids[0].res if grids else 0.0)
    ):
        best = None
    held = best or fallback
    return None if held is None else held[3]


#: At most this many windows are kept per grid when the alternatives are
#: listed (:func:`_options`), spread evenly over the ones that hold.
OPTIONS_PER_GRID = 160
#: The lattice the alternatives are cut on, in cells: neighbouring windows
#: draw nearly the same pad, so every few feet is enough.
OPTIONS_STRIDE_CELLS = 6


def _options(
    grids: Sequence[Grid],
    d_cells: int,
    w_cells: int,
    *,
    across_b: float,
    deep_b: float,
    street: np.ndarray,
    fitter: Fitter,
    over_ft: float,
    max_front_ft: float | None,
    include_frontmost: bool,
    lane_outside: bool = False,
    court: _Court | None = None,
    yard: Iterable[tuple[float, float, float, float]] = (),
    stretch: AlleyStretch | None = None,
    groups: Sequence[np.ndarray] = (),
) -> list[_Placed]:
    """Every way the window can stand on the lot with the building toward
    the street and the court behind it, thinned to a lattice
    (:data:`OPTIONS_STRIDE_CELLS`) and to :data:`OPTIONS_PER_GRID`.

    The building must stand nearer the front lines than the court does, and
    no further from them than ``max_front_ft`` where the code sets a
    maximum front setback. When requested, the nearest valid window is kept
    ahead of the thinned lattice so a boundary-flush option is not skipped
    (between equally near ones, the nearest every street direction in
    ``groups``, as :func:`_place`).
    Nothing is ranked here: the caller grades them. With ``yard`` and
    ``court`` (:func:`_place`), a window whose court stands between its
    building and a yard line is not listed at all: the placements the fire,
    flatter and front-maximum searches choose among keep the parking out of
    the front yard (Steph 2026-11-08). With ``stretch``, nor is a window
    whose court the partial rear alley feeds standing anywhere but against
    its covered stretch (:class:`AlleyStretch`).
    """
    out: list[_Placed] = []
    yard = tuple(yard)
    spec = court
    fronts: list[tuple[float, float, _Placed]] = []
    if not len(street):
        return out
    for grid in grids:
        masks = fitter.court_masks(grid, d_cells, w_cells, over_ft)
        yard_local = _lines_local(yard, grid) if spec is not None else np.empty((0, 4))
        segs = _lines_local(stretch.lines, grid) if stretch is not None else np.empty((0, 4))
        if masks is None:
            continue
        hits = np.argwhere(masks[0] | masks[1])
        if not len(hits):
            continue
        all_hits = hits
        stride = OPTIONS_STRIDE_CELLS
        keep = (hits[:, 0] % stride == 0) & (hits[:, 1] % stride == 0)
        # A window the lattice misses still counts where it is the only way.
        lattice = hits[keep] if keep.any() else hits
        if len(lattice) > OPTIONS_PER_GRID:
            lattice = lattice[np.linspace(0, len(lattice) - 1, OPTIONS_PER_GRID).astype(int)]
        pts = _local(street, grid)
        res = grid.res
        wx0 = grid.minx + lattice[:, 1] * res
        wy0 = grid.miny + lattice[:, 0] * res
        wx1 = wx0 + w_cells * res
        wy1 = wy0 + d_cells * res
        for low in (True, False):
            way = masks[0 if low else 1][lattice[:, 0], lattice[:, 1]]
            if not way.any():
                continue
            by0, by1 = (wy0, wy0 + deep_b) if low else (wy1 - deep_b, wy1)
            cy0, cy1 = (by1, wy1) if low else (wy0, by0)
            court = _box_distance(wx0, cy0, wx1, cy1, pts)
            for left in ((False,) if lane_outside else (True, False)):
                bx0, bx1 = (wx0, wx0 + across_b) if left else (wx1 - across_b, wx1)
                building = _box_distance(bx0, by0, bx1, by1, pts)
                ok = way & (building < court) & ~_yard_bad(
                    wx0, wy0, wy1, low=low, left=left, across_b=across_b, deep_b=deep_b,
                    court=spec, yard=yard_local,
                ) & ~_stretch_bad(
                    wx0, wy0, wy1, low=low, left=left, across_b=across_b, deep_b=deep_b,
                    court=spec, stretch=stretch, segs=segs,
                )
                if max_front_ft is not None:
                    ok &= building <= max_front_ft
                for i in np.nonzero(ok)[0]:
                    hit = lattice[i]
                    out.append(_Placed(grid, int(hit[0]), int(hit[1]), d_cells, low, left))
        if include_frontmost and max_front_ft is not None:
            pts = _local(street, grid)
            gpts = [_local(g, grid) for g in groups]
            res = grid.res
            wx0 = grid.minx + all_hits[:, 1] * res
            wy0 = grid.miny + all_hits[:, 0] * res
            wx1 = wx0 + w_cells * res
            wy1 = wy0 + d_cells * res
            for low in (True, False):
                way = masks[0 if low else 1][all_hits[:, 0], all_hits[:, 1]]
                if not way.any():
                    continue
                by0, by1 = (wy0, wy0 + deep_b) if low else (wy1 - deep_b, wy1)
                cy0, cy1 = (by1, wy1) if low else (wy0, by0)
                court = _box_distance(wx0, cy0, wx1, cy1, pts)
                for left in (True, False):
                    bx0, bx1 = (wx0, wx0 + across_b) if left else (wx1 - across_b, wx1)
                    building = _box_distance(bx0, by0, bx1, by1, pts)
                    valid = (
                        way
                        & (building < court)
                        & (building <= max_front_ft)
                        & ~_yard_bad(
                            wx0, wy0, wy1, low=low, left=left and not lane_outside,
                            across_b=across_b, deep_b=deep_b, court=spec, yard=yard_local,
                        )
                        & ~_stretch_bad(
                            wx0, wy0, wy1, low=low, left=left and not lane_outside,
                            across_b=across_b, deep_b=deep_b, court=spec, stretch=stretch,
                            segs=segs,
                        )
                    )
                    candidates = np.nonzero(valid)[0]
                    if not len(candidates):
                        continue
                    spread = _spread(
                        bx0[candidates], by0[candidates], bx1[candidates], by1[candidates], gpts
                    )
                    j = int(
                        np.lexsort((spread, _near_tie(building[candidates], grid.res)))[0]
                    )
                    i = candidates[j]
                    hit = all_hits[i]
                    placed = _Placed(grid, int(hit[0]), int(hit[1]), d_cells, low, left)
                    fronts.append((float(building[i]), float(spread[j]), placed))
    frontmost = _pick_near(fronts, max((g.res for g in grids), default=0.0))
    if frontmost is not None:
        out.insert(0, frontmost[2])
    return out


def draw(
    fitter: Fitter,
    fit: Fit,
    *,
    width_ft: float,
    depth_ft: float,
    lane_ft: float,
    court_depth_ft: float,
    court_beyond_ft: float,
    street: Iterable[tuple[float, float, float, float]] = (),
    side_streets: Iterable[tuple[float, float, float, float]] = (),
    beside_band_ft: float = 0.0,
    beside_len_ft: float = 0.0,
    paved_across_ft: float | None = None,
    gap_ft: float = 0.0,
    side_drive: bool = False,
    lane_overlap_ft: float = 0.0,
    court_overlap_ft: float = 0.0,
    short_ft: float = 0.0,
    where: _Placed | None = None,
    listing: list[_Placed] | None = None,
    max_front_ft: float | None = None,
    include_frontmost: bool = False,
    yard: Iterable[tuple[float, float, float, float]] = (),
    yard_moves: bool = True,
    stretch: AlleyStretch | None = None,
    column_across_ft: float = 0.0,
    alley_lines: Iterable[tuple[float, float, float, float]] = (),
) -> Drawing | None:
    """The fit drawn: room, building, lane and court, in world coordinates.

    ``width_ft`` / ``depth_ft`` are the design's footprint, unrotated;
    ``fit.orientation`` says which stands across. ``court_depth_ft`` is the
    whole court behind the wall (gap, stalls, aisle), ``court_beyond_ft`` the
    part of it the envelope has to hold (the rest stands in the rear yard).
    ``street`` is the lot's front lines, ``(x1, y1, x2, y2)``. ``None`` where
    the search found no room at the fit's width at all. ``side_streets`` is
    a corner's side-street lines: never what the building is set toward,
    only what breaks a tie between windows equally near the front -- the
    one nearest every street direction wins (:func:`_street_groups`; rel4
    move-read finding 3).

    ``beside_band_ft`` draws a court BESIDE the building instead
    (:attr:`flats.fit.rectangle.Fit.beside`): the band on the building's
    flank where the lane would be, ``beside_len_ft`` long from the front
    line, and no lane -- the court's aisle is the drive.
    ``paved_across_ft`` and ``gap_ft`` ask for :attr:`Drawing.paved` too: the
    width the court's stalls and aisle pave across (the wider of the row and
    the lane that reaches it) and the unpaved standoff off the rear wall;
    ``side_drive`` says the court is fed across a side yard (a side street
    or a side alley) and paves its depth band across the whole lot.
    ``lane_overlap_ft`` and ``court_overlap_ft`` stand the parking on the
    low-x side of the room and draw that amount into the side setback.

    ``short_ft`` is how far short of the plan the room may be and still be
    drawn as fitting: the fit's tolerance, on a plan the screen passed tight
    (:attr:`flats.score.screen.Screening.tight_fit`, Steph 2026-09-25). Only
    where no full window stands; the room found is that much shallower, the
    building and court are drawn whole, and the drawing says ``tight``. A
    building that stands somewhere is one a hose route and a pad grade can be
    measured to (FOLLOWUPS 45, 49(d)).

    ``where`` draws the plan at a window :func:`_options` listed instead of
    the one nearest the street (FOLLOWUPS 57). ``listing``, when given,
    asks for those windows instead of a drawing: they are appended to it
    and ``None`` comes back; ``max_front_ft`` bounds how far from the front
    lines the building may stand in them. ``include_frontmost`` keeps the
    nearest valid option in a listing even when it falls between lattice
    windows.

    ``yard`` is the lines whose yard the court may not stand in (Steph
    2026-11-08, no front-yard parking; :func:`flats.ingest.quadfit.
    court_yard_lines`): the window chosen is the nearest whose court stands
    clear of them (:func:`_place`), else the nearest at all, which the
    caller reads with :func:`court_between`; a listing holds only clear
    windows (:func:`_options`). ``yard_moves`` is :func:`_place`'s.

    ``stretch`` is where a partial rear alley serves as the court's aisle
    (:class:`AlleyStretch`, FOLLOWUPS 3(c)): the court is drawn against the
    covered stretch wherever a window allows, and a listing holds only those
    windows; the caller reads the drawing with :func:`court_on_stretch`.

    ``column_across_ft`` draws a column of stalls along a side alley
    (:attr:`flats.fit.rectangle.Fit.column`; :func:`flats.score.paper.
    side_column_across`): the court ``court_depth_ft`` deep behind the
    building but only this wide, against the room's side nearer
    ``alley_lines`` (the side alley's lot lines). Without ``alley_lines``,
    or where the column is as wide as the room, the court spans the room.
    """
    if fit.across_ft is None or fit.angle_deg is None:
        return None
    grids = _grids_at(fitter, fit.angle_deg)
    if not grids:
        return None
    if fit.orientation is Orientation.depth_facing:
        across_b, deep_b = depth_ft, width_ft
    else:
        across_b, deep_b = width_ft, depth_ft
    res = grids[0].res
    w_cells = cells_for(fit.across_ft, res)
    need = cells_for(deep_b + max(court_beyond_ft, 0.0), res)
    street = tuple(street)
    pts = _along(street)
    groups = _street_groups(street + tuple(side_streets))

    # The room: the window the fit needs where one exists; otherwise the
    # deepest the lot holds at that width.
    # How far the court runs past the window: behind, its depth less the
    # charge; beside, its row past the rear wall less the charge.
    if beside_band_ft > 0:
        over = max(0.0, beside_len_ft - deep_b - max(court_beyond_ft, 0.0))
    else:
        over = max(0.0, court_depth_ft - max(court_beyond_ft, 0.0))
    lane_outside = lane_overlap_ft > 0 or court_overlap_ft > 0
    yard = tuple(yard)
    spec = (
        _Court(
            across_ft=fit.across_ft,
            depth_ft=court_depth_ft,
            overlap_ft=court_overlap_ft,
            beside_band_ft=beside_band_ft,
            beside_len_ft=beside_len_ft,
        )
        if yard or stretch is not None
        else None
    )
    if listing is not None:
        listing.extend(
            _options(
                grids, need, w_cells, across_b=across_b, deep_b=deep_b, street=pts,
                fitter=fitter, over_ft=over, max_front_ft=max_front_ft,
                include_frontmost=include_frontmost,
                lane_outside=lane_outside,
                court=spec,
                yard=yard,
                stretch=stretch,
                groups=groups,
            )
        )
        return None
    placed = (
        replace(where, left=False)
        if where is not None and lane_outside
        else where
    ) or _place(
        grids,
        need,
        w_cells,
        across_b=across_b,
        deep_b=deep_b,
        street=pts,
        fitter=fitter,
        over_ft=over,
        lane_outside=lane_outside,
        court=spec,
        yard=yard,
        yard_moves=yard_moves,
        stretch=stretch,
        groups=groups,
    )
    tight = False
    if placed is None and short_ft > 0:
        short = cells_for(max(deep_b + max(court_beyond_ft, 0.0) - short_ft, res), res)
        if short < need:
            placed = _place(
                grids,
                short,
                w_cells,
                across_b=across_b,
                deep_b=deep_b,
                street=pts,
                lane_outside=lane_outside,
                fitter=fitter,
                over_ft=over,
                court=spec,
                yard=yard,
                yard_moves=yard_moves,
                stretch=stretch,
                groups=groups,
            )
            tight = placed is not None
    fits = placed is not None
    if placed is None:
        d_cells = max(g.max_depth_cells(w_cells) for g in grids)
        if d_cells < 1:
            return None
        placed = _place(
            grids,
            d_cells,
            w_cells,
            across_b=across_b,
            deep_b=min(deep_b, d_cells * res),
            street=pts,
            lane_outside=lane_outside,
            groups=groups,
        )
        if placed is None:
            return None

    grid = placed.grid
    x0 = grid.minx + placed.col * grid.res
    y0 = grid.miny + placed.row * grid.res
    across = fit.across_ft
    room_deep = placed.d_cells * grid.res
    # The street end, and the direction into the lot from it.
    face, sign = (y0, 1.0) if placed.low else (y0 + room_deep, -1.0)
    # The building's side of the room, and the lane beyond it.
    flank = beside_band_ft if beside_band_ft > 0 else lane_ft
    bx0 = x0 if placed.left else x0 + across - across_b
    lx0 = bx0 + across_b if placed.left else bx0 - flank

    def band(a: float, b: float, left: float, right: float) -> BaseGeometry:
        y1, y2 = face + sign * a, face + sign * b
        return shapely.box(left, min(y1, y2), right, max(y1, y2))

    room = shapely.box(x0, y0, x0 + across, y0 + room_deep)
    building = band(0.0, deep_b, bx0, bx0 + across_b)
    lane = band(0.0, deep_b, lx0, lx0 + lane_ft) if lane_ft > 0 and not beside_band_ft else None
    if beside_band_ft > 0:
        court = band(0.0, beside_len_ft, lx0, lx0 + beside_band_ft)
    elif court_depth_ft > 0:
        cx0, cx1 = x0 - court_overlap_ft, x0 + across
        at = _column_side(alley_lines, grid, cx0, cx1, column_across_ft)
        if at is not None:
            cx0, cx1 = at
        court = band(deep_b, deep_b + court_depth_ft, cx0, cx1)
    else:
        court = None

    def world(g: BaseGeometry | None) -> BaseGeometry | None:
        return None if g is None else affinity.rotate(g, grid.angle_deg, origin=grid.origin)

    paved: list[BaseGeometry] = []
    rows: list[BaseGeometry] = []
    if side_drive and court_depth_ft > 0:
        # The drive meets the court somewhere along a side lot line the
        # drawing does not know: pave the court's depth band clean across,
        # far past any lot line (the lot clips it).
        reach = SIDE_DRIVE_REACH_FT
        paved.append(
            world(band(deep_b + gap_ft, deep_b + court_depth_ft, x0 - reach, x0 + across + reach))
        )
        rows.append(world(band(deep_b + gap_ft, deep_b + court_depth_ft, x0, x0 + across)))
    elif paved_across_ft is not None and court_depth_ft > 0:
        outer_x0, outer_x1 = x0 - court_overlap_ft, x0 + across
        pw = min(paved_across_ft, outer_x1 - outer_x0)
        if lane_ft > 0:
            # The row stands against the lane, so the lane meets the aisle.
            sides = [lx0 + lane_ft - pw] if placed.left else [lx0]
        else:
            sides = [outer_x0, outer_x1 - pw]
        way_in = band(0.0, deep_b + gap_ft, lx0, lx0 + lane_ft) if lane_ft > 0 else None
        for left in dict.fromkeys(sides):
            left = min(max(left, outer_x0), outer_x1 - pw)
            shape = band(deep_b + gap_ft, deep_b + court_depth_ft, left, left + pw)
            rows.append(world(shape))
            if way_in is not None:
                shape = shape.union(way_in)
            paved.append(world(shape))

    return Drawing(
        room=world(room),
        building=world(building),
        lane=world(lane),
        court=world(court),
        fits=fits,
        paved=tuple(paved),
        rows=tuple(rows),
        tight=tight,
    )
