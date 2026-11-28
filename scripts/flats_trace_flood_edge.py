"""Trace Portland's flood-hazard edge rule (PCC 24.50.050) off the ground.

PCC 24.50.050 (stored at data/flats/books/flood/portland/24.50.txt#L100):
"When topographic data shows ground surface elevations at the boundary of
the special flood hazard area as shown on the FIRM are at or below the base
flood elevation, the boundary of the special flood hazard area will be
extended until it intercepts the elevation contour equal to the base flood
elevation."  FEMA's map is therefore a floor, not the edge: a lot outside the
mapped line can still be in the regulated flood area.  quadfit measures only
the mapped line (``ovl_fema_sfha``), so this script traces the extension and
writes it as a FLATS traced area (flats/config/areas/...), read against each
lot's shape by :func:`flats.ingest.quadfit._traced_on` as a closer look.

How (all choices lean toward more of the lot being in the flood area):

* the band searched is the ground within ``--band-ft`` of the mapped special
  flood hazard area, inside Portland (zoning union, grown 300 ft);
* the mapped boundary is sampled every ``--step-ft``.  Each sample's base
  flood elevation is the zone's static BFE (AH), else the highest of the
  three nearest FEMA BFE lines within 2,000 ft (NFHL layer 16, fetched live,
  NAVD88 feet) -- the upper of the lines either side of it -- else, where FEMA
  gives none (Zone A, AO), the ground at the boundary itself;
* ground is the USGS 1 m lidar DEMs given (first wins), taken to a 2 m grid
  by the LOWEST of each 2 x 2 block; where none covers a cell, the 10 m DEM,
  bilinear, with a wider tolerance; a cell no DEM covers is taken as low;
* a cell is flood ground when its ground is at or below the BFE of the
  nearest boundary sample plus the tolerance (``--tol-ft`` for lidar: USGS
  QL2 lidar is good to 10 cm RMSE, 19.6 cm at 95 percent);
* only flood ground connected to the mapped area is kept (the 24.50.050
  extension runs outward from the boundary; ground behind higher ground, a
  levee for one, is not reached).

Run on the scan host where quadfit's raw layers live; light (nice 19).
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
import time
from datetime import date
from pathlib import Path

import httpx
import numpy as np
import pyarrow.parquet as pq
import rasterio
import shapely
from pyproj import Transformer
from rasterio import features as rfeatures
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject
from rasterio.windows import Window, from_bounds
from shapely.geometry import mapping, shape
from shapely.ops import transform as stransform

FT_PER_M = 1 / 0.3048
NFHL_BFE = "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/16/query"
NO_BFE = -9000.0


def log(*a: object) -> None:
    print(time.strftime("%H:%M:%S"), *a, file=sys.stderr, flush=True)


def fetch_bfe_lines(bbox_ll: tuple[float, float, float, float], cache: Path) -> list[dict]:
    """FEMA's BFE lines over the box, as GeoJSON features in EPSG:2913."""
    if cache.exists():
        return json.loads(cache.read_text())["features"]
    feats: list[dict] = []
    off = 0
    while True:
        q = {
            "geometry": ",".join(map(str, bbox_ll)), "geometryType": "esriGeometryEnvelope", "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects", "outFields": "ELEV,LEN_UNIT,V_DATUM,DFIRM_ID",
            "outSR": 2913, "f": "geojson", "resultOffset": off, "resultRecordCount": 1000,
        }
        j = httpx.get(NFHL_BFE, params=q, timeout=120).json()
        got = j.get("features", [])
        feats += got
        log("bfe lines", len(feats))
        if len(got) < 1000 and not j.get("exceededTransferLimit") and not j.get("properties", {}).get("exceededTransferLimit"):
            break
        off += len(got)
    cache.write_text(json.dumps({"type": "FeatureCollection", "retrieved": date.today().isoformat(), "features": feats}))
    return feats


class Ground:
    """Ground in feet NAVD88 on a 2 m UTM 10N grid, window by window."""

    def __init__(self, lidar: list[str], coarse: str | None) -> None:
        self.lidar = [rasterio.open(f) for f in lidar]
        self.coarse = rasterio.open(coarse) if coarse else None

    def window(self, x0: float, y1: float, n: int, cell: float) -> tuple[np.ndarray, np.ndarray]:
        """``(ground_ft, level)``: level 1 lidar, 2 the coarse DEM, 0 none."""
        z = np.full((n, n), np.nan, dtype=np.float32)
        lvl = np.zeros((n, n), dtype=np.uint8)
        x1, y0 = x0 + n * cell, y1 - n * cell
        k = int(round(cell))  # lidar cells per grid cell, each way (1 m lidar)
        for r in self.lidar:
            b = r.bounds
            if b.right <= x0 or b.left >= x1 or b.top <= y0 or b.bottom >= y1:
                continue
            w = from_bounds(x0, y0, x1, y1, r.transform)
            w = Window(round(w.col_off), round(w.row_off), n * k, n * k)
            a = r.read(1, window=w, boundless=True, fill_value=r.nodata if r.nodata is not None else -999999).astype(np.float32)
            a[(a < -100) | (a > 3000)] = np.nan
            if r.nodata is not None:
                a[a == r.nodata] = np.nan
            with np.errstate(all="ignore"):
                blk = a.reshape(n, k, n, k)
                m = np.nanmin(np.where(np.isnan(blk), np.inf, blk), axis=(1, 3))
            m[np.isinf(m)] = np.nan
            put = np.isnan(z) & ~np.isnan(m)
            z[put] = m[put] * FT_PER_M
            lvl[put] = 1
        if self.coarse is not None and np.isnan(z).any():
            dst = np.full((n, n), np.nan, dtype=np.float32)
            reproject(
                rasterio.band(self.coarse, 1), dst, dst_transform=from_origin(x0, y1, cell, cell),
                dst_crs="EPSG:26910", resampling=Resampling.bilinear, dst_nodata=np.nan,
            )
            dst[(dst < -100) | (dst > 3000)] = np.nan
            put = np.isnan(z) & ~np.isnan(dst)
            z[put] = dst[put] * FT_PER_M
            lvl[put] = 2
        return z, lvl


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sfha", required=True, help="quadfit raw overlay_fema_sfha.geojson (EPSG:2913)")
    ap.add_argument("--zoning", required=True, help="quadfit s1_zoning_zoning_portland.parquet (wkb, EPSG:2913)")
    ap.add_argument("--lidar", nargs="+", required=True, help="1 m DEM tile globs, first wins")
    ap.add_argument("--coarse", help="10 m DEM for cells no lidar covers")
    ap.add_argument("--work", required=True, help="scratch dir (BFE line cache)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--band-ft", type=float, default=1000.0)
    ap.add_argument("--step-ft", type=float, default=15.0)
    ap.add_argument("--tol-ft", type=float, default=0.65)
    ap.add_argument("--tol-coarse-ft", type=float, default=3.0)
    ap.add_argument("--cell-m", type=float, default=2.0)
    ap.add_argument("--edge-ft", type=float, default=7.0)
    args = ap.parse_args()
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    to_utm = Transformer.from_crs(2913, 26910, always_xy=True)
    to_ft = Transformer.from_crs(26910, 2913, always_xy=True)
    to_ll = Transformer.from_crs(2913, 4326, always_xy=True)

    z = pq.read_table(args.zoning, columns=["wkb"]).column("wkb").to_pylist()
    city = shapely.union_all(shapely.make_valid(shapely.from_wkb(z))).buffer(300)
    log("portland area sq mi", round(city.area / 5280**2, 1))
    sf = json.loads(Path(args.sfha).read_text())["features"]
    geoms = shapely.make_valid(np.array([shape(f["geometry"]) for f in sf]))
    near = shapely.intersects(geoms, city.buffer(args.band_ft))
    geoms = geoms[near]
    props = [f["properties"] for f, k in zip(sf, near) if k]
    tree = shapely.STRtree(geoms)
    U = shapely.union_all(geoms)
    log("sfha features near portland", len(geoms))
    band = U.buffer(args.band_ft).difference(U).intersection(city)
    reach = city.buffer(args.band_ft)

    x0, y0, x1, y1 = reach.bounds
    (lx0, lx1), (ly0, ly1) = to_ll.transform([x0, x1], [y0, y1])
    lines = fetch_bfe_lines((lx0, ly0, lx1, ly1), work / "bfe_lines.geojson")
    units = {(f["properties"].get("LEN_UNIT"), f["properties"].get("V_DATUM")) for f in lines}
    log("bfe line units", units)
    lgeo = np.array([shape(f["geometry"]) for f in lines])
    lelev = np.array([float(f["properties"]["ELEV"]) for f in lines])
    ltree = shapely.STRtree(lgeo)

    # boundary samples, inside the reach
    bnd = shapely.intersection(shapely.boundary(U), reach)
    segs = shapely.get_parts(shapely.line_merge(bnd)) if not bnd.is_empty else []
    pts = []
    for s in segs:
        n = max(1, int(math.ceil(s.length / args.step_ft)))
        pts += [s.interpolate(i / n, normalized=True) for i in range(n + 1)]
    P = np.array(pts)
    log("boundary samples", len(P))
    which = tree.query_nearest(P, all_matches=False)[1]
    zone = np.array([props[i].get("FLD_ZONE") for i in which])
    static = np.array([float(props[i].get("STATIC_BFE") or NO_BFE) for i in which])
    bfe = np.where(static > NO_BFE, static, np.nan)
    how = np.where(static > NO_BFE, "static", "").astype(object)
    # three nearest BFE lines within 2,000 ft, highest of them
    cand = ltree.query(P, predicate="dwithin", distance=2000.0)
    dist = shapely.distance(P[cand[0]], lgeo[cand[1]])
    order = np.lexsort((dist, cand[0]))
    pi, li = cand[0][order], cand[1][order]
    first = np.r_[True, pi[1:] != pi[:-1]]
    rank = np.arange(len(pi)) - np.maximum.accumulate(np.where(first, np.arange(len(pi)), 0))
    keep = rank < 3
    top = np.full(len(P), np.nan)
    np.fmax.at(top, pi[keep], lelev[li[keep]])
    use = np.isnan(bfe) & ~np.isnan(top) & (zone != "A") & (zone != "AO")
    bfe[use] = top[use]
    how[use] = "lines"
    # ground at the boundary where FEMA gives no BFE
    ux, uy = to_utm.transform(shapely.get_x(P), shapely.get_y(P))
    gr = Ground(sorted(f for g in args.lidar for f in glob.glob(g)), args.coarse)
    pg = np.full(len(P), np.nan)
    for r in gr.lidar + ([gr.coarse] if gr.coarse else []):
        sx, sy = (ux, uy) if r.crs.to_epsg() == 26910 else Transformer.from_crs(26910, r.crs, always_xy=True).transform(ux, uy)
        b = r.bounds
        m = np.isnan(pg) & (sx >= b.left) & (sx < b.right) & (sy > b.bottom) & (sy <= b.top)
        if m.any():
            v = np.array([q[0] for q in r.sample(list(zip(sx[m], sy[m])))], dtype=float)
            v[(v < -100) | (v > 3000)] = np.nan
            pg[np.where(m)[0]] = v * FT_PER_M
    gnd = np.isnan(bfe)
    bfe[gnd] = pg[gnd]
    how[gnd] = "boundary ground"
    ok = ~np.isnan(bfe)
    log("samples by method", {k: int((how[ok] == k).sum()) for k in ("static", "lines", "boundary ground")}, "unmeasured", int((~ok).sum()))
    S, SB = P[ok], bfe[ok]
    stree = shapely.STRtree(S)
    low_at_line = int((pg[ok] <= SB).sum())
    log("samples with boundary ground at or below BFE", low_at_line)

    # windows over the band, UTM 2 m grid aligned to whole windows
    cell, n = args.cell_m, 1024
    band_u = stransform(to_utm.transform, band)
    shapely.prepare(band_u)
    bx0, by0, bx1, by1 = band_u.bounds
    gx0 = math.floor(bx0 / (cell * n)) * cell * n
    gy1 = math.ceil(by1 / (cell * n)) * cell * n
    polys, stats = [], {"cells": 0, "lidar": 0, "coarse": 0, "none": 0, "low": 0}
    diffs: list[np.ndarray] = []
    nx = math.ceil((bx1 - gx0) / (cell * n))
    ny = math.ceil((gy1 - by0) / (cell * n))
    for iy in range(ny):
        for ix in range(nx):
            wx0, wy1 = gx0 + ix * cell * n, gy1 - iy * cell * n
            wbox = shapely.box(wx0, wy1 - cell * n, wx0 + cell * n, wy1)
            if not band_u.intersects(wbox):
                continue
            part = band_u.intersection(wbox)
            tr = from_origin(wx0, wy1, cell, cell)
            inb = rfeatures.rasterize([part], out_shape=(n, n), transform=tr, all_touched=True, dtype=np.uint8).astype(bool)
            if not inb.any():
                continue
            g, lvl = gr.window(wx0, wy1, n, cell)
            stats["cells"] += int(inb.sum())
            stats["lidar"] += int((inb & (lvl == 1)).sum())
            stats["coarse"] += int((inb & (lvl == 2)).sum())
            stats["none"] += int((inb & (lvl == 0)).sum())
            # local samples bound the BFE any cell here can take
            near_s = stree.query(stransform(to_ft.transform, wbox).buffer(args.band_ft + 50))
            if len(near_s) == 0:
                continue
            hi = float(np.nanmax(SB[near_s]))
            tol = np.where(lvl == 2, args.tol_coarse_ft, args.tol_ft)
            cand_m = inb & (np.isnan(g) | (g <= hi + tol))
            rr, cc = np.nonzero(cand_m)
            if len(rr) == 0:
                continue
            cx, cy = wx0 + (cc + 0.5) * cell, wy1 - (rr + 0.5) * cell
            fx, fy = to_ft.transform(cx, cy)
            # query_nearest returns ties too; keep the highest BFE per cell
            best = np.full(len(rr), -np.inf)
            qi = stree.query_nearest(shapely.points(fx, fy))
            np.maximum.at(best, qi[0], SB[qi[1]])
            gv = g[rr, cc]
            low = np.isnan(gv) | (gv <= best + tol[rr, cc])
            m = np.zeros((n, n), dtype=bool)
            m[rr[low], cc[low]] = True
            stats["low"] += int(m.sum())
            both = inb & (lvl == 1)
            if both.any() and gr.coarse is not None and ix % 3 == 0:
                c = np.full((n, n), np.nan, dtype=np.float32)
                reproject(rasterio.band(gr.coarse, 1), c, dst_transform=tr, dst_crs="EPSG:26910", resampling=Resampling.bilinear, dst_nodata=np.nan)
                d = (c * FT_PER_M - g)[both]
                diffs.append(d[~np.isnan(d)][:: max(1, d.size // 2000)])
            for geom, _ in rfeatures.shapes(m.astype(np.uint8), mask=m, transform=tr, connectivity=8):
                polys.append(shape(geom))
        log("row", iy + 1, "of", ny, "polys", len(polys))
    log("stats", stats)
    if diffs:
        d = np.abs(np.concatenate(diffs))
        log("coarse minus lidar |diff| ft p50/p90/p95/p99", [round(float(np.percentile(d, q)), 2) for q in (50, 90, 95, 99)])

    low_u = shapely.union_all(polys)
    U_u = stransform(to_utm.transform, U)
    touch = U_u.buffer(cell * 1.5)
    shapely.prepare(touch)
    comps = [c for c in shapely.get_parts(low_u) if touch.intersects(c)]
    log("components", len(shapely.get_parts(low_u)), "kept", len(comps))
    outer = stransform(to_utm.transform, U.buffer(args.band_ft - 20).intersection(city))
    feats = []
    for c in comps:
        cf = stransform(to_ft.transform, c).buffer(0.5).simplify(1.0)
        if cf.is_empty:
            continue
        hit = stree.query(cf.buffer(cell * FT_PER_M * 2))
        zones = sorted({str(zone[ok][i]) for i in hit}) if len(hit) else []
        feats.append({
            "type": "Feature",
            "properties": {
                "EDGE_FT": args.edge_ft, "HOW": "dem_trace", "ZONES": ",".join(zones),
                "BFE_FT_MAX": round(float(SB[hit].max()), 2) if len(hit) else None,
                "AREA_SQFT": round(cf.area), "REACHES_BAND_EDGE": bool(not outer.contains(c)),
            },
            "geometry": mapping(shapely.set_precision(cf, 0.1)),
        })
    doc = {
        "type": "FeatureCollection",
        "name": "portland_flood_edge_24_50_050",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::2913"}},
        "source": {
            "rule": "PCC 24.50.050 flood hazard area edge extension",
            "quote": "or/multnomah/portland/24.50.txt#L100",
            "says": "the boundary of the special flood hazard area will be extended until it intercepts the elevation contour equal to the base flood elevation",
            "traced": f"{date.today().isoformat()} by scripts/flats_trace_flood_edge.py",
            "mapped_area": f"FEMA NFHL special flood hazard area as quadfit holds it ({Path(args.sfha).name}, {len(geoms)} features near Portland)",
            "bfe": f"NFHL MapServer layer 16 BFE lines ({len(lines)}, units {sorted(map(str, units))}); static BFE for AH; boundary ground where FEMA gives none",
            "ground": "USGS 1 m lidar DEM (lowest of each 2 x 2 m block), 10 m DEM where no lidar",
            "tolerance_ft": {"lidar": args.tol_ft, "coarse": args.tol_coarse_ft},
            "band_ft": args.band_ft, "cell_m": cell, "stats": stats,
            "edge": f"each feature's EDGE_FT {args.edge_ft} is one 2 m grid cell: the traced edge is good to a cell",
        },
        "features": feats,
    }
    Path(args.out).write_text(json.dumps(doc))
    log("wrote", args.out, len(feats), "features", "edge-reaching", sum(f["properties"]["REACHES_BAND_EDGE"] for f in feats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
