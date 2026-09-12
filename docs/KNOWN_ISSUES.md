# Known issues and open items

Agent-facing list of accepted limitations and deferred fixes. Human-action
items live in [HUMAN_TODO.md](HUMAN_TODO.md).

1. **X-Forwarded-For shows `192.168.1.1`**: UniFi SNAT on port forwards. The
   rate limiter buckets on the proxy IP (global). The per-email limit still
   works. Accepted as-is.

2. **Organization management**: no org creation UI or invite flow yet. The
   first registered user auto-creates "Default Organization".

3. **`docs/FINANCIAL_MODEL.md`** needs an update for per-loan
   `_loan_pre_op_months`, trigger-chain requirements, and the
   `_PERIOD_TYPE_RANK` windowing logic.

4. **Listing jurisdiction data inaccurate**: scraped `city` values from listing
   sources (Crexi/LoopNet) often use the metro name instead of the actual
   jurisdiction (e.g. Gresham listings tagged "Portland"). Fix: add a
   `jurisdiction` column to `scraped_listings`, backfill via nearest-parcel
   lookup using lat/lng against parcels with known jurisdictions, update the
   scraper pipeline to assign jurisdiction on ingest.

5. **Concurrent `compute_cash_flows` on one scenario is a race, and only the
   slider path is guarded.** The engine clears a scenario's cash flows, line
   items, draw events and outputs and writes them again, so two computes of the
   same scenario running together interleave four delete-then-insert passes.
   The first symptom is a unique violation on
   `uq_operational_outputs_scenario_project`. `POST /models/{id}/sliders` now
   takes a transaction-scoped advisory lock (`_compute_lock_key`) because a
   fast slider drag is the one path known to fire twice in a second; found
   2026-09-04 by the concurrency test in `tests/api/test_gap_adjustment_sliders.py`
   once it was given a session per request. The same pattern is unguarded at
   `models.py:722`, `models.py:918` and `app/tasks/scenario.py:321`. Left alone
   deliberately — the money-model side is not open for opportunistic fixes.
