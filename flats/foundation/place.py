"""MEASURE a drawn building where it stands: frame, door face, ground grid, record.

One path for both callers -- the foundation measure run
(``scripts/flats_foundation.py measure-run``) and the screen's six-step cap
(:mod:`flats.ingest.foundation_cap`) -- so the record the lot page shows and the
colour the screen gives are read from the same ground in the same frame.

* :func:`flats.foundation.frame.frame` names the long side nearer the street
  the front; :func:`flats.foundation.doors.choose` says which face takes the
  front doors (Steph 2026-11-20) and the frame is turned to put that face at
  y = 0, where :func:`flats.foundation.measure.door_points` stands the front
  doors.
* The grid is the 1 m model's, else (blank cells, or no 1 m tile) the 10 m
  model's (:class:`flats.foundation.terrain.Dem`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from flats.foundation import doors as door_face
from flats.foundation import ground as grounds
from flats.foundation import measure
from flats.foundation.frame import Frame, frame
from flats.foundation.measure import Measured
from flats.foundation.settings import Settings

Seg = tuple[float, float, float, float]


@dataclass(frozen=True)
class Placed:
    """One drawn building's measure, or why there is none."""

    #: The frame measured in: its front face carries the front doors.
    frame: Frame
    #: The frame as :func:`frame` names it (front = the street side), for the
    #: street-face turn FD5 reads.
    street_frame: Frame
    turned: bool
    rule: str
    measured: Measured | None
    #: Why nothing was measured ("no elevation model covers the whole grid").
    error: str | None = None
    #: The ground measured on (``ground(x, y)`` ft in ``frame``'s model
    #: coordinates), for the main entrance's distance from grade
    #: (:mod:`flats.ingest.entrance_grade`). None where nothing was measured.
    ground: Any = None


def grid_xy(s: Settings) -> tuple[Any, Any]:
    import numpy as np

    _x0, _y0, xs, ys = grounds.grid_centres(s)
    return np.meshgrid(np.asarray(xs, dtype=float), np.asarray(ys, dtype=float))


def place(
    ring: Sequence[Sequence[float]],
    streets: Sequence[Seg],
    dem: Any,
    s: Settings,
    *,
    required: bool,
    court: Sequence[Sequence[float]] | None = None,
    lane: Sequence[Sequence[float]] | None = None,
    lot: Any = None,
    tlid: str | None = None,
    county: str | None = None,
    grid: tuple[Any, Any] | None = None,
) -> Placed:
    """MEASURE the building drawn as ``ring`` (EPSG:2913 ft)."""
    import numpy as np

    street = frame(ring, streets)
    turned, rule = door_face.choose(street, required=required, court=court, lane=lane, lot=lot)
    fr = street.turned() if turned else street
    gx, gy = grid if grid is not None else grid_xy(s)
    pts = fr.world(gx.ravel(), gy.ravel(), s.length_ft, s.width_ft, s.box_ft)
    z = None
    src_name = cell = None
    for coarse in (False, True):
        z_of, src_name, cell = dem.z_reader(ring, coarse=coarse)
        if z_of is None:
            continue
        z = np.asarray(z_of(pts), dtype=float).reshape(gy.shape)
        if np.isfinite(z).all():
            break
        z = None
    if z is None:
        return Placed(fr, street, turned, rule, None, "LookupError: no elevation model covers the whole grid")
    g = grounds.cell_grid(z.tolist(), s, cell, f"{src_name} grid")
    m = measure.measure(g, s, tlid=tlid, county=county,
                        inputs={"door_face": door_face.AWAY if turned else door_face.STREET, "door_face_rule": rule})
    return Placed(fr, street, turned, rule, m, ground=g)


__all__ = ["Placed", "grid_xy", "place"]
