# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **Load the county run into production.** The bridge
   (`flats/ingest/quadfit.py`) has run the whole map twice on 137: six-stall
   `/root/bridge_county` (before) and four-stall `/root/bridge_county2`
   (after, 2026-09-18, 25,182 s, `lots.parquet` 579,690 rows = 289,845 lots
   x `pod56x36@2` / `pod80x25@2`, plus `meta.json`, `summary.md`; the
   both-ways ruling is at `/root/both_ways_county.txt` and
   `/root/county_dig2.txt`, numbers in FLATS_PLAN §2 "The county run, and
   the stall count it settled" and HUMAN_TODO's built-and-run entry: green
   34,445 -> 42,115, none lost). Next: a one-shot script that writes
   `flats.runs` (one row: code/rules version, design keys, params from
   `meta.json`), `flats.lots` (TLID, county, jurisdiction, zone, area, geom
   + centroid from s4 -- geometry travels 137 -> 114, so the parquet or a
   GeoPackage moves first) and `flats.lot_results` (lot x design: tier =
   the screen's verdict, UNKNOWN today; `checks` JSONB carries `if_signed`,
   reasons, head, fit, stalls charged/seated/band, so the signed colour is
   queryable without a re-run). Never a direct data edit; the script is
   idempotent on (tlid, design_key, run_id). Decide before writing: does
   the app show the verdict or the if-signed colour first (the verdict,
   with the colour beside it, per the 2026-09-17 data-source ruling).
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
   sizes from the four-stall county run (2026-09-18, `/root/bridge_county2`),
   on the 4,024 quadfit-green / FLATS-yellow lots (all `fit_ft`): (b) 3,507
   on the alley (2,976 seating four there), (a) 517 off their own lane, 268
   of them seating eight with the row along the lot; (c) + (d) are 21,660
   GREEN-where-red. Also under (a), the other direction: on the 13,196 lots
   both call green FLATS seats FEWER than quadfit on 3,881 (one row across
   where s6s found two) and MORE on 160 (`target` where quadfit's tier is
   `minimum` 100, `preferred` where `target` 58) -- find what the screen's
   row counts that s6s's rectangle does not before changing either. The
   stall count was decided 2026-09-18 (HUMAN_TODO 18) and is out of this
   item.
