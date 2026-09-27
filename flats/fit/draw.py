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
building at the column's depth -- the column's side is not known here.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import shapely
from shapely import affinity
from shapely.geometry.base import BaseGeometry

from flats.designs.model import Orientation
from flats.fit.raster import Grid, cells_for
from flats.fit.rectangle import Fit, Fitter

#: Coordinates are stored to a tenth of a foot: finer than a county lot line
#: is good to, coarse enough to keep a lot's drawing a few hundred bytes.
#: The envelope is simplified to this before it is stored.
SIMPLIFY_FT = 0.5


@dataclass(frozen=True, slots=True)
class Drawing:
    """The shapes one fit is drawn as, in the lot's coordinates."""

    room: BaseGeometry
    building: BaseGeometry | None
    lane: BaseGeometry | None
    court: BaseGeometry | None
    #: The room holds the building and the court's excess: the fit passed.
    fits: bool

    def to_json(self, envelope: BaseGeometry | None = None) -> dict:
        """Rings of ``[x, y]`` pairs, rounded, for the lot page.

        ``envelope`` is the ground searched, stored beside the plan so the
        page draws the yards the lot lost as well as what stands in them.
        """
        out: dict = {"fits": self.fits, "room": _ring(self.room)}
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


def _local(points: Iterable[tuple[float, float]], grid: Grid) -> np.ndarray:
    """World points into the grid's unrotated frame."""
    t = math.radians(-grid.angle_deg)
    ox, oy = grid.origin
    pts = np.asarray(list(points), dtype=float).reshape(-1, 2)
    dx, dy = pts[:, 0] - ox, pts[:, 1] - oy
    return np.column_stack(
        (ox + dx * math.cos(t) - dy * math.sin(t), oy + dx * math.sin(t) + dy * math.cos(t))
    )


def _window(
    grid: Grid, d_cells: int, w_cells: int, street: np.ndarray | None
) -> tuple[int, int, bool] | None:
    """The window of this size nearest the street, and which end faces it.

    ``street`` is the front lines' midpoints in the grid's frame. The street
    end is the window's low-``y`` end when the street lies below the grid's
    middle, else its high end; among windows the one whose street end is
    nearest the street is taken, then the one nearest it across.
    """
    w = grid._windows(d_cells, w_cells)
    if w is None:
        return None
    hits = np.argwhere(w == d_cells * w_cells)
    if not len(hits):
        return None
    if street is None or not len(street):
        return int(hits[0][0]), int(hits[0][1]), True
    mid_y = grid.miny + grid.rows * grid.res / 2
    sy, sx = float(street[:, 1].mean()), float(street[:, 0].mean())
    low = sy <= mid_y
    rows, cols = hits[:, 0], hits[:, 1]
    end_y = grid.miny + (rows if low else rows + d_cells) * grid.res
    centre_x = grid.minx + (cols + w_cells / 2) * grid.res
    order = np.lexsort((np.abs(centre_x - sx), np.abs(end_y - sy)))
    best = hits[order[0]]
    return int(best[0]), int(best[1]), low


def draw(
    fitter: Fitter,
    fit: Fit,
    *,
    width_ft: float,
    depth_ft: float,
    lane_ft: float,
    court_depth_ft: float,
    court_beyond_ft: float,
    street: Iterable[tuple[float, float]] = (),
) -> Drawing | None:
    """The fit drawn: room, building, lane and court, in world coordinates.

    ``width_ft`` / ``depth_ft`` are the design's footprint, unrotated;
    ``fit.orientation`` says which stands across. ``court_depth_ft`` is the
    whole court behind the wall (gap, stalls, aisle), ``court_beyond_ft`` the
    part of it the envelope has to hold (the rest stands in the rear yard).
    ``street`` is the midpoints of the lot's front lines. ``None`` where the
    search found no room at the fit's width at all.
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
    street_pts = list(street)

    # The room: the window the fit needs where one exists; otherwise the
    # deepest the lot holds at that width.
    chosen: tuple[Grid, int, int, int, bool] | None = None
    fits = False
    for grid in grids:
        s = _local(street_pts, grid) if street_pts else None
        got = _window(grid, need, w_cells, s)
        if got is not None:
            chosen, fits = (grid, got[0], got[1], need, got[2]), True
            break
    if chosen is None:
        deepest = max(grids, key=lambda g: g.max_depth_cells(w_cells))
        d_cells = deepest.max_depth_cells(w_cells)
        if d_cells < 1:
            return None
        s = _local(street_pts, deepest) if street_pts else None
        got = _window(deepest, d_cells, w_cells, s)
        if got is None:
            return None
        chosen = (deepest, got[0], got[1], d_cells, got[2])

    grid, row, col, d_cells, low = chosen
    x0 = grid.minx + col * grid.res
    y0 = grid.miny + row * grid.res
    room_deep = d_cells * grid.res
    # The street end, and the direction into the lot from it.
    face, sign = (y0, 1.0) if low else (y0 + room_deep, -1.0)

    def band(a: float, b: float, left: float, right: float) -> BaseGeometry:
        y1, y2 = face + sign * a, face + sign * b
        return shapely.box(left, min(y1, y2), right, max(y1, y2))

    room = shapely.box(x0, y0, x0 + fit.across_ft, y0 + room_deep)
    building = band(0.0, deep_b, x0, x0 + across_b)
    lane = band(0.0, deep_b, x0 + across_b, x0 + across_b + lane_ft) if lane_ft > 0 else None
    court = (
        band(deep_b, deep_b + court_depth_ft, x0, x0 + fit.across_ft) if court_depth_ft > 0 else None
    )

    def world(g: BaseGeometry | None) -> BaseGeometry | None:
        return None if g is None else affinity.rotate(g, grid.angle_deg, origin=grid.origin)

    return Drawing(
        room=world(room),
        building=world(building),
        lane=world(lane),
        court=world(court),
        fits=fits,
    )
