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
the site must be from the alley." Gresham says it of the same building in GDC
7.0420(B)(1): "Lots, including middle housing without existing access, that
abut an alley, shall take access from the alley." On a lot in either city with
an alley edge (s4 class ``A``; `DrivewayRules.alley_access_required` names the
city) the plan is
`townhome_rear_court_alley`: the same pod across the same front, the same court
behind it, and NO lane from the street -- the court is reached from the alley
lot line across the alley setback, by a lane of the city's width running
straight up from the court's back or straight out of its side to the cells of
the envelope that stand on the alley strip, or by nothing at all when the
court already stands there. A lot the alley cannot reach that way fails
`no_alley_lane`; it is not handed the street lane the city forbids.

THE ALLEY AS THE AISLE (Steph's ruling, 2026-09-13; `DrivewayRules.alley_is_aisle`
names the city). On an alley-fed lot the cars in the row of stalls along the
alley back straight out into it, so the aisle the court used to draw inside
the lot is the alley itself. Where the city's row says so, a court standing
on the alley strip is asked for one stall depth (18 ft) plus whatever the
alley's width leaves short of the room a car needs to back out, instead of
a stall and a full aisle (42 ft in Portland), and that row is drawn against
the alley edge -- `townhome_rear_court_alley_aisle`, its own name so every
crosstab shows how many plans rest on it. Gresham states the relief
outright, Figure 9.0825A: "Public alley width may be included as part of
aisle width (A1 or A2) dimension, but all stalls must be on private
property, off the public right-of-way." Portland's fourplex chapter,
33.266.120, states the 9 x 18 stall and neither an aisle nor a forward-
motion rule; its all-other-development chapter, 33.266.130.F.1.b(2), lets
parking areas be "designed so that vehicles back out into an alley" given
20 ft of manoeuvring to the alley's far side, "some of this maneuvering
area" on-site where the alley is narrower. The room is the city's
(`DrivewayRules.alley_backout_ft`: Portland's twenty; Gresham's one-way
aisle, 23 ft, where the row states none), and THE ALLEY'S WIDTH IS
MEASURED: s4 reads it as the gap in the taxlot fabric between the lot and
the first private lot across the alley, looking through the right-of-way
polygon where the file draws one, or off the alley's centreline where the
land beyond is a freeway (`alley_width_ft`; the typical Portland alley is
14 ft), so the shortfall -- six feet on that alley in Portland -- is paved
on the lot between the stalls and the alley line and counted in the parking
area. Until 2026-09-13 the width was trusted, the way the assumed aisle
trusts SUDAS; now nothing in this drawing is. A lot whose alley has no
width on record is laid out as if the alley were nothing, the strict way.
It is taken only where it buys a stall -- a court deep enough for its own
aisle keeps it -- so the count of plans on this drawing is the count that
need it. The setback IS: 33.110.220.D.9 and 33.120.220.B.3.g ask
no side or rear setback from a lot line abutting an alley, and Gresham's
district tables print a "Rear With Alley" column (8 ft where the plain rear
is 15); `ZoneRule.setback_alley_ft` carries the zero or the number, s5 cuts
the envelope to it, and the strip this stage looks for along the alley is
whatever s5 left there (`lot_setbacks`, asked here rather than re-derived).
Fairview 19.145.090 says the same of VTH/VA and is moot on the data (no VTH
lot, no Fairview lot within 50 ft of an alley); see `alley_access_required`.

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

THE SIDE COURT, AND THE THROUGH LOT (FOLLOWUPS 5 iii/iv, 2026-09-19). A
lot with a street at BOTH ends -- one bearing, front edges at both ends,
6,118 of them on the September tree -- has two front lot lines (Portland
33.910; Wood Village 720.030; Gresham: "each street frontage shall be
considered a front yard"), and the court behind the building stands in
the second one, between the building and the second street. Portland
33.266.120.C.1.a bans a vehicle area there unless it is "entirely behind
the front and side street building lines", and Milwaukie 19.505.3.D.4.a
bans one "directly between the facade of a primary building(s) and an
abutting street right-of-way" (`DrivewayRules.parking_front_prohibited`,
the cell's `front_ban`): in those two cities a through lot is refused
every rear court, alley-fed or not, and offered the one arrangement the
words allow -- a court BESIDE the building, `townhome_side_court`, its
stalls against the side lot line and its aisle along the building's
wall, no farther back than the building's rear wall, reached by the same
lane from the front street (or from the alley, `townhome_side_court_alley`,
where the city sends the driveway there). The side court is offered on
every lot, in every city: on a wide shallow lot it is the plan where the
rear court is too shallow, and on a corner lot it is the court that
touches no street, which Steph's ruling prefers; in a ban city it is
never drawn on the side that faces a side street. The rear court keeps a
tie (`_plan_rank`), so a lot that draws a rear court today draws the same
one unless the side court is greener, seats a higher band, or stands on
less street. The other twelve cities state no ban, so a through lot keeps
its rear court there and may also take the lane in straight from the
second street across its setback strip (`townhome_rear_court_rear_street`,
the side-street lane's construction on the far end's edges). Each end of a
through lot is tried as the front (`_candidate_fronts`, `_through_ends`).

THE REAR COURT IS TRIMMED TO WHAT IT PARKS (the same day). Until then the
rear court WAS the largest free rectangle behind the building: a two-row
court on a deep lot put its second row at the back of the lot with the
whole depth between as "aisle", its side ran the side street's length and
its aisle was paved across the lot's width -- and against a side court
trimmed to its stalls the rear court lost on any lot wide enough to hold
one. Now the court is the rows it seats and the aisle between them, one
row or two (both tried), placed at any corner of the room behind the
building (`_court_places`) with the lane found from where it stands: a
court that can slide off the side street's strip, or off the far end's,
is offered there at zero exposure with a lane to that street, beside the
one that stands on the strip with none, and Steph's ruling chooses. The
one-row court turns its aisle toward the lane. The paper lot
(`flats.score.paper.court_depth`) charged the court this way all along;
this is the drawing agreeing with it, and `parking_area_sqft` /
`open_space_sqft` move on every rear-court lot (the bound run counts
them). The two-row court's lane still lands on its near row's end, where
a stall is drawn (FOLLOWUPS 5). The bound of 2026-09-20 read its LOST lots
and found two more constructions that had held on small lots and gave out
on big or bent ones: the trimmed court at the room's four corners cannot
reach a mouth that meets a 3-acre room mid-side (the whole room's lane now
says where, `_court_places`), and the front lane had to be free from the
BUILDING's front row, which no column beside the pod is on a lot whose
front bends (`_front_runs`: from each column's own edge on the front
street's strip). That second fix, run, lost 903 lots of its own: the strip
was sought at the FRONT setback's reach where a corner lot's is cut to the
street-side one, and a flag lot's pole is setback ground end to end (or a
sliver of envelope narrower than the lane), so no lane could start -- the
strip is now found at the street setback, and a pole at least the lane's
width is the lane, resumed at the body's top. The
lane still runs inside the envelope: a pole narrower than the lane, and a
street piece that does not line up with a column beside the pod (the lane
would jog through the front yard, or run in the side setback), refuse the
lot, which the drawing before 2026-09-20 parked over ground it never
checked (FOLLOWUPS 5 (k)). The pole's own lane is taken at ANY column of
the body's top: the pod is placed first-fit at the body's top-left, so
where the pole meets the body at the left the lane stands to the pod's
right, and the run along the body's top from the pole to it is neither
drawn nor charged -- 92 of the 123 pole lots the bound of 2026-09-20
restored (median 23 ft; six wide tracts with a short street piece, 240 to
400 ft, where the lot's ground at the street, not the envelope's, would
have told a stub from a pole). The drawing before 2026-09-20 took the same
lots with the same jog; the pod belongs beside the pole's lane (FOLLOWUPS
5 (n)).

`layout_method` is `townhome_rear_court` (lane from the front street down
the side of the building), `townhome_rear_court_side_street` (a corner lot
whose lane comes in from the side street, where the city allows it),
`townhome_rear_court_rear_street` (a through lot whose lane comes in from
the street at the far end), `townhome_rear_court_alley` (reached from the
alley, parked off the court's own aisle), `townhome_rear_court_alley_aisle`
(parked against the alley, backing out into it), `townhome_side_court` (a
court beside the building, lane from the front street) or
`townhome_side_court_alley` (the same court reached from the alley). WHICH
STREET IS THE FRONT on a corner lot, and how the plan kept is chosen among
the streets and lanes tried, is `layout_lot`'s docstring (FOLLOWUPS 5;
Steph's ruling of 2026-09-19).

Output stage `s6s_lots` carries every s6 column forward and adds:
  site_plan_ok (bool) · parking_tier · stalls_provided · layout_method ·
  layout_fail · building_name · driveway_len_ft · parking_area_sqft ·
  open_space_sqft · open_space_ok · utility_run_ft · siteplan_json
  (role -> WKB-hex geometry) · front_bearing_deg · fronts_tried ·
  court_street_ft · through_lot.

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

from common import DATA_DIR, load_footprints, load_rules, read_stage, stage_path, write_stage
from s4_edges import BEARING_CLUSTER_TOL_DEG, bearing_deg, bearing_delta
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


def _lane_to_alley(free, mouths, rr: int, cc: int, rh: int, rw: int, drive_c: int,
                   aisle: tuple[int, int] | None = None):
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
    pave. A side lane is looked for within the court's aisle rows first
    (`aisle`, (row0, row1) in full-grid cells) so a car drives out of the
    aisle and not out of a stall, and anywhere along the court's side after.
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
    rows_ = list(range(rr, rr + rh - drive_c + 1))
    if aisle is not None:
        first = [r0 for r0 in rows_ if aisle[0] <= r0 and r0 + drive_c <= aisle[1]]
        rows_ = first + [r0 for r0 in rows_ if r0 not in first]
    for r0 in rows_:
        if on_strip_right[r0:r0 + drive_c].all():
            return (r0, cc + rw, drive_c, int(right[r0:r0 + drive_c].min()))
        if on_strip_left[r0:r0 + drive_c].all():
            w = int(left[r0:r0 + drive_c].min())
            return (r0, cc - w, drive_c, w)
    return None


def _row_boxes(rr: int, cc: int, rh: int, rw: int, rows: int, stalls: int,
               sw_c: int, sd_c: int, aisle_first: bool = False
               ) -> list[tuple[int, int, int, int]]:
    """The stall boxes of a court parked off its own aisle: one row along
    the front of the court -- or along its back, `aisle_first`, when the
    lane meets the court's front and the aisle belongs there -- or two
    along its front and back with the aisle between, tiled from its left
    edge. (r0, c0, h, w) in grid cells."""
    boxes: list[tuple[int, int, int, int]] = []
    for band_i in range(rows):
        y0 = rr + (band_i * (rh - sd_c) if rows == 2
                   else (rh - sd_c) if aisle_first else 0)
        x = cc
        while x + sw_c <= cc + rw and len(boxes) < stalls:
            boxes.append((int(y0), x, sd_c, sw_c))
            x += sw_c
    return boxes


def _court_places(rr: int, cc: int, rh: int, rw: int, rh_u: int, rw_u: int,
                  lane: tuple[int, int, int, int] | None = None, drive_c: int = 0,
                  aisle: tuple[int, int] = (0, 0)) -> list[tuple[int, int]]:
    """Where a court `rh_u` by `rw_u` can stand in the room `rh` by `rw` at
    (rr, cc): its four corners -- against the building (the room's top) or
    the back, the left side or the right -- each once, the near-left corner
    first, which is where the court stood before 2026-09-19 when the room
    was no bigger than the court; and, given the lane the WHOLE room found
    to a strip (`lane`, `_lane_to_alley`'s (r0, c0, h, w)), the court slid
    under that lane -- against the room's back with the lane's columns
    inside its width, or against the side the lane leaves from with the
    lane's rows inside its aisle band (`aisle`, the band's (offset, depth)
    from the court's top) -- clamped to the room. The four corners alone
    lost five lots on the 2026-09-20 bound: a 10-acre Oregon City lot whose
    11-ft side street meets a 600-ft room mid-side, a Portland CM3 lot
    whose alley mouth does. (r0, c0) in grid cells."""
    rows = sorted({rr, rr + rh - rh_u})
    cols = sorted({cc, cc + rw - rw_u})
    out = [(r, c) for r in rows for c in cols]
    if lane is not None:
        r0, c0, h, w = lane
        if w == drive_c:                                   # up from the back
            r_u = rr + rh - rh_u
            cands = [(r_u, c0 + drive_c - rw_u), (r_u, c0)]
        else:                                              # out of a side
            c_u = cc + rw - rw_u if c0 >= cc + rw else cc
            off, dep = aisle
            cands = [(r0 + drive_c - dep - off, c_u), (r0 - off, c_u)]
        for r_u, c_u in cands:
            r_u = min(max(rr, r_u), rr + rh - rh_u)
            c_u = min(max(cc, c_u), cc + rw - rw_u)
            if (r_u, c_u) not in out:
                out.append((r_u, c_u))
    return out


def _front_runs(free, fcells, stop_r: int):
    """Which columns a lane can run straight down from the front street to
    row `stop_r` -- a court's top, a room's. A column carries one where its
    first free cell stands on the front street's strip (`fcells`; on a flag
    lot, whose pole is the lane, the body's top edge) and every cell from
    there to `stop_r` is free. Returns (clear, start): `clear[c]`
    and the row the lane's pavement starts, one cell ahead of the first
    free one -- the boundary cell corner containment leaves unset, inside
    the lot and the setback strip. Until 2026-09-20 the lane had to be free
    from the BUILDING's front row, so on a lot whose front bends -- the
    envelope's edge recedes behind that row beside the building -- no
    column beside the pod could carry a lane at all: 283 Portland through
    lots and their side courts, and every bent-front rear court, lost to a
    lane that was refused for crossing ground outside the lot."""
    import numpy as np

    R, C = free.shape
    has = free.any(axis=0)
    start = np.where(has, free.argmax(axis=0), R)
    # A court whose own top row is the column's first free cell stands on
    # the strip itself: nothing between, and the lane is the strip.
    rows = np.arange(R)[:, None]
    between = (~free) & (rows >= start[None, :]) & (rows < stop_r)
    clear = (has & (start <= stop_r) & ~between.any(axis=0)
             & fcells[np.clip(start, 0, R - 1), np.arange(C)])
    return clear, np.maximum(start - 1, 0)


def _alley_aisle_stalls(mouths, rr: int, cc: int, rh: int, rw: int,
                        sw_c: int, sd_c: int, cap: int, sb_c: int = 0):
    """The row of stalls that backs straight out into the alley, or None.

    Three edges of the court, in the order a plan reads: its back (the alley
    behind a mid-block lot), then its right and left sides (the alley beside
    a corner lot). A stall stands on an edge only where every cell of its
    width along that edge is on the alley strip (`_alley_mouths`), so a court
    whose back is half against the alley and half against a notch parks
    along the half that is; and a stall is `sd_c` deep INTO the court behind
    `sb_c` cells of manoeuvring room along the alley edge -- the on-site
    part of the back-out room the alley's width does not cover -- which
    together are the whole depth the court is asked for. The aisle is the
    alley. Returns (stalls, boxes, edge) for the edge that seats the most,
    boxes as (r0, c0, h, w) in grid cells; the back wins a tie. None where
    no edge seats one.
    """
    import numpy as np

    def runs(on):
        # (start, length) of each maximal run of True along an edge.
        out, start = [], None
        for i, v in enumerate(list(on) + [False]):
            if v and start is None:
                start = i
            elif not v and start is not None:
                out.append((start, i - start))
                start = None
        return out

    edges = []
    if rh >= sd_c + sb_c:
        edges.append(("back", mouths[rr + rh - 1, cc:cc + rw],
                      lambda s: (rr + rh - sb_c - sd_c, cc + s, sd_c, sw_c)))
    if rw >= sd_c + sb_c:
        edges.append(("right", mouths[rr:rr + rh, cc + rw - 1],
                      lambda s: (rr + s, cc + rw - sb_c - sd_c, sw_c, sd_c)))
        edges.append(("left", mouths[rr:rr + rh, cc],
                      lambda s: (rr + s, cc + sb_c, sw_c, sd_c)))
    best = None
    for edge, on, box_at in edges:
        boxes = []
        for start, length in runs(np.asarray(on, dtype=bool)):
            for k in range(length // sw_c):
                if len(boxes) >= cap:
                    break
                boxes.append(box_at(start + k * sw_c))
        if boxes and (best is None or len(boxes) > len(best[1])):
            best = (edge, boxes)
    if best is None:
        return None
    return len(best[1]), best[1], best[0]


def _alley_setback_for(rules, jur: str, zone: str, area: float, tier: str) -> float:
    """How far s5 stood the envelope off the alley lot line, in feet.

    Asked of s5's own arithmetic (`lot_setbacks`) rather than re-derived, so
    the layout is told the number the envelope was actually cut to. On a
    tier A or B lot that is the alley setback -- the rear, or the code's own
    where it states one (zero in Portland's R zones, 8 ft plus the roof plane
    in Gresham's LDR-5). On a tier C lot it is
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


def _street_setback_for(rules, jur: str, zone: str, area: float, tier: str) -> float:
    """How far s5 stood the envelope off EVERY street lot line, in feet.

    The same question as `_alley_setback_for`, asked of the F edges: the front
    setback on a tier A lot; on a tier B (corner) lot the larger of the front
    and the street-side setback, because s5 cannot tell which street is the
    legal front and cuts every street edge to the larger; the largest of all
    four on a tier C lot. This is the strip a lane from the side street
    crosses, and the distance that tells an envelope cell on a street from
    one on a neighbour.
    """
    jr = rules.jurisdictions.get(jur)
    zr = jr.rule_for(zone) if jr else None
    if zr is None:
        return 0.0
    d = lot_setbacks(zr, area, tier)
    v = max(d.values()) if tier == "C" else d["F"]
    return float(v or 0.0)


#: Two street bearings closer than this are ONE street that bends, not two
#: streets meeting at a corner. s4 clusters front edges at 20 degrees, so a
#: crescent, a cul-de-sac approach or an S-curve along one lot comes out as
#: two bearings 20-40 degrees apart; a corner lot's streets meet at 60-120.
#: On the September tree 15,530 of the 86,775 two-bearing lots are under 45
#: degrees (9,166 under 30). A lot at an acute intersection -- Sandy
#: Boulevard against Portland's grid -- is read as one bending street too,
#: and forgoes its second front rather than have its 16 ft clip taken for
#: one; the street's NAME per edge, which s4 does not hold, would tell the
#: two apart (FOLLOWUPS 5 (c)).
CORNER_MIN_DEG = 45.0
# Two groups of a street's front edges farther apart than this, measured
# across the bearing, are the two ENDS of a through lot rather than a jog in
# one frontage (the 30 ft step of 1S2E15BB-02800 is a jog; a lot is deeper).
THROUGH_MIN_FT = 40.0


def _extent_along(xy, bearing: float) -> float:
    """The lot's length along a bearing: the spread of its corners projected
    onto that direction. On every simple shape this is the length of the lot
    LINE that runs at that bearing -- the whole line, corner to corner,
    whether or not a street abuts all of it."""
    t = math.radians(bearing)
    proj = [x * math.cos(t) + y * math.sin(t) for x, y in xy]
    return max(proj) - min(proj) if proj else 0.0


def _through_ends(bearing: float, edges: list[list[float]], lot_xy=None):
    """The two ends of a through lot, or None.

    One street cluster's front edges split ACROSS the bearing: each edge's
    midpoint projected onto the bearing's normal, the widest gap between
    neighbours found, and where that gap is at least `THROUGH_MIN_FT` --
    and, with the lot's corners in hand, at least half the lot's extent
    across the bearing, so a long edge on a street that bends (up to 45
    degrees, one street by `CORNER_MIN_DEG`) is never taken for a far
    end -- the edges below the gap are one end and the edges above it the
    other. Which is "near" is the caller's flip, not this function's.
    Returns (low, high) lists of edges, or None on a lot with one frontage.
    """
    if len(edges) < 2:
        return None
    t = math.radians(bearing)
    nx, ny = -math.sin(t), math.cos(t)
    keyed = sorted(((e[0] + e[2]) / 2.0 * nx + (e[1] + e[3]) / 2.0 * ny, i)
                   for i, e in enumerate(edges))
    gaps = [(keyed[k + 1][0] - keyed[k][0], k) for k in range(len(keyed) - 1)]
    gap, at = max(gaps)
    need = THROUGH_MIN_FT
    if lot_xy:
        need = max(need, 0.5 * _extent_along(lot_xy, bearing + 90.0))
    if gap < need:
        return None
    low = [edges[i] for _, i in keyed[:at + 1]]
    high = [edges[i] for _, i in keyed[at + 1:]]
    return low, high


def _candidate_fronts(bearings: list[float], front_edges: list[list[float]],
                      rule: str | None, lot_xy=None) -> list[tuple[float, list, list]]:
    """The streets this lot may be laid out to face, one entry each.

    Each entry is (bearing, that street's front edges, the other streets'
    front edges). A lot on one street has one entry and every front edge in
    it. A through lot with streets at both ends is one cluster mod 180 whose
    edges split into two ends (`_through_ends`): each end is an entry with
    the other end among the "other streets", so each is tried as the front
    and the far end may serve the lane -- until 2026-09-19 the two ends were
    one entry, drawn to whichever the flip put nearer. A corner lot has an
    entry per street cluster (s4 writes at most two), and WHICH of them
    depends on the city's own definition of the front lot line, mirrored
    from FLATS `front_lot_line_corner` (`DrivewayRules.front_lot_line_corner`):

    - `shortest` -- Portland 33.910, Oregon City 17.04.490, Wilsonville
      4.001, West Linn 02, Multnomah 39.2000, Wood Village 720.030: the front
      is the street with the shorter lot LINE. One entry, unless the two are
      equal (within a foot, the platted "equal" of 33.910), when the
      applicant chooses and both are tried. The line's length is the lot's
      extent along the bearing (`_extent_along` over `lot_xy`, the lot's
      corners), NOT the sum of that street's front edges: the September run
      of 2026-09-19 read the sum and faced 738 lots the wrong way -- a lot
      with streets at both ends and along one side sums its two ends past
      the side, and a jogged frontage's perpendicular step (30 ft on
      1S2E15BB-02800) is no second street. Without the corners (a test) the
      front-edge sum stands in.
    - `owner` / `entrance` / `both` -- Gladstone, Happy Valley, Milwaukie,
      Gresham, Troutdale; Tualatin, Fairview; Clackamas ZDO 202: the
      choice is the applicant's (or follows the door, which the applicant
      places), so every street is tried and `layout_lot` chooses by Steph's
      ruling of 2026-09-19. Gresham's definition fixes the front where the
      minimum lot depth is met in one direction only, which nothing here
      measures yet; it is tried both ways like the others (FOLLOWUPS 5).
    - unread (None) -- the longest street, as before this rule was read.

    An edge farther than the cluster tolerance from every bearing (a curved
    corner) belongs to no street: it is in nobody's front edges and nobody's
    side edges, and counts only toward the court's exposure. Two bearings
    closer than `CORNER_MIN_DEG` are one street that bends: one entry, every
    front edge in it, drawn as before -- the first bound run took the 16 ft
    clip at the bend of 1S1E07DC-04600 for the shorter of two streets and
    refused a lot that parks eight.
    """
    if not bearings:
        return [(0.0, list(front_edges), [])]
    members: list[list[list[float]]] = [[] for _ in bearings]
    for e in front_edges:
        d, k = min((bearing_delta(bearing_deg(*e[:4]), float(b)), k)
                   for k, b in enumerate(bearings))
        if d <= BEARING_CLUSTER_TOL_DEG:
            members[k].append(e)
    groups = [(float(b), fe, sum(math.hypot(e[2] - e[0], e[3] - e[1]) for e in fe))
              for b, fe in zip(bearings, members) if fe]
    if len(groups) < 2 or bearing_delta(groups[0][0], groups[1][0]) < CORNER_MIN_DEG:
        groups = [(float(bearings[0]), list(front_edges), 0.0)]
        keep = groups
    elif rule == "shortest":
        def line_len(g):
            return _extent_along(lot_xy, g[0]) if lot_xy else g[2]
        groups.sort(key=line_len)
        keep = [g for g in groups if line_len(g) <= line_len(groups[0]) + 1.0]
    elif rule in ("owner", "entrance", "both"):
        keep = groups
    else:
        keep = groups[:1]
    out = []
    for b, fe, _ in keep:
        se = [e for g in groups if g[1] is not fe for e in g[1]]
        ends = _through_ends(b, fe, lot_xy)
        if ends is None:
            out.append((b, fe, se))
        else:
            low, high = ends
            out.append((b, low, high + se))
            out.append((b, high, low + se))
    return out


def _side_court(ok, r_lo: int, r_hi: int, c_lo: int, c_hi: int, outer: str,
                stall_d: float, aisle_two: float, res: float,
                sw_c: int, sd_c: int, aisle_c: int, cap: int):
    """A court BESIDE the building, or None where no rectangle stands there.

    The largest free rectangle in the strip of the grid beside the building
    (rows [r_lo, r_hi), columns [c_lo, c_hi)), its stalls at 90 degrees to
    the side lot line -- `outer`, "left" or "right", says which column of the
    rectangle stands on it -- and its aisle running along the building's
    wall, so a car comes down the lane from the street and turns straight
    into the aisle. One row of stalls against the lot line where the
    rectangle is a stall and the two-way aisle wide, two rows (the second
    against the building's side) where it is two stalls and an aisle wide,
    none where it is narrower. The rectangle is TRIMMED to what the stalls
    need: as long as the stalls it holds, as wide as the rows and the aisle
    -- "sufficient, but minimal parking", and the rest of the strip is the
    yard, not pavement.

    Returns ((rr, cc, rh, rw), rows, stalls, stall_boxes, (a0, a1)) with the
    rectangle in full-grid cells, the boxes as `_row_boxes` gives them and
    the aisle's columns [a0, a1); stalls is 0 (and the rest empty) where the
    rectangle is too narrow to park in, so the caller's ladder can say so.
    """
    if r_hi <= r_lo or c_hi <= c_lo:
        return None
    rect = _largest_rect(ok[r_lo:r_hi, c_lo:c_hi])
    if rect is None:
        return None
    cr, cc0, rh, rw = rect
    rr, cc = r_lo + cr, c_lo + cc0
    w_ft = rw * res
    rows = (2 if w_ft >= 2 * stall_d + aisle_two
            else 1 if w_ft >= stall_d + aisle_two else 0)
    per_row = rh // sw_c
    n = min(cap, rows * per_row)
    if n <= 0:
        return (rr, cc, rh, rw), rows, 0, [], None
    per_used = -(-n // rows)
    rh_u = min(rh, per_used * sw_c)
    rw_u = min(rw, rows * sd_c + aisle_c)
    if outer == "right":
        cc_u = cc + rw - rw_u
        outer_c, inner_c = cc_u + rw_u - sd_c, cc_u
        aisle = (cc_u + (sd_c if rows == 2 else 0), outer_c)
    else:
        cc_u = cc
        outer_c, inner_c = cc_u, cc_u + rw_u - sd_c
        aisle = (cc_u + sd_c, cc_u + rw_u - (sd_c if rows == 2 else 0))
    boxes: list[tuple[int, int, int, int]] = []
    for col in ((outer_c, inner_c) if rows == 2 else (outer_c,)):
        y = rr
        while y + sw_c <= rr + rh_u and len(boxes) < n:
            boxes.append((int(y), int(col), sw_c, sd_c))
            y += sw_c
    return (rr, cc_u, rh_u, rw_u), rows, int(n), boxes, aisle


def _street_exposure(scells, rr: int, cc: int, rh: int, rw: int, res: float) -> float:
    """Feet of the court's edge that stand on a street strip.

    The court's ring of cells, counted where `scells` -- the envelope cells
    within the street setback of a street lot line, built the way the alley
    strip is -- is set. A court behind the building on an interior lot
    touches no street and scores zero; on a corner lot the side of the court
    that runs along the side street scores its depth.
    """
    sub = scells[rr:rr + rh, cc:cc + rw]
    if sub.size == 0:
        return 0.0
    ring = sub.copy()
    if rh > 2 and rw > 2:
        ring[1:-1, 1:-1] = False
    return float(ring.sum()) * res


def _plan_rank(ok_plan: bool, band: int, exposure_ft: float, method: str,
               paved_sqft: float) -> tuple:
    """Steph's ruling of 2026-09-19 (HUMAN_TODO 21) as a sort key; higher wins.

    (1) a plan that turns the lot green; (2) the higher stall band --
    minimum, target, preferred as 1, 2, 3, below the floor 0; (3) the court
    least exposed to a street, to the nearest five feet -- less than a
    stall's width apart is the raster's corner cells, not a preference: a
    rear court along the side street and a side court whose end stands on
    it show the same 42 ft of pavement and differ by two corner cells; (4)
    the arrangement: the rear court off its
    own aisle over the side court (the rear court is the drawing every
    code here describes, and the one every lot drew before 2026-09-19 --
    the side court takes a lot only where the three tests above prefer
    it; FOLLOWUPS 5 holds the other reading, that the side court frees the
    rear yard for a second pod) over the court that trusts the alley's
    width, as before the ruling; (5) the least pavement, to the square
    foot -- "sufficient, but minimal parking so we can fit a 2nd pod".
    Never the most stalls: within a band the plan with fewer stalls paves
    less and wins.
    """
    return (bool(ok_plan), int(band), -round(exposure_ft / 5.0),
            _METHOD_RANK.get(method, 2), -round(paved_sqft))


_METHOD_RANK = {"townhome_rear_court_alley_aisle": 0,
                "townhome_side_court": 1, "townhome_side_court_alley": 1}


def layout_lot(env_wkb: bytes, bearings: list[float], front_edges: list[list[float]],
               area_sqft: float, front_setback_ft: float,
               jurisdiction: str = "", zone: str = "",
               parking_setback_ft: float | None = None,
               alley_edges: list[list[float]] | None = None,
               alley_setback_ft: float = 0.0,
               alley_width_ft: float | None = None,
               street_setback_ft: float | None = None,
               lot_xy=None) -> dict:
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
    `alley_width_ft` is the alley's width as s4 measured it across the
    taxlot fabric, read only where the cell says `alley_aisle`: the
    city's back-out room (`alley_need`) less this width is paved on the lot
    behind the stalls. None -- no width on record -- is laid out as zero.

    `street_setback_ft` is how far the envelope stands off EVERY street lot
    line (`_street_setback_for`: on a corner lot s5 cuts each street edge to
    the larger of the front and street-side setbacks). It is the strip a
    lane from the SIDE street crosses and the reach that finds the envelope
    cells standing on a street, for the court's exposure. None means the
    front setback, which is right on a lot with one street.

    `lot_xy` is the lot's corners, (x, y) pairs, for the length of each street
    LOT LINE where the city's front is the shorter one (`_candidate_fronts`);
    None (a test) falls back to the length of the street's front edges.

    WHICH STREET IS THE FRONT, AND WHERE THE LANE COMES FROM (FOLLOWUPS 5;
    Steph's ruling of 2026-09-19, HUMAN_TODO 21). On a corner lot the pod is
    laid out facing each street the city's definition of the front lot line
    allows (`_candidate_fronts`: the shortest street where the code fixes it,
    either where it leaves the choice to the applicant), and on each the
    court may be reached down the side of the building from the front street
    (`townhome_rear_court`) or straight in from the side street across its
    setback strip (`townhome_rear_court_side_street`) where the city's
    `corner_access_street` allows it -- `any`, or `lowest_class` (Clackamas
    845.02, Milwaukie 12.16, Oregon City 16.12.035, West Linn 48.025,
    Wilsonville, Fairview 19.162: the lower-classified street first, which
    nothing measures yet, so it is drawn as `any` and FOLLOWUPS 5 says so);
    `side` (a townhouse project on a corner lot takes its one driveway from
    the side street -- the unit-lot branch in Gresham, Oregon City,
    Milwaukie, Wilsonville, Fairview, Troutdale; not this design's) allows
    only the side street. An alley-fed city keeps its alley rule and draws
    no lane from any street.

    Among every plan that reaches a lane, the one kept is chosen by Steph's
    ruling, in this order and never by "most stalls": (1) a plan that turns
    the lot green (enough stalls, a lane, the open-space reserve met); (2)
    the higher stall BAND (preferred over target over minimum); (3) the court
    LEAST EXPOSED to a street (`_street_exposure`); (4) the court's own
    aisle over one that trusts the alley's width, as before; (5) the LEAST
    pavement -- "sufficient, but minimal parking so we can fit a 2nd pod".
    Ties keep the first plan found, which is the front the lot was drawn to
    before this ruling. Before 2026-09-19 the plan with the most stalls won,
    so within a band a lot may now show one or two fewer stalls than it did
    and the same colour.

    THE SIDE COURT AND THE THROUGH LOT (the module docstring). Every pod
    placement is also offered a court beside the building on each side
    (`_side_court`), reached by the front lane or, on an alley-fed lot,
    from the alley; in a city whose cell says `front_ban` it is never drawn
    on the side that faces a side street, and on a through lot -- one with
    front edges parallel to this front among the other streets' edges --
    it stops at the building's rear wall and NO rear court is offered at
    all, the code's words leaving no other court. A through lot elsewhere
    keeps its rear court and may take the lane from the far end
    (`townhome_rear_court_rear_street`). `through_lot` in the result says
    whether any front tried was one end of a through lot. The rear court is
    the rows it seats and their aisle, not the room behind the building,
    and stands at whichever corner of that room the ruling prefers
    (`_court_places`; the module docstring).
    """
    import numpy as np
    import shapely
    from shapely import affinity
    from shapely.geometry import LineString, MultiLineString, MultiPoint, box

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
    # ... and where the city's row says the alley is the aisle, the row of
    # stalls along it backs straight out (THE ALLEY AS THE AISLE, above).
    alley_aisle = alley_fed and bool(cell.get("alley_aisle"))
    # The city's words on a corner lot: which street is the front, and which
    # street the driveway may come from (`_candidate_fronts` and the
    # docstring above). Absent from a cell nobody has read: the longest
    # street is the front and the lane comes from it, as before.
    front_rule: str | None = cell.get("front_rule")
    access_rule: str | None = cell.get("access_rule")
    # ... and whether the city bans a vehicle area between the building and
    # a street (`parking_front_prohibited`): Portland and Milwaukie. It is
    # what refuses the rear court on a through lot and keeps the side court
    # off the side-street side of a corner lot.
    front_ban = bool(cell.get("front_ban"))
    street_sb: float = (front_setback_ft if street_setback_ft is None
                        else float(street_setback_ft))

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
        "layout_fail": "no_envelope", "front_bearing_deg": float("nan"),
        "fronts_tried": 0, "court_street_ft": float("nan"), "through_lot": False,
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

    # Fixed-element cell dimensions.
    stall_w, stall_d = cell["stall_w"], cell["stall_d"]
    aisle_two, aisle_one = cell["aisle_two"], cell["aisle_one"]
    sw_c = max(1, math.ceil(stall_w / res))
    sd_c = max(1, math.ceil(stall_d / res))
    drive_c = max(1, round(drive_w / res))
    # The side court's aisle carries the lane in from the street, so it is
    # never narrower than the lane: West Linn's two-way drive is 24 ft
    # against a 23 ft aisle.
    side_aisle = max(aisle_two, drive_w)
    aisle_c = max(1, math.ceil(side_aisle / res))
    aisle2_c = max(1, math.ceil(aisle_two / res))
    gap_c = max(0, round(gap / res))
    # THE ALLEY AS THE AISLE: the room a car backing out of its stall needs
    # is the city's (`alley_need` -- Portland's twenty feet to the far side
    # of the alley, Gresham's one-way aisle), the alley's measured width
    # counts toward it, and the rest is paved on the lot between the stalls
    # and the alley line. An alley with no width on record counts for
    # nothing: the strict reading, not the generous one.
    alley_need: float = cell.get("alley_need") or aisle_one
    shortfall_ft = (max(0.0, alley_need - (alley_width_ft or 0.0))
                    if alley_aisle else 0.0)
    sb_c = math.ceil(round(shortfall_ft / res, 6))
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
    # The stall bands the choice below is ranked on. `target` is optional in
    # the config a test hands in; without it the middle band is the top one.
    min_stalls: int = _CFG["min_stalls"]
    preferred: int = _CFG["preferred_stalls"]
    target: int = _CFG.get("target_stalls", preferred)
    # Concurrent claims, not alternatives: a city stating both a share and a
    # flat area asks for the larger. A city stating neither asks for nothing,
    # and four of the five cities laid out here are in that position — the 15
    # percent they used to be charged was Gresham's rule, collected citywide.
    open_req = max((open_pct / 100.0) * area_sqft, open_flat)
    # The reach that finds an envelope cell standing on a street strip: the
    # setback s5 cut plus the cell or two the raster loses at the boundary,
    # the same construction as the alley strip.
    street_reach = street_sb + 2.0 * res + 0.5

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
    # For each street the lot may face, each pod size × orientation: place the
    # pod frontmost, carve a rear court, and require a lane that reaches it.
    # Every plan that does is OFFERED, and the one kept is the best by the
    # ruling in the docstring (`offer` below) -- not the first that fits and
    # not the one with the most stalls.
    best: list = [None, None]  # [key, plan]

    def offer(plan: dict) -> None:
        stalls = plan["stalls"]
        parking_area = stalls * stall_w * stall_d + plan["aisle"] * plan["span_ft"]
        # The driveway is separate pavement from the court aisle (counted in
        # parking_area), so the two do not double-count. Zero on a lot whose
        # court stands on the strip it is reached across: nothing to pave.
        driveway_area = plan["driveway_len_c"] * res * drive_w
        open_space = max(0.0, area_sqft - plan["bld"][5] - parking_area - driveway_area)
        open_ok = open_space >= open_req
        ok_plan = bool(stalls >= min_stalls and plan["reaches"] and open_ok)
        band = int(stalls >= min_stalls) + int(stalls >= target) + int(stalls >= preferred)
        exposure = _street_exposure(plan["scells"], *plan["rect"], res)
        key = _plan_rank(ok_plan, band, exposure, plan["method"],
                         parking_area + driveway_area)
        if best[0] is None or key > best[0]:
            best[0] = key
            best[1] = {**plan, "parking_area": parking_area,
                       "driveway_area": driveway_area, "open_space": open_space,
                       "open_ok": open_ok, "ok": ok_plan, "exposure": exposure}

    # How far the best attempt got. A lot is reported on its FURTHEST attempt,
    # not its first or its last: a pod that will not fit in one orientation but
    # reaches the driveway test in the other has not been stopped by its size.
    # Indexed by the last stage PASSED, so each label names what failed next:
    # nothing placed -> the building; placed -> no court behind it; court found
    # -> too shallow to park in; stalls counted -> no lane reaches them.
    reach, REACH = 0, ("no_building", "no_court", "court_too_shallow",
                       "no_alley_lane" if alley_fed else "no_side_lane")
    fronts = _candidate_fronts(bearings, front_edges, front_rule, lot_xy)
    any_through = False
    for b, fe, se in fronts:
        # The other streets' edges that run WITH this front are the far end
        # of a through lot (`_through_ends`); a side street is at least
        # `CORNER_MIN_DEG` off. The far end takes the ban and may serve the
        # lane; a side street only serves the lane.
        far = [e for e in se
               if bearing_delta(bearing_deg(*e[:4]), b) <= BEARING_CLUSTER_TOL_DEG]
        through = bool(far)
        any_through = any_through or through
        # Rotate so this front bearing aligns to the grid, then pick the 180deg
        # orientation that puts THIS street's lot line at MIN-y ("south") --
        # the flip reads the street being tried, not both at once.
        rot = b
        if fe:
            mids = MultiPoint([((e[0] + e[2]) / 2.0, (e[1] + e[3]) / 2.0)
                               for e in fe])
            fmid = affinity.rotate(mids, -b, origin=origin)
            if fmid.centroid.y > origin.y:
                rot = b + 180.0

        poly_r = affinity.rotate(poly, -rot, origin=origin)
        minx, miny, maxx, maxy = poly_r.bounds
        ok = _cell_grid(poly_r, res)
        if ok is None or not ok.any():
            continue
        R, C = ok.shape

        def rotated(edges):
            g = affinity.rotate(
                MultiLineString([[(e[0], e[1]), (e[2], e[3])] for e in edges]),
                -rot, origin=origin)
            return [list(shapely.get_coordinates(p).ravel()) for p in g.geoms]

        # The cells of the envelope that stand on the alley strip: on the edge
        # of the envelope, and no farther from an alley lot line than the
        # setback the envelope was cut to (plus the cell the raster loses at
        # the boundary). Rotated into the same frame as the lot, so the lane
        # search below can walk the grid. An envelope with no cell on the
        # strip is not refused here: the ladder still has to say whether the
        # building and the court fit before it says the alley cannot be
        # reached, so the empty set just means no lane is ever found at the
        # fourth rung.
        mouths = None
        if alley_fed:
            mouths = _alley_mouths(ok, rotated(alley_edges), minx, miny, res,
                                   alley_setback_ft + 2.0 * res + 0.5)
        # The cells standing on ANY street strip, for the court's exposure;
        # and, where the city lets a corner lot's driveway come from the
        # side street, the cells on the SIDE street's strip, which the lane
        # search treats exactly as it treats the alley's.
        scells = (_alley_mouths(ok, rotated(front_edges), minx, miny, res, street_reach)
                  if front_edges else np.zeros_like(ok))
        # The cells on THIS front's strip alone: where a lane from the front
        # street may start (`_front_runs`), the envelope's edge at the street
        # setback (`street_sb`: on a corner lot s5 cuts every street edge to
        # the larger of the front and street-side setbacks, so the front's
        # own setback finds nothing there -- 161 corner lots on the bound of
        # 2026-09-20) and not an overlay's carve-out or the far end's strip.
        # A flag lot's pole is setback ground end to end, or keeps a sliver
        # of envelope narrower than the lane between its side setbacks (a
        # 16-ft pole, 5-ft sides: 6 ft), and is the lane itself where the
        # pole is at least the lane's width: the strip is then the body's
        # top edge, each column's first envelope cell, so the lane starts
        # there with nothing of the building above it, and the pole's
        # length is uncounted as it always was. A pole narrower than the
        # lane refuses the lot; the drawing before 2026-09-20 took every
        # pole, a 5-ft one included. A front the strip misses for any
        # other reason -- a wide one set back farther than the street
        # setback -- stays refused, and so does a stub narrower than the
        # lane on a wide lot.
        fcells = (_alley_mouths(ok, rotated(fe), minx, miny, res, street_reach)
                  if fe else np.zeros_like(ok))
        fe_len = sum(math.hypot(e[2] - e[0], e[3] - e[1]) for e in fe)
        strip_cols = np.flatnonzero(fcells.any(axis=0))
        strip_w = (strip_cols.max() - strip_cols.min() + 1) * res if strip_cols.size else 0.0
        if fe and strip_w < drive_w and drive_w <= fe_len <= 0.5 * C * res:
            fcells = ok & (np.cumsum(ok, axis=0) == 1)
        # The cells on the OTHER streets' strips -- a side street's, a far
        # end's -- which tell a side court in a ban city which side of the
        # building faces a street, and feed the lane from that street.
        ocells = (_alley_mouths(ok, rotated(se), minx, miny, res, street_reach)
                  if se else None)
        smouths = None
        if se and not alley_fed and access_rule in ("side", "any", "lowest_class"):
            smouths = ocells
        # `side` is the one word that takes the front street's lane away, and
        # only on a lot that has a side street to take it from.
        front_lane_ok = not (access_rule == "side" and se)
        frame = {"rot": rot, "minx": minx, "miny": miny, "scells": scells,
                 "front_deg": float(b), "street_sb": street_sb}

        Sok = _integral(ok)
        for name, w_ft, d_ft in pods:
            for ww, dd in ((w_ft, d_ft), (d_ft, w_ft)):
                bw, bh = math.ceil(ww / res), math.ceil(dd / res)
                hit = _placement(Sok, bh, bw)
                if hit is None:
                    continue
                reach = max(reach, 1)
                br, bc = hit
                free = ok.copy()
                free[br:br + bh, bc:bc + bw] = False
                bld = {**frame, "bld": (name, br, bc, bh, bw, ww * dd), "reaches": True}
                # THE SIDE COURT: beside the building on either side, off the
                # street by the parking setback like the rear court, a gap
                # off the wall; in a ban city, never on a side that faces a
                # street, and on a through lot no farther back than the
                # rear wall. The strip is skipped without a search where it
                # cannot hold one stall and the aisle, which is most lots.
                s_lo = max(br, park_c)
                s_hi = br + bh if (front_ban and through) else R
                for outer, c_lo, c_hi in (("right", bc + bw + gap_c, C),
                                          ("left", 0, bc - gap_c)):
                    c_lo, c_hi = max(0, c_lo), min(C, c_hi)
                    if c_hi - c_lo < sd_c + aisle_c or s_hi <= s_lo:
                        continue
                    if (front_ban and ocells is not None
                            and ocells[s_lo:s_hi, c_lo:c_hi].any()):
                        continue
                    found = _side_court(ok, s_lo, s_hi, c_lo, c_hi, outer, stall_d,
                                        side_aisle, res, sw_c, sd_c, aisle_c, cap)
                    if found is None:
                        continue
                    reach = max(reach, 2)
                    s_rect, s_rows, n_sc, s_boxes, s_aisle = found
                    if n_sc <= 0:
                        continue
                    reach = max(reach, 3)
                    s_rr, s_cc, s_rh, s_rw = s_rect
                    side = {**bld, "rect": s_rect, "stalls": n_sc, "aisle": side_aisle,
                            "span_ft": s_rh * res, "stall_boxes": s_boxes}
                    if alley_fed:
                        lane = _lane_to_alley(free, mouths, s_rr, s_cc, s_rh, s_rw, drive_c)
                        if lane is not None:
                            r0, c0, h, w = lane
                            lane_len_c = h if w == drive_c else w
                            offer({**side, "driveway": lane if lane_len_c else None,
                                   "driveway_len_c": lane_len_c,
                                   "driveway_len": lane_len_c * res + alley_setback_ft,
                                   "method": "townhome_side_court_alley"})
                        continue
                    # The front lane runs straight into the aisle: the first
                    # clear corridor within the aisle's columns from the
                    # front street's strip to the court's top (`_front_runs`).
                    a0, a1 = s_aisle
                    clear, start = _front_runs(free, fcells, s_rr)
                    lane_c0 = next((c0 for c0 in range(a0, a1 - drive_c + 1)
                                    if clear[c0:c0 + drive_c].all()), None)
                    if lane_c0 is None:
                        continue
                    r_top = int(start[lane_c0:lane_c0 + drive_c].max())
                    offer({**side, "driveway": ((r_top, lane_c0, s_rr - r_top, drive_c)
                                                if s_rr > r_top else None),
                           "driveway_len_c": s_rr - r_top,
                           "driveway_len": (s_rr - r_top) * res + street_sb,
                           "method": "townhome_side_court"})
                if front_ban and through:
                    # The rear court would stand between the building and the
                    # far street: the words refuse it, and no lane cures it.
                    continue
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
                # THE COURT IS TWO-WAY, ONE ROW OR TWO. A car reaches this court
                # down one side lane and leaves the way it came, so the aisle in
                # front of the stalls carries traffic both ways whether stalls
                # stand on one side of it or both. Until 2026-09-17 a one-row
                # court was sized to the city's ONE-way aisle, which is a figure
                # for a court with an exit at the far end -- 23 ft in Gresham and
                # 12 in Wood Village, where a car backing out of a 90-degree
                # stall into 12 ft of pavement is not a drawing. The paper lot
                # (`flats.score.paper.court_depth`) had ruled the same way all
                # along; this is the county drawing agreeing with it.
                rows = (2 if cd_ft >= 2 * stall_d + aisle_two
                        else 1 if cd_ft >= stall_d + aisle_two else 0)
                n_ct = min(cap, rows * int(cw_ft // stall_w))
                # The alley as the aisle: the stalls that stand on the alley strip
                # and back straight out into it, asked for a stall depth and no
                # aisle. Counted beside the court's own aisle, never instead of it.
                on_alley = (_alley_aisle_stalls(mouths, rr, cc, rh, rw, sw_c, sd_c, cap, sb_c)
                            if alley_aisle else None)
                if n_ct <= 0 and on_alley is None:
                    continue
                reach = max(reach, 3)
                base = {**bld, "rect": (rr, cc, rh, rw)}
                if alley_fed and on_alley is not None:
                    n_al, boxes, _edge = on_alley
                    offer({
                        **base, "stalls": n_al,
                        # The aisle inside the lot is only what the alley's
                        # width leaves short of the back-out room, along the
                        # row; the rest of the aisle IS the alley. The
                        # pavement past that is the setback strip, as on
                        # the lane-less plan below.
                        "aisle": shortfall_ft, "span_ft": n_al * stall_w,
                        "stall_boxes": boxes,
                        "driveway": None, "driveway_len_c": 0,
                        "driveway_len": alley_setback_ft,
                        "method": "townhome_rear_court_alley_aisle",
                    })
                if n_ct <= 0:
                    continue
                # THE COURT IS TRIMMED TO WHAT IT PARKS (2026-09-19). The
                # rectangle is the room behind the building; the court is the
                # rows it seats and the aisle between them, `rows` deep and as
                # many stalls wide as it parks, the way the paper lot charges
                # it (`flats.score.paper.court_depth`). Until this date the
                # court WAS the rectangle -- a two-row court on a deep lot put
                # its second row at the back of the lot with forty feet of
                # "aisle" between, its side ran the side street's whole
                # length, and it paved the aisle across the lot's whole width
                # -- which is the opposite of the sufficient, minimal parking
                # Steph's ruling asks for, and made the rear court lose to the
                # side court on any lot wide enough to hold one. Two rows
                # where the room allows and one where it does not, and one
                # row also tried where two fit: the shallower court is the
                # one that hides from a side street. Each court is placed at
                # each corner of the room (`_court_places`) -- against the
                # building or the back, the left side or the right -- and the
                # lane is found from where it stands: a court that can slide
                # off the side street's strip is offered there, exposure
                # zero and a lane to the street, beside the one that stands
                # on the strip with none; the ruling chooses.
                # The lane the WHOLE room finds to the alley or the side
                # street says where its mouth is; the trimmed court is also
                # placed under it (`_court_places`), which is how a court
                # in a room far bigger than itself reaches a mouth that
                # meets the room mid-side.
                room_lane = None
                if alley_fed or smouths is not None:
                    room_lane = _lane_to_alley(free, mouths if alley_fed else smouths,
                                               rr, cc, rh, rw, drive_c)
                front_run = (_front_runs(free, fcells, rr)
                             if front_lane_ok and not alley_fed else None)
                for rows_u in ((2, 1) if rows == 2 else (1,)):
                    n_u = min(cap, rows_u * int(cw_ft // stall_w))
                    if n_u <= 0:
                        continue
                    rh_u = min(rh, rows_u * sd_c + aisle2_c)
                    rw_u = min(rw, math.ceil(n_u / rows_u) * sw_c)

                    # The one-row court turns its aisle toward the lane: at
                    # its front for a lane down the pod's side or out of the
                    # court's own side, at its back for a lane out of its
                    # back to the alley or the far street. The two-row
                    # court's aisle is between its rows either way.
                    def court(r_u, c_u, aisle_first=False, rows_u=rows_u, n_u=n_u,
                              rh_u=rh_u, rw_u=rw_u):
                        return {**bld, "rect": (r_u, c_u, rh_u, rw_u), "stalls": n_u,
                                "aisle": aisle_two, "span_ft": rw_u * res,
                                "stall_boxes": _row_boxes(r_u, c_u, rh_u, rw_u, rows_u,
                                                          n_u, sw_c, sd_c, aisle_first)}

                    def aisle_rows(r_u, rows_u=rows_u, rh_u=rh_u):
                        # Where a side lane should meet the court: its front
                        # aisle (one row, turned toward the lane) or the band
                        # between its rows (two).
                        a0 = r_u if rows_u == 1 else r_u + sd_c
                        return (a0, a0 + aisle2_c)

                    places = _court_places(rr, cc, rh, rw, rh_u, rw_u, room_lane, drive_c,
                                           (0 if rows_u == 1 else sd_c, aisle2_c))
                    if alley_fed:
                        # From the alley: a straight lane from the court to the
                        # cells on the alley strip, or none at all when the
                        # court already stands there. Nothing is drawn from the
                        # street; the city forbids it, and a lot that cannot be
                        # reached from the alley is refused rather than handed
                        # the street lane.
                        for r_u, c_u in places:
                            lane = _lane_to_alley(free, mouths, r_u, c_u, rh_u, rw_u, drive_c,
                                                  aisle_rows(r_u))
                            if lane is None:
                                continue
                            r0, c0, h, w = lane
                            lane_len_c = h if w == drive_c else w
                            offer({
                                **court(r_u, c_u, aisle_first=(w != drive_c)),
                                "driveway": lane if lane_len_c else None,
                                "driveway_len_c": lane_len_c,
                                "driveway_len": lane_len_c * res + alley_setback_ft,
                                "method": "townhome_rear_court_alley",
                            })
                        continue
                    if smouths is not None:
                        # From the side street: the same lane the alley gets,
                        # out of the court's side (or its back, on a lot the
                        # street wraps) to the cells on the side street's
                        # strip, or none when the court already stands there;
                        # the strip itself is the driveway's last stretch. On
                        # a through lot the lane out of the court's BACK
                        # reaches the far end's street: the rear-street lane,
                        # its own name.
                        for r_u, c_u in places:
                            lane = _lane_to_alley(free, smouths, r_u, c_u, rh_u, rw_u, drive_c,
                                                  aisle_rows(r_u))
                            if lane is None:
                                continue
                            r0, c0, h, w = lane
                            lane_len_c = h if w == drive_c else w
                            offer({
                                **court(r_u, c_u, aisle_first=(w != drive_c)),
                                "driveway": lane if lane_len_c else None,
                                "driveway_len_c": lane_len_c,
                                "driveway_len": lane_len_c * res + street_sb,
                                "method": ("townhome_rear_court_rear_street"
                                           if through and w == drive_c
                                           else "townhome_rear_court_side_street"),
                            })
                    if not front_lane_ok:
                        continue
                    # Side driveway: first clear column run (in the envelope,
                    # clear of the building) at least drive_c wide, running
                    # alongside the building from the front street's strip
                    # down to the room behind it (`_front_runs`: each column
                    # from its own first free cell, so a front that bends
                    # still carries a lane beside the pod), whose columns
                    # overlap that room so cars can reach it. The court
                    # stands against the building with the lane meeting one
                    # end of its aisle: slid to the lane's left edge or its
                    # right, whichever the ruling prefers on this lot.
                    clear, start = front_run
                    corridor_c0, run = None, 0
                    for c in range(C):
                        run = run + 1 if clear[c] else 0
                        if run >= drive_c:
                            c0 = c - drive_c + 1
                            if c0 < cc + rw and c0 + drive_c > cc:  # lane meets the room
                                corridor_c0 = c0
                                break
                    if corridor_c0 is None:
                        continue
                    r_top = int(start[corridor_c0:corridor_c0 + drive_c].max())
                    for c_u in sorted({min(max(cc, corridor_c0 + drive_c - rw_u), cc + rw - rw_u),
                                       min(max(cc, corridor_c0), cc + rw - rw_u)}):
                        offer({
                            **court(rr, c_u, aisle_first=True),
                            "driveway": ((r_top, corridor_c0, rr - r_top, drive_c)
                                         if rr > r_top else None),
                            "driveway_len_c": rr - r_top,
                            "driveway_len": (rr - r_top) * res + street_sb,
                            "method": "townhome_rear_court",
                        })

    plan = best[1]
    if plan is None:
        return {**fail, "layout_fail": REACH[reach], "fronts_tried": len(fronts),
                "through_lot": any_through}
    stalls, method = plan["stalls"], plan["method"]

    # --- realize the chosen plan into geometry (rotate back to CRS) --------
    rot, minx, miny = plan["rot"], plan["minx"], plan["miny"]
    bname, br, bc, bh, bw, building_area = plan["bld"]
    rr, cc, rh, rw = plan["rect"]
    parking_area = plan["parking_area"]
    driveway_len = plan["driveway_len"]
    open_space, open_space_ok = plan["open_space"], plan["open_ok"]
    geoms: dict = {}

    def cell_box(r0: int, c0: int, h: int, w: int):
        return box(minx + c0 * res, miny + r0 * res,
                   minx + (c0 + w) * res, miny + (r0 + h) * res)

    def emit(name: str, g):
        geoms[name] = affinity.rotate(g, rot, origin=origin)

    emit("building", cell_box(br, bc, bh, bw))
    emit("parking_court", cell_box(rr, cc, rh, rw))
    if plan["driveway"] is not None:
        dr0, dc0, dh, dwid = plan["driveway"]
        emit("driveway", cell_box(dr0, dc0, dh, dwid))
    bx_center = minx + (bc + bw / 2.0) * res
    emit("utility", LineString([(bx_center, miny + br * res), (bx_center, miny)]))

    for i, (y0, x0, h, w) in enumerate(plan["stall_boxes"]):
        emit(f"stall_{i}", cell_box(y0, x0, h, w))

    ok_plan = plan["ok"]
    return {
        # A drawn plan can still be rejected, and those two rejections are not
        # "no layout" -- there IS a layout, it is short of stalls or short of
        # the city's open-space reserve. Naming them separately keeps them out
        # of the geometry bucket, where they would read as land that cannot
        # hold the product.
        "layout_fail": ("" if ok_plan
                        else "too_few_stalls" if stalls < min_stalls
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
        # Which street the plan faces (s4's bearing of its front lot line)
        # and how many the lot was drawn to, so a run can count where the
        # city's rule or Steph's ruling chose -- and the feet of the court's
        # edge on a street, the number the ruling's third test read.
        "front_bearing_deg": float(plan["front_deg"]),
        "fronts_tried": len(fronts),
        "court_street_ft": float(round(plan["exposure"], 1)),
        "through_lot": any_through,
        "geoms": geoms,
    }


def _work_chunk(chunk):
    import shapely

    out = []
    for (idx, env_wkb, bearings, fedges, area, fsb, jur, zone, psb, aedges, asb, aw,
         ssb, xy) in chunk:
        r = layout_lot(env_wkb, bearings, fedges, area, fsb, jur, zone, psb,
                       aedges, asb, aw, ssb, xy)
        r["geoms_hex"] = {role: shapely.to_wkb(g).hex() for role, g in r.pop("geoms").items()}
        out.append((idx, r))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--processes", type=int, default=max(1, cpu_count() - 2))
    ap.add_argument("--limit", type=int, help="only first N in-scope lots (debug)")
    args = ap.parse_args()

    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq
    import shapely

    rules = load_rules()
    fps = load_footprints()
    sp = fps.siteplan
    res = rules.defaults.grid_resolution_ft

    lots = read_stage("s6_lots")  # every column except geom (dropped in s6)
    # Re-attach the carved setback envelope (s5o geom) — s6 drops it.
    s5o = read_stage("s5o_lots")[["TLID", "geom"]].rename(columns={"geom": "env_geom"})
    lots = lots.merge(s5o, on="TLID", how="left")
    # The alley's width is s4's (`alley_width_ft`, the gap in the taxlot
    # fabric), taken from s4's own parquet the way s7 takes the lot width,
    # so an s4-only refresh reaches the plans without the stages between.
    # NaN where the lot has no alley edge or the stage predates the column,
    # and NaN is laid out as zero: an alley of no known width earns no
    # back-out room.
    _s4p = stage_path("s4_lots")
    lots = lots.drop(columns=[c for c in ("alley_width_ft",) if c in lots.columns])
    if "alley_width_ft" in pq.read_schema(_s4p).names:
        lots = lots.merge(pd.read_parquet(_s4p, columns=["TLID", "alley_width_ft"]),
                          on="TLID", how="left")
    else:
        lots["alley_width_ft"] = float("nan")

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
    front_deg = np.full(n, np.nan)
    fronts_tried = np.zeros(n, dtype=int)
    court_street = np.full(n, np.nan)
    through = np.zeros(n, dtype=bool)
    extra = {"front_bearing_deg": front_deg, "fronts_tried": fronts_tried,
             "court_street_ft": court_street, "through_lot": through}

    if sp is None or not sp.enabled:
        print("s6s: siteplan disabled in footprints.yaml — writing passthrough columns")
        _finalize(lots, site_ok, tier, stalls, method, lfail, bname, drive_len,
                  drive_w, park_area, open_sqft, open_req, open_ok, sp_json,
                  extra=extra)
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
                  drive_w, park_area, open_sqft, open_req, open_ok, sp_json,
                  extra=extra)
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
    # it -- the alley setback on a tier A/B lot (zero in Portland's R zones,
    # Gresham's alley column plus its roof plane),
    # the largest of the four on a tier C lot -- and that strip is what an
    # alley-fed lane crosses. See `_alley_setback_for`.
    def _alley_setback(jur: str, zone: str, area: float = 0.0,
                       tier: str = "A") -> float:
        return _alley_setback_for(rules, jur, zone, area, tier)

    # ... and off every STREET edge, which on a corner lot is the larger of
    # the front and street-side setbacks: the strip a lane from the side
    # street crosses. See `_street_setback_for`.
    def _street_setback(jur: str, zone: str, area: float = 0.0,
                        tier: str = "A") -> float:
        return _street_setback_for(rules, jur, zone, area, tier)

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
            "alley_aisle": bool(dw and dw.alley_is_aisle),
            # The back-out room the alley's width is measured against: the
            # city's own number where its row states one, else its one-way
            # aisle (Figure 9.0825A's reading, in Gresham's case).
            "alley_need": (dw.alley_backout_ft
                           if dw and dw.alley_backout_ft is not None
                           else g.aisle_one_way_ft),
            # Which street is the front on a corner lot, and which street its
            # driveway may come from -- the city's own words, mirrored from
            # FLATS (`front_lot_line_corner`, `corner_access_street`); see
            # `_candidate_fronts` and `layout_lot`. None where unread.
            "front_rule": dw.front_lot_line_corner if dw else None,
            "access_rule": dw.corner_access_street if dw else None,
            # Whether a vehicle area may stand between the building and a
            # street (`parking_front_prohibited`: Portland 33.266.120.C.1.a,
            # Milwaukie 19.505.3.D.4.a). Exempt or unread reads as no ban.
            "front_ban": bool(dw and dw.parking_front_prohibited),
        }

    # Said per city because the two words decide the drawing on every corner
    # lot: which street the pod faces, and whether the lane may come in from
    # the side street. `lowest_class` is drawn as `any` -- no stage holds a
    # street's functional classification -- and says so.
    for j in cities:
        fr, ar = cells[j]["front_rule"], cells[j]["access_rule"]
        front = {"shortest": "the SHORTER street is the front",
                 "owner": "the owner picks the front, so both streets are tried",
                 "entrance": "the entrance sets the front, so both streets are tried",
                 "both": "both streets are fronts, so both are tried",
                 None: "front rule unread: the longer street is the front"}[fr]
        lane = {"any": "the lane may come from either street",
                "side": "the lane comes from the SIDE street only",
                "lowest_class": "the lane comes from the lower-classified street "
                                "first, which nothing measures, so drawn as either",
                None: "access rule unread: the lane comes from the front street"}[ar]
        print(f"s6s: {j} corner lots -- {front}; {lane}")
    banned = [j for j in cities if cells[j]["front_ban"]]
    if banned:
        print(f"s6s: {', '.join(banned)} ban a vehicle area between the building "
              f"and a street (parking_front_prohibited): a through lot there is "
              f"refused the rear court and offered the side court only; a corner "
              f"lot's side court keeps off the side-street side")

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
        "target_stalls": sp.target_stalls(),
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
        _aw = row["alley_width_ft"]
        tasks.append((
            int(i), shapely.to_wkb(row["env_geom"]),
            json.loads(row["front_bearings_json"]), fedges,
            float(row["area_sqft"]),
            _front_setback(jur, zone, float(row["area_sqft"])), jur, zone,
            sp.parking_street_setback_for(jur, zone),
            aedges, _alley_setback(jur, zone, float(row["area_sqft"]),
                                   str(row["tier"])),
            None if _aw is None or not np.isfinite(float(_aw)) else float(_aw),
            _street_setback(jur, zone, float(row["area_sqft"]), str(row["tier"])),
            # the lot's corners, for the length of a street lot LINE
            [(e[0], e[1]) for e in edges],
        ))
    for j, k in alley_fed.items():
        print(f"s6s: {j} sends the driveway to the alley on a lot that has one "
              f"(alley_access_required); {k:,} lots in scope carry an alley edge "
              f"and are laid out from it, with no lane from the street"
              + (f"; the alley is the aisle where that seats more stalls "
                 f"(alley_is_aisle), with {cells[j]['alley_need']:g} ft of back-out "
                 f"room asked of its measured width" if cells[j]["alley_aisle"] else ""))

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
        front_deg[idx] = r["front_bearing_deg"]
        fronts_tried[idx] = r["fronts_tried"]
        court_street[idx] = r["court_street_ft"]
        through[idx] = r["through_lot"]

    _finalize(lots, site_ok, tier, stalls, method, lfail, bname, drive_len,
              drive_w, park_area, open_sqft, open_req, open_ok, sp_json,
              assumed_cities=assumed, extra=extra)

    ev = stalls >= 0
    print(f"s6s: evaluated {int(ev.sum()):,} lots; "
          f"site_plan_ok {int(site_ok.sum()):,}; tiers "
          + ", ".join(f"{t}={int((tier == t).sum()):,}"
                      for t in ("preferred", "target", "minimum", "fail")))
    # The plans that stand on the alley's width, said out loud for the same
    # reason the assumed aisle is: a caveat that only lives in a column is a
    # caveat nobody reads -- and here the width is measured, so say that too.
    on_alley = method == "townhome_rear_court_alley_aisle"
    if on_alley.any():
        per = lots.loc[on_alley, "jurisdiction"].value_counts()
        _w = pd.to_numeric(lots.loc[on_alley, "alley_width_ft"],
                           errors="coerce").to_numpy(dtype=float)
        _need = np.array([cells[j]["alley_need"]
                          for j in lots.loc[on_alley, "jurisdiction"]], dtype=float)
        _short = np.maximum(0.0, _need - np.nan_to_num(_w, nan=0.0))
        _ok = np.isfinite(_w)
        print(f"s6s: {int(on_alley.sum()):,} plans park against the alley and "
              f"back out into it (alley_is_aisle): "
              + ", ".join(f"{j} {v:,}" for j, v in per.items())
              + f"; the alley's width is on record for {int(_ok.sum()):,} of them"
              + (f" (p50 {np.median(_w[_ok]):.0f} ft)" if _ok.any() else "")
              + f", {int((_short > 0).sum()):,} pave the shortfall of the back-out "
                f"room on the lot"
              + (f" (p50 {np.median(_short[_short > 0]):.0f} ft)"
                 if (_short > 0).any() else ""))
    line = _corner_summary(lots["front_bearings_json"].to_numpy(),
                           lots["jurisdiction"].to_numpy(), fronts_tried,
                           front_deg, method, cities, through)
    if line:
        print(line)
    for line in _through_summary(lots["jurisdiction"].to_numpy(), through,
                                 site_ok, method, lfail, cities, banned):
        print(line)
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


def _through_summary(jurisdiction, through, site_ok, method, lfail, cities,
                     banned) -> list[str]:
    """The through lots and the side courts, per city, so a run can be
    compared with the one before (FOLLOWUPS 5 iii/iv): how many lots have
    a street at both ends and how many of them drew a plan; how many plans
    park beside the building, and from where; how many take the lane in
    from the far street; and, in the cities that ban a court between the
    building and a street, how many through lots the ban left with nothing."""
    import numpy as np

    through = np.asarray(through, dtype=bool)
    ok = np.asarray(site_ok, dtype=bool)
    method = np.asarray(method)
    lfail = np.asarray(lfail)
    per = np.asarray(jurisdiction)
    side = np.isin(method, ["townhome_side_court", "townhome_side_court_alley"])
    rear_st = method == "townhome_rear_court_rear_street"
    out: list[str] = []
    if through.any():
        out.append(f"s6s: {int(through.sum()):,} through lots (a street at both ends) "
                   f"drawn to each end; {int((through & ok).sum()):,} draw a plan, "
                   f"{int((through & rear_st).sum()):,} of them with the lane from the "
                   f"far street: "
                   + ", ".join(f"{j} {int((through & (per == j)).sum()):,}/"
                               f"{int((through & ok & (per == j)).sum()):,}/"
                               f"{int((through & rear_st & (per == j)).sum()):,}"
                               for j in cities if (through & (per == j)).any()))
    if side.any():
        alley = method == "townhome_side_court_alley"
        out.append(f"s6s: {int(side.sum()):,} plans park BESIDE the building "
                   f"(townhome_side_court; {int(alley.sum()):,} from the alley), "
                   f"{int((side & ok).sum()):,} of them a plan the lot is graded on: "
                   + ", ".join(f"{j} {int((side & (per == j)).sum()):,}/"
                               f"{int((side & ok & (per == j)).sum()):,}"
                               for j in cities if (side & (per == j)).any()))
    for j in banned:
        m = through & (per == j)
        if not m.any():
            continue
        lost = m & ~ok & np.isin(lfail, ["no_court", "court_too_shallow",
                                         "no_side_lane", "no_alley_lane"])
        out.append(f"s6s: {j} refuses the rear court on its {int(m.sum()):,} through "
                   f"lots (parking_front_prohibited): {int((m & side).sum()):,} draw a "
                   f"side court, {int((m & ok).sum()):,} draw a plan the lot is graded "
                   f"on, {int(lost.sum()):,} draw nothing")
    return out


def _corner_summary(bearings_json, jurisdiction, fronts_tried, front_deg, method,
                    cities, through=None) -> str | None:
    """The corner lots, said per city so a run can be compared with the one
    before: how many were drawn to more than one front, how many face a
    street other than s4's first (the longest) bearing, and how many take the
    lane in from the side street -- the three numbers FOLLOWUPS 5 moves.
    None when no lot was drawn to two fronts.

    `bearings_json` is s4's `front_bearings_json`: "[]" on a lot with no street
    bearing at all -- an empty LIST, not an empty string, which is why the
    first bearing is read through `or`. A through lot is drawn to each of
    its ends and is not a corner lot: `through` keeps it out of this count
    (`_through_summary` has it)."""
    import numpy as np

    fronts_tried = np.asarray(fronts_tried)
    two = fronts_tried >= 2
    if through is not None:
        two = two & ~np.asarray(through, dtype=bool)
    if not two.any():
        return None
    first = np.array([(json.loads(b) or [float("nan")])[0] if b else float("nan")
                      for b in bearings_json], dtype=float)
    front_deg = np.asarray(front_deg, dtype=float)
    other = two & np.isfinite(front_deg) & (np.abs(front_deg - first) > 1e-6)
    side = np.asarray(method) == "townhome_rear_court_side_street"
    per = np.asarray(jurisdiction)
    return (f"s6s: {int(two.sum()):,} corner lots drawn to each street the city "
            f"allows as the front; {int(other.sum()):,} chose the street s4 did "
            f"not list first; {int(side.sum()):,} plans take the lane in from "
            f"the side street: "
            + ", ".join(f"{j} {int((two & (per == j)).sum()):,}/"
                        f"{int((other & (per == j)).sum()):,}/"
                        f"{int((side & (per == j)).sum()):,}"
                        for j in cities if (two & (per == j)).any()))


def _finalize(lots, site_ok, tier, stalls, method, lfail, bname, drive_len,
              drive_w, park_area, open_sqft, open_req, open_ok,
              sp_json, assumed_cities=(), extra=None) -> None:
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
    # Which street the plan faces, how many it was drawn to, and the feet of
    # its court on a street (FOLLOWUPS 5). NaN / 0 where nothing was drawn.
    for col, arr in (extra or {}).items():
        lots[col] = arr
    write_stage(lots, "s6s_lots")


if __name__ == "__main__":
    main()
