"""Synthetic elevation models for the slope tests (FOLLOWUPS 38).

A GeoTIFF in the CRS s0's real tiles carry (UTM 10N, EPSG:26910), covering
a box given in the working CRS (EPSG:2913, feet) and a margin round it, its
elevations whatever ``z`` says at each cell's centre (metres east, metres
north, both from the box's south-west corner).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

UTM = "EPSG:26910"


def plane(pct: float) -> Callable[[Any, Any], Any]:
    """Ground rising ``pct`` percent eastward."""
    return lambda x, y: x * pct / 100.0


def write_dem(
    path: Path,
    box_2913: tuple[float, float, float, float],
    z: Callable[[Any, Any], Any],
    *,
    res_m: float = 1.0,
    margin_m: float = 60.0,
) -> Path:
    import numpy as np
    import rasterio
    from pyproj import Transformer
    from rasterio.transform import from_origin

    tf = Transformer.from_crs("EPSG:2913", UTM, always_xy=True)
    xs, ys = tf.transform(
        [box_2913[0], box_2913[2], box_2913[0], box_2913[2]],
        [box_2913[1], box_2913[1], box_2913[3], box_2913[3]],
    )
    left, bottom = min(xs) - margin_m, min(ys) - margin_m
    right, top = max(xs) + margin_m, max(ys) + margin_m
    width = int(np.ceil((right - left) / res_m))
    height = int(np.ceil((top - bottom) / res_m))
    cols, rows = np.meshgrid(np.arange(width), np.arange(height))
    east = (cols + 0.5) * res_m - (min(xs) - left)
    north = (top - (rows + 0.5) * res_m) - min(ys)
    elev = (100.0 + z(east, north)).astype("float32")
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=width,
        height=height,
        count=1,
        dtype="float32",
        crs=UTM,
        transform=from_origin(left, top, res_m, res_m),
        nodata=-999999.0,
    ) as out:
        out.write(elev, 1)
    return path
