"""Walls that must have windows, kept where a wall may have them (FOLLOWUPS 186).

Gresham 7.0420(I)(2) asks for clear glass on 5 percent of "all other
facades" -- every wall that does not face a street -- and Steph read that as
EACH facade (2026-11-12, rulings.yaml ``2026-11-12-gresham-glass-each-facade``):
the pod's two end walls and its back wall each carry glass. The walls between
its homes are inside the building and are not facades. The building code
allows no opening at all in a wall under 3 ft from a side or rear lot line
(ORSC R302.1 and Table R302.1, ``wall_opening_min_ft`` in the state layer),
measured at right angles from the wall (R302.1 Exception 1: a wall square to
the line is not measured to it) and, for a street or an alley, to its centre
line (R302.2), which no wall comes within 3 ft of. So in those zones a
placement whose end wall stands under 3 ft from a side or rear line is one the
two codes together forbid.

:func:`wall_opening_gap` measures the drawn building: rays cast square out of
every outside wall, a foot apart, each read to the first lot line it meets.
:func:`wall_openings_checked` re-screens the plan on that distance and, where
it is short, looks for another placement the fit allows that is not -- the
same listing, the same verification and the same "nothing worse" test the
flatter-spot search uses (:mod:`flats.ingest.flatter`). A plan with no such
placement keeps its drawing and fails the check: RED, the exclusion Steph
ruled ("fine to exclude").

Measured with the lot's edges, never its polygon: s4's outline and its edges
can differ by a fraction of a foot along a street, and only the edges know
which line is which.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any, Iterable

from shapely.geometry import MultiLineString, Polygon

from flats.geom.edges import Edge, EdgeClass

#: Feet between the rays cast out of each wall; each wall's two ends are
#: always cast.
RAY_STEP_FT = 1.0
#: How far a ray is read. A wall with no side or rear line this near in front
#: of it is reported this far away -- far past any floor the check reads.
RAY_REACH_FT = 50.0
#: A lot line this far BEHIND a wall's face is read as touching it: a drawn
#: building may overhang a lot line by a raster cell, and a ray cast outward
#: from a wall already past the line would never meet it.
BEHIND_TOL_FT = 0.5
#: Placements re-screened the whole way, nearest the street first.
VERIFY_MAX = 6
#: Placements listed per angle (the listing is thinned evenly).
LISTED_MAX = 200


def _interior(edge: Edge, streets: frozenset[tuple[float, float, float, float]]) -> bool:
    """A side or rear lot line a wall's fire separation distance is measured
    to: not a street (nor a street a through-lot plan renamed rear), and not
    an alley vouched for along its whole length. An alley whose stretch is
    partly unmeasured or partly a neighbour's is read as a neighbour's line,
    the conservative answer."""
    if edge.cls not in (EdgeClass.side, EdgeClass.rear):
        return False
    if (edge.x1, edge.y1, edge.x2, edge.y2) in streets:
        return False
    if edge.alley:
        if edge.cover is None:
            return False
        if edge.cover and set(edge.cover) <= {"1"}:
            return False
    return True


def _hit(px: float, py: float, nx: float, ny: float, edge: Edge) -> float | None:
    """How far along the ray ``p + t n`` (``n`` a unit vector) it meets the
    segment, or None; a crossing just behind the wall reads as 0."""
    ex, ey = edge.x2 - edge.x1, edge.y2 - edge.y1
    den = nx * ey - ny * ex
    if abs(den) < 1e-9:
        return None  # parallel: R302.1 Exception 1
    qx, qy = edge.x1 - px, edge.y1 - py
    t = (qx * ey - qy * ex) / den
    u = (qx * ny - qy * nx) / den
    if u < -1e-9 or u > 1 + 1e-9 or t < -BEHIND_TOL_FT:
        return None
    return max(t, 0.0)


def _walls(ring: list[list[float]]) -> Iterable[tuple[float, float, float, float, float, float]]:
    """Each outside wall as ``(x1, y1, x2, y2, nx, ny)``, ``n`` its outward
    unit normal."""
    pts = [(float(x), float(y)) for x, y in ring]
    if pts[0] == pts[-1]:
        pts = pts[:-1]
    area = sum(
        pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
        for i in range(len(pts))
    )
    ccw = area > 0
    for i in range(len(pts)):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % len(pts)]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        nx, ny = (dy / length, -dx / length) if ccw else (-dy / length, dx / length)
        yield x1, y1, x2, y2, nx, ny


def gap_ft(
    ring: list[list[float]],
    edges: Iterable[Edge],
    streets: Iterable[Edge] = (),
) -> float:
    """The nearest distance, square out of any wall of the building ``ring``,
    to a side or rear lot line that ray meets first; :data:`RAY_REACH_FT`
    where no such line is that near."""
    edges = tuple(edges)
    street_keys = frozenset((e.x1, e.y1, e.x2, e.y2) for e in streets)
    interior = [_interior(e, street_keys) for e in edges]
    best = RAY_REACH_FT
    for x1, y1, x2, y2, nx, ny in _walls(ring):
        length = math.hypot(x2 - x1, y2 - y1)
        n = max(1, math.ceil(length / RAY_STEP_FT))
        for k in range(n + 1):
            f = k / n
            px, py = x1 + f * (x2 - x1), y1 + f * (y2 - y1)
            first, inner = None, False
            for edge, is_in in zip(edges, interior):
                t = _hit(px, py, nx, ny, edge)
                if t is not None and (first is None or t < first):
                    first, inner = t, is_in
            if first is not None and inner and first < best:
                best = first
    return round(best, 2) + 0.0  # never -0.0


def _street_edges(s: Any) -> tuple[Edge, ...]:
    """The lot's street lines as cut, before a through-lot plan renamed an
    end rear (:attr:`flats.ingest.quadfit.Screened.street_edges`)."""
    held = getattr(s, "street_edges", None)
    if held is None:
        return ()
    return tuple(e for e in held.edges if e.cls in (EdgeClass.front, EdgeClass.street_side))


def wall_opening_gap(s: Any) -> float | None:
    """The drawn building's :func:`gap_ft`, or None where no fitting building
    is drawn or the lot has no classified lines."""
    drawing = s.drawing or {}
    ring = drawing.get("building")
    edges = getattr(s.lot, "edges", None)
    if not (drawing.get("fits") and ring and len(ring) >= 4) or edges is None:
        return None
    return gap_ft(ring, edges.edges, _street_edges(s))


def _applies(s: Any) -> float | None:
    """The no-openings floor where this plan's zone asks for glass on every
    non-street facade, else None."""
    from flats.score.screen import _pct

    glass = _pct(s.rules, "facade_glass_other_pct")
    floor = _pct(s.rules, "wall_opening_min_ft")
    if not glass or floor is None:
        return None
    return floor


def _screened(s: Any, gap: float | None, *, policy: Any, relief: Any) -> Any:
    """``s`` screened again with the measured distance in its facts."""
    from flats.ingest import quadfit as q

    facts = dataclasses.replace(s.facts, wall_opening_gap_ft=gap, wall_opening_tried=True)
    result = q.screen(s.rules, facts, s.design, s.fit, policy=policy, relief=relief, config=s.config)
    shadow = q._if_signed(
        s.rules, facts, s.design, s.fit, result, policy=policy, relief=relief, config=s.config
    )
    return dataclasses.replace(s, screening=result, signed=shadow, facts=facts)


def _red(s: Any) -> bool:
    from flats.score import flags as flag_plan

    return s.screening.colour is flag_plan.Colour.red and s.signed.colour is flag_plan.Colour.red


def _elsewhere(
    s: Any,
    lot: Any,
    fitter: Any,
    terrain: Any,
    floor: float,
    *,
    rules: Any,
    policy: Any,
    relief: Any,
    step_deg: float,
    roads: Any,
) -> Any | None:
    """The plan stood where every wall clears the floor, through the whole
    chain again and no worse than ``s`` in anything; None where no such
    placement is found. Only a court reached down a lane beside the building
    is moved: a court fed across a side yard, off an alley or a side street
    has a drive the drawing does not place (as :mod:`flats.ingest.flatter`)."""
    from flats.ingest import flatter
    from flats.ingest import quadfit as q

    drawing = s.drawing or {}
    if not (drawing.get("fits") and not drawing.get("tight") and drawing.get("lane")):
        return None
    if not flatter._lane_in_from_street(s):
        return None
    street = q._street_lines(lot)
    if not street:
        return None
    cap = flatter._max_front_ft(s, street)
    lines = MultiLineString([[(x1, y1), (x2, y2)] for x1, y1, x2, y2 in street])
    edges = s.lot.edges.edges
    streets = _street_edges(s)

    found: list[tuple[float, float, Any, Any]] = []
    for angle in flatter._angles(s, fitter):
        at = dataclasses.replace(s, fit=dataclasses.replace(s.fit, angle_deg=angle))
        listing: list[Any] = []
        q.drawing_for(
            at, fitter, listing=listing, max_front_ft=cap, include_frontmost=cap is not None
        )
        if len(listing) > LISTED_MAX:
            step = (len(listing) - 1) / (LISTED_MAX - 1)
            listing = [listing[round(i * step)] for i in range(LISTED_MAX)]
        for where in listing:
            drawn = q.drawing_for(at, fitter, where=where)
            if not drawn or not drawn.get("fits") or drawn.get("tight"):
                continue
            ring = drawn.get("building")
            if not ring or gap_ft(ring, edges, streets) < floor:
                continue
            front = Polygon(ring).distance(lines)
            if cap is not None and front > cap + flatter.FRONT_TOL_FT:
                continue
            found.append((front, angle, at, drawn))
    found.sort(key=lambda r: (r[0], r[1]))

    for _, _, at, drawn in found[:VERIFY_MAX]:
        if not flatter._drive_clear(drawn, at, street):
            continue
        facts = dataclasses.replace(
            s.facts,
            fire_route_ft=None,
            fire_route_tried=False,
            fire_route_curb_ft=None,
            fire_route_freed_ft=None,
            fire_route_row_ft=None,
            site_grade_pct=None,
            site_grade_source=None,
            site_grade_tried=False,
        )
        if facts.front_max_tried:
            facts = dataclasses.replace(
                facts,
                front_max_streets=q.front_max_streets(dataclasses.replace(at, drawing=drawn)),
            )
        result = q.screen(
            s.rules, facts, s.design, s.fit, policy=policy, relief=relief, config=s.config
        )
        shadow = q._if_signed(
            s.rules, facts, s.design, s.fit, result, policy=policy, relief=relief, config=s.config
        )
        cand = dataclasses.replace(
            at, fit=s.fit, drawing=drawn, facts=facts, screening=result, signed=shadow
        )
        cand = q.fire_checked(cand, lot, roads, policy=policy, relief=relief, fitter=None)
        cand = q.slope_checked(
            cand, lot, terrain, rules=rules, policy=policy, relief=relief, step_deg=step_deg,
            roads=roads,
        )
        if flatter._no_worse(s, cand):
            return dataclasses.replace(cand, room=s.room)
    return None


def wall_openings_checked(
    s: Any,
    lot: Any,
    fitter: Any,
    terrain: Any,
    *,
    rules: Any,
    policy: Any,
    relief: Any,
    step_deg: float,
    roads: Any,
) -> Any:
    """``s`` re-screened on how near its walls stand to a side or rear lot
    line, where the zone asks for glass on every non-street facade; stood
    elsewhere first where the drawn spot is too near and another spot is not
    (module docstring). Called after the fire route and the flatter spot have
    stood the building, before its distance from the street is measured
    again (:func:`flats.ingest.quadfit.moved_checked`)."""
    if s.facts is None:
        return s
    floor = _applies(s)
    if floor is None:
        return s
    gap = wall_opening_gap(s)
    if gap is not None and gap < floor and fitter is not None and not _red(s):
        moved = _elsewhere(
            s, lot, fitter, terrain, floor, rules=rules, policy=policy, relief=relief,
            step_deg=step_deg, roads=roads,
        )
        if moved is not None:
            return _screened(moved, wall_opening_gap(moved), policy=policy, relief=relief)
    return _screened(s, gap, policy=policy, relief=relief)
