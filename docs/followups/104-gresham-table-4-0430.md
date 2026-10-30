# 104. Gresham Table 4.0430 notes, read note by note (Steph 2026-10-20).

104. [Claude] [left: (f), (g)] [LIVE run 81 2026-10-21 (main 0060aad3); Gresham green 1,834 -> 2,039] [scan: (a) LIVE run 80 2026-10-21] **Gresham Table 4.0430
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
   LEFT: (f) the 50% frontage is applied to the TOWNHOUSE form too (as on the eight zones that already
   carry it) -- J.1 names plexes only; read 7.0431 before exempting townhouses (possible false REDs).
   (g) 1S3E14AA-08900 + two big yellows fail the 150 ft fire hose at 167 ft -- placement on very
   large lots looks poor (too strict, not a false GREEN).
