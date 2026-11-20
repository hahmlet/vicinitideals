"""Reading the elevation models under a drawn building (FD6 build step 8).

Copied from the code that produced the lot file's six readings, so the grid and
the six readings come from the same ground, read the same way:

* :class:`Dem` is ``flats/fit/slope.py`` ``Terrain.__init__``, ``_read`` and
  ``_fine`` (main), reading only: the 1 m lidar tiles (quadfit ``raw/dem``, UTM
  10N) and the ~10 m USGS model warped beside them (``raw/dem10_utm``);
* :meth:`Dem.z_reader` is ``scripts/flats_fd2_pass1.py`` ``_z_reader()`` (branch
  ``flats/fd2-pass1`` at 56806fe1): a window 120 ft round the footprint, 1 m
  first, the 10 m model when more than half the 1 m window is blank, bilinear
  between cell centres, metres to feet.

Opens files lazily and reads one small window per lot, so one process stays far
under 1 GB. Needs rasterio and pyproj (the venv on LXC 137 has both).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import Any

CRS_WORKING = "EPSG:2913"
FT_PER_M = 3.28084
PAD_FT = 120.0  # _z_reader's window round the footprint
ONE_M, TEN_M = "dem_1m", "dem_10m"


class Dem:
    """The elevation models, opened once per process (reading only)."""

    def __init__(self, dem_dir: Path | None, coarse: Path | None = None) -> None:
        import rasterio

        self.tiles = []
        if dem_dir is not None and Path(dem_dir).is_dir():
            self.tiles = [rasterio.open(p) for p in sorted(Path(dem_dir).glob("*.tif"))]
        self.coarse = None
        if coarse is not None:
            path = Path(coarse)
            found = sorted(path.glob("*.tif")) if path.is_dir() else [path]
            if found and found[0].exists():
                self.coarse = rasterio.open(found[0])
        crs = (self.tiles[0] if self.tiles else self.coarse).crs if (self.tiles or self.coarse) else None
        self._fwd = None
        if crs is not None:
            from pyproj import Transformer

            self._fwd = Transformer.from_crs(CRS_WORKING, crs, always_xy=True)

    def _read(self, ds: Any, bounds: tuple[float, float, float, float]) -> tuple[Any, Any] | None:
        import numpy as np
        from rasterio.windows import from_bounds

        win = from_bounds(*bounds, transform=ds.transform).round_offsets().round_lengths()
        if win.width < 1 or win.height < 1:
            return None
        a = ds.read(1, window=win, boundless=True, fill_value=np.nan, masked=False).astype(np.float64)
        nodata = ds.nodata
        if nodata is not None and not (isinstance(nodata, float) and math.isnan(nodata)):
            a[a == nodata] = np.nan
        a[a < -1000] = np.nan
        return a, ds.window_transform(win)

    def _fine(self, bounds: tuple[float, float, float, float]) -> tuple[Any, Any] | None:
        """1 m elevations over ``bounds``, stitched across tiles, gaps NaN."""
        import numpy as np

        left, bottom, right, top = bounds
        hit = [
            ds
            for ds in self.tiles
            if ds.bounds.left < right and ds.bounds.right > left and ds.bounds.bottom < top and ds.bounds.top > bottom
        ]
        if not hit:
            return None
        base = self._read(hit[0], bounds)
        if base is None:
            return None
        a, tf = base
        for ds in hit[1:]:
            more = self._read(ds, bounds)
            if more is None or more[0].shape != a.shape:
                continue
            gap = np.isnan(a)
            a[gap] = more[0][gap]
        return a, tf

    def z_reader(self, ring: Any) -> tuple[Callable[[Any], Any] | None, str | None, float | None]:
        """A function from (N, 2) EPSG:2913 points to ground (ft) round the
        footprint ``ring``, the model used, and its cell size (m)."""
        import numpy as np
        import shapely

        if self._fwd is None:
            return None, None, None
        fp = shapely.Polygon(ring)
        b = fp.buffer(PAD_FT).bounds
        fx, fy = self._fwd.transform([b[0], b[2], b[0], b[2]], [b[1], b[1], b[3], b[3]])
        bounds = (min(fx), min(fy), max(fx), max(fy))
        got = self._fine(bounds) if self.tiles else None
        source = ONE_M
        if got is None or np.isnan(got[0]).mean() > 0.5:
            got = self._read(self.coarse, bounds) if self.coarse is not None else None
            source = TEN_M
            if got is not None and np.isnan(got[0]).all():
                got = None
        if got is None:
            return None, None, None
        raw, tf = got
        cell = abs(tf.a)
        fwd = self._fwd

        def z_of(pts: Any) -> Any:
            pts = np.asarray(pts, dtype=float).reshape(-1, 2)
            if not len(pts):
                return np.zeros(0)
            x, y = fwd.transform(pts[:, 0], pts[:, 1])
            col = (np.asarray(x) - tf.c) / tf.a - 0.5
            row = (np.asarray(y) - tf.f) / tf.e - 0.5
            c0 = np.floor(col).astype(int)
            r0 = np.floor(row).astype(int)
            dc = col - c0
            dr = row - r0
            h, w = raw.shape
            ok = (c0 >= 0) & (r0 >= 0) & (c0 + 1 < w) & (r0 + 1 < h)
            out = np.full(len(pts), np.nan)
            if ok.any():
                cc, rr, a, bb = c0[ok], r0[ok], dc[ok], dr[ok]
                z = (
                    raw[rr, cc] * (1 - a) * (1 - bb)
                    + raw[rr, cc + 1] * a * (1 - bb)
                    + raw[rr + 1, cc] * (1 - a) * bb
                    + raw[rr + 1, cc + 1] * a * bb
                )
                out[ok] = z * FT_PER_M
            return out

        return z_of, source, cell
