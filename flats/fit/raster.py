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
from dataclasses import dataclass

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


@dataclass(frozen=True, slots=True)
class Grid:
    """One rotated envelope part, as an integral image of buildable cells."""

    integral: np.ndarray
    minx: float
    miny: float
    res: float
    angle_deg: float
    origin: tuple[float, float]

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

        Binary search is valid because depth is monotone: any sub-window of an
        all-buildable window is itself all-buildable, so if depth d fits, every
        depth below it fits too.
        """
        lo, hi = 0, self.rows
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self.has_window(mid, w_cells):
                lo = mid
            else:
                hi = mid - 1
        return lo

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


def _cell_grid(part: BaseGeometry, res: float) -> np.ndarray | None:
    """Boolean buildable-cell array for one polygon, by corner containment.

    Corners are tested against the envelope grown by a hair. Containment
    excludes the boundary, so without that nudge a rectangular envelope would
    lose its outermost ring of cells to floating-point noise on its own edge —
    a foot in each dimension, invented out of arithmetic. The epsilon is a
    millionth of a cell: enough to settle the boundary, far too small to admit
    a placement that does not exist.
    """
    minx, miny, maxx, maxy = part.bounds
    ncols = max(1, math.ceil((maxx - minx) / res))
    nrows = max(1, math.ceil((maxy - miny) / res))
    if ncols * nrows > MAX_CELLS:
        return None
    xs = minx + np.arange(ncols + 1) * res
    ys = miny + np.arange(nrows + 1) * res
    x, y = np.meshgrid(xs, ys)
    probe = shapely.buffer(part, res * 1e-6)
    shapely.prepare(probe)
    inside = shapely.contains_xy(probe, x.ravel(), y.ravel()).reshape(x.shape)
    # All four corners, so a cell the boundary crosses is discarded. On a
    # concave envelope four inside corners do not strictly prove the cell is
    # inside; that residual error runs toward REVIEW, never toward a silent RED.
    return inside[:-1, :-1] & inside[1:, :-1] & inside[:-1, 1:] & inside[1:, 1:]


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
