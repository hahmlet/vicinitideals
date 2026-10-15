"""The parking's share of each street frontage, measured on the drawn plan.

Wilsonville 4.113(.14)D.3, Hillsboro 12.50.715 C.1, Clackamas ZDO 845.02(D)
and Beaverton 60.05.60.2 S11 print the model code's cap: garages, parking
and maneuvering area may take at most half of a street frontage. Steph
2026-10-14 (FOLLOWUPS 80(a)): "I read this as 'any' street frontage. So
front, back, side streets if they exist." So the cap is read on every street
the lot has, one street at a time:

    for each street (:func:`street_chains`: the lot's front and street-side
    lines, run by run and split where the street turns a corner)
      walk the line a foot at a time and look straight into the lot
      a foot counts where the first thing seen is the court's stalls or aisle
        (:attr:`flats.fit.draw.Drawing.rows`, never the lane that reaches
        them -- the driveway is not parking), and that parking stands nearer
        the street than the building's far wall: a court BEHIND the building,
        seen from the street the building faces, is not reached
      the street's share is the feet counted over the line's length

and the worst street is the answer, with the feet it faces on that street
(:func:`street_runs`) for a cap stated in feet as well as a share -- Oregon
City 17.16.060.D.1, "forty feet wide or fifty percent of the lot frontage,
whichever is less". Oregon City, Fairview 19.30.040(E)(2), Troutdale
8.120.C.4.d and Sandy 17.90.160 F read the same cap (FOLLOWUPS 84).

A rear court on a lot with one street is behind the building and counts
nothing; on a corner lot it faces the side street across its depth; on a
through lot it faces the far street across its width.

Pure geometry on the lot's own coordinates (EPSG:2913, feet). Overlays, the
planted strip and the lane are not obstacles to the look: a strip of
landscaping between the street and a court leaves the court facing the
street.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np
import shapely
from shapely.geometry.base import BaseGeometry

from flats.geom.corner import STREET_CLASS, through_lot, two_streets
from flats.geom.edges import Edge, EdgeClass, LotEdges, bearing_delta

#: How far apart the looks into the lot are, feet. A foot is finer than any
#: stall, and a 300 ft frontage is 300 looks.
STEP_FT = 1.0

_STREET = (EdgeClass.front, EdgeClass.street_side)


def street_chains(edges: LotEdges) -> tuple[tuple[Edge, ...], ...]:
    """The lot's streets, each the run of street lines along it.

    Street lines are the front and street-side edges that are not alleys.
    Lines next to one another around the lot are one street until the street
    turns: each line goes to the nearer of the lot's (at most two) street
    directions, and a change of direction starts another street. Lines apart
    -- the two ends of a through lot -- are two streets. Two directions closer
    than the corner test's angle (:func:`flats.geom.corner.two_streets`, the
    ONE test for "two streets") are one street that bends, or a cul-de-sac
    bulb, and stay one street. So are runs apart along one street direction
    that are not a through lot's two ends (:func:`flats.geom.corner.through_lot`,
    the test the ``through_lot`` site fact asks): a jog or a notch in one
    frontage.
    """
    ring = edges.edges
    n = len(ring)
    bearings = [float(b) for b in edges.front_bearings[:2]]
    if not two_streets(bearings):
        bearings = bearings[:1]

    def street_of(e: Edge) -> int:
        if len(bearings) < 2:
            return 0
        return min(range(len(bearings)), key=lambda k: bearing_delta(e.bearing_deg, bearings[k]))

    on = [ring[i].cls in _STREET and not ring[i].alley for i in range(n)]
    if not any(on):
        return ()
    # Start the walk just after a break, so a street that wraps past the
    # ring's first line is not cut in two.
    start = next(
        (
            i
            for i in range(n)
            if not on[i - 1] or (on[i] and street_of(ring[i - 1]) != street_of(ring[i]))
        ),
        0,
    )
    chains: list[list[Edge]] = []
    last: int | None = None
    for k in range(n):
        i = (start + k) % n
        if not on[i]:
            last = None
            continue
        here = street_of(ring[i])
        if last is None or here != last:
            chains.append([])
        chains[-1].append(ring[i])
        last = here
    if len(chains) > 1 and len(bearings) < 2 and not through_lot(
        [(e.x1, e.y1, e.x2, e.y2, STREET_CLASS if on[i] else "") for i, e in enumerate(ring)],
        edges.front_bearings,
    ):
        return (tuple(e for c in chains for e in c),)
    return tuple(tuple(c) for c in chains)


def _looks(
    lot: BaseGeometry, chain: Sequence[Edge], reach_ft: float
) -> tuple[np.ndarray, np.ndarray, float]:
    """The look points along ``chain``, the looks themselves (lines straight
    into the lot, ``reach_ft`` long), and the feet each stands for."""
    starts: list[tuple[float, float]] = []
    ends: list[tuple[float, float]] = []
    feet: list[float] = []
    for e in chain:
        dx, dy = e.x2 - e.x1, e.y2 - e.y1
        length = math.hypot(dx, dy)
        if length <= 0:
            continue
        ux, uy = dx / length, dy / length
        nx, ny = -uy, ux
        mx, my = (e.x1 + e.x2) / 2, (e.y1 + e.y2) / 2
        if not lot.contains(shapely.Point(mx + nx * 0.5, my + ny * 0.5)):
            nx, ny = -nx, -ny
        count = max(1, math.ceil(length / STEP_FT))
        piece = length / count
        for j in range(count):
            t = (j + 0.5) * piece
            px, py = e.x1 + ux * t, e.y1 + uy * t
            starts.append((px, py))
            ends.append((px + nx * reach_ft, py + ny * reach_ft))
            feet.append(piece)
    if not starts:
        return np.empty(0, dtype=object), np.empty(0, dtype=object), 0.0
    pts = shapely.points(np.asarray(starts))
    lines = shapely.linestrings(
        np.stack([np.asarray(starts), np.asarray(ends)], axis=1)
    )
    return pts, lines, float(np.mean(feet))


def _first_seen(pts: np.ndarray, lines: np.ndarray, shape: BaseGeometry | None) -> np.ndarray:
    """How far each look goes before it meets ``shape``; infinity where it
    never does."""
    if shape is None or shape.is_empty:
        return np.full(len(pts), np.inf)
    hit = shapely.intersection(lines, shape)
    got = shapely.distance(pts, hit)
    return np.where(np.isnan(got) | shapely.is_empty(hit), np.inf, got)


def street_shares(
    lot: BaseGeometry,
    edges: LotEdges,
    rows: BaseGeometry,
    building: BaseGeometry,
) -> tuple[float, ...]:
    """Each street's share of its frontage that the parking ``rows`` face,
    in percent, in :func:`street_chains` order."""
    return tuple(pct for pct, _ in street_runs(lot, edges, rows, building))


def street_runs(
    lot: BaseGeometry,
    edges: LotEdges,
    rows: BaseGeometry,
    building: BaseGeometry,
) -> tuple[tuple[float, float], ...]:
    """Each street's ``(share in percent, feet)`` of frontage that the
    parking ``rows`` face, in :func:`street_chains` order. The feet are what
    a cap in feet reads (Oregon City 17.16.060.D.1, "forty feet wide or fifty
    percent of the lot frontage, whichever is less"); the share is the same
    run over the street's length."""
    minx, miny, maxx, maxy = lot.bounds
    reach = math.hypot(maxx - minx, maxy - miny) + 1.0
    corners = shapely.points(np.asarray(shapely.get_coordinates(building)))
    out: list[tuple[float, float]] = []
    for chain in street_chains(edges):
        frontage = sum(math.hypot(e.x2 - e.x1, e.y2 - e.y1) for e in chain)
        if frontage <= 0:
            continue
        pts, lines, piece = _looks(lot, chain, reach)
        if not len(pts):
            continue
        street = shapely.multilinestrings([[(e.x1, e.y1), (e.x2, e.y2)] for e in chain])
        far_wall = float(np.max(shapely.distance(corners, street))) if len(corners) else 0.0
        parked = _first_seen(pts, lines, rows)
        built = _first_seen(pts, lines, building)
        seen = (parked < built) & (parked < far_wall)
        run = min(frontage, float(seen.sum()) * piece)
        out.append((100.0 * run / frontage, run))
    return tuple(out)


def parking_share_pct(
    lot: BaseGeometry,
    edges: LotEdges,
    rows: Sequence[BaseGeometry],
    building: BaseGeometry | None,
) -> float | None:
    """The parking's share of the worst street frontage, percent, at the
    best of the ways to stand the row (``rows``, one shape each); None
    where there is no building or row to measure, or no street.
    """
    got = parking_share(lot, edges, rows, building)
    return None if got is None else got[0]


def parking_share(
    lot: BaseGeometry,
    edges: LotEdges,
    rows: Sequence[BaseGeometry],
    building: BaseGeometry | None,
) -> tuple[float, float] | None:
    """``(percent, feet)``: the worst street's share of frontage and the
    longest run of frontage in feet that the parking faces, both read off
    the SAME way of standing the row -- the one with the smallest worst
    share (the feet break a tie). Pairing the share of one row with the feet
    of another would pass a plan no single drawing passes. None where
    :func:`parking_share_pct` is None.
    """
    if building is None or building.is_empty or not rows:
        return None
    best: tuple[float, float] | None = None
    for row in rows:
        if row is None or row.is_empty:
            continue
        runs = street_runs(lot, edges, row.intersection(lot), building)
        if not runs:
            return None
        worst = (max(pct for pct, _ in runs), max(ft for _, ft in runs))
        best = worst if best is None else min(best, worst)
    return best


__all__ = [
    "STEP_FT",
    "parking_share",
    "parking_share_pct",
    "street_chains",
    "street_runs",
    "street_shares",
]
