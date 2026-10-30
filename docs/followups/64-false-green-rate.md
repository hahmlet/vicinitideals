# 64. Measure the false-GREEN rate, so "are we converging?" has a number (offered 2026-10-09 when Steph asked whether the work ever ends).

64. [Claude] [scan: NO (a reading exercise; fixes it finds get their own items)] **Measure the
   false-GREEN rate, so "are we converging?" has a number (offered 2026-10-09 when Steph
   asked whether the work ever ends).** Draw a random sample of ~100 GREEN lots from the
   live run (stratified by county/city, not by flag), read each one deeply and blind
   (zoning words, lot shape, access, fire, slope, tract/ownership) and count how many are
   wrong and why. Repeat after each weekly. Also log per fix: greens moved as a share of
   all greens, and whether the cause was a NEW kind of problem or a known kind in a new
   place. Stopping signal to propose to Steph: a week whose fixes move < ~0.5% of greens
   and find no new kind of problem -> switch from hunting to maintenance (code-change
   watch, item 54) + onboarding new territory. Steph to decide whether to run it.
   ROUND 1 DONE 2026-10-10 (flats/false-green-sample, data/flats/false_green/2026-10-10/,
   seed fgs-2026-10-10-seed1): 102 greens from run 70, 97 RIGHT / 4 WRONG / 1 CAN'T TELL.
   ROUND 2 DONE 2026-10-14 (flats/false-green-sample-r2, data/flats/false_green/2026-10-14/,
   seed fgs-2026-10-14-seed2, work/draw.sql, work/consolidate.py): 108 greens from run 74,
   97 RIGHT / 7 WRONG / 4 CAN'T TELL; weighted 5.5% (95% range 1.7%-14.6%). BOTH ROUNDS
   POOLED (207 lots, 9 wrong): 3.9%, 1.5%-8.9% -- the number to quote; no change between
   rounds. Wrongs: road land to the centre line x5 (items 67/77), WashCo transit-district
   Type II-only path x1 (item 79), Portland Main Street overlay minimum FAR x1 (item 78).
   Can't tell: Portland Map 120-2/120-3 (item 68), Wilsonville x2 and Wood Village TC x1
   (item 80). PER-FIX LOG run 70 -> 74: hunting fixes moved 156 greens = 0.31%; gains 1,152
   from new territory. STOPPING SIGNAL NOT MET: moves < 0.5% but one new kind and two known
   kinds in five new places; item 67 alone will move ~3% of greens.
   NEXT: round 3 after the weekly that carries 67/77 (both merged) and once 78-80 are
   decided; new seed, weight the same way. Not read yet: the 59 PUB greens.
   POLICY class (counted apart, never "wrong"): FLATS ignores existing buildings by design --
   e.g. 1S2E02BB  -01100, a 6.66-acre Portland CE lot with a 75,050 sq ft commercial building,
   GREEN with the pod in a corner. Steph RULED 2026-10-14 (register
   `2026-10-14-existing-buildings-stay-green`) that occupied buildings STAY GREEN; the
   2026-10-10 question "should a lot whose pod sits on a working building's parking or yard
   stay green?" reads as answered by it -- confirm with Steph only if a case differs.
