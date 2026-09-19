# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **The county map copy: after the first candidate (HUMAN_TODO 20).** All
   four phases shipped 2026-09-19 (snapshots + banner + probe 41b64c45;
   delta dc1dbaad; every-lot normalize/assign + gate 1318db5b; promote /
   rollback / drift / `/flats/refresh` ffe407ec; runbook
   `docs/ops/flats-county-refresh.md`). The September copy is loaded as
   **run 6** (`candidate`, snapshot 3: 402,033 lots = 290,032 measured +
   112,001 unmeasured with a reason; 804,066 results; `?run=6`, default
   still run 2), drift 2 -> 6 stored (579,400 compared, 178 moved: ground
   39 / rules 0 / code 139 / unexplained 0), gate trips **new_zones only**
   -- Steph reads; nobody promotes. When Steph promotes: `flats_promote.py
   prune --dry-run` then real (keeps snapshot 1 whole), confirm the Lots
   default is run 6 and the footer says 2026-09-18, re-run the probe.
   **Drift attribution is too coarse** (found on the first real report):
   `code` is the fall-through whenever the repo HEAD differs, which it does
   on every refresh, so `unexplained` can only fire when nothing was
   committed -- and of the 139 filed under `code`, the screen's code did
   not change; the facts that differ are `corner_lot` 25, `fronts_cul_de_sac`
   18, `abuts_alley`/`alley_at_*` 13, `in_floodplain` 8, `in_sewer_district`
   8, `split_zone` 8 -- the streets, alley, FEMA, sewer and zoning layers
   re-read around an unchanged lot. Fix in `app/services/flats_refresh.py
   drift()`: a `surroundings` cause when any measured fact in
   `facts.quadfit` / `facts.observed` differs between the two rows (before
   rules/code), and `code` only when the screen's own files changed (hash
   of `flats/score`, `flats/geom`, `flats/ingest/quadfit.py`, `Lot
   Analysis/quadfit` between the two code versions -- `git diff --stat`),
   else `unexplained`. Add the new words to `GATE_WORDS`/the page; test in
   `tests/services/test_flats_refresh.py`. Loose ends the September map
   found, queued not fixed: Happy Valley's layer carries both `MURM2` and
   `MURm2` (one lot; the source's casing, kept), Oregon City's zoning says
   `County` on 14 lots inside its boundary; 2,001 Multnomah unit lots
   (`-8xxxx` / `-9xxxx` / `-6xxxx` TLIDs, ~1,000-1,800 sq ft, all red) that
   quadfit's s1 measured but `flats/normalize/condo.py` excluded as
   condominium records (`condo_excluded` 47,114) -- the two condo readings
   disagree; the bundle keeps quadfit's answer for them without roll or
   condo facts; Terrain (DEM tiles) stays
   `deferred` until the slope stage exists; no writer for lot decisions in
   `app/` yet (they are inserted by hand or by a future review page).
2. **The court search takes the biggest rectangle, not the deepest one that
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
3. **Four places the screen and the county map disagree, found by the
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
4. **Draw what the screen fitted on the lot page.** `/flats/lots/{county}/
   {tlid}` (`app/api/routers/ui_flats.py`, the "lots" section) draws the
   outline only. Two things are missing before the building can be
   drawn on it: quadfit's carved envelope (s5o `wkb`) is not carried by
   `scripts/flats_load_bridge.py` -- a geometry column on `flats.lots`
   (migration) and one more `export` column; and the screen's `fit_for`
   reports depth / across / angle / orientation but no *position*, so a
   placement (the rectangle's origin on the lot, in 2913 feet) has to be
   returned by the fit and stored in `checks.fit` before anything can be
   drawn. Offered 2026-09-18 with the pages.
