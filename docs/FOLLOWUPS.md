# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **The county map copy, kept current (HUMAN_TODO 20 decided 2026-09-19:
   A, in the database; the agent may promote a clean refresh, anything with
   a warning waits for Steph).** The plan with the process, cadence, change
   types, failure modes and drift audit is in the approved plan file (the
   runbook `docs/ops/flats-county-refresh.md` is phase 4). *Phase 1
   shipped 2026-09-19:* `flats.snapshots` / `flats.probes` (migration 0132;
   every lot row now belongs to a snapshot, unique `(snapshot_id, county,
   tlid)`; run 2 backfilled onto a synthetic 2026-07-28 snapshot), the
   red/amber banner + always-present footer on the Lots pages
   (`flats/ingest/status.py`, computed from rows only), the monthly
   warn-only probe (`flats/ingest/probe.py`, Celery beat 3rd 09:00 UTC,
   `scripts/flats_probe.py` by hand), `scripts/flats_snapshot.py register`,
   the loader's `--snapshot`, candidate runs reachable by `?run=` and never
   the default. *Phase 2 shipped 2026-09-19:* `flats/ingest/delta.py`
   (lineage by geometry overlap -- attr_change / reshape / split / merge /
   renumbered / added / deleted / vacated; an old lot >= 95 % inside a
   neighbour that grew is a merge), `flats.lot_changes` (migration 0133,
   loaded by `flats_load_bridge.py load-changes --from --to`), the
   `rlis_taxlot_change` registry member, `flats_snapshot.py report` (the
   summary on the snapshot row). *The real July-vs-September run* (137,
   10 s): 453,264 -> 453,782 lots, 439,980 unchanged, 14,047 rows --
   attr_change 11,395 / reshape 1,291 / split 946 / merge 356 / renumbered
   46 / added 7 / deleted 5 / vacated 1; 1,354 rows put a decision in
   doubt; Metro's list agrees (recall 97-100 %, precision 94-99 %; the
   warning is < 80 %). These are the runbook's normal ranges. *Phase 3
   shipped 2026-09-19:* the 19 Clackamas city overlays quadfit read but the
   registry lacked (West Linn x6, Wilsonville SROZ, Happy Valley NROZ +
   slope, Milwaukie x4, Oregon City NROD, Tualatin x5 -- 61 datasets now),
   `scripts/flats_stage_quadfit_raw.py` (a quadfit tree per snapshot:
   links under quadfit's names, four renames, FEMA split, DEM tiles shared
   from July, `SOURCE.json`; refuses a snapshot that is not whole;
   `QUADFIT_DATA_DIR` moves every quadfit stage), `flats/ingest/
   normalize.py` (every lot from the snapshot: jurisdiction from
   JURIS_CITY, majority-area zoning, roll values, condo, and a **gate** --
   JURISDICTION_NOT_ENCODED / JURISDICTION_OFF / OUTSIDE_UGB / NO_ZONE /
   ZONE_NOT_ENCODED; the September map: 400,032 lots, 311,202 screenable,
   5,329 in 128 zone codes the rules do not hold -- commercial, industrial,
   farm, Wilsonville PD*, Happy Valley MUR*), `flats/ingest/assign.py`
   (the bridge's rows byte for byte + one `unknown` row per design for
   every other lot with the reason, NOT_MEASURED carrying quadfit's s3
   step from the new `s3_dropped.csv`), the loader (`export` takes an
   unmeasured lot's record from the normalized table and gives every lot
   `facts.assessor` / `facts.condo` / `facts.snapshot_zone` and a real
   `condo_verdict`; a snapshot-fed run loads as `candidate`; `load` ends
   by writing `flats.snapshots.checks` from `flats/ingest/checks.py` --
   layers_incomplete, count_drift 5 % / taxlots 2 %, new_zones (codes the
   copy in use did not have; the rest carried), lots_drift 2 %,
   zone_changes 10 % of a city, rlis_agreement recall 80 % -- and `counts`
   for the next refresh to compare against). *In flight on 137 (started
   2026-09-19 07:23 UTC):* quadfit s1..s7 from the September tree
   (`/root/qf_sep.log`; s4 saw 290,032 lots vs July's 289,845), then the
   bridge (~7 h, `/root/bridge_sep`), then assign -> export -> scp to 114
   -> `load --snapshot 3` (dry run first) -> VACUUM -> `?run=<id>`. When
   it lands: HUMAN_TODO 20 "built so far" gets the numbers (the first
   candidate WILL trip new_zones -- snapshot 1 is synthetic and knew no
   codes -- so Steph reads it; that is the design). *Still owed:* **phase
   4** -- migration 0134 (re-review flags on decisions), `app/services/
   flats_refresh.py` promote / rollback / drift, `scripts/flats_promote.py`,
   page `/flats/refresh` showing the six checks, the runbook `docs/ops/
   flats-county-refresh.md`, `docs/ops/data-sources-active.md` RLIS section
   marked decommissioned. Terrain (DEM tiles) stays `deferred` until the
   slope stage exists. Two loose ends found by the September map, queued
   not fixed: Happy Valley's layer carries both `MURM2` and `MURm2` (one
   lot; the source's casing, kept as it is), and Oregon City's zoning
   layer says `County` on 14 lots inside its boundary.
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
