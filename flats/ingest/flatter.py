"""A flatter spot for the pod on the ground the lot already allows (FOLLOWUPS 57).

The drawing stands the building and its court at one place: the window
nearest the street (:func:`flats.fit.draw.draw`). The grade under that spot
is measured, and on a hillside lot it reads 5-15% -- a closer look -- or
over 15% -- red -- though the same buildable ground often holds a flatter
spot. This module looks for one.

For a plan the grade alone holds out of GREEN, every other spot the fit
allows is listed (:func:`flats.fit.draw.draw` ``listing``) at the fit's
angle and at the other angles the code allows, ranked by the fall under it
(:class:`flats.fit.slope.Surface`, one read of the elevation model for the
lot), and the flattest few are put through the whole chain again: the
court's ground is in the listing, the setbacks are the envelope's, and the
fire hose route and the grade are measured on the new drawing
(:func:`flats.ingest.quadfit.fire_checked`, ``slope_checked``). A spot is
adopted only if it is flatter by the ruling's own bands, its drive in from
the street is clear, it stands no further from the street than a stated
maximum front setback allows, and nothing about the plan is worse: no colour,
no check, no flag the old spot did not have. Otherwise the plan comes back
as it came.

Steph's ruling on the grade does not change (``flats/config/slope.yaml``):
the pad is measured as before, and a flatter spot is only a different pad.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any

from shapely.geometry import LineString, MultiLineString, Polygon
from shapely.ops import nearest_points

from flats.fit.angles import normalize
from flats.fit.slope import ONE_M, load_rules as slope_rules
from flats.score import flags as flag_plan

#: The models whose grade is searched for a flatter spot. The 10 m model
#: reads a pad a few cells wide, so the fall under one spot differs from the
#: next by noise as much as by ground, and the flattest of hundreds would be
#: the luckiest reading rather than the flattest ground.
SEARCH_SOURCES: tuple[str, ...] = (ONE_M,)
#: Angles searched, nearest square to a street first (the fit's own first).
ANGLES_MAX = 7
#: Spots ranked at most, over every angle: the listing is thinned evenly.
RANKED_MAX = 1500
#: Spots put through the whole chain, flattest first.
VERIFY_MAX = 4
#: A spot is looked at only if the fall under it is lower by this much.
GAIN_PCT = 0.5
#: Overlap, in sqft, a drive in from the street may share with ground the
#: plan may not use, or with the building.
DRIVE_OVERLAP_SQFT = 1.0
#: Feet a drive's centreline may end short of, or past, the street line.
DRIVE_TOL_FT = 0.5
#: Feet past a stated maximum front setback the drawn building may stand:
#: the listing measures to street points two feet apart.
FRONT_TOL_FT = 2.5

_BAND = {"green": 0, "closer": 1, "red": 2}
_COLOUR = {
    flag_plan.Colour.green: 0,
    flag_plan.Colour.yellow: 1,
    flag_plan.Colour.red: 2,
}


def _band(s: Any) -> int | None:
    facts = s.facts
    if facts is None or facts.site_grade_pct is None:
        return None
    return _BAND[slope_rules().band(facts.site_grade_pct, facts.site_grade_source or "")]


def _ring(drawing: dict[str, Any] | None, key: str) -> Polygon | None:
    ring = (drawing or {}).get(key)
    if not ring or len(ring) < 4:
        return None
    return Polygon(ring)


def _no_worse(base: Any, cand: Any) -> bool:
    """Whether ``cand`` is, under both readings, no worse than ``base`` in
    colour, in what it fails, and in what it asks."""
    for b, c in ((base.screening, cand.screening), (base.signed, cand.signed)):
        if _COLOUR[c.colour] > _COLOUR[b.colour]:
            return False
        if {x.check for x in c.binds} - {x.check for x in b.binds}:
            return False
        if {f.code for f in c.flags} - {f.code for f in b.flags}:
            return False
    return True


def _could_improve(s: Any, *, policy: Any, relief: Any) -> bool:
    """Whether a pad with no fall at all would lift ``s`` in colour: the
    grade is all that stands in the way. A plan another flag or a failed
    check holds where it is gains nothing from a flatter spot."""
    from flats.ingest import quadfit as q

    facts = dataclasses.replace(s.facts, site_grade_pct=0.0, site_grade_source=ONE_M)
    result = q.screen(s.rules, facts, s.design, s.fit, policy=policy, relief=relief, config=s.config)
    shadow = q._if_signed(
        s.rules, facts, s.design, s.fit, result, policy=policy, relief=relief, config=s.config
    )
    return any(
        _COLOUR[after.colour] < _COLOUR[before.colour]
        for before, after in ((s.screening, result), (s.signed, shadow))
    )


def _lane_in_from_street(s: Any) -> bool:
    """Whether this plan's court is reached down a lane beside the building,
    the one way a drawn spot other than the nearest the street is sound. A
    court reached across a side yard, from an alley or off a side street has
    a drive the drawing does not place."""
    from flats.ingest import quadfit as q

    lot = s.lot
    if s.fit.beside or s.fit.column or not s.design.parking.parks:
        return False
    if lot.facts.alley_at_rear:
        return False
    across = q.court_across(s.design, s.rules, lot.facts.alley, corner=lot.facts.corner)
    return bool(across.lane_ft)


def _max_front_ft(s: Any, street: tuple[tuple[float, float, float, float], ...]) -> float | None:
    """How far from the front lines the building may stand: the stated
    maximum front setback, or where the plan already stands further, that."""
    stated = s.rules.get("setback_front_max_ft")
    here = _ring(s.drawing, "building")
    if stated is None or here is None or not street:
        return None
    try:
        cap = float(stated)
    except (TypeError, ValueError):
        return None
    lines = MultiLineString([[(x1, y1), (x2, y2)] for x1, y1, x2, y2 in street])
    return max(cap, here.distance(lines))


def _drive_clear(
    drawing: dict[str, Any],
    s: Any,
    street: tuple[tuple[float, float, float, float], ...],
) -> bool:
    """Whether the lane's way in from the street lot line lies on the lot,
    off the ground the plan may not use, and off the building."""
    lane = _ring(drawing, "lane")
    building = _ring(drawing, "building")
    lot = s.lot
    if lane is None or building is None or lot.lot_geom is None or not street:
        return False
    lines = MultiLineString([[(x1, y1), (x2, y2)] for x1, y1, x2, y2 in street])
    here, there = nearest_points(lane, lines)
    if here.distance(there) <= DRIVE_TOL_FT:
        return True
    width = max(min(lane.bounds[2] - lane.bounds[0], lane.bounds[3] - lane.bounds[1]), 1.0)
    drive = LineString([(here.x, here.y), (there.x, there.y)]).buffer(width / 2, cap_style="flat")
    if not lot.lot_geom.buffer(DRIVE_TOL_FT).contains(drive.buffer(-0.01)):
        return False
    if drive.intersection(building).area > DRIVE_OVERLAP_SQFT:
        return False
    for bar in (lot.carve, lot.steep):
        if bar is not None and not bar.is_empty and drive.intersection(bar).area > DRIVE_OVERLAP_SQFT:
            return False
    return True


def _angles(s: Any, fitter: Any) -> list[float]:
    """The fit's own angle, then the other angles the fitter holds, nearest
    square to a street first, at most :data:`ANGLES_MAX` in all."""
    square = [normalize(b + turn) for b in s.lot.front_bearings for turn in (0.0, 90.0)]

    def off(angle: float) -> float:
        d = min((abs(angle - a) % 180.0 for a in square), default=0.0)
        return min(d, 180.0 - d)

    own = s.fit.angle_deg
    others = sorted(
        {g.angle_deg for g in fitter.grids if not math.isclose(g.angle_deg, own, abs_tol=1e-6)},
        key=lambda a: (off(a), a),
    )
    return [own, *others][:ANGLES_MAX]


def flatter_checked(
    s: Any,
    lot: Any,
    terrain: Any,
    fitter: Any,
    *,
    rules: Any,
    policy: Any,
    relief: Any,
    step_deg: float,
    roads: Any,
) -> Any:
    """``s``, or the same plan stood on a flatter spot of the same ground
    (module docstring). Called after :func:`flats.ingest.quadfit.
    slope_checked` has graded the plan where the drawing first put it."""
    from flats.ingest import quadfit as q

    if terrain is None or fitter is None or s.facts is None or lot.lot_geom is None:
        return s
    if s.facts.site_grade_source not in SEARCH_SOURCES or s.facts.outdoor_square_ft is not None:
        return s
    base_band = _band(s)
    if not base_band or s.fit.angle_deg is None:
        return s
    drawing = s.drawing or {}
    if not (drawing.get("fits") and not drawing.get("tight") and drawing.get("lane")):
        return s
    if not _lane_in_from_street(s) or not _could_improve(s, policy=policy, relief=relief):
        return s
    street = q._street_lines(lot)
    if not street:
        return s
    surface = terrain.surface(lot.lot_geom)
    if surface is None:
        return s
    cap = _max_front_ft(s, street)
    base_pct = float(s.facts.site_grade_pct)

    ranked: list[tuple[float, float, Any, Any]] = []
    for angle in _angles(s, fitter):
        at = dataclasses.replace(s, fit=dataclasses.replace(s.fit, angle_deg=angle))
        listing: list[Any] = []
        q.drawing_for(at, fitter, listing=listing, max_front_ft=cap)
        if len(listing) > RANKED_MAX // ANGLES_MAX:
            step = (len(listing) - 1) / (RANKED_MAX // ANGLES_MAX - 1)
            listing = [listing[round(i * step)] for i in range(RANKED_MAX // ANGLES_MAX)]
        for where in listing:
            drawn = q.drawing_for(at, fitter, where=where)
            if not drawn or not drawn.get("fits"):
                continue
            pads = [p for p in (_ring(drawn, "building"), _ring(drawn, "court")) if p is not None]
            got = surface.grade(pads)
            if got is None or got.source not in SEARCH_SOURCES:
                continue
            if got.pct <= base_pct - GAIN_PCT and _BAND[slope_rules().band(got.pct, got.source)] < base_band:
                ranked.append((got.pct, angle, at, drawn))
    ranked.sort(key=lambda r: (r[0], r[1]))

    for _, _, at, drawn in ranked[:VERIFY_MAX]:
        if not _drive_clear(drawn, at, street):
            continue
        building = _ring(drawn, "building")
        lines = MultiLineString([[(x1, y1), (x2, y2)] for x1, y1, x2, y2 in street])
        if cap is not None and (building is None or building.distance(lines) > cap + FRONT_TOL_FT):
            continue
        facts = dataclasses.replace(
            s.facts,
            fire_route_ft=None,
            fire_route_tried=False,
            fire_route_curb_ft=None,
            site_grade_pct=None,
            site_grade_source=None,
            site_grade_tried=False,
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
        band = _band(cand)
        if band is not None and band < base_band and _no_worse(s, cand):
            return dataclasses.replace(cand, room=s.room)
    return s
