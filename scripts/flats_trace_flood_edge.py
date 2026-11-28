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
  flood elevation is the zone's static BFE (AH), else the higher of the
  two nearest FEMA BFE lines within 2,000 ft (NFHL layer 16, fetched live,
  NAVD88 feet) -- the upper of the lines either side of it -- else, where FEMA
  gives none (Zone A, AO), the ground at the boundary itself;
* ground is the USGS 1 m lidar DEMs given (first wins), taken to a 2 m grid
  by the LOWEST of each 2 x 2 block; where none covers a cell, the 10 m DEM,
  bilinear, with a wider tolerance; a cell no DEM covers is taken as low;
* the extension runs outward from the mapped line, as 24.50.050 says: a
  cell beside the mapped area starts at the BFE of the nearest boundary
  sample if its ground is at or below that BFE plus the tolerance
  (``--tol-ft`` for lidar: USGS QL2 lidar is good to 10 cm RMSE, 19.6 cm at
  95 percent), and the water then spreads cell to cell at the highest level
  that reaches it while the ground stays at or below it -- so ground behind
  higher ground, a levee for one, is not reached.

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
    ap.add_argument("--samples", help="also write the boundary samples here (.npz)")
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
    # two nearest BFE lines within 2,000 ft (the pair either side), higher of them
    cand = ltree.query(P, predicate="dwithin", distance=2000.0)
    dist = shapely.distance(P[cand[0]], lgeo[cand[1]])
    order = np.lexsort((dist, cand[0]))
    pi, li = cand[0][order], cand[1][order]
    first = np.r_[True, pi[1:] != pi[:-1]]
    rank = np.arange(len(pi)) - np.maximum.accumulate(np.where(first, np.arange(len(pi)), 0))
    keep = rank < 2
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
    if args.samples:
        np.savez(args.samples, x=shapely.get_x(S), y=shapely.get_y(S), bfe=SB, ground=pg[ok], how=how[ok].astype(str), zone=zone[ok].astype(str))
    stree = shapely.STRtree(S)
    low_at_line = int((pg[ok] <= SB).sum())
    log("samples with boundary ground at or below BFE", low_at_line)

    # windows over the band, UTM 2 m grid aligned to whole windows; each is filled with a margin
    # wider than the band, so flood ground entering it from a neighbour's mapped area is reached
    cell, n = args.cell_m, 1024
    marg = int(math.ceil(args.band_ft / FT_PER_M / cell)) + 40
    N = n + 2 * marg
    band_u = stransform(to_utm.transform, band)
    U_u = stransform(to_utm.transform, U)
    shapely.prepare(band_u)
    shapely.prepare(U_u)
    bx0, by0, bx1, by1 = band_u.bounds
    gx0 = math.floor(bx0 / (cell * n)) * cell * n
    gy1 = math.ceil(by1 / (cell * n)) * cell * n
    polys, stats = [], {"cells": 0, "lidar": 0, "coarse": 0, "none": 0, "seeds": 0, "low": 0}
    diffs: list[np.ndarray] = []
    nx = math.ceil((bx1 - gx0) / (cell * n))
    ny = math.ceil((gy1 - by0) / (cell * n))

    def nbr_max(a: np.ndarray) -> np.ndarray:
        """The highest of each cell's eight neighbours."""
        p = np.pad(a, 1, constant_values=-np.inf)
        out = np.full(a.shape, -np.inf, dtype=a.dtype)
        for dy in (0, 1, 2):
            for dx in (0, 1, 2):
                if dy == 1 and dx == 1:
                    continue
                np.maximum(out, p[dy:dy + a.shape[0], dx:dx + a.shape[1]], out=out)
        return out

    for iy in range(ny):
        for ix in range(nx):
            wx0, wy1 = gx0 + ix * cell * n, gy1 - iy * cell * n
            wbox = shapely.box(wx0, wy1 - cell * n, wx0 + cell * n, wy1)
            if not band_u.intersects(wbox):
                continue
            ex0, ey1 = wx0 - marg * cell, wy1 + marg * cell
            ebox = shapely.box(ex0, ey1 - cell * N, ex0 + cell * N, ey1)
            tr = from_origin(ex0, ey1, cell, cell)
            inb = rfeatures.rasterize([band_u.intersection(ebox)], out_shape=(N, N), transform=tr, all_touched=True, dtype=np.uint8).astype(bool)
            sfp = U_u.intersection(ebox)
            if sfp.is_empty or not inb.any():
                continue
            sfm = rfeatures.rasterize([sfp], out_shape=(N, N), transform=tr, dtype=np.uint8).astype(bool)
            inb &= ~sfm
            g, lvl = gr.window(ex0, ey1, N, cell)
            core = (slice(marg, marg + n), slice(marg, marg + n))
            ci = inb[core]
            stats["cells"] += int(ci.sum())
            stats["lidar"] += int((ci & (lvl[core] == 1)).sum())
            stats["coarse"] += int((ci & (lvl[core] == 2)).sum())
            stats["none"] += int((ci & (lvl[core] == 0)).sum())
            tol = np.where(lvl == 2, args.tol_coarse_ft, args.tol_ft).astype(np.float32)
            ground = np.where(np.isnan(g), -np.inf, g).astype(np.float32)  # no DEM: taken as low
            # seeds: band cells beside the mapped area, at the BFE of the nearest boundary sample
            adj = inb & (nbr_max(sfm.astype(np.float32)) > 0)
            rr, cc = np.nonzero(adj)
            if len(rr) == 0:
                continue
            fx, fy = to_ft.transform(ex0 + (cc + 0.5) * cell, ey1 - (rr + 0.5) * cell)
            best = np.full(len(rr), -np.inf)
            qi = stree.query_nearest(shapely.points(fx, fy))  # ties too: keep the highest BFE
            np.maximum.at(best, qi[0], SB[qi[1]])
            level = np.full((N, N), -np.inf, dtype=np.float32)
            ok_seed = ground[rr, cc] <= best + tol[rr, cc]
            level[rr[ok_seed], cc[ok_seed]] = best[ok_seed]
            stats["seeds"] += int(ok_seed.sum())
            # the water spreads outward at its own level while the ground stays at or below it
            for _ in range(4 * N):
                cand = nbr_max(level)
                grow = inb & (cand > level + 0.01) & (ground <= cand + tol)
                if not grow.any():
                    break
                level[grow] = cand[grow]
            m = (level > -np.inf)[core]
            stats["low"] += int(m.sum())
            both = ci & (lvl[core] == 1)
            if both.any() and gr.coarse is not None and ix % 3 == 0:
                c = np.full((n, n), np.nan, dtype=np.float32)
                reproject(rasterio.band(gr.coarse, 1), c, dst_transform=from_origin(wx0, wy1, cell, cell), dst_crs="EPSG:26910", resampling=Resampling.bilinear, dst_nodata=np.nan)
                d = (c * FT_PER_M - g[core])[both]
                diffs.append(d[~np.isnan(d)][:: max(1, d.size // 2000)])
            for geom, _ in rfeatures.shapes(m.astype(np.uint8), mask=m, transform=from_origin(wx0, wy1, cell, cell), connectivity=8):
                polys.append(shape(geom))
        log("row", iy + 1, "of", ny, "polys", len(polys))
    log("stats", stats)
    if diffs:
        d = np.abs(np.concatenate(diffs))
        log("coarse minus lidar |diff| ft p50/p90/p95/p99", [round(float(np.percentile(d, q)), 2) for q in (50, 90, 95, 99)])

    comps = list(shapely.get_parts(shapely.union_all(polys)))
    log("components", len(comps))
    outer = stransform(to_utm.transform, U.buffer(args.band_ft - 20).intersection(city))
    feats = []
    for c in comps:
        # holes filled (dry islands inside flood ground are read as flood ground) and the outline
        # grown 2 ft before a 1.5 ft simplify, so the file stays small and never shrinks the area
        cf = stransform(to_ft.transform, c)
        cf = shapely.union_all(shapely.polygons(shapely.get_exterior_ring(shapely.get_parts(cf))))
        cf = cf.buffer(2.0).simplify(1.5)
        if cf.is_empty:
            continue
        hit = stree.query(cf.buffer(cell * FT_PER_M * 2))
        zones = sorted({str(zone[ok][i]) for i in hit}) if len(hit) else []
        methods = sorted({str(how[ok][i]) for i in hit}) if len(hit) else []
        feats.append({
            "type": "Feature",
            "properties": {
                "EDGE_FT": args.edge_ft, "HOW": "dem_trace", "ZONES": ",".join(zones), "BFE_FROM": ",".join(methods),
                "BFE_FT_MAX": round(float(SB[hit].max()), 2) if len(hit) else None,
                "AREA_SQFT": round(cf.area), "REACHES_BAND_EDGE": bool(not outer.contains(c)),
            },
            "geometry": mapping(shapely.set_precision(cf, 0.5)),
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
            "edge": f"each feature's EDGE_FT {args.edge_ft} is one 2 m grid cell: the traced edge is good to a cell; outlines are grown 2 ft and holes filled before a 1.5 ft simplify",
        },
        "features": feats,
    }
    Path(args.out).write_text(json.dumps(doc))
    log("wrote", args.out, len(feats), "features", "edge-reaching", sum(f["properties"]["REACHES_BAND_EDGE"] for f in feats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
