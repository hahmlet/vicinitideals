"""Shared geographic utilities: polygon loading, point-in-polygon, bbox clipping."""
from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from app.config import settings


def load_polygons(path: str | None = None) -> list[dict[str, Any]]:
    """Read the polygons JSON file. Returns only polygons with is_active=true."""
    p = Path(path or settings.loopnet_polygon_path)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return [poly for poly in data if poly.get("is_active")]


def polygon_bbox(points: Sequence[Sequence[float]]) -> tuple[float, float, float, float]:
    """Return (minLng, minLat, maxLng, maxLat)."""
    lngs = [p[0] for p in points]
    lats = [p[1] for p in points]
    return (min(lngs), min(lats), max(lngs), max(lats))


def point_in_polygon(points: Sequence[Sequence[float]], lng: float, lat: float) -> bool:
    """Ray-casting point-in-polygon test. Points are [lng, lat] pairs."""
    n = len(points)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = points[i][0], points[i][1]
        xj, yj = points[j][0], points[j][1]
        if (yi > lat) != (yj > lat):
            x_intersect = (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi
            if lng < x_intersect:
                inside = not inside
        j = i
    return inside


def clip_to_polygon(
    rows: Iterable[dict[str, Any]],
    polygon_points: Sequence[Sequence[float]],
) -> list[dict[str, Any]]:
    """Single-polygon variant — kept for loopnet_ingest compatibility."""
    survivors = []
    for row in rows:
        coords = row.get("coordinations") or []
        if not coords:
            continue
        if any(point_in_polygon(polygon_points, c[0], c[1]) for c in coords):
            survivors.append(row)
    return survivors


def clip_to_polygons(
    rows: Iterable[dict[str, Any]],
    polygons: list[dict[str, Any]],
    *,
    coord_key: str = "coordinations",
) -> list[dict[str, Any]]:
    """Keep rows whose coordinates fall inside any active polygon.

    coord_key: the dict key holding a list of [lng, lat] pairs per row.
    """
    if not polygons:
        return list(rows)
    survivors = []
    for row in rows:
        coords = row.get(coord_key) or []
        if not coords:
            continue
        for poly in polygons:
            pts = poly.get("points", [])
            if any(point_in_polygon(pts, c[0], c[1]) for c in coords):
                survivors.append(row)
                break
    return survivors
