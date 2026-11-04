# 146. Let the drive lane (and court) use the side setback where the code allows it.

146. [Claude] [GO Steph 2026-11-04: after the overlays] [scan: YES -- reds/yellows only go green]
   **Let the drive lane (and court) use the side setback where the code allows it.**

Raised 2026-11-04 from Steph's question "are we currently placing parking within setbacks?" (FOLLOWUPS 68).

TODAY (flats/score/paper.py paper_fit ~L1441-L1452, behind_wall_ft ~L521):
- REAR yard: the court SHARES it (parks inside the rear setback) everywhere, unless the code keeps
  parking out of required yards (`parking_required_yard_prohibited`, Cornelius) or states a planted
  strip (`parking_lot_line_buffer_ft`: Gladstone, Tualatin, Hillsboro, Multnomah + WashCo uninc).
- SIDE yards: never used. Width needed = building + drive lane beside it (or the stall row, if wider)
  + BOTH side setbacks. The lane and the court are searched inside the envelope the side setbacks cut.
- FRONT: `parking_street_setback_ft` and the no-parking-between-building-and-street rules.

PORTLAND (checked 2026-11-04): the pod is an attached-house / fourplex development, so parking is
governed by PCC 33.266.120, not 33.266.130 (33.266.130.B excludes residential vehicle areas subject
to 33.266.120; Table 266-5's 5 ft perimeter strip therefore does not apply). 33.266.120 sets no
side- or rear-lot-line buffer: only no vehicle area between building and street (C.1.a), 40% front
paving cap (C.1.b), no stall within 10 ft of the front line (C.2.a), alley access when there is one
(C.3), 9x18 stalls and a 9 ft min driveway (D). So a Portland drive lane may run in the side setback.

SIZE (live run 113, rough): 29,772 RED lots bound by fit_ft miss by under 10 ft. Some share are WIDTH
misses that letting the lane overlap one side setback (typically 5 ft) would clear; not measured.

WORK if Steph says go:
(a) per-city reading: does each code let a driveway / parking aisle / stalls sit in a required side
    setback, and with what strip? New field (e.g. `parking_side_yard_allowed` + reuse
    `parking_lot_line_buffer_ft`); unread = today's behaviour (conservative).
(b) paper_fit + quadfit envelope: where allowed, the lane (and court) may overlap ONE side setback
    down to the buffer; the building still keeps its full side setbacks. Fire access, turning, the
    40%-front-paving style caps and frontage-share caps still bind.
(c) bound per city, read every gain.

GO 2026-11-04 (Steph: "Yes"), to start after the Portland plan-district overlays (109 part 2). Prep now: Copilot read-only scout collects every city's side-setback parking/driveway text with quotes (brief docs/copilot/briefs/side-yard-parking-scout.txt); Claude verifies each quote before any encoding.
