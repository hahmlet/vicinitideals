# Claude AI Assistant Instructions — vicinitideals

## Product Overview

Self-hosted real estate financial modeling + deal intelligence platform for Portland-area investment team. Two core functions:

1. **Parcel intelligence** — scrapes commercial listings (Crexi, LoopNet, REALie) + county GIS (Portland Maps, Clackamas, Oregon City, Gresham ArcGIS). Maintains living parcel inventory across Multnomah + Clackamas County, OR.
2. **Deal underwriting** — full financial model builder: Uses, Sources, debt carry (4 types), operating cash flow, equity waterfall, draw schedule, sensitivity analysis, Excel export.

**Live URL**: `https://viciniti.deals`
**Domain**: Cloudflare DNS, Let's Encrypt wildcard cert on NGINX Proxy Manager (LXC 109)

---

## Tech Stack

FastAPI 0.110+ (Python 3.12+) · SQLAlchemy 2.0 async + asyncpg · Alembic · Celery 5.3+ (2 queues: default, analysis) · Redis · PostgreSQL 16 · Jinja2 + HTMX 2.0.9 · pyxirr (IRR/XIRR) · openpyxl · Pydantic v2 · pydantic-settings · httpx · curl-cffi · uv (package manager) · Docker Compose · Ruff (linter)

---

## Infrastructure

| Component | Location | Notes |
|---|---|---|
| App (all Docker containers) | VM 114 (`192.168.1.28:8001`) | FastAPI on port 8001, Celery workers, PostgreSQL, Redis |
| NGINX Proxy Manager | LXC 109 (`192.168.1.195`) | Proxies `viciniti.deals` → VM 114:8001 |
| MCP Servers | LXC 112 | Proxmox, Home Assistant, Node-RED, Wallabag |
| PostgreSQL | Docker on VM 114 | Named volume `re-modeling-postgres-data` |
| Redis | Docker on VM 114 | Celery broker + backend |
| Resend (email) | External SaaS | API key in VM 114 `.env` only |
| Proxmox host docs | `../personalproxmox/documentation/MCP/` | Infrastructure reference |

**Docker services** (in `docker-compose.yml`):
- `vicinitideals-api` (FastAPI, port 8001→8000)
- `vicinitideals-worker-default` (Celery, `-Q default -c 2`)
- `vicinitideals-worker-analysis` (Celery, `-Q analysis -c 2`)
- `vicinitideals-beat` (Celery beat scheduler)
- `vicinitideals-static` (nginx:alpine, port 8002)
- `re-modeling-postgres` (PostgreSQL 16, DB name `re_modeling`)
- `re-modeling-redis` (Redis 7)

---

## Deploy Workflow

**IMPORTANT: Task NOT complete until deployed to production.** Agents manage 100% of deploys. Unless told otherwise, always deploy after commit+push — no permission needed. "Done" means live on `viciniti.deals`, not committed locally.

**Deploy steps** (all three required):
1. `git push origin main`
2. `mcp__proxmox-mcp__ssh_exec container_id=114 command="bash /root/deploy-vicinitideals.sh"`
3. Verify smoke checks pass in deploy output

Deploy script runs: `git pull → docker compose build → alembic upgrade head → docker compose up -d → health check`

**Manual fallback** (if MCP unavailable):
```bash
# SSH to VM 114 directly
ssh root@192.168.1.28 "bash /root/deploy-vicinitideals.sh"
```

---

## Working in This Repo

### Branch & worktree convention

Primary checkout (`c:\Users\Steph\Repos\vicinitideals`) stays on `main`. Branched work lives in worktrees at `c:\Users\Steph\Repos\vicinitideals-worktrees\<slug>\` so parallel agent sessions don't collide on shared working-tree state.

**When to use worktree:**
- **Bug fixes, small tweaks, doc edits, config changes** → work on `main` in primary checkout. No worktree.
- **New features, refactors, risky changes** → **confirm with user first** before creating worktree. Don't start branched work in primary checkout.

**Per-worktree setup** (from primary):
```bash
git worktree add ../vicinitideals-worktrees/<slug> -b feature/<slug> main
cp .env ../vicinitideals-worktrees/<slug>/.env
( cd ../vicinitideals-worktrees/<slug> && uv sync )
```

`.gitignore` excludes `.env`, `.venv/`, `.claude/` — each worktree gets own. Shared `.git` object DB makes worktrees cheap.

**Granularity:** one branch = one shippable slice = one worktree. If worktree scope grows beyond one mergeable change, split into multiple branches/worktrees. Merge each slice when independently deployable; gate user-visible behavior with feature flags rather than delaying merges.

**Cleanup** — remove finished worktree: `git worktree remove <path> && git branch -d <branch>`. Find stale worktrees (run from primary, safe weekly):
```bash
git worktree list --porcelain | grep '^worktree' | awk '{print $2}' | while read wt; do
  branch=$(git -C "$wt" branch --show-current)
  if [ -n "$branch" ] && [ "$branch" != "main" ] && git merge-base --is-ancestor "$branch" main 2>/dev/null; then
    echo "stale (merged): $wt on $branch"
  fi
done
```

### End-of-session checklist

When user indicates session ending, run through before closing:

1. **Undone items** — list anything discussed but not finished, plus follow-ups identified (open questions, deferred fixes, things user said "later").
2. **Completed work summary** — commits (branch + SHA), pushes, deploys, decisions not captured in commit messages.
3. **Worktree trim** — if session branch merged into main and won't be touched again, run `git worktree remove` + `git branch -d`. If work in progress, leave. If unsure, ask.
4. **Schema doc updates** — if session changed engine behavior, data model, or architecture, update relevant docs:
   - [docs/FINANCIAL_MODEL.md](docs/FINANCIAL_MODEL.md) — financial engine math (cashflow, draw schedule, waterfall, underwriting metrics, carry types, auto-sizing)
   - [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — ORM schema (deal, scenario, capital, milestone, project, parcel)
   - [docs/MARKET_MODEL.md](docs/MARKET_MODEL.md) — market/comp model
   - [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) — overall architecture

   Don't write doc updates every commit — only when behavior, schema, or invariants changed.

---

## Project Structure

```
app/
  api/routers/
    ui.py              # HTMX UI routes (~7900 lines, most active file)
    auth_routes.py     # Login, register, verify email, password reset
    capital.py         # Capital stack API
    deals.py, scenarios.py, projects.py, listings.py, parcels.py, ...
  engines/
    cashflow.py        # Monthly cashflow engine (~1800 lines)
    draw_schedule.py   # Self-referential draw sizing
    waterfall.py       # Equity distribution waterfall
    underwriting.py    # Deal metrics (cap rate, CoC, IRR, DSCR, LTV)
    sensitivity.py     # Multi-variable sensitivity tables
  models/
    deal.py            # Deal, Scenario, OperationalInputs, UseLine, IncomeStream, OpEx
    capital.py         # CapitalModule, WaterfallTier, DrawSource
    milestone.py       # Timeline milestones with trigger chains
    project.py         # Project, Opportunity
    parcel.py, scraped_listing.py, org.py, ...
  schemas/
    capital.py         # Pydantic schemas for JSONB columns (source/carry/exit_terms)
    deal.py            # JSON export/import schemas
  emails/
    sender.py          # Async Resend wrapper (httpx, no SDK)
    tokens.py          # itsdangerous token generation
    templates/         # Email HTML templates
  scrapers/            # One module per data source
  tasks/               # Celery tasks (scraping, parcel seed, analysis)
  exporters/           # Excel + JSON export/import
  templates/           # Jinja2 HTML templates (HTMX partials in templates/partials/)
  config.py            # pydantic-settings (reads .env)
  scripts/             # CLI utilities (seed_e2e_user.py, check_promotion_gates.py)
alembic/versions/      # 41 migrations (latest: 0041_user_email_verified)
tests/
  engines/             # Unit tests: cashflow, draw_schedule, underwriting, waterfall
  api/, models/, exporters/, scrapers/, tasks/, contract/
  e2e/                 # Playwright E2E tests
  conftest.py          # Shared fixtures: per-run Postgres test DB, seed helpers
scripts/
  test_phase_b_debt.py # 8-test regression suite (Sources=Uses, DSCR parity, carry formulas)
docs/
  FINANCIAL_MODEL.md   # 846-line math reference
  PROJECT_OVERVIEW.md  # Architecture overview
  testing-strategy.md  # Test architecture
  Troubleshooting/     # Per-symptom debug guides (start here when something breaks)
  ops/, security/, verification/, wireframes/
```

---

## Key Architectural Concepts

### Financial Engine (cashflow.py)

- **4 carry types**: `io_only` (True IO), `interest_reserve` (avg-draw, day-precise via `period_interest_months()`), `capitalized_interest` (PIK, full-balance, day-precise via `period_interest_months()`), `pi` (amortizing). Statistical `(N+1)/2` and `N` factors are used for the principal sizing solve; period-level cash flows use `app/engines/interest.py:period_interest_months()` with actual day-count conventions.
- **Per-loan active windows**: each loan's pre-op months from `_loan_pre_op_months(module)`, NOT global `constr_months_total`
- **`_PERIOD_TYPE_RANK` + `_APS_TO_RANK`**: maps `active_phase_start` to phase ordering for windowed month counting
- **Auto-sizing**: `_auto_size_debt_modules()` with one-pass algebraic divisor fold-in for closing costs (Sources = Uses invariant)
- **DSCR-capped mode**: principal capped via `newton_solve.solve_principal_for_dscr()` (Newton-Raphson with bisection fallback); when DSCR cap binds, gap is surfaced to user
- **Source-Use eligibility**: `app/engines/source_routing.py` — `eligible_sources_for_use()` / `route_use_to_sources()`; permissive by default, whitelist via `capital_modules.eligible_use_tags` or `use_lines.eligible_module_ids`
- **Default loan closing costs**: `_DEFAULT_LOAN_COSTS` table per `funder_type`
- **`vehicle_type` + `equity_role` are canonical** on `CapitalModule` (post-0085); `funder_type` is a legacy bridge field retained for backward compat
- Uses `Decimal` arithmetic throughout (`MONEY_PLACES = Decimal("0.000001")`)

### Milestone Timeline

- Milestones use **trigger chains** (`trigger_milestone_id`) — `computed_start()` resolves dates via chain-walk
- Timeline wizard does **two-pass creation**: Pass 1 creates milestones with durations, Pass 2 wires trigger IDs
- Without trigger chains, engine falls back to `OperationalInputs.*_months` scalars (NULL → 1mo fallback) — production bug fixed in commit `5d5caf4`

### Entity Hierarchy

```
Deal → Opportunity → Project → Milestones (timeline)
Scenario → UseLines, CapitalModules, IncomeStreams, ExpenseLines, DrawSources, WaterfallTiers
Parcel → ScrapedListings (many listings per parcel)
```

Old `Deal` ORM class now `Scenario`. (`DealModel` alias removed 2026-06-15.)

### Capital Stack

`CapitalModule` stores structured data in JSONB columns: `source` (CapitalSourceSchema), `carry` (CapitalCarrySchema), `exit_terms`. `extra="allow"` on schemas preserves engine-written keys not declared in schema.

---

## Testing

### Test Infrastructure
- **pytest-asyncio** (auto mode) with a dedicated Postgres test database on VM 114
  (container `re-modeling-postgres-test`, port `5433`, tmpfs-backed)
- Session-scoped event loop and engine. `CREATE DATABASE` per pytest run via sync
  psycopg2 (outside any asyncio loop), `DROP DATABASE ... WITH (FORCE)` on teardown
- Function-scoped session that `TRUNCATE`s all tables for the next test — safe even
  when test code calls `session.commit()`
- `httpx.AsyncClient` + `ASGITransport` for API integration tests
- Seed helpers in `tests/conftest.py`: `seed_org()`, `seed_deal_model()`,
  `seed_deal_model_with_financials()`
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

### Running Tests
```bash
uv run pytest tests/ -q -m "unit" --ignore=tests/e2e     # Unit tests only
uv run pytest tests/ -q --ignore=tests/e2e                # Unit + integration
uv run pytest tests/e2e/ -q -m e2e                        # E2E (needs running app)
uv run ruff check app/ tests/                              # Lint
```

### Test Creation Requirement

**Every plan must end with a test validation step.** Before marking any task done:

1. **Review existing tests** — read the relevant test file(s) and check whether any existing tests cover the changed behavior. Update them if the change altered something they assert.
2. **Write new tests if missing** — if no test exercises the new behavior, write one:

| Changed area | Required test |
|---|---|
| `app/engines/` | Unit test in `tests/engines/` verifying the changed math/behavior |
| `app/api/routers/` | Integration test in `tests/api/` covering the new/changed route |
| New or changed UI feature | E2E test in `tests/e2e/` exercising it in a browser |
| Bug fix | Test that would have caught the bug |

3. **Run targeted E2E tests** — do not run the full suite. Run only the test file(s) that cover the changed feature:
```bash
# Example: wizard change → run only wizard tests
$env:E2E_BASE_URL="https://viciniti.deals"; uv run pytest tests/e2e/test_wizard_flow.py -v

# Example: underwriting change → run only underwriting tests
$env:E2E_BASE_URL="https://viciniti.deals"; uv run pytest tests/e2e/test_underwriting_flow.py -v
```
Confirm they pass before stopping. If they fail, fix and re-run.

The stop hook separately runs `pytest tests/ --ignore=tests/e2e` when `app/` changes are detected (up to 3 attempts, then escalates). Bypass mid-refactor: `New-Item .claude/state/skip_verify.json`.

### Phase B Debt Regression (scripts/test_phase_b_debt.py)
8 tests covering Sources=Uses parity, DSCR-capped gaps, carry-type formula round-trips. Runs against live instance:
```bash
uv run python scripts/test_phase_b_debt.py --base-url https://viciniti.deals --auth tests/e2e/auth-state.json
```

### CI Pipeline (`.github/workflows/ci.yml`)
- **Scope detection**: skips heavy gates for docs/templates-only changes
- **Light gate**: Ruff lint + unit tests (every push/PR)
- **Full gate**: integration tests + E2E (Playwright) + Phase B regression + Trivy image scan + Semgrep SAST
- CI seeds E2E user via `app/scripts/seed_e2e_user.py`

---

## Auth System

- **Session-based auth** with `bcrypt` password hashing
- **Email verification** (soft gate): yellow banner for unverified users, `POST /resend-verification`
- **Password reset**: `itsdangerous.URLSafeTimedSerializer` with password-hash-prefix binding (single-use), 30-min expiry
- **Rate limiting**: Redis-backed fixed-window counters (`app/api/rate_limit.py`), 5/15min per IP + 3/hour per email on `/forgot-password`
- **Email delivery**: async httpx to Resend API (no SDK), graceful no-op when `RESEND_API_KEY` empty

---

## Coding Conventions

- **Python 3.12+**, `from __future__ import annotations` where needed
- **Decimal for money** — never `float` for financial values
- **SQLAlchemy 2.0 style**: `Mapped[type]`, `mapped_column()`, async sessions
- **Pydantic v2** for schemas and settings
- **Ruff** for linting (`uv run ruff check app/ tests/`)
- **uv** as package manager (not pip)
- **HTMX** for UI — server renders HTML partials, no client-side JS framework
- Module docstrings describe purpose and entity relationships
- Enums are `str, enum.Enum` subclasses for JSON serialization

---

## Database Safety

- PostgreSQL data lives in Docker named volume `re-modeling-postgres-data`
- **NEVER run `docker compose down -v`** — deletes volume and all data
- DB name and user remain `re_modeling` (intentional legacy name — renaming requires dump/restore)
- Alembic migrations run automatically during deploy (`alembic upgrade head`)

---

## Critical Do-Nots

- **NEVER use `sudo`** — use Proxmox MCP for system operations on VMs/LXCs
- **NEVER commit credentials** (.env, API keys, secrets)
- **NEVER hardcode infrastructure IPs/ports** — reference docs or config
- **NEVER run `docker compose down -v`** — destroys database
- **NEVER modify production data directly** — use migration scripts or one-shot scripts

---

## Market Coverage Policy

**Portland city proper NOT target acquisition market.** Team does not buy deals in Portland jurisdiction.

Portland listings retained for two purposes:
1. **Market comp data** — Portland has densest financial data, essential for KNN comp recommendations in jurisdictions where local comp coverage sparse
2. **Testing and development** — feature work, bug repros, UI testing where realistic data variety needed

**Do not spend money on Portland data**:
- No HelloData enrichment calls for Portland properties
- No paid API calls for Portland addresses
- No prioritization of Portland listings for manual data entry

**Target acquisition jurisdictions**: Multnomah + Clackamas county cities *other than Portland* — Gresham, Fairview, Wood Village, Troutdale, Happy Valley, Milwaukie, Oregon City, Gladstone, Lake Oswego, West Linn, Tualatin, Wilsonville, unincorporated areas. These get spending priority for paid data enrichment.

---

## Troubleshooting

### Failed E2E Test — Diagnostic Runbook

Work through in order. Stop when cause found.

**1. Read the assertion failure**
- Exact assertion text + line number in pytest output
- Expected vs. actual value
- Which parametrized variant (browser, scenario name)

**2. Check the browser console dump** (auto-captured in pytest output on failure)
- `[ERROR]` — JS exceptions, HTMX failures, network errors
- `[PAGE ERROR]` — uncaught exceptions that crashed the page
- `[WARNING]` — degraded behavior (missing elements, failed fetches)

**3. Check the screenshot** (saved to `/tmp/e2e-fail-<test_name>.png` on test runner)
- What did page actually show when assertion ran?
- Is UI in right state (correct URL, correct panel open)?

**4. Check app logs for 5xx**
```bash
mcp__proxmox-mcp__ssh_exec container_id=114 command="docker logs vicinitideals-api --tail 100 --since 10m"
```
- `500` → crash in route handler; stack trace here
- `422` → Pydantic validation failure; check request payload

**5. Match error type to cause**

| Symptom | Where to look |
|---|---|
| Element not found / timeout | Template changed — grep `app/templates/` for the selector |
| Wrong computed value | Engine unit tests in `tests/engines/`; run isolated |
| 500 on compute | `app/engines/cashflow.py` — check recent changes |
| HTMX swap didn't fire | Check `hx-target`, `hx-swap`, response Content-Type in logs |
| Auth redirect / 403 | Session stale — re-run `seed_e2e_user.py`, regenerate auth-state.json |

**6. Reproduce in isolation before fixing**
```bash
$env:E2E_BASE_URL="https://viciniti.deals"
uv run pytest tests/e2e/<file>.py::<test_name> -v -s
```
`-s` disables capture so console dumps print immediately.

---

Before diagnosing a UI or infrastructure regression, check `docs/Troubleshooting/` for a matching symptom guide. Current guides:

- [HTMX tables go empty](docs/Troubleshooting/htmx-table-loading.md) — opportunities page tables blank after deploy; covers 4 root causes and a debugging checklist

---

## Known Issues / Open Items

1. **X-Forwarded-For shows `192.168.1.1`**: UniFi SNAT on port forwards. Rate limiter buckets on proxy IP (global). Per-email limit still works. Accepted as-is.
2. **Organization management**: no org creation UI or invite flow yet. First registered user auto-creates "Default Organization".
3. **`docs/FINANCIAL_MODEL.md`** needs update for per-loan `_loan_pre_op_months`, trigger-chain requirements, `_PERIOD_TYPE_RANK` windowing logic.
4. **Listing jurisdiction data inaccurate**: scraped `city` values from listing sources (Crexi/LoopNet) often use metro name instead of actual jurisdiction (e.g. Gresham listings tagged "Portland"). Fix: add `jurisdiction` column to `scraped_listings`, backfill via nearest-parcel lookup using lat/lng against 446K parcels with known jurisdictions, update scraper pipeline to assign jurisdiction on ingest.

---

## Subagent Routing

Spawn subagents (Agent tool) for bulk mechanical work, scoped research, or parallel investigations. Don't spawn when parent needs reasoning for judgment call, when synthesis requires holding multiple threads in one head, or when spawn overhead dominates work.

**Pack strategic why, not just task.** Tell subagent what parent trying to decide, not only what to fetch. Subagent that knows "choosing between new column vs reusing existing field" can flag third option or surface that question wrong. Subagent told only "search for column X" cannot.

**Verify load-bearing claims, especially absences.** "No existing helper for this" = extraordinary claim — when parent plan depends on it, ask subagent to confirm against actual files (grep + read), not vibes. Surface results ≠ underlying reality.

**Pick cheapest agent that can do subtask well:**
- `Explore` (Sonnet): scoped code/file search, grep-and-summarize, file inventories. Default for research.
- `general-purpose`: open-ended cross-codebase questions, web research, multi-step lookups.
- `Plan`: design implementation approach for non-trivial change.
- `claude-code-guide`: questions about Claude Code tool itself.

If subagent realizes task needs more reasoning than its tier provides, return to parent rather than burning tokens.

**Avoid sprawl.** Batch related work into one subagent prompt rather than fanning out. Each spawn costs context-loading overhead.

Parent owns final synthesis. User instructions override these rules.

**If a Read is intercepted by the memory hook** ("File unchanged since last read"), this is not an error — it means the file content is already in context from an earlier read. Use that prior result instead of retrying.

Do NOT attempt offset/limit workarounds to bypass it — the hook fires on file path regardless of parameters. If you are a subagent without the prior read in context, retrieve cached content via `mcp__plugin_claude-mem_mcp-search__get_observations` or use `mcp__code-review-graph__get_minimal_context_tool` for the file instead.

---

## Code Search Routing

**Prefer code-review-graph MCP over Grep/Glob for codebase exploration.** The graph (2,500+ nodes, 31k edges, Tree-sitter AST) gives precise, token-efficient answers. Grep/Glob scan raw text and return noisy matches from large files.

| Task | Prefer |
|---|---|
| Find where a function is defined or called | `mcp__code-review-graph__query_graph_tool` |
| Find files affected by a change | `mcp__code-review-graph__get_impact_radius_tool` |
| Semantic search ("where is DSCR calculated?") | `mcp__code-review-graph__semantic_search_nodes_tool` |
| Trace call paths / dependencies | `mcp__code-review-graph__traverse_graph_tool` |
| Understand what a file imports / exports | `mcp__code-review-graph__get_minimal_context_tool` |
| Find large or complex functions | `mcp__code-review-graph__find_large_functions_tool` |

Use Grep/Glob only when: searching template/HTML files (not parsed by Tree-sitter), doing exact string matches in non-Python files, searching for external library usage patterns (`requests.get`, `urllib`, `open()`— external packages not in graph), or when graph returns no results. Always try graph first.

For route/function discovery in a known file, use `query_graph_tool` (lists all functions as nodes) — faster and cheaper than regex grep.

**Skip graph immediately** for UI/template concepts — go straight to Grep on `app/templates/`: drawer, slider, modal, panel, button, checkbox, badge, pill, HTMX attribute (`hx-`, `hx_`), Jinja2 variable/block names. These live in `.html` files the graph does not index.

**Skip `smart_outline` for `.txt`, `.html`, and docs files** — claude-mem's Tree-sitter parser has no grammar for plain text or HTML. Use `Read` directly on anything in `docs/` or `app/templates/`. Use code-review-graph MCP for template searches instead.