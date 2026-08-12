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
"""

from __future__ import annotations

from dataclasses import dataclass

import shapely
from shapely.geometry import LineString, MultiPolygon
from shapely.geometry.base import BaseGeometry

from flats.geom.edges import EdgeClass, LotEdges, Tier

#: Envelope fragments below this hold nothing worth rasterizing.
MIN_PART_SQFT = 200.0


@dataclass(frozen=True, slots=True)
class Setbacks:
    """The four numbers the envelope is cut with, in feet."""

    front_ft: float = 0.0
    side_ft: float = 0.0
    rear_ft: float = 0.0
    #: The side setback along a second street. None means the code does not
    #: distinguish it, in which case a corner lot uses the front setback.
    street_side_ft: float | None = None

    def for_class(self, cls: EdgeClass) -> float:
        return {
            EdgeClass.front: self.front_ft,
            EdgeClass.rear: self.rear_ft,
            EdgeClass.side: self.side_ft,
        }[cls]

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
        d = setbacks.for_class(edge.cls)
        if d <= 0:
            continue
        strips.append(
            LineString([(edge.x1, edge.y1), (edge.x2, edge.y2)]).buffer(
                d, cap_style="square", join_style="mitre"
            )
        )
    env = lot.difference(shapely.union_all(strips)) if strips else lot
    return _clean(env, min_part_sqft)
