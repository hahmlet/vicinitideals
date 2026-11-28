# 219. Would a lot-by-lot parking layout builder pay off? Trial on the near misses first

[Claude] [Steph: go / no-go on the trial] [scan: YES -- toward green]

Steph asked 2026-11-27: "Should we just build our parking dynamic builder? Would that solve a lot of things?"

Measured on the fd8c bridge (435,158 bridge lots: 402,455 red / 26,372 yellow / 6,331 green):
- 212,006 reds fail ONLY on the building-plus-parking fit. By how much they miss: under 5 ft 1,527; 5-10 ft 2,662;
  10-20 ft 8,765; 20-40 ft 60,475; over 40 ft 138,577 (median lot ~7,000 sq ft -- too small at any layout).
- 601 reds fail only on parking/driveway checks; 5,245 yellows on unmeasured court turns (FOLLOWUPS 216 fixes most);
  12,167 yellows carry some parking/court flag.
- Recent false reds/yellows (stairs, corner stand-back, fire, connectors) are placement or rule issues, not the fixed
  parking templates; a builder would not fix them.

Recommendation given: no full rebuild yet. Trial: on the ~4,200 fit-only reds missing by under 10 ft (and the 601
parking-only reds), try the alternate arrangements the city rules allow (court beside vs behind, tandem where allowed,
the other stall band within Steph's "4 is enough" ruling) and count how many would pass with every check. If the
count is large, scope the builder; if small, close this. Turning stays on measured courts (216's method), never an
unmeasured pass.

## Status 2026-11-27
Steph: "No, continue on your path" -- not now; current lanes first. Parked; re-offer only when the
current lanes (213-218) are shipped.
