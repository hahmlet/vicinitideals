# Follow-ups offered but not yet done

Agent-maintained queue. Written when options are offered, pruned when they are
done or declined. Newest at the bottom; "do the next thing" means item 1.
Human-action items live in [HUMAN_TODO.md](HUMAN_TODO.md), not here.

1. **The screen's production caller is a bridge from the county map --
   DECIDED 2026-09-17, IN PROGRESS.** Steph: "bridge from the county map for
   now, but we will need an authoritative offline source." So: (A) a bridge
   stage that reads quadfit's per-lot measurements on LXC 137 (s4 width /
   depth / edges / alley / cul-de-sac, s5o carved envelope + slope + sewer +
   FEMA, `lots_results.csv` triage) into `LotFacts` + `configure(observed=)`
   + `Fitter`/`fit_for` + `screen()` for every lot x catalog design, writes
   per-lot FLATS verdicts to a parquet, and compares against quadfit's
   triage -- the Phase 0 exit test ("pipeline reproduces quadfit's numbers,
   everything in REVIEW pending verification"). Every corpus value is still
   `draft` (no `flats/config/verifications.jsonl` exists), so the honest
   verdict is UNKNOWN / RULE_UNVERIFIED on every lot; the bridge also
   reports the colour the same checks would give once signed, named as such.
   Later step, not started: load `flats.lots` / `flats.runs` /
   `flats.lot_results` in production from that parquet (geometry has to
   travel 137 -> 114).
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
