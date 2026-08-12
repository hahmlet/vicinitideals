"""Lot geometry: naming the edges, then cutting the buildable envelope.

:mod:`edges` infers which lot line faces the street and rates how much to trust
that inference; :mod:`envelope` turns the naming plus a set of setbacks into the
area a building may occupy. The envelope is what :mod:`flats.fit` rasterizes.
"""

from flats.geom.edges import (
    Edge,
    EdgeClass,
    LotEdges,
    StreetIndex,
    Tier,
    bearing_delta,
    bearing_deg,
    classify,
    cluster_bearings,
)
from flats.geom.envelope import MIN_PART_SQFT, Setbacks, buildable

__all__ = [
    "MIN_PART_SQFT",
    "Edge",
    "EdgeClass",
    "LotEdges",
    "Setbacks",
    "StreetIndex",
    "Tier",
    "bearing_deg",
    "bearing_delta",
    "buildable",
    "classify",
    "cluster_bearings",
]
