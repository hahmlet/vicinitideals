# Claude AI Assistant Instructions — vicinitideals

## Product Overview

Self-hosted real estate platform for an Oregon investment and development team.
**The repo holds two products.** They share infrastructure, a database, and auth;
they do not share code. Know which one you are working on before you edit.

1. **Deal underwriting** (`app/`) — full financial model builder: Uses, Sources,
   debt carry (4 types), operating cash flow, equity waterfall, draw schedule,
   sensitivity analysis, Excel export. Plus deal intelligence: Crexi/LoopNet
   listing ingest, brokers, dedup, KNN comps.
2. **FLATS** (`flats/`) — *Fitment, Land, and Tolerance Screening.* Answers one
   question at county scale: can a fixed-dimension, factory-built 4-unit attached
   townhome be legally and physically placed on this lot, with its parking and
   vehicle access? Emits GREEN / REVIEW / RED with continuous slack and
   binding-constraint attribution. See
   [Lot Analysis/FLATS_PLAN.md](Lot%20Analysis/FLATS_PLAN.md).

> **The financial engine is off limits to FLATS work.** A commit may not touch
> `flats/` and `app/engines/` (or the capital/deal models, their schemas, their
> routers, or `tests/engines/`) at the same time, and nothing under `flats/` may
> import `app.engines`. `scripts/check_flats_firewall.py` enforces both and runs
> in CI. The seam is one-directional: FLATS produces, finance consumes. If a
> change seems to need both, it is two changes.

> **FLATS is not the decommissioned parcel subsystem.** The old `parcels` table
> was dropped in migration 0113 and is not coming back. FLATS uses its own
> `flats.*` Postgres schema with a different data model, and the Archive section
> of [docs/DATA_MODEL.md](docs/DATA_MODEL.md) does not describe it.

**Live URL**: `https://viciniti.deals` (Cloudflare DNS, Let's Encrypt wildcard
cert on NGINX Proxy Manager, LXC 109)

**Tech stack**: FastAPI 0.110+ (Python 3.12+) · SQLAlchemy 2.0 async + asyncpg ·
Alembic · Celery 5.3+ (queues: default, analysis) · Redis · PostgreSQL 16 ·
Jinja2 + HTMX 2.0.9 · pyxirr · openpyxl · Pydantic v2 · httpx · curl-cffi ·
uv · Docker Compose · Ruff

---

## Infrastructure

| Component | Location |
|---|---|
| App (all Docker containers) | VM 114 (`192.168.1.28:8001`) — FastAPI, Celery workers, PostgreSQL, Redis |
| NGINX Proxy Manager | LXC 109 (`192.168.1.195`) → VM 114:8001 |
| MCP servers | LXC 112 |
| Resend (email) | External; API key in VM 114 `.env` only |

Docker service names and the deploy pipeline diagram are in
[docs/PROJECT_OVERVIEW.md §4](docs/PROJECT_OVERVIEW.md). Proxmox host docs live in
`../personalproxmox/documentation/MCP/`.

---

## Deploy Workflow

**IMPORTANT: a task is NOT complete until deployed to production.** Agents manage
100% of deploys. Unless told otherwise, always deploy after commit+push — no
permission needed. "Done" means live on `viciniti.deals`, not committed locally.

**Deploy steps** (all three required):
1. `git push origin main`
2. `mcp__proxmox-mcp__ssh_exec container_id=114 command="bash /root/deploy-vicinitideals.sh"`
3. Verify smoke checks pass in the deploy output

The script runs: `git pull → docker compose build → alembic upgrade head → docker compose up -d → health check`.
Manual fallback if MCP is unavailable: `ssh root@192.168.1.28 "bash /root/deploy-vicinitideals.sh"`.

---

## Working in This Repo

### Branches and worktrees

The primary checkout stays on `main`. Bug fixes, small tweaks, doc edits and
config changes go straight on `main`. New features, refactors and risky changes
go in a worktree under `../vicinitideals-worktrees/<slug>/` — **confirm with the
user first** before creating one. One branch = one shippable slice = one
worktree. Setup and cleanup commands: [docs/ops/worktrees.md](docs/ops/worktrees.md).

### End-of-session checklist

When the user indicates the session is ending:

1. **Undone items** — anything discussed but not finished, plus follow-ups (open
   questions, deferred fixes, "later" items).
2. **Completed work summary** — commits (branch + SHA), pushes, deploys, decisions
   not captured in commit messages.
3. **Worktree trim** — remove a merged, finished worktree; leave work in progress;
   ask if unsure.
4. **Schema doc updates** — only when engine behaviour, data model or architecture
   changed: [docs/FINANCIAL_MODEL.md](docs/FINANCIAL_MODEL.md) (engine math),
   [docs/DATA_MODEL.md](docs/DATA_MODEL.md) (ORM), [docs/MARKET_MODEL.md](docs/MARKET_MODEL.md),
   [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) (architecture).

---

## Where Things Are

Top level: `app/` (underwriting product), `flats/` (FLATS), `tests/`,
`flats/tests/`, `alembic/versions/`, `scripts/` (ops utilities incl. the
firewall check), `Lot Analysis/` (FLATS plan + the quadfit predecessor), `docs/`.

The full annotated tree, the financial-engine concepts (carry types, per-loan
windows, auto-sizing, DSCR cap, source routing), the milestone trigger-chain
model, the entity hierarchy and the auth system are in
[docs/PROJECT_OVERVIEW.md §6–8](docs/PROJECT_OVERVIEW.md). Read the relevant
section before editing an engine, a model or a router.

Two facts that bite often enough to keep here:

- **Trigger chains**: milestones resolve dates via `trigger_milestone_id`
  chain-walk; without them the engine falls back to `OperationalInputs.*_months`
  scalars (NULL → 1-month fallback).
- The old `Deal` ORM class is now `Scenario`; `Deal → Opportunity → Project →
  Milestones` and `Scenario → UseLines, CapitalModules, IncomeStreams, …`.

---

## Testing

Full reference: [docs/TESTING.md](docs/TESTING.md) — test DB setup, markers, the
Phase B regression, CI gates, and the E2E diagnostic runbook.

```bash
uv run pytest tests/ -q -m "unit" --ignore=tests/e2e     # Unit tests only
uv run pytest flats/tests -q -n auto                       # FLATS (no DB needed)
uv run pytest tests/ -q --ignore=tests/e2e                # Unit + integration
uv run pytest tests/e2e/ -q -m e2e                        # E2E (needs running app)
uv run ruff check app/ tests/ flats/ scripts/               # Lint (same scope as CI)
```

- **`-n auto` is for `flats/tests` only.** The `tests/` suites share one Postgres
  database and `TRUNCATE` between tests; parallel workers would wipe each other's
  rows. There is deliberately no `-n` in `pyproject.toml` `addopts`.
- **The FLATS corpus census** (`qualified()`, ~14 s, ~26 tests) is 63% of that
  suite's runtime. Before adding a census test or caching the census, read the
  three rules in [docs/TESTING.md](docs/TESTING.md#the-flats-corpus-census--read-before-touching-it).
- Don't mix unit and E2E tests in one Windows pytest run (event-loop policy).

### Test creation requirement

**Every plan ends with a test validation step.** Before marking a task done:
review the existing tests for the changed area and update any the change
invalidated; if nothing exercises the new behaviour, write it —
`app/engines/` → unit test in `tests/engines/`; `app/api/routers/` → integration
test in `tests/api/`; new or changed UI → Playwright E2E in `tests/e2e/` (UI
flows use the browser, not API shortcuts); bug fix → the test that would have
caught it. Then run only the E2E file(s) covering the change against
`E2E_BASE_URL=https://viciniti.deals`, not the whole suite, and confirm green.

The stop hook runs `pytest tests/ --ignore=tests/e2e` when `app/` changed (3
attempts, then escalates). Bypass mid-refactor: `New-Item .claude/state/skip_verify.json`.

CI is behind production: a red CI is the only thing between a bad push and an
outage. Read CI before calling a commit clean.

---

## Coding Conventions

- **Python 3.12+**, `from __future__ import annotations` where needed
- **Decimal for money** — never `float` for financial values
- **SQLAlchemy 2.0 style**: `Mapped[type]`, `mapped_column()`, async sessions
- **Pydantic v2** for schemas and settings
- **Ruff** for linting (`uv run ruff check app/ tests/ flats/ scripts/` — the CI scope)
- **uv** as package manager (not pip)
- **HTMX** for UI — server renders HTML partials, no client-side JS framework
- Module docstrings describe purpose and entity relationships
- Enums are `str, enum.Enum` subclasses for JSON serialization

---

## Database Safety

- PostgreSQL data lives in the Docker named volume `re-modeling-postgres-data`
- **NEVER run `docker compose down -v`** — deletes the volume and all data
- DB name and user remain `re_modeling` (intentional legacy name)
- Alembic migrations run automatically during deploy
- **Document-room files** live on disk at `/app/data/doc_room/` (bind mount), NOT
  in Postgres; the `documents` table holds only metadata. Back up both.

## Critical Do-Nots

- **NEVER use `sudo`** — use the Proxmox MCP for system operations on VMs/LXCs
- **NEVER commit credentials** (.env, API keys, secrets)
- **NEVER hardcode infrastructure IPs/ports** — reference docs or config
- **NEVER run `docker compose down -v`**
- **NEVER modify production data directly** — use migration or one-shot scripts

---

## Market Coverage Policy

**The entire state of Oregon is the acquisition market (since 2026-07-28).**
Portland included; paid data spend allowed anywhere in Oregon. Policy ≠ data
coverage: quadfit and the parcel inventory currently cover Multnomah + Clackamas;
extending is a data task, not a policy blocker.

---

## Troubleshooting and Known Issues

Before diagnosing a UI or infrastructure regression, check
[docs/Troubleshooting/](docs/Troubleshooting/) for a matching symptom guide —
[e2e-failed-test.md](docs/Troubleshooting/e2e-failed-test.md) is the runbook for
any failed E2E test. Accepted limitations and deliberately-deferred fixes
(including the unguarded `compute_cash_flows` race) are in
[docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md). Human-action items are in
[docs/HUMAN_TODO.md](docs/HUMAN_TODO.md).

---

## Subagent Routing

Spawn subagents for bulk mechanical work, scoped research, or parallel
investigations — anything whose raw output (file reads, search results, test
logs) does not need to sit in the main conversation. Don't spawn when the parent
needs the reasoning for a judgment call, when synthesis means holding several
threads in one head, or when spawn overhead dominates the work.

- **Pack the strategic why**, not just the task — a subagent that knows what
  decision the parent is weighing can flag a third option.
- **Verify load-bearing claims, especially absences.** "No existing helper for
  this" is an extraordinary claim; ask for grep + read confirmation.
- **Cheapest agent that can do it well**: `Explore` (Sonnet) for scoped search
  and file inventories — the default for research; `general-purpose` for
  open-ended cross-codebase questions; `Plan` for design; `claude-code-guide`
  for questions about Claude Code itself.
- **Avoid sprawl** — batch related work into one prompt. Parent owns synthesis.

If a Read is intercepted by the memory hook ("File unchanged since last read"),
the content is already in context from an earlier read — use it; don't retry
with offset/limit.

---

## Code Search Routing

**Prefer the code-review-graph MCP over Grep/Glob for Python exploration** —
`query_graph_tool` (definitions, callers), `get_impact_radius_tool` (affected
files), `semantic_search_nodes_tool` ("where is DSCR calculated?"),
`traverse_graph_tool` (call paths), `get_minimal_context_tool` (a file's
imports/exports). Try the graph first.

Use Grep/Glob when: searching templates/HTML, exact strings in non-Python files,
external-library usage patterns, or the graph returns nothing. **Skip the graph
entirely** for UI/template concepts (drawer, slider, modal, panel, `hx-`
attributes, Jinja2 names) — go straight to Grep on `app/templates/`. Use `Read`
directly on `docs/` and `app/templates/` (no Tree-sitter grammar for text/HTML).
