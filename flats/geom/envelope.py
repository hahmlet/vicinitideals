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
front. Fragments too small to hold anything are dropped — a pod does not fit in
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
"""

from __future__ import annotations

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

    def for_class(self, cls: EdgeClass) -> float:
        return {
            EdgeClass.front: self.front_ft,
            EdgeClass.rear: self.rear_ft,
            EdgeClass.side: self.side_ft,
        }[cls]

    def for_edge(self, edge: Edge) -> float:
        """The setback one edge takes: its class's, unless it is the alley side."""
        if edge.alley and edge.cls is EdgeClass.side and self.alley_side_ft is not None:
            return self.alley_side_ft
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
        )


def _clean(env: BaseGeometry, min_part_sqft: float) -> MultiPolygon:
    parts = [
        p
        for p in shapely.get_parts(env)
        if p.geom_type == "Polygon" and p.area >= min_part_sqft
    ]
    return MultiPolygon(parts)


def buildable(
    lot: BaseGeometry,
    edges: LotEdges,
    setbacks: Setbacks,
    *,
    min_part_sqft: float = MIN_PART_SQFT,
) -> MultiPolygon:
    """The area of ``lot`` a building may occupy. May be empty.

    An empty envelope is a real answer — on a small lot deep setbacks can
    consume everything — and it flows through to a fit of zero rather than an
    error.
    """
    if lot is None or lot.is_empty:
        return MultiPolygon([])

    if edges.tier is Tier.corner:
        setbacks = setbacks.on_a_corner()

    use_strips = edges.tier in (Tier.clean, Tier.corner) and bool(edges.edges)
    if not use_strips:
        # Irregular, flag, or unclassifiable: shrink uniformly by the worst
        # setback. Conservative on purpose — see the module docstring.
        env = lot.buffer(-setbacks.largest_ft) if setbacks.largest_ft > 0 else lot
        return _clean(env, min_part_sqft)

    strips = []
    for edge in edges.edges:
        d = setbacks.for_edge(edge)
        if d <= 0:
            continue
        strips.append(
            LineString([(edge.x1, edge.y1), (edge.x2, edge.y2)]).buffer(
                d, cap_style="square", join_style="mitre"
            )
        )
    env = lot.difference(shapely.union_all(strips)) if strips else lot
    return _clean(env, min_part_sqft)
