"""s5o — overlay carve, slope statistics, sewer proximity (phase 2).

Runs between s5 (setback envelope) and s6 (rectangle fit). Everything here is
driven by config/overlays.yaml (see common.OverlaysConfig):

- For EVERY configured overlay whose raw layer exists: per-lot any-touch flag
  `ovl_<key>` (lot shrunk 0.5 ft so boundary contact doesn't count) plus
  intersection area `ovl_<key>_sqft` — s7 applies kill/flag policy from these
  columns, so kill/flag reclassification is an s7-only re-run.
- CARVE overlays additionally subtract their (buffer_ft-buffered) geometry
  from the setback envelope -> `geom` becomes the carved envelope that s6
  fits against (envelope_carved_sqft records the loss). Changing a carve
  buffer therefore needs s5o+s6+s7 (~40 min), documented in README.
- Slope: per-lot mean/p85/max slope %, computed from USGS 3DEP 1 m DEM tiles
  over the carved envelope (falls back to the lot when the envelope is
  empty). Tier cutlines live in config and are applied at s7 time.
- Sewer: distance (ft) from the lot to the nearest mapped sewer main across
  all util_sewer_* layers. Unincorporated pockets have no public layer —
  distances there are to Portland/Gresham mains and are a proxy only.

Missing raw layers or DEM tiles degrade gracefully: the affected columns are
skipped/NaN and the gap is printed so the report can caveat it.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import DATA_DIR, load_geojson_features, load_overlays, read_stage, write_stage

RAW_DIR = DATA_DIR / "raw"
# 1/3 arc-second (~10 m) national DEM, pre-warped to the 1 m tiles'
# CRS by s0. Stands in east of the metro lidar footprint.
DEM10_DIR = RAW_DIR / "dem10_utm"
SHRINK_FT = 0.5  # any-touch test excludes pure boundary contact
SEWER_LAYERS = [
    "util_sewer_portland", "util_sewer_gresham", "util_sewer_troutdale",
    "util_sewer_fairview", "util_sewer_wood_village",
    # Clackamas (5 of 8 cities publish public mains; WES/CWS gaps stay NaN)
    "util_sewer_oregon_city", "util_sewer_wilsonville", "util_sewer_west_linn",
    "util_sewer_milwaukie", "util_sewer_gladstone",
]


def _load_layer_geoms(key: str):
    """Valid shapely geometries for one raw layer, or None if file absent."""
    import shapely

    path = RAW_DIR / f"{key}.geojson"
    if not path.exists():
        return None
    geoms = []
    for f in load_geojson_features(path):
        g = f.get("geometry")
        if not g:
            continue
        try:
            geom = shapely.make_valid(shapely.geometry.shape(g))
        except Exception:
            continue
        if not geom.is_empty:
            geoms.append(geom)
    return geoms


def overlay_columns(lots, spec, geoms):
    """(flags, sqft) per lot for one overlay layer via STRtree."""
    import numpy as np
    import shapely
    from shapely.strtree import STRtree

    n = len(lots)
    flags = np.zeros(n, dtype=bool)
    sqft = np.zeros(n)
    tree = STRtree(geoms)
    garr = np.array(geoms, dtype=object)
    for i, (jur, geom) in enumerate(zip(lots["jurisdiction"], lots["lot_geom"])):
        if not spec.applies_to(jur):
            continue
        shrunk = shapely.buffer(geom, -SHRINK_FT)
        if shrunk.is_empty:
            shrunk = geom
        idx = tree.query(shrunk, predicate="intersects")
        if len(idx) == 0:
            continue
        flags[i] = True
        inter = 0.0
        for g in garr[idx]:
            try:
                inter += shapely.intersection(geom, g).area
            except Exception:
                pass
        sqft[i] = inter
    return flags, sqft


def carve_envelopes(lots, carve_specs, layer_geoms):
    """Subtract buffered carve-overlay geometry from each lot's envelope."""
    import numpy as np
    import shapely
    from shapely.strtree import STRtree

    # One buffered tree per carve layer (buffer once, not per lot).
    trees = []
    for spec in carve_specs:
        geoms = layer_geoms[spec.key]
        if spec.buffer_ft > 0:
            geoms = [shapely.buffer(g, spec.buffer_ft) for g in geoms]
        trees.append((spec, STRtree(geoms), np.array(geoms, dtype=object)))

    carved = []
    for jur, env in zip(lots["jurisdiction"], lots["geom"]):
        out = env
        if out is not None and not out.is_empty:
            for spec, tree, garr in trees:
                if not spec.applies_to(jur):
                    continue
                idx = tree.query(out, predicate="intersects")
                for g in garr[idx]:
                    out = shapely.difference(out, g)
                    if out.is_empty:
                        break
                if out.is_empty:
                    break
        carved.append(out)
    return carved


class DemIndex:
    """Window-read slope stats from 3DEP 1 m tiles (slope computed per tile
    lazily via elevation gradient, cached in memory as float16 arrays)."""

    def __init__(self, dem_dir: Path):
        import rasterio

        self.tiles = []
        for tif in sorted(dem_dir.glob("*.tif")):
            ds = rasterio.open(tif)
            self.tiles.append(ds)
        self.crs = self.tiles[0].crs if self.tiles else None
        self._transformer = None
        self._slope_cache: dict[int, object] = {}

    def _to_dem_crs(self, geom):
        import shapely
        from pyproj import Transformer

        from common import CRS_WORKING

        if self._transformer is None:
            self._transformer = Transformer.from_crs(
                CRS_WORKING, self.crs, always_xy=True)

        def _fn(coords):
            import numpy as np

            x, y = self._transformer.transform(coords[:, 0], coords[:, 1])
            return np.column_stack([x, y])

        return shapely.transform(geom, _fn)

    def _tile_slope(self, ti: int):
        """Full-tile slope %, computed once from elevation gradient."""
        import numpy as np

        if ti in self._slope_cache:
            return self._slope_cache[ti]
        ds = self.tiles[ti]
        elev = ds.read(1, masked=True).filled(np.nan).astype(np.float32)
        px = ds.res[0]  # 1 m tiles; metres
        gy, gx = np.gradient(elev, px)
        slope = (np.sqrt(gx * gx + gy * gy) * 100.0).astype(np.float16)
        self._slope_cache[ti] = slope
        if len(self._slope_cache) > 4:  # keep memory bounded (~450MB/tile f16)
            self._slope_cache.pop(next(iter(self._slope_cache)))
        return slope

    def tile_of(self, geom_2913) -> int | None:
        """Index of the tile containing the geometry's centroid (None = off-DEM)."""
        if not self.tiles or geom_2913 is None or geom_2913.is_empty:
            return None
        g = self._to_dem_crs(geom_2913)
        cx, cy = g.centroid.x, g.centroid.y
        return next((i for i, ds in enumerate(self.tiles)
                     if ds.bounds.left <= cx <= ds.bounds.right
                     and ds.bounds.bottom <= cy <= ds.bounds.top), None)

    def stats(self, geom_2913) -> tuple[float, float, float]:
        """(mean, p85, max) slope % over the polygon; NaNs if no coverage."""
        import numpy as np
        from rasterio.errors import WindowError
        from rasterio.features import geometry_mask
        from rasterio.windows import from_bounds

        nan3 = (math.nan, math.nan, math.nan)
        ti = self.tile_of(geom_2913)
        if ti is None:
            return nan3
        g = self._to_dem_crs(geom_2913)
        ds = self.tiles[ti]
        b = g.bounds
        win = from_bounds(*b, transform=ds.transform).round_offsets().round_lengths()
        # Sliver/degenerate geometries can round to a zero-size window, and
        # Window.intersection RAISES on empty overlap — guard both.
        if win.width < 1 or win.height < 1:
            return nan3
        try:
            win = win.intersection(
                from_bounds(*ds.bounds, transform=ds.transform)
                .round_offsets().round_lengths())
        except WindowError:
            return nan3
        if win.width < 1 or win.height < 1:
            return nan3
        slope = self._tile_slope(ti)
        r0, c0 = int(win.row_off), int(win.col_off)
        patch = slope[r0:r0 + int(win.height), c0:c0 + int(win.width)]
        if patch.size == 0:
            return nan3
        mask = geometry_mask([g.__geo_interface__], out_shape=patch.shape,
                             transform=ds.window_transform(win), invert=True)
        vals = patch[mask & ~np.isnan(patch.astype(np.float32))]
        if vals.size == 0:
            return nan3
        v = vals.astype(np.float32)
        return float(v.mean()), float(np.percentile(v, 85)), float(v.max())


def _fill_from_coarse_dem(lots, tiers) -> None:
    """Fill slope columns from the ~10 m DEM wherever the 1 m one had nothing.

    3DEP's 1 m lidar for this metro comes from two projects (OR_PortlandMetro,
    OR_OLCMetro_2019) whose footprints stop at roughly UTM 10N easting 540,000
    -- about longitude -122.48. Everything east of that line has NO 1 m product
    at any vintage: Gresham, Troutdale, Fairview, Wood Village entirely, and
    Portland's eastern third. Those lots carried NaN slope, which s7 tiers as
    "unknown", which is a review trigger -- so four whole cities could never
    grade green for want of an elevation pixel, while `slope_coverage` in
    overlays.yaml called them grade A.

    The 1/3 arc-second national DEM is seamless and covers all of it. It is a
    coarser instrument, so the statistic is deliberately not the same one: a
    lot is one to four cells wide here, and the honest reading of a handful of
    cells is their MAXIMUM over a window around the lot, not a percentile
    across a polygon. `slope_source` records which DEM answered, and s7
    decides separately what a coarse answer is allowed to conclude.
    """
    import numpy as np
    import rasterio
    from pyproj import Transformer

    from common import CRS_WORKING

    tifs = sorted(DEM10_DIR.glob("*.tif")) if DEM10_DIR.exists() else []
    if not tifs:
        print("  slope: no coarse (10 m) DEM present — eastern lots stay NaN")
        return
    need = ~np.isfinite(np.asarray(lots["slope_p85_pct"], dtype=float))
    if not need.any():
        print("  slope: 1 m DEM covered every lot — coarse fallback unused")
        return

    ds = rasterio.open(tifs[0])
    elev = ds.read(1, masked=True).filled(np.nan).astype(np.float32)
    gy, gx = np.gradient(elev, ds.res[0])
    slope = (np.sqrt(gx * gx + gy * gy) * 100.0).astype(np.float32)

    tf = Transformer.from_crs(CRS_WORKING, ds.crs, always_xy=True)
    targets = [env if env is not None and not env.is_empty else lot_geom
               for env, lot_geom in zip(lots["geom"], lots["lot_geom"])]
    cx = np.array([g.centroid.x if g is not None and not g.is_empty else np.nan
                   for g in targets])
    cy = np.array([g.centroid.y if g is not None and not g.is_empty else np.nan
                   for g in targets])
    finite = np.isfinite(cx) & np.isfinite(cy)
    ux = np.full(len(cx), np.nan)
    uy = np.full(len(cy), np.nan)
    ux[finite], uy[finite] = tf.transform(cx[finite], cy[finite])

    rows, cols = rasterio.transform.rowcol(
        ds.transform, np.nan_to_num(ux, nan=ds.bounds.left - 1e6),
        np.nan_to_num(uy, nan=ds.bounds.bottom - 1e6))
    rows = np.asarray(rows)
    cols = np.asarray(cols)
    r = max(int(tiers.fallback_10m_window) // 2, 0)
    h, w = slope.shape
    inside = (rows >= r) & (rows < h - r) & (cols >= r) & (cols < w - r) & finite
    use = need & inside
    if not use.any():
        print("  slope: coarse DEM covers none of the 1 m gaps")
        return

    ri, ci = rows[use], cols[use]
    stack = np.stack([slope[ri + dr, ci + dc]
                      for dr in range(-r, r + 1)
                      for dc in range(-r, r + 1)], axis=1)
    with np.errstate(all="ignore"):
        agg = {"max": np.nanmax(stack, axis=1),
               "p95": np.nanpercentile(stack, 95, axis=1),
               "p85": np.nanpercentile(stack, 85, axis=1),
               "mean": np.nanmean(stack, axis=1)}[tiers.fallback_10m_stat]
        mean = np.nanmean(stack, axis=1)
        mx = np.nanmax(stack, axis=1)

    for col, vals in (("slope_p85_pct", agg), ("slope_mean_pct", mean),
                      ("slope_max_pct", mx)):
        cur = np.asarray(lots[col], dtype=float)
        cur[use] = vals
        lots[col] = cur
    src = np.asarray(lots["slope_source"], dtype=object)
    src[use] = "dem_10m"
    lots["slope_source"] = src
    print(f"  slope: coarse {tiers.fallback_10m_stat}{tiers.fallback_10m_window} "
          f"filled {int(use.sum()):,} of {int(need.sum()):,} lots the 1 m DEM "
          f"could not reach")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-slope", action="store_true")
    args = ap.parse_args()

    import numpy as np
    import shapely

    cfg = load_overlays()
    lots = read_stage("s5_lots")
    s3 = read_stage("s3_lots")[["TLID", "geom"]].rename(columns={"geom": "lot_geom"})
    lots = lots.merge(s3, on="TLID", how="left")
    print(f"s5o: {len(lots):,} lots, {len(cfg.overlays)} configured overlays")

    # Per-overlay any-touch flags + intersection area.
    layer_geoms: dict[str, list] = {}
    missing: list[str] = []
    for spec in cfg.overlays:
        geoms = _load_layer_geoms(f"overlay_{spec.key}")
        if geoms is None:
            missing.append(spec.key)
            continue
        layer_geoms[spec.key] = geoms
        flags, sqft = overlay_columns(lots, spec, geoms)
        lots[f"ovl_{spec.key}"] = flags
        lots[f"ovl_{spec.key}_sqft"] = sqft
        print(f"  ovl_{spec.key} [{spec.action}]: {int(flags.sum()):,} lots touched")
    if missing:
        print(f"  MISSING raw layers (skipped, must be caveated): {missing}")

    # Carve: subtract buffered carve overlays from the setback envelope.
    carve_specs = [s for s in cfg.overlays
                   if s.action == "carve" and s.key in layer_geoms]
    lots["envelope_setback_sqft"] = lots["envelope_sqft"]
    if carve_specs:
        print(f"  carving {len(carve_specs)} overlay layers from envelopes...")
        lots["geom"] = carve_envelopes(lots, carve_specs, layer_geoms)
        lots["envelope_sqft"] = [
            0.0 if g is None or g.is_empty else g.area for g in lots["geom"]]
        shrunk = int((lots["envelope_sqft"]
                      < lots["envelope_setback_sqft"] - 1.0).sum())
        emptied = int((lots["envelope_sqft"] <= 0).sum())
        print(f"  carve shrank {shrunk:,} envelopes ({emptied:,} to empty)")
    lots["envelope_carved_sqft"] = lots["envelope_sqft"]

    # Slope stats over the (carved) envelope; lot as fallback.
    if args.skip_slope:
        print("  slope: skipped by flag")
    else:
        dem_dir = RAW_DIR / "dem"
        tifs = list(dem_dir.glob("*.tif")) if dem_dir.exists() else []
        if not tifs:
            print("  slope: NO DEM tiles present — columns NaN, must be caveated")
            lots["slope_mean_pct"] = np.nan
            lots["slope_p85_pct"] = np.nan
            lots["slope_max_pct"] = np.nan
            lots["slope_source"] = "none"
            if cfg.slope.fallback_10m:
                _fill_from_coarse_dem(lots, cfg.slope)
        else:
            print(f"  slope: {len(tifs)} DEM tiles")
            dem = DemIndex(dem_dir)
            targets = [env if env is not None and not env.is_empty else lot_geom
                       for env, lot_geom in zip(lots["geom"], lots["lot_geom"])]
            # Tile-sorted order: each tile's gradient computed once instead of
            # thrashing the 4-slot cache (arbitrary order = hours, sorted = min).
            tile_ids = np.array([t if (t := dem.tile_of(g)) is not None else -1
                                 for g in targets])
            order = np.argsort(tile_ids, kind="stable")
            arr = np.full((len(targets), 3), np.nan)
            for n, i in enumerate(order):
                arr[i] = dem.stats(targets[i])
                if n and n % 20000 == 0:
                    print(f"    {n:,}/{len(lots):,}")
            lots["slope_mean_pct"] = arr[:, 0]
            lots["slope_p85_pct"] = arr[:, 1]
            lots["slope_max_pct"] = arr[:, 2]
            ok = int(np.isfinite(arr[:, 1]).sum())
            print(f"  slope computed for {ok:,}/{len(lots):,} lots")
            lots["slope_source"] = np.where(np.isfinite(arr[:, 1]),
                                            "dem_1m", "none")
            if cfg.slope.fallback_10m:
                _fill_from_coarse_dem(lots, cfg.slope)

    # Sewer main proximity (all city layers pooled; nearest distance).
    sewer_geoms = []
    for key in SEWER_LAYERS:
        geoms = _load_layer_geoms(key)
        if geoms is None:
            print(f"  sewer: {key} missing")
            continue
        sewer_geoms.extend(geoms)
    if sewer_geoms:
        from shapely.strtree import STRtree

        tree = STRtree(sewer_geoms)
        garr = np.array(sewer_geoms, dtype=object)
        dists = []
        for lot_geom in lots["lot_geom"]:
            ni = tree.nearest(lot_geom)
            dists.append(shapely.distance(lot_geom, garr[ni]))
        lots["sewer_main_dist_ft"] = dists
        near = int((np.array(dists) <= 100).sum())
        print(f"  sewer: {len(sewer_geoms):,} mains; {near:,} lots within 100 ft")
    else:
        lots["sewer_main_dist_ft"] = np.nan

    # Sanitary sewer DISTRICT membership (Clackamas polygons). A lot inside a
    # mapped district is connectable to public sewer even where no main
    # linework is published (WES/CWS gaps) — s7 uses this to clear the sewer
    # review flag. Only Clackamas districts are mapped, so lots elsewhere are
    # simply False and fall back to the main-distance signal.
    dist_geoms = _load_layer_geoms("util_sewer_district_clackamas")
    if dist_geoms:
        from shapely.strtree import STRtree

        dtree = STRtree(dist_geoms)
        lot_arr = np.array(lots["lot_geom"].tolist(), dtype=object)
        hit = dtree.query(lot_arr, predicate="intersects")
        in_dist = np.zeros(len(lots), dtype=bool)
        in_dist[np.unique(hit[0])] = True
        lots["in_sewer_district"] = in_dist
        print(f"  sewer districts: {len(dist_geoms)} polys; "
              f"{int(in_dist.sum()):,} lots inside a district")
    else:
        print("  sewer districts: layer missing — in_sewer_district all False")
        lots["in_sewer_district"] = False

    lots = lots.drop(columns=["lot_geom"])
    write_stage(lots, "s5o_lots")
    print("s5o done.")


if __name__ == "__main__":
    main()
