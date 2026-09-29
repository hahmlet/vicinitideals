"""Does the pod fit — and by how much.

The screen needs more than a yes. A lot that clears by four feet and one that
clears by four inches are different prospects, and a lot that misses by three
inches is worth a phone call while one that misses by thirty is not. So every
fit answers with a continuous margin: the deepest rectangle of the required
width the envelope will hold, minus the depth the design needs.

Rasterizing is the expensive step and it does not depend on the design, so it
happens once per lot and every design in the catalog queries the same grids.
That is what makes comparing ten pod designs cost roughly what comparing one
costs, and it is why :class:`Fitter` is an object rather than a function.

The margin is a lower bound — see :mod:`flats.fit.raster` for why every rounding
here shrinks the lot rather than the pod. A miss inside one cell is a
measurement artifact, and the ``fit_ft`` tolerance in the slack policy exists to
keep it from reading as RED -- since Steph's 2026-09-25 ruling the screen calls
a fit inside it, either way, GREEN with a ``tight_fit`` flag.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

from shapely.geometry.base import BaseGeometry

from flats.designs.model import Design, Orientation
from flats.fit.angles import angles_for, normalize
from flats.fit.raster import GRID_FT, MAX_CELLS, Grid, cells_for, rasterize


@dataclass(frozen=True, slots=True)
class Fit:
    """The best placement found for one rectangle, and how close it was."""

    fits: bool
    width_ft: float
    depth_ft: float
    #: Deepest run the envelope holds at the winning orientation's *across*
    #: dimension, over every angle tried. Zero when nothing that wide fits.
    best_depth_ft: float
    #: ``best_depth_ft`` less what the winning orientation had to find.
    #: Negative is a shortfall in feet.
    slack_ft: float
    angle_deg: float | None = None
    orientation: Orientation | None = None
    #: What the envelope was searched for, across, in the winning orientation:
    #: the design's own side, or wider where the caller charged the drive lane
    #: beside the building or the parking court behind it (the court sits
    #: behind both, so it is the wider of building-plus-lane and court, never
    #: their sum). ``None`` on a fit built without the search -- the screen
    #: reads that as "the parking's width was never looked for", which is not
    #: the same as a court of no width.
    across_ft: float | None = None
    #: The winning rectangle in the lot's own coordinates, when asked for:
    #: ``across_ft`` wide and the building deep, so the lane or the court
    #: shows in it and the depth the court needs behind the building does not.
    placement: BaseGeometry | None = None
    #: How many stalls the caller found room for, when it looked
    #: (:func:`flats.score.screen.fit_for`): the most of the design's counts,
    #: floor to preferred, whose row the envelope holds beside the building
    #: at the depth the parking needs, in any orientation allowed. 0 when
    #: not even the floor holds. ``None`` on a fit built without the search
    #: -- not looked for, which is not the same as none.
    stalls: int | None = None
    #: The parking the depth was charged for is a column of stalls along a
    #: side alley, backing out into it (:func:`flats.score.paper.side_column`),
    #: not a row behind the building with its own aisle. Set by
    #: :func:`flats.score.screen.fit_for` on the fit it took for that plan:
    #: searched at the building's own side, since the column stands inside it.
    column: bool = False
    #: The parking the fit was searched for is a court BESIDE the building
    #: (:func:`flats.score.paper.side_court`), its row of stalls along the
    #: lot, not a row across it behind the building: ``across_ft`` is the
    #: building's side plus that court's band, and what the court runs past
    #: the rear wall is charged as depth by the screen. Set by
    #: :meth:`Fitter.fit_beside`.
    beside: bool = False

    @property
    def required_ft(self) -> float:
        """The depth that had to be found, for the orientation that won.

        Not always ``depth_ft``. A pod that will not stand broadside may stand
        end-on, and when that flip wins the envelope was searched at the *depth*
        as a width, so the run it had to hold is the design's **width**. The two
        recorded dimensions are the design's, unrotated, so a caller comparing
        ``best_depth_ft`` against ``depth_ft`` measures the wrong pair whenever
        the flip won — reading 50 ft of found depth against a 36 ft dimension as
        a comfortable pass on a lot where a 56 ft run was needed and never
        found. That is a false GREEN, and it was live in
        :func:`flats.score.screen._checks` until 2026-09-08.

        Recovered from ``slack_ft`` rather than re-derived, because ``slack_ft``
        is set from the requirement the search actually used and so cannot drift
        away from it.
        """
        return self.best_depth_ft - self.slack_ft


def res_for(envelope: BaseGeometry, res: float = GRID_FT) -> float:
    """The finest grid, in steps of ``res``, that keeps every rotation of the
    envelope under :data:`~flats.fit.raster.MAX_CELLS`.

    Past the cap a part rasterizes to nothing, and a farm-sized lot would
    read as fitting nothing at all -- a big lot measured as an empty one. A
    coarser grid answers it instead, and a coarser grid only ever shrinks
    the lot (every cell a boundary crosses is dropped), so the answer stays
    a lower bound. Every lot an infill pod is screened on stays at ``res``.
    """
    minx, miny, maxx, maxy = envelope.bounds
    # Any rotation's bounding box fits inside the square on the diagonal.
    diagonal = math.hypot(maxx - minx, maxy - miny) + 2 * res
    if (diagonal / res) ** 2 <= MAX_CELLS:
        return res
    return math.ceil(diagonal / math.sqrt(MAX_CELLS) / res) * res


class Fitter:
    """An envelope rasterized at every candidate angle, queryable by design.

    Construction does the work; queries are cheap. A lot with an empty envelope
    still produces a valid Fitter — it simply fits nothing, which is a result,
    not an error.
    """

    def __init__(
        self,
        envelope: BaseGeometry | None,
        angles: Iterable[float] | None = None,
        *,
        res: float = GRID_FT,
    ) -> None:
        self.angles: tuple[float, ...] = tuple(angles) if angles is not None else angles_for()
        self.grids: list[Grid] = []
        self.res = res
        if envelope is None or envelope.is_empty:
            return
        self.res = res_for(envelope, res)
        # One rotation origin for the whole lot, so placements from different
        # angles are expressed in the same frame.
        c = envelope.centroid
        origin = (c.x, c.y)
        for angle in self.angles:
            self.grids.extend(rasterize(envelope, angle, res=self.res, origin=origin))

    @property
    def empty(self) -> bool:
        return not self.grids

    def _grids(self, angles: Iterable[float] | None) -> list[Grid]:
        """The grids at these angles (folded into [0, 180)); all where None."""
        if angles is None:
            return self.grids
        wanted = [normalize(a) for a in angles]
        return [
            g
            for g in self.grids
            if any(abs(normalize(g.angle_deg) - a) < 1e-6 for a in wanted)
        ]

    def _best(self, w_ft: float, angles: Iterable[float] | None = None) -> tuple[float, Grid | None]:
        """Deepest achievable depth at this width, and the grid that achieved it.

        Every angle is scanned even after one clears the requirement: the margin
        is reported, ranked on, and compared across designs, so the best one is
        worth finding rather than the first one. ``angles`` confines the scan
        to the grids at those angles.
        """
        w_cells = cells_for(w_ft, self.res)
        best_cells, best_grid = 0, None
        for grid in self._grids(angles):
            if grid.cols < w_cells:
                continue
            got = grid.max_depth_cells(w_cells)
            if got > best_cells:
                best_cells, best_grid = got, grid
        return best_cells * self.res, best_grid

    def holds(
        self, across_ft: float, depth_ft: float, *, angles: Iterable[float] | None = None
    ) -> bool:
        """Whether a rectangle this wide and this deep fits at any angle.

        A yes/no, not a margin: one window test per grid and the first hit
        ends it, where :meth:`fit` binary-searches every grid for the deepest
        run. That is what makes it cheap enough to ask several times per lot
        -- the screen asks it once per stall it counts beyond the floor.
        ``angles`` confines it to the grids at those angles.
        """
        w_cells, d_cells = cells_for(across_ft, self.res), cells_for(depth_ft, self.res)
        return any(grid.has_window(d_cells, w_cells) for grid in self._grids(angles))

    def fit(
        self,
        width_ft: float,
        depth_ft: float,
        *,
        allow_flip: bool = True,
        placement: bool = True,
        lane_ft: float = 0.0,
        court_width_ft: float = 0.0,
    ) -> Fit:
        """Best fit for one rectangle across every angle and orientation.

        ``lane_ft`` and ``court_width_ft`` are what the rectangle's parking
        asks across the lot: a drive lane down one flank of the building, and
        a row of stalls behind it. Each orientation is searched at the wider
        of the building plus its lane and the court -- the court sits behind
        both, so the lane is never added to it -- and the depth that has to be
        found stays the building's own. What the court needs *behind* the
        building is depth, charged by the screen against the rear yard, not
        here. Both default to zero, which is the bare rectangle.
        """
        options: list[tuple[Orientation, float, float]] = [
            (Orientation.width_facing, max(width_ft + lane_ft, court_width_ft), depth_ft)
        ]
        if allow_flip and width_ft != depth_ft:
            options.append(
                (Orientation.depth_facing, max(depth_ft + lane_ft, court_width_ft), width_ft)
            )

        best: Fit | None = None
        best_grid: Grid | None = None
        for orientation, across_ft, d_ft in options:
            got_ft, grid = self._best(across_ft)
            slack = got_ft - d_ft
            if best is None or slack > best.slack_ft:
                best = Fit(
                    fits=got_ft >= d_ft,
                    width_ft=width_ft,
                    depth_ft=depth_ft,
                    best_depth_ft=got_ft,
                    slack_ft=slack,
                    angle_deg=grid.angle_deg if grid else None,
                    orientation=orientation,
                    across_ft=across_ft,
                )
                best_grid = grid

        assert best is not None
        if not (placement and best.fits and best_grid is not None):
            return best

        assert best.across_ft is not None
        d_ft = depth_ft if best.orientation is Orientation.width_facing else width_ft
        w_cells, d_cells = cells_for(best.across_ft, self.res), cells_for(d_ft, self.res)
        hit = best_grid.first_window(d_cells, w_cells)
        if hit is None:
            return best
        row, col = hit
        return Fit(
            fits=best.fits,
            width_ft=best.width_ft,
            depth_ft=best.depth_ft,
            best_depth_ft=best.best_depth_ft,
            slack_ft=best.slack_ft,
            angle_deg=best.angle_deg,
            orientation=best.orientation,
            across_ft=best.across_ft,
            placement=best_grid.to_world(row, col, d_cells, w_cells),
        )

    def fit_beside(
        self,
        width_ft: float,
        depth_ft: float,
        *,
        band_ft: float,
        beyond: Callable[[float], float],
        angles: Iterable[float],
        allow_flip: bool = True,
        placement: bool = True,
    ) -> Fit | None:
        """Best fit for the building with a court BESIDE it.

        Each orientation is searched at the building's side plus ``band_ft``
        (the court's gap, aisle and stall), and the depth to find is the
        building's own; ``beyond(deep)`` is what that orientation's court
        asks past the rear wall, which the screen charges as depth, and it
        is what the orientations are ranked on here -- the court's length
        is fixed, so the shallower building can need more depth past its
        wall than the deeper one. An orientation whose ``beyond`` is
        infinite may not have the court at all. ``None`` where none may.

        Only at ``angles``, the street's directions: the court's aisle runs
        in from the street, so the building and its band have to stand side
        by side ALONG the street. Turned a quarter, the same rectangle is a
        building with its court behind it and no lane to reach it -- the
        arrangement the row search already refused. No angle, no court.
        """
        angles = tuple(angles)
        if not angles:
            return None
        options: list[tuple[Orientation, float, float]] = [
            (Orientation.width_facing, width_ft, depth_ft)
        ]
        if allow_flip and width_ft != depth_ft:
            options.append((Orientation.depth_facing, depth_ft, width_ft))
        best: tuple[float, Fit, Grid | None, float] | None = None
        for orientation, side, deep in options:
            extra = beyond(deep)
            if math.isinf(extra):
                continue
            across_ft = side + band_ft
            got_ft, grid = self._best(across_ft, angles)
            room = got_ft - deep - extra
            if best is None or room > best[0]:
                best = (
                    room,
                    Fit(
                        fits=got_ft >= deep + extra,
                        width_ft=width_ft,
                        depth_ft=depth_ft,
                        best_depth_ft=got_ft,
                        slack_ft=got_ft - deep,
                        angle_deg=grid.angle_deg if grid else None,
                        orientation=orientation,
                        across_ft=across_ft,
                        beside=True,
                    ),
                    grid,
                    deep,
                )
        if best is None:
            return None
        _room, fit, grid, deep = best
        if not (placement and fit.fits and grid is not None):
            return fit
        assert fit.across_ft is not None
        w_cells, d_cells = cells_for(fit.across_ft, self.res), cells_for(deep, self.res)
        hit = grid.first_window(d_cells, w_cells)
        if hit is None:
            return fit
        return dataclasses.replace(fit, placement=grid.to_world(hit[0], hit[1], d_cells, w_cells))

    def fit_design(
        self,
        design: Design,
        *,
        axis_required: bool = False,
        placement: bool = True,
        lane_ft: float | None = None,
        court_width_ft: float | None = None,
    ) -> Fit:
        """Fit one catalog design. ``axis_required`` forbids the flipped orientation.

        The design's own lane and court width are charged unless the caller
        passes a city's -- ``flats.score.screen.fit_for`` does, from the
        zone's stall width, driveway minimum and parking cap. A design that
        parks on the street charges nothing across and this is the bare
        footprint.
        """
        return self.fit(
            design.footprint.width_ft,
            design.footprint.depth_ft,
            allow_flip=not axis_required,
            placement=placement,
            lane_ft=design.parking.lane_width_ft if lane_ft is None else lane_ft,
            court_width_ft=design.court_width_ft if court_width_ft is None else court_width_ft,
        )

    def frontier(self, widths_ft: Sequence[float]) -> tuple[float, ...]:
        """Deepest rectangle available at each width.

        Design-independent: it answers any future W×D question about this lot
        without re-rasterizing, which is what lets a new pod design be screened
        against an existing run.
        """
        return tuple(self._best(w)[0] for w in widths_ft)
