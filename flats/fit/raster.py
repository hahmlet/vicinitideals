"""Turn a buildable envelope into something a rectangle query can run against.

The envelope is an arbitrary polygon; the question is whether an axis-aligned
W×D rectangle fits inside it. Rasterizing to a grid turns that into a
constant-time query per candidate size, via an integral image: the sum over any
rectangular window equals four array lookups, and the window is buildable
exactly when that sum equals its cell count.

**Every approximation here errs toward the lot being smaller than it is.** A
cell counts as buildable only when all four of its corners are inside the
envelope, so a cell the boundary clips is discarded even though part of it is
usable, and a required size rounds *up* to whole cells. The result is that a
reported fit is real, while a reported miss may be off by up to one cell —
which is why ``fit_ft`` in ``flats/config/slack.yaml`` carries a tolerance of
exactly one cell width. That tolerance is what stops the rasterizer from
inventing REDs; nothing about it can invent a GREEN.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry.base import BaseGeometry

#: Grid cell size in feet. Half a foot is finer than any setback is written and
#: matches the ``fit_ft`` tolerance in the slack policy.
GRID_FT = 0.5

#: A lot big enough to blow past this is a farm, not an infill site. Rasterizing
#: it would cost gigabytes for an answer that is obviously yes.
MAX_CELLS = 4_000_000

#: Envelope fragments below this are slivers — no pod fits in one, and grinding
#: through their rasters costs more than the lots are worth.
MIN_PART_SQFT = 100.0

#: How far outside the envelope's edge a cell corner may stand and still count,
#: in cells: a millionth, to settle the boundary against floating-point noise
#: (:func:`_corners_inside`).
EDGE_EPS = 1e-6

#: Most corner points × crossings :func:`_corners_inside` compares at once: a
#: farm-sized part is answered a band of rows at a time.
SCAN_BLOCK = 4_000_000


@dataclass(frozen=True, slots=True)
class Grid:
    """One rotated envelope part, as an integral image of buildable cells."""

    integral: np.ndarray
    minx: float
    miny: float
    res: float
    angle_deg: float
    origin: tuple[float, float]
    #: :meth:`max_depth_cells` answers by width: a lot asks the same widths
    #: again for every design, fix and seat it tries.
    _depths: dict[int, int] = field(default_factory=dict, compare=False, repr=False)
    #: :meth:`max_width_cells` answers by depth, the same way.
    _widths: dict[int, int] = field(default_factory=dict, compare=False, repr=False)

    @property
    def rows(self) -> int:
        return int(self.integral.shape[0] - 1)

    @property
    def cols(self) -> int:
        return int(self.integral.shape[1] - 1)

    def _windows(self, d_cells: int, w_cells: int) -> np.ndarray | None:
        if d_cells < 1 or w_cells < 1 or d_cells > self.rows or w_cells > self.cols:
            return None
        s = self.integral
        return (
            s[d_cells:, w_cells:]
            - s[:-d_cells, w_cells:]
            - s[d_cells:, :-w_cells]
            + s[:-d_cells, :-w_cells]
        )

    def has_window(self, d_cells: int, w_cells: int) -> bool:
        """Does an all-buildable window of this size exist anywhere?"""
        w = self._windows(d_cells, w_cells)
        return bool(w is not None and (w == d_cells * w_cells).any())

    def first_window(self, d_cells: int, w_cells: int) -> tuple[int, int] | None:
        """Row/column of one fitting window, or None.

        The first hit in scan order, which puts the pod at the low corner of the
        envelope. Any fitting placement proves fitment; choosing among them
        (best solar, shortest driveway) is a site-planning question, not a
        screening one.
        """
        w = self._windows(d_cells, w_cells)
        if w is None:
            return None
        hits = np.argwhere(w == d_cells * w_cells)
        return (int(hits[0][0]), int(hits[0][1])) if len(hits) else None

    def max_depth_cells(self, w_cells: int) -> int:
        """Deepest window of the given width that fits.

        A window ``d`` deep and ``w_cells`` wide is all buildable exactly where
        ``d`` rows running down one column each hold ``w_cells`` buildable
        cells in a row from there: the answer is the longest such run, read
        in one pass (it was a binary search over :meth:`has_window`, the same
        answer at a ninth of the work).
        """
        got = self._depths.get(w_cells)
        if got is None:
            got = self._depths[w_cells] = self._longest_run(w_cells)
        return got

    def _longest_run(self, w_cells: int) -> int:
        if w_cells < 1 or w_cells > self.cols:
            return 0
        s = self.integral
        ok = (s[1:, w_cells:] - s[:-1, w_cells:] - s[1:, :-w_cells] + s[:-1, :-w_cells]) == w_cells
        if not ok.any():
            return 0
        count = np.cumsum(ok, axis=0, dtype=np.int32)
        # The count where each run last broke, carried down the column.
        broke = np.maximum.accumulate(np.where(ok, 0, count), axis=0)
        return int((count - broke).max())

    def max_width_cells(self, d_cells: int) -> int:
        """Widest window of the given depth that fits: :meth:`max_depth_cells`
        turned a quarter -- the longest run, along one row, of columns that
        each hold ``d_cells`` buildable cells down from there. How much wider
        a pod could be at the run it needs (FOLLOWUPS 37(ii))."""
        got = self._widths.get(d_cells)
        if got is None:
            got = self._widths[d_cells] = self._widest_run(d_cells)
        return got

    def _widest_run(self, d_cells: int) -> int:
        if d_cells < 1 or d_cells > self.rows:
            return 0
        s = self.integral
        ok = (s[d_cells:, 1:] - s[:-d_cells, 1:] - s[d_cells:, :-1] + s[:-d_cells, :-1]) == d_cells
        if not ok.any():
            return 0
        count = np.cumsum(ok, axis=1, dtype=np.int32)
        broke = np.maximum.accumulate(np.where(ok, 0, count), axis=1)
        return int((count - broke).max())

    def to_world(self, row: int, col: int, d_cells: int, w_cells: int):
        """The window as a polygon back in the lot's own coordinates."""
        x0 = self.minx + col * self.res
        y0 = self.miny + row * self.res
        rect = shapely.box(x0, y0, x0 + w_cells * self.res, y0 + d_cells * self.res)
        return affinity.rotate(rect, self.angle_deg, origin=self.origin)


def cells_for(length_ft: float, res: float = GRID_FT) -> int:
    """Whole cells needed to cover a length — always rounded up.

    Rounding down would let a pod claim to fit in less space than it occupies,
    which is the one direction of error this screen cannot tolerate.
    """
    return max(1, math.ceil(length_ft / res - 1e-9))


def _cell_grid(
    part: BaseGeometry,
    res: float,
    lattice: tuple[float, float, int, int] | None = None,
) -> np.ndarray | None:
    """Boolean buildable-cell array for one polygon, by corner containment.

    Corners are tested against the envelope grown by a hair. Containment
    excludes the boundary, so without that nudge a rectangular envelope would
    lose its outermost ring of cells to floating-point noise on its own edge —
    a foot in each dimension, invented out of arithmetic. The epsilon is a
    millionth of a cell: enough to settle the boundary, far too small to admit
    a placement that does not exist.

    ``lattice`` is ``(minx, miny, ncols, nrows)`` where the cells must sit on
    another grid's lines (:func:`ground_for`); the part's own bounds otherwise.
    """
    if lattice is None:
        minx, miny, maxx, maxy = part.bounds
        ncols = max(1, math.ceil((maxx - minx) / res))
        nrows = max(1, math.ceil((maxy - miny) / res))
    else:
        minx, miny, ncols, nrows = lattice
    if ncols * nrows > MAX_CELLS:
        return None
    xs = minx + np.arange(ncols + 1) * res
    ys = miny + np.arange(nrows + 1) * res
    inside = _corners_inside(part, xs, ys, res * EDGE_EPS)
    # All four corners, so a cell the boundary crosses is discarded. On a
    # concave envelope four inside corners do not strictly prove the cell is
    # inside; that residual error runs toward REVIEW, never toward a silent RED.
    return inside[:-1, :-1] & inside[1:, :-1] & inside[:-1, 1:] & inside[1:, 1:]


def _corners_inside(part: BaseGeometry, xs: np.ndarray, ys: np.ndarray, eps: float) -> np.ndarray:
    """Which lattice points ``(xs[c], ys[r])`` stand in ``part``, as a
    ``(len(ys), len(xs))`` array -- by scanline, not a point query each.

    Each row is read twice, ``eps / 2`` above and below its line, and a point
    counts where either reading puts it inside or within ``eps / 2`` of an
    edge crossing. So no reading ever falls on a vertex or along an edge
    (the cases a crossing count gets wrong), a point ON the boundary counts,
    and every point counted lies within ``eps`` of the polygon: inside the
    polygon grown by ``eps``, the probe the point queries asked
    (2026-10-04; they were half the county run). Holes count by the same
    crossings: a point is in where the crossings to its left are odd.
    """
    h = eps / 2
    edges = []
    for ring in (part.exterior, *part.interiors):
        c = np.asarray(ring.coords)[:, :2]
        edges.append(np.column_stack([c[:-1], c[1:]]))
    x0, y0, x1, y1 = np.concatenate(edges).T
    keep = y0 != y1  # a level edge crosses no reading: none sits on a vertex's line
    x0, y0, x1, y1 = x0[keep], y0[keep], x1[keep], y1[keep]
    lo, hi = np.minimum(y0, y1), np.maximum(y0, y1)
    slope = (x1 - x0) / (y1 - y0)
    nx = len(xs)
    res = float(xs[1] - xs[0]) if nx > 1 else 1.0
    out = np.zeros((len(ys), nx), dtype=bool)
    step = max(1, SCAN_BLOCK // max(1, nx + len(x0)))
    for r0 in range(0, len(ys), step):
        band = ys[r0 : r0 + step]
        marks = np.zeros(len(band) * (nx + 1) + 1, dtype=np.int32)
        for dy in (-h, h):
            yy = band[:, None] + dy
            hit = (lo <= yy) & (yy < hi)
            if not hit.any():
                continue
            # Each row's crossings, sorted along the row; a closed ring
            # crosses a line it does not touch an even number of times, so
            # they pair off into the runs the row spends inside.
            rr, ee = np.nonzero(hit)
            at = x0[ee] + (yy[rr, 0] - y0[ee]) * slope[ee]
            order = np.lexsort((at, rr))
            rr, at = rr[order], at[order]
            row, a, b = rr[0::2], at[0::2], at[1::2]
            # The points from a - h to b + h, as column numbers.
            first = np.clip(np.ceil((a - h - xs[0]) / res), 0, nx).astype(np.int64)
            last = np.clip(np.floor((b + h - xs[0]) / res) + 1, 0, nx).astype(np.int64)
            ok = first < last
            base = row[ok] * (nx + 1)
            np.add.at(marks, base + first[ok], 1)
            np.add.at(marks, base + last[ok], -1)
        runs = np.cumsum(marks[:-1].reshape(len(band), nx + 1), axis=1)[:, :nx]
        out[r0 : r0 + step] = runs > 0
    return out


def _integral(cell_ok: np.ndarray) -> np.ndarray:
    rows, cols = cell_ok.shape
    s = np.zeros((rows + 1, cols + 1), dtype=np.int32)
    np.cumsum(np.cumsum(cell_ok, axis=0), axis=1, out=s[1:, 1:])
    return s


def rasterize(
    envelope: BaseGeometry,
    angle_deg: float,
    *,
    res: float = GRID_FT,
    origin: tuple[float, float] | None = None,
) -> list[Grid]:
    """Grids for one envelope at one rotation — one per disjoint part.

    The envelope is rotated by ``-angle_deg`` so that testing an axis-aligned
    rectangle is equivalent to testing a pod at ``angle_deg``. Parts are kept
    separate rather than rasterized together: a rectangle spanning the gap
    between two disjoint fragments would score as fitting when it does not.
    """
    if envelope is None or envelope.is_empty:
        return []
    if res <= 0:
        raise ValueError(f"grid resolution must be positive, got {res}")

    if origin is None:
        c = envelope.centroid
        origin = (c.x, c.y)
    rotated = affinity.rotate(envelope, -angle_deg, origin=origin)

    grids: list[Grid] = []
    for part in shapely.get_parts(rotated):
        if part.geom_type != "Polygon" or part.area < MIN_PART_SQFT:
            continue
        cell_ok = _cell_grid(part, res)
        if cell_ok is None or not cell_ok.any():
            continue
        grids.append(
            Grid(
                integral=_integral(cell_ok),
                minx=part.bounds[0],
                miny=part.bounds[1],
                res=res,
                angle_deg=angle_deg,
                origin=origin,
            )
        )
    return grids


@dataclass(frozen=True, slots=True)
class Ground:
    """The ground a parking court may stand on (FOLLOWUPS 33), on one
    :class:`Grid`'s own cell lines: the grid's cell ``(r, c)`` is this
    one's ``(r + row0, c + col0)``. Holds the grid's envelope and more --
    the strip the envelope lost at the rear."""

    integral: np.ndarray
    row0: int
    col0: int

    @property
    def rows(self) -> int:
        return int(self.integral.shape[0] - 1)

    @property
    def cols(self) -> int:
        return int(self.integral.shape[1] - 1)


def ground_for(grid: Grid, ground: BaseGeometry | None) -> Ground:
    """``ground`` rasterized on ``grid``'s lattice, at its angle.

    Only the part of ``ground`` the grid's envelope stands in: a court may
    not leap a gap the envelope's part does not span either. Every way this
    can fail -- no ground, no part holding the envelope, a part past
    :data:`MAX_CELLS` -- answers the grid's own envelope, the court then
    held to the ground the building stands on: smaller, never larger.
    """
    own = Ground(grid.integral, 0, 0)
    if ground is None or ground.is_empty:
        return own
    cells = np.argwhere(np.diff(np.diff(grid.integral, axis=0), axis=1) > 0)
    if not len(cells):
        return own
    r, c = cells[len(cells) // 2]
    probe = shapely.Point(grid.minx + (c + 0.5) * grid.res, grid.miny + (r + 0.5) * grid.res)
    rotated = affinity.rotate(ground, -grid.angle_deg, origin=grid.origin)
    part = next((p for p in shapely.get_parts(rotated) if p.geom_type == "Polygon" and p.covers(probe)), None)
    if part is None:
        return own
    res = grid.res
    minx, miny, maxx, maxy = part.bounds
    kx0 = math.floor((minx - grid.minx) / res)
    ky0 = math.floor((miny - grid.miny) / res)
    ncols = max(1, math.ceil((maxx - grid.minx) / res) - kx0)
    nrows = max(1, math.ceil((maxy - grid.miny) / res) - ky0)
    cell_ok = _cell_grid(
        part, res, (grid.minx + kx0 * res, grid.miny + ky0 * res, ncols, nrows)
    )
    if cell_ok is None:
        return own
    return Ground(_integral(cell_ok), -ky0, -kx0)


def _sums(integral: np.ndarray, d_cells: int, w_cells: int) -> np.ndarray | None:
    rows, cols = integral.shape[0] - 1, integral.shape[1] - 1
    if d_cells < 1 or w_cells < 1 or d_cells > rows or w_cells > cols:
        return None
    s = integral
    return (
        s[d_cells:, w_cells:]
        - s[:-d_cells, w_cells:]
        - s[d_cells:, :-w_cells]
        + s[:-d_cells, :-w_cells]
    ) == d_cells * w_cells


def _shifted(full: np.ndarray | None, shape: tuple[int, int], dr: int, dc: int) -> np.ndarray:
    """``out[r, c] = full[r + dr, c + dc]``, False where that falls outside."""
    out = np.zeros(shape, dtype=bool)
    if full is None:
        return out
    r0, r1 = max(0, -dr), min(shape[0], full.shape[0] - dr)
    c0, c1 = max(0, -dc), min(shape[1], full.shape[1] - dc)
    if r0 < r1 and c0 < c1:
        out[r0:r1, c0:c1] = full[r0 + dr : r1 + dr, c0 + dc : c1 + dc]
    return out


def court_windows(
    grid: Grid, ground: Ground, d_cells: int, w_cells: int, over_cells: int
) -> tuple[np.ndarray, np.ndarray] | None:
    """Which ``d_cells`` x ``w_cells`` windows of the envelope also have
    ``over_cells`` more of ``ground`` past one end, the same width: the
    court's run past the room (FOLLOWUPS 33). Two masks over the grid's
    windows: the run past the high-row end (the street at the low end), and
    past the low-row end. None where no window of that size fits at all."""
    inside = grid._windows(d_cells, w_cells)
    if inside is None:
        return None
    inside = inside == d_cells * w_cells
    if over_cells <= 0:
        return inside, inside
    run = _sums(ground.integral, d_cells + over_cells, w_cells)
    high = _shifted(run, inside.shape, ground.row0, ground.col0)
    low = _shifted(run, inside.shape, ground.row0 - over_cells, ground.col0)
    return inside & high, inside & low
