# Postgres Test DB

**Status**: Landed 2026-05-21. Branch `feature/postgres-test-db`.
**Owner**: Steph
**Replaces**: in-memory SQLite test fixtures.

## What shipped

Tests now run against a dedicated Postgres 16 container (`re-modeling-postgres-test`)
instead of in-memory SQLite. Same image as production, full JSONB / ARRAY / server
default parity, no shim divergence for new code.

### Container

Lives on VM 114, port `5433`, tmpfs-backed data dir (wiped on every container
restart — never holds real data). Standalone compose file
(`docker-compose.test.yml`) so production deploys never touch it.

Start command:
```
docker compose -f docker-compose.test.yml up -d
```

Bound to `0.0.0.0:5433`. Test runners connect over LAN at `192.168.1.28:5433`.

### Conftest design

`tests/conftest.py` orchestrates per-run database lifecycle:

1. **Session-scoped `_test_db_url`**: synchronous psycopg2 connection to the
   maintenance DB. `CREATE DATABASE re_modeling_test_<uuid>` → run
   `Base.metadata.create_all` via sync engine → yield connection URL →
   `DROP DATABASE ... WITH (FORCE)` on teardown. **Synchronous** because
   asyncpg connections are pinned to the asyncio loop that opened them; any
   long-lived async session-scoped resource fights pytest-asyncio's loop
   management.

2. **Session-scoped `_test_engine`**: AsyncEngine bound to the per-run DB, with
   `NullPool` to keep connection state minimal.

3. **Function-scoped `session`**: yields a fresh `AsyncSession`, then issues
   `TRUNCATE ... RESTART IDENTITY CASCADE` over all `Base.metadata` tables.
   Truncate (vs SAVEPOINT rollback) handles tests that call `session.commit()`
   internally — common in engine compute helpers.

### Event loop policy

`pyproject.toml` pins `asyncio_default_fixture_loop_scope = "session"` and
`asyncio_default_test_loop_scope = "session"` so all tests share one event
loop. On Windows the conftest also forces `WindowsSelectorEventLoopPolicy`
because asyncpg + ProactorEventLoop drops connections on teardown.

### CI

Both `light-gate` and `full-gate` jobs add an ephemeral `postgres-test`
service container on port 5433, with `TEST_DATABASE_URL` pointed at
`localhost:5433`. No reliance on the prod-style compose stack for the
test DB.

## Known limitations

- **7 legacy test files still use inline SQLite engines** instead of the shared
  conftest: `test_scenario.py`, `test_scraper.py`, `test_import_tower_ap_deal.py`,
  `test_tower_ap_parity.py`, `test_dedup.py`, `test_benchmark_fixtures.py`,
  `test_routers.py`. These still need the `JSONB().with_variant(JSON(), "sqlite")`
  shims on a handful of models to compile their schema. Migrate to the Postgres
  conftest when touched; the shims can come off entirely once all seven are gone.

- **LAN-only access for local dev**: the test container is reachable on VM 114's
  LAN IP only. Tests can't run offline (e.g. laptop on a coffee shop wifi without
  VPN back to the homelab). Acceptable trade-off chosen to avoid installing
  Docker Desktop or native Postgres on Windows.

- **Some pre-existing test failures became visible** after the swap — stale
  field references (`Project(deal_type=...)`) and inline `Opportunity(...)`
  constructions that omit `source_url`. These were always broken; SQLite's
  permissiveness or the test never running masked them. Out of scope for this
  change.

## Follow-ups (separate work)

1. Migrate the 7 inline-SQLite test files to the shared Postgres conftest.
2. Strip every `with_variant(JSON(), "sqlite")` and `with_variant(JSONB, "postgresql")`
   shim from model files once (1) lands.
3. Fix the stale `Project(deal_type=...)` and seed-helper omissions surfaced by
   the swap.
4. Consider Tailscale if local-without-LAN testing becomes important.
