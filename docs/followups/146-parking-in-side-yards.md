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

SCOUT 2026-11-04 (Copilot gpt-6-luna, 8.2 AI units; quotes SEEN, verdicts NOT yet checked by Claude):
- ALLOWS: Canby CMC 16.22.010(b) (residential parking "to the side of the building", not a street-facing side yard; cmc.16.22.010.txt#L15);
  Beaverton BDC 60.30.10.B (RMA/RMB/RMC/CM-RM, middle housing "may be located in side and rear yards"; 60.30.10.txt#L404-L406).
- FORBIDS (townhouse model code "No off-street parking ... in the front yard or side yard of a townhouse"): Oregon City 17.16.040.B.1
  (17.zoning.txt#L5349), Wilsonville 4.113 (#L417), Fairview 19.30.050 (#L118), Gresham 7.0431 (#L39); Cornelius required yards
  (encoded). NOTE: our yaml carries parking_side_prohibited exempt:true in most places -- read WHY before relying on it; and
  "off-street parking" may not reach a DRIVE LANE (a driveway is not a parking space in most of these codes) -- the lane and the
  stalls may need separate answers.
- BUFFER: Gladstone 10 ft stalls / drives+aisles allowed within 10 ft (17.10.065 #L62-L64; encoded 5 -- check); Tualatin 10 ft
  landscape setback parking areas, townhouse/quadplex driveways allowed within 5 ft (73C.220 #L3, 73C.090 #L97-L98);
  Multnomah uninc 5 ft non-street (39.8045 #L23, encoded).
- UNCLEAR: Happy Valley "landscaped yard areas" (16.43.030 #L513); Milwaukie 19.600 #L955 + quadplex/townhouse split; Sandy
  (street-abutting side yards only, SDC 17.98.50 #L253); Troutdale 8.130.C.4 (depends on meeting (a)); Hillsboro 12.50.715 vs
  12.50.350; WashCo uninc overlays.
- SILENT (not "allowed"): Clackamas uninc, Estacada, Johnson City, Lake Oswego, Rivergrove, West Linn, Portland interior sides
  (33.266.120 sets nothing), Wood Village, Durham, King City, Sherwood, Tigard. Maywood Park: no stored code.
Next (after the overlays): Claude reads each, settles drive lane vs stalls, and how "silent" is treated (a setback is a BUILDING
setback in most codes; whether flat paving may sit in it may be answered by each code's "allowed in setbacks" list) -- likely a
Steph question with a recommended default.

PORTLAND VERIFIED by Claude 2026-11-04 (Steph also brought another AI's answer, which agrees): ALLOWED in interior side
setbacks. Chain: 33.120.220.txt#L13 "Setbacks for parking areas are in Chapter 33.266." -> 33.266.120 (houses, attached houses,
duplexes..fourplexes, any zone) sets no interior side/rear limit -- only no vehicle area between building and street (C.1.a), 40%
front paving cap and 20% side-street cap on corners (C.1.b), no stall within 10 ft of the front line or in a side-street setback
(C.2.a), alley access (C.3). Paving is at grade (33.120.280.txt#L107: structures <= 2.5 ft high allowed in all building
setbacks). 33.120.235.C.1 L1 setback landscaping exempts "development allowed in the setbacks" and sites <= 10,000 sq ft, except
the EPA rear-setback 50% cap (ruled by area, 2026-11-04). The other AI said the 40% cap is "single-dwelling areas": wrong -- it
follows the building type, so it binds our RM lots too (already encoded? check before building).
- 2026-11-05 STARTED (for the Monday sizing study, FOLLOWUPS 149): Copilot builds the mechanism on flats/side-yard-parking (field parking_side_yard_allowed none|lane|lane_and_court; unset = today); batch reader verifies every city. [Steph] silent codes: allowed or not?
