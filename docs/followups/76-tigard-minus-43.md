# 76. Tigard pod80x25 red at exactly -43 ft, and split-zoned lots.

76. [Claude] [Steph: (c) assessor lookup] [(a)(b) READ at run 78 2026-10-20, Estacada 34E17 02000 as expected; only (c) open; MERGED to main (5e29be82, 72f96818)] **Tigard pod80x25 red at exactly -43 ft, and split-zoned lots.**
   (a) -43 is NOT a sentinel: it is the floor fit_ft reports when no window as wide as building +
   lane (80 + 20 = 100 ft) exists at any street bearing: best_depth 0 minus (25 ft building + 18 ft
   court) = -43 (pod56x36 floors at -36). Checked against exact geometry: all true no-fits except
   raster near-misses (3 of 785 fit at width-0.5 ft). Steph ruled yes (register
   `2026-10-14-split-zone-near-miss-real-shortfall`): the fit now reports the real width shortfall
   (`Fit.width_short_ft`, flats/fit/rectangle.py) so the 1-ft rule applies (>= 1 ft red, < 1 ft
   yellow FIT-TIGHT). Bound: 50 design rows red -> yellow (Tigard 47, Gresham 2 DRL-2, Happy Valley
   1 R7). SIDE EFFECT, colour-neutral, on RED lots: the slack shown is now the real shortfall
   (-37/-48/-56/-80 ft ...) instead of the -43/-54 floor, and ~1,100 red rows gain or lose an
   informational flag (Milwaukie MEASURE-OUTDOOR-SHAPE +542, Beaverton net-area swaps). If the
   lot page should keep the old numbers for red lots, that is a separate decision (not asked).
   (b) Split zones. Steph's ruling (register `2026-10-14-split-zones`): "first check if the city
   has a rule on this. If no, I would say yellow." Built: flats/config/split_zone.yaml (cite +
   quote per city, tested against the stored text; what was searched in the 17 silent layers is
   written there so nobody searches again) and flats/geom/split_zone.py. Rule found -> applied
   (Beaverton BDC 10.35.2.C and Milwaukie MMC 19.107.5 <= 20 ft inclusive; Cornelius CMC
   18.05(D)(3), Hillsboro CDC 12.01(C)(1), Canby CMC 16.08.030 "less than" 20 ft; Sandy SDC
   17.04.80.B.6 majority; Portland and Multnomah PCC 33.110 each district for its own part). No
   rule -> a green whose building, lane or court stands on another district's ground goes YELLOW,
   ZONE-SPLIT (severity 4); an undrawn plan or unresolved district is the worst case. Bound: 134
   lots green -> yellow (Portland 94, Washington-uninc 20, Clackamas-uninc 12, ...), nothing else.
   CHECK after the weekly: these two bounds' moves. Estacada 34E17 02000: pod80x25@2 yellow,
   pod56x36@2 stays green.
   (c) OPEN, human lookup: Estacada 34E20AC00200 / 00201 (1015 NW Wade St) -- owner NOT in our
   data (RLIS roll carries no owner name); roll says COM class 201, taxed (assessed > 0), so the
   public-land rule correctly did not fire. Look up tax lot 34E20AC00201 at the Clackamas
   assessor: if the owner is the city or a district, it is a miss the roll cannot see.
