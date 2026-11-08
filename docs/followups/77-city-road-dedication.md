# 77. Road land to the centre line in the cities, not just unincorporated Washington County (found 2026-10-14 by item 64 round 2: 4 of the 7 wrong lots).

77. [Claude] [READ at run 78 2026-10-20: the four CHECK lots red, moves at the bound; OPEN list below] [MERGED to main (7cbc3346 + d3b6db52, with item 67), rides the weekly ~2026-10-19] **Road land to the
   centre line in the cities, not just unincorporated Washington County (found 2026-10-14 by
   item 64 round 2: 4 of the 7 wrong lots).** Steph RULED 2026-10-14 "YES" (register
   `2026-10-14-road-dedication`). Built: Sherwood 16.106.020 A + 16.106.040 D, 26/32/32/37/61 by
   its TSP class map (street_class_sherwood; a street the consultant map lacks = 61); King City
   16.80.060 A by named streets, 99W borrowing Sherwood's 61, county pockets on the county rule;
   Oregon City 16.12.011.B, half the widest Table 16.12.016 right-of-way 31/44/59/63 by
   street_class_oregon_city (RULED 2026-10-14 widest row per class; superseded by item 82: the
   zones on both sides stand in for the designation, the widest row kept only where that cannot
   be read); Milwaukie its 29 named rows of Table 19.501.2.A. Beaverton a refusal note
   (dedication at the decision-maker's call, no width stated).
   CHECK after the weekly: lots 2S132CD12600, 2S132AC01500, 2S116AA14200, 31E01DA00229 read red;
   expected moves are in item 67's table (Oregon City 713 / 56 / 228 / 19; Sherwood 20/0/30/2;
   Milwaukie 17/18/57/6; King City 3 yellow->red).
   TRAP: scripts/flats_weekly_chain.py preflight REFUSES a snapshot without
   street_class_washington/sherwood/oregon_city/milwaukie or rlis_streets (dedication_keys());
   runbook docs/ops/flats-county-refresh.md.
   OPEN: Tigard NOT ENCODED (18.210.030.A.1 setbacks from the future street edge; TSP widths not
   held -- a remaining false-GREEN gap, item 81); segment qualifiers in the tables applied to the
   whole street; lot area not reduced by the strip (only the envelope); an unmeasured public line
   gives up the whole 40-63 ft.
- 2026-11-08 BUILT 19ee2d97 (flats/tigard-road-land): Tigard was already encoded (item 81); lot area now net of the strip for min lot size + coverage (WashCo + Milwaukie keep gross per their text); rides flats/rescreen-1110; toward red only. [Steph] OPEN: Oregon City -- if the road hand-over shrinks an existing lot below the zone minimum, does the lot still count (17.58.020)? Built as NO (conservative).
- Steph 2026-11-08: Oregon City question answered NO (rulings.yaml 2026-11-08-oregon-city-dedication-below-minimum, c9cc73a4) -- matches the build.
- 2026-11-08 BUILT on flats/road-land-leftovers (off rescreen-1110 0f2620b3): segment qualifiers now read. A row printed for one stretch (Milwaukie Table 19.501.2.A's 18 bracketed rows; King City 16.80.060 A.2 c/e/f, now bracketed in the YAML) is lifted only where the bridge reads the lot line OFF the stretch: each end street found crossing the named street once within 15,000 ft, both on one unbroken run, and every sample point more than 60 ft past an end (side forms 'south of X' also checked by compass). Anything unread keeps the row (conservative). Off a Milwaukie stretch = no added yard; off a King City stretch = 25 ft. Toward green only, small. STILL OPEN (left conservative, cannot be measured from the PC): an unmeasured public line (no centreline within 60 ft in Metro or OSM) still gives up the whole 40-63 ft -- the street may simply be missing from both files.
