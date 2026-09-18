# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **The bridge from the county map is BUILT and running (7a32a5e3,
   2026-09-17); the county run and its numbers are next.**
   `flats/ingest/quadfit.py` reads quadfit's s4 + s5o on LXC 137 into
   `LotFacts` + `configure(observed=)` + `Fitter`/`fit_for` + `screen()` for
   every lot x design and writes `lots.parquet` / `meta.json` / `summary.md`
   with the comparison against quadfit's triage. Verdict is UNKNOWN /
   RULE_UNVERIFIED everywhere (all 1,942 values draft); the `if_signed`
   column is the same checks with that reason lifted. The 3,000-lot sample
   at 1 degree took 376 s on 12 workers (`/root/bridge_sample`); the full
   county (289,845 lots, 580 chunks) is ~10 h and was launched 2026-09-17
   19:40 PDT in the background at `/root/bridge_county` on 137
   (`/root/bridge_county.log`; parts land per chunk). Next: read its
   `summary.md`, write the county numbers into FLATS_PLAN (the paragraph
   after the one-row court) and HUMAN_TODO (the built-and-run entry), then
   load `flats.lots` / `flats.runs` / `flats.lot_results` in production from
   the parquet (geometry travels 137 -> 114).
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
   (assumed False today, named on every lot it leans on). The stall count
   itself (six charged vs quadfit's four-as-a-floor) is Steph's call --
   HUMAN_TODO 18.
