"""Clear-vision areas at street corners and at the drive (FOLLOWUPS 161).

A city keeps a triangle at a street corner clear of anything tall, and in
most of the region that bars a building (the jurisdiction YAML's
``clear_vision`` block, :class:`flats.rules.model.SightRule`, says which).
This module draws the areas; the bridge carves the corner's out of the
buildable envelope before the fit (:func:`flats.ingest.quadfit.screen_lot`)
and checks the drive's against the drawn building afterwards.

Two areas are drawn per corner (:class:`SightAreas`):

* ``high`` -- the largest the rule may be: the street lines AS the lot
  lines (the curb at the lot line, rulings.yaml
  2026-11-09-curb-position-middle-way), the largest figure the rule offers,
  both readings of an asymmetric or sight-distance rule. A fit outside it is
  clear.
* ``low`` -- what the rule surely keeps: the smallest figure, the reading
  every orientation shares, and, where the code measures from a curb or a
  pavement edge the maps do not hold, the curb a generous
  :data:`GENEROUS_CURB_OFFSET_FT` out from the lot line. A fit inside it
  does not stand: RED is earned only there. Unsettled rules
  (rulings.yaml 2026-11-09-sight-triangle-corner-check) keep nothing for
  sure: ``low`` is empty and the lot is never RED on it.

A fit in between is YELLOW with the area's reason.

Coordinates are the lot polygon's, in feet. The corners are where two of
the lot's streets (:func:`flats.fit.frontage.street_chains`, which merges a
rounded corner's chords into the streets they join) meet: the straight
lines near the corner are extended to their meeting point, which on a
rounded corner lies off the lot, as every code here measures it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from flats.fit.frontage import street_chains
from flats.geom.edges import Edge, LotEdges

#: The curb's distance out from the lot line for the RED test where a code
#: measures from the curb or pavement edge (rulings.yaml
#: 2026-11-09-curb-position-middle-way: "red only if blocked even at a
#: generous offset"). A judgement, not a code figure: one figure for every
#: street, since no lot line here carries its street's type. Portland's
#: PBOT curb layer (data/flats/sources/2026-11-09-curb, 62.7% of GREENs)
#: puts the ordinary local street's curb 10-12 ft off the line (a 5-6 ft
#: sidewalk and a 4-6 ft planting strip); 15 ft is past that on every
#: local street and short of an arterial's, so a lot RED at 15 ft is
#: blocked wherever an ordinary curb stands.
GENEROUS_CURB_OFFSET_FT = 15.0
#: Where a sight line runs in the street: half a travel lane (an 11-12 ft
#: lane) out from the curb, the driver's eye and the oncoming car both.
WEDGE_LANE_HALF_FT = 6.0
#: The two street lines meet at a corner only between these angles: the
#: corner test's own floor (:data:`flats.geom.corner.CORNER_MIN_DEG`, 45)
#: less a margin for a skewed intersection.
CORNER_TURN_MIN_DEG = 40.0
#: The straight line near a corner: the first edge from the corner at least
#: this long (a rounded corner's chords are shorter), else the longest.
STRAIGHT_MIN_FT = 15.0
#: Two chain ends this close are one corner.
_MEET_TOL_FT = 1.0
#: Less than this of a building inside an area is a drawing's rounding.
OVERLAP_SQFT = 1.0


@dataclass(frozen=True)
class StreetLine:
    """One street's lot line near a corner: a point on it, the unit
    direction along it away from the corner, and the unit normal into the
    lot."""

    px: float
    py: float
    ux: float
    uy: float
    nx: float
    ny: float


@dataclass(frozen=True)
class Corner:
    a: StreetLine
    b: StreetLine


@dataclass(frozen=True)
class SightAreas:
    """The corner clear-vision areas on one lot (module docstring)."""

    low: BaseGeometry
    high: BaseGeometry
    #: :data:`flats.score.screen.SIGHT_CORNER_CURB` or ``..._UNSETTLED``:
    #: why a fit between the two is held YELLOW.
    reason: str
    cite: str

    @property
    def doubt(self) -> BaseGeometry:
        return self.high.difference(self.low)


def _inward(lot: BaseGeometry, e: Edge) -> tuple[float, float]:
    dx, dy = e.x2 - e.x1, e.y2 - e.y1
    n = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / n, dx / n
    mx, my = (e.x1 + e.x2) / 2, (e.y1 + e.y2) / 2
    probe = Point(mx + nx * 0.5, my + ny * 0.5)
    return (nx, ny) if lot.contains(probe) or lot.distance(probe) < 1e-6 else (-nx, -ny)


def _line_at(lot: BaseGeometry, chain: Sequence[Edge], corner_end: str) -> StreetLine:
    """The straight street line near the chain's ``corner_end`` (``start``
    or ``end`` of the chain), pointing away from the corner."""
    order = list(chain) if corner_end == "start" else list(reversed(chain))
    pick = next((e for e in order if e.length_ft >= STRAIGHT_MIN_FT), None)
    if pick is None:
        pick = max(order, key=lambda e: e.length_ft)
    # Away from the corner: in ring order when the corner is the chain's start.
    if corner_end == "start":
        x0, y0, x1, y1 = pick.x1, pick.y1, pick.x2, pick.y2
    else:
        x0, y0, x1, y1 = pick.x2, pick.y2, pick.x1, pick.y1
    n = math.hypot(x1 - x0, y1 - y0) or 1.0
    nx, ny = _inward(lot, pick)
    return StreetLine(x0, y0, (x1 - x0) / n, (y1 - y0) / n, nx, ny)


def _turn_deg(a: StreetLine, b: StreetLine) -> float:
    dot = max(-1.0, min(1.0, a.ux * b.ux + a.uy * b.uy))
    return math.degrees(math.acos(dot))


def corners(lot: BaseGeometry, edges: LotEdges | None) -> tuple[Corner, ...]:
    """Where two of the lot's streets meet (module docstring)."""
    if edges is None or lot is None or lot.is_empty:
        return ()
    chains = street_chains(edges)
    if len(chains) < 2:
        return ()
    out: list[Corner] = []
    for i, ci in enumerate(chains):
        for cj in chains[i + 1 :]:
            for end_i, end_j, (xi, yi), (xj, yj) in (
                ("end", "start", (ci[-1].x2, ci[-1].y2), (cj[0].x1, cj[0].y1)),
                ("start", "end", (ci[0].x1, ci[0].y1), (cj[-1].x2, cj[-1].y2)),
            ):
                if math.hypot(xi - xj, yi - yj) > _MEET_TOL_FT:
                    continue
                a, b = _line_at(lot, ci, end_i), _line_at(lot, cj, end_j)
                # Two lines leaving a corner make an angle near 90 degrees;
                # the same street bending is near 180.
                turn = _turn_deg(a, b)
                if CORNER_TURN_MIN_DEG <= turn <= 180.0 - CORNER_TURN_MIN_DEG:
                    out.append(Corner(a, b))
    return tuple(out)


def _shift(s: StreetLine, d: float) -> tuple[float, float]:
    """A point on the street line moved ``d`` ft out into the street."""
    return s.px - s.nx * d, s.py - s.ny * d


def apex(c: Corner, d: float = 0.0) -> tuple[float, float]:
    """Where the two street lines, each moved ``d`` ft into the street,
    meet (extended, on a rounded corner)."""
    (ax, ay), (bx, by) = _shift(c.a, d), _shift(c.b, d)
    den = c.a.ux * c.b.uy - c.a.uy * c.b.ux
    if abs(den) < 1e-9:
        return ax, ay
    t = ((bx - ax) * c.b.uy - (by - ay) * c.b.ux) / den
    return ax + c.a.ux * t, ay + c.a.uy * t


def triangle(c: Corner, leg_a: float, leg_b: float, d: float = 0.0) -> Polygon:
    """The triangle with legs ``leg_a`` along street a and ``leg_b`` along
    street b from the apex of the lines ``d`` ft out (unclipped)."""
    x, y = apex(c, d)
    return Polygon([
        (x, y),
        (x + c.a.ux * leg_a, y + c.a.uy * leg_a),
        (x + c.b.ux * leg_b, y + c.b.uy * leg_b),
    ])


def wedge(c: Corner, sight_ft: float, eye_back_ft: float, d: float = 0.0) -> Polygon:
    """A sight-distance area, street a the one looked along: the driver's
    eye ``eye_back_ft`` back along street b from street a's curb (``d`` ft
    out from the lot line), half a lane out in street b; the car seen
    ``sight_ft`` along street a, half a lane out in it. The area is what
    lies between that sight line and the corner (unclipped)."""
    x, y = apex(c, d)
    h = WEDGE_LANE_HALF_FT
    eye = (
        x + c.b.ux * eye_back_ft - c.b.nx * h,
        y + c.b.uy * eye_back_ft - c.b.ny * h,
    )
    seen = (x + c.a.ux * sight_ft - c.a.nx * h, y + c.a.uy * sight_ft - c.a.ny * h)
    return Polygon([(x, y), eye, seen])


def _shapes(c: Corner, rule: Any, legs: Sequence[float], d: float) -> list[Polygon]:
    """The rule's area at one corner, for one figure: every reading of an
    asymmetric or sight-distance rule (which street is which is not mapped)."""
    if rule.kind == "wedge":
        eye = float(rule.eye_back_ft or 0.0)
        flip = Corner(c.b, c.a)
        return [wedge(c, legs[0], eye, d), wedge(flip, legs[0], eye, d)]
    if rule.kind == "asymmetric":
        p, q = legs
        return [triangle(c, p, q, d), triangle(c, q, p, d)]
    return [triangle(c, legs[0], legs[0], d)]


def _figures(rule: Any, zone: str | None) -> list[tuple[float, ...]]:
    if rule.kind == "wedge":
        return [(s,) for s in rule.sight_ft]
    legs = tuple(rule.zone_legs_ft.get(zone, rule.legs_ft) if zone else rule.legs_ft)
    if rule.kind == "asymmetric":
        return [legs]
    return [(v,) for v in legs]


def corner_areas(
    lot: BaseGeometry,
    edges: LotEdges | None,
    rule: Any,
    zone: str | None = None,
    *,
    generous_ft: float = GENEROUS_CURB_OFFSET_FT,
) -> SightAreas | None:
    """The corner clear-vision areas on this lot under ``rule`` (a
    :class:`flats.rules.model.SightRule`), clipped to the lot; None where
    the rule keeps nothing off it (no rule, ``status: none``, a zone it
    excepts, no corner, or nothing of either area on the lot)."""
    from flats.score.screen import SIGHT_CORNER_CURB, SIGHT_CORNER_UNSETTLED

    if rule is None or rule.status == "none" or (zone and zone in rule.except_zones):
        return None
    found = corners(lot, edges)
    if not found:
        return None
    unsettled = rule.status == "unsettled" or bool(zone and zone in rule.unsettled_zones)
    curb = rule.basis != "lot_line"
    figures = _figures(rule, zone)
    if not figures or not all(figures):
        return None
    biggest = max(figures, key=lambda f: max(f))
    smallest = min(figures, key=lambda f: max(f))
    high = unary_union([
        p for c in found for p in _shapes(c, rule, biggest, 0.0)
    ]).intersection(lot)
    if unsettled:
        low: BaseGeometry = Polygon()
        reason = SIGHT_CORNER_UNSETTLED
    else:
        d = generous_ft if curb else 0.0
        parts = []
        for c in found:
            shapes = _shapes(c, rule, smallest, d)
            sure = shapes[0]
            for p in shapes[1:]:
                sure = sure.intersection(p)
            parts.append(sure)
        low = unary_union(parts).intersection(lot)
        # A gap between the figures with the lot line as the basis is a
        # street class nobody mapped: as unsettled as an unread rule.
        reason = SIGHT_CORNER_CURB if curb else SIGHT_CORNER_UNSETTLED
    if high.is_empty or high.area < OVERLAP_SQFT:
        return None
    return SightAreas(low=low, high=high, reason=reason, cite=rule.cite or "")


# --- the drive -----------------------------------------------------------


@dataclass(frozen=True)
class Mouth:
    """Where the drawn drive meets a street line: the centre point on the
    lot line, the unit direction along the street, the unit normal into
    the lot, and the drive's half-width."""

    cx: float
    cy: float
    tx: float
    ty: float
    nx: float
    ny: float
    half_ft: float


def drive_mouth(lane: BaseGeometry, lot: BaseGeometry, edges: LotEdges | None) -> Mouth | None:
    """The drawn lane's mouth on the nearest street line, or None (no
    lane, no street line within 2 ft of it)."""
    if lane is None or lane.is_empty or edges is None:
        return None
    best: tuple[float, Edge] | None = None
    for chain in street_chains(edges):
        for e in chain:
            if e.length_ft <= 0:
                continue
            seg = LineString([(e.x1, e.y1), (e.x2, e.y2)])
            dist = seg.distance(lane)
            if best is None or dist < best[0]:
                best = (dist, e)
    if best is None or best[0] > 2.0:
        return None
    e = best[1]
    seg = LineString([(e.x1, e.y1), (e.x2, e.y2)])
    tx, ty = (e.x2 - e.x1) / e.length_ft, (e.y2 - e.y1) / e.length_ft
    nx, ny = _inward(lot, e)
    # The lane's footprint along the street line: its points within 3 ft of
    # the line, projected.
    ring = list(lane.exterior.coords) if hasattr(lane, "exterior") else list(lane.coords)
    near = [(x, y) for x, y in ring if seg.distance(Point(x, y)) <= 3.0]
    if len(near) < 2:
        near = ring
    s = [(x - e.x1) * tx + (y - e.y1) * ty for x, y in near]
    lo, hi = min(s), max(s)
    mid = (lo + hi) / 2
    return Mouth(e.x1 + tx * mid, e.y1 + ty * mid, tx, ty, nx, ny, max((hi - lo) / 2, 0.0))


def driveway_area(
    m: Mouth,
    rule: Any,
    d: float = 0.0,
    *,
    front_setback_ft: float | None = None,
) -> BaseGeometry:
    """The drive's clear-vision area under ``rule`` with the curb ``d`` ft
    out from the lot line (lot-line basis: ``d`` is ignored). Unclipped."""
    if rule.basis == "lot_line":
        d = 0.0
    cx, cy = m.cx - m.nx * d, m.cy - m.ny * d
    if rule.kind == "apex":
        base = float(rule.base_ft or 0.0)
        if rule.depth_from == "front_setback":
            depth = float(front_setback_ft or 0.0)
            ox, oy = m.cx, m.cy
        elif rule.depth_from == "lot_line":
            depth, ox, oy = float(rule.depth_ft or 0.0), m.cx, m.cy
        else:
            depth, ox, oy = float(rule.depth_ft or 0.0), cx, cy
        tip = (ox + m.nx * depth, oy + m.ny * depth)
        return Polygon([
            (cx - m.tx * base, cy - m.ty * base), (cx + m.tx * base, cy + m.ty * base), tip,
        ])
    if rule.kind == "wedge":
        sight = max(rule.sight_ft)
        eye = (cx + m.nx * float(rule.eye_back_ft or 0.0), cy + m.ny * float(rule.eye_back_ft or 0.0))
        h = WEDGE_LANE_HALF_FT
        out = []
        for sgn in (1.0, -1.0):
            seen = (cx + sgn * m.tx * sight - m.nx * h, cy + sgn * m.ty * sight - m.ny * h)
            out.append(Polygon([(cx, cy), eye, seen]))
        return unary_union(out)
    # edge: a triangle each side of the drive, legs along the drive's edge
    # (into the lot) and along the street line (away from the drive).
    leg = max(rule.legs_ft) if rule.legs_ft else 0.0
    out = []
    for sgn in (1.0, -1.0):
        px, py = cx + sgn * m.tx * m.half_ft, cy + sgn * m.ty * m.half_ft
        out.append(Polygon([
            (px, py), (px + m.nx * leg, py + m.ny * leg),
            (px + sgn * m.tx * leg, py + sgn * m.ty * leg),
        ]))
    return unary_union(out)


def reaches(area: BaseGeometry, building: BaseGeometry, lot: BaseGeometry | None = None) -> bool:
    """Whether more than :data:`OVERLAP_SQFT` of the building stands in the
    area (on the lot)."""
    if area is None or building is None or area.is_empty or building.is_empty:
        return False
    if lot is not None:
        area = area.intersection(lot)
    return area.intersection(building).area > OVERLAP_SQFT
