# 104. Gresham Table 4.0430 notes, read note by note (Steph 2026-10-20).

104. [Claude] [2026-11-08: (f) done, (g) folded into 142(a); close after the rescreen-1110 read] [LIVE run 81 2026-10-21 (main 0060aad3); Gresham green 1,834 -> 2,039] [scan: (a) LIVE run 80 2026-10-21] **Gresham Table 4.0430
   notes, read note by note (Steph 2026-10-20).** DONE: all 18 notes read, plain-English page
   https://claude.ai/artifact/BQaymC5Un4njJZaTH9LJDf; note 14 encoded as civic_corridor variants.
   (a) Steph 2026-10-20 "Yes, map it". Gresham has NO map (zoning layer GME/Planning/MapServer/4 is plain
   CMF; Ord. 1830 2022 names the streets only). 659 CMF lots (505 red, 154 yellow); seven CMF blocks
   touch Glisan/162nd. LIVE run 80 (main 67611b26): true = a street lot line on NE Glisan or NE
   162nd north of Burnside (~59); false = CMF outside the seven blocks (~569); unknown = the ~31 behind
   the frontage in touching blocks (NE 183rd, deep lots, the NE Halsey strip). STEPH 2026-10-21 "only lots actually touching the street count as along. If it touches, it's
   along" -> behind-frontage = false, a lot touching Glisan/162nd (Halsey strip corner) = true. BUILDING. Was asked:
   do lots behind the frontage count; does the Halsey strip that touches 162nd only at its corner
   count. Vs live: 5 lots unknown->green (off the corridor, every one >1,247 ft from
   Glisan/162nd), 10 answers unknown->yellow (on it: the corridor yards do not fit); the unknowns wait on
   the two questions. (b) BUILDING (Steph 2026-10-21 "map Rockwood") note 12's target 7.0512.B.6 requires 3 storeys at the
   181st/Burnside, 181st/Stark, Burnside/Stark gateways -- yellow, should be red once Rockwood is
   mapped; (c) note 6 townhouse lot width not held on its own (low risk); (d) HOLD (Steph 2026-10-21: "could be a big change") row M buffering points
   to Section 9.0100, not stored; (e) BUILDING (Steph 2026-10-21) row C width/depth ratio for a single-lot quadplex in SC, SC-RJ,
   CMU not encoded.
   BUILT 2026-10-21 (flats/gresham-4430 c0c53f7f): along = within 75 ft of the centreline (frontage lots
   34-54 ft, nearest behind-frontage 125 ft); ratio row C on SC, SC-RJ, CMU, CMF (townhouse split exempt,
   note 6); NEW FIX Table 4.0420 note 2 -- CMF land division only on the corridor. Bound: 40 ratio reds
   (9 green->red), 16 note-2 reds (4 green), 3 corridor greens. (b) Rockwood does NOT reach the pod:
   7.0502(B) exempts quadplexes, 7.0512 "All Development" excludes townhouses -- no gateway reds.
   STEPH 2026-10-21 ANSWERED both: (i) "assume that the lots from the gis and other data sources we
   have are legal. Every lot we try to purchase will go thru a legal review" -> yes; (ii) yes. Were: (i) 4.0431.C lets an EXISTING lot of record that misses lot
   size, frontage or the ratio still be built on (and skips min density) -- treat every taxlot as a lot
   of record on the single-lot path? (ii) lift note 13's Rockwood setback hold, since 7.0502(B)/7.0512
   take the pod out? BUILDING both, then bound, merge, splice.
   ALSO (possible false GREEN, found by 109): 7.0420(J)(1)(a) 50% street-oriented frontage reaches plexes
   in the Corridor Design District, which 3.0100#L834 defines to include MDR-12, MDR-24, OFR -- encoded
   on the corridor zones, missing on these three (live: 54 greens). Added to flats/gresham-4430.
   BOUND (ead841e2, 25,660 Gresham lots): 289 move, 0 false GREEN -- +149 green lots of record (CMF CMU
   SC SC-RJ), +65 Rockwood setbacks, +81 both; -20 green on the 50% frontage (MDR-12 11, MDR-24 9).
   (f) DONE a4a4dcc1 (2026-10-22, FOLLOWUPS 109 chunk 3): townhouse form exempt from the 50% share and the
   long-axis rule outside Rockwood on MDR-12, MDR-24, OFR, DRL-1, DRL-2, CMF, CMU, RTC (7.0420(J)(1) names
   plexes; 7.0431 asks no share); Rockwood keeps both (7.0512(A)(2) S2). SC and SC-RJ carry no townhouse
   exemption, and need none: checked 2026-11-08 against the city zoning layer (GME/Planning/MapServer/4), all
   154.2 ac of SC, 28.7 ac of SC-RJ and 194.7 ac of RTC lie inside the Rockwood Design District outline, and
   4.0433(B)(1) sends SC/SC-RJ townhouse orientation to 7.0500 -- no lot moves.
   (g) FOLDED INTO FOLLOWUPS 142(a) (fire-hose placement retry, merged into rescreen-1110 1b08a69e, rounds 1-6).
   1S3E14AA-08900 (live run 122: red, hose 167.5 ft on pod56x36) is a spot-check for the rescreen-1110 read.
   Item closes when that read confirms (g).
