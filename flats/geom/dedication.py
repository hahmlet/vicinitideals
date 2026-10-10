"""Right-of-way a middle-housing lot gives up before its first building permit,
and how far that takes its building line back.

Washington County CDC 302-2.14 C(1) (and 303 through 306 alike): on a public
street, "along the entire site frontage, existing right-of-way width meets the
required minimum below, or the applicant proposes to dedicate right-of-way to
meet the following: Local street: 25 feet to centerline; Neighborhood route:
30 feet to centerline; Collector: 37 feet to centerline; Arterial: 45 feet to
centerline; or If road improvements built to ultimate County standard exist,
no additional right-of-way is required." C(2) has the dedication recorded
"prior to issuance of the first building permit", and the yards then run from
the new line (the lot's AREA is counted before it, 302-7.1 A).

**What is measured.** The distance from each street lot line to the centreline
of the street it abuts (Metro's RLIS file, the same street
:mod:`flats.geom.street_class` ranks), at the nine sample points the class
rank is read at. The centreline is the code's own reference ("to
centerline"), and the exemption -- a road already at its final width -- is
the half-width meeting the distance. The lot gives up the shortfall of the
NARROWEST measured point, never below zero, along the whole line: the strip
is taken as a setback is, a uniform offset of the lot line.

**What is not.** A street line is *unmeasured* when fewer than
:data:`MIN_MEASURED` of its nine points have a centreline running beside
them, and the lot then gives up the whole distance (the worst case: the lot
line on the centreline). A line whose street class is unread takes the
deepest distance the code lists (:func:`required_ft`). A street that is not
public (a private road, RLIS TYPE 1700 / 1800) is not "a public street"
and takes nothing.

The distances are the rules' (``row_to_centerline_*_ft``); this module holds
only how the class rank picks one.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from flats.geom.corridor import SAMPLES, STREET_CLASS, _fronted
from flats.geom.street_class import ClassMap, _samples

#: Layers whose code makes a lot dedicate right-of-way. Only these rows are
#: measured.
LAYERS: tuple[str, ...] = ("or/washington/_unincorporated",)

#: The rules' four distances, by street class: Washington County's TSP rank
#: (0 local, 1 neighbourhood route, 2 collector, 3 and up arterial).
RANK_FIELDS: tuple[str, ...] = (
    "row_to_centerline_local_ft",
    "row_to_centerline_neighborhood_route_ft",
    "row_to_centerline_collector_ft",
    "row_to_centerline_arterial_ft",
)

#: A street Metro types as a private road or drive is not a public street.
PRIVATE_TYPES: frozenset[int] = frozenset({1700, 1800})

#: Fewest sample points (of :data:`SAMPLES`) that must have a centreline
#: beside them for a line to count as measured.
MIN_MEASURED = SAMPLES // 2 + 1


def applies(layer_id: str | None) -> bool:
    """Whether ``layer_id``'s code asks for a dedication."""
    return bool(layer_id) and any(layer_id == s or layer_id.startswith(f"{s}/") for s in LAYERS)


def half_width_ft(edge: Sequence[float], cmap: ClassMap) -> tuple[float | None, bool]:
    """One street lot line's measured half-width, and whether the street is public.

    The smallest centreline distance over the sample points that have a
    street beside them, or None where fewer than :data:`MIN_MEASURED` do. The
    street is public unless a point abuts a private road or drive.
    """
    got = _samples(edge)
    if got is None:
        return None, True
    points, own = got
    widths: list[float] = []
    for p in points:
        s = _fronted(p, own, cmap.streets)
        if s is None:
            continue
        if cmap.types[s] in PRIVATE_TYPES:
            return None, False
        widths.append(float(cmap.streets.lines[s].distance(p)))
    if len(widths) < MIN_MEASURED:
        return None, True
    return min(widths), True


def measure(
    edges: Iterable[Sequence[Any]],
    ranks: Sequence[int | None],
    layer_id: str | None,
    maps: Sequence[ClassMap],
) -> list[list[Any]]:
    """Every street line of one lot, as ``[x1, y1, x2, y2, half_width_ft,
    rank, public]`` -- the half-width None where unmeasured, the rank None
    where the street's class is unread. ``ranks`` is
    :func:`flats.geom.street_class.street_ranks` for the same edges. Empty
    where no map serves the layer."""
    serving = [m for m in maps if m.covers(layer_id)]
    if not serving:
        return []
    cmap = serving[0]
    out: list[list[Any]] = []
    for e, rank in zip(edges, ranks, strict=True):
        if len(e) < 5 or e[4] != STREET_CLASS:
            continue
        width, public = half_width_ft(e, cmap)  # type: ignore[arg-type]
        out.append(
            [
                *(round(float(v), 3) for v in e[:4]),
                None if width is None else round(width, 3),
                rank,
                public,
            ]
        )
    return out


def key(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float, float]:
    """The coordinates a measured line is looked up by."""
    return (round(float(x1), 3), round(float(y1), 3), round(float(x2), 3), round(float(y2), 3))


def required_ft(rank: int | None, distances: Sequence[float]) -> float:
    """The distance to centreline the code asks for a street of ``rank``;
    the deepest one where the class is unread. ``distances`` is the rules'
    four, in :data:`RANK_FIELDS` order."""
    if rank is None:
        return max(distances)
    return distances[min(max(rank, 0), len(distances) - 1)]


def depth_ft(required: float, half_width: float | None) -> float:
    """The strip a lot gives up on one street line: the shortfall, never
    below zero, and the whole distance where the half-width is unmeasured."""
    if half_width is None:
        return required
    return max(0.0, required - half_width)


__all__ = [
    "LAYERS",
    "MIN_MEASURED",
    "PRIVATE_TYPES",
    "RANK_FIELDS",
    "applies",
    "depth_ft",
    "half_width_ft",
    "key",
    "measure",
    "required_ft",
]
