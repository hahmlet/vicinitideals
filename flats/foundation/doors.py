"""Which long face of the drawn building carries the front doors (FD8, Steph 2026-11-20).

The front and back doors stand in different places along the building (FD8 2a,
``door_x_front_ft`` / ``door_x_back_ft``), so which face takes the front doors
decides the step count at each one. rulings.yaml
``2026-11-20-front-doors-face-parking``:

1. Where the zone requires the main entrance to face the street
   (``entrance_faces_street`` ``required`` or ``required_named``), the front
   doors face the street as placed: the frame's front, the long side nearer
   the street lot lines (:func:`flats.foundation.frame.frame`).
2. Elsewhere they go on the long face toward the drawn parking (the court and
   its stalls, else the lane).
3. With no parking drawn, on the face with more open lot in front of it: the
   lot's area beyond each long face, across the building's length.

A tie at 2 or 3 keeps the street side. Pure geometry: no number is set here.

Never a colour by itself; :mod:`flats.ingest.foundation_cap` reads the result.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from flats.foundation.frame import Frame

STREET = "street"
AWAY = "away"

#: Why the front doors are on the face they are on (``Measured.door_face_rule``).
REQUIRED = "entrance_faces_street"
PARKING = "toward_parking"
LANE = "toward_lane"
OPEN_LOT = "more_open_lot"
STREET_DEFAULT = "street_side"
RULES = (REQUIRED, PARKING, LANE, OPEN_LOT, STREET_DEFAULT)

WORDS = {
    REQUIRED: "the front doors face the street: the zone requires the main entrance to",
    PARKING: "the front doors face the drawn parking court (Steph 2026-11-20)",
    LANE: "the front doors face the drawn drive lane (Steph 2026-11-20)",
    OPEN_LOT: "no parking drawn: the front doors face the side with more open lot (Steph 2026-11-20)",
    STREET_DEFAULT: "the front doors face the street side (nothing else chose a face)",
}

#: Two faces this close (ft, or sq ft for area) are a tie: the street side keeps them.
_TIE = 0.5


def _poly(ring: Sequence[Sequence[float]] | None) -> Any:
    import shapely

    if not ring or len(ring) < 3:
        return None
    try:
        g = shapely.Polygon([(float(p[0]), float(p[1])) for p in ring])
    except (TypeError, ValueError):
        return None
    return g if g.is_valid and not g.is_empty else g.buffer(0)


def _mid(a: tuple[float, float], b: tuple[float, float]) -> Any:
    import shapely

    return shapely.Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _toward(fr: Frame, target: Any) -> bool | None:
    """True where the back face is nearer ``target`` (turn the frame), False
    where the front is, None on a tie."""
    d_front = _mid(fr.fl, fr.fr).distance(target)
    d_back = _mid(fr.bl, fr.br).distance(target)
    if abs(d_front - d_back) <= _TIE:
        return None
    return d_back < d_front


def _beyond(a: tuple[float, float], b: tuple[float, float], away: tuple[float, float], lot: Any) -> float:
    """The lot's area beyond the face a-b (on the side away from ``away``),
    across the face's own length."""
    import math

    import shapely

    ex, ey = b[0] - a[0], b[1] - a[1]
    n = math.hypot(ex, ey) or 1.0
    nx, ny = -ey / n, ex / n
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    if (away[0] - mx) * nx + (away[1] - my) * ny > 0:
        nx, ny = -nx, -ny
    minx, miny, maxx, maxy = lot.bounds
    far = 2.0 * (math.hypot(maxx - minx, maxy - miny) + 1.0)
    strip = shapely.Polygon([a, b, (b[0] + nx * far, b[1] + ny * far), (a[0] + nx * far, a[1] + ny * far)])
    return float(lot.intersection(strip).area)


def choose(
    fr: Frame,
    *,
    required: bool,
    court: Sequence[Sequence[float]] | None = None,
    lane: Sequence[Sequence[float]] | None = None,
    lot: Any = None,
) -> tuple[bool, str]:
    """``(turned, rule)``: whether the front doors go on the frame's back face
    (so :meth:`Frame.turned` is the frame to measure in), and why."""
    if required:
        return False, REQUIRED
    for ring, rule in ((court, PARKING), (lane, LANE)):
        target = _poly(ring)
        if target is None:
            continue
        got = _toward(fr, target)
        if got is not None:
            return got, rule
    if lot is not None and not lot.is_empty:
        front = _beyond(fr.fl, fr.fr, _mid(fr.bl, fr.br).coords[0], lot)
        back = _beyond(fr.bl, fr.br, _mid(fr.fl, fr.fr).coords[0], lot)
        if abs(front - back) > _TIE:
            return back > front, OPEN_LOT
    return False, STREET_DEFAULT


def entrance_required(rules: Any, entrance_side_fit: Any = None) -> bool:
    """The zone requires the main entrance to face the street and the drawing
    keeps it there (a side-door fit, FOLLOWUPS 177, stands its doors to a side
    yard instead)."""
    try:
        got = rules.get("entrance_faces_street")
    except AttributeError:
        return False
    return got in ("required", "required_named") and not entrance_side_fit


__all__ = ["AWAY", "RULES", "STREET", "WORDS", "choose", "entrance_required"]
