# B3 notes -- unincorporated Washington County (R-5, R-6, TO:R18-24), run 74

Stored code: flats/provenance/docs/or/washington/_unincorporated/ (CDC). Lots: work/groups/B3.txt (15).

## Method
- Geometry from work/dossiers.jsonl (lot ring, neighbours with geometry, the green design's drawn
  building / court / lane / envelope). Read-only SELECT on the production DB only for a reach count.
- Street half-width, two ways, for every lot line that faces no neighbour: (a) a ray from the
  middle of the line out to the first parcel across ("gap"; half of it = existing half-width);
  (b) distance to the county's own street centreline (public layer gispub LUT_PDS/Base_Layers
  MapServer/1 "All Streets", which also gives owner/maintainer). Street class from the county TSP
  layer (LUT_PDS/TSP_Layers MapServer/4, FClass2: 5 NR, 4 Collector, 3 Arterial, 1 Freeway; local
  streets are not drawn). The gap is the main measure, as the protocol says; the centreline is
  the cross-check. Where they disagree I say so.
- Dedication test: cut the strip (required half-width minus existing) off the lot along that line,
  move the setback line in by the same amount, then search translations of the drawn layout
  (building inside the cut envelope, court and lane inside the cut lot), 0.5 ft steps, +/-60 ft.
  No rotation (the screen's 181 angles could only do better), so "fits after an X ft shift" is a
  lower bound on the room. Scripts in my scratchpad, not kept in the repo.
- Every lot: assessor prop_code 101 SFR with an ordinary house (no POLICY note needed), no flood
  or floodway, inside UGB, no z-overlay, single zone (zone_frac >= 0.998), every street owned and
  maintained by Washington County (public), fire route 81.7-137.4 ft (<= 150).

## Common reading
1. USE. Quadplex is Middle Housing (430-84 preamble, cdc.430-84.middle-housing.txt:3-10; 430-84.3
   A(1) :92-96). R-5 Type I under 302-2.14 (cdc.302.r-5.txt:86-114): A. <= 16,500 sf buildable, or
   B. more and the units meet 4 u/ac; C. on a public street, ROW to 25 ft (local) / 30 (NR) / 37
   (Collector) / 45 (Arterial) from centerline "or the applicant proposes to dedicate", none due
   "If road improvements built to ultimate County standard exist" (:93-104); recorded before the
   first building permit (C(2)). R-6 the same at 13,100 sf and 5 u/ac (cdc.303.r-6.txt:86-114).
   TO districts are different -- see lot 2.
   418-2 (future-ROW setbacks) "does not apply to ... Middle Housing" (cdc.418-419.setbacks-height.txt:34-36);
   the 2.14 C strip is the operative rule. 501-8.4 dedication also applies to Middle Housing
   (cdc.501.public-facilities.txt:70-80).
2. LOT. Quadplex parent lot 7,000 sf "based on lot size prior to any right-of-way dedications"
   (cdc.302.r-5.txt:341-348; R-6 :350). No frontage minimum for a Quadplex (302-7.1 E(2)).
3. BUILDING. Front 15 ft to front wall (cdc.302.r-5.txt:357; R-6 :361), street side 8 (:367 / :371),
   side 5, rear 15, height 35 (pod 26; no cap between 22 and 30). Yards measured from "the property
   line, sidewalk, or easement for public travel, whichever is closest".
4. PARKING/ACCESS. 430-84.3 B(4) (cdc.430-84.middle-housing.txt:219-247): 32 ft of approaches; the
   collector/arterial spacing of 501-8.5 B reaches a Quadplex only when ALL frontages are
   collector/arterial (B(4)(c)(ii)); 501-8.5 preamble agrees (cdc.501.public-facilities.txt:"For
   Middle Housing, access spacing requirements Section 501 apply only to ... specific circumstances").
   Parking grade <= 5% (413-4.8, cdc.413.parking.txt:174). 413-4.9 10 ft parking setbacks are for
   parking "not associated with a structure" (:175-177) -- the pod's court is associated, so courts
   reaching a rear line are not a miss.
8. UNCHECKED (same list on every lot: frontage, width, depth, depth ratio, coverage, FAR, stories,
   min height, density): 302-7.1 / 303-7.1 carry none of these numbers for a Quadplex; density is
   "not a consideration" (302-6.1). 430-84.3 A(7) sends a below-minimum-density plex to 430-37.1 B
   (future development plan); every R-5/R-6 lot here is far above 4 / 5 u/ac.

## 1. 1S118BC04000 (R-5, 18240 SW Kinnaman Rd) RIGHT
20,368 sf, single frontage 111.8 ft on SW Kinnaman Rd = TSP Collector (FClass2 4). Gap 49.5 ft
(half 24.75), county centreline 25.4 ft -> strip ~11.6-12.3 ft. 20,368 > 16,500 so 302-2.14 B:
4 / 0.4676 ac = 8.6 u/ac >= 4; max slope 17.6% so all buildable. Pod56 green, slack 87.5, building
15.2 ft from the line; with a 12.25 ft strip the layout fits after a 12.1 ft shift (court has ~76 ft
behind it). Pod80 also green, same shift. Fire 116 ft (+12 ft = 128). Neighbour to the west is an
INST lot (not this lot). The 9.2 ft west sliver faces a 9 ft gap to the INST parcel, not a street.

## 2. 1S103DA00200 (TO:R18-24, 10855 SW Butner Rd) WRONG -> RED
- USE. Table A (cdc.375.transit-oriented.txt:695-700): "Middle Housing - Section 430-84 ... (30.c.)"
  = "N N N I/II I/II I/II N N N" (TO:R18-24 is the sixth column). 375-7 30.c (:439-445): "Type I:
  Middle Housing may be allowed, through a Type I procedure, on an existing lot or parcel that was
  approved through a Standard Subdivision or Standard Partition plat for the construction of a
  detached dwelling, provided that the lot or parcel meets the following: (i) Does not exceed 10,000
  square feet in buildable area." Unlike R-5/R-6 there is no "or B. exceeds ... and meets density"
  Type I branch. So above 10,000 sf buildable the only path is Type II.
- LOT. 21,377 sf. Unbuildable (300-3.1, cdc.300.introduction.txt:103-122): slope max 10.2% (none
  over 20%), no flood/wetland; G. future ROW for Collectors = Butner Rd strip ~12 ft x 102 ft
  ~1,200 sf. Buildable ~20,000 sf, twice the 10,000 cap.
- The layer (_unincorporated.yaml ~1538-1544, TO:R9-12 reused for TO:R18-24) says "30.c. is the Type
  I path on an existing platted lot of up to 10,000 sq ft buildable; the rest is Type II" and still
  sets quadplex_allowed true; checks.ask = as_of_right. Under the by-right ruling a Type II review
  on the only path = RED.
- Also seen (not needed for the ruling): TO front yard 10 min / 15 max (Table B(1)); pod56 building
  10.0 ft from Butner Rd; Butner is a Collector (gap 50, centreline 17.3 ft) so a 12 ft strip would
  also push the max-15 ft front window back; rear line faces the Sunset Hwy ramp (ODOT). 4 units on
  0.49 ac = 8.2 u/ac is below TO:R18-24's 18 u/ac "other housing" minimum, so 430-84.3 A(7) would
  also pull in 430-37.1 B (not held in the store).
- Kind: NEW (TO 10,000 sf buildable-area Type I gate not encoded), by-right family. REACH (read-only
  SQL, run 74): 26 WashCo-uninc greens in TO:R9-12/R12-18/R18-24, 22 of them over 10,000 sf lot
  area (buildable area may be a little less).

## 3. 1S124DD04600 (R-5, 7715 SW 69th Ave) RIGHT
10,315 sf, single frontage 73.9 ft. No TSP line within 250 ft (local). Gap 49.9 (half 25.0),
centreline 28.8 -> no strip. Pod56 slack 16.5, building 15.3 ft from the line (depth-facing),
lane along the south side to a rear court. Max slope 24% off the design; grade 2.7%.

## 4. 1S201CA07300 (R-5, 19865 SW Jay St) RIGHT
Corner, 11,032 sf. SW 199th Ct (west, 63.6 ft) = TSP Neighborhood Route: gap 50.0, centreline 26.1
-> strip 3.9-5.0 ft. SW Jay St (south, 125 ft) local, gap 50 -> none. Pod56 faces 199th Ct, building
16.5 ft from it; with a 5 ft strip it needs 20 ft; the layout fits after a 3.5 ft shift east (slack
41 ft along Jay). Court 13.7 ft from Jay, drive on Jay (side street) -- corner rule and 430-84.3
B(4)(c)(iii) met. Pod80 red (fit -2.0) is not the green design.

## 5. 1S211BA06900 (R-6, 21670 SW Imperial Ct) RIGHT
9,586 sf on a curved local frontage (four 16.5 ft chords) beside the cul-de-sac. Gap 50, centreline
25.5-26.9 -> no strip. Pod56 FIT-TIGHT, bounds -0.5..+0.5 ft: inside the 1 ft fit ruling. Envelope is
14.4 ft from the chords (curve simplification) but the building is 16.2-19.2 ft from them. Court
runs to the rear line (413-4.9 does not reach associated parking). Grade 1.8%.

## 6. 2S108BD05100 (R-6, 14540 SW Juliet Ter) RIGHT
Corner, 15,621 sf. 303-2.14 B applies (> 13,100): 4 / 0.3586 ac = 11.2 u/ac >= 5. SW Bull Mountain
Rd (north) = TSP Collector: gap 58.5 (half 29.25), centreline 30.9 -> strip 6.1-7.75 ft; it is the
street side (8 ft): building 31.0 ft, court 29.5 ft from it -> fine. SW Juliet Ter (west, local):
gap 46 (half 23), centreline 26.3 -> up to 2 ft; building 24 ft from it (15 ft front) -> fine.
Lane runs along the south of the building from Juliet (local side street) to the court. Steep ground
3,465 sf carved (envelope jagged), max slope 35.8%; court grade 1.9%; pod80 red on steep ground.
Large 1997 house (4,026 sf) -- ordinary SFR, no POLICY note.

## 7. 1S125CD03300 (R-5, 7711 SW Landau St) RIGHT
Corner + through, 14,242 sf. SW Larch St gap 60.1 (centreline 32.3), SW 77th Ave gap 50.0
(centreline 24.0 -> at most ~1 ft), SW Landau St gap 58.8 (31.1). No TSP class. Pod56 building 15.1
ft from 77th; with 1 ft strip fits after a 1 ft shift (slack 44). Court grades 4.95% (pod56) and
4.89% (pod80) sit just under the 5% cap of 413-4.8 -- a DEM reading, passes, noted as thin.

## 8. 1N223DA11500 (R-5, 20925 NW Rock Creek Blvd) WRONG -> RED (KNOWN-67, same place)
- 9,454 sf, single frontage on NW Rock Creek Blvd = TSP Collector (FClass2 4), segments 62.6 ft
  (gap 60.0 to 20940 Rock Creek Blvd) and 27.6 ft (gap 106 -- open land across). County centreline
  29.1-29.4 ft (TSP line 29.1-29.2). 302-2.14 C(1)(c) "Collector: 37 feet to centerline"
  (cdc.302.r-5.txt:100) -> strip 7.0-7.9 ft along the whole frontage.
- Pod56 green, slack 5.0, room depth 5.0 / both 5.0. Building 15.5-15.6 ft from the line (15 ft
  front). Translation search: a 5 ft strip still fits (shift 4.5 ft), 6 ft does not, 7 ft does not.
  The pod is long side to the street (56 along, 36 deep) with the court behind to the rear line; the
  lot is ~108 ft deep, so rotating cannot help. Miss ~2 ft >= 1 ft = RED.
- Escape clause ("road improvements built to ultimate County standard") cannot be tested from the
  store; a 60 ft collector ROW is below the 74 ft the 37-ft rule implies. If the county deems it
  built out, the lot is RIGHT with 5 ft slack.
- Pod80 red (fit -35). No other finding: grade 0.7%, fire 109 ft, single frontage so B(4)(a) only.

## 9. 1S123DA07500 (R-5, 7370 SW 92nd Ave) RIGHT
Corner, 11,139 sf. SW 92nd Ave (west, 60.4 ft) = TSP Arterial (FClass2 3): gap 59.5 (half 29.75),
centreline 37.6 -> strip 7.4-15.25 ft (gap method 15.25). SW Brier Ln (south, 119.6 ft) local: gap
50, centreline only 16.9 (pavement drawn off-centre) -> none by the gap. Pod56 faces 92nd, building
20.3 ft from it; with a 15.25 ft strip it needs 30.25 ft; the layout fits after a 10.5 ft shift east
along Brier (slack 40.5 ft), and still fits (11.1 ft shift) even if Brier also took an 8 ft strip.
Court 11.9 ft from Brier, drive on Brier (local side street), not on the arterial. Grade 0.9%.

## 10. 1S112CB04300 (R-5, 8260 SW Cashmur Ln) RIGHT
9,043 sf, 83 ft local frontage, gap 50, centreline 26.5 -> no strip. FIT-TIGHT 0..1 ft (fits).
Court corner sits outside the slanted rear envelope edge but inside the lot (parking, not building).
Lane on the west side to Cashmur. Grade 4.45% (< 5%). Max slope 26.8% elsewhere.

## 11. 1N129CA03500 (R-5, 15530 NW Oak Hills Dr) RIGHT (drawing flaw noted)
11,921 sf, frontage 70.8 ft on a concave curve (three 23.6 ft chords, bearings 113/110/107) on NW
Oak Hills Dr = TSP Neighborhood Route. Gap 59.4-59.7 (half ~29.8) -> strip ~0.3 ft; county
centreline 45 ft (line drawn off-centre; across parcels 59.5 ft away rule it out as the ROW centre).
- The drawn building's front wall is 14.2 ft from the chord vertex at (7603129.0, 690136.3); front
  yard is 15 ft (cdc.302.r-5.txt:357). The envelope's front edge is one straight line 13.7 ft from
  the middle vertices -- it was cut from the chord between the curve's end points, ignoring the two
  inward vertices. So the drawn placement misses the front yard by 0.8 ft.
- But room is 12.5-17 ft (slack 16.5): the pod fits after a ~1-3 ft shift back with the true lot
  line (translation search with the strips cut from all three chords: fits at a 3.2 ft shift; with a
  0.5 ft NR strip, 3.8 ft). The GREEN answer stands. Pattern worth a look on tight lots: on a
  concave (inside-of-curve) front the envelope can sit up to ~1.3 ft too close to the street.

## 12. 1S201CA07600 (R-5, 19872 SW Jay St) RIGHT
10,141 sf, 72 ft local frontage, gap 50, centreline 25.2 -> no strip. Pod56 slack 18, building 15.2
ft from the line, lane along the east side to the rear court. Grade 0.5%.

## 13. 1S118AD01624 (R-5, 16755 SW Cambridge Dr) RIGHT
Corner, 7,491 sf (>= 7,000, measured before dedication). SW Cambridge Ct (south, 74.9 ft, front):
gap 50, centreline 29.3. SW Cambridge Dr (east, 100 ft, street side): gap 50, centreline 24.4 ->
at most 0.6 ft; building 10.5 ft from it vs 8 + 0.6 -> fine as drawn. Slack 1.5. Court north of the
building, 9.7 ft from Cambridge Dr; drive on the Dr (side street). Grade 0.8%.

## 14. 1S112DD02600 (R-5, 6625 SW Hamilton St) RIGHT
Corner + through, 11,813 sf. SW Scholls Ferry Rd (east, 88.4 ft) = TSP Arterial: across is a lot on
Santa Monica Ct (84.7 ft, diagonal, not a clean measure); county centreline 36.1, TSP 34.8 -> strip
~9-10 ft. SW Fraser Ave (west, parallel, local) gap 50, centreline 36.0; SW Hamilton St (south,
local) gap 60. Pod80 (green): building 69 ft, court 22 ft from Scholls -> fits as drawn even with a
15 ft strip. Pod56 (green): building 23.1 ft from Scholls, fits after a 2.5 ft shift with a 10.5 ft
strip. side_street = true; the court is closest to Fraser/Hamilton for the drive (local), so no
arterial access question. (R10 neighbours to the NE are across the county line, not this lot.)

## 15. 1N120AD07000 (R-6, 5043 NW 146th Ter) RIGHT
8,000 sf, 80 ft local frontage. Across the lot is a T-intersection (no parcel straight across);
county centreline 28.0 ft -> no strip. FIT-TIGHT 0..1 ft (fits). Building 15.5 ft from the front
line, lane along the north side from 146th Ter to the court on the west. Grade 1.65%.

## Cross-lot patterns
- KNOWN-67 strip: due on 7 of 15 lots (Collectors 1, 6, 8; NR 4, 11; Arterials 9, 14). Only lot 8
  fails: it is the only one where the strip lands on the FRONT of a pod with under ~5 ft of depth
  slack. Lots with tight slack (5, 10, 13, 15) all sit on 50 ft local streets where no strip is due.
- NEW: TO districts' 10,000 sf buildable cap on the Type I path is not encoded; 22 of 26 TO greens
  are over 10,000 sf. Same family, NOT in my sample but worth a count: R-5 lots over 1 acre (39
  greens) and R-6 over 0.8 acre (34 greens) would put four units below 4 / 5 u/ac and fail
  302-2.14 B / 303-2.14 B, i.e. Type II -- check whether the screen gates those (buildable area,
  not lot area, is the measure).
- Concave curved fronts: the envelope is cut from the chord, up to ~1.3 ft too close (lot 11,
  similar on lot 5). Harmless here; could flip a 0-1 ft slack lot.
- Parking grade 4.95% on lot 7: 413-4.8 5% cap is met only by 0.05 pt of DEM.
