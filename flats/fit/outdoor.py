"""The largest outdoor square a plan leaves on the real lot (FOLLOWUPS 7(b)).

Portland 33.110.240 asks each single-dwelling lot for an outdoor area of 250
sq ft (200 in R2.5) whose "shape ... must be such that a square of the stated
dimension will fit entirely in the outdoor area" -- 12 by 12 feet (10 by 10).
It must be contiguous, it "may not be used as vehicle area", it may extend
into the side and rear setbacks, and it "may not be located in the front
building setback" (33.110.240.B-C).

The screen's own window cannot answer that: it knows the rectangle the fit
searched, not the lot beside it, and a turned pod on a 50 ft lot fills its
window with building, lane and court while the side yards and the rear yard
stand empty. This module measures the ground itself:

    the lot polygon
      less the front building setback (a strip the front setback deep along
        every front line, round-ended: more than the code removes, never less)
      less the building, the lane and the paved court as the plan is drawn
        (:attr:`flats.fit.draw.Drawing.paved`)
      less every overlay carve on the lot (``carve_wkb``): 33.110.240 says
        nothing about environmental zones, and ground an overlay restricts is
        not ground this screen counts as a garden on its own say-so

and asks, piece by contiguous piece, whether a piece holding the required
area also holds the square, rasterized the way the fit is
(:mod:`flats.fit.raster`, a cell counts only when all four corners are
inside), at the plan's angle and the lot's street directions. Every
approximation shrinks the ground, so a square found is real; a miss may be up
to a cell short, which is the ``fit_ft`` tolerance's bargain again.
"""

from __future__ import annotations

from typing import Iterable, Sequence

import shapely
from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry

from flats.fit.raster import GRID_FT, rasterize


def open_ground(
    lot: BaseGeometry,
    *,
    front_lines: Iterable[tuple[float, float, float, float]],
    front_ft: float,
    taken: Sequence[BaseGeometry | None] = (),
    carve: BaseGeometry | None = None,
) -> BaseGeometry:
    """The lot less its front setback, what the plan stands and paves, and
    every overlay carve: where an outdoor area may be."""
    cut: list[BaseGeometry] = [g for g in taken if g is not None and not g.is_empty]
    if front_ft > 0:
        cut.extend(LineString([(x1, y1), (x2, y2)]).buffer(front_ft) for x1, y1, x2, y2 in front_lines)
    if carve is not None and not carve.is_empty:
        cut.append(carve)
    ground = lot.buffer(0)
    if cut:
        ground = ground.difference(shapely.union_all(cut))
    return ground


def largest_square(
    ground: BaseGeometry,
    angles: Iterable[float],
    *,
    min_area_sqft: float = 0.0,
    res: float = GRID_FT,
) -> float:
    """Side in feet of the largest square standing wholly inside one piece of
    ``ground`` whose area is at least ``min_area_sqft``, at any of ``angles``.

    0.0 where no piece is big enough. A lower bound, by whole cells.
    """
    if ground is None or ground.is_empty:
        return 0.0
    pieces = [
        p for p in shapely.get_parts(ground)
        if p.geom_type == "Polygon" and p.area >= max(min_area_sqft, 1e-9)
    ]
    best = 0
    for piece in pieces:
        origin = (piece.centroid.x, piece.centroid.y)
        for angle in dict.fromkeys(angles):
            for grid in rasterize(piece, angle, res=res, origin=origin):
                lo, hi = best, min(grid.rows, grid.cols)
                if hi <= lo:
                    continue
                # Largest k with a k-by-k window, by bisection: a window
                # that fits at k fits at every smaller k.
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if grid.has_window(mid, mid):
                        lo = mid
                    else:
                        hi = mid - 1
                best = max(best, lo)
    return best * res
