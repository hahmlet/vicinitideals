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
route it to REVIEW instead of RED.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from shapely.geometry.base import BaseGeometry

from flats.designs.model import Design, Orientation
from flats.fit.angles import angles_for
from flats.fit.raster import GRID_FT, Grid, cells_for, rasterize


@dataclass(frozen=True, slots=True)
class Fit:
    """The best placement found for one rectangle, and how close it was."""

    fits: bool
    width_ft: float
    depth_ft: float
    #: Deepest rectangle of ``width_ft`` the envelope holds, over every angle
    #: and orientation tried. Zero when nothing of that width fits at all.
    best_depth_ft: float
    #: ``best_depth_ft - depth_ft``. Negative is a shortfall in feet.
    slack_ft: float
    angle_deg: float | None = None
    orientation: Orientation | None = None
    #: The winning rectangle in the lot's own coordinates, when asked for.
    placement: BaseGeometry | None = None


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
        self.res = res
        self.angles: tuple[float, ...] = tuple(angles) if angles is not None else angles_for()
        self.grids: list[Grid] = []
        if envelope is None or envelope.is_empty:
            return
        # One rotation origin for the whole lot, so placements from different
        # angles are expressed in the same frame.
        c = envelope.centroid
        origin = (c.x, c.y)
        for angle in self.angles:
            self.grids.extend(rasterize(envelope, angle, res=res, origin=origin))

    @property
    def empty(self) -> bool:
        return not self.grids

    def _best(self, w_ft: float) -> tuple[float, Grid | None]:
        """Deepest achievable depth at this width, and the grid that achieved it.

        Every angle is scanned even after one clears the requirement: the margin
        is reported, ranked on, and compared across designs, so the best one is
        worth finding rather than the first one.
        """
        w_cells = cells_for(w_ft, self.res)
        best_cells, best_grid = 0, None
        for grid in self.grids:
            if grid.cols < w_cells:
                continue
            got = grid.max_depth_cells(w_cells)
            if got > best_cells:
                best_cells, best_grid = got, grid
        return best_cells * self.res, best_grid

    def fit(
        self,
        width_ft: float,
        depth_ft: float,
        *,
        allow_flip: bool = True,
        placement: bool = True,
    ) -> Fit:
        """Best fit for one rectangle across every angle and orientation."""
        options: list[tuple[Orientation, float, float]] = [
            (Orientation.width_facing, width_ft, depth_ft)
        ]
        if allow_flip and width_ft != depth_ft:
            options.append((Orientation.depth_facing, depth_ft, width_ft))

        best: Fit | None = None
        best_grid: Grid | None = None
        for orientation, w_ft, d_ft in options:
            got_ft, grid = self._best(w_ft)
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
                )
                best_grid = grid

        assert best is not None
        if not (placement and best.fits and best_grid is not None):
            return best

        w_ft, d_ft = (
            (width_ft, depth_ft)
            if best.orientation is Orientation.width_facing
            else (depth_ft, width_ft)
        )
        w_cells, d_cells = cells_for(w_ft, self.res), cells_for(d_ft, self.res)
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
            placement=best_grid.to_world(row, col, d_cells, w_cells),
        )

    def fit_design(self, design: Design, *, axis_required: bool = False, placement: bool = True):
        """Fit one catalog design. ``axis_required`` forbids the flipped orientation."""
        return self.fit(
            design.footprint.width_ft,
            design.footprint.depth_ft,
            allow_flip=not axis_required,
            placement=placement,
        )

    def frontier(self, widths_ft: Sequence[float]) -> tuple[float, ...]:
        """Deepest rectangle available at each width.

        Design-independent: it answers any future W×D question about this lot
        without re-rasterizing, which is what lets a new pod design be screened
        against an existing run.
        """
        return tuple(self._best(w)[0] for w in widths_ft)
