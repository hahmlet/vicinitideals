# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **The screen still has no production caller -- DECISION PENDING
   (asked 2026-09-17).** `flats/score/screen.py` (`screen()`, `fit_for`) is
   exercised only by tests. The real gap is data, not code: `flats.lots`,
   `flats.runs`, `flats.lot_results` are all EMPTY in production (checked
   2026-09-17); the acquire/normalize/assign ingest is the one unchecked
   Phase 0 box (`flats/config/pipeline.yaml` lists the sources, nothing
   downloads them). Three shapes offered: (A) a bridge stage that reads
   quadfit's per-lot measurements on LXC 137 (s4 width/depth/alley/cul-de-
   sac, s5o envelope, s6 fits) into `LotFacts` + `Fit` + `configure()`, runs
   the screen on all 289,845 lots x catalog, writes `flats.lot_results`, and
   compares against quadfit's triage -- the Phase 0 exit test, fastest, leans
   on quadfit's measurements; (B) FLATS's own ingest from the county GIS
   sources into `flats.lots`, its own geometry, then the screen and the web
   views (Phase 3) -- self-standing, several sessions; (C) a one-lot lookup
   page (address/TLID -> fetch the parcel -> screen -> verdict with reasons)
   -- small and visible, no county numbers. Recommended A. Offered
   2026-09-17.
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
