"""Durham 3.7.1.7: bound whether an apron can clear mapped intersections.

The bridge has parcel street edges and RLIS street centerlines, but no
apron-location drawing. The Durham rule lets access use any frontage, so each
frontage is checked for a continuous apron-width interval against every mapped
street intersection. Centerline intersections are projected by station onto
the whole frontage chain. Passing subtracts the cross street's half-width and
a conservative curb-return allowance; failure uses the unadjusted centerline
distance. The interval between those bounds remains unmeasured.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import shapely
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry
from shapely.strtree import STRtree

from flats.fit.frontage import street_chains
from flats.geom.corridor import FRONT_REACH_FT
from flats.geom.edges import Edge, EdgeClass, LotEdges, Tier, bearing_deg, bearing_delta

DURHAM_APRON_MIN_CLEARANCE_FT = 100.0
DEFAULT_CROSS_STREET_HALF_ROW_FT = 40.0
# A conservative allowance, not a code figure, pending a measured curb layer.
CURB_RETURN_ALLOWANCE_FT = 35.0
_PARALLEL_TOL_DEG = 20.0
_COLLINEAR_TOL_DEG = 8.0
_BEARING_HALF_RUN_FT = 3.0


@dataclass(frozen=True)
class StreetNetwork:
    """Street centerlines from one acquire snapshot, spatially indexed."""

    geoms: tuple[BaseGeometry, ...]
    names: tuple[str, ...]
    tree: STRtree | None

    @classmethod
    def build(
        cls, geoms: Sequence[BaseGeometry], names: Sequence[object] = ()
    ) -> StreetNetwork:
        kept: list[BaseGeometry] = []
        kept_names: list[str] = []
        for i, geom in enumerate(geoms):
            if geom is None or geom.is_empty or geom.geom_type not in ("LineString", "MultiLineString"):
                continue
            kept.append(geom)
            name = names[i] if i < len(names) else ""
            kept_names.append("" if name is None or str(name).lower() in {"nan", "<na>"} else str(name))
        arr = np.asarray(kept, dtype=object)
        return cls(tuple(kept), tuple(kept_names), STRtree(arr) if len(arr) else None)


def load_street_network(path: Path) -> StreetNetwork | None:
    """Load snapshot street lines; None when the file cannot measure them."""
    import pandas as pd
    import pyarrow.parquet as pq

    if not path.is_file() or "wkb" not in pq.read_schema(path).names:
        return None
    columns = ["wkb"]
    names = set(pq.read_schema(path).names)
    if "name" in names:
        columns.append("name")
    frame = pd.read_parquet(path, columns=columns)
    geoms = shapely.from_wkb(frame["wkb"].to_numpy())
    return StreetNetwork.build(geoms, frame["name"].tolist() if "name" in columns else ())


def frontage_chains(
    edges_json: str | Sequence[Sequence[object]],
    bearings: Sequence[float],
) -> tuple[tuple[Edge, ...], ...]:
    """The lot's street frontages, split where a corner turns."""
    import json

    raw = json.loads(edges_json) if isinstance(edges_json, str) else edges_json
    edges: list[Edge] = []
    for row in raw:
        if len(row) < 5:
            continue
        x1, y1, x2, y2 = (float(v) for v in row[:4])
        length = math.hypot(x2 - x1, y2 - y1)
        if length <= 0:
            continue
        cls = EdgeClass.front if row[4] == "F" else EdgeClass.side
        edges.append(Edge(x1, y1, x2, y2, length, bearing_deg(x1, y1, x2, y2), cls))
    if not edges:
        return ()
    bounds = LotEdges(
        tier=Tier.corner if len(bearings) >= 2 else Tier.clean,
        edges=tuple(edges),
        front_bearings=tuple(float(b) for b in bearings[:2]),
        frontage_ft=sum(e.length_ft for e in edges if e.cls is EdgeClass.front),
        convexity=1.0,
    )
    return street_chains(bounds)


def maximum_clearance_ft(
    edges_json: str | Sequence[Sequence[object]],
    bearings: Sequence[float],
    streets: StreetNetwork | None,
    apron_width_ft: float | None,
    street_half_widths_ft: Mapping[str, float] | None = None,
) -> float | None:
    """A proved clearance, or None if the result is indeterminate.

    A known frontage that cannot fit an apron is a zero-clearance result. An
    unmeasurable frontage prevents a failure conclusion unless another
    measured frontage already proves a legal placement. A returned clearance
    of at least 100 ft is reduced by the ROW and curb-return allowances; a
    returned clearance below 100 ft is the unadjusted centerline bound.
    """
    if streets is None or streets.tree is None or not apron_width_ft or apron_width_ft < 0:
        return None
    chains = frontage_chains(edges_json, bearings)
    if not chains:
        return None

    measured_failures: list[float] = []
    passing: list[float] = []
    unknown = False
    street_half_widths_ft = street_half_widths_ft or {}
    largest_half_width = max(
        (DEFAULT_CROSS_STREET_HALF_ROW_FT, *street_half_widths_ft.values())
    )
    for chain in chains:
        length = sum(edge.length_ft for edge in chain)
        chain_line = LineString(
            [(chain[0].x1, chain[0].y1), *((edge.x2, edge.y2) for edge in chain)]
        )
        chain_bearing = max(chain, key=lambda edge: edge.length_ft).bearing_deg
        reach = (
            FRONT_REACH_FT
            + DURHAM_APRON_MIN_CLEARANCE_FT
            + largest_half_width
            + CURB_RETURN_ALLOWANCE_FT
            + apron_width_ft
        )
        eligible_edges = [
            edge
            for edge in chain
            if edge.length_ft >= apron_width_ft
            or bearing_delta(edge.bearing_deg, chain_bearing) <= _PARALLEL_TOL_DEG
        ]
        chain_dx = chain[-1].x2 - chain[0].x1
        chain_dy = chain[-1].y2 - chain[0].y1
        forward_eligible_edges = [
            edge
            for edge in eligible_edges
            if (edge.x2 - edge.x1) * chain_dx
            + (edge.y2 - edge.y1) * chain_dy
            > 0.0
        ]
        if forward_eligible_edges:
            first = forward_eligible_edges[0]
            last = forward_eligible_edges[-1]
        else:
            forward_edges = [
                edge
                for edge in chain
                if (edge.x2 - edge.x1) * chain_dx
                + (edge.y2 - edge.y1) * chain_dy
                > 0.0
            ]
            if not forward_edges:
                unknown = True
                continue
            first = last = max(forward_edges, key=lambda edge: edge.length_ft)
        first_ux = (first.x2 - first.x1) / first.length_ft
        first_uy = (first.y2 - first.y1) / first.length_ft
        last_ux = (last.x2 - last.x1) / last.length_ft
        last_uy = (last.y2 - last.y1) / last.length_ft
        extended_chain = LineString(
            [
                (chain[0].x1 - first_ux * reach, chain[0].y1 - first_uy * reach),
                *list(chain_line.coords),
                (chain[-1].x2 + last_ux * reach, chain[-1].y2 + last_uy * reach),
            ]
        )
        nearest_names: set[str] = set()
        chain_measured = True
        for edge in eligible_edges:
            line = LineString(((edge.x1, edge.y1), (edge.x2, edge.y2)))
            middle = line.interpolate(line.length / 2.0)
            own_bearing = edge.bearing_deg
            near = streets.tree.query(
                middle, predicate="dwithin", distance=FRONT_REACH_FT
            )
            ranked: list[tuple[float, int]] = []
            for idx in near:
                idx = int(idx)
                road = streets.geoms[idx]
                road_bearing = _bearing(road, middle)
                if road_bearing is None or bearing_delta(own_bearing, road_bearing) > _PARALLEL_TOL_DEG:
                    continue
                distance = float(road.distance(middle))
                ranked.append((distance, idx))
            if not ranked:
                chain_measured = False
                break

            nearest = min(d for d, _ in ranked)
            nearest_names.update(
                streets.names[idx]
                for distance, idx in ranked
                if distance <= nearest + 1e-6 and streets.names[idx]
            )

        if not chain_measured:
            unknown = True
            continue
        parallel: set[int] = set()
        nearby = streets.tree.query(
            chain_line.buffer(FRONT_REACH_FT), predicate="intersects"
        )
        for idx_raw in nearby:
            idx = int(idx_raw)
            road = streets.geoms[idx]
            for edge in eligible_edges:
                line = LineString(((edge.x1, edge.y1), (edge.x2, edge.y2)))
                if road.distance(line) > FRONT_REACH_FT:
                    continue
                connector = shapely.shortest_line(line, road)
                coords = shapely.get_coordinates(connector)
                road_point = Point(float(coords[-1][0]), float(coords[-1][1]))
                road_bearing = _bearing(road, road_point)
                if (
                    road_bearing is not None
                    and bearing_delta(edge.bearing_deg, road_bearing)
                    <= _PARALLEL_TOL_DEG
                ):
                    parallel.add(idx)
                    break
        frontage_segments = [
            idx
            for idx in parallel
            if not nearest_names
            or not streets.names[idx]
            or streets.names[idx] in nearest_names
        ]
        candidates = streets.tree.query(
            chain_line.buffer(reach), predicate="intersects"
        )
        junctions: dict[tuple[float, float], tuple[float, float]] = {}
        for primary_idx in frontage_segments:
            primary = streets.geoms[primary_idx]
            for other_idx_raw in candidates:
                other_idx = int(other_idx_raw)
                if other_idx == primary_idx:
                    continue
                other = streets.geoms[other_idx]
                if (
                    streets.names[primary_idx]
                    and streets.names[primary_idx] == streets.names[other_idx]
                ):
                    continue
                hit = shapely.intersection(primary, other)
                if hit.is_empty:
                    continue
                for point in shapely.get_parts(hit):
                    if point.geom_type != "Point" or point.is_empty:
                        continue
                    other_bearing = _bearing(other, point)
                    primary_bearing = _bearing(primary, point)
                    if (
                        other_bearing is None
                        or primary_bearing is None
                        or bearing_delta(other_bearing, primary_bearing) <= _COLLINEAR_TOL_DEG
                    ):
                        continue
                    if point.distance(chain_line) > reach:
                        continue
                    station = float(
                        shapely.line_locate_point(extended_chain, point) - reach
                    )
                    street_name = _street_key(streets.names[other_idx])
                    half_width = street_half_widths_ft.get(
                        street_name, DEFAULT_CROSS_STREET_HALF_ROW_FT
                    )
                    if not math.isfinite(half_width) or half_width < 0:
                        half_width = DEFAULT_CROSS_STREET_HALF_ROW_FT
                    key = (round(float(point.x), 6), round(float(point.y), 6))
                    old = junctions.get(key)
                    allowance = half_width + CURB_RETURN_ALLOWANCE_FT
                    junctions[key] = (
                        station,
                        max(allowance, old[1]) if old else allowance,
                    )
        events = list(junctions.values())
        centerline_clearance = _best_clearance(
            length, [station for station, _ in events], apron_width_ft
        )
        if centerline_clearance < DURHAM_APRON_MIN_CLEARANCE_FT:
            measured_failures.append(centerline_clearance)
            continue
        conservative_clearance = _best_clearance_with_allowances(
            length, events, apron_width_ft
        )
        if conservative_clearance >= DURHAM_APRON_MIN_CLEARANCE_FT:
            passing.append(conservative_clearance)
        else:
            unknown = True

    if passing:
        return max(passing)
    if unknown or not measured_failures:
        return None
    return max(measured_failures)


def _best_clearance(length: float, events: Sequence[float], width: float) -> float:
    if width > length:
        return 0.0
    if not events:
        return DURHAM_APRON_MIN_CLEARANCE_FT

    ordered = sorted(events)
    latest_start = length - width
    candidates = {0.0, latest_start}
    for i, left in enumerate(ordered):
        for right in ordered[i + 1 :]:
            candidates.add(min(latest_start, max(0.0, (left + right - width) / 2.0)))

    best = 0.0
    for start in candidates:
        end = start + width
        clearance = min(max(start - point, point - end, 0.0) for point in ordered)
        best = max(best, clearance)
    return best


def _best_clearance_with_allowances(
    length: float, events: Sequence[tuple[float, float]], width: float
) -> float:
    """Maximise centerline clearance after each intersection's allowances."""
    if width > length:
        return 0.0
    if not events:
        return DURHAM_APRON_MIN_CLEARANCE_FT

    latest_start = length - width
    candidates = {0.0, latest_start}
    branches: list[tuple[float, float]] = []
    for station, allowance in events:
        candidates.update((station - width, station))
        branches.extend(
            (
                (1.0, -station - allowance),
                (-1.0, station - width - allowance),
                (0.0, -allowance),
            )
        )
    for i, (left_slope, left_intercept) in enumerate(branches):
        for right_slope, right_intercept in branches[i + 1 :]:
            if left_slope == right_slope:
                continue
            start = (right_intercept - left_intercept) / (
                left_slope - right_slope
            )
            if 0.0 <= start <= latest_start:
                candidates.add(start)

    best = -math.inf
    for start in candidates:
        if not 0.0 <= start <= latest_start:
            continue
        end = start + width
        clearance = min(
            max(start - station, station - end, 0.0) - allowance
            for station, allowance in events
        )
        best = max(best, clearance)
    return best


def _street_key(name: str) -> str:
    from flats.geom.street_class import street_key

    return street_key(name)


def _bearing(line: BaseGeometry, point: Point) -> float | None:
    length = float(shapely.length(line))
    if length <= 0:
        return None
    at = float(shapely.line_locate_point(line, point))
    a = shapely.line_interpolate_point(line, max(at - _BEARING_HALF_RUN_FT, 0.0))
    b = shapely.line_interpolate_point(line, min(at + _BEARING_HALF_RUN_FT, length))
    (x1, y1), (x2, y2) = shapely.get_coordinates([a, b])
    if math.hypot(x2 - x1, y2 - y1) <= 1e-9:
        return None
    return bearing_deg(float(x1), float(y1), float(x2), float(y2))


__all__ = [
    "CURB_RETURN_ALLOWANCE_FT",
    "DEFAULT_CROSS_STREET_HALF_ROW_FT",
    "DURHAM_APRON_MIN_CLEARANCE_FT",
    "StreetNetwork",
    "frontage_chains",
    "load_street_network",
    "maximum_clearance_ft",
]
