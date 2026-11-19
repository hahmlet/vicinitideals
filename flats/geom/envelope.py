"""The buildable envelope: the lot minus everything the setbacks take.

Two constructions, chosen by how much the edge classification can be trusted.

*Per-edge strips.* Take from the lot every point nearer a lot line than that
line's setback, and keep the rest. Each strip is exactly that ground for one
line (:func:`_strip`): the band either side of the line, closed at each end by
the half-disc around the endpoint -- the ground near the end of a line is near
the line. So the envelope is the legal one: a building point is kept only if
it is at least each line's setback from that line. The half-disc is drawn as
a polygon around the circle, never inside it, so the strip never falls short
of the setback (by at most ``ARC_SPLITS``' sag, a few hundredths of a foot,
it reaches past). Until 2026-11-09 the strips had square caps, which ran each
one a full setback past its ends; at an inward bend in a line that took a
sliver up to a setback deep beyond the bend (Tigard 2S103BA00137, a 4.5 deg
front bend, pushed the building to 21.08 ft against a 20 ft front maximum).

Each strip is measured from the lot line the edge stands for, not from the
edge: an edge is a chord of the simplified ring, and where the lot's own line
bows inside it the strip is widened by that much (:func:`_sag`).

*Uniform inward buffer.* For irregular and flag-shaped lots, shrink the whole
lot by the largest setback. Strictly smaller than the truth, often by a lot, and
that is the point: on a shape where naming the front is guesswork, an envelope
that might be too big would produce false GREENs on the least reviewable lots.
An Eastern Pattern Area depth-proportional rear setback is added only along the
rear edge(s) farthest from the front; every other rear edge keeps its ordinary
rear setback.

Corner lots take the stricter of the front and street-side setback on every
street edge, because geometry cannot say which street line is legally the
front -- unless the code has said it and the edges carry the answer
(:func:`flats.geom.corner.name_front`): then the named front takes the front
setback, the other street the street-side one, and nothing is doubled.
Fragments too small to hold anything are dropped — a pod does not fit in
a forty-square-foot wedge, and carrying it costs a raster.

*The alley line.* Portland (and the county's copy of its chapter) requires no
side or rear setback from a lot line abutting an alley. The rear half is a
rule about the rear line, and the rule layer holds it on the rear setback
itself, switched by ``alley_at_rear`` — so it arrives here as a ``rear_ft`` of
zero and needs nothing more. The side half is a rule about ONE of the two side
lines, and ``setback_side_ft`` is one number for both; so it has its own field,
``setback_alley_side_ft``, which arrives as :attr:`Setbacks.alley_side_ft` and
is applied to the side edge flagged :attr:`~flats.geom.edges.Edge.alley` and to
no other. None means the code does not distinguish that line, and it takes the
ordinary side setback. The far side yard is never touched either way.

*A line on the alley is not a line the alley runs the length of* (FOLLOWUPS
3(e)). quadfit's s4 names a line an alley line on three rays of five, and
also records where along it the alley really runs (``alley_cover_json``,
:attr:`~flats.geom.edges.Edge.cover`). The side line is cut stretch by
stretch (:func:`_pieces`): the alley's number where the alley runs, the
ordinary side setback across from the neighbour. So is the rear line the
alley runs PART of (Steph 2026-09-28, "careful reading": such a line abuts
the alley along the covered stretch only). The bridge switches
``alley_at_rear`` on only where the alley runs the whole rear line
(:func:`flats.geom.alley.registry_alley`), so a part-covered lot resolves
with the ordinary rear; the bridge resolves it once more with the alley and
hands that rear over as :attr:`Setbacks.alley_rear_ft`, which the covered
stretches take -- and the rest of the line the larger of the two. No cover
on record is no covered stretch, and the whole line keeps the larger.

*Two rear lines, one on the alley* (FOLLOWUPS 12(b), 3). A corner lot's
line opposite the side street, or the second leg of a jogged rear, is a rear
line too, and the alley behind the lot is not behind it. The rules resolve
the rear setback once for the lot, so the bridge resolves it twice -- with
``alley_at_rear`` and without -- and hands both over: the alley's
(:attr:`Setbacks.alley_rear_ft`) for the rear edges on the alley, the
ordinary ``rear_ft`` for every other rear edge. An exemption is a zero like
any other number here, and an alley rear edge whose cover does not vouch for
all of it takes the larger of the two.

*The street line off a corridor.* Portland's commercial zones set 10 ft from a
street lot line on a Map 130-1 stretch and none from any other. The rule
layer holds the 10 on the front setback behind a lot-level fact that is true
when ANY street line is on a stretch -- the conservative reading every
edgeless reader keeps -- and the plain row on its own field,
``setback_street_off_corridor_ft``, which arrives as
:attr:`Setbacks.street_off_corridor_ft` and is applied to a street edge
flagged :attr:`~flats.geom.edges.Edge.off_corridor` and to no other. The zone
states one number for every street lot line, so it stands in for both the
front and the street-side number; where the zone also states a street-side
setback, the bridge does not pass it (:func:`flats.ingest.quadfit.setbacks_for`).

*The street line across from a residential zone.* The same zones set 5 ft
from a street lot line facing an RF-RM2 or RMP zone across a local street
(33.130.215.B.1.b). The street's class is not held, so every street is read
as local, and the 5 is the zone's street number -- the front setback, and
``setback_street_off_corridor_ft`` off the corridor. The plain "none" row
arrives as :attr:`Setbacks.street_clear_ft` and is applied only to a street
edge flagged both ``off_corridor`` and
:attr:`~flats.geom.edges.Edge.across_clear` (every ray across the street read
and none of them residential, :func:`flats.geom.neighbour.street_lines_clear`).
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

import numpy as np
import shapely
from shapely.geometry import LineString, MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry

from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier

#: Envelope fragments below this hold nothing worth rasterizing.
MIN_PART_SQFT = 200.0

#: The most a lot line may stray from the edge that stands for it. The edges
#: the bridge reads are quadfit s4's, the lot's ring simplified at
#: ``geometry.simplify_tolerance_ft`` (Lot Analysis/quadfit/config/rules.yaml,
#: 1.5 ft; ``flats/tests/test_envelope_sag.py`` holds this figure to it). Used
#: only where an edge cannot be found on the lot's own ring (:func:`_sag`).
SMOOTH_FT = 1.5

#: How near an edge's end a vertex of the lot's own ring must lie to be that
#: end, in feet. Simplifying keeps vertices, it does not move them.
SNAP_FT = 0.05

#: Chords per half-disc at a strip's end (:func:`_strip`). Even, so a chord's
#: midpoint (not a corner) sits straight off the line's end and the strip
#: stays inside the old square cap. 32 chords overshoot the circle by
#: ``1/cos(pi/64) - 1`` = 0.12% of the setback (0.024 ft at 20 ft).
ARC_SPLITS = 32


@dataclass(frozen=True, slots=True)
class Setbacks:
    """The numbers the envelope is cut with, in feet."""

    front_ft: float = 0.0
    side_ft: float = 0.0
    rear_ft: float = 0.0
    #: A depth-proportional rear setback applied only on the rear edge(s)
    #: farthest from the front lot line (Portland's Eastern Pattern Area).
    depth_rear_ft: float | None = None
    #: The side setback along a second street. None means the code does not
    #: distinguish it, in which case a corner lot uses the front setback.
    street_side_ft: float | None = None
    #: The side setback on the side line abutting an alley
    #: (``setback_alley_side_ft``; zero where the code waives it). None means
    #: the code does not distinguish that line and it takes ``side_ft``. Read
    #: for the side edge flagged ``alley`` only; the other side line never
    #: sees it.
    alley_side_ft: float | None = None
    #: The setback on a street line surely OFF every Map 130-1 stretch
    #: (``setback_street_off_corridor_ft``). None means the zone does not
    #: distinguish it and the line takes its class's number. Read for a front
    #: or street-side edge flagged ``off_corridor`` only.
    street_off_corridor_ft: float | None = None
    #: The scenic corridor setback (``setback_scenic_corridor_ft``; Portland
    #: 33.480.040.B.2.a, Table 480-1) on a street line read ON a scenic
    #: corridor. A minimum beside the zone's own, so the line takes the
    #: larger of the two (Table 480-1 note [1]: "Larger minimum setbacks ...
    #: supersede this setback"). None means the code states none. Read for an
    #: edge flagged ``on_scenic`` only, whatever its class: only a street
    #: line is ever flagged, and a through lot's far street line is one.
    scenic_corridor_ft: float | None = None
    #: The rear setback on a rear line the alley runs end to end -- the rear
    #: setback's ``alley_at_rear`` variant (Portland's and Multnomah's
    #: exemption, as zero; Gresham's, Troutdale's and Fairview's numbers)
    #: where the lot ALSO has a rear line off the alley, which then takes
    #: ``rear_ft``, the ordinary number (FOLLOWUPS 12(b), 3). None means the
    #: lot's rear lines are not told apart and every one takes ``rear_ft``.
    #: Read for a rear edge flagged ``alley`` only: the whole edge where its
    #: cover vouches for all of it (:meth:`for_edge`), else the stretches it
    #: does vouch for (:func:`_pieces`). Also set, with ``rear_ft`` the
    #: ordinary number, on a lot whose alley runs PART of its rear line.
    alley_rear_ft: float | None = None
    #: The setback on a street line surely off every Map 130-1 stretch AND
    #: surely facing no zone the across-the-street rule names
    #: (``setback_street_across_nonresidential_ft``; Portland 33.130.215.B.1.b).
    #: None means the zone does not distinguish it. Read for a front or
    #: street-side edge flagged both ``off_corridor`` and ``across_clear``.
    street_clear_ft: float | None = None
    #: Clackamas ZDO 1005.02(L): the separation a line drawn off the top of
    #: the building owes toward the north (``setback_north_ft``) and toward
    #: the east and west (``setback_east_west_ft``), cut by the bearing of
    #: each lot line rather than by its class (:mod:`flats.geom.bearing`).
    #: Zero where the zone states neither, which is every zone but three.
    north_ft: float = 0.0
    east_west_ft: float = 0.0
    #: What a public road on the north line counts toward ``north_ft``:
    #: 1005.02(L)(1)(a)'s "plus 15 feet into the property", the road's own
    #: width unmeasured.
    north_street_credit_ft: float = 0.0
    #: Where true north points at this lot, in degrees from grid north
    #: (:func:`flats.geom.bearing.true_north_deg`). None sweeps grid north
    #: alone.
    true_north_deg: float | None = None
    #: The larger of two unequal side yards, where the code names both
    #: (Milwaukie 19.301.5.A: "one side yard shall be at least 5 ft and one
    #: side yard shall be at least 10 ft"); ``side_ft`` is the smaller. None
    #: where the code states one side yard.
    side_larger_ft: float | None = None
    #: Which of the lot's two side lot lines takes ``side_larger_ft``: 0 or
    #: 1, into :func:`side_lines`. None lays it on EVERY side line -- the
    #: cautious cut, and the only one where the side lines do not fall in two.
    larger_side: int | None = None

    @property
    def by_bearing(self) -> bool:
        return self.north_ft > 0 or self.east_west_ft > 0

    def for_class(self, cls: EdgeClass) -> float:
        return {
            EdgeClass.front: self.front_ft,
            EdgeClass.rear: self.rear_ft,
            EdgeClass.side: self.side_ft,
            EdgeClass.street_side: (
                self.front_ft if self.street_side_ft is None else self.street_side_ft
            ),
        }[cls]

    def for_edge(self, edge: Edge) -> float:
        """The setback one edge takes: its class's, unless it is an alley line.

        A rear edge on the alley takes :attr:`alley_rear_ft` where it is set
        and the edge's cover vouches for all of it (or the edge came from a
        classifier that measures no stretch, ``cover`` None). An alley rear
        edge whose cover does not -- none on record, or the alley stopping
        short -- takes the larger of the two rear numbers: the waiver or the
        alley number is about "a lot line abutting an alley", and nothing
        says where along this one the neighbour's yard begins.
        """
        return self._plain(edge) + edge.dedication_ft

    def for_far_rear_edge(self, edge: Edge) -> float:
        """The setback on a rear edge farthest from the front lot line."""
        if self.depth_rear_ft is None or edge.cls is not EdgeClass.rear:
            return self.for_edge(edge)
        return self.depth_rear_ft + edge.dedication_ft

    def _plain(self, edge: Edge) -> float:
        """:meth:`for_edge` before any right-of-way is given up."""
        base = self._by_line(edge)
        if edge.on_scenic and self.scenic_corridor_ft is not None:
            return max(base, self.scenic_corridor_ft)
        return base

    def _by_line(self, edge: Edge) -> float:
        """:meth:`_plain` before the scenic corridor's minimum."""
        if edge.alley and edge.cls is EdgeClass.side and self.alley_side_ft is not None:
            return self.alley_side_ft
        if edge.alley and edge.cls is EdgeClass.rear and self.alley_rear_ft is not None:
            from flats.geom.alley import whole

            if edge.cover is None or whole(edge.cover):
                return self.alley_rear_ft
            return max(self.rear_ft, self.alley_rear_ft)
        if (
            edge.off_corridor
            and edge.across_clear
            and edge.cls in (EdgeClass.front, EdgeClass.street_side)
            and self.street_clear_ft is not None
        ):
            return self.street_clear_ft
        if (
            edge.off_corridor
            and edge.cls in (EdgeClass.front, EdgeClass.street_side)
            and self.street_off_corridor_ft is not None
        ):
            return self.street_off_corridor_ft
        return self.for_class(edge.cls)

    @property
    def largest_ft(self) -> float:
        return max(
            self.front_ft,
            self.side_ft,
            self.rear_ft,
            self.street_side_ft or 0.0,
            self.alley_rear_ft or 0.0,
            self.side_larger_ft or 0.0,
        )

    def on_a_corner(self) -> Setbacks:
        """The same setbacks, with street edges taking the stricter standard."""
        if self.street_side_ft is None:
            return self
        return dataclasses.replace(
            self, front_ft=max(self.front_ft, self.street_side_ft)
        )


def _clean(env: BaseGeometry, min_part_sqft: float) -> MultiPolygon:
    parts = [
        p
        for p in shapely.get_parts(env)
        if p.geom_type == "Polygon" and p.area >= min_part_sqft
    ]
    return MultiPolygon(parts)


def _by_bearing(
    lot: BaseGeometry, env: BaseGeometry, edges: LotEdges, setbacks: Setbacks
) -> BaseGeometry:
    """``env`` less the ground 1005.02(L) keeps a building off, swept from
    the taxlot's own lines (:func:`flats.geom.bearing.bearing_cut`)."""
    if not setbacks.by_bearing or env.is_empty:
        return env
    from flats.geom.bearing import bearing_cut

    cut = bearing_cut(
        lot,
        edges.edges,
        north_ft=setbacks.north_ft,
        east_west_ft=setbacks.east_west_ft,
        street_credit_ft=setbacks.north_street_credit_ft,
        true_north=setbacks.true_north_deg,
    )
    return env if cut is None else env.difference(cut)


def _less(env: BaseGeometry, less: BaseGeometry | None) -> BaseGeometry:
    if less is None or less.is_empty or env.is_empty:
        return env
    return env.difference(less)


Segment = tuple[float, float, float, float]


def _pieces(edge: Edge, setbacks: Setbacks) -> list[tuple[Segment, float]]:
    """The stretches of one edge and the setback each takes.

    One piece, at :meth:`Setbacks.for_edge`, for every edge but an alley
    line whose cover s4 measured and whose code states its own number for
    that line: a side line's ``setback_alley_side_ft`` (FOLLOWUPS 3(e)), a
    rear line's :attr:`Setbacks.alley_rear_ft` (the rear setback's
    ``alley_at_rear`` variant; FOLLOWUPS 3, Steph's careful reading of
    2026-09-28). The alley number is a rule about "a lot line abutting an alley",
    and on a line the alley runs part of -- s4 classes the line an alley
    line on three rays of five -- the stretch across from the neighbour's
    yard abuts the neighbour. So the line is cut stretch by stretch: the
    alley's number where the cover's rays found it
    (:func:`flats.geom.alley.cover_stretches`), and elsewhere the larger of
    it and the ordinary side setback -- a waiver does not reach the
    neighbour, and a city that calls the alley line a rear lot line (the
    bridge's ``max(side, rear)``) is not relaxed by a stretch it did not
    measure. The rear line is cut the same way: the alley's rear where the
    rays found it, the larger of it and the ordinary rear elsewhere. Each
    piece's strip is closed by the half-disc round its end (:func:`_strip`),
    so an uncovered piece bites into the covered one as far as its own
    setback reaches: never larger than the legal envelope. A cover of ``""``
    (none on record) vouches for no stretch, and the whole line takes the
    larger number.
    """
    whole_edge: Segment = (edge.x1, edge.y1, edge.x2, edge.y2)
    d = setbacks.for_edge(edge)
    if not edge.alley or edge.cover is None:
        return [(whole_edge, d)]
    if edge.cls is EdgeClass.side and setbacks.alley_side_ft is not None:
        alley_ft, plain_ft = setbacks.alley_side_ft, setbacks.side_ft
    elif edge.cls is EdgeClass.rear and setbacks.alley_rear_ft is not None:
        alley_ft, plain_ft = setbacks.alley_rear_ft, setbacks.rear_ft
    else:
        return [(whole_edge, d)]
    from flats.geom.alley import cover_stretches

    ordinary = max(plain_ft, alley_ft)
    length = math.hypot(edge.x2 - edge.x1, edge.y2 - edge.y1)
    covered = cover_stretches(length, edge.cover)
    if covered == ((0.0, length),) or ordinary == alley_ft:
        return [(whole_edge, alley_ft)]
    if not covered or length <= 0:
        return [(whole_edge, ordinary)]
    ex, ey = (edge.x2 - edge.x1) / length, (edge.y2 - edge.y1) / length

    def seg(a: float, b: float) -> Segment:
        return (edge.x1 + a * ex, edge.y1 + a * ey, edge.x1 + b * ex, edge.y1 + b * ey)

    out: list[tuple[Segment, float]] = []
    at = 0.0
    for a, b in covered:
        if a > at:
            out.append((seg(at, a), ordinary))
        out.append((seg(a, b), alley_ft))
        at = b
    if at < length:
        out.append((seg(at, length), ordinary))
    return out


Ring = tuple[np.ndarray, bool, LineString]


def _rings(lot: BaseGeometry) -> list[Ring]:
    """Each ring of ``lot``: its vertices (the closing one dropped), whether
    the lot's ground lies to the left of the way the ring runs, and the ring."""
    out: list[Ring] = []
    for part in shapely.get_parts(lot):
        if part.geom_type != "Polygon" or part.is_empty:
            continue
        for k, ring in enumerate((part.exterior, *part.interiors)):
            xy = np.asarray(ring.coords, dtype=float)[:-1, :2]
            if len(xy) >= 3:
                out.append((xy, ring.is_ccw if k == 0 else not ring.is_ccw, ring))
    return out


def _bow(pts: np.ndarray, x1: float, y1: float, x2: float, y2: float, lot_on_left: bool) -> float:
    """The farthest of ``pts`` from the chord, counting those on the lot's
    side of it and those past its ends."""
    if not len(pts):
        return 0.0
    length = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    rx, ry = pts[:, 0] - x1, pts[:, 1] - y1
    along = rx * ux + ry * uy
    left = ux * ry - uy * rx
    at = np.clip(along, 0.0, length)
    off = np.hypot(rx - at * ux, ry - at * uy)
    inside = (left > 0) if lot_on_left else (left < 0)
    counted = np.where(inside | (along < 0) | (along > length), off, 0.0)
    return float(counted.max())


def _sag(rings: list[Ring], x1: float, y1: float, x2: float, y2: float) -> float:
    """How far, in feet, the lot's own line runs INSIDE the edge that stands
    for it (FOLLOWUPS 205).

    An edge is a chord of the simplified ring (or a stretch of one: s4 splits
    a line where the neighbour changes): the lot line between its two ends
    may bow up to the simplifying tolerance either way. Where it bows into
    the lot, a yard measured from the chord is that much short of the yard
    measured from the lot line (Portland 1S3E06BD -09500, a curved front:
    13.7 ft of a 15 ft front yard). The strip is widened by this figure, so
    no kept point is nearer the true line than the setback. A bow outward
    needs nothing: the chord is then the nearer of the two.

    The line is the shorter run of the ring between the edge's two ends, and
    the figure is the farthest of its vertices on the lot's side of the
    chord -- exact, since both are straight between vertices. Zero on an
    edge that is a lot line as drawn. The ends are the ring's own vertices
    where the edge ends on them; otherwise the nearest points of the ring,
    no farther off than a chord can lie. An edge that is not on the ring at
    all is not read: it takes :data:`SMOOTH_FT`, the most the line can stray.
    """
    if math.hypot(x2 - x1, y2 - y1) <= 0:
        return 0.0
    for xy, lot_on_left, _ring in rings:
        d1 = np.hypot(xy[:, 0] - x1, xy[:, 1] - y1)
        i = int(d1.argmin())
        if d1[i] > SNAP_FT:
            continue
        d2 = np.hypot(xy[:, 0] - x2, xy[:, 1] - y2)
        j = int(d2.argmin())
        if d2[j] > SNAP_FT or i == j:
            continue
        n = len(xy)
        ahead = [(i + k) % n for k in range(1, (j - i) % n)]  # i to j, the ring's way
        back = [(j + k) % n for k in range(1, (i - j) % n)]  # j to i, the ring's way
        if not ahead or not back:
            return 0.0  # the edge is one of the ring's own segments

        def run(idx: list[int], a: int, b: int, xy: np.ndarray = xy) -> float:
            return float(np.hypot(*np.diff(xy[[a, *idx, b]], axis=0).T).sum())

        # The lot is on the chord's left where the chord runs the ring's way
        # and the lot is on the ring's left.
        if run(ahead, i, j) <= run(back, j, i):
            return _bow(xy[ahead], x1, y1, x2, y2, lot_on_left)
        return _bow(xy[back], x1, y1, x2, y2, not lot_on_left)
    return _sag_between_vertices(rings, x1, y1, x2, y2)


def _sag_between_vertices(rings: list[Ring], x1: float, y1: float, x2: float, y2: float) -> float:
    """:func:`_sag` for an edge that ends between the ring's vertices."""
    from shapely.ops import substring

    reach = SMOOTH_FT + SNAP_FT
    p1, p2 = Point(x1, y1), Point(x2, y2)
    for _xy, lot_on_left, ring in rings:
        if ring.distance(p1) > reach or ring.distance(p2) > reach:
            continue
        s1, s2, total = ring.project(p1), ring.project(p2), ring.length
        lo, hi = min(s1, s2), max(s1, s2)
        if hi - lo <= 0:
            continue
        if hi - lo <= total - (hi - lo):
            pts = np.asarray(substring(ring, lo, hi).coords, dtype=float)[:, :2]
            with_ring = s1 < s2
        else:
            pts = np.vstack(
                [
                    np.asarray(substring(ring, hi, total).coords, dtype=float)[:, :2],
                    np.asarray(substring(ring, 0.0, lo).coords, dtype=float)[:, :2],
                ]
            )
            with_ring = s1 > s2
        return _bow(pts, x1, y1, x2, y2, lot_on_left == with_ring)
    return SMOOTH_FT


def _strip(x1: float, y1: float, x2: float, y2: float, d: float) -> Polygon:
    """Every point within ``d`` of the segment, and no more than a sag beyond.

    The band ``d`` either side of the segment, closed at each end by a
    half-disc of radius ``d`` round the endpoint, drawn with
    :data:`ARC_SPLITS` chords that touch the circle at their midpoints:
    the polygon holds the whole circle (never short of the setback) and sits
    inside the old square cap (never more than it took). A segment of no
    length is the disc.
    """
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    ux, uy = (dx / length, dy / length) if length > 0 else (1.0, 0.0)
    nx, ny = -uy, ux  # the left normal
    step = math.pi / ARC_SPLITS
    corner = d / math.cos(step / 2)

    def arc(cx: float, cy: float, sx: float, sy: float, fx: float, fy: float):
        # The half-disc from side s round through forward f to -s: a
        # tangent point, the chord corners, a tangent point.
        pts = [(cx + d * sx, cy + d * sy)]
        for i in range(ARC_SPLITS):
            t = (i + 0.5) * step
            c, si = math.cos(t), math.sin(t)
            pts.append((cx + corner * (c * sx + si * fx), cy + corner * (c * sy + si * fy)))
        pts.append((cx - d * sx, cy - d * sy))
        return pts

    return Polygon(arc(x2, y2, nx, ny, ux, uy) + arc(x1, y1, -nx, -ny, -ux, -uy))


def _farthest_rear_edges(edges: LotEdges) -> frozenset[int]:
    """Indices of rear edges whose midpoints are farthest from the front."""
    fronts = [
        LineString([(edge.x1, edge.y1), (edge.x2, edge.y2)])
        for edge in edges.edges
        if edge.cls is EdgeClass.front
    ]
    rears = [
        (i, edge)
        for i, edge in enumerate(edges.edges)
        if edge.cls is EdgeClass.rear
    ]
    if not fronts or not rears:
        return frozenset()
    front = shapely.union_all(fronts)
    distances = {
        i: front.distance(Point((edge.x1 + edge.x2) / 2, (edge.y1 + edge.y2) / 2))
        for i, edge in rears
    }
    farthest = max(distances.values())
    return frozenset(i for i, distance in distances.items() if math.isclose(distance, farthest))


#: Two side edges whose ends come this close are one side lot line.
SIDE_MEET_FT = 0.5


def side_lines(edges: LotEdges) -> tuple[frozenset[int], ...]:
    """The lot's side lot lines: its side-class edges, grouped where they
    meet end to end. Each group is the indexes into ``edges.edges`` of one
    line's edges; the groups are ordered by their first edge. A plain
    interior lot has two, one either side of the building."""

    def ends(i: int) -> tuple[tuple[float, float], tuple[float, float]]:
        e = edges.edges[i]
        return (e.x1, e.y1), (e.x2, e.y2)

    def meet(i: int, j: int) -> bool:
        return any(math.hypot(ax - bx, ay - by) <= SIDE_MEET_FT for ax, ay in ends(i) for bx, by in ends(j))

    lines: list[set[int]] = []
    for i, edge in enumerate(edges.edges):
        if edge.cls is not EdgeClass.side:
            continue
        joined = [line for line in lines if any(meet(i, j) for j in line)]
        lines = [line for line in lines if all(line is not other for other in joined)]
        lines.append({i}.union(*joined))
    return tuple(frozenset(line) for line in sorted(lines, key=min))


def _larger_side_edges(edges: LotEdges, setbacks: Setbacks) -> frozenset[int]:
    """The edges that take the larger of two unequal side yards
    (:attr:`Setbacks.side_larger_ft`): the chosen side lot line's where the
    lot's side lines fall in two and one was chosen, else every side edge."""
    if setbacks.side_larger_ft is None or setbacks.side_larger_ft <= setbacks.side_ft:
        return frozenset()
    lines = side_lines(edges)
    if setbacks.larger_side is not None and len(lines) == 2:
        return lines[setbacks.larger_side]
    return frozenset(i for i, e in enumerate(edges.edges) if e.cls is EdgeClass.side)


def buildable(
    lot: BaseGeometry,
    edges: LotEdges,
    setbacks: Setbacks,
    *,
    min_part_sqft: float = MIN_PART_SQFT,
    less: BaseGeometry | None = None,
) -> MultiPolygon:
    """The area of ``lot`` a building may occupy. May be empty.

    An empty envelope is a real answer — on a small lot deep setbacks can
    consume everything — and it flows through to a fit of zero rather than an
    error.

    ``less`` is ground taken off after the setbacks and before fragments are
    dropped: the overlays a city keeps building out of (a greenway, a
    wetland buffer), as quadfit's s5o records them per lot.
    """
    if lot is None or lot.is_empty:
        return MultiPolygon([])

    if edges.tier is Tier.corner and not any(
        e.cls is EdgeClass.street_side for e in edges.edges
    ):
        # No front named: every street edge takes the stricter standard.
        setbacks = setbacks.on_a_corner()

    use_strips = edges.tier in (Tier.clean, Tier.corner) and bool(edges.edges)
    far_rear = _farthest_rear_edges(edges) if setbacks.depth_rear_ft is not None else frozenset()
    if not use_strips:
        # Irregular, flag, or unclassifiable: shrink uniformly by the worst
        # setback. Conservative on purpose — see the module docstring.
        # A right-of-way strip (:attr:`Edge.dedication_ft`) is given up on top
        # of the largest yard, on the deepest street line.
        shrink = setbacks.largest_ft + max((e.dedication_ft for e in edges.edges), default=0.0)
        if far_rear:
            ordinary_largest = max(
                setbacks.front_ft,
                setbacks.side_ft,
                setbacks.rear_ft,
                setbacks.street_side_ft or 0.0,
                setbacks.alley_rear_ft or 0.0,
                setbacks.side_larger_ft or 0.0,
            )
            shrink = ordinary_largest + max(
                (e.dedication_ft for e in edges.edges), default=0.0
            )
            env = lot.buffer(-shrink) if shrink > 0 else lot
            strips = []
            for i in far_rear:
                edge = edges.edges[i]
                extra = max(0.0, setbacks.depth_rear_ft + edge.dedication_ft - shrink)
                if extra:
                    strips.append(
                        LineString([(edge.x1, edge.y1), (edge.x2, edge.y2)]).buffer(
                            extra, cap_style="square", join_style="mitre"
                        )
                    )
            if strips:
                env = env.difference(shapely.union_all(strips))
            env = _by_bearing(lot, env, edges, setbacks)
            return _clean(_less(env, less), min_part_sqft)
        env = lot.buffer(-shrink) if shrink > 0 else lot
        env = _by_bearing(lot, env, edges, setbacks)
        return _clean(_less(env, less), min_part_sqft)

    strips = []
    rings = _rings(lot)
    larger = _larger_side_edges(edges, setbacks)
    for i, edge in enumerate(edges.edges):
        pieces = (
            [((edge.x1, edge.y1, edge.x2, edge.y2), setbacks.for_far_rear_edge(edge))]
            if i in far_rear
            else _pieces(edge, setbacks)
        )
        if i in larger and setbacks.side_larger_ft is not None:
            # The larger of two unequal side yards, on every stretch of this
            # side lot line: an alley's number does not relax it.
            floor = setbacks.side_larger_ft + edge.dedication_ft
            pieces = [(seg, max(d, floor)) for seg, d in pieces]
        sag: float | None = None
        for (x1, y1, x2, y2), d in pieces:
            if d <= 0:
                continue
            if sag is None:
                # The whole edge's, on every stretch of it: the yard is
                # measured from the lot line, not from the chord (:func:`_sag`).
                sag = _sag(rings, edge.x1, edge.y1, edge.x2, edge.y2)
            strips.append(_strip(x1, y1, x2, y2, d + sag))
    env = lot.difference(shapely.union_all(strips)) if strips else lot
    env = _by_bearing(lot, env, edges, setbacks)
    return _clean(_less(env, less), min_part_sqft)
