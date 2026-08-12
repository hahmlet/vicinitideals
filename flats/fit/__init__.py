"""Geometric fitment: can the pod's rectangle sit inside the buildable area.

:mod:`angles` decides which rotations to try, :mod:`raster` turns an envelope
into integral images, :mod:`rectangle` answers fit-and-by-how-much for a design.
Pure geometry — no zoning judgement, no verdict. Coverage caps, frontage
minimums and orientation policy are applied downstream against these numbers.
"""

from flats.fit.angles import DEFAULT_STEP_DEG, SWEEP_SPAN_DEG, angles_for, normalize, sweep
from flats.fit.raster import GRID_FT, MAX_CELLS, MIN_PART_SQFT, Grid, cells_for, rasterize
from flats.fit.rectangle import Fit, Fitter

__all__ = [
    "DEFAULT_STEP_DEG",
    "GRID_FT",
    "MAX_CELLS",
    "MIN_PART_SQFT",
    "SWEEP_SPAN_DEG",
    "Fit",
    "Fitter",
    "Grid",
    "angles_for",
    "cells_for",
    "normalize",
    "rasterize",
    "sweep",
]
