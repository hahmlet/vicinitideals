# Refreshing the county map copy (FLATS)

Last updated: 2026-09-19 (HUMAN_TODO 20, decided A)

## 1. What this is

The FLATS screen reads its own dated copy of the county map — every taxlot in
Multnomah and Clackamas, the zoning layers, the overlays, sewer, streets — and
that copy lives in the app's database as `flats.lots` under a `flats.snapshots`
row. **Nothing updates it by itself.** A refresh is taken by hand, lands beside
the copy in use as a *candidate*, and is shown only after someone says
**promote**. Until then the Lots pages show the copy in use exactly as before,
and the candidate is reachable by `?run=<id>` for comparison.

The one automated piece is a monthly check that *reads* the county's services
and compares them with what the copy in use was taken from. It can only warn.
Every warning is computed from database rows, never from a live request, so a
dead service or a dead analysis box cannot silence it: red on the Lots pages
means "you should know", and the grey footer line that names the copy is always
there so the *absence* of a warning is visible too.

The page for all of this is **County copy** (`/flats/refresh`).

## 2. When

| Trigger | What |
|---|---|
| Each RLIS quarterly release, about two weeks after it lands | Full refresh. Metro's release is named in the footer (`2026_08` today); the next are expected Nov 2026, Feb, May, Aug. Two weeks lets Metro's own corrections land first. |
| The banner turns red or amber | Read §7; a refresh is usually the fix. |
| A rules change that needs re-screening anyway | Refresh on that rules commit, so data and rules move together and the drift report can tell them apart. |
| Steph asks | — |
| 3rd of every month, 09:00 (Celery beat) | The probe only. It writes one `flats.probes` row; it downloads nothing and changes nothing. |

A copy older than 120 days turns the banner red on its own.

## 3. Who

The agent runs every step below. Steph reads one page (§5) and says promote —
or the agent does, on the standing word:

> **"Me, when clean; you, when warned."** (Steph, 2026-09-19)

A clean gate (every row on the County copy page quiet) may be promoted by the
agent, recorded as `promoted_by = "agent, standing word 2026-09-19"`. Anything
with a warning waits for Steph, who promotes it from the page with a written
reason that the row keeps, or asks for the cause to be fixed first. Registry
fixes (a moved service, a renamed field) are the agent's job; the *meaning* of
a change the agent cannot tell from the data goes to `docs/HUMAN_TODO.md`.

## 4. The steps

Machines: **137** is the analysis box (LXC, `/root/code/vicinitideals`, the
`.venv`; reached by the Proxmox MCP `ssh_exec` only); **114** runs the app
(`/root/stacks/vicinitideals`, the `api` container). Files hop 137 → 114 by
`scp` (137 holds a key for 114). Long jobs on 137 run under
`nohup setsid bash /root/x.sh > /root/x.log 2>&1 < /dev/null &` and are read
back from their log; `PYTHONIOENCODING=utf-8` on every FLATS command there.
Never `git stash -u` on 137: `data/` is untracked and a stash drop discards it.

Durations are from the first real run (2026-09-18/19, 453,782 taxlots).

| # | Step | Where | Command | Takes | Done when |
|---|---|---|---|---|---|
| 1 | Pull the code | 137 | `git pull` (the refresh runs on the rules commit that is live) | 1 min | `git log -1` matches production |
| 2 | Acquire | 137 | `PYTHONIOENCODING=utf-8 .venv/bin/python -m flats.ingest.acquire` (today's date; `--keys …` to re-fetch some) | ~25 min (RLIS ZIP) + ~10 min (ArcGIS) | `data/flats/sources/<date>/manifest.json`; every dataset `acquired`/`present`/`deferred`/`retired`, none `refused`/`failed`, no `unfetched_ids` |
| 3 | Read the manifest | 137 | `.venv/bin/python -m flats.ingest.acquire --show <date>` | — | Any `refused` / `failed` → fix `flats/config/pipeline.yaml` (§8-A), re-run step 2 for those keys |
| 4 | Delta | 137 | `python -m flats.ingest.delta --prev data/flats/sources/<prev>/rlis_taxlots.geojson --new data/flats/sources/<date>/rlis_taxlots.geojson --change-log data/flats/sources/<date>/rlis_taxlot_change.geojson --out data/flats/deltas/<date>` | ~10 s classify after ~5 min load | `changes.csv.gz`, `summary.json`, `report.md`; numbers in the ranges of §5 |
| 5 | Stage quadfit's raw files from the snapshot | 137 | `python scripts/flats_stage_quadfit_raw.py --snapshot <date>` | 1 min | `data/quadfit_<date>/raw/` with `SOURCE.json` |
| 6 | Measure (quadfit s1–s7) | 137 | `QUADFIT_DATA_DIR=data/quadfit_<date> python "Lot Analysis/quadfit/run_all.py" --force` | ~50 min | `EXIT 0`; `data/quadfit_<date>/summary.md` |
| 7 | Normalize every lot | 137 | `python -m flats.ingest.normalize --snapshot <date>` | ~5 min | `data/flats/normalized/<date>/` with `new_zones.json` |
| 8 | Screen (the bridge) | 137 | `python -m flats.ingest.quadfit --s4 data/quadfit_<date>/s4_lots.parquet --s5o data/quadfit_<date>/s5o_lots.parquet --results data/quadfit_<date>/lots_results.csv --out /root/bridge_<date> --processes 12 --chunk-size 250` | **~7 h** (290k measured lots) | `lots.parquet` + `meta.json` in the run dir |
| 9 | Assign (measured + unmeasured → one run) | 137 | `python -m flats.ingest.assign --normalized data/flats/normalized/<date> --bridge /root/bridge_<date> --quadfit-dir data/quadfit_<date> --out /root/assign_<date>` | ~5 min | `summary.md` with the funnel; "measured by quadfit but not land" (condominium units quadfit's s1 keeps -- 2,001 in September) is normal, "measured but not in the snapshot's lot table (kept)" should be 0 -- a number there is a lot normalize lost for no named reason |
| 10 | Export the bundle | 137 | `python scripts/flats_load_bridge.py export --run-dir /root/assign_<date> --out /root/bundle_<date>` | ~5 min | `lots.csv.gz`, `results.csv.gz`, `run.json` (`status: candidate`) |
| 11 | Copy to 114 | 137 | `scp -r /root/bundle_<date> root@<vm114>:/root/stacks/vicinitideals/data/flats/bridge/<date>`; also `data/flats/sources/<date>/manifest.json` → `/root/stacks/vicinitideals/data/flats/sources/<date>/` and `data/flats/deltas/<date>/` → `…/data/flats/deltas/<date>/` | 2 min | files present under `/app/data/flats/…` in the container |
| 12 | Register the copy | 114 | `docker compose run --rm api python scripts/flats_snapshot.py register --manifest /app/data/flats/sources/<date>/manifest.json --host 137 --status candidate` | 1 s | `flats_snapshot.py list` shows it `candidate`; note its id `N` |
| 13 | Load the delta | 114 | `docker compose run --rm api python scripts/flats_load_bridge.py load-changes --changes /app/data/flats/deltas/<date>/changes.csv.gz --from <prev id> --to N` then `flats_snapshot.py report --snapshot N --section delta --summary /app/data/flats/deltas/<date>/summary.json` | 1 min | `report.delta` on the row |
| 14 | Load the candidate | 114 | `docker compose run --rm api python scripts/flats_load_bridge.py load --bundle /app/data/flats/bridge/<date> --snapshot N --dry-run`, then without `--dry-run` | ~10 min each | a new `flats.runs` row `candidate`; `checks` written on the snapshot |
| 15 | Vacuum | 114 | `psql … -c "VACUUM (FULL, ANALYZE) flats.lots"` then `psql … -c "VACUUM (FULL, ANALYZE) flats.lot_results"` -- one statement per call: psql runs a multi-statement `-c` as one transaction and VACUUM refuses to run inside one | ~5 min | space back (each copy ≈ 1.2 GB) |
| 16 | Drift | 114 | `docker compose run --rm api python scripts/flats_promote.py drift --from-run <run in use> --to-run <candidate run> --out /app/data/flats/reports/<date>/drift.md` | 1 min | `report.drift` on the row; the County copy page shows it |
| 17 | Read the gate | 114 / browser | `flats_promote.py status`, or `/flats/refresh` | — | every row `ok` → agent promotes; any `!!` → Steph reads §5 |
| 18 | Promote | 114 or browser | `flats_promote.py promote --snapshot N --by "agent, standing word 2026-09-19"` (clean) / the **Promote** button, or `--by Steph --override "…"` (warned) | 1 s | the Lots pages default to the new run; the previous copy is `retired` and still reachable by `?run=` |
| 19 | Prune, next quarter | 114 | `flats_promote.py prune --dry-run`, then real, then step 15 again | ~5 min | the database holds the copy in use, the one before it, and any candidates |

Steps 5–10 chain on 137 as one nohup script (`/root/chain_<date>.sh` ending
in `CHAIN DONE`) so the seven-hour bridge is not babysat.

## 5. What Steph reads

The candidate's card on `/flats/refresh`. Four questions, top to bottom:

1. **Did every layer come down whole?** — the first gate row. The 2026-09-18
   copy: 62 datasets, 35 downloaded and 25 unchanged from the copy before,
   896,398 features; `dem_3dep` deferred and `rlis_ugb` retired on purpose.
2. **Did the ground move the way a quarter moves it?** — "What moved on the
   ground". July → September 2026: 453,264 lots before, 453,782 after;
   439,980 unchanged; 14,047 changed — attribute-only 11,395, reshaped 1,291,
   split 946, merged 356, renumbered 46, added 7, deleted 5, vacated 1;
   1,354 of those put an earlier decision in doubt. Metro's own change list
   agreed (lowest recall 0.969). Anything an order of magnitude off — a
   county with thousands added, a city with a fifth of its lots rezoned — is
   the source changing shape, not the ground.
3. **Any zone code the rules do not hold?** — "Zone codes the rules do not
   hold", per layer with lot counts. Those lots screen `unknown` with reason
   `ZONE_NOT_ENCODED`, never green or red; encoding the code is a FOLLOWUPS
   item. The first candidate trips this row by design: July's copy never
   counted them.
4. **Did any verdict move for no reason?** — "Verdicts that moved". Every
   move is put to one cause, tried in this order: the ground (a lot-change
   row or a zone change), the surroundings (a measured fact that differs
   between the two readings beyond float noise -- the streets it fronts, an
   alley, a flood or sewer line, a zoning line; the layers the taxlot delta
   never sees, listed under "What moved around them"), a re-measurement (a
   fact differs only within tolerance -- 0.05 or 2 % -- yet the answer sat
   on a line and flipped: an unstable verdict, not a wrong one), a rules
   change, or a code change; **unexplained** must be 0. Each unexplained lot is linked so
   it can be opened on both runs. Normal range from the first real report
   (July -> September, run 2 -> run 10, 575,478 answers): 178 moves --
   ground 39, surroundings 104, re-measured 35 -- none unexplained.

Then: promote, or say what to fix.

## 6. What promote means, and how to undo it

Promote flips three rows in one transaction: the candidate run → `complete`
(the Lots pages' default is the newest complete run), the copy in use →
`retired`, the candidate copy → `current` with `promoted_at` / `promoted_by`
and, if it went over a warning, the reason in `notes`. Then every active
review decision whose lot the new copy shows split, merged, renumbered,
deleted, vacated, or rezoned is marked *look again*
(`review_decisions.needs_rereview_snapshot_id` + reason); the decision still
stands, and the lot page says why it is in doubt.

Undo: **Roll back to the previous copy** on the promoted card, with a reason,
or `flats_promote.py rollback --by Steph --reason "…"`. The previous copy is
`current` again, the promoted one is a `candidate` again with its run, and
the reason is kept on both rows. Rollback refuses if the previous copy's lot
rows were pruned — prune only after the next quarter has settled.

## 7. Warnings on the Lots pages

| Banner | Cause | Do |
|---|---|---|
| red — "The county map copy is N days old" | copy in use older than 120 days | §4 |
| red — "The last county download did not complete: N layers failed" | a snapshot with `refused` / `failed` / unfetched | §8-A, then re-acquire those keys |
| red — "A county source changed on its own side (layer X)" | probe found `moved` / `fields_missing` / `count_drift` / `registry_changed` | §8-A; the copy in use is unaffected |
| amber — "Layer X did not answer this month's check" | probe `unreachable` (a site down is not evidence the data changed); two months in a row turns red | nothing yet; check next month or run `scripts/flats_probe.py` by hand |
| amber — "A refreshed copy from D is waiting for review" | a candidate older than 14 days | §5 |
| amber — "The monthly source check has not run since D" | no probe row in 45 days | check Celery beat; `docker compose run --rm api python scripts/flats_probe.py` |
| grey footer only | nothing wrong | — |

## 8. Failure modes

**A. The source moved or changed shape** (the downloader and the probe catch these)

| What | Shows as | Handling |
|---|---|---|
| Service URL gone / republished under a new name (Wood Village sewer, 2026-09) | `failed` in the manifest; probe `moved` | Find the new service on the city's open-data portal, repoint `pipeline.yaml` with a note, re-acquire the key. Meaning unclear → HUMAN_TODO. |
| Declared field renamed or dropped | `refused` (no file written) | Read the new schema, fix `fields` / `zone_field`, re-acquire. The zone field itself gone → HUMAN_TODO. |
| ZIP member renamed (ugb.shp, 2026-09) | `failed: member not in archive` | Repoint the member or replace with an ArcGIS source. |
| A layer replaced by a different product (Gladstone = the regional fabric) | count far outside tolerance; `count_drift` | Add or fix the `where` clause; confirm the count is the city's order of magnitude. |
| Flaky service / partial fetch | `unfetched_ids` | Re-acquire the key; `layers_incomplete` blocks promotion until none remain. |
| Rate limit / very slow | long `seconds`, possible `failed` | Re-run the key later. |

**B. The content changed** (expected every quarter; the delta classifies it)

| Change | Normal volume (M+C, a quarter) | Handling |
|---|---|---|
| Attribute-only (assessment, sale, year built, sq ft) | ~11,000 | Adopted into `facts.assessor`; no re-measure; verdict unchanged unless a rule reads the field. |
| Split, parent keeps its number and shrinks | ~950 rows | Parent re-measured and re-screened, its decision marked look again; children screened fresh with a lineage row. |
| Split, parent renumbered | ~50 | Same; the old number's results stay on the old run. |
| Merge | ~350 | New lot screened fresh; each parent's decision marked. |
| Reshape (same number, boundary moved) | ~1,300 | Re-measured; adopted. |
| Deleted / vacated with no successor | a handful | Absent from the new copy; results kept on the old run. |
| Added with no predecessor | a handful | Screened fresh. |
| Rezoned | hundreds of lots a year per city; `zone_changes` trips above 10 % of a city | Re-screened; decisions marked look again. |
| New zone code | a few a year | Screens `unknown / ZONE_NOT_ENCODED`; listed per layer; encoding is a FOLLOWUPS item; `new_zones` waits for Steph. |
| Annexation (`JURIS_CITY` changes) | 5 this quarter | Jurisdiction reassigned → other rules → re-screened; decision marked. |

**C. Our own process failed**

| Failure | Handling |
|---|---|
| Acquire stopped half way | Re-run the same date; `present` datasets are skipped. Check disk first (a snapshot ≈ 1.6 GB). |
| Drift report fails with "could not resize shared memory segment" | Docker's default /dev/shm (64 MB) is too small for the parallel hash join across two copies; the postgres service carries `shm_size: 1g` since 02752a1f -- check `docker inspect re-modeling-postgres --format '{{.HostConfig.ShmSize}}'`. |
| Load failed midway | The load is one transaction; nothing partial lands. Fix, re-run. The first September load stopped twice on real data, both fixed in code: a lot outline longer than the CSV reader's 128 KB default (f8d1147a) and a blank jurisdiction for the 16,963 lots in Canby, Sandy, Molalla, Estacada and Barlow -- on the roll, in no layer the rules hold -- which now carry `juris_city:<name>` and screen `JURISDICTION_NOT_ENCODED` (5512490a). |
| Candidate loaded, measurement was wrong | Never promote; the copy in use is untouched. Leave the candidate for inspection, or replace it: a re-export is a new `source_id`, so the loader makes a *second* candidate run on the same snapshot and its upsert never deletes -- a lot the re-export no longer carries would stay behind with the old run's results, `candidate_run()` would pick the newest run, and the Lots page would list both. So first retire the old run in one transaction (rehearse it with `ROLLBACK`, then `COMMIT`): `DELETE FROM flats.lot_results WHERE run_id = <old>; DELETE FROM flats.lots WHERE snapshot_id = N; DELETE FROM flats.runs WHERE id = <old>;` -- the whole lot table of the snapshot, not just the orphans, so the fresh load writes a truthful `first_seen_run_id` and computes `checks` on exactly the rows it loaded; `lot_changes` is keyed by snapshot and survives. Then steps 14–16 again (keep the old bundle beside the new one as `bridge/<date>.run<old>`). Done 2026-09-19 for run 6 -> run 8 (2,001 condominium unit records dropped, 8e596f8b). When only quadfit's columns changed (a drawing fix in s6s; the badge, stalls and method on the lot page), the 7-hour screen is not re-run: re-export from the same assign dir -- its `meta.json` names the quadfit directory, whose `lots_results.csv` is read at export time -- with `--code-version` and `--rules-version` set to the run being replaced, so the bundle names the checkout the FLATS results were screened on and the drift report reads them as unchanged. Done 2026-09-19 for run 8 -> run 10 (quadfit's corner-lot drawing, 364c360e: 15,741 lots' badge moved, 0 FLATS answers, drift unchanged at 178 / 0 unexplained). And when the re-export carries the SAME lots (the same assign dir, nothing dropped), the retire step is not needed at all: the loader finds the run by its `source_id` (the assign dir and its finish time) and lands on the same row, upserting every lot and result in place -- `run_created: false`, `lots_updated` = the bundle's count, `checks` recomputed. Rehearse with `--dry-run` (it reports the same counts and rolls back), then load, VACUUM, and re-run the drift report so `report.drift` reads the new columns. Done 2026-09-20 for the side-court / through-lot drawing (d5181f1a) into run 10: 400,032 lots and 800,064 results updated, badge moved on 6,357 lots, 0 FLATS answers, drift unchanged at 178 / 0 unexplained. |
| The wrong copy was promoted | Roll back (§6). |
| No new RLIS release yet | Not a failure: the ArcGIS layers still refresh; RLIS keys report `present`; the footer names the release. |
| Rules changed between the two runs | The drift report attributes moves to `rules`; take the refresh on the rules commit that is live so this is normally 0. |
| "measured but not in the snapshot's lot table (kept)" is not 0 in assign's `summary.md` | quadfit measured a TLID normalize neither kept nor named in `excluded.csv.gz`. Look the TLID up in the snapshot's `rlis_taxlots.geojson`; a lot that is there and is land is a normalize bug, a lot that is not there is a stale quadfit stage file (step 5 not run). |
| Many moves under `code` | `code` is what is left when neither the ground nor a measured fact moved and the repo HEAD differs -- it says a commit landed between the runs, not which. Read `git log <from code_version>..<to code_version> -- flats/score flats/geom flats/ingest/quadfit.py "Lot Analysis/quadfit"`; if nothing there changed, the moves are a bug and belong under `unexplained` by hand. |

## 9. Drift audit

Three kinds, and all three leave rows:

1. **Source drift** — the monthly probe (`flats.probes`): URL answers, fields
   present, count within tolerance, registry spec unchanged, RLIS release
   name unchanged. Warn-only.
2. **Content drift** — every refresh: `flats.lot_changes` between the two
   copies (§5 question 2), cross-checked against Metro's `taxlot_change`
   list; disagreement above 20 % trips `rlis_agreement`.
3. **Verdict drift** — every refresh: `report.drift` on the candidate (§5
   question 4); a move with no cause trips `verdict_drift` and blocks the
   agent.

Once a year, take a snapshot and run steps 2–4 with no intention of promoting,
as a check that nothing moved unseen between quarters.
