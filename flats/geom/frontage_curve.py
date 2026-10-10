"""The shape of a lot's street frontage, measured the way a corner-lot clause writes it.

A city's corner-lot definition may turn a CURVING street into two: Beaverton's
"straight lines drawn from the foremost points of the side lot lines to the
foremost point of the lot meet at an interior angle of less than 135 degrees"
(a chord construction), Gresham's "inside curve of a street with a delta
angle ... of 60 degrees or more" (the whole curve's deflection), Portland's
"a street that curves with angles that are 120 degrees or less" (the angle
between the street's ends). Each is ONE angle across the curve. Reading a
curve vertex by vertex (:func:`flats.rules.definitions.interior_angle_deg`)
misses a gentle multi-bend curve whose every bend is under the threshold and
whose total is well over it (FOLLOWUPS 63, 2026-10-09: 24 of Beaverton's 29
lots lost to this).

Everything here reads ``edges_json`` rings (``[x1, y1, x2, y2, class]`` in ring
order, consecutive edges sharing a vertex). Pure geometry: no layers, no rules.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Sequence

from flats.geom.edges import bearing_deg, bearing_delta
from flats.geom.one_street import SLIVER_FT, SLIVER_TURN_DEG, STREET_CLASS

#: A farthest vertex closer to the chord than this is not a bulge, it is noise.
APEX_MIN_FT = 0.5

Edge = Sequence[Any]


@dataclass(frozen=True, slots=True)
class Curve:
    """One unbroken street frontage, measured.

    ``tangent_deg``: 180 minus the frontage's total deflection -- the angle
    between its first and last lot line. ``apex_deg``: the angle at the
    foremost point between lines to the frontage's two ends (None when the
    frontage does not bulge toward the street). ``inside``: whether the
    frontage turns toward the lot, i.e. the lot sits on the inside curve.
    """

    tangent_deg: float
    apex_deg: float | None
    inside: bool


def _length(e: Edge) -> float:
    return math.hypot(float(e[2]) - float(e[0]), float(e[3]) - float(e[1]))


def _ring(edges_json: str | None) -> list[Edge]:
    return [e for e in json.loads(edges_json or "[]") if len(e) >= 5]


def _runs(ring: Sequence[Edge]) -> list[list[Edge]]:
    """Street edges split into unbroken stretches of the ring.

    A street edge under :data:`SLIVER_FT` that turns :data:`SLIVER_TURN_DEG`
    or more off the longest street edge is where the front ends, not a break
    and not frontage (:func:`flats.geom.one_street.street_midpoints`); it is
    set aside -- but only inside a stretch that also holds a real front edge.
    A short piece with no street edge joining it to the front is a second
    frontage, however short. Any other edge that is not a street ends the
    stretch.
    """
    streets = [e for e in ring if e[4] == STREET_CLASS]
    if not streets:
        return []
    main = max(streets, key=_length)
    main_bearing = bearing_deg(*(float(v) for v in main[:4]))

    def is_sliver(e: Edge) -> bool:
        return (
            e[4] == STREET_CLASS
            and _length(e) < SLIVER_FT
            and bearing_delta(bearing_deg(*(float(v) for v in e[:4])), main_bearing) >= SLIVER_TURN_DEG
        )

    n_ring = len(ring)
    on_street = [e[4] == STREET_CLASS for e in ring]
    stretch = [-1] * n_ring
    sid = 0
    first = next((i for i in range(n_ring) if on_street[i] and not on_street[i - 1]), 0)
    for step in range(n_ring):
        i = (first + step) % n_ring
        if not on_street[i]:
            continue
        if step and on_street[i - 1]:
            stretch[i] = stretch[i - 1]
        else:
            stretch[i] = sid
            sid += 1
    has_front = {stretch[i] for i in range(n_ring) if on_street[i] and not is_sliver(ring[i])}
    kept: list[Edge] = [
        e for i, e in enumerate(ring) if not (on_street[i] and stretch[i] in has_front and is_sliver(e))
    ]
    flags = [e[4] == STREET_CLASS for e in kept]
    n = len(kept)
    if all(flags):
        return [list(kept)]
    start = next(i for i in range(n) if flags[i] and not flags[i - 1])
    runs: list[list[Edge]] = []
    for step in range(n):
        i = (start + step) % n
        if not flags[i]:
            continue
        if runs and flags[i - 1]:
            runs[-1].append(kept[i])
        else:
            runs.append([kept[i]])
    return runs


def is_unbroken(edges_json: str | None) -> bool:
    """True when the lot's street edges are ONE unbroken stretch of the ring.

    The same street name on two stretches parted by a rear or side line is
    two frontages, not a bend (FOLLOWUPS 63: 1S224CA18200's 231 ft and 132 ft
    fronts either side of a 387 ft rear line).
    """
    return len(_runs(_ring(edges_json))) == 1


def _signed_area(ring: Sequence[Edge]) -> float:
    return 0.5 * sum(float(e[0]) * float(e[3]) - float(e[2]) * float(e[1]) for e in ring)


def measure(edges_json: str | None) -> Curve | None:
    """The lot's one street frontage as a curve, or None where it is not one
    unbroken stretch of at least two lot lines."""
    ring = _ring(edges_json)
    runs = _runs(ring)
    if len(runs) != 1 or len(runs[0]) < 2:
        return None
    run = runs[0]
    area = _signed_area(ring)
    if area == 0.0:
        return None
    sign = 1.0 if area > 0 else -1.0
    pts = [(float(run[0][0]), float(run[0][1]))] + [(float(e[2]), float(e[3])) for e in run]
    total = 0.0
    for a, b, c in zip(pts, pts[1:], pts[2:]):
        ux, uy, vx, vy = b[0] - a[0], b[1] - a[1], c[0] - b[0], c[1] - b[1]
        total += math.degrees(math.atan2(ux * vy - uy * vx, ux * vx + uy * vy))
    tangent = max(0.0, 180.0 - abs(total))
    inside = total * sign > 0.0
    s, e = pts[0], pts[-1]
    chord = math.hypot(e[0] - s[0], e[1] - s[1])
    apex_deg: float | None = None
    if inside and chord > 0.0:
        # Distance of each interior vertex beyond the chord, on the street side
        # (the side away from the lot): the foremost point is the farthest.
        best, far = 0.0, None
        for p in pts[1:-1]:
            d = -sign * ((e[0] - s[0]) * (p[1] - s[1]) - (e[1] - s[1]) * (p[0] - s[0])) / chord
            if d > best:
                best, far = d, p
        if far is not None and best >= APEX_MIN_FT:
            ax, ay, bx, by = s[0] - far[0], s[1] - far[1], e[0] - far[0], e[1] - far[1]
            cos = (ax * bx + ay * by) / (math.hypot(ax, ay) * math.hypot(bx, by))
            apex_deg = math.degrees(math.acos(max(-1.0, min(1.0, cos))))
    return Curve(tangent_deg=tangent, apex_deg=apex_deg, inside=inside)


def makes_corner(
    curve_by: str,
    ceiling_deg: float,
    *,
    inclusive: bool,
    inside_only: bool,
    edges_json: str | None,
) -> bool:
    """Whether the frontage's curve is two streets by the clause this code
    wrote: ``apex`` (a chord construction) or ``tangent`` (the angle between
    the frontage's ends). Anything it cannot measure is not a corner here --
    the caller keeps the corner reading on a doubt before it gets this far."""
    c = measure(edges_json)
    if c is None or (inside_only and not c.inside):
        return False
    angle = c.apex_deg if curve_by == "apex" else c.tangent_deg
    if angle is None:
        return False
    return angle <= ceiling_deg if inclusive else angle < ceiling_deg


__all__ = ["APEX_MIN_FT", "Curve", "is_unbroken", "makes_corner", "measure"]
