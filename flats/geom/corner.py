"""Which street is the front of a corner lot, where the code says.

Until 2026-09-26 the screen named no front on a corner lot: every street edge
took the stricter of the front and street-side setback and both interior lines
took the rear, because geometry cannot say which street line is legally the
front (:mod:`flats.geom.envelope`). That is conservative both ways -- a missed
green, never a false one -- and on the 62,944 corner lots of run 26 it was the
reading 56,565 yellows rested on.

The codes do say. ``front_lot_line_corner`` (FOLLOWUPS 6, slice A) holds each
city's definition, and Steph ruled 2026-09-26 that it is followed where it
fixes the answer: *"Some cities allow developer choice, others have strict
standards. So we need to abide if Portland has guidance on which is front
and which is side."*

* ``shortest`` -- Portland 33.910, Oregon City 17.04.490, Wilsonville 4.001,
  West Linn 02, Wood Village 720.030, unincorporated Multnomah 39.2000: the
  street with the shorter lot LINE is the front. Only when the two are equal
  (within a foot, the platted "equal" of 33.910) does the applicant choose,
  and both are offered.
* ``owner`` / ``entrance`` -- the applicant's choice (or the door's, which
  the applicant places): both streets are offered, and the screen keeps the
  better answer (Steph's ruling of 2026-09-19, HUMAN_TODO 21).
* ``both`` (unincorporated Clackamas ZDO 202) -- every street line IS a front
  line and takes the front setback, which is the envelope already cut. Nothing
  to name.
* unread -- nothing to name either.

The line's length is the lot's extent along the street's bearing, corner to
corner, NOT the sum of that street's edges: quadfit's first corner run read
the sum and faced 738 lots the wrong way (a street at both ends summed past
the side, a jogged frontage's 30 ft step taken for a street; fcea6d57). Two
bearings closer than :data:`CORNER_MIN_DEG` are one street that bends, not a
corner (364c360e), and are left unnamed.

Naming the front renames the other lines: the second street's edges become
:attr:`~flats.geom.edges.EdgeClass.street_side`, and an interior line that
runs with the second street -- opposite it, beside the front -- is a SIDE
line, not a rear one. The interior line opposite the named front stays the
rear. A street edge that runs with neither street (a chord across the
corner) stays a front.

A lot with an alley edge is left unnamed: the alley is named rear or side
against either frontage (:func:`flats.geom.alley.alley_lines`), the rules
resolve the alley's setback on that name, and renaming the line under them
would cut an envelope the resolution did not describe.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Sequence

from flats.geom.edges import (
    BEARING_CLUSTER_TOL_DEG,
    PARALLEL_TOL_DEG,
    Edge,
    EdgeClass,
    LotEdges,
    Tier,
    bearing_deg,
    bearing_delta,
)

#: Two street bearings closer than this are one street that bends
#: (quadfit s6s ``CORNER_MIN_DEG``, 364c360e).
CORNER_MIN_DEG = 45.0
#: Two street lines within this of each other are equal, and the applicant
#: chooses between them (the platted "equal" of Portland 33.910).
EQUAL_LINE_FT = 1.0

#: ``front_lot_line_corner`` values that leave the choice to the applicant.
CHOICE = frozenset({"owner", "entrance"})


def two_streets(bearings: Sequence[float]) -> bool:
    """Whether the lot's two street directions are two streets, not one bending.

    ``bearings`` are s4's clustered street directions, longest frontage
    first. s4 splits a street at 20 degrees, so two directions between 20
    and :data:`CORNER_MIN_DEG` apart are either one street that bends or two
    that meet at a shallow angle, and geometry cannot say which. This is the
    ONE test for "two streets": naming a corner lot's front
    (:func:`is_corner`) and the ``corner_lot`` site fact
    (:func:`flats.ingest.quadfit.observed_facts`) both ask it.
    """
    return (
        len(bearings) >= 2
        and bearing_delta(float(bearings[0]), float(bearings[1])) >= CORNER_MIN_DEG
    )


#: Two groups of one street direction's front edges farther apart than this,
#: measured across the bearing, are the two ENDS of a through lot rather than
#: a jog in one frontage (quadfit s6s ``THROUGH_MIN_FT``: the 30 ft step of
#: 1S2E15BB-02800 is a jog; a lot is deeper).
THROUGH_MIN_FT = 40.0

#: s4's class letter for a street (frontage) edge in ``edges_json``.
STREET_CLASS = "F"


def through_lot(edges: Sequence[Sequence[object]], bearings: Sequence[float]) -> bool:
    """Whether a street runs along two opposite lines of the lot.

    ``edges`` is s4's ``edges_json`` decoded (``[x1, y1, x2, y2, cls]``) and
    ``bearings`` its clustered street directions. s4 clusters bearings mod
    180, so the two ends of a through lot are ONE direction and
    :func:`two_streets` cannot see them. The test is quadfit's
    (s6s ``_through_ends``): a direction's street edges, their midpoints
    projected across the bearing, split by a gap of at least
    :data:`THROUGH_MIN_FT` AND at least half the lot's extent across the
    bearing -- so a jog in one frontage, or a long edge on a street that
    bends, is never taken for a far end. Alley edges are not street edges
    (class ``A``): every code read says an alley is not frontage.
    """
    streets = [
        (float(e[0]), float(e[1]), float(e[2]), float(e[3]))
        for e in edges
        if e[4] == STREET_CLASS
    ]
    if len(streets) < 2:
        return False
    ends = [(float(e[0]), float(e[1]), float(e[2]), float(e[3])) for e in edges]
    corners = [pt for x1, y1, x2, y2 in ends for pt in ((x1, y1), (x2, y2))]
    for b in bearings:
        group = [
            s for s in streets
            if bearing_delta(bearing_deg(*s), float(b)) <= BEARING_CLUSTER_TOL_DEG
        ]
        if len(group) < 2:
            continue
        t = math.radians(float(b))
        nx, ny = -math.sin(t), math.cos(t)
        across = sorted((x1 + x2) / 2.0 * nx + (y1 + y2) / 2.0 * ny for x1, y1, x2, y2 in group)
        gap = max(hi - lo for lo, hi in zip(across, across[1:]))
        proj = [x * nx + y * ny for x, y in corners]
        if gap >= max(THROUGH_MIN_FT, 0.5 * (max(proj) - min(proj))):
            return True
    return False


def is_corner(edges: LotEdges | None) -> bool:
    """Two streets on the lot that really are two: a corner, not a bend."""
    return (
        edges is not None
        and edges.tier is Tier.corner
        and two_streets(edges.front_bearings)
    )


def line_length(edges: LotEdges, bearing: float) -> float:
    """The lot's extent along ``bearing``: the length of the lot line at it.

    The spread of every edge end projected onto the direction -- on a simple
    shape, the line that runs that way, corner to corner, whether or not a
    street abuts all of it.
    """
    t =math.radians(bearing)
    proj = [
        x * math.cos(t) + y * math.sin(t)
        for e in edges.edges
        for x, y in ((e.x1, e.y1), (e.x2, e.y2))
    ]
    return max(proj) - min(proj) if proj else 0.0


def front_bearings(edges: LotEdges | None, rule: object) -> tuple[float, ...]:
    """The street bearings this lot may be laid out to front, per the code.

    Empty where no front is to be named: not a corner, a street that bends,
    a lot on an alley, or a rule that names none (``both``, unread).
    """
    if not is_corner(edges) or rule not in CHOICE | {"shortest"}:
        return ()
    assert edges is not None
    if any(e.alley for e in edges.edges):
        return ()
    streets = tuple(float(b) for b in edges.front_bearings[:2])
    if rule in CHOICE:
        return streets
    lengths = [line_length(edges, b) for b in streets]
    shortest = min(lengths)
    return tuple(b for b, n in zip(streets, lengths) if n <= shortest + EQUAL_LINE_FT)


def name_front(edges: LotEdges, front: float) -> LotEdges:
    """The same edges with ``front`` named as the front street.

    ``front`` is one of ``edges.front_bearings``. The other street's edges
    become street sides, and the interior lines that run with the other
    street become sides; everything else keeps its class.
    """
    other = next(
        (float(b) for b in edges.front_bearings if bearing_delta(float(b), front) >= CORNER_MIN_DEG),
        None,
    )
    if other is None:
        return edges

    def renamed(edge: Edge) -> Edge:
        if edge.cls is EdgeClass.front:
            if bearing_delta(edge.bearing_deg, front) <= BEARING_CLUSTER_TOL_DEG:
                return edge
            if bearing_delta(edge.bearing_deg, other) <= BEARING_CLUSTER_TOL_DEG:
                return dataclasses.replace(edge, cls=EdgeClass.street_side)
            return edge
        if edge.cls is EdgeClass.rear and not edge.alley:
            if bearing_delta(edge.bearing_deg, front) <= PARALLEL_TOL_DEG:
                return edge
            if bearing_delta(edge.bearing_deg, other) <= PARALLEL_TOL_DEG:
                return dataclasses.replace(edge, cls=EdgeClass.side)
        return edge

    return dataclasses.replace(edges, edges=tuple(renamed(e) for e in edges.edges))
