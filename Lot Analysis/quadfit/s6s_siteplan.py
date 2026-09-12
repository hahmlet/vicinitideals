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

THE ALLEY. Portland sends the driveway round the back in one sentence, PCC
33.266.120.C.3: "If the lot abuts an alley, all parking and vehicle access to
the site must be from the alley." On a Portland lot with an alley edge (s4
class ``A``; `DrivewayRules.alley_access_required` names the city) the plan is
`townhome_rear_court_alley`: the same pod across the same front, the same court
behind it, and NO lane from the street -- the court is reached from the alley
lot line across the alley setback, by a lane of the city's width running
straight up from the court's back or straight out of its side to the cells of
the envelope that stand on the alley strip, or by nothing at all when the
court already stands there. A lot the alley cannot reach that way fails
`no_alley_lane`; it is not handed the street lane the city forbids. Cars still
leave forward off the court's own aisle: 33.266.130.F.1.b(2) would let them
back straight into the alley given twenty feet of manoeuvring to its far side,
but the streets file carries centrelines and not widths, so that relief is not
taken. The setback IS: 33.110.220.D.9 and 33.120.220.B.3.g ask no side or
rear setback from a lot line abutting an alley, `ZoneRule.setback_alley_ft`
carries the zero, s5 cuts the envelope to the alley line, and the strip this
stage looks for along the alley is whatever s5 left there (`lot_setbacks`,
asked here rather than re-derived). Fairview 19.145.090 says the same of
VTH/VA and is moot on the data (no VTH lot, no Fairview lot within 50 ft of
an alley); see `alley_access_required`.

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
  layout_fail · building_name · driveway_len_ft · parking_area_sqft ·
  open_space_sqft · open_space_ok · utility_run_ft · siteplan_json
  (role -> WKB-hex geometry).

`layout_fail` is empty where a plan was drawn and where the city was never
evaluated, and otherwise names how far the best attempt got before it gave
out -- no_envelope, no_building, no_court, court_too_shallow, no_side_lane
(or no_alley_lane where the city sends the driveway to the alley),
or, on a lot that DID draw a plan and was rejected anyway,
too_few_stalls / no_open_space. Reported, never graded on: it changes no
verdict, it says why the verdict is what it is.
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
from s5_envelope import lot_setbacks
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


def _alley_mouths(ok, alley_edges, minx: float, miny: float, res: float,
                  reach_ft: float):
    """Cells of the envelope grid that stand on the alley strip.

    The strip is drawn the way s5 drew the cut it made for the alley: each
    alley lot line buffered by `reach_ft` with square caps and mitred joins,
    the pieces unioned, and a cell counts when its centre lies inside. The
    caller passes the setback the envelope was cut to plus the cell or two
    the raster loses at the boundary, so every cell this finds is already at
    the envelope's edge: a straight rear edge standing off a straight alley
    is a mouth from end to end, corners included, while a side line five
    feet in stays a side line and an overlay carved out behind the court
    leaves the court where it is, farther from the alley than the setback
    and not a mouth.

    Two earlier drafts measured the plain distance to the alley line
    instead. The first also asked the cell to be an EDGE cell of the grid --
    redundant on a rear line parallel to the grid and wrong on one that is
    not, where the strip thins to a staircase one cell wide per row; 18
    Portland lots with a plan from the street were refused from the alley
    for it. The second dropped that and still refused an alley that turns a
    corner: s5's square caps leave the envelope's corner at a bend up to
    setback * sqrt(2) from the alley, farther than a round reach, so the
    lane had a gap at every bend. Same construction as the cut, and the
    question answers itself.
    """
    import numpy as np
    import shapely
    from shapely.geometry import LineString

    rows, cols = np.nonzero(ok)
    out = np.zeros_like(ok)
    if not len(rows) or not alley_edges:
        return out
    strip = shapely.union_all([
        LineString([(e[0], e[1]), (e[2], e[3])]).buffer(
            reach_ft, cap_style="square", join_style="mitre")
        for e in alley_edges])
    shapely.prepare(strip)
    near = shapely.contains_xy(strip, minx + (cols + 0.5) * res,
                               miny + (rows + 0.5) * res)
    out[rows[near], cols[near]] = True
    return out


def _lane_to_alley(free, mouths, rr: int, cc: int, rh: int, rw: int, drive_c: int):
    """A straight lane from the court to the alley, or None.

    Three directions, in the order a plan reads: up from the back of the court
    (the alley behind a mid-block lot), then out of its right and left sides
    (the alley beside a lot that fronts the cross street). The lane is
    `drive_c` cells wide and runs through free cells only. Every column of it
    (row, for a side lane) must run clear from the court to a cell on the
    alley strip -- its own last free cell, which on a rear line that is not
    parallel to the grid is one step higher or lower than its neighbour's --
    so a lane that reaches the back of the lot beside the alley rather than
    at it does not count. The rectangle returned is the part clear across
    the lane's whole width, (r0, c0, h, w) in grid cells; a zero-length lane
    means the court already stands on the alley and there is nothing to
    pave.
    """
    import numpy as np

    def run_of_free(a, axis):
        # How many free cells each column (axis 0) or row (axis 1) holds
        # before the first blocked one -- the whole length when none is.
        n = a.shape[axis]
        if n == 0:
            return np.zeros(a.shape[1 - axis], dtype=int)
        blocked = ~a
        return np.where(blocked.any(axis=axis), blocked.argmax(axis=axis), n)

    R, C = free.shape
    top_row = rr + rh
    up = run_of_free(free[top_row:, :], 0)
    # The last free cell of each column, or the court's own top cell where
    # the court already stands against the envelope.
    on_strip_up = mouths[np.clip(top_row + up - 1, 0, R - 1), np.arange(C)]
    for c0 in range(cc, cc + rw - drive_c + 1):
        if on_strip_up[c0:c0 + drive_c].all():
            return (top_row, c0, int(up[c0:c0 + drive_c].min()), drive_c)
    right = run_of_free(free[:, cc + rw:], 1)
    left = run_of_free(free[:, :cc][:, ::-1], 1)
    on_strip_right = mouths[np.arange(R), np.clip(cc + rw + right - 1, 0, C - 1)]
    on_strip_left = mouths[np.arange(R), np.clip(cc - left, 0, C - 1)]
    for r0 in range(rr, rr + rh - drive_c + 1):
        if on_strip_right[r0:r0 + drive_c].all():
            return (r0, cc + rw, drive_c, int(right[r0:r0 + drive_c].min()))
        if on_strip_left[r0:r0 + drive_c].all():
            w = int(left[r0:r0 + drive_c].min())
            return (r0, cc - w, drive_c, w)
    return None


def _alley_setback_for(rules, jur: str, zone: str, area: float, tier: str) -> float:
    """How far s5 stood the envelope off the alley lot line, in feet.

    Asked of s5's own arithmetic (`lot_setbacks`) rather than re-derived, so
    the layout is told the number the envelope was actually cut to. On a
    tier A or B lot that is the alley setback -- the rear, or the code's own
    where it states one (zero in Portland's R zones). On a tier C lot it is
    not: s5 gives an irregular lot one uniform inset by the LARGEST of its
    setbacks, front included, so the strip along the alley there is as wide
    as the front yard (ten feet in Portland's R5 against a five-foot rear),
    and a lane told to look five feet found nothing on seven of the thirteen
    lots it refused on 2026-09-12.
    """
    jr = rules.jurisdictions.get(jur)
    zr = jr.rule_for(zone) if jr else None
    if zr is None:
        return 0.0
    d = lot_setbacks(zr, area, tier)
    v = max(d.values()) if tier == "C" else d["A"]
    return float(v or 0.0)


def layout_lot(env_wkb: bytes, bearings: list[float], front_edges: list[list[float]],
               area_sqft: float, front_setback_ft: float,
               jurisdiction: str = "", zone: str = "",
               parking_setback_ft: float | None = None,
               alley_edges: list[list[float]] | None = None,
               alley_setback_ft: float = 0.0) -> dict:
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

    `alley_edges` are the lot's alley lot lines (s4 class ``A``), and they
    change the drawing only where the city's cell says `alley_access` -- then
    the driveway comes from the alley and no lane is drawn from the street.
    `alley_setback_ft` is how far the envelope stands off those lines, which
    is the strip the lane crosses to reach the alley and the distance that
    tells an envelope cell on the alley side from one on any other.
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
    # The driveway comes from the alley where the city says so AND the lot has
    # one. An alley edge in a city that says nothing changes nothing here; a
    # city that says so on a lot without one is laid out from the street like
    # anyone else.
    alley_fed = bool(cell.get("alley_access")) and bool(alley_edges)

    # `layout_fail` names how far the lot got before the plan gave out. A flat
    # "no layout" is the largest single reason in the whole screen -- 148,939
    # lots on the 2026-09-03 run -- and it has never said whether those lots
    # are too small for the building, too shallow for a court behind it, or
    # merely too narrow to get a car down the side. Those are three different
    # answers: the first is the product, the second is the typology, and the
    # third is a rule. It is reported, never graded on.
    fail = {
        "site_plan_ok": False, "stalls_provided": 0, "layout_method": "none",
        "building_name": None, "driveway_len_ft": 0.0, "parking_area_sqft": 0.0,
        "open_space_sqft": 0.0, "open_space_req_sqft": 0.0,
        "open_space_ok": False, "driveway_width_ft": 0.0, "geoms": {},
        "layout_fail": "no_envelope",
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
    # The cells of the envelope that stand on the alley strip: on the edge of
    # the envelope, and no farther from an alley lot line than the setback the
    # envelope was cut to (plus the cell the raster loses at the boundary).
    # Rotated into the same frame as the lot, so the lane search below can
    # walk the grid. An envelope with no cell on the strip is not refused
    # here: the ladder still has to say whether the building and the court
    # fit before it says the alley cannot be reached, so the empty set just
    # means no lane is ever found at the fourth rung.
    mouths = None
    if alley_fed:
        from shapely.geometry import MultiLineString
        alley_r = affinity.rotate(
            MultiLineString([[(e[0], e[1]), (e[2], e[3])] for e in alley_edges]),
            -rot, origin=origin)
        mouths = _alley_mouths(
            ok, [list(shapely.get_coordinates(g).ravel()) for g in alley_r.geoms],
            minx, miny, res, alley_setback_ft + 2.0 * res + 0.5)

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
    # How far the best attempt got. A lot is reported on its FURTHEST attempt,
    # not its first or its last: a pod that will not fit in one orientation but
    # reaches the driveway test in the other has not been stopped by its size.
    # Indexed by the last stage PASSED, so each label names what failed next:
    # nothing placed -> the building; placed -> no court behind it; court found
    # -> too shallow to park in; stalls counted -> no lane reaches them.
    reach, REACH = 0, ("no_building", "no_court", "court_too_shallow",
                       "no_alley_lane" if alley_fed else "no_side_lane")
    for name, w_ft, d_ft in pods:
        for ww, dd in ((w_ft, d_ft), (d_ft, w_ft)):
            bw, bh = math.ceil(ww / res), math.ceil(dd / res)
            hit = _placement(Sok, bh, bw)
            if hit is None:
                continue
            reach = max(reach, 1)
            br, bc = hit
            court_r0 = max(br + bh + gap_c, park_c)  # behind pod + gap, off the street
            if court_r0 >= R:
                continue
            rect = _largest_rect(ok[court_r0:, :])
            if rect is None:
                continue
            reach = max(reach, 2)
            cr, cc, rh, rw = rect
            rr = court_r0 + cr                     # court top row in full grid
            cw_ft, cd_ft = rw * res, rh * res
            rows = (2 if cd_ft >= 2 * stall_d + aisle_two
                    else 1 if cd_ft >= stall_d + aisle_one else 0)
            n_ct = min(cap, rows * int(cw_ft // stall_w))
            if n_ct <= 0:
                continue
            reach = max(reach, 3)
            free = ok.copy()
            free[br:br + bh, bc:bc + bw] = False
            if alley_fed:
                # From the alley: a straight lane from the court to the cells
                # on the alley strip, or none at all when the court already
                # stands there. Nothing is drawn from the street; the city
                # forbids it, and a lot that cannot be reached from the alley
                # is refused rather than handed the street lane.
                lane = _lane_to_alley(free, mouths, rr, cc, rh, rw, drive_c)
                if lane is None:
                    continue
                if n_ct <= best_stalls:
                    continue
                best_stalls = n_ct
                r0, c0, h, w = lane
                lane_len_c = h if w == drive_c else w
                plan = {
                    "rect": (rr, cc, rh, rw), "rows": rows, "stalls": n_ct,
                    "aisle": aisle_two if rows == 2 else aisle_one,
                    "span_ft": cw_ft, "bld": (name, br, bc, bh, bw, ww * dd),
                    "driveway": lane if lane_len_c else None,
                    "driveway_len_c": lane_len_c,
                    "driveway_len": lane_len_c * res + alley_setback_ft,
                    "reaches": True, "method": "townhome_rear_court_alley",
                }
                continue
            # Side driveway: first clear column run (in the envelope, clear of the
            # building) at least drive_c wide, running alongside the building from
            # its front row down to the court, whose columns overlap the court so
            # cars can reach it. Scanning from `br` (not row 0) skips the border-
            # False perimeter cells in the setback strip ahead of the pod, which
            # are always open anyway — checking them would falsely reject every
            # column since a conservative grid leaves the envelope edge unset.
            clear = free[br:rr, :].all(axis=0)
            corridor_c0, run = None, 0
            for c in range(C):
                run = run + 1 if clear[c] else 0
                if run >= drive_c:
                    c0 = c - drive_c + 1
                    if c0 < cc + rw and c0 + drive_c > cc:  # lane meets the court
                        corridor_c0 = c0
                        break
            if corridor_c0 is None:
                continue
            if n_ct <= best_stalls:
                continue
            best_stalls = n_ct
            plan = {
                "rect": (rr, cc, rh, rw), "rows": rows, "stalls": n_ct,
                "aisle": aisle_two if rows == 2 else aisle_one,
                "span_ft": cw_ft, "bld": (name, br, bc, bh, bw, ww * dd),
                "driveway": (0, corridor_c0, rr, drive_c), "driveway_len_c": rr,
                "driveway_len": rr * res + front_setback_ft, "reaches": True,
                "method": "townhome_rear_court",
            }

    if plan is None:
        return {**fail, "layout_fail": REACH[reach]}
    stalls, method = plan["stalls"], plan["method"]

    # --- realize the chosen plan into geometry (rotate back to CRS) --------
    bname, br, bc, bh, bw, building_area = plan["bld"]
    rr, cc, rh, rw = plan["rect"]
    parking_area = stalls * stall_w * stall_d + plan["aisle"] * plan["span_ft"]
    driveway_len = plan["driveway_len"]
    # The driveway is separate pavement from the court aisle (counted in
    # parking_area), so the two do not double-count. Zero on an alley-fed lot
    # whose court stands on the alley strip: there is no lane to pave.
    driveway_area = plan["driveway_len_c"] * res * drive_w
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

    ok_plan = bool(stalls >= _CFG["min_stalls"] and plan["reaches"]
                   and open_space_ok)
    return {
        # A drawn plan can still be rejected, and those two rejections are not
        # "no layout" -- there IS a layout, it is short of stalls or short of
        # the city's open-space reserve. Naming them separately keeps them out
        # of the geometry bucket, where they would read as land that cannot
        # hold the product.
        "layout_fail": ("" if ok_plan
                        else "too_few_stalls" if stalls < _CFG["min_stalls"]
                        else "no_open_space"),
        "site_plan_ok": ok_plan,
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
    for idx, env_wkb, bearings, fedges, area, fsb, jur, zone, psb, aedges, asb in chunk:
        r = layout_lot(env_wkb, bearings, fedges, area, fsb, jur, zone, psb,
                       aedges, asb)
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
    lfail = np.array([""] * n, dtype=object)
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
        _finalize(lots, site_ok, tier, stalls, method, lfail, bname, drive_len,
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
        _finalize(lots, site_ok, tier, stalls, method, lfail, bname, drive_len,
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
    #
    # Wilsonville states its front setback per lot size, so the cell is really
    # (jurisdiction, zone, which band the lot falls in). The band index is one
    # comparison per lot and the cache still holds a few dozen entries -- what
    # it must not do is answer per zone and quietly give a 12,000 sq ft lot the
    # small-lot number.
    setbacks: dict[tuple[str, str, int], float] = {}

    def _front_setback(jur: str, zone: str, area: float = 0.0) -> float:
        jr = rules.jurisdictions.get(jur)
        zr = jr.rule_for(zone) if jr else None
        rows = zr.lot_size_bands.get("setback_front_ft") if zr else None
        band = sum(1 for at_least, _ in rows if area >= at_least) if rows else 0
        key = (jur, zone, band)
        if key not in setbacks:
            v = zr.effective_setback_front_ft(area) if zr else None
            setbacks[key] = float(v) if v else 10.0
        return setbacks[key]

    # The alley edge stands off by the setback s5 cut the envelope to along
    # it -- the alley setback on a tier A/B lot (zero in Portland's R zones),
    # the largest of the four on a tier C lot -- and that strip is what an
    # alley-fed lane crosses. See `_alley_setback_for`.
    def _alley_setback(jur: str, zone: str, area: float = 0.0,
                       tier: str = "A") -> float:
        return _alley_setback_for(rules, jur, zone, area, tier)

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
            "alley_access": bool(dw and dw.alley_access_required),
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
        # No lot in hand here, so this reads the SMALLEST-lot band -- the
        # loosest front setback the zone states, which is the one a parking
        # setback is most likely to reach past. If it does not bind there it
        # binds nowhere.
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
    alley_fed = {j: 0 for j in cities if cells[j]["alley_access"]}
    for i in idxs:
        row = lots.iloc[i]
        if row["env_geom"] is None:
            continue
        edges = json.loads(row["edges_json"])
        fedges = [e[:4] for e in edges if e[4] == "F"]
        jur, zone = str(row["jurisdiction"]), str(row["zone"])
        # The alley lot lines, handed over only where the city sends the
        # driveway to them; everywhere else they are the rear lot lines s5
        # already set back and the plan has no further use for them.
        aedges = ([e[:4] for e in edges if e[4] == "A"]
                  if cells[jur]["alley_access"] else [])
        if aedges:
            alley_fed[jur] += 1
        tasks.append((
            int(i), shapely.to_wkb(row["env_geom"]),
            json.loads(row["front_bearings_json"]), fedges,
            float(row["area_sqft"]),
            _front_setback(jur, zone, float(row["area_sqft"])), jur, zone,
            sp.parking_street_setback_for(jur, zone),
            aedges, _alley_setback(jur, zone, float(row["area_sqft"]),
                                   str(row["tier"])),
        ))
    for j, k in alley_fed.items():
        print(f"s6s: {j} sends the driveway to the alley on a lot that has one "
              f"(alley_access_required); {k:,} lots in scope carry an alley edge "
              f"and are laid out from it, with no lane from the street")

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
        lfail[idx] = r["layout_fail"]
        bname[idx] = r["building_name"] or ""
        drive_len[idx] = r["driveway_len_ft"]
        park_area[idx] = r["parking_area_sqft"]
        open_sqft[idx] = r["open_space_sqft"]
        open_req[idx] = r["open_space_req_sqft"]
        open_ok[idx] = r["open_space_ok"]
        drive_w[idx] = r["driveway_width_ft"]
        sp_json[idx] = json.dumps(r["geoms_hex"])

    _finalize(lots, site_ok, tier, stalls, method, lfail, bname, drive_len,
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


def _finalize(lots, site_ok, tier, stalls, method, lfail, bname, drive_len,
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
    # Empty on a lot that got a plan, and on one nobody evaluated. The two are
    # told apart by parking_tier, as everywhere else in this stage.
    lots["layout_fail"] = lfail
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
