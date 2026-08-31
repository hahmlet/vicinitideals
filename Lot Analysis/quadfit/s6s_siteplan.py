"""s6s — procedural site-plan generator.

s6 answers "does a bare pod RECTANGLE fit in the setback envelope?". That is a
necessary but not sufficient test: a lot can seat the building yet have no room
left for parking or a driveway. This stage lays out an actual site plan per lot
— building at the front, a driveway from the street, a parking court with real
90° stalls, and a mandatory private open-space reservation — and reports the
best parking tier each lot achieves. s7 then TIGHTENS the 1-lot conversion
verdict with `site_plan_ok` in place of the bare-rectangle test.

Scoped by what has been READ, not by a cell somebody picked: every lot in every
city whose own code states a stall AND an aisle, in every zone. A city nobody
has read passes through untouched with `parking_tier = "not_evaluated"`, so s7
still sees the full table.

A city that states a stall and no aisle used to be declined by name. Two do —
Milwaukie and Wilsonville — and both were read to the end of the state's own
redirect (OAR 660-046-0220(2)(e)(E), single-family standards) before concluding
the number is not published anywhere. They are laid out to an ASSUMED 24 ft
aisle, sourced in footprints.yaml, and every lot so drawn carries
`geometry_assumed = True` for the CSV.

Those lots grade like any other, green included. ORS 197A.400 lets a city apply
only clear and objective standards to housing, and a standard nobody wrote down
cannot be one — so silence is a stronger position than a published number, not
a weaker one. The old rule stands everywhere it still applies: a court laid out
to a *borrowed* aisle — one lifted off a neighbour, or off a table this city
took away from this building — is a stall count no reviewer could defend. An
assumption that names its source, on a dimension the city genuinely never
stated, is a different animal from a number quietly copied.

Each city contributes exactly three numbers: its stall width, its stall depth,
its aisle — plus a stall CEILING where it states one, because a maximum makes
the higher marketability tiers unreachable however much room a lot has. The
arrangement itself does not vary: pod across the front, one consolidated
driveway down a side, a rear court, cars leaving forward. That is Gresham
§7.0431's shape and also Milwaukie 19.607.1.E.2's and Happy Valley
16.43.030.F.5's, which is why one typology travels.

Product = attached townhomes on ONE lot (the plat path s7's conversion verdict
reports and the FLATS design catalog defaults to). It is a real fork rather
than a formality: Oregon City's parking chapter reaches a quadplex and excludes
townhouses, so its dimensions stand on one lot and evaporate on four.

One honest typology `townhome_rear_court`. Phase-1 layout is greedy +
approximate (documented seams toward realism):
  - building: frontmost fitting pod placement (reuses s6's raster placement)
  - driveway: a single consolidated lane down one SIDE of the pod (never across
    the front, §7.0431(B)(3)(b)(iii)); its width is far under the combined curb-
    cut cap of 18 ft or 34% of frontage (§7.0431(B)(2)(b))
  - parking: a REAR-yard court (front/side-yard parking is barred for townhouses,
    §7.0431(B)(3)(b)(i)) — the largest free rectangle behind the building, tiled
    with 90° stalls served by a one-way or two-way aisle. Cars enter/leave
    forward, so nothing backs onto the street (banned only on arterials, A5.404)
  - open space: §7.0431(D)(1) requires 15% of the gross lot; modeled as a
    residual area reservation competing with building + pavement
  - utility run: phase-1 reuses `sewer_main_dist_ft` (s5o); a routed connector
    polyline is a phase-2 seam

NOT modelled, and the largest known gap in this stage: where a code says
parking may not SIT. Happy Valley 16.43.030.E.4 sets a parking area back from a
street lot line by the building setback (twenty feet in its residential zones);
Oregon City 17.16.060.D caps outdoor parking and manoeuvring at forty feet or
half the frontage; Milwaukie 19.607.1.D allows a quadplex a fourth front-yard
space and no more. A rear court is the arrangement that survives all of them,
which is the one drawn here — but the side driveway is not obviously exempt
from any of them, and no field in the corpus holds them yet. Every city outside
Gresham is drawn to its stall and its aisle, and to Gresham's driveway rules.

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
               area_sqft: float, front_setback_ft: float,
               jurisdiction: str = "", zone: str = "",
               parking_setback_ft: float | None = None) -> dict:
    """Lay out one lot's site plan. Runs in worker processes.

    Returns a dict of scalar results + `geoms` (role -> shapely geometry in the
    working CRS). `main()` turns geoms into WKB-hex and derives parking_tier /
    site_plan_ok from the scalars + config.

    `jurisdiction` selects every DIMENSION in the layout — the stall, the
    aisle, the stall ceiling, the width of the side lane, the gap behind the
    building and the open space that must be left over. The arrangement is the
    same everywhere; not one measurement is. It defaults to "" so a caller with
    a single-city config (the tests) can leave it off; the lookup falls back to
    the lone entry.

    `zone` is consulted for open space -- Portland is the one city that states
    the reserve by zone rather than citywide -- and, through
    `parking_setback_ft`, for how far a stall must stand off a street.

    `parking_setback_ft` is measured from the STREET LOT LINE, and the envelope
    handed in is already inset from it by the building setback, so what it can
    ask for here is the difference. None where the city states no such
    standard, which is not the same as zero.
    """
    import numpy as np
    import shapely
    from shapely import affinity
    from shapely.geometry import MultiPoint, box

    res: float = _CFG["res"]
    pods: list[tuple[str, float, float]] = _CFG["pods"]
    cells: dict = _CFG["cells"]
    cell = cells.get(jurisdiction) or next(iter(cells.values()))
    # Every one of these used to be a module-level constant carrying a Gresham
    # section number. They are per-city now, resolved in main() from the FLATS
    # corpus mirror, and the spread is not cosmetic: Happy Valley's side lane
    # is twenty feet where everyone else's is twelve, and the open-space
    # reserve is fifteen percent of the lot in Gresham, a flat 384 sq ft in
    # Milwaukie, 250 or 200 in Portland depending on the zone, and NOTHING in
    # the four cities that state no such standard for this building.
    gap: float = cell["gap"]
    drive_w: float = cell["lane"]
    open_pct: float = cell["open_pct"]
    open_flat: float = cell["open_by_zone"].get(zone, cell["open_sqft"]) or 0.0

    fail = {
        "site_plan_ok": False, "stalls_provided": 0, "layout_method": "none",
        "building_name": None, "driveway_len_ft": 0.0, "parking_area_sqft": 0.0,
        "open_space_sqft": 0.0, "open_space_req_sqft": 0.0,
        "open_space_ok": False, "driveway_width_ft": 0.0, "geoms": {},
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
    stall_w, stall_d = cell["stall_w"], cell["stall_d"]
    aisle_two, aisle_one = cell["aisle_two"], cell["aisle_one"]
    sw_c = max(1, math.ceil(stall_w / res))
    sd_c = max(1, math.ceil(stall_d / res))
    drive_c = max(1, round(drive_w / res))
    gap_c = max(0, round(gap / res))
    # A 4-plex never needs more than 2/unit — unless the city says fewer, in
    # which case the city's number is the cap and the higher tiers are simply
    # not reachable here. Milwaukie's one-per-unit is the live case.
    cap = cell["cap"]
    # No stall within `parking_setback_ft` of the street lot line. The envelope
    # already stands the whole buildable area back by the BUILDING setback, so
    # only the excess is left to enforce here -- and in Happy Valley, the one
    # city whose code states the standard by pointing at that same building
    # setback (LDC 16.43.030.E.4), the excess is zero by construction. Kept as
    # arithmetic rather than an assertion because the next city to print one
    # may print a bigger number, and on a corner lot the envelope is inset by
    # more than `front_setback_ft`, never less, so measuring off the front is
    # the conservative end.
    park_c = 0
    if parking_setback_ft is not None:
        park_c = max(0, math.ceil(
            max(0.0, parking_setback_ft - front_setback_ft) / res))
    geoms: dict = {}

    # Attached-townhome layout (Gresham §7.0431): the pod sits across the front;
    # a single consolidated driveway runs down one SIDE (never across the front,
    # §7.0431(B)(3)(b)(iii)) to a REAR parking court. Front/side-yard parking is
    # not allowed in the general townhouse case, so the court must sit BEHIND the
    # building. Cars enter and leave forward — nothing backs onto the street (the
    # code bans that only on arterials, Appendix A5.404) — so the plan is legal
    # on any street class.
    #
    # The lane is `drive_w`, which is the city's own two-way driveway minimum
    # where it states one and the design lane otherwise. Where the city caps
    # the curb CUT below the lane — Gresham does, at ten feet — the opening
    # narrows at the property line and the drive widens behind it, which is
    # what the approach standard governs and all it governs; main() has already
    # declined any city whose cap falls below one car's width.
    #
    # Try each pod size × orientation: place the pod frontmost, carve a rear
    # court, and require a side lane that reaches it. A builder orients the pod
    # to leave a driveway, so we keep the orientation with the MOST stalls rather
    # than the first that fits (a full-width pod would otherwise block the lane).
    Sok = _integral(ok)
    plan = None
    best_stalls = -1
    for name, w_ft, d_ft in pods:
        for ww, dd in ((w_ft, d_ft), (d_ft, w_ft)):
            bw, bh = math.ceil(ww / res), math.ceil(dd / res)
            hit = _placement(Sok, bh, bw)
            if hit is None:
                continue
            br, bc = hit
            court_r0 = max(br + bh + gap_c, park_c)  # behind pod + gap, off the street
            if court_r0 >= R:
                continue
            rect = _largest_rect(ok[court_r0:, :])
            if rect is None:
                continue
            cr, cc, rh, rw = rect
            rr = court_r0 + cr                     # court top row in full grid
            cw_ft, cd_ft = rw * res, rh * res
            rows = (2 if cd_ft >= 2 * stall_d + aisle_two
                    else 1 if cd_ft >= stall_d + aisle_one else 0)
            n_ct = min(cap, rows * int(cw_ft // stall_w))
            if n_ct <= 0:
                continue
            # Side driveway: first clear column run (in the envelope, clear of the
            # building) at least drive_c wide, running alongside the building from
            # its front row down to the court, whose columns overlap the court so
            # cars can reach it. Scanning from `br` (not row 0) skips the border-
            # False perimeter cells in the setback strip ahead of the pod, which
            # are always open anyway — checking them would falsely reject every
            # column since a conservative grid leaves the envelope edge unset.
            free = ok.copy()
            free[br:br + bh, bc:bc + bw] = False
            clear = free[br:rr, :].all(axis=0)
            corridor_c0, run = None, 0
            for c in range(C):
                run = run + 1 if clear[c] else 0
                if run >= drive_c:
                    c0 = c - drive_c + 1
                    if c0 < cc + rw and c0 + drive_c > cc:  # lane meets the court
                        corridor_c0 = c0
                        break
            if corridor_c0 is None or n_ct <= best_stalls:
                continue
            best_stalls = n_ct
            plan = {
                "rect": (rr, cc, rh, rw), "rows": rows, "stalls": n_ct,
                "aisle": aisle_two if rows == 2 else aisle_one,
                "span_ft": cw_ft, "bld": (name, br, bc, bh, bw, ww * dd),
                "driveway": (0, corridor_c0, rr, drive_c),
                "driveway_len": rr * res + front_setback_ft, "reaches": True,
            }

    if plan is None:
        return fail
    stalls, method = plan["stalls"], "townhome_rear_court"

    # --- realize the chosen plan into geometry (rotate back to CRS) --------
    bname, br, bc, bh, bw, building_area = plan["bld"]
    rr, cc, rh, rw = plan["rect"]
    parking_area = stalls * stall_w * stall_d + plan["aisle"] * plan["span_ft"]
    driveway_len = plan["driveway_len"]
    # The side driveway is separate pavement from the court aisle (counted in
    # parking_area), so the two do not double-count.
    driveway_area = plan["driveway"][2] * res * drive_w if plan["driveway"] else 0.0
    open_space = max(0.0, area_sqft - building_area - parking_area - driveway_area)
    # Concurrent claims, not alternatives: a city stating both a share and a
    # flat area asks for the larger. A city stating neither asks for nothing,
    # and four of the five cities laid out here are in that position — the 15
    # percent they used to be charged was Gresham's rule, collected citywide.
    open_req = max((open_pct / 100.0) * area_sqft, open_flat)
    open_space_ok = open_space >= open_req

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
        "open_space_req_sqft": float(round(open_req, 2)),
        "open_space_ok": bool(open_space_ok),
        "driveway_width_ft": float(cell["cut"]),
        "geoms": geoms,
    }


def _work_chunk(chunk):
    import shapely

    out = []
    for idx, env_wkb, bearings, fedges, area, fsb, jur, zone, psb in chunk:
        r = layout_lot(env_wkb, bearings, fedges, area, fsb, jur, zone, psb)
        r["geoms_hex"] = {role: shapely.to_wkb(g).hex() for role, g in r.pop("geoms").items()}
        out.append((idx, r))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processes", type=int, default=max(1, cpu_count() - 2))
    ap.add_argument("--limit", type=int, help="only first N in-scope lots (debug)")
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
    open_req = np.full(n, np.nan)
    open_ok = np.zeros(n, dtype=bool)
    drive_w = np.full(n, np.nan)
    sp_json = np.array([""] * n, dtype=object)

    if sp is None or not sp.enabled:
        print("s6s: siteplan disabled in footprints.yaml — writing passthrough columns")
        _finalize(lots, site_ok, tier, stalls, method, bname, drive_len,
                  drive_w, park_area, open_sqft, open_req, open_ok, sp_json)
        return

    pod_list = [(f.name, f.width_ft, f.depth_ft) for f in fps.footprints]
    fp_names = [f.name for f in fps.footprints]

    # Which lots: every city whose own code states a stall AND an aisle, on
    # every zone, wherever a pod geometrically fits. A city that states a stall
    # and no aisle is declined rather than laid out to somebody else's numbers
    # -- the stall count is the whole output of this stage, and a borrowed
    # dimension is a made-up one. A city nobody has read is passed through.
    fits_any = np.zeros(n, dtype=bool)
    for name in fp_names:
        fits_any |= (lots[f"fits_{name}_wf"].to_numpy()
                     | lots[f"fits_{name}_df"].to_numpy())

    cities = sp.cities_it_can_dimension()
    declined = sorted(set(sp.geometry) - set(cities))
    if not cities:
        print("s6s: no city in footprints.yaml states both a stall and an aisle; "
              "writing passthrough columns")
        _finalize(lots, site_ok, tier, stalls, method, bname, drive_len,
                  drive_w, park_area, open_sqft, open_req, open_ok, sp_json)
        return
    for j in declined:
        why = ("its code states a stall size but no aisle width"
               if sp.geometry_for(j) is not None
               else f"its parking chapter does not reach this building on the "
                    f"{sp.plat} plat path")
        print(f"s6s: declining {j} -- {why}")
    # Said out loud on every run, because it is the one number in this stage
    # that no city published and the console is where a reviewer meets it.
    assumed = sp.cities_on_an_assumed_aisle()
    for j in assumed:
        g = sp.geometry_for(j)
        print(f"s6s: {j} laid out on an ASSUMED {g.aisle_two_way_ft:g} ft aisle "
              f"-- its code states a stall and no aisle, so under ORS 197A.400 "
              f"there is no clear and objective width to fail; graded normally, "
              f"flagged in geometry_assumed")

    in_scope = (lots["jurisdiction"].isin(cities) & fits_any).to_numpy()
    if sp.scope == "pilot_cell":
        in_scope &= (lots["zone"] == sp.pilot_zone).to_numpy()

    # Per-CELL front setback from the verified zone rule (fallback 10 ft). One
    # lookup per (jurisdiction, zone) rather than per lot: there are a few dozen
    # cells and a quarter of a million lots.
    setbacks: dict[tuple[str, str], float] = {}

    def _front_setback(jur: str, zone: str) -> float:
        key = (jur, zone)
        if key not in setbacks:
            jr = rules.jurisdictions.get(jur)
            zr = jr.rule_for(zone) if jr else None
            setbacks[key] = (float(zr.setback_front_ft)
                             if zr and zr.setback_front_ft else 10.0)
        return setbacks[key]

    # Each city's own numbers, keyed by name and handed to the workers whole.
    # The ARRANGEMENT is per-corpus -- pod at the front, one side driveway, a
    # rear court, cars out forward, which every code here asks for in its own
    # words -- and every DIMENSION in it is per-city. Stall, aisle and ceiling
    # come from the city's parking chapter; lane, curb cut, building gap and
    # open space from its access chapter, both mirrored from FLATS.
    cells = {}
    for j in cities:
        g = sp.geometry_for(j)
        dw = sp.driveway_for(j)
        cells[j] = {
            "stall_w": g.stall_width_ft, "stall_d": g.stall_depth_ft,
            "aisle_one": g.aisle_one_way_ft, "aisle_two": g.aisle_two_way_ft,
            "cap": sp.stall_cap_for(j),
            "lane": sp.lane_ft_for(j), "cut": sp.curb_cut_ft_for(j),
            "gap": sp.gap_ft_for(j),
            "open_pct": (dw.open_space_pct or 0.0) if dw else 0.0,
            "open_sqft": (dw.open_space_sqft or 0.0) if dw else 0.0,
            "open_by_zone": dict(dw.open_space_sqft_by_zone) if dw else {},
        }

    # Where a city keeps stalls off the street, say what it asks and whether
    # the envelope already answers it. Happy Valley states the standard by
    # pointing at the building setback the envelope is cut to, so the honest
    # report is that it binds nowhere -- which is worth printing, because a
    # rule encoded and never mentioned again is indistinguishable from one
    # nobody wired up.
    for j in cities:
        asks = {z: sp.parking_street_setback_for(j, z)
                for z in {str(z) for z in lots.loc[lots["jurisdiction"] == j, "zone"]}}
        asks = {z: v for z, v in asks.items() if v}
        if not asks:
            continue
        over = {z: (v, _front_setback(j, z)) for z, v in asks.items()
                if v > _front_setback(j, z)}
        lo, hi = min(asks.values()), max(asks.values())
        span = f"{lo:g} ft" if lo == hi else f"{lo:g}-{hi:g} ft"
        print(f"s6s: {j} keeps parking {span} off a street lot line; "
              + (f"beyond the envelope in {len(over)} zone(s): "
                 + ", ".join(f"{z} {v:g} vs {f:g}" for z, (v, f) in sorted(over.items()))
                 if over else "the building setback already covers it in every zone"))

    # A city nobody has read its access chapter for is laid out to the design
    # lane and reserves no open space. That is a real gap and not a verdict, so
    # it is said out loud rather than left to the reader of a CSV.
    unread = [j for j in cities if sp.driveway_for(j) is None]
    if unread:
        print(f"s6s: no driveway rules read for {', '.join(unread)} -- laid out "
              f"to the {sp.driveway_lane_design_ft:g} ft design lane, with no "
              f"open-space reserve and no approach cap")

    cfg = {
        "res": res, "pods": pod_list, "min_stalls": sp.min_stalls(),
        "preferred_stalls": sp.preferred_stalls(),
        "cells": cells,
        "methods": list(sp.layout_methods),
    }

    idxs = np.nonzero(in_scope)[0]
    if args.limit:
        idxs = idxs[: args.limit]
    capped = [f"{j} (max {cells[j]['cap']})" for j in cities
              if cells[j]["cap"] < sp.preferred_stalls()]
    scope_note = (f"{sp.pilot_zone} only" if sp.scope == "pilot_cell"
                  else "all zones")
    print(f"s6s: {len(idxs):,} lots in scope of {n:,} total, {scope_note}, across "
          f"{len(cities)} cities ({', '.join(cities)}); {args.processes} processes"
          + (f"; stall ceiling binds in {', '.join(capped)}" if capped else ""))

    tasks = []
    for i in idxs:
        row = lots.iloc[i]
        if row["env_geom"] is None:
            continue
        fedges = [e[:4] for e in json.loads(row["edges_json"]) if e[4] == "F"]
        jur, zone = str(row["jurisdiction"]), str(row["zone"])
        tasks.append((
            int(i), shapely.to_wkb(row["env_geom"]),
            json.loads(row["front_bearings_json"]), fedges,
            float(row["area_sqft"]), _front_setback(jur, zone), jur, zone,
            sp.parking_street_setback_for(jur, zone),
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
        open_req[idx] = r["open_space_req_sqft"]
        open_ok[idx] = r["open_space_ok"]
        drive_w[idx] = r["driveway_width_ft"]
        sp_json[idx] = json.dumps(r["geoms_hex"])

    _finalize(lots, site_ok, tier, stalls, method, bname, drive_len,
              drive_w, park_area, open_sqft, open_req, open_ok, sp_json,
              assumed_cities=assumed)

    ev = stalls >= 0
    print(f"s6s: evaluated {int(ev.sum()):,} lots; "
          f"site_plan_ok {int(site_ok.sum()):,}; tiers "
          + ", ".join(f"{t}={int((tier == t).sum()):,}"
                      for t in ("preferred", "target", "minimum", "fail")))
    # Per city, because that is the whole reason this stage stopped being one
    # cell: a city's stall and aisle are what decide its lots, and a total hides
    # which city paid for which number.
    jur = lots["jurisdiction"].to_numpy()
    for j in cities:
        m = ev & (jur == j)
        if not m.any():
            print(f"  {j:16s} no lots in scope")
            continue
        c = cells[j]
        aisle = f"{c['aisle_one']}/{c['aisle_two']}"
        if c["open_by_zone"]:
            osp = "by zone"
        elif c["open_pct"]:
            osp = f"{c['open_pct']:g}%"
        elif c["open_sqft"]:
            osp = f"{c['open_sqft']:g}sf"
        else:
            osp = "none"
        print(f"  {j:16s} {int(m.sum()):>7,} evaluated  "
              f"site_plan_ok {int((site_ok & m).sum()):>6,}  "
              f"stall {c['stall_w']}x{c['stall_d']} aisle {aisle} cap {c['cap']}  "
              f"lane {c['lane']:g} cut {c['cut']:g} open {osp}  "
              + ", ".join(f"{t}={int(((tier == t) & m).sum()):,}"
                          for t in ("preferred", "target", "minimum", "fail")))
    print("s6s done.")


def _finalize(lots, site_ok, tier, stalls, method, bname, drive_len,
              drive_w, park_area, open_sqft, open_req, open_ok,
              sp_json, assumed_cities=()) -> None:
    import numpy as np

    if "env_geom" in lots.columns:
        lots = lots.drop(columns=["env_geom"])  # env re-read from s5o in s7
    # True where the plan on this row was drawn to an ASSUMED aisle rather than
    # a published one -- Milwaukie and Wilsonville, the two cities that state a
    # stall and never state the lane. It rides on the lot rather than being
    # re-derived from config in s7 so that the CSV a reviewer opens carries the
    # caveat next to the plan it qualifies, and so a stale run cannot lose it.
    lots["geometry_assumed"] = (
        lots["jurisdiction"].isin(list(assumed_cities)).to_numpy()
        & np.asarray(site_ok, dtype=bool)
    )
    lots["site_plan_ok"] = site_ok
    lots["parking_tier"] = tier
    lots["stalls_provided"] = stalls
    lots["layout_method"] = method
    lots["building_name"] = bname
    lots["driveway_len_ft"] = drive_len
    # The width of the opening at the property line: the lane, narrowed to the
    # city's approach ceiling. Reported because it is the number that moved
    # most in this change and the one a reviewer will check first.
    lots["driveway_width_ft"] = drive_w
    lots["parking_area_sqft"] = park_area
    lots["open_space_sqft"] = open_sqft
    lots["open_space_req_sqft"] = open_req
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
