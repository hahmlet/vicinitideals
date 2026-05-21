# Plan — Migrate Test DB from In-Memory SQLite to Postgres

**Status**: Drafted 2026-05-20. Not started.
**Owner**: Steph
**Depends on**: JSONB shim patch (landed 2026-05-20, branch `main`).

## Why

Test suite uses in-memory SQLite. Production uses PostgreSQL 16 with JSONB and ARRAY columns. To keep tests runnable on SQLite we ship per-column `with_variant(JSON(), "sqlite")` shims on every Postgres-specific type. This has cost us:

- **Recurring per-feature blocker**: every time a new model adds a JSONB/ARRAY column, integration tests collection-fail until shim is added. Three separate sessions hit this in the last month (memory IDs 9210, 9425, 9515).
- **SQLite ≠ Postgres divergence risk**: SQLite JSON does not support Postgres operators (`@>`, `->>`, indexing on JSON keys). Engine code that uses those operators cannot be tested.
- **No ARRAY semantics**: SQLite stores arrays as JSON text. Postgres `ANY()`, `&&`, `@>` array ops untestable.
- **Pre-existing test failures masked**: 17 engine/waterfall tests fail post-shim — some may be SQLite-vs-Postgres behavior diffs we can't diagnose without parity.

## What changes

Replace `sqlite+aiosqlite:///:memory:` engine in `tests/conftest.py` with a Postgres engine pointed at a dedicated per-worker test database. Drop the `with_variant(JSON(), "sqlite")` shims everywhere they exist (~12 sites across 7 model files).

## Approach — per-worker isolated DBs

CI and local dev both already run Docker Compose with a Postgres container. Use it.

### Local dev

- New env var `TEST_DATABASE_URL` defaults to `postgresql+asyncpg://re_modeling:re_modeling@localhost:5432/re_modeling_test`.
- Test runner creates `re_modeling_test_<worker_id>` database per pytest-xdist worker (or `re_modeling_test` if no parallelism).
- Session-scoped fixture: `CREATE DATABASE` → `alembic upgrade head` → yield engine → `DROP DATABASE` on teardown.
- Function-scoped fixture: open transaction → yield session → `ROLLBACK` (current pattern, unchanged).

### CI

- Already has Postgres service. Reuse it.
- Add step before pytest: `createdb re_modeling_test` (no-op if exists).
- Set `TEST_DATABASE_URL` in workflow env.

## Open decisions

1. **Schema creation: Alembic vs `Base.metadata.create_all`?**
   - Alembic: tests run real migrations. Catches migration bugs. Slower (~5–10s for all 94 migrations on cold DB).
   - `create_all`: instant, matches current SQLite behavior. Misses migration ordering bugs.
   - **Recommend**: `create_all` per worker, plus a separate `tests/migrations/test_alembic_upgrade.py` that runs all migrations sequentially against a throwaway DB. Best of both.

2. **Per-test isolation: transaction rollback vs truncate?**
   - Current: function-scoped session, `await sess.rollback()` on teardown. Works because SQLite `:memory:` is per-engine.
   - With shared Postgres test DB: rollback works as long as test doesn't `commit()`. Most tests don't. Spots that do (a handful of seed helpers calling `flush()` then expecting persistence across sessions) need audit.
   - Fallback: `TRUNCATE ... CASCADE` of all tables between tests. Slower but bulletproof.

3. **Parallelism**: pytest-xdist not currently configured. Adding it amplifies the win (4–8× speedup) but multiplies DB setup cost. Defer unless test suite slow enough to matter.

## Effort estimate

- Conftest engine swap + per-worker DB management: **2–3h**
- Strip `with_variant(JSON(), "sqlite")` shims from models: **1h**
- Update CI workflow: **30m**
- Smoke-test full suite, fix anything that relied on SQLite quirks: **1–2h**
- Local dev setup docs (CLAUDE.md update): **30m**

**Total: ~half-day project.**

## Risks

- **Postgres dependency for unit tests**: developers must have Docker + Postgres running to run tests. Currently `pytest tests/engines/` works with zero infra. Mitigation: keep one Postgres test DB always-running in the existing Compose stack so it's free if the project is already up.
- **Test suite slowdown**: SQLite in-memory is ~milliseconds per fixture. Postgres TCP + transaction overhead adds tens of ms. Across hundreds of tests this could double runtime (current ~30s → ~60s). Acceptable for the parity win.
- **CI cache invalidation**: per-worker DB creation slows cold CI starts by ~10s. Trivial.

## Out of scope

- Migrating E2E tests (already use live Postgres via deployed app).
- Replacing SQLite for any non-test code path (none exists).
- Adding integration tests that exercise Postgres-specific JSONB operators — that's a follow-up.

## Rollout

1. Land plan doc (this file).
2. Branch `feature/postgres-test-db`. Worktree.
3. Conftest swap + DB management fixtures. Run smoke (`pytest tests/engines/`).
4. Strip shims one model file at a time, run targeted tests after each.
5. Full suite green on Postgres. Compare pass count to current shimmed-SQLite baseline (107 pass / 17 fail). Investigate any newly-failing test before declaring done.
6. CI workflow update.
7. Merge. Delete shim helper if any centralized.
