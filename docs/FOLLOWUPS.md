# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **The county re-run under the four-stall screen, then the load into
   production.** The bridge (`flats/ingest/quadfit.py`, 7a32a5e3) ran the
   whole map under the six-stall screen (`/root/bridge_county` on 137,
   289,845 lots, 24,949 s; numbers in FLATS_PLAN §2 "The county run, and
   the stall count it settled" and HUMAN_TODO's built-and-run entry). Steph
   2026-09-18: *"same as the county map. 4 is enough to sell"* -- built as
   `StallBands` / `pod56x36@2` / `pod80x25@2`, the floor charged, the seat
   count + band beside the colour, and `parking_cap` for a cap below the
   floor (9b045c40, deployed). Sample re-run both ways (`/root/bridge_sample`
   vs `/root/bridge_sample2`, same 3,000 lots, `/root/both_ways.py`): green
   342 -> 420, **0 greens lost**, 78 yellow -> green all on `fit_ft` (end-on
   at 48 / 37 ft where 54 was refused; seat 4 x 28, 5 x 50, all band
   minimum; quadfit green 23 / red 46 / review 9), 6 Portland EX unknown ->
   yellow on `parking_cap`, 3 yellow -> unknown (fit passes, a fact
   unobserved). quadfit-green / FLATS-yellow 63 -> 38 (30 alley, 5 row
   along the lot, 3 other). Band vs quadfit's tier on the 123 both-green:
   96 agree, 27 FLATS seats fewer (court shape). **The county re-run is
   RUNNING**: launched 10:51 UTC 2026-09-18 to `/root/bridge_county2`
   (`/root/bridge_county2.log`, 16 processes, ~7 h). Next: `python
   /root/both_ways.py /root/bridge_county /root/bridge_county2` on 137,
   write the numbers into FLATS_PLAN (§2 "The county run, and the stall
   count it settled") + HUMAN_TODO (item 18 and the built-and-run entry),
   then load `flats.lots` / `flats.runs` / `flats.lot_results` in
   production from the parquet (geometry travels 137 -> 114).
2. **An authoritative offline source for lots (Steph 2026-09-17: "we will
   need an authoritative offline source").** FLATS's own durable, versioned
   copy of the taxlots, streets and zoning it screens -- option (B) refined:
   `flats/config/pipeline.yaml` already names the county GIS sources and
   `flats/ingest/sources.py` validates them; nothing downloads, normalizes
   or assigns. Replaces the quadfit-parquet bridge above when built. Several
   sessions; needs a decision on where the copy lives (disk on 137 vs
   `flats.lots` in Postgres) before starting.
3. **The court search takes the biggest rectangle, not the deepest one that
   holds a row.** `s6s_siteplan.py` `_largest_rect(ok[court_r0:, :])` returns
   the maximum-AREA all-clear rectangle behind the building and then asks
   whether it is deep enough for a row of stalls (stall + two-way aisle). A
   wide, shallow rectangle can win that contest on an irregular lot while a
   narrower rectangle one cell over is deep enough for a row -- a lot refused
   `court_too_shallow` that has a court. Conservative direction (a lost
   GREEN, never a false one), so it has waited; the 2026-09-17 aisle run
   turned 113 plans into `court_too_shallow` / `no_side_lane` and some may be
   of this kind. Measure first: re-search the failed lots for the deepest
   rectangle at least `cap x stall_w` wide and count how many would hold a
   row, before changing the search. Offered 2026-09-17.
4. **Four places the screen and the county map disagree, found by the
   bridge's sample run (2026-09-17) and left alone on purpose.** Named so
   the comparison stays readable, each its own change: (a) the court's
   shape -- `court_across` draws one row of stalls across the lot behind
   the building (six at 9 ft = 54 ft), quadfit's s6s lays the stalls in the
   largest rectangle behind the building whichever way round fits, so a
   63-ft-wide Portland R5 lot seats eight along its depth where the 54-ft
   row does not fit across it -- 18 of the 63 quadfit greens the screen
   calls yellow (all on `fit_ft`) seat six-plus that way; (b) the alley is
   the aisle (Steph 2026-09-13) on the county map and nowhere in
   `flats/score/` -- 33 of the 63 park on the alley in quadfit; (c)
   quadfit's policy gates are not site facts: `z_overlay_constrained_site`
   (PCC 33.418), the overlay kill layers, `existing_*` current use and the
   sewer gate (`no_public_sewer` is a hard gate there; here `public_sewer`
   is observed but no Clackamas standard turns on it) -- 84 of the 178
   screen-GREEN / quadfit-red lots in the sample; (d) the sweep -- the
   screen tries 180 angles, s6 fits at the front bearings only, and 94 of
   those 178 are quadfit `siteplan_no_layout` lots the sweep found a fit on.
   Also owed: FLATS's own envelope from the corpus setbacks
   (`geom/envelope.buildable`) instead of quadfit's carved one, and
   `steep_slope` from s5o's DEM percentile / Gresham's hillside overlay
   (assumed False today, named on every lot it leans on). County-scale
   sizes from the 2026-09-18 run, on the 7,372 quadfit-green / FLATS-yellow
   lots: (b) 3,653 on the alley, (a) 2,020 six-plus with the row along the
   lot; (c) + (d) are 17,837 GREEN-where-red (siteplan_no_layout 10,068,
   z_overlay 6,164, no_public_sewer 764, existing_* 749). The stall count
   was decided 2026-09-18 (HUMAN_TODO 18) and is out of this item.
