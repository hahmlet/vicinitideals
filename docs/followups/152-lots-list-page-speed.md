# 152. The FLATS lots list is slow (9-25 s per query) and times out the prod E2E

[Claude] [scan: no] Found 2026-11-06 during the run-118 release (148 + 118).

## What
`/flats/lots` computes each lot's best colour across designs live: a GROUP BY
over the whole run in `flats.lot_results` (run 118 = 1,175,630 rows, 587,815
lots), then a nested-loop join to `flats.lots` for the sort, several such
queries per page (list, city counts, verdict counts). EXPLAIN ANALYZE on 114,
2026-11-06: 12.3 s for the LIMIT 50 page query (HashAggregate spills 21
batches to disk; 587,815 pkey probes into `flats.lots`, 520k buffers read).

## Effect
Prod E2E `tests/e2e/test_flats_lots*.py` fails 2 of 15 on Page.goto timeouts,
a different two each run (green_lot_opens..., tight_fit_is_a_filter...,
city_filter_narrows..., counts_the_run_by_verdict). Not a run-118 regression:
the plan is the same shape for any run; it got worse as runs grew.
The UI works, just slowly.

## Options (no Steph decision needed -- it is speed, not a verdict)
1. Precompute best colour per (run, lot) at load/promote time into a small
   table (the `lot_works_as` pattern), with the jurisdiction/tlid sort keys,
   and index it. The list and counts read that table. Best fix.
2. Stop-gap: raise `work_mem` for the session that runs these queries (the
   aggregate spills to disk) and the E2E goto timeout.

## Test
Integration test that the list reads the precomputed table and agrees with
the live GROUP BY on a fixture run; prod E2E lots file green 3 runs in a row.
