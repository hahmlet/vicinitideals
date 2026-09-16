"""Which lot line is the front, and how much to trust the answer.

Setbacks are written per edge — front, side, rear — so the envelope cannot be
computed until each edge has a name. Nothing in the assessor data says which
line faces the street, so it is inferred: simplify the boundary to merge
collinear vertices, then measure each edge's midpoint to the nearest street
centerline. Close enough is frontage. Edges roughly parallel to a frontage
bearing are rear; everything else is side.

Alongside the classification comes a confidence tier, because the inference is
much safer on a rectangular interior lot than on a flag lot with a driveway
pole. The tier does not decide anything on its own — it selects how
conservative the envelope construction should be, and it travels with the
result so a reviewer knows what they are looking at.

**A lot with no street found is still a lot.** The predecessor pipeline dropped
those from its headline numbers, which is exactly the failure this project
exists to prevent: no street centerline nearby can mean landlocked, or it can
mean the street layer has a gap. One of those is a real exclusion and the other
is a data bug, and they are indistinguishable from here. So the lot keeps a
conservative envelope and carries :attr:`LotEdges.landlocked`, and the verdict
is somebody else's decision downstream.

**An alley is not a street, and the line on it is still a rear or a side.**
Eleven of the fourteen codes read for this say so outright, and every setback
table is written for the street. So an alley centerline never makes a front;
the edge on it keeps the orientation class its bearing gives it -- rear where it
runs with the frontage, side where it does not -- and carries
:attr:`Edge.alley` beside that class, because the codes carve that one line
out. Portland 33.110.220.D.9 waives the "side, rear, or garage entrance setback
... from a lot line abutting an alley"; the rear half of that is a rule about
the rear line and rides on the rear setback, and the side half is a rule about
ONE of the two side lines, which is why the flag is on the edge and not on the
lot. :meth:`LotEdges.alley_facts` reports the same three facts the quadfit
bridge (:mod:`flats.geom.alley`) does -- ``abuts_alley``, ``alley_at_rear``,
``alley_at_side`` -- so the edge the rules resolve on is the edge the envelope
cuts. A lot whose only public way is the alley takes it as frontage, as
quadfit's s4 does, so that a lot on a public way is not called landlocked; such
a lot owes its front setback to the alley and reports no alley facts.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
import shapely
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

#: An edge within this of a frontage bearing is the opposite lot line, not a side.
PARALLEL_TOL_DEG = 30.0
#: Frontage bearings closer than this are the same street direction.
BEARING_CLUSTER_TOL_DEG = 20.0
#: Area over convex-hull area below which a lot is treated as irregular.
CONVEXITY_IRREGULAR = 0.80
#: More boundary segments than a plausible platted lot has.
MAX_EDGES_REGULAR = 10
#: Inward buffer that collapses a flag lot's access pole (poles run ~15 ft).
POLE_TEST_BUFFER_FT = -7.5
#: Boundary segments shorter than this are survey noise, not lot lines.
MIN_EDGE_FT = 1.0


class EdgeClass(str, enum.Enum):
    """Which setback governs an edge."""

    front = "front"
    rear = "rear"
    side = "side"


class Tier(str, enum.Enum):
    """How much the frontage inference can be trusted for this shape."""

    #: Near-convex, one street direction. The per-edge envelope is reliable.
    clean = "clean"
    #: Two or more street directions — a corner. Which line is legally the
    #: front is unknowable from geometry, so the envelope takes the stricter
    #: of front and street-side on every street edge.
    corner = "corner"
    #: Concave, many-sided, or flag-shaped. Per-edge strips are not trustworthy,
    #: so the envelope falls back to a uniform inward buffer at the largest
    #: setback — strictly smaller than the real one.
    irregular = "irregular"
    #: No street centerline within reach. May be landlocked, may be a hole in
    #: the street data. Kept, flagged, and routed to review.
    landlocked = "landlocked"


@dataclass(frozen=True, slots=True)
class Edge:
    """One boundary segment and the setback class it takes."""

    x1: float
    y1: float
    x2: float
    y2: float
    length_ft: float
    bearing_deg: float
    cls: EdgeClass
    #: The line abuts an alley. Orthogonal to ``cls``: an alley edge is still
    #: rear or side by its bearing, and the flag is what lets a setback table
    #: carve that one line out (Portland waives the side and rear setback from
    #: it). Never set on a front -- an alley is not a street.
    alley: bool = False


@dataclass(frozen=True, slots=True)
class LotEdges:
    """The classified boundary of one lot."""

    tier: Tier
    edges: tuple[Edge, ...]
    #: Distinct street directions, widest frontage first. At most two are kept;
    #: a third street on one lot changes nothing about which rotations to try.
    front_bearings: tuple[float, ...]
    frontage_ft: float
    #: Lot area over convex-hull area. 1.0 is convex.
    convexity: float

    @property
    def landlocked(self) -> bool:
        return self.tier is Tier.landlocked

    def of_class(self, cls: EdgeClass) -> tuple[Edge, ...]:
        return tuple(e for e in self.edges if e.cls is cls)

    def alley_facts(self) -> dict[str, bool]:
        """The three alley site facts, as ``configure(observed=...)`` takes them.

        The same shape :func:`flats.geom.alley.observed_alley` returns from
        quadfit's edge record, produced here from this classification so a
        caller that names its own edges resolves the rules on the line it is
        about to cut. Every key is always present: a False is a measurement.
        """
        rear = any(e.alley and e.cls is EdgeClass.rear for e in self.edges)
        side = any(e.alley and e.cls is EdgeClass.side for e in self.edges)
        return {"abuts_alley": rear or side, "alley_at_rear": rear, "alley_at_side": side}


def bearing_deg(x1: float, y1: float, x2: float, y2: float) -> float:
    """Edge direction in [0, 180) — a lot line has no front and back."""
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180.0


def bearing_delta(a: float, b: float) -> float:
    """Smallest angle between two directions, mod 180."""
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def cluster_bearings(bearings_lengths: Iterable[tuple[float, float]]) -> list[float]:
    """Collapse frontage bearings into distinct street directions.

    Length-weighted and greedy: the longest frontage anchors a cluster and
    shorter edges join it if they point roughly the same way. Weighting by
    length keeps a two-foot jog in a curb line from registering as a second
    street.
    """
    clusters: list[list[float]] = []  # [center, total length]
    for b, ln in sorted(bearings_lengths, key=lambda t: -t[1]):
        for c in clusters:
            if bearing_delta(b, c[0]) <= BEARING_CLUSTER_TOL_DEG:
                w = c[1] + ln
                delta = b - c[0]
                if delta > 90:
                    delta -= 180
                elif delta < -90:
                    delta += 180
                c[0] = (c[0] + delta * ln / w) % 180.0
                c[1] = w
                break
        else:
            clusters.append([b, ln])
    clusters.sort(key=lambda c: -c[1])
    return [c[0] for c in clusters]


class StreetIndex:
    """Street centerlines, queryable for nearest distance.

    A lot line on a street abuts the right-of-way, so the distance from the
    line's midpoint to the centerline is a sound frontage proxy — roughly
    half the right-of-way width plus any planting strip. The taxlot layers
    do draw the right-of-way, as their own rows (Multnomah's ``-STR`` per
    quarter-section, Clackamas's ``ROADS``; quadfit's ``NOT_A_TAXLOT_RE``
    names them), and where an alley is platted as nothing at all the gap in
    the fabric is the alley — which is how its width is measured. Neither
    reaches this index: it holds centerlines only.
    """

    def __init__(self, streets: Sequence[BaseGeometry]) -> None:
        self.geoms = np.array(list(streets), dtype=object)
        self.tree = STRtree(self.geoms) if len(self.geoms) else None

    def __len__(self) -> int:
        return len(self.geoms)

    def distance(self, point: Point) -> float:
        """Distance to the nearest centerline, or infinity when there are none."""
        if self.tree is None:
            return math.inf
        return float(point.distance(self.geoms[self.tree.nearest(point)]))


def _segments(geom: BaseGeometry, simplify_tol_ft: float) -> list[tuple[float, ...]]:
    simplified = geom.simplify(simplify_tol_ft, preserve_topology=True)
    ring = list(simplified.exterior.coords)
    out = []
    for (x1, y1), (x2, y2) in zip(ring[:-1], ring[1:]):
        length = math.hypot(x2 - x1, y2 - y1)
        if length >= MIN_EDGE_FT:
            out.append((x1, y1, x2, y2, length, bearing_deg(x1, y1, x2, y2)))
    return out


def _is_irregular(geom: BaseGeometry, n_edges: int) -> tuple[bool, float]:
    hull_area = geom.convex_hull.area
    convexity = geom.area / hull_area if hull_area > 0 else 0.0
    shrunk = geom.buffer(POLE_TEST_BUFFER_FT)
    parts = shapely.get_parts(shrunk) if not shrunk.is_empty else []
    total = sum(p.area for p in parts)
    # A shape that breaks into pieces none of which dominates is a body plus a
    # pole — a flag lot, whose "frontage" is a driveway.
    pole_like = len(parts) > 1 and max((p.area for p in parts), default=0) < 0.8 * total
    irregular = convexity < CONVEXITY_IRREGULAR or n_edges > MAX_EDGES_REGULAR or pole_like
    return irregular, convexity


def classify(
    lot: BaseGeometry,
    streets: StreetIndex,
    *,
    street_threshold_ft: float,
    simplify_tol_ft: float = 1.0,
    alleys: StreetIndex | None = None,
) -> LotEdges:
    """Name every edge of one lot and rate the confidence of the naming.

    ``streets`` holds street centerlines only; ``alleys`` holds the alley
    centerlines, kept apart because an alley is not a street (see the module
    docstring). An edge within ``street_threshold_ft`` of an alley and not of
    a street is flagged :attr:`Edge.alley` and classed rear or side by its
    bearing like any other. Where a street wins, the street wins: a line
    within reach of both is frontage.
    """
    segments = _segments(lot, simplify_tol_ft)
    irregular, convexity = _is_irregular(lot, len(segments))

    if not segments:
        return LotEdges(Tier.landlocked, (), (), 0.0, convexity)

    mids = [Point((x1 + x2) / 2, (y1 + y2) / 2) for x1, y1, x2, y2, _len, _b in segments]
    fronts = [streets.distance(m) <= street_threshold_ft for m in mids]
    on_alley = [
        not f and alleys is not None and alleys.distance(m) <= street_threshold_ft
        for m, f in zip(mids, fronts)
    ]

    if not any(fronts) and any(on_alley):
        # The alley is the lot's only public way, so it is the frontage -- the
        # lot is not landlocked -- and no line is carved out as an alley line.
        fronts, on_alley = on_alley, [False] * len(segments)

    if not any(fronts):
        # No street found. Every edge is a side, which is the strictest reading
        # available, and the tier records why the lot needs a human.
        edges = tuple(
            Edge(x1, y1, x2, y2, length, b, EdgeClass.side)
            for x1, y1, x2, y2, length, b in segments
        )
        return LotEdges(Tier.landlocked, edges, (), 0.0, convexity)

    front_bearings = cluster_bearings(
        [(s[5], s[4]) for s, f in zip(segments, fronts) if f]
    )
    frontage_ft = sum(s[4] for s, f in zip(segments, fronts) if f)

    edges = []
    for (x1, y1, x2, y2, length, b), is_front, is_alley in zip(segments, fronts, on_alley):
        if is_front:
            cls = EdgeClass.front
        elif any(bearing_delta(b, fb) <= PARALLEL_TOL_DEG for fb in front_bearings):
            cls = EdgeClass.rear
        else:
            cls = EdgeClass.side
        edges.append(Edge(x1, y1, x2, y2, length, b, cls, alley=is_alley))

    if irregular:
        tier = Tier.irregular
    elif len(front_bearings) >= 2:
        tier = Tier.corner
    else:
        tier = Tier.clean

    return LotEdges(
        tier=tier,
        edges=tuple(edges),
        front_bearings=tuple(round(b, 4) for b in front_bearings[:2]),
        frontage_ft=frontage_ft,
        convexity=convexity,
    )
