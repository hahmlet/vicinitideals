"""s6s — procedural site-plan generator (Gresham LDR-5 pilot).

s6 answers "does a bare pod RECTANGLE fit in the setback envelope?". That is a
necessary but not sufficient test: a lot can seat the building yet have no room
left for parking or a driveway. This stage lays out an actual site plan per lot
— building at the front, a driveway from the street, a parking court with real
90° stalls, and a mandatory private open-space reservation — and reports the
best parking tier each lot achieves. s7 then TIGHTENS the 1-lot conversion
verdict with `site_plan_ok` in place of the bare-rectangle test.

Scoped to a single pilot cell (`siteplan.pilot_jurisdiction` / `pilot_zone` in
footprints.yaml — Gresham LDR-5). Every other lot passes through untouched with
`parking_tier = "not_evaluated"`, so the stage is cheap and s7 sees the full
table. Generalizing to more cells is a post-pilot step (needs their utility
data + slope DEM).

Phase-1 layout is greedy + approximate (documented seams toward realism):
  - building: frontmost fitting pod placement (reuses s6's raster placement)
  - parking: largest free rectangle after the building, tiled with 90° stalls
    served by a two-way (double-loaded / `central_lot`) or one-way (single-
    loaded / `driveway_frontage`) aisle; best stall count over both wins
  - driveway: a min-travel-width strip from the parking court out to the front
    lot line (through the front setback, where Gresham allows driveway parking)
  - open space: §7.0420(D) requires 15% of the gross lot; modeled as a residual
    area reservation competing with building + pavement
  - utility run: phase-1 reuses `sewer_main_dist_ft` (s5o); a routed connector
    polyline is a phase-2 seam

Geometry works in the front-aligned rotated frame (front lot line along the
grid, building/stalls axis-aligned), then rotates back to EPSG:2913 for output.

Output stage `s6s_lots` carries every s6 column forward and adds:
  site_plan_ok (bool) · parking_tier · stalls_provided · layout_method ·
  building_name · driveway_len_ft · parking_area_sqft · open_space_sqft ·
  open_space_ok · utility_run_ft · siteplan_json (role -> WKB-hex geometry).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from multiprocessing import Pool, cpu_count
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOL_DIR))

from common import DATA_DIR, load_footprints, load_rules, read_stage, write_stage
from s6_fit import _cell_grid, _integral, _placement

_CFG: dict = {}


def _init_worker(cfg: dict) -> None:
    global _CFG
    _CFG = cfg


def _largest_rect(ok):
    """Largest all-True axis-aligned rectangle in a boolean grid.

    Returns (r0, c0, h, w) in cells (rows [r0,r0+h), cols [c0,c0+w)) of maximum
    area, or None. Standard histogram sweep, O(rows x cols).
    """
    import numpy as np

    R, C = ok.shape
    if R == 0 or C == 0 or not ok.any():
        return None
    heights = np.zeros(C, dtype=np.int64)
    best = (0, 0, 0, 0, 0)  # (area, r0, c0, h, w)
    for r in range(R):
        row = ok[r]
        heights = np.where(row, heights + 1, 0)
        stack: list[tuple[int, int]] = []  # (start_col, height)
        for c in range(C + 1):
            cur_h = int(heights[c]) if c < C else 0
            start = c
            while stack and stack[-1][1] > cur_h:
                s_col, s_h = stack.pop()
                area = s_h * (c - s_col)
                if area > best[0]:
                    best = (area, r - s_h + 1, s_col, s_h, c - s_col)
                start = s_col
            stack.append((start, cur_h))
    if best[0] == 0:
        return None
    return best[1], best[2], best[3], best[4]


def layout_lot(env_wkb: bytes, bearings: list[float], front_edges: list[list[float]],
               area_sqft: float, front_setback_ft: float) -> dict:
    """Lay out one lot's site plan. Runs in worker processes.

    Returns a dict of scalar results + `geoms` (role -> shapely geometry in the
    working CRS). `main()` turns geoms into WKB-hex and derives parking_tier /
    site_plan_ok from the scalars + config.
    """
    import numpy as np
    import shapely
    from shapely import affinity
    from shapely.geometry import MultiPoint, box

    res: float = _CFG["res"]
    gap: float = _CFG["gap"]
    drive_w: float = _CFG["drive_travel"]
    pods: list[tuple[str, float, float]] = _CFG["pods"]
    open_pct: float = _CFG["open_space_pct"]

    fail = {
        "site_plan_ok": False, "stalls_provided": 0, "layout_method": "none",
        "building_name": None, "driveway_len_ft": 0.0, "parking_area_sqft": 0.0,
        "open_space_sqft": 0.0, "open_space_ok": False, "geoms": {},
    }

    env = shapely.from_wkb(env_wkb)
    if env is None or env.is_empty:
        return fail
    parts = [p for p in shapely.get_parts(env)
             if p.geom_type == "Polygon" and p.area >= 100]
    if not parts:
        return fail
    poly = max(parts, key=lambda p: p.area)
    origin = poly.centroid

    # Rotate so the primary front bearing aligns to the grid, then pick the
    # 180deg orientation that puts the front lot line at MIN-y (street "south").
    b = float(bearings[0]) if bearings else 0.0
    rot = b
    if front_edges:
        mids = MultiPoint([((e[0] + e[2]) / 2.0, (e[1] + e[3]) / 2.0)
                           for e in front_edges])
        fmid = affinity.rotate(mids, -b, origin=origin)
        if fmid.centroid.y > origin.y:
            rot = b + 180.0

    poly_r = affinity.rotate(poly, -rot, origin=origin)
    minx, miny, maxx, maxy = poly_r.bounds
    ok = _cell_grid(poly_r, res)
    if ok is None or not ok.any():
        return fail
    R, C = ok.shape

    def cell_box(r0: int, c0: int, h: int, w: int):
        return box(minx + c0 * res, miny + r0 * res,
                   minx + (c0 + w) * res, miny + (r0 + h) * res)

    # Fixed-element cell dimensions.
    stall_w, stall_d = _CFG["stall_w"], _CFG["stall_d"]
    aisle_two, aisle_one = _CFG["aisle_two"], _CFG["aisle_one"]
    sw_c = max(1, math.ceil(stall_w / res))
    sd_c = max(1, math.ceil(stall_d / res))
    drive_c = max(1, round(drive_w / res))
    gap_c = max(0, round(gap / res))
    cap = _CFG["preferred_stalls"]  # a 4-plex never needs more than 2/unit
    methods = _CFG["methods"]
    geoms: dict = {}

    def place_building(min_row: int):
        """Frontmost fitting pod with rows < min_row masked out; both
        orientations. Returns (name, br, bc, bh, bw, area_sqft) or None."""
        work = ok.copy()
        if min_row > 0:
            work[:min_row, :] = False
        Sb = _integral(work)
        for name, w_ft, d_ft in pods:
            for ww, dd in ((w_ft, d_ft), (d_ft, w_ft)):
                w_c2, d_c2 = math.ceil(ww / res), math.ceil(dd / res)
                hit = _placement(Sb, d_c2, w_c2)
                if hit is not None:
                    r0, c0 = hit
                    return name, r0, c0, d_c2, w_c2, ww * dd
        return None

    candidates = []  # (stalls, method, plan)

    # driveway_frontage (Gresham PRIMARY, §7.0420(B)(5)(c)): a single row of
    # stalls across the front, backing directly onto the street apron; the pod
    # sits behind them. Needs no side corridor — works on narrow lots.
    if "driveway_frontage" in methods and ok.shape[0] >= sd_c:
        band = _largest_rect(ok[0:sd_c + 2, :])
        if band is not None and band[2] >= sd_c:
            fr0, fc0, _fh, fw = band
            n_front = min(cap, int((fw * res) // stall_w))
            bld = place_building(sd_c + gap_c) if n_front > 0 else None
            if n_front > 0 and bld is not None:
                candidates.append((n_front, "driveway_frontage", {
                    "rect": (fr0, fc0, sd_c, fw), "rows": 1,
                    "aisle": drive_w, "span_ft": fw * res, "bld": bld,
                    "driveway": None, "driveway_len": front_setback_ft,
                    "reaches": True,
                }))

    # central_lot (fallback): pod at the front, a rear/side parking court
    # reached by a driveway corridor clear of the building.
    if "central_lot" in methods:
        bld = place_building(0)
        if bld is not None:
            _n, br, bc, bh, bw, _a = bld
            free = ok.copy()
            free[br:br + bh, bc:bc + bw] = False
            free[br + bh:br + bh + gap_c, bc:bc + bw] = False
            rect = _largest_rect(free)
            if rect is not None:
                rr, cc, rh, rw = rect
                cw_ft, cd_ft = rw * res, rh * res
                rows = (2 if cd_ft >= 2 * stall_d + aisle_two
                        else 1 if cd_ft >= stall_d + aisle_one else 0)
                n_ct = min(cap, rows * int(cw_ft // stall_w))
                if rr == 0:
                    corridor_c0, reaches = cc, True
                else:
                    clear = free[0:rr, :].all(axis=0)
                    corridor_c0, run = None, 0
                    for c in range(C):
                        run = run + 1 if clear[c] else 0
                        if run >= drive_c:
                            c0 = c - drive_c + 1
                            corridor_c0 = c0 if corridor_c0 is None else corridor_c0
                            if cc - drive_c <= c0 <= cc + rw:
                                corridor_c0 = c0
                                break
                    reaches = corridor_c0 is not None
                if n_ct > 0 and reaches:
                    candidates.append((n_ct, "central_lot", {
                        "rect": (rr, cc, rh, rw), "rows": rows,
                        "aisle": aisle_two if rows == 2 else aisle_one,
                        "span_ft": cw_ft, "bld": bld,
                        "driveway": (0, corridor_c0, rr, drive_c) if rr > 0 else None,
                        "driveway_len": rr * res + front_setback_ft, "reaches": True,
                    }))

    if not candidates:
        return fail
    stalls, method, plan = max(candidates, key=lambda t: t[0])

    # --- realize the chosen plan into geometry (rotate back to CRS) --------
    bname, br, bc, bh, bw, building_area = plan["bld"]
    rr, cc, rh, rw = plan["rect"]
    parking_area = stalls * stall_w * stall_d + plan["aisle"] * plan["span_ft"]
    driveway_len = plan["driveway_len"]
    # Central-lot corridor is separate pavement; the front apron is already in
    # parking_area (as the aisle term), so it is not double-counted here.
    driveway_area = plan["driveway"][2] * res * drive_w if plan["driveway"] else 0.0
    open_space = max(0.0, area_sqft - building_area - parking_area - driveway_area)
    open_space_ok = open_space >= (open_pct / 100.0) * area_sqft

    def emit(name: str, g):
        geoms[name] = affinity.rotate(g, rot, origin=origin)

    emit("building", cell_box(br, bc, bh, bw))
    emit("parking_court", cell_box(rr, cc, rh, rw))
    if plan["driveway"] is not None:
        dr0, dc0, dh, dwid = plan["driveway"]
        emit("driveway", cell_box(dr0, dc0, dh, dwid))
    bx_center = minx + (bc + bw / 2.0) * res
    from shapely.geometry import LineString
    emit("utility", LineString([(bx_center, miny + br * res), (bx_center, miny)]))

    placed = 0
    for band_i in range(plan["rows"]):
        y0 = rr + (band_i * (rh - sd_c) if plan["rows"] == 2 else 0)
        x = cc
        while x + sw_c <= cc + rw and placed < stalls:
            emit(f"stall_{placed}", cell_box(int(y0), x, sd_c, sw_c))
            placed += 1
            x += sw_c

    return {
        "site_plan_ok": bool(stalls >= _CFG["min_stalls"] and plan["reaches"]
                             and open_space_ok),
        "stalls_provided": int(stalls),
        "layout_method": method,
        "building_name": bname,
        "driveway_len_ft": float(round(driveway_len, 3)),
        "parking_area_sqft": float(round(parking_area, 2)),
        "open_space_sqft": float(round(open_space, 2)),
        "open_space_ok": bool(open_space_ok),
        "geoms": geoms,
    }


def _work_chunk(chunk):
    import shapely

    out = []
    for idx, env_wkb, bearings, fedges, area, fsb in chunk:
        r = layout_lot(env_wkb, bearings, fedges, area, fsb)
        r["geoms_hex"] = {role: shapely.to_wkb(g).hex() for role, g in r.pop("geoms").items()}
        out.append((idx, r))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processes", type=int, default=max(1, cpu_count() - 2))
    ap.add_argument("--limit", type=int, help="only first N pilot lots (debug)")
    args = ap.parse_args()

    import numpy as np
    import shapely

    rules = load_rules()
    fps = load_footprints()
    sp = fps.siteplan
    res = rules.defaults.grid_resolution_ft

    lots = read_stage("s6_lots")  # every column except geom (dropped in s6)
    # Re-attach the carved setback envelope (s5o geom) — s6 drops it.
    s5o = read_stage("s5o_lots")[["TLID", "geom"]].rename(columns={"geom": "env_geom"})
    lots = lots.merge(s5o, on="TLID", how="left")

    n = len(lots)
    site_ok = np.zeros(n, dtype=bool)
    tier = np.array(["not_evaluated"] * n, dtype=object)
    stalls = np.full(n, -1, dtype=int)
    method = np.array([""] * n, dtype=object)
    bname = np.array([""] * n, dtype=object)
    drive_len = np.full(n, np.nan)
    park_area = np.full(n, np.nan)
    open_sqft = np.full(n, np.nan)
    open_ok = np.zeros(n, dtype=bool)
    sp_json = np.array([""] * n, dtype=object)

    if sp is None or not sp.enabled:
        print("s6s: siteplan disabled in footprints.yaml — writing passthrough columns")
        _finalize(lots, site_ok, tier, stalls, method, bname, drive_len,
                  park_area, open_sqft, open_ok, sp_json)
        return

    pod_list = [(f.name, f.width_ft, f.depth_ft) for f in fps.footprints]
    fp_names = [f.name for f in fps.footprints]

    # Pilot cell: right jurisdiction + zone AND a pod geometrically fits.
    fits_any = np.zeros(n, dtype=bool)
    for name in fp_names:
        fits_any |= (lots[f"fits_{name}_wf"].to_numpy()
                     | lots[f"fits_{name}_df"].to_numpy())
    pilot = ((lots["jurisdiction"] == sp.pilot_jurisdiction)
             & (lots["zone"] == sp.pilot_zone) & fits_any).to_numpy()

    # Per-cell front setback from the verified zone rule (fallback 10 ft).
    jrules = rules.jurisdictions.get(sp.pilot_jurisdiction)
    zrule = jrules.rule_for(sp.pilot_zone) if jrules else None
    front_setback = float(zrule.setback_front_ft) if zrule and zrule.setback_front_ft \
        else 10.0

    cfg = {
        "res": res, "gap": sp.building_parking_gap_ft,
        "drive_travel": sp.driveway_min_travel_ft, "pods": pod_list,
        "open_space_pct": sp.private_open_space_pct, "min_stalls": sp.min_stalls(),
        "preferred_stalls": sp.preferred_stalls(),
        "stall_w": sp.stall_width_ft, "stall_d": sp.stall_depth_ft,
        "aisle_two": sp.aisle_width_two_way_ft, "aisle_one": sp.aisle_width_one_way_ft,
        "methods": list(sp.layout_methods),
    }

    idxs = np.nonzero(pilot)[0]
    if args.limit:
        idxs = idxs[: args.limit]
    print(f"s6s: {len(idxs):,} pilot lots ({sp.pilot_jurisdiction}/{sp.pilot_zone}, "
          f"pod fits) of {n:,} total; {args.processes} processes")

    tasks = []
    for i in idxs:
        row = lots.iloc[i]
        if row["env_geom"] is None:
            continue
        fedges = [e[:4] for e in json.loads(row["edges_json"]) if e[4] == "F"]
        tasks.append((
            int(i), shapely.to_wkb(row["env_geom"]),
            json.loads(row["front_bearings_json"]), fedges,
            float(row["area_sqft"]), front_setback,
        ))

    chunk_size = 500
    chunks = [tasks[i:i + chunk_size] for i in range(0, len(tasks), chunk_size)]
    results: dict[int, dict] = {}
    if args.processes == 1:
        _init_worker(cfg)
        for ch in chunks:
            for idx, r in _work_chunk(ch):
                results[idx] = r
    else:
        with Pool(args.processes, initializer=_init_worker, initargs=(cfg,)) as pool:
            done = 0
            for out in pool.imap_unordered(_work_chunk, chunks):
                for idx, r in out:
                    results[idx] = r
                done += 1
                if done % 5 == 0:
                    print(f"  {min(done * chunk_size, len(tasks)):,}/{len(tasks):,}")

    for idx, r in results.items():
        site_ok[idx] = r["site_plan_ok"]
        s = r["stalls_provided"]
        stalls[idx] = s
        tier[idx] = sp.tier_for(s)
        method[idx] = r["layout_method"]
        bname[idx] = r["building_name"] or ""
        drive_len[idx] = r["driveway_len_ft"]
        park_area[idx] = r["parking_area_sqft"]
        open_sqft[idx] = r["open_space_sqft"]
        open_ok[idx] = r["open_space_ok"]
        sp_json[idx] = json.dumps(r["geoms_hex"])

    _finalize(lots, site_ok, tier, stalls, method, bname, drive_len,
              park_area, open_sqft, open_ok, sp_json)

    ev = stalls >= 0
    print(f"s6s: evaluated {int(ev.sum()):,} lots; "
          f"site_plan_ok {int(site_ok.sum()):,}; tiers "
          + ", ".join(f"{t}={int((tier == t).sum()):,}"
                      for t in ("preferred", "target", "minimum", "fail")))
    print("s6s done.")


def _finalize(lots, site_ok, tier, stalls, method, bname, drive_len,
              park_area, open_sqft, open_ok, sp_json) -> None:
    import numpy as np

    if "env_geom" in lots.columns:
        lots = lots.drop(columns=["env_geom"])  # env re-read from s5o in s7
    lots["site_plan_ok"] = site_ok
    lots["parking_tier"] = tier
    lots["stalls_provided"] = stalls
    lots["layout_method"] = method
    lots["building_name"] = bname
    lots["driveway_len_ft"] = drive_len
    lots["parking_area_sqft"] = park_area
    lots["open_space_sqft"] = open_sqft
    lots["open_space_ok"] = open_ok
    # utility_run_ft: phase-1 reuses the s5o sewer-main distance where present.
    if "sewer_main_dist_ft" in lots.columns:
        lots["utility_run_ft"] = np.where(
            stalls >= 0, lots["sewer_main_dist_ft"].to_numpy(), np.nan)
    else:
        lots["utility_run_ft"] = np.nan
    lots["siteplan_json"] = sp_json
    write_stage(lots, "s6s_lots")


if __name__ == "__main__":
    main()
