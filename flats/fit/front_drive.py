"""The drive a drawn plan needs from the street to its parking, drawn (FOLLOWUPS 206).

:func:`flats.fit.draw.draw` draws the building, the lane beside it and the
court, but not the pavement between the street and the building's street
face: the lane is drawn ``band(0, deep_b)`` from that face back, so the run
across the front yard to the street line is nobody's shape. Nothing could
then measure it against ground the lot may not be paved on (an overlay carve,
:func:`flats.ingest.quadfit.plan_on_carve_checked`).

:func:`corridors` draws it from the stored drawing alone (the rings
:meth:`flats.fit.draw.Drawing.to_json` writes), in the drawing's own frame:

* **a lane** -- the lane's width, from the building's street face straight out
  along the fit's deep axis, away from the court, to where the lot ends;
* **a court beside the building** (no lane; the court's aisle is the drive) --
  the court's band, the same way;
* **a court behind the building with no lane** (an alley, a side street or a
  rear street feeds it) -- the court's depth band out each side to the lot's
  line, and its width out the back: each run that reaches a street or alley
  line is the drive; where none does, every run is (where the drive meets the
  court is not known, so every place it could run is measured).

The lot is the lot polygon together with the ring its classified lines
close (``ground``): where the polygon stops short of the street line the
drive still runs to the line. A run is kept only as far as it stays on the
lot from its mouth (the piece touching the mouth), so a lot that bends back
does not lend it ground past a gap.

**Which way is the street.** The deep axis is one of the building ring's two
axes: the one a drawn lane confirms (the lane spans the building's depth on
it), else the one nearest the fit's angle; with neither, both are drawn. The
street face is the building's end away from the court (else the room); where
neither says, both ends are drawn. Every doubt draws more drive, never less:
more ground measured can only hold a lot, never pass one.
"""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Sequence

import shapely
from shapely import affinity
from shapely.geometry import LineString, Polygon, box
from shapely.geometry.base import BaseGeometry

#: Longer than any lot: the lot's line is what ends a run.
REACH_FT = 5000.0
#: A drawn ring is rounded to a tenth of a foot and the raster's cell is half
#: a foot: two edges this close are the same edge.
TOL_FT = 0.6
#: A run piece this near its mouth starts there.
MOUTH_FT = 0.5
#: A run reaches a street or alley line this near.
LINE_FT = 0.5

Line = tuple[float, float, float, float]


def _poly(ring: Any) -> BaseGeometry | None:
    if not ring or len(ring) < 4:
        return None
    got = Polygon(ring)
    if not got.is_valid:
        got = got.buffer(0)
    return None if got.is_empty else got


def ground(lot: BaseGeometry | None, lines: Iterable[Line] = ()) -> BaseGeometry | None:
    """``lot`` together with the polygon its classified lot lines close."""
    segs = [LineString(((x1, y1), (x2, y2))) for x1, y1, x2, y2 in lines]
    ring = None
    if len(segs) >= 3:
        got = shapely.polygonize(segs)
        parts = [p for p in shapely.get_parts(got) if p.area > 0]
        if parts:
            ring = shapely.union_all(parts)
    if lot is None or lot.is_empty:
        return ring
    if ring is None or ring.is_empty:
        return lot
    return lot.union(ring)


def _axis_deg(building: BaseGeometry) -> float:
    """The bearing of the building ring's first side, in degrees."""
    (x1, y1), (x2, y2) = list(building.exterior.coords)[:2]
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def _diff_mod_180(a: float, b: float) -> float:
    d = (a - b) % 180.0
    return min(d, 180.0 - d)


def _bounds(geom: BaseGeometry | None, ang: float, origin: Any) -> tuple[float, float, float, float] | None:
    if geom is None:
        return None
    return affinity.rotate(geom, -ang, origin=origin).bounds


def _frames(
    building: BaseGeometry, lane: BaseGeometry | None, angle_deg: float | None
) -> list[float]:
    """The frame angles (degrees) whose y axis may be the deep axis."""
    a0 = _axis_deg(building)
    # The drawing's frame turns the world by ``ang``; its deep axis is the
    # frame's y. Candidates: the building ring's two axes as that frame.
    cands = [a0 - 90.0, a0]
    o = building.centroid
    if lane is not None:
        ok = []
        for ang in cands:
            _, by0, _, by1 = _bounds(building, ang, o)
            lx0, ly0, lx1, ly1 = _bounds(lane, ang, o)
            bx0, _, bx1, _ = _bounds(building, ang, o)
            beside = lx1 <= bx0 + TOL_FT or lx0 >= bx1 - TOL_FT
            if abs(ly0 - by0) <= TOL_FT and abs(ly1 - by1) <= TOL_FT and beside:
                ok.append(ang)
        if len(ok) == 1:
            return ok
        cands = ok or cands
    if angle_deg is not None:
        best = min(cands, key=lambda c: _diff_mod_180(c, angle_deg))
        if _diff_mod_180(best, angle_deg) < 10.0:
            return [best]
    return cands


def _far(
    ang: float, origin: Any, b: tuple[float, float, float, float], refs: Sequence[BaseGeometry | None]
) -> list[int]:
    """+1 where the court (else the room) runs past the building's high-y
    end, -1 past its low-y end; both where neither says."""
    _, by0, _, by1 = b
    for ref in refs:
        got = _bounds(ref, ang, origin)
        if got is None:
            continue
        _, ry0, _, ry1 = got
        hi, lo = ry1 > by1 + TOL_FT, ry0 < by0 - TOL_FT
        if hi and not lo:
            return [+1]
        if lo and not hi:
            return [-1]
    return [+1, -1]


def _run(
    strip: BaseGeometry, mouth: BaseGeometry, ang: float, origin: Any, land: BaseGeometry
) -> BaseGeometry | None:
    """``strip`` (frame coordinates) on the lot, as far as it stays on it from
    ``mouth``."""
    world = affinity.rotate(strip, ang, origin=origin)
    at = affinity.rotate(mouth, ang, origin=origin)
    got = world.intersection(land)
    parts = [p for p in shapely.get_parts(got) if p.area > 0 and p.distance(at) < MOUTH_FT]
    if not parts:
        return None
    return shapely.union_all(parts)


def corridors(
    plan: Mapping[str, Any] | None,
    lot: BaseGeometry | None,
    *,
    angle_deg: float | None = None,
    lines: Iterable[Line] = (),
    streets: Iterable[Line] = (),
) -> tuple[BaseGeometry, ...]:
    """The drive runs ``plan`` needs from a street to its parking, each on the
    lot (see the module docstring). ``lines`` are all the lot's classified
    lines (they extend a lot polygon that stops short), ``streets`` the ones a
    car may come in from (street lines, alleys, a private road). Empty where
    nothing fitting is drawn, no building is drawn, or the plan parks nothing.
    """
    if not plan or not plan.get("fits"):
        return ()
    building = _poly(plan.get("building"))
    if building is None:
        return ()
    lane, court, room = (_poly(plan.get(k)) for k in ("lane", "court", "room"))
    if lane is None and court is None:
        return ()
    land = ground(lot, lines)
    if land is None or land.is_empty:
        return ()
    street_lines = [LineString(((x1, y1), (x2, y2))) for x1, y1, x2, y2 in streets]
    o = building.centroid
    out: list[BaseGeometry] = []
    for ang in _frames(building, lane, angle_deg):
        b = _bounds(building, ang, o)
        bx0, by0, bx1, by1 = b
        mouths: list[tuple[float, float]] = []
        if lane is not None:
            lx0, _, lx1, _ = _bounds(lane, ang, o)
            mouths.append((lx0, lx1))
        else:
            cx0, cy0, cx1, cy1 = _bounds(court, ang, o)
            if cx1 <= bx0 + TOL_FT or cx0 >= bx1 - TOL_FT:
                mouths.append((cx0, cx1))
            else:
                out.extend(_side_fed(court, b, ang, o, land, street_lines))
                continue
        for far in _far(ang, o, b, (court, room)):
            face = by0 if far == +1 else by1
            for mx0, mx1 in mouths:
                if far == +1:
                    strip = box(mx0, face - REACH_FT, mx1, face)
                else:
                    strip = box(mx0, face, mx1, face + REACH_FT)
                got = _run(strip, LineString(((mx0, face), (mx1, face))), ang, o, land)
                if got is not None:
                    out.append(got)
    return tuple(out)


def _side_fed(
    court: BaseGeometry,
    b: tuple[float, float, float, float],
    ang: float,
    o: Any,
    land: BaseGeometry,
    streets: Sequence[LineString],
) -> list[BaseGeometry]:
    """A court behind the building with no lane: its runs out each side and
    out the back (never toward the building, which stands in that way);
    those reaching a street or alley line, else all of them."""
    cx0, cy0, cx1, cy1 = _bounds(court, ang, o)
    _, by0, _, by1 = b
    candidates = [
        (box(cx0 - REACH_FT, cy0, cx0, cy1), LineString(((cx0, cy0), (cx0, cy1)))),
        (box(cx1, cy0, cx1 + REACH_FT, cy1), LineString(((cx1, cy0), (cx1, cy1)))),
    ]
    if cy1 > by1 + TOL_FT:
        candidates.append((box(cx0, cy1, cx1, cy1 + REACH_FT), LineString(((cx0, cy1), (cx1, cy1)))))
    if cy0 < by0 - TOL_FT:
        candidates.append((box(cx0, cy0 - REACH_FT, cx1, cy0), LineString(((cx0, cy0), (cx1, cy0)))))
    runs = [got for strip, mouth in candidates if (got := _run(strip, mouth, ang, o, land)) is not None]
    reach = [r for r in runs if any(r.distance(s) < LINE_FT for s in streets)]
    return reach or runs
