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

A city's adopted fire code amendment states its own length, and the stated
number governs its lots: Portland's 31.30.010.B lets a dead end run "more
than 300 feet in length" before it needs a turnaround
(``or/multnomah/portland/31.30.txt#L7``). Each length is read from
``flats/config/fire_roads.yaml`` (:func:`rules`), and :func:`build_all`
cuts the network once for each length a run needs.

Where the truck could reach a lot only by driving an existing dead end past
its length, the lot is not cleared and not failed either: Steph 2026-11-10
(rulings.yaml ``2026-11-10-fire-long-dead-end-yellow``): "Yellow." -- crews
often back in, and the fire marshal decides. So every piece also carries
the walk it would have were such dead ends driven (:attr:`Piece.free`), and
the screen holds a lot that clears only on that reading at YELLOW with a
flag (FIRE-DEAD-END). Which dead ends count is the register's switch
(``long_dead_end``), read here.

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
from typing import Mapping, Sequence

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.ops import substring

#: The register of fire-road lengths and the long-dead-end switch.
CONFIG = Path(__file__).resolve().parents[1] / "config" / "fire_roads.yaml"

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
    #: The same three where the dead ends :func:`rules` releases are driven
    #: to their ends (:data:`RELEASE`): the reading a fire marshal's yes
    #: would give. ``free`` None means as ``stand``.
    free: bool | None = None
    free0: float = 0.0
    free1: float = 0.0


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
    *,
    dead_end_ft: float = DEAD_END_FT,
    release: frozenset[str] = frozenset({DEAD_END, DEAD_END_UNSURE}),
) -> list[Piece]:
    """:func:`build_all` for one dead-end length."""
    return build_all(lines, kinds, links, fabric, private, lengths=(dead_end_ft,), release=release)[dead_end_ft]


def build_all(
    lines: Sequence[BaseGeometry],
    kinds: Sequence[int],
    links: Sequence[BaseGeometry],
    fabric: Sequence[BaseGeometry],
    private: Sequence[bool],
    *,
    lengths: Sequence[float] = (DEAD_END_FT,),
    release: frozenset[str] = frozenset({DEAD_END, DEAD_END_UNSURE}),
) -> dict[float, list[Piece]]:
    """The truck roads ``lines`` (their RLIS TYPE in ``kinds``) in pieces,
    each standing or walked, for each dead-end length in ``lengths`` (the
    farthest a truck may go up a dead end with no turnaround; a city's
    adopted amendment states its own, :func:`rules`).

    ``release`` names the walked kinds a fire marshal's yes would let the
    truck drive (:attr:`Piece.free`): the dead ends the register's switch
    holds YELLOW rather than RED.

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
    found: list[tuple[list[tuple[int, bool]], float, str]] = []
    body = shapely.STRtree(np.asarray([g for g, _, _ in pieces] + link_parts, dtype=object))
    shortest = min(lengths)
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
        if not chain or deg.get(n, 0) < 3 or length <= shortest:
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
        found.append((chain, length, room))

    out: dict[float, list[Piece]] = {}
    for ft in sorted(set(lengths)):
        split_at: dict[int, list[tuple[float, bool]]] = {}
        unsure: set[int] = set()
        for chain, length, room in found:
            if length <= ft:
                continue
            # Everything more than ``ft`` from the intersection -- within
            # (length - ft) of the dead end -- is walked.
            deep = length - ft
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

        # Re-cut the dead-end pieces at the length's point.
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
        out[ft] = _walked(final, release)
    return out


def _walked(
    final: Sequence[tuple[LineString, bool, str]], release: frozenset[str] = frozenset()
) -> list[Piece]:
    """Each walked piece's distance from either end to the nearest point a
    truck stands, along walked pieces only; and the same with the kinds in
    ``release`` standing (:attr:`Piece.free`)."""
    ends = [(_node(g.coords[0]), _node(g.coords[-1])) for g, _, _ in final]
    strict = _distances(ends, [(g, st) for g, st, _ in final])
    freed = [(g, st or why in release) for g, st, why in final]
    loose = _distances(ends, freed)
    out = []
    for (a, b), (g, st, why), (_, free) in zip(ends, final, freed):
        f0, f1 = (0.0, 0.0) if free else (loose.get(a, math.inf), loose.get(b, math.inf))
        if st:
            out.append(Piece(g, True, free=True))
        else:
            out.append(Piece(g, False, strict.get(a, math.inf), strict.get(b, math.inf), why, free, f0, f1))
    return out


def _distances(
    ends: Sequence[tuple[tuple[int, int], tuple[int, int]]], pieces: Sequence[tuple[LineString, bool]]
) -> dict[tuple[int, int], float]:
    """Each node's distance to the nearest standing point, along walked
    pieces only."""
    dist: dict[tuple[int, int], float] = {}
    for (a, b), (_, st) in zip(ends, pieces):
        if st:
            dist[a] = dist[b] = 0.0
    adj: dict[tuple[int, int], list[tuple[tuple[int, int], float]]] = {}
    for (a, b), (g, st) in zip(ends, pieces):
        if not st:
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
    return dist


def write(pieces: Sequence[Piece] | Mapping[float, Sequence[Piece]], path: Path) -> Path:
    """Write the pieces, one set per dead-end length (a bare sequence is
    the state's :data:`DEAD_END_FT`)."""
    import pandas as pd

    by_ft = pieces if isinstance(pieces, Mapping) else {DEAD_END_FT: pieces}
    frames = []
    for ft, got in by_ft.items():
        frames.append(
            pd.DataFrame(
                {
                    "dead_end_ft": [float(ft)] * len(got),
                    "wkb": shapely.to_wkb(np.asarray([p.geom for p in got], dtype=object)),
                    "stand": [p.stand for p in got],
                    "walk0": [p.walk0 for p in got],
                    "walk1": [p.walk1 for p in got],
                    "why": [p.why for p in got],
                    "free": [p.stand if p.free is None else p.free for p in got],
                    "free0": [p.free0 for p in got],
                    "free1": [p.free1 for p in got],
                }
            )
        )
    pd.concat(frames, ignore_index=True).to_parquet(path, index=False)
    return path


@dataclass(frozen=True)
class Walks:
    """Per truck-road geometry (parallel to the index's geometries): whether
    the truck stands on it, and the hose's walk from either end where not."""

    stand: np.ndarray
    walk0: np.ndarray
    walk1: np.ndarray


@dataclass(frozen=True)
class Roads:
    """One dead-end length's pieces, indexed as :mod:`flats.fit.fire`
    takes them: the code's reading (``walks``) and the reading with the
    released dead ends driven (``freed``)."""

    tree: shapely.STRtree
    geoms: np.ndarray
    walks: Walks
    freed: Walks


def load_all(path: Path) -> dict[float, Roads]:
    """Every dead-end length :func:`write` wrote."""
    import pandas as pd

    frame = pd.read_parquet(path)
    if "dead_end_ft" not in frame.columns:
        frame["dead_end_ft"] = DEAD_END_FT
    out: dict[float, Roads] = {}
    for ft, part in frame.groupby("dead_end_ft", sort=True):
        geoms = shapely.from_wkb(part["wkb"].to_numpy())
        walks = Walks(
            part["stand"].to_numpy(dtype=bool),
            part["walk0"].to_numpy(dtype=float),
            part["walk1"].to_numpy(dtype=float),
        )
        freed = (
            Walks(
                part["free"].to_numpy(dtype=bool),
                part["free0"].to_numpy(dtype=float),
                part["free1"].to_numpy(dtype=float),
            )
            if "free" in part.columns
            else walks
        )
        out[float(ft)] = Roads(shapely.STRtree(geoms), geoms, walks, freed)
    return out


def load(path: Path) -> tuple[shapely.STRtree, np.ndarray, Walks]:
    """The pieces :func:`write` wrote for the state's length (or the only
    length written), indexed as :mod:`flats.fit.fire` takes them."""
    every = load_all(path)
    roads = every.get(DEAD_END_FT) or next(iter(every.values()))
    return roads.tree, roads.geoms, roads.walks


@dataclass(frozen=True)
class FireRoadRules:
    """``flats/config/fire_roads.yaml``: the dead-end length each place
    states and which dead ends a lot may clear only with the fire marshal's
    yes (:data:`Piece.free`)."""

    default_ft: float
    by_layer: Mapping[str, float]
    release: frozenset[str]

    def dead_end_ft(self, layer_id: str | None) -> float:
        """The length the lot's place states; the state's where it states
        none."""
        return self.by_layer.get(layer_id or "", self.default_ft)

    @property
    def lengths(self) -> tuple[float, ...]:
        return tuple(sorted({self.default_ft, *self.by_layer.values()}))


#: The switch's two settings.
LONG_DEAD_END = ("yellow", "red")


def rules(path: Path = CONFIG) -> FireRoadRules:
    """Read the register. A length with no stored quote, or a switch set to
    anything but yellow or red, is refused."""
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    lengths = data["dead_end_ft"]
    by_layer: dict[str, float] = {}
    default = None
    for key, entry in lengths.items():
        if not entry.get("quote"):
            raise ValueError(f"{path}: dead_end_ft.{key} has no stored quote")
        ft = float(entry["value"])
        if key == "default":
            default = ft
        else:
            by_layer[key] = ft
    if default is None:
        raise ValueError(f"{path}: dead_end_ft has no default")
    switch = data["long_dead_end"]
    if switch not in LONG_DEAD_END:
        raise ValueError(f"{path}: long_dead_end must be one of {LONG_DEAD_END}, not {switch!r}")
    # An end whose room is unclear is never RED: it is a question either way.
    release = frozenset({DEAD_END_UNSURE, DEAD_END} if switch == "yellow" else {DEAD_END_UNSURE})
    return FireRoadRules(default, by_layer, release)


@dataclass(frozen=True)
class Network:
    """A run's truck roads, every length its places state; :meth:`at`
    picks a lot's."""

    by_ft: Mapping[float, Roads]
    rules: FireRoadRules
    #: The street edges (curbs and widths) the hose is measured from.
    edges: object = None

    def at(self, layer_id: str | None) -> Roads:
        ft = self.rules.dead_end_ft(layer_id)
        return self.by_ft.get(ft) or self.by_ft[self.rules.default_ft]


__all__ = [
    "CONFIG",
    "DEAD_END_FT",
    "FireRoadRules",
    "MIN_WIDTH_FT",
    "Network",
    "Piece",
    "Roads",
    "TURN_RADIUS_FT",
    "Walks",
    "build",
    "build_all",
    "load",
    "load_all",
    "narrow_spans",
    "rules",
    "write",
]
