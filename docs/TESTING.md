# Testing — current infrastructure and runbooks

> Authoritative reference for how the test suites are wired and run. The short
> commands live in [CLAUDE.md](../CLAUDE.md) "Testing"; everything longer lives
> here. [testing-strategy.md](testing-strategy.md) is the historical design
> doc and is marked stale.

## Test infrastructure

- **pytest-asyncio** (auto mode) with a dedicated Postgres test database on VM 114
  (container `re-modeling-postgres-test`, port `5433`, tmpfs-backed)
- Session-scoped event loop and engine. `CREATE DATABASE` per pytest run via sync
  psycopg2 (outside any asyncio loop), `DROP DATABASE ... WITH (FORCE)` on teardown
- Function-scoped session that `TRUNCATE`s all tables for the next test — safe even
  when test code calls `session.commit()`
- `httpx.AsyncClient` + `ASGITransport` for API integration tests
- Seed helpers in `tests/conftest.py`: `seed_org()`, `seed_deal_model()`,
  `seed_deal_model_with_financials()`
- Markers are auto-assigned at collection: e2e by path, integration when DB
  fixtures are present, else unit.
- A handful of legacy test files still spin up their own in-memory SQLite engine
  inline (test_scenario, test_scraper, test_dedup, test_benchmark_fixtures, the
  two tower_ap scripts, test_routers). They depend on the
  `JSONB().with_variant(JSON(), "sqlite")` shims still present on a few models.
  Migrate them to the shared Postgres conftest when touched.

### Local dev: starting the test Postgres

The container lives on VM 114 and runs from a standalone compose file:

```bash
mcp__proxmox-mcp__ssh_exec container_id=114 command="cd /root/stacks/vicinitideals && docker compose -f docker-compose.test.yml up -d"
```

It's restart-policy `unless-stopped`, so once started it stays up across VM reboots.
Tests connect over LAN to `192.168.1.28:5433`. Override with `TEST_DATABASE_URL`
when running tests from outside the LAN (e.g. CI).

### Windows event-loop policy

`pytest_collection_finish` picks the Selector or Proactor loop based on what was
collected. Don't mix unit and E2E tests in one Windows pytest run — run them as
separate invocations.

## Running tests

```bash
uv run pytest tests/ -q -m "unit" --ignore=tests/e2e     # Unit tests only
uv run pytest flats/tests -q -n auto                       # FLATS (no DB needed)
uv run pytest tests/ -q --ignore=tests/e2e                # Unit + integration
uv run pytest tests/e2e/ -q -m e2e                        # E2E (needs running app)
uv run ruff check app/ tests/ flats/ scripts/               # Lint (same scope as CI)
```

**`-n auto` is for `flats/tests` and nothing else.** The FLATS suite touches no
database, no network and no shared file, so it shards cleanly — measured
2026-09-10 on 16 cores, 13:07 → **2:24** at `-n auto` (16 workers) with the same
3,096 passed / 5 skipped and zero failures. The `tests/` suites share one
Postgres database and `TRUNCATE` between tests, so running them under `-n` would
have workers wiping each other's rows. There is deliberately **no `addopts` in
`pyproject.toml`** putting `-n` on every run, for exactly that reason.

## The FLATS corpus census — read before touching it

`flats.encode.qualified.qualified()` costs **~14 seconds and is recomputed on
every call.** Roughly 26 tests across thirteen files run the same corpus-wide
footnote census with it (`test_every_new_note_is_ruled_and_none_blocks` and its
siblings in `test_block_limit`, `test_declared_notes`, `test_glued_run`,
`test_legend_lines`, `test_lettered_markers`, `test_notes_lead`,
`test_page_frame`, `test_parenthesised_table_names`, `test_wrapped_citations`,
`test_nested_notes_and_lone_cells`, `test_wilsonville_notes`,
`test_wood_village`, `test_lake_oswego_notes`). That is **1.3% of the suite
holding 63% of its runtime**, and it accumulated honestly — each of those tests
was added the day a new footnote shape was found, and each is individually
correct. `-n auto` hides the cost. It does not remove it.

**Three rules for anything that touches this, now or later:**

1. **Adding another census test adds another ~14 seconds.** If a new footnote
   shape needs one, that is fine and correct — but say so, because the number
   above moves and this note goes stale otherwise.
2. **If the census is ever cached, it must be a session-scoped pytest fixture —
   never a module-level `@lru_cache` on `qualified()`.** The standing project
   rule is *regenerate a ledger before trusting it*; a process-lifetime cache in
   the module would carry into the CLI ledgers and the review screens, where a
   stale census is exactly the failure the funnel ledgers exist to prevent.
   Caching in the test session is safe because the corpus cannot change mid-run.
3. **A cached census must be invalidated by any test that writes to the corpus.**
   If a fixture is built, tests that save a document or rewrite a jurisdiction
   YAML have to opt out of it or clear it, or they will assert against a census
   taken before their own edit.

Not fixing this is a live decision, re-taken every time the suite is touched.
Corpus I/O is *not* the cause and caching reads will not help: all 181
documents (13.3 MB) load in 0.26s and `load_rules()` in 0.19s. The cost is
processing.

## Test creation requirement

**Every plan must end with a test validation step.** Before marking any task done:

1. **Review existing tests** — read the relevant test file(s) and check whether any
   existing tests cover the changed behavior. Update them if the change altered
   something they assert.
2. **Write new tests if missing** — if no test exercises the new behavior, write one:

| Changed area | Required test |
|---|---|
| `app/engines/` | Unit test in `tests/engines/` verifying the changed math/behavior |
| `app/api/routers/` | Integration test in `tests/api/` covering the new/changed route |
| New or changed UI feature | E2E test in `tests/e2e/` exercising it in a browser |
| Bug fix | Test that would have caught the bug |

UI flows must be exercised through Playwright, not API shortcuts; API-only tests
are for engine, auth and data behaviour.

3. **Run targeted E2E tests** — do not run the full suite. Run only the test
   file(s) that cover the changed feature:

```powershell
# Example: wizard change → run only wizard tests
$env:E2E_BASE_URL="https://viciniti.deals"; uv run pytest tests/e2e/test_wizard_flow.py -v

# Example: underwriting change → run only underwriting tests
$env:E2E_BASE_URL="https://viciniti.deals"; uv run pytest tests/e2e/test_underwriting_flow.py -v
```

Confirm they pass before stopping. If they fail, fix and re-run.

The stop hook separately runs `pytest tests/ --ignore=tests/e2e` when `app/`
changes are detected (up to 3 attempts, then escalates). Bypass mid-refactor:
`New-Item .claude/state/skip_verify.json`.

## Phase B debt regression (`tests/e2e/test_phase_b_debt.py`)

8 tests covering Sources=Uses parity, DSCR-capped gaps, carry-type formula
round-trips. Playwright wizard flows + engine math verification against the live
instance:

```powershell
$env:E2E_BASE_URL="https://viciniti.deals"; uv run pytest tests/e2e/test_phase_b_debt.py -m e2e -v
```

## CI pipeline (`.github/workflows/ci.yml`)

- **Scope detection**: skips heavy gates for docs/templates-only changes
- **Light gate**: Ruff lint + unit tests (every push/PR)
- **Full gate**: integration tests + E2E (Playwright) + Phase B regression + Trivy
  image scan + Semgrep SAST
- CI seeds the login via `app/scripts/seed_e2e_user.py` and the reference rows the
  suite reads but never creates via `app/scripts/seed_e2e_fixtures.py` (brokers, so
  far). Every seeder there is guarded on its table being empty, so it no-ops
  anywhere the rows already exist.
- The E2E step runs `-m "e2e and not slow"`. `slow` excludes exactly
  `tests/e2e/test_proforma_cache.py`, which needs the analysis worker *and* a
  locally-hosted Ollama model — neither exists on a runner. Run it deliberately
  against an environment that has them: `pytest tests/e2e/test_proforma_cache.py
  -m "e2e and slow"`.
- CI is behind production: a red CI is the only thing between a bad push and an
  outage. Run the whole suite and read CI before calling a commit clean.

## When an E2E test fails

Work through [Troubleshooting/e2e-failed-test.md](Troubleshooting/e2e-failed-test.md)
in order.
