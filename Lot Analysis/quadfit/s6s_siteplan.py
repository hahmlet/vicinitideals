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


def _pack_stalls(court_w_ft: float, court_d_ft: float, cfg: dict):
    """Best (stalls, method, aisle_ft, stall_axis) for a free rectangle.

    Tries both axis assignments and, where the enabled layout methods allow, a
    double-loaded (central_lot, two-way aisle) and single-loaded
    (driveway_frontage, one-way aisle) module. `stall_axis` is which rectangle
    dimension the stall row is tiled along ("w" = court_w_ft, "d" = court_d_ft).
    """
    sw = cfg["stall_w"]
    sd = cfg["stall_d"]
    a2 = cfg["aisle_two"]
    a1 = cfg["aisle_one"]
    methods = cfg["methods"]

    best = (0, "fail", 0.0, "w")  # (stalls, method, aisle_ft, stall_axis)
    for span_a, span_b, axis in ((court_w_ft, court_d_ft, "w"),
                                  (court_d_ft, court_w_ft, "d")):
        per_row = int(span_a // sw)
        if per_row <= 0:
            continue
        if "central_lot" in methods and span_b >= 2 * sd + a2:
            stalls = 2 * per_row
            if stalls > best[0]:
                best = (stalls, "central_lot", a2, axis)
        if "driveway_frontage" in methods and span_b >= sd + a1:
            stalls = per_row
            if stalls > best[0]:
                best = (stalls, "driveway_frontage", a1, axis)
    return best


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

    # --- building: frontmost fitting pod (both orientations) ---------------
    S = _integral(ok)
    building = None  # (name, br, bc, bh, bw)  in cells
    for name, w_ft, d_ft in pods:
        for ww, dd in ((w_ft, d_ft), (d_ft, w_ft)):
            w_c, d_c = math.ceil(ww / res), math.ceil(dd / res)
            hit = _placement(S, d_c, w_c)  # (row, col): frontmost, then leftmost
            if hit is not None:
                br, bc = hit
                building = (name, br, bc, d_c, w_c)
                break
        if building is not None:
            break
    if building is None:
        return fail
    bname, br, bc, bh, bw = building
    building_area = (bw * res) * (bh * res)

    # --- parking: largest free rectangle after removing the building -------
    free = ok.copy()
    free[br:br + bh, bc:bc + bw] = False
    # A small gap band directly behind the building keeps stalls off the wall.
    gap_c = max(0, round(gap / res))
    free[br + bh:br + bh + gap_c, bc:bc + bw] = False

    rect = _largest_rect(free)
    stalls = 0
    method = "none"
    parking_area = 0.0
    geoms: dict = {}
    court = None  # (r0, c0, h, w)
    if rect is not None:
        rr, cc, rh, rw = rect
        court_w_ft, court_d_ft = rw * res, rh * res
        stalls, method, aisle_ft, axis = _pack_stalls(court_w_ft, court_d_ft, _CFG)
        if stalls > 0:
            court = (rr, cc, rh, rw)
            span_a = court_w_ft if axis == "w" else court_d_ft
            parking_area = (stalls * _CFG["stall_w"] * _CFG["stall_d"]
                            + aisle_ft * span_a)

    # --- driveway: min-travel strip from the court out to the front line ----
    driveway_len = 0.0
    drive_reaches_front = False
    if court is not None:
        rr, cc, rh, rw = court
        drive_c = max(1, round(drive_w / res))
        # Place the drive at the court edge clear of the building footprint.
        left_cols = range(cc, cc + drive_c)
        right_cols = range(cc + rw - drive_c, cc + rw)
        b_cols = set(range(bc, bc + bw))
        drive_c0 = cc if not (set(left_cols) & b_cols) else cc + rw - drive_c
        drive_c0 = max(0, min(drive_c0, C - drive_c))
        # From the court's front row down through the front setback to the lot
        # line (driveway parking is allowed in the front setback, §7.0420).
        y_court_front = miny + rr * res
        y_lot_line = miny - front_setback_ft
        driveway_len = round(y_court_front - y_lot_line, 3)
        drive_reaches_front = driveway_len > 0
        drive_geom = box(minx + drive_c0 * res, y_lot_line,
                         minx + (drive_c0 + drive_c) * res, y_court_front)
        geoms["driveway"] = drive_geom

    # --- open space: §7.0420(D) reservation of the gross lot ---------------
    driveway_area = driveway_len * drive_w if court is not None else 0.0
    open_space = max(0.0, area_sqft - building_area - parking_area - driveway_area)
    open_space_ok = open_space >= (open_pct / 100.0) * area_sqft

    # --- assemble geometry (rotate back to the working CRS) ----------------
    def emit(name: str, g):
        geoms[name] = affinity.rotate(g, rot, origin=origin)

    building_geom_r = cell_box(br, bc, bh, bw)
    # Utility stub: building front-center straight out to the front lot line.
    bx_center = minx + (bc + bw / 2.0) * res
    by_front = miny + br * res
    from shapely.geometry import LineString
    util_geom_r = LineString([(bx_center, by_front),
                              (bx_center, miny - front_setback_ft)])

    if "driveway" in geoms:
        geoms["driveway"] = affinity.rotate(geoms["driveway"], rot, origin=origin)
    emit("building", building_geom_r)
    emit("utility", util_geom_r)

    if court is not None and stalls > 0:
        rr, cc, rh, rw = court
        emit("parking_court", cell_box(rr, cc, rh, rw))
        # Individual stall rectangles (best-effort visual; count is authoritative).
        sw_c = max(1, round(_CFG["stall_w"] / res))
        sd_c = max(1, round(_CFG["stall_d"] / res))
        placed = 0
        rows = 2 if method == "central_lot" else 1
        for band in range(rows):
            y0 = rr + band * (rh - sd_c) if rows == 2 else rr
            x = cc
            while x + sw_c <= cc + rw and placed < stalls:
                geoms[f"stall_{placed}"] = affinity.rotate(
                    cell_box(int(y0), x, sd_c, sw_c), rot, origin=origin)
                placed += 1
                x += sw_c

    return {
        "site_plan_ok": bool(court is not None and stalls >= _CFG["min_stalls"]
                             and drive_reaches_front and open_space_ok),
        "stalls_provided": int(stalls),
        "layout_method": method,
        "building_name": bname,
        "driveway_len_ft": float(driveway_len),
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
