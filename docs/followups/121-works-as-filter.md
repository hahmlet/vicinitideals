# 121. The lots list's "Works as" filter gives up on production (found 2026-10-28, run 87).

121. [Copilot] [scan: NO] **The lots list's "Works as" filter gives up on production (found 2026-10-28, run 87).**
   `_works_as` (app/api/routers/ui_flats.py ~3352) groups all ~1.18M results of a run and reads two colours out of
   the `checks` JSON for each: 10-14 s per call on 114, and the page runs it inside both the count and the rows
   query, so it passes the 25 s Lots page limit (`_LOTS_TIMEOUT_MS`) and Steph sees "too slow". Same on run 85
   (not a run-87 regression). E2E `tests/e2e/test_flats_lots.py::test_the_works_as_filter_narrows_the_list_and_the_lot_page_says_it_in_words`
   fails against https://viciniti.deals on the Show click (30 s). Change: work the answer out once per run at load,
   as `flats.lot_prices` is (app/models/flats.py ~405, filled by flats/ingest/lot_prices.py from
   scripts/flats_load_bridge.py ~1129): a small table (run_id, lot_id, design_key, apartment_green,
   townhomes_green) + Alembic migration + index on (run_id, design_key); the loader fills it; a backfill script for
   the kept runs; `_works_as` reads it with the same meaning (any design green in that form; rows without both
   forms match no choice). Must not change: any colour, count or lot shown for a filter; the lot page's
   per-design sentence. Test: tests/api integration test that the four choices return the same lots as the old
   JSON query on seeded results; then (Claude) run the backfill on 114 and the E2E above against production.
