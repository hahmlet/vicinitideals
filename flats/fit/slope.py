"""Steep ground on a lot, and the grade under a plan (FOLLOWUPS 38).

Steph, 2026-10-04: "slope-based lot elimination should happen before pod
placement ... for any small lot, 16% slope on any part of it likely
eliminates it. The more thorough way would be to measure how much of the
lot is sloped like that and subtract it and see if there's even enough land
for the pod." And for the ground the plan does stand on: up to 5% is GREEN,
5 to 15% is a closer look (a stepped foundation or retaining walls, a cost
to price), over 15% is RED.

Two measurements, both off the bare-earth elevation models quadfit already
holds (s0's USGS 3DEP 1 m lidar tiles, and the ~10 m national DEM where no
1 m product exists -- Gresham, Troutdale, Fairview, Wood Village and the
eastern third of Portland):

* :meth:`Terrain.steep` -- the part of a lot steeper than a grade, taken off
  the ground the pod and its parking may use, the same way a hillside
  overlay's carve is. A slope is read over a RUN (``run_m``: the 1 m
  elevations averaged over a square that wide, about 16 ft), never pixel
  to pixel: the 1 m model resolves curbs, ditches and the cut round a
  basement, and pixel slope read every flat Portland lot at twice its real
  grade (FOLLOWUPS 38: 5.9% mean on 1 m against 3.1% on 10 m). The 10 m
  model is read cell to cell -- a cell is already wider than the run.
* :meth:`Terrain.grade` -- the fall across the ground a plan's building and
  court stand on: the plane that best fits every elevation under them, its
  steepest direction as a percentage. One number for the whole pad, which
  is what a builder grades to; micro-relief inside it averages out.

Both return the model that answered (:data:`ONE_M` or :data:`TEN_M`) so the
screen can say how much a number is worth. None where neither model covers
the ground.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

#: The working CRS every geometry here arrives and leaves in (feet).
CRS_WORKING = "EPSG:2913"
#: Which model answered.
ONE_M = "dem_1m"
TEN_M = "dem_10m"
#: Steep patches smaller than this are dropped, square feet: a single
#: smoothed cell over the line is a wall or a bank, not a hillside.
MIN_PATCH_SQFT = 100.0
SQFT_PER_SQM = 10.763910416709722
FT_PER_M = 3.280839895013123


#: Steph's slope ruling (HUMAN-OWNED).
RULES_PATH = Path(__file__).resolve().parents[1] / "config" / "slope.yaml"


@dataclass(frozen=True, slots=True)
class SlopeRules:
    """``flats/config/slope.yaml``: Steph's cut-offs of 2026-10-04."""

    steep_over_pct: float
    grade_green_max_pct: float
    grade_red_over_pct: float
    run_m: float
    coarse_red_is_closer_look: bool
    #: A steep patch whose ground falls less than this from its top to its
    #: bottom, feet, is a bank to regrade, not land lost; 0 counts every one.
    min_bank_ft: float = 0.0
    #: Whether steep ground inside the setbacks comes off the court's ground
    #: too, or only steep ground where the building may stand counts.
    steep_in_setbacks: bool = True

    def band(self, pct: float, source: str) -> str:
        """``green``, ``closer`` or ``red`` for a grade read off ``source``."""
        if pct <= self.grade_green_max_pct:
            return "green"
        if pct > self.grade_red_over_pct and not (
            source != ONE_M and self.coarse_red_is_closer_look
        ):
            return "red"
        return "closer"


@lru_cache(maxsize=None)
def load_rules(path: Path = RULES_PATH) -> SlopeRules:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    got = SlopeRules(
        steep_over_pct=float(raw["steep_over_pct"]),
        grade_green_max_pct=float(raw["grade_green_max_pct"]),
        grade_red_over_pct=float(raw["grade_red_over_pct"]),
        run_m=float(raw["run_m"]),
        coarse_red_is_closer_look=bool(raw["coarse_red_is_closer_look"]),
        min_bank_ft=float(raw.get("min_bank_ft", 0.0)),
        steep_in_setbacks=bool(raw.get("steep_in_setbacks", True)),
    )
    if not 0 < got.grade_green_max_pct <= got.grade_red_over_pct:
        raise ValueError(f"{path}: the green line must sit at or under the red one")
    if got.run_m < 1:
        raise ValueError(f"{path}: run_m is metres over a 1 m model, at least 1")
    if got.min_bank_ft < 0:
        raise ValueError(f"{path}: min_bank_ft is a height, 0 or more")
    return got


@dataclass(frozen=True, slots=True)
class Steep:
    """The steep part of one lot."""

    #: The ground steeper than the grade asked, in the working CRS; empty
    #: where none of the lot is.
    geom: Any
    #: Its area, square feet.
    sqft: float
    #: The model that answered.
    source: str
    #: Square feet of the lot at or steeper than each grade the caller asked
    #: (``areas_over``), every short bank and small patch included: the
    #: figure a code's "slopes over 25 percent" deducts, not the ground the
    #: pod gives up.
    areas: dict[float, float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Grade:
    """The fall across the ground one plan stands on."""

    pct: float
    source: str
    #: How many elevation cells the plane was fitted to.
    cells: int


def _box_mean(a: Any, k: int) -> Any:
    """Each cell's mean over the k x k square centred on it (k odd), NaN
    where the square reaches past the array."""
    import numpy as np

    h, w = a.shape
    out = np.full(a.shape, np.nan, dtype=np.float64)
    if h < k or w < k:
        return out
    c = np.zeros((h + 1, w + 1), dtype=np.float64)
    c[1:, 1:] = np.cumsum(np.cumsum(a, axis=0), axis=1)
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    r = k // 2
    out[r : r + h - k + 1, r : r + w - k + 1] = s / (k * k)
    return out


class Terrain:
    """The elevation models, opened once per process.

    ``dem_dir`` holds the 1 m tiles (s0's ``raw/dem``); ``coarse`` is the
    ~10 m model warped to the same CRS (s0's ``raw/dem10_utm``, a file or the
    directory holding it). Either may be missing: a lot neither covers gets
    None from every measurement.
    """

    def __init__(
        self, dem_dir: Path | None, coarse: Path | None = None, *, run_m: float | None = None
    ) -> None:
        import rasterio

        self.run_m = float(run_m if run_m is not None else load_rules().run_m)

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
        self._fwd = self._back = None
        if crs is not None:
            from pyproj import Transformer

            self._fwd = Transformer.from_crs(CRS_WORKING, crs, always_xy=True)
            self._back = Transformer.from_crs(crs, CRS_WORKING, always_xy=True)

    # -- reading --------------------------------------------------------------

    def _to(self, geom: Any, tf: Any) -> Any:
        import numpy as np
        import shapely

        def fn(xy: Any) -> Any:
            x, y = tf.transform(xy[:, 0], xy[:, 1])
            return np.column_stack([x, y])

        return shapely.transform(geom, fn)

    def _read(self, ds: Any, bounds: tuple[float, float, float, float]) -> tuple[Any, Any] | None:
        """Elevations inside ``bounds`` (model CRS) from one dataset, NaN
        off it, and the window's transform."""
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
        """1 m elevations over ``bounds``, stitched across tiles; None where
        any cell is uncovered."""
        import numpy as np

        left, bottom, right, top = bounds
        hit = [
            ds for ds in self.tiles
            if ds.bounds.left < right and ds.bounds.right > left
            and ds.bounds.bottom < top and ds.bounds.top > bottom
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
        if np.isnan(a).any():
            return None
        return a, tf

    def _slope_pct(self, geom_m: Any) -> tuple[Any, Any, str, Any] | None:
        """Slope % over the box round ``geom_m`` (model CRS), read over the
        run on 1 m, cell to cell on 10 m; the grid's transform; the model;
        the elevations as read, before any averaging."""
        import numpy as np

        k = max(int(round(self.run_m)) | 1, 3)
        pad = k + 2.0
        b = geom_m.bounds
        got = self._fine((b[0] - pad, b[1] - pad, b[2] + pad, b[3] + pad)) if self.tiles else None
        if got is not None:
            raw, tf = got
            z = _box_mean(raw, k)
            source = ONE_M
        elif self.coarse is not None:
            res = self.coarse.res[0]
            got = self._read(self.coarse, (b[0] - 2 * res, b[1] - 2 * res, b[2] + 2 * res, b[3] + 2 * res))
            if got is None or np.isnan(got[0]).all():
                return None
            z, tf = got
            raw = z
            source = TEN_M
        else:
            return None
        if z.shape[0] < 3 or z.shape[1] < 3:
            return None
        gy, gx = np.gradient(z, abs(tf.e), tf.a)
        return np.hypot(gx, gy) * 100.0, tf, source, raw

    # -- measuring ------------------------------------------------------------

    def steep(
        self,
        lot: Any,
        over_pct: float,
        *,
        min_bank_ft: float = 0.0,
        areas_over: tuple[float, ...] = (),
    ) -> Steep | None:
        """The part of ``lot`` (working CRS) steeper than ``over_pct``.

        A patch whose ground, inside the lot, falls less than ``min_bank_ft``
        from its highest cell to its lowest is left out: a raised front yard
        or a terrace wall, which the run reads as a strip of steep ground
        but a builder regrades.

        ``areas_over`` asks, off the same reading, how much of the lot is at
        or steeper than each of those grades (:attr:`Steep.areas`): the cells
        whose centres fall inside the lot, counted.
        """
        import numpy as np
        import shapely
        from rasterio.features import geometry_mask, shapes
        from shapely.geometry import shape

        if self._fwd is None or lot is None or lot.is_empty:
            return None
        lot_m = self._to(lot, self._fwd)
        got = self._slope_pct(lot_m)
        if got is None:
            return None
        pct, tf, source, raw = got
        grades = np.nan_to_num(pct, nan=0.0)
        areas: dict[float, float] = {}
        if areas_over:
            on_lot = geometry_mask(
                [lot_m.__geo_interface__], out_shape=grades.shape, transform=tf, invert=True
            )
            cell_sqft = abs(tf.a * tf.e) * SQFT_PER_SQM
            for at in areas_over:
                areas[at] = float(np.count_nonzero(on_lot & (grades >= at))) * cell_sqft
        mask = grades > over_pct
        if not mask.any():
            return Steep(shapely.Polygon(), 0.0, source, areas)
        polys = [
            shape(g) for g, v in shapes(mask.astype(np.uint8), mask=mask, transform=tf) if v == 1
        ]
        steep_m = shapely.union_all(polys).intersection(lot_m)
        if min_bank_ft > 0 and not steep_m.is_empty:

            def fall_ft(part: Any) -> float:
                cells = geometry_mask(
                    [part.__geo_interface__], out_shape=raw.shape, transform=tf,
                    invert=True, all_touched=True,
                ) & ~np.isnan(raw)
                if not cells.any():
                    return 0.0
                return float(np.nanmax(raw[cells]) - np.nanmin(raw[cells])) * FT_PER_M

            tall = [
                p for p in getattr(steep_m, "geoms", [steep_m])
                if p.area > 0 and fall_ft(p) >= min_bank_ft
            ]
            steep_m = shapely.union_all(tall) if tall else shapely.Polygon()
        steep = self._to(steep_m, self._back).buffer(0)
        parts = [p for p in getattr(steep, "geoms", [steep]) if p.area >= MIN_PATCH_SQFT]
        steep = shapely.union_all(parts) if parts else shapely.Polygon()
        return Steep(steep, float(steep.area), source, areas)

    def grade(self, ground: Iterable[Any]) -> Grade | None:
        """The fall across ``ground`` (working-CRS polygons: a plan's
        building and court), as the steepest direction of the plane that
        best fits the elevations under it."""
        import numpy as np
        import shapely
        from rasterio.features import geometry_mask

        if self._fwd is None:
            return None
        pad = shapely.union_all([g for g in ground if g is not None and not g.is_empty])
        if pad.is_empty:
            return None
        pad_m = self._to(pad, self._fwd)
        b = pad_m.bounds
        got = self._fine((b[0] - 1, b[1] - 1, b[2] + 1, b[3] + 1)) if self.tiles else None
        source = ONE_M
        if got is None and self.coarse is not None:
            # A pad is two or three 10 m cells across: read every cell the
            # pad's box touches, and its neighbours, so the plane is fitted
            # to the hillside the pad sits in rather than to three points.
            res = self.coarse.res[0]
            got = self._read(self.coarse, (b[0] - res, b[1] - res, b[2] + res, b[3] + res))
            source = TEN_M
            if got is not None:
                z, tf = got
                inside = ~np.isnan(z)
                return self._plane(z, tf, inside, source)
        if got is None:
            return None
        z, tf = got
        inside = geometry_mask(
            [pad_m.__geo_interface__], out_shape=z.shape, transform=tf, invert=True, all_touched=True
        ) & ~np.isnan(z)
        return self._plane(z, tf, inside, source)

    @staticmethod
    def _plane(z: Any, tf: Any, inside: Any, source: str) -> Grade | None:
        import numpy as np

        rows, cols = np.nonzero(inside)
        if rows.size < 4:
            return None
        x = tf.c + (cols + 0.5) * tf.a
        y = tf.f + (rows + 0.5) * tf.e
        a = np.column_stack([x - x.mean(), y - y.mean(), np.ones_like(x)])
        (gx, gy, _), *_ = np.linalg.lstsq(a, z[rows, cols], rcond=None)
        return Grade(float(math.hypot(gx, gy) * 100.0), source, int(rows.size))
