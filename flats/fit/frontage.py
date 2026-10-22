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

from flats.geom.corner import STREET_CLASS, THROUGH_MIN_FT, through_lot, two_streets
from flats.geom.edges import BEARING_CLUSTER_TOL_DEG, Edge, EdgeClass, LotEdges, bearing_delta

#: How far apart the looks into the lot are, feet. A foot is finer than any
#: stall, and a 300 ft frontage is 300 looks.
STEP_FT = 1.0

_STREET = (EdgeClass.front, EdgeClass.street_side)


def street_chains(edges: LotEdges) -> tuple[tuple[Edge, ...], ...]:
    """The lot's streets, each the whole run of street line along it.

    Street lines are the front and street-side edges that are not alleys.
    Lines next to one another around the lot are one street until the street
    turns a corner. Lines apart -- the two ends of a through lot -- are two
    streets. Two directions closer than the corner test's angle
    (:func:`flats.geom.corner.two_streets`, the ONE test for "two streets")
    are one street that bends, or a cul-de-sac bulb, and stay one street. So
    are runs apart along one street direction that are not a through lot's
    two ends (:func:`flats.geom.corner.through_lot`, the test the
    ``through_lot`` site fact asks): a jog or a notch in one frontage.

    On a lot with two street directions the run is cut where the street
    turns, and ONLY there (:func:`_streets_of_run`). A county lot line
    follows the street in pieces: a rounded corner is drawn as short chords
    whose directions lie between the two streets, and a frontage steps in
    and out. Cut at every change of direction, those pieces became streets
    of their own -- a 6 ft "street" on a lot with 300 ft of frontage -- and
    a cap on a share of one street's line read against them (FOLLOWUPS 84
    phase 3, the bound of 2026-10-15: about 75 false reds). A piece is merged
    into the street it belongs to, never dropped: a lot whose side street
    really is 30 ft long keeps a 30 ft street.
    """
    ring = edges.edges
    n = len(ring)
    bearings = [float(b) for b in edges.front_bearings[:2]]
    if not two_streets(bearings):
        bearings = bearings[:1]
    on = [ring[i].cls in _STREET and not ring[i].alley for i in range(n)]
    if not any(on):
        return ()
    chains: list[list[int]] = []
    for run in _runs(on):
        chains.extend(_streets_of_run(ring, run, bearings))
    if len(chains) > 1 and len(bearings) < 2 and not through_lot(
        [(e.x1, e.y1, e.x2, e.y2, STREET_CLASS if on[i] else "") for i, e in enumerate(ring)],
        edges.front_bearings,
    ):
        return (tuple(ring[i] for c in chains for i in c),)
    return tuple(tuple(ring[i] for i in c) for c in chains)


def _runs(on: Sequence[bool]) -> list[list[int]]:
    """The runs of street lines next to one another around the ring, as
    indices. The walk starts just after a break, so a street that wraps past
    the ring's first line is not cut in two."""
    n = len(on)
    start = next((i for i in range(n) if on[i] and not on[i - 1]), 0)
    runs: list[list[int]] = []
    open_run = False
    for k in range(n):
        i = (start + k) % n
        if not on[i]:
            open_run = False
            continue
        if not open_run:
            runs.append([])
            open_run = True
        runs[-1].append(i)
    return runs


def _closes(ring: Sequence[Edge], run: list[int]) -> bool:
    """Whether ``run`` is every line of the ring: no break to start it."""
    return len(run) == len(ring)


def _streets_of_run(
    ring: Sequence[Edge], run: list[int], bearings: Sequence[float]
) -> list[list[int]]:
    """One run of street lines cut into its streets.

    With one street direction the run is one street. With two (a corner):

    1. Each piece takes the street direction it lies along, within s4's own
       20 degrees (:data:`flats.geom.edges.BEARING_CLUSTER_TOL_DEG`); a
       piece along neither -- a chord of a rounded corner -- takes none yet.
    2. Pieces of one direction next to one another are one stretch.
    3. A stretch between two stretches of one direction, where the line goes
       on the SAME way along that street after it, is a step in that one
       frontage and is merged with both: a piece along neither direction, or
       one along the other direction shorter than a lot is deep
       (:data:`flats.geom.corner.THROUGH_MIN_FT`, the jog the through-lot
       test allows). Where the line comes back the other way, the lot wraps
       round a block end and the middle is a street of its own.
    4. What still has no direction is a rounded corner. Between stretches
       of the two streets it is cut where its turn crosses from one
       street's direction to the other's, each street taking the chords
       nearer it; beside one street only, it joins that street whole.
    """
    if len(bearings) < 2:
        return [list(run)]

    def label(e: Edge) -> int | None:
        k = min(range(2), key=lambda j: bearing_delta(e.bearing_deg, bearings[j]))
        return k if bearing_delta(e.bearing_deg, bearings[k]) <= BEARING_CLUSTER_TOL_DEG else None

    def length(g: list[int]) -> float:
        return sum(ring[i].length_ft for i in g)

    def heading(g: list[int]) -> tuple[float, float]:
        return (
            sum(ring[i].x2 - ring[i].x1 for i in g),
            sum(ring[i].y2 - ring[i].y1 for i in g),
        )

    groups: list[tuple[int | None, list[int]]] = []
    for i in run:
        here = label(ring[i])
        if groups and groups[-1][0] == here:
            groups[-1][1].append(i)
        else:
            groups.append((here, [i]))
    # A run round the whole lot (streets on every side) closes on itself.
    if len(groups) > 1 and groups[0][0] == groups[-1][0] and _closes(ring, run):
        last = groups.pop()
        groups[0] = (last[0], last[1] + groups[0][1])

    merged = True
    while merged:
        merged = False
        for j in range(1, len(groups) - 1):
            (a, ga), (m, gm), (b, gb) = groups[j - 1], groups[j], groups[j + 1]
            if a is None or a != b or m == a:
                continue
            if m is not None and length(gm) >= THROUGH_MIN_FT:
                continue
            (ax, ay), (bx, by) = heading(ga), heading(gb)
            if ax * bx + ay * by <= 0.0:
                continue
            groups[j - 1 : j + 2] = [(a, ga + gm + gb)]
            merged = True
            break

    def lean(g: list[int], k: int) -> float:
        total = length(g) or 1.0
        return sum(ring[i].length_ft * bearing_delta(ring[i].bearing_deg, bearings[k]) for i in g) / total

    out: list[tuple[int | None, list[int]]] = []
    for j, (k, g) in enumerate(groups):
        if k is not None:
            out.append((k, list(g)))
    if not out:
        return [list(run)]
    for j, (k, g) in enumerate(groups):
        if k is not None:
            continue
        before = next((groups[p] for p in range(j - 1, -1, -1) if groups[p][0] is not None), None)
        after = next((groups[p] for p in range(j + 1, len(groups)) if groups[p][0] is not None), None)
        near = [h for h in (before, after) if h is not None]
        if len(near) == 2 and near[0][0] != near[1][0]:
            # A rounded corner between the two streets: its chords turn from
            # one street's direction to the other's, so it is cut where the
            # turn crosses over -- the chords nearer the first street go to
            # it, the rest to the second. Given whole to either street, an
            # arc of 80 ft made the other street 80 ft shorter than it is
            # (Beaverton 1S121BA00807, 84 ft read as 43).
            ka, kb = near[0][0], near[1][0]

            def cost(c: int) -> float:
                return sum(
                    ring[i].length_ft * bearing_delta(ring[i].bearing_deg, bearings[ka if p < c else kb])  # type: ignore[index]
                    for p, i in enumerate(g)
                )

            cut = min(range(len(g) + 1), key=cost)
            pieces = [(near[0], g[:cut]), (near[1], g[cut:])]
        else:
            host = min(near, key=lambda h: lean(g, h[0]))  # type: ignore[arg-type]
            pieces = [(host, g)]
        for host, piece in pieces:
            if piece:
                target = next(o for o in out if o[1][0] == host[1][0])
                target[1].extend(piece)
    # Keep each street's lines in the ring's order.
    order = {i: p for p, i in enumerate(run)}
    return [sorted(g, key=order.__getitem__) for _, g in out]


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


def along(chain: Sequence[Edge], bearing: float) -> bool:
    """Whether a street runs along ``bearing``: more of its line lies within
    s4's 20 degrees of that direction than off it."""
    on = sum(e.length_ft for e in chain if bearing_delta(e.bearing_deg, bearing) <= BEARING_CLUSTER_TOL_DEG)
    return on > 0.5 * sum(e.length_ft for e in chain)


def street_runs(
    lot: BaseGeometry,
    edges: LotEdges,
    rows: BaseGeometry,
    building: BaseGeometry,
    *,
    front_deg: float | None = None,
) -> tuple[tuple[float, float], ...]:
    """Each street's ``(share in percent, feet)`` of frontage that the
    parking ``rows`` face, in :func:`street_chains` order. The feet are what
    a cap in feet reads (Oregon City 17.16.060.D.1, "forty feet wide or fifty
    percent of the lot frontage, whichever is less"); the share is the same
    run over the street's length.

    ``front_deg`` keeps only the streets along the named front (both ends of
    a through lot): a cap on parking "in the front yard" where the code names
    one front (``parking_area_frontage_front_yard``, Oregon City 17.16.060.D
    with 17.04.490 and 17.04.1515). None reads every street."""
    minx, miny, maxx, maxy = lot.bounds
    reach = math.hypot(maxx - minx, maxy - miny) + 1.0
    corners = shapely.points(np.asarray(shapely.get_coordinates(building)))
    out: list[tuple[float, float]] = []
    for chain in street_chains(edges):
        if front_deg is not None and not along(chain, front_deg):
            continue
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
    *,
    front_deg: float | None = None,
) -> tuple[float, float] | None:
    """``(percent, feet)``: the worst street's share of frontage and the
    longest run of frontage in feet that the parking faces, both read off
    the SAME way of standing the row -- the one with the smallest worst
    share (the feet break a tie). Pairing the share of one row with the feet
    of another would pass a plan no single drawing passes. None where
    :func:`parking_share_pct` is None. ``front_deg`` as :func:`street_runs`
    reads it; a plan that faces none of the front streets is ``(0, 0)``.
    """
    if building is None or building.is_empty or not rows:
        return None
    best: tuple[float, float] | None = None
    for row in rows:
        if row is None or row.is_empty:
            continue
        runs = street_runs(lot, edges, row.intersection(lot), building, front_deg=front_deg)
        if not runs:
            if front_deg is not None and street_chains(edges):
                runs = ((0.0, 0.0),)
            else:
                return None
        worst = (max(pct for pct, _ in runs), max(ft for _, ft in runs))
        best = worst if best is None else min(best, worst)
    return best


#: How near the street line the lane must be seen for that foot of frontage
#: to be the driveway crossing it, feet.
DRIVE_AT_LINE_FT = 1.0

#: Slack on the band's far edge, feet: a building drawn on the maximum
#: setback line is inside it.
BAND_TOL_FT = 0.5


def building_runs(
    lot: BaseGeometry,
    edges: LotEdges,
    building: BaseGeometry,
    band_ft: float,
    *,
    lane: BaseGeometry | None = None,
) -> tuple[tuple[float, float], ...]:
    """Each street's ``(share in percent, net frontage in feet)`` that the
    BUILDING occupies within ``band_ft`` of the street line, in
    :func:`street_chains` order (FOLLOWUPS 109): the feet of street line from
    which the first thing seen straight into the lot is the building, no
    further than the maximum setback -- "the length of the building present
    between the minimum and maximum front setback" (Gresham 7.0420(J)(1)),
    "occupied by a building located no further than the maximum 20-foot
    setback" (Washington County 392-8). The minimum setback holds already:
    the building is drawn inside the yards.

    ``lane`` given, the feet where the lane is seen at the street line come
    off that street's frontage before the share is taken (Beaverton
    60.05.15.6.A.4.a, 70.20.05.4 S1.g.I: the driveway's width is subtracted).
    """
    minx, miny, maxx, maxy = lot.bounds
    reach = math.hypot(maxx - minx, maxy - miny) + 1.0
    out: list[tuple[float, float]] = []
    for chain in street_chains(edges):
        frontage = sum(math.hypot(e.x2 - e.x1, e.y2 - e.y1) for e in chain)
        if frontage <= 0:
            continue
        pts, lines, piece = _looks(lot, chain, reach)
        if not len(pts):
            continue
        built = _first_seen(pts, lines, building)
        held = built <= band_ft + BAND_TOL_FT
        net = frontage
        if lane is not None and not lane.is_empty:
            drive = _first_seen(pts, lines, lane)
            crossing = (drive <= DRIVE_AT_LINE_FT) & (drive < built)
            net = max(frontage - float(crossing.sum()) * piece, 0.0)
        run = min(net, float(held.sum()) * piece)
        out.append((100.0 * run / net if net > 0 else 100.0, net))
    return tuple(out)


__all__ = [
    "BAND_TOL_FT",
    "DRIVE_AT_LINE_FT",
    "STEP_FT",
    "along",
    "building_runs",
    "parking_share",
    "parking_share_pct",
    "street_chains",
    "street_runs",
    "street_shares",
]
