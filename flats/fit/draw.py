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
from typing import Iterable, Sequence

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
#: The front lines are sampled this often to find the street end.
STREET_STEP_FT = 2.0
#: Windows compared per grid, evenly spaced over every one that fits: a
#: big lot has hundreds of thousands, and the one nearest the street is
#: found about as well among a few thousand.
MAX_CANDIDATES = 4000


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
    #: not pavement. Empty where not asked. Read by the outdoor-area shape
    #: test (FOLLOWUPS 7(b)), never by the page.
    paved: tuple[BaseGeometry, ...] = ()

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


def _box_distance(
    x0: np.ndarray, y0: np.ndarray, x1: np.ndarray, y1: np.ndarray, pts: np.ndarray
) -> np.ndarray:
    """Distance from each box to the nearest of ``pts`` (0 where one is inside)."""
    px, py = pts[None, :, 0], pts[None, :, 1]
    dx = np.maximum(np.maximum(x0[:, None] - px, 0.0), px - x1[:, None])
    dy = np.maximum(np.maximum(y0[:, None] - py, 0.0), py - y1[:, None])
    return np.hypot(dx, dy).min(axis=1)


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
) -> _Placed | None:
    """The window of this size, and the way round, that puts the building
    nearest the street.

    Every window that fits is a candidate, each four ways (street at either
    end, lane on either side); the one whose building is nearest the front
    lines wins, the court's distance from them breaking a tie the other way
    -- the parking stands behind, not in front. Without front lines, the
    first window, street at its low end.
    """
    best: tuple[float, float, _Placed] | None = None
    for grid in grids:
        w = grid._windows(d_cells, w_cells)
        if w is None:
            continue
        hits = np.argwhere(w == d_cells * w_cells)
        if not len(hits):
            continue
        if not len(street):
            return _Placed(grid, int(hits[0][0]), int(hits[0][1]), d_cells, True, True)
        if len(hits) > MAX_CANDIDATES:
            hits = hits[np.linspace(0, len(hits) - 1, MAX_CANDIDATES).astype(int)]
        pts = _local(street, grid)
        res = grid.res
        wx0 = grid.minx + hits[:, 1] * res
        wy0 = grid.miny + hits[:, 0] * res
        wx1 = wx0 + w_cells * res
        wy1 = wy0 + d_cells * res
        for low in (True, False):
            by0, by1 = (wy0, wy0 + deep_b) if low else (wy1 - deep_b, wy1)
            cy0, cy1 = (by1, wy1) if low else (wy0, by0)
            court = _box_distance(wx0, cy0, wx1, cy1, pts)
            for left in (True, False):
                bx0, bx1 = (wx0, wx0 + across_b) if left else (wx1 - across_b, wx1)
                building = _box_distance(bx0, by0, bx1, by1, pts)
                i = int(np.lexsort((-court, building))[0])
                key = (float(building[i]), -float(court[i]))
                if best is None or key < best[:2]:
                    hit = hits[i]
                    best = (*key, _Placed(grid, int(hit[0]), int(hit[1]), d_cells, low, left))
    return None if best is None else best[2]


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
    beside_band_ft: float = 0.0,
    beside_len_ft: float = 0.0,
    paved_across_ft: float | None = None,
    gap_ft: float = 0.0,
) -> Drawing | None:
    """The fit drawn: room, building, lane and court, in world coordinates.

    ``width_ft`` / ``depth_ft`` are the design's footprint, unrotated;
    ``fit.orientation`` says which stands across. ``court_depth_ft`` is the
    whole court behind the wall (gap, stalls, aisle), ``court_beyond_ft`` the
    part of it the envelope has to hold (the rest stands in the rear yard).
    ``street`` is the lot's front lines, ``(x1, y1, x2, y2)``. ``None`` where
    the search found no room at the fit's width at all.

    ``beside_band_ft`` draws a court BESIDE the building instead
    (:attr:`flats.fit.rectangle.Fit.beside`): the band on the building's
    flank where the lane would be, ``beside_len_ft`` long from the front
    line, and no lane -- the court's aisle is the drive.
    ``paved_across_ft`` and ``gap_ft`` ask for :attr:`Drawing.paved` too: the
    width the court's stalls and aisle pave across (the wider of the row and
    the lane that reaches it) and the unpaved standoff off the rear wall.
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
    pts = _along(street)

    # The room: the window the fit needs where one exists; otherwise the
    # deepest the lot holds at that width.
    placed = _place(grids, need, w_cells, across_b=across_b, deep_b=deep_b, street=pts)
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
        court = band(deep_b, deep_b + court_depth_ft, x0, x0 + across)
    else:
        court = None

    def world(g: BaseGeometry | None) -> BaseGeometry | None:
        return None if g is None else affinity.rotate(g, grid.angle_deg, origin=grid.origin)

    paved: list[BaseGeometry] = []
    if paved_across_ft is not None and court_depth_ft > 0:
        pw = min(paved_across_ft, across)
        if lane_ft > 0:
            # The row stands against the lane, so the lane meets the aisle.
            sides = [lx0 + lane_ft - pw] if placed.left else [lx0]
        else:
            sides = [x0, x0 + across - pw]
        way_in = band(0.0, deep_b + gap_ft, lx0, lx0 + lane_ft) if lane_ft > 0 else None
        for left in dict.fromkeys(sides):
            left = min(max(left, x0), x0 + across - pw)
            shape = band(deep_b + gap_ft, deep_b + court_depth_ft, left, left + pw)
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
    )
