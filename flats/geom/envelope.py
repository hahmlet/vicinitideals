"""The buildable envelope: the lot minus everything the setbacks take.

Two constructions, chosen by how much the edge classification can be trusted.

*Per-edge strips.* Buffer each lot line inward by its own setback and subtract
the union. Square caps run each strip past its endpoints so the wedge in every
corner is covered by one neighbour or the other — the result is never larger
than the legal envelope, and the error is confined to corner wedges and bounded
by the difference between adjacent setbacks.

*Uniform inward buffer.* For irregular and flag-shaped lots, shrink the whole
lot by the largest setback. Strictly smaller than the truth, often by a lot, and
that is the point: on a shape where naming the front is guesswork, an envelope
that might be too big would produce false GREENs on the least reviewable lots.

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
ordinary side setback across from the neighbour. The rear line cannot be,
because its alley number is the rear setback itself, resolved once for the
line: the bridge switches ``alley_at_rear`` on only where the alley runs the
whole rear line (:func:`flats.geom.alley.registry_alley`), and a rear line
the alley runs part of arrives here with the ordinary rear setback.

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
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import shapely
from shapely.geometry import LineString, MultiPolygon
from shapely.geometry.base import BaseGeometry

from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier

#: Envelope fragments below this hold nothing worth rasterizing.
MIN_PART_SQFT = 200.0


@dataclass(frozen=True, slots=True)
class Setbacks:
    """The numbers the envelope is cut with, in feet."""

    front_ft: float = 0.0
    side_ft: float = 0.0
    rear_ft: float = 0.0
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
        """The setback one edge takes: its class's, unless it is the alley side."""
        if edge.alley and edge.cls is EdgeClass.side and self.alley_side_ft is not None:
            return self.alley_side_ft
        if (
            edge.off_corridor
            and edge.cls in (EdgeClass.front, EdgeClass.street_side)
            and self.street_off_corridor_ft is not None
        ):
            return self.street_off_corridor_ft
        return self.for_class(edge.cls)

    @property
    def largest_ft(self) -> float:
        return max(self.front_ft, self.side_ft, self.rear_ft, self.street_side_ft or 0.0)

    def on_a_corner(self) -> Setbacks:
        """The same setbacks, with street edges taking the stricter standard."""
        if self.street_side_ft is None:
            return self
        return Setbacks(
            front_ft=max(self.front_ft, self.street_side_ft),
            side_ft=self.side_ft,
            rear_ft=self.rear_ft,
            street_side_ft=self.street_side_ft,
            alley_side_ft=self.alley_side_ft,
            street_off_corridor_ft=self.street_off_corridor_ft,
        )


def _clean(env: BaseGeometry, min_part_sqft: float) -> MultiPolygon:
    parts = [
        p
        for p in shapely.get_parts(env)
        if p.geom_type == "Polygon" and p.area >= min_part_sqft
    ]
    return MultiPolygon(parts)


def _less(env: BaseGeometry, less: BaseGeometry | None) -> BaseGeometry:
    if less is None or less.is_empty or env.is_empty:
        return env
    return env.difference(less)


Segment = tuple[float, float, float, float]


def _pieces(edge: Edge, setbacks: Setbacks) -> list[tuple[Segment, float]]:
    """The stretches of one edge and the setback each takes.

    One piece, at :meth:`Setbacks.for_edge`, for every edge but a side line
    on an alley whose code states its own number for that line
    (``setback_alley_side_ft``) and whose cover s4 measured (FOLLOWUPS
    3(e)). The alley number is a rule about "a lot line abutting an alley",
    and on a line the alley runs part of -- s4 classes the line an alley
    line on three rays of five -- the stretch across from the neighbour's
    yard abuts the neighbour. So the line is cut stretch by stretch: the
    alley's number where the cover's rays found it
    (:func:`flats.geom.alley.cover_stretches`), and elsewhere the larger of
    it and the ordinary side setback -- a waiver does not reach the
    neighbour, and a city that calls the alley line a rear lot line (the
    bridge's ``max(side, rear)``) is not relaxed by a stretch it did not
    measure. Square caps run each piece's strip past its ends, so an
    uncovered piece bites a few feet into the covered one: never larger
    than the legal envelope. A cover of ``""`` (none on record) vouches for
    no stretch, and the whole line takes the larger number.
    """
    whole_edge: Segment = (edge.x1, edge.y1, edge.x2, edge.y2)
    d = setbacks.for_edge(edge)
    if (
        not edge.alley
        or edge.cls is not EdgeClass.side
        or setbacks.alley_side_ft is None
        or edge.cover is None
    ):
        return [(whole_edge, d)]
    from flats.geom.alley import cover_stretches

    alley_ft = setbacks.alley_side_ft
    ordinary = max(setbacks.side_ft, alley_ft)
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
    if not use_strips:
        # Irregular, flag, or unclassifiable: shrink uniformly by the worst
        # setback. Conservative on purpose — see the module docstring.
        env = lot.buffer(-setbacks.largest_ft) if setbacks.largest_ft > 0 else lot
        return _clean(_less(env, less), min_part_sqft)

    strips = []
    for edge in edges.edges:
        for (x1, y1, x2, y2), d in _pieces(edge, setbacks):
            if d <= 0:
                continue
            strips.append(
                LineString([(x1, y1), (x2, y2)]).buffer(
                    d, cap_style="square", join_style="mitre"
                )
            )
    env = lot.difference(shapely.union_all(strips)) if strips else lot
    return _clean(_less(env, less), min_part_sqft)
