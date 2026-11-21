"""The ground under one pod, as one function ``ground(x, y)`` (FD6 section 5.1).

Frame (FD6 section 3): **x** runs along the 80 ft face from the left end (0)
to the right end (80) as seen from the front; **y** runs from the front wall
(0) to the back wall (25); **z** is ground height in feet on any datum. Only
differences in z matter.

Everything else in :mod:`flats.foundation` calls a :class:`Ground` and nothing
else, so the two sources are interchangeable:

* :class:`SixReadings` -- the lot file's six readings (front and back, at left,
  middle and right): straight between left, middle and right along the front
  and along the back, then straight from front to back. The true high point
  is not known from six readings, so it carries a **lump allowance**: a share
  (``lump_share``, 0.5) of the relief inside the footprint minus the range of
  the six readings, never below zero, added to the high point.
* :class:`CellGrid` -- a ground model's cells in the building's own frame,
  blended straight-line between the four cells round a point. Its lump
  allowance is zero. :func:`grid_centres` / :func:`cell_grid` build one from
  any reader of real ground (FD6 build step 8: ``scripts/flats_foundation.py``
  reads the elevation models through :mod:`flats.foundation.terrain`).
* :class:`Plane` -- an even plane, the section 8 test lots.

Each carries ``cell_m``, the ground model's cell size, through to the result:
lots read from a coarse model (over ``coarse_cell_over_m``) have their relief
understated and are reported apart (FD6 sections 3 and 7).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from flats.foundation.settings import Settings


class Ground:
    """Ground height (ft) at (x, y) in the building frame."""

    #: Added to the sampled high point (ft). Zero unless the source cannot see
    #: the whole footprint.
    lump_ft: float = 0.0
    #: The ground model's cell size (m), or None when not known.
    cell_m: float | None = None
    #: Where the heights came from: "six readings", "cell grid" or "plane".
    source: str = ""

    def __call__(self, x: float, y: float) -> float:  # pragma: no cover - interface
        raise NotImplementedError


@dataclass(frozen=True)
class Plane(Ground):
    """An even plane: the left end higher than the right by ``fall_along_ft``,
    the front higher than the back by ``fall_across_ft``; ``base_ft`` is the
    height at the front-left corner."""

    fall_along_ft: float
    fall_across_ft: float
    length_ft: float
    width_ft: float
    base_ft: float = 0.0
    cell_m: float | None = None
    source: str = "plane"

    def __call__(self, x: float, y: float) -> float:
        z = -self.fall_along_ft * x / self.length_ft - self.fall_across_ft * y / self.width_ft
        return z + self.base_ft if self.base_ft else z


def plane(settings: Settings, fall_along_ft: float, fall_across_ft: float, base_ft: float = 0.0) -> Plane:
    return Plane(fall_along_ft, fall_across_ft, settings.length_ft, settings.width_ft, base_ft)


@dataclass(frozen=True)
class SixReadings(Ground):
    """The six readings as a surface, with the lump allowance."""

    front_left: float
    front_mid: float
    front_right: float
    back_left: float
    back_mid: float
    back_right: float
    length_ft: float
    width_ft: float
    lump_ft: float = 0.0
    cell_m: float | None = None
    source: str = "six readings"

    def _edge(self, x: float, left: float, mid: float, right: float) -> float:
        half = self.length_ft / 2
        if x <= half:
            return left + (mid - left) * x / half
        return mid + (right - mid) * (x - half) / half

    def __call__(self, x: float, y: float) -> float:
        front = self._edge(x, self.front_left, self.front_mid, self.front_right)
        back = self._edge(x, self.back_left, self.back_mid, self.back_right)
        return front + (back - front) * y / self.width_ft

    @property
    def readings(self) -> tuple[float, ...]:
        return (self.front_left, self.front_mid, self.front_right, self.back_left, self.back_mid, self.back_right)


def six_readings(
    settings: Settings,
    front_left: float,
    front_mid: float,
    front_right: float,
    back_left: float,
    back_mid: float,
    back_right: float,
    relief_ft: float | None = None,
    cell_m: float | None = None,
) -> SixReadings:
    """Six readings and the relief inside the footprint -> a ground with its lump allowance."""
    z = (front_left, front_mid, front_right, back_left, back_mid, back_right)
    lump = 0.0
    if relief_ft is not None:
        lump = max(0.0, relief_ft - (max(z) - min(z))) * settings.lump_share
    return SixReadings(*z, settings.length_ft, settings.width_ft, lump_ft=lump, cell_m=cell_m)


@dataclass(frozen=True)
class CellGrid(Ground):
    """A ground model's cells in the building frame, blended bilinearly.

    ``z[j][i]`` is the height of the cell whose centre is at
    ``(x0_ft + (i + 0.5) * cell_ft, y0_ft + (j + 0.5) * cell_ft)``: row j runs
    along x, rows step from the front (y0) to the back. ``x0_ft, y0_ft`` is the
    grid's outer corner (negative when the grid takes in a margin round the
    footprint, as FD6 section 3 prefers). Beyond the outermost cell centres the
    edge cells' heights are held. The lump allowance is zero: the grid sees the
    whole footprint.
    """

    z: tuple[tuple[float, ...], ...]
    x0_ft: float
    y0_ft: float
    cell_ft: float
    cell_m: float | None = None
    source: str = "cell grid"

    def __post_init__(self) -> None:
        if not self.z or not self.z[0]:
            raise ValueError("cell grid: no cells")
        if any(len(row) != len(self.z[0]) for row in self.z):
            raise ValueError("cell grid: rows differ in length")
        if self.cell_ft <= 0:
            raise ValueError("cell grid: cell size must be positive")

    @classmethod
    def of(
        cls,
        z: Sequence[Sequence[float]],
        x0_ft: float,
        y0_ft: float,
        cell_ft: float,
        cell_m: float | None = None,
        source: str = "cell grid",
    ) -> CellGrid:
        return cls(tuple(tuple(float(v) for v in row) for row in z), x0_ft, y0_ft, cell_ft, cell_m, source)

    @staticmethod
    def _axis(u: float, n: int) -> tuple[int, int, float]:
        """Cell-centre index below u, the one above, and the blend between them."""
        if n == 1 or u <= 0.0:
            return 0, 0, 0.0
        if u >= n - 1:
            return n - 1, n - 1, 0.0
        i = math.floor(u)
        return i, i + 1, u - i

    def __call__(self, x: float, y: float) -> float:
        rows, cols = len(self.z), len(self.z[0])
        i0, i1, fx = self._axis((x - self.x0_ft) / self.cell_ft - 0.5, cols)
        j0, j1, fy = self._axis((y - self.y0_ft) / self.cell_ft - 0.5, rows)
        front = self.z[j0][i0] + (self.z[j0][i1] - self.z[j0][i0]) * fx
        back = self.z[j1][i0] + (self.z[j1][i1] - self.z[j1][i0]) * fx
        return front + (back - front) * fy


def grid_centres(settings: Settings) -> tuple[float, float, list[float], list[float]]:
    """The cell centres of a ground grid in the building frame: the footprint plus
    ``grid_margin_ft`` all round, every ``grid_step_ft``. Returns the grid's outer
    corner (x0, y0) and the centres along x and along y."""
    m, step = settings.grid_margin_ft, settings.grid_step_ft
    nx = max(1, round((settings.length_ft + 2 * m) / step))
    ny = max(1, round((settings.width_ft + 2 * m) / step))
    x0, y0 = -m, -m
    return x0, y0, [x0 + (i + 0.5) * step for i in range(nx)], [y0 + (j + 0.5) * step for j in range(ny)]


def cell_grid(z_rows: Sequence[Sequence[float]], settings: Settings, cell_m: float | None, source: str) -> CellGrid:
    """A :class:`CellGrid` from heights at :func:`grid_centres` (rows front to
    back, each left to right). Refuses a blank (NaN) cell: a grid with a hole
    is a lot error, not a guess."""
    x0, y0, xs, ys = grid_centres(settings)
    if len(z_rows) != len(ys) or any(len(r) != len(xs) for r in z_rows):
        raise ValueError("cell grid: heights do not match the grid centres")
    if any(math.isnan(float(v)) for r in z_rows for v in r):
        raise ValueError("cell grid: blank cells")
    return CellGrid.of(z_rows, x0, y0, settings.grid_step_ft, cell_m, source)


def high_low(ground: Ground, settings: Settings) -> tuple[float, float]:
    """Highest and lowest ground anywhere under the footprint (the whole
    footprint is sampled, not only the wall lines). The lump allowance is not
    included here."""
    nx = max(1, round(settings.length_ft / settings.high_point_along_ft))
    ny = max(1, round(settings.width_ft / settings.high_point_across_ft))
    xs = [i * settings.length_ft / nx for i in range(nx + 1)]
    ys = [j * settings.width_ft / ny for j in range(ny + 1)]
    zs = [ground(x, y) for x in xs for y in ys]
    return max(zs), min(zs)
