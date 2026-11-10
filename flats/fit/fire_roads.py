"""Which stretches of street a fire truck can stand on (FOLLOWUPS 168).

:mod:`flats.fit.fire` measures the hose from the nearest street centreline a
truck may use, and until 2026-11-09 every mapped street of a truck class was
one. Two kinds of street are not, by the fire code's own words:

* a street too narrow for the truck. "Fire apparatus access roads shall have
  an unobstructed driving surface width of not less than 20 feet" (OFC
  503.2.1, ``or/ofc.2022.applications-guide.txt#L167-L169``; the 12-foot
  surface the note allows for three dwellings or fewer still needs 20 feet
  unobstructed, L170-L171). The width measured here is the gap in the taxlot
  fabric between the PRIVATE lots either side of the centreline -- the
  right-of-way, which is a CEILING on the driving surface, never the surface
  itself. A gap under :data:`MIN_WIDTH_FT` proves the street too narrow; a
  gap at or over it says nothing about the pavement, and such a street keeps
  the reading it had (Steph's brief, 2026-11-09).
* a dead end longer than 150 feet with no turnaround. "Dead end fire
  apparatus access roads more than 150 feet in length shall be provided
  with an approved turnaround" (OFC 503.2.5, L137-L139), and "An approved
  turnaround is required if the remaining distance to an approved
  intersecting roadway, as measured along the fire apparatus access road, is
  greater than 150 feet" (OFC 503.1.1, L134). So without one the truck goes
  no farther than :data:`DEAD_END_FT` from the last intersection. A
  turnaround is taken as absent only where the right-of-way at the end
  CANNOT hold one (:func:`_room_to_turn`); a dead end the fabric does not
  close (the edge of the map, open land) keeps the reading it had.

Portland's own rule is looser (City Code 31.30.010.B: a dead end "more than
300 feet in length" must turn the truck "within 150 feet of the closed
end"); the state figure is the stricter and is the one held.

Where a truck cannot stand, it stands at the last point it can reach and
the hose walks from there along the street's centreline (:func:`build`'s
``walk``): a route that exists, inside the right-of-way, so a lot it still
clears is cleared and a lot it fails is failed by a real distance.

:func:`build` reads the street file and the fabric once for a run and
writes the pieces (:func:`write`); each screening process reads them back
(:func:`load`) as :mod:`flats.fit.fire` takes them.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import substring

#: OFC 503.2.1: the narrowest unobstructed width of a fire apparatus road
#: (``or/ofc.2022.applications-guide.txt#L167-L169``).
MIN_WIDTH_FT = 20.0
#: OFC 503.2.5 and 503.1.1: the farthest a truck may go from an intersecting
#: road with no turnaround (L134, L137-L139).
DEAD_END_FT = 150.0
#: OFC 503.2.4 / D103.3: the outside turning radius of a 20-foot road
#: (L198-L199). A dead end whose right-of-way leaves less clear room than
#: this round its end, and no room for a hammerhead either
#: (:data:`HAMMER_ARM_FT`), cannot hold a turnaround.
TURN_RADIUS_FT = 48.0
#: Half a hammerhead's cross-bar: D103.4's 120-foot hammerhead is 60 feet
#: either side of the road, and its alternative 60 feet to one side. Clear
#: right-of-way this far to either side, square to the road near its end, is
#: room for one.
HAMMER_ARM_FT = 60.0
#: How far back from the end the hammerhead's bar is looked for.
HAMMER_BACK_FT = (0.0, 10.0, 20.0, 30.0)
#: How far back from a dead end a bulb's middle is looked for.
BULB_REACH_FT = 60.0
#: Where a dead end's own half-width is read, back from the end.
HALF_BACK_FT = 80.0
#: A dead end whose clear room widens this much over its own half-width
#: has a bulb. Measured on the 6,593 dead ends past 150 ft in the three
#: counties (RLIS 2026-11-04): the widening is bimodal, 3,329 under 5 ft
#: (a street that stops) and 2,913 at 10 ft or more (cul-de-sacs, most
#: 15-30 ft), 351 between.
BULB_FT = 10.0
#: Under this, the right-of-way does not widen at the end at all.
JOG_FT = 5.0
#: How often a centreline is measured across.
STATION_FT = 10.0
#: A width is read only where both sides find private land within this.
RAY_FT = 60.0
#: A narrow stretch must hold over this many stations in a row (10 ft at
#: :data:`STATION_FT`): one station under the width is a lot corner drawn a
#: foot into the street as often as a pinch.
NARROW_RUN = 2
#: A station this near a private lot is ON one -- a private road on a tract,
#: or a centreline drawn over a lot line -- and the fabric says nothing of
#: its width there.
ON_LOT_FT = 0.5
#: Endpoints this close are one node.
SNAP_FT = 1.0
#: A connected stretch of truck road that touches no other road class and is
#: shorter than this is cut off from the network (beyond a narrow pinch).
ISLAND_FT = 10_000.0
#: Classes that join a street to the outside world: highway and arterials
#: (RLIS TYPE 1200-1450). A component holding none of them and shorter than
#: :data:`ISLAND_FT` is cut off.
TRUNK_TYPES: frozenset[int] = frozenset({1200, 1300, 1400, 1450})
#: How far ahead of a dead end the fabric must hold a lot for the end to be
#: read as closed: past the map's edge, or into open land, the street may go
#: on.
CLOSED_AHEAD_FT = 100.0


@dataclass(frozen=True)
class Piece:
    """A stretch of truck road: where the truck may ``stand``, or, where it
    may not, how far the hose walks from each end to where it can
    (``walk0`` from the first coordinate, ``walk1`` from the last; infinite
    where nothing reaches)."""

    geom: LineString
    stand: bool
    walk0: float = 0.0
    walk1: float = 0.0
    why: str = ""


def _node(xy: Sequence[float]) -> tuple[int, int]:
    return (round(xy[0] / SNAP_FT), round(xy[1] / SNAP_FT))


def _stations(line: LineString) -> np.ndarray:
    n = max(1, int(line.length // STATION_FT))
    return np.linspace(0.0, line.length, n + 1)


def _normals(line: LineString, at: np.ndarray) -> np.ndarray:
    """Unit normals to ``line`` at the distances ``at``."""
    a = shapely.line_interpolate_point(line, np.maximum(at - 1.0, 0.0))
    b = shapely.line_interpolate_point(line, np.minimum(at + 1.0, line.length))
    d = shapely.get_coordinates(b) - shapely.get_coordinates(a)
    norm = np.hypot(d[:, 0], d[:, 1])
    norm[norm == 0] = 1.0
    return np.stack([-d[:, 1] / norm, d[:, 0] / norm], axis=1)


def _first_hit(
    origins: np.ndarray, dirs: np.ndarray, reach: float, tree: shapely.STRtree, lots: np.ndarray
) -> np.ndarray:
    """How far along each ray (origin, unit dir, ``reach``) the first lot of
    ``tree`` is entered; infinite where none is."""
    out = np.full(len(origins), math.inf)
    if not len(origins):
        return out
    rays = shapely.linestrings(np.stack([origins, origins + dirs * reach], axis=1))
    ri, li = tree.query(rays, predicate="intersects")
    if not len(ri):
        return out
    hit = shapely.intersection(rays[ri], lots[li])
    d = shapely.distance(shapely.points(origins[ri]), hit)
    np.minimum.at(out, ri, np.where(np.isfinite(d), d, math.inf))
    return out


def narrow_spans(
    line: LineString, tree: shapely.STRtree, lots: np.ndarray
) -> list[tuple[float, float]]:
    """The stretches of ``line`` (start, end distances along it) whose gap
    between the private lots either side is under :data:`MIN_WIDTH_FT`.

    Only a station with private land within half that width is measured
    (the gap is the two sides' sum, so one of them must be under half); one
    standing on a lot (:data:`ON_LOT_FT`), or with no lot within
    :data:`RAY_FT` on a side, is unmeasured and read as wide."""
    at = _stations(line)
    pts = shapely.line_interpolate_point(line, at)
    near, _ = tree.query(pts, predicate="dwithin", distance=MIN_WIDTH_FT / 2.0)
    if not len(near):
        return []
    cand = np.unique(near)
    on, _ = tree.query(pts[cand], predicate="dwithin", distance=ON_LOT_FT)
    cand = np.setdiff1d(cand, cand[np.unique(on)]) if len(on) else cand
    if not len(cand):
        return []
    xy = shapely.get_coordinates(pts[cand])
    nrm = _normals(line, at[cand])
    left = _first_hit(xy, nrm, RAY_FT, tree, lots)
    right = _first_hit(xy, -nrm, RAY_FT, tree, lots)
    gap = left + right
    narrow = np.zeros(len(at), dtype=bool)
    narrow[cand[gap < MIN_WIDTH_FT]] = True
    spans: list[tuple[float, float]] = []
    i = 0
    while i < len(at):
        if not narrow[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(at) and narrow[j + 1]:
            j += 1
        if j - i + 1 >= NARROW_RUN:
            half = STATION_FT / 2.0
            spans.append((max(0.0, at[i] - half), min(line.length, at[j] + half)))
        i = j + 1
    return spans


def _cut(line: LineString, a: float, b: float) -> LineString:
    return substring(line, a, b)


def _split(line: LineString, spans: Sequence[tuple[float, float]]) -> list[tuple[LineString, bool]]:
    """``line`` in pieces, each flagged narrow or not."""
    out: list[tuple[LineString, bool]] = []
    pos = 0.0
    for a, b in spans:
        if a - pos > 1e-6:
            out.append((_cut(line, pos, a), False))
        out.append((_cut(line, a, b), True))
        pos = b
    if line.length - pos > 1e-6:
        out.append((_cut(line, pos, line.length), False))
    return [(g, n) for g, n in out if g.length > 0]


#: Why a piece is walked (:attr:`Piece.why`): too narrow, cut off from the
#: network beyond a narrow stretch, past 150 ft into a dead end that cannot
#: turn a truck, or one whose end the fabric leaves in doubt (no hose is
#: walked there: the lots beyond are unmeasured).
NARROW = "narrow"
CUT_OFF = "cut_off"
DEAD_END = "dead_end"
DEAD_END_UNSURE = "dead_end_unsure"
#: What :func:`_room_to_turn` finds at a dead end.
ROOM = "room"
NO_ROOM = "no_room"
UNSURE = "unsure"
SILENT = "silent"


def _room_to_turn(
    road: LineString, tree: shapely.STRtree, lots: np.ndarray, every: shapely.STRtree
) -> str:
    """Whether the right-of-way at the end of a dead end could hold a
    turnaround. ``road`` runs from the dead end back to its intersection.

    :data:`ROOM` where it could: clear right-of-way :data:`TURN_RADIUS_FT` round
    some point of the last :data:`BULB_REACH_FT` (D103.4's 96-foot
    cul-de-sac), or a bulb at all -- the clear room there wider than the
    street's own half-width :data:`HALF_BACK_FT` back by :data:`BULB_FT` or
    more, a cul-de-sac built to the city's own street standard, which
    "supersede[s] and prevail[s] over" the fire code's (ORS 368.039(1),
    ``or/ofc.2022.applications-guide.txt#L13-L16``) -- or room for a
    hammerhead's arm (:data:`HAMMER_ARM_FT`) to either side near the end.
    :data:`NO_ROOM` where none of them is there and the right-of-way does
    not widen by even :data:`JOG_FT`: a street that simply stops.
    :data:`UNSURE` where it widens by less than a bulb and more than a jog:
    :func:`build` walks no hose past the 150 ft there, and the lots beyond
    are left unmeasured (held out of GREEN). :data:`SILENT` where the
    fabric does not close the end (no lot of any kind ahead within
    :data:`CLOSED_AHEAD_FT`: the edge of the map, open land) or the end
    stands on a private lot (a private road on a tract): the fabric says
    nothing, and the road keeps the reading it had.
    """
    coords = np.asarray(road.coords)[:, :2]
    end = coords[0]
    p = Point(*end)
    inside = tree.query(p, predicate="within")
    if len(inside) and float(shapely.distance(p, shapely.boundary(lots[inside])).max()) > ON_LOT_FT:
        return SILENT
    toward = np.asarray(road.interpolate(min(5.0, road.length)).coords[0])[:2] - end
    back = toward / (float(np.hypot(*toward)) or 1.0)
    ahead = _first_hit(end[None, :], -back[None, :], CLOSED_AHEAD_FT, every, np.asarray(every.geometries))
    if not np.isfinite(ahead[0]):
        return SILENT

    def clear(at: float) -> float:
        q = road.interpolate(min(at, road.length))
        near = tree.query(q, predicate="dwithin", distance=RAY_FT)
        return float(shapely.distance(q, lots[near]).min()) if len(near) else math.inf

    room = max(clear(k) for k in np.arange(0.0, BULB_REACH_FT + 1e-6, STATION_FT))
    if room >= TURN_RADIUS_FT:
        return ROOM
    widen = room - clear(HALF_BACK_FT)
    if widen >= BULB_FT:
        return ROOM
    side = np.array([-back[1], back[0]])
    origins = np.array([end + back * k for k in HAMMER_BACK_FT])
    for d in (side, -side):
        reach = _first_hit(origins, np.repeat(d[None, :], len(origins), axis=0), HAMMER_ARM_FT, tree, lots)
        if (reach >= HAMMER_ARM_FT).any():
            return ROOM
    return NO_ROOM if widen < JOG_FT else UNSURE


def build(
    lines: Sequence[BaseGeometry],
    kinds: Sequence[int],
    links: Sequence[BaseGeometry],
    fabric: Sequence[BaseGeometry],
    private: Sequence[bool],
) -> list[Piece]:
    """The truck roads ``lines`` (their RLIS TYPE in ``kinds``) in pieces,
    each standing or walked.

    ``links`` are the other drivable lines (freeways and their ramps): a
    truck road that meets one is not a dead end there and is not cut off.
    ``fabric`` is the whole taxlot file and ``private`` which of its polygons
    are private land (not right-of-way or water)."""
    lots = np.asarray([g for g, p in zip(fabric, private) if p], dtype=object)
    tree = shapely.STRtree(lots)
    every = shapely.STRtree(np.asarray(list(fabric), dtype=object))

    pieces: list[tuple[LineString, bool, int]] = []
    for g, k in zip(lines, kinds):
        for part in getattr(g, "geoms", [g]):
            if part.is_empty or part.length <= 0:
                continue
            part = LineString(np.asarray(part.coords)[:, :2])
            for seg, narrow in _split(part, narrow_spans(part, tree, lots)):
                pieces.append((seg, narrow, int(k)))

    # The drivable graph: wide pieces and the links.
    edges: list[tuple[tuple[int, int], tuple[int, int], float, int]] = []
    for i, (g, narrow, _) in enumerate(pieces):
        if not narrow:
            c = g.coords
            edges.append((_node(c[0]), _node(c[-1]), g.length, i))
    link_nodes: set[tuple[int, int]] = set()
    link_parts: list[BaseGeometry] = []
    for g in links:
        for part in getattr(g, "geoms", [g]):
            if part.is_empty:
                continue
            c = part.coords
            link_nodes.update((_node(c[0]), _node(c[-1])))
            link_parts.append(part)
    deg: dict[tuple[int, int], int] = {}
    adj: dict[tuple[int, int], list[tuple[tuple[int, int], float, int]]] = {}
    for a, b, length, i in edges:
        deg[a] = deg.get(a, 0) + 1
        deg[b] = deg.get(b, 0) + 1
        adj.setdefault(a, []).append((b, length, i))
        adj.setdefault(b, []).append((a, length, i))
    for n in link_nodes:
        if n in deg:
            deg[n] += 1

    stand = [not narrow for _, narrow, _ in pieces]
    why = [NARROW if narrow else "" for _, narrow, _ in pieces]

    # Where a narrow stretch begins or ends.
    cut_nodes = set()
    for g, narrow, _ in pieces:
        if narrow:
            c = g.coords
            cut_nodes.update((_node(c[0]), _node(c[-1])))
    # Cut off: a component a narrow stretch leads into, with no trunk road,
    # no link and little length. One no narrow stretch touches is joined to
    # the rest some way the street file does not draw (a drive, a junction
    # off a node) and keeps its reading.
    seen: set[tuple[int, int]] = set()
    for start in adj:
        if start in seen:
            continue
        comp, members, stack = [start], set(), [start]
        seen.add(start)
        while stack:
            n = stack.pop()
            for m, _, i in adj[n]:
                members.add(i)
                if m not in seen:
                    seen.add(m)
                    comp.append(m)
                    stack.append(m)
        total = sum(pieces[i][0].length for i in members)
        joined = any(n in link_nodes for n in comp) or any(pieces[i][2] in TRUNK_TYPES for i in members)
        if not joined and total < ISLAND_FT and any(n in cut_nodes for n in comp):
            for i in members:
                stand[i] = False
                why[i] = CUT_OFF

    # Dead ends: from each end, back through plain joins to an intersection.
    split_at: dict[int, list[tuple[float, bool]]] = {}
    unsure: set[int] = set()
    body = shapely.STRtree(np.asarray([g for g, _, _ in pieces] + link_parts, dtype=object))
    for leaf, d in deg.items():
        if d != 1 or leaf in link_nodes:
            continue
        # An end on the body of another line is a junction the file did not
        # node, not a dead end.
        here = Point(leaf[0] * SNAP_FT, leaf[1] * SNAP_FT)
        near = body.geometries[body.query(here, predicate="dwithin", distance=SNAP_FT)]
        ends = shapely.distance(here, shapely.get_point(near, 0)), shapely.distance(here, shapely.get_point(near, -1))
        if ((ends[0] > SNAP_FT) & (ends[1] > SNAP_FT)).any():
            continue
        chain: list[tuple[int, bool]] = []  # (piece, the leaf side is its last coordinate)
        n, prev_piece, length = leaf, None, 0.0
        while True:
            nxt = [(m, ln, i) for m, ln, i in adj.get(n, []) if i != prev_piece]
            if len(nxt) != 1:
                break
            m, ln, i = nxt[0]
            if not stand[i]:
                chain = []
                break
            c = pieces[i][0].coords
            chain.append((i, _node(c[-1]) == n))
            length += ln
            prev_piece, n = i, m
            if deg.get(n, 0) != 2:
                break
        if not chain or deg.get(n, 0) < 3 or length <= DEAD_END_FT:
            continue
        road = LineString(
            np.vstack(
                [
                    np.asarray(pieces[i][0].coords)[::-1, :2] if last else np.asarray(pieces[i][0].coords)[:, :2]
                    for i, last in chain
                ]
            )
        )
        room = NO_ROOM if leaf in cut_nodes else _room_to_turn(road, tree, lots, every)
        if room in (ROOM, SILENT):
            continue
        # Everything more than DEAD_END_FT from the intersection -- within
        # (length - DEAD_END_FT) of the dead end -- is walked.
        deep = length - DEAD_END_FT
        run = 0.0
        for i, from_last in chain:
            ln = pieces[i][0].length
            if run >= deep:
                break
            take = min(ln, deep - run)
            at = ln - take if from_last else take
            split_at.setdefault(i, []).append((at, from_last))
            if room == UNSURE:
                unsure.add(i)
            run += ln

    # Re-cut the dead-end pieces at the 150-ft point.
    final: list[tuple[LineString, bool, str]] = []
    for i, (g, _, _) in enumerate(pieces):
        cuts = split_at.get(i)
        if not cuts:
            final.append((g, stand[i], why[i]))
            continue
        at, from_last = cuts[0]
        kind = DEAD_END_UNSURE if i in unsure else DEAD_END
        a, b = _cut(g, 0.0, at), _cut(g, at, g.length)
        parts = [(a, True, ""), (b, False, kind)] if from_last else [(a, False, kind), (b, True, "")]
        final.extend(p for p in parts if p[0].length > 1e-6)

    return _walked(final)


def _walked(final: Sequence[tuple[LineString, bool, str]]) -> list[Piece]:
    """Each walked piece's distance from either end to the nearest point a
    truck stands, along walked pieces only."""
    ends = [(_node(g.coords[0]), _node(g.coords[-1])) for g, _, _ in final]
    dist: dict[tuple[int, int], float] = {}
    for (a, b), (_, st, _) in zip(ends, final):
        if st:
            dist[a] = dist[b] = 0.0
    adj: dict[tuple[int, int], list[tuple[tuple[int, int], float]]] = {}
    for (a, b), (g, st, why) in zip(ends, final):
        if not st and why != DEAD_END_UNSURE:
            adj.setdefault(a, []).append((b, g.length))
            adj.setdefault(b, []).append((a, g.length))
    heap = [(0.0, n) for n in dist if n in adj]
    heapq.heapify(heap)
    while heap:
        d, n = heapq.heappop(heap)
        if d > dist.get(n, math.inf):
            continue
        for m, w in adj.get(n, []):
            if d + w < dist.get(m, math.inf):
                dist[m] = d + w
                heapq.heappush(heap, (d + w, m))
    out = []
    for (a, b), (g, st, why) in zip(ends, final):
        if st:
            out.append(Piece(g, True))
        elif why == DEAD_END_UNSURE:
            out.append(Piece(g, False, math.inf, math.inf, why))
        else:
            out.append(Piece(g, False, dist.get(a, math.inf), dist.get(b, math.inf), why))
    return out


def write(pieces: Sequence[Piece], path: Path) -> Path:
    import pandas as pd

    pd.DataFrame(
        {
            "wkb": shapely.to_wkb(np.asarray([p.geom for p in pieces], dtype=object)),
            "stand": [p.stand for p in pieces],
            "walk0": [p.walk0 for p in pieces],
            "walk1": [p.walk1 for p in pieces],
            "why": [p.why for p in pieces],
        }
    ).to_parquet(path, index=False)
    return path


@dataclass(frozen=True)
class Walks:
    """Per truck-road geometry (parallel to the index's geometries): whether
    the truck stands on it, and the hose's walk from either end where not."""

    stand: np.ndarray
    walk0: np.ndarray
    walk1: np.ndarray


def load(path: Path) -> tuple[shapely.STRtree, np.ndarray, Walks]:
    """The pieces :func:`write` wrote, indexed as :mod:`flats.fit.fire`
    takes them."""
    import pandas as pd

    frame = pd.read_parquet(path)
    geoms = shapely.from_wkb(frame["wkb"].to_numpy())
    walks = Walks(
        frame["stand"].to_numpy(dtype=bool),
        frame["walk0"].to_numpy(dtype=float),
        frame["walk1"].to_numpy(dtype=float),
    )
    return shapely.STRtree(geoms), geoms, walks


__all__ = [
    "DEAD_END_FT",
    "MIN_WIDTH_FT",
    "Piece",
    "TURN_RADIUS_FT",
    "Walks",
    "build",
    "load",
    "narrow_spans",
    "write",
]
