"""Lot width, measured the way the code that asks for it defines it.

s4 measures *frontage*: the run of boundary that touches a street. Two of the
cities in this screen state a minimum lot **width** instead, and both of them
define it as a line drawn across the middle of the lot. On a rectangle those
are the same line. On a cul-de-sac wedge, a flag lot, or anything that tapers
toward the road they are not, and comparing one against the other threw 988
lots out of the funnel for failing a test their city never applied to that edge.

The interim answer was to stop deciding: where the number is a width, a lot
that falls short goes to review rather than red. That could not turn anything
green -- it only stopped the screen from asserting something it had not
measured. This module is the other half, and it takes the measurement.

Two cities, two definitions, and they are not the same measurement:

``side_midpoints``
    Oregon City OCMC 17.04.700 -- "the perpendicular distance measured between
    the midpoints of the two principal opposite side lot lines and generally at
    approximately right angles to the lot depth". So: find the two principal
    side lines, join their midpoints, measure that.

``center_parallel``
    Tualatin TDC 31.060 -- "the horizontal distance between the side lot lines,
    ordinarily measured parallel to the front lot line, at the center of the
    lot". So: a chord through the middle of the lot, in the direction of the
    street, clipped to the parcel.

    Tualatin's definition has a second half -- "or, in the case of a corner
    lot, the horizontal distance between the front lot line and a side lot
    line" -- which is a different measurement on a different pair of lines.
    Corner lots are refused here rather than measured wrong.

Every function returns ``None`` for "I could not take this measurement", and a
``None`` is a lot held for review, exactly as before. That is the shape of the
whole module: it converts *unmeasured* into *measured* where it honestly can,
and leaves the rest where it was. A width this module invents is worse than a
width it declines, because a wrong width can turn a lot green.
"""

from __future__ import annotations

import math

#: Two side lines are "opposite" if the segment joining their midpoints stays
#: inside the parcel. A wedge's sides converge and are nowhere near parallel,
#: which is the whole reason this measurement exists, so parallelism cannot be
#: the test. Containment can: on an L-shaped lot the join between the midpoints
#: of two sides that do not face each other leaves the polygon.
_INSIDE_TOL_FT = 0.5

#: A side line shorter than this against its opposite number is a chamfered
#: corner or a jog, not a principal side lot line.
_PRINCIPAL_RATIO = 0.40

#: How far the chord is thrown before being clipped to the parcel.
_CHORD_REACH = 4.0


def _length(e) -> float:
    return math.hypot(e[2] - e[0], e[3] - e[1])


def _midpoint(e) -> tuple[float, float]:
    return ((e[0] + e[2]) / 2.0, (e[1] + e[3]) / 2.0)


def side_midpoints_width_ft(geom, edges) -> float | None:
    """Oregon City: the distance between the midpoints of the two principal
    opposite side lot lines.

    "Principal" is read as the longest, and "opposite" as facing each other
    across the parcel rather than as parallel -- the lots this measurement is
    for are the ones whose sides converge. The pair is the longest two side
    lines whose join stays inside the lot; a lot offering no such pair is not
    measured.
    """
    import shapely
    from shapely.geometry import LineString

    if geom is None or geom.is_empty:
        return None
    sides = sorted(
        (e for e in edges if len(e) > 4 and e[4] == "S"), key=_length, reverse=True
    )
    if len(sides) < 2:
        return None
    inside = geom.buffer(_INSIDE_TOL_FT)
    longest = _length(sides[0])
    best = None
    # Only the principal sides are candidates, and among those the longest pair
    # that actually faces each other. Pairs are few -- a lot with more than a
    # handful of side lines is tier C and never reaches here.
    principal = [e for e in sides[:6] if _length(e) >= _PRINCIPAL_RATIO * longest]
    for i in range(len(principal)):
        for j in range(i + 1, len(principal)):
            a, b = _midpoint(principal[i]), _midpoint(principal[j])
            join = LineString([a, b])
            if join.length <= 0 or not shapely.covers(inside, join):
                continue
            weight = _length(principal[i]) + _length(principal[j])
            if best is None or weight > best[0]:
                best = (weight, join.length)
    return None if best is None else round(best[1], 2)


def center_parallel_width_ft(geom, front_bearings) -> float | None:
    """Tualatin: the distance between the side lot lines, measured parallel to
    the front lot line, at the center of the lot.

    The chord is thrown through the centre of the parcel along the street's
    bearing and clipped to it, and what is returned is the piece of it the
    centre stands on -- not the total clipped length, because on a lot that
    wraps around a neighbour the chord can re-enter further along and that
    second piece is somebody else's width.
    """
    import shapely
    from shapely.geometry import LineString, Point

    if geom is None or geom.is_empty or not front_bearings:
        return None
    # A corner lot measures something else entirely under this definition.
    if len(front_bearings) > 1:
        return None
    centre = geom.centroid
    if not geom.covers(centre):
        centre = geom.representative_point()
    x0, y0, x1, y1 = geom.bounds
    reach = _CHORD_REACH * max(math.hypot(x1 - x0, y1 - y0), 1.0)
    theta = math.radians(float(front_bearings[0]))
    dx, dy = math.cos(theta) * reach, math.sin(theta) * reach
    chord = LineString(
        [(centre.x - dx, centre.y - dy), (centre.x + dx, centre.y + dy)]
    )
    clipped = shapely.intersection(geom, chord)
    if clipped.is_empty:
        return None
    parts = [p for p in shapely.get_parts(clipped) if p.length > 0]
    if not parts:
        return None
    here = Point(centre.x, centre.y)
    on = [p for p in parts if p.distance(here) <= _INSIDE_TOL_FT]
    if not on:
        return None
    return round(max(p.length for p in on), 2)


#: A width is only taken on a lot whose shape the screen trusts. Tier C is the
#: irregular/flag pile, where "the two principal opposite side lot lines" is a
#: phrase without a referent, and tier D has no street to measure from.
MEASURABLE_TIERS = frozenset({"A", "B"})


def width_ft(measure: str | None, geom, edges, front_bearings, tier: str):
    """The lot's width under one city's definition, or ``None`` if unmeasured."""
    if not measure or tier not in MEASURABLE_TIERS:
        return None
    if measure == "side_midpoints":
        return side_midpoints_width_ft(geom, edges)
    if measure == "center_parallel":
        return center_parallel_width_ft(geom, front_bearings)
    raise ValueError(f"unknown lot width measure: {measure!r}")
