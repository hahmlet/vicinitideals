# Agent Guide: Migrate & Rebrand + DevOps Enhancement

This is the primary reference document for an agent executing the two-epic work plan tracked in Plane (project: REAL).

**Reading order:** Read this entire document before touching any file. Then pull the Plane tasks and execute them in order. Task descriptions contain the specific actions — this document contains the rationale and cross-cutting rules.

---

## Part 1: Migrate & Rebrand (ketch-media-ai → vicinitideals)

### Context

The re-modeling FastAPI app was incorrectly placed in `ketch-media-ai` early in development. It belongs in `vicinitideals` — that repo already has wireframes and design artifacts for the same product. `ketch-media-ai` should be reserved for AI/MCP tooling.

**Scope:**
- Move `re-modeling/` code from `ketch-media-ai` to `vicinitideals` (root-level layout — no subdirectory)
- **Rebrand:** rename Python package `vicinitideals` → `vicinitideals`, Docker containers, config vars
- **Do NOT rename:** PostgreSQL database/user (`vicinitideals`) or Docker volume (`re-modeling-postgres-data`) — risky, invisible to users
- Remove all Appsmith artifacts from both repos (Appsmith is fully deprecated)
- Update VM 114 deploy pipeline to pull from `vicinitideals`
- No git history preservation — clean copy is fine

**Sequencing: migrate first, then DevOps work (Part 2).**

The DevOps work creates ~15 new files and modifies ~10 existing ones. Doing it in ketch-media-ai first means every path gets written twice. Migrate first (mechanical, no behavior change), then invest the DevOps work in the right repo.

---

### Repo state at migration time

**ketch-media-ai — what moves vs stays:**

| Item | Path | Action |
|------|------|--------|
| MCP servers | `mcp-servers/` | STAYS |
| Copilot skills | `.github/skills/` | STAYS (except appsmith-skill) |
| Skill configs | `configs/` | STAYS |
| Skill scripts | `scripts/` | STAYS (except appsmith scripts) |
| skill-seekers submodule | `cloned-repos/skill-seekers/` | STAYS |
| Generated skill output | `output-generated/` | STAYS (except appsmith-docs-curated) |
| CLAUDE.md | `CLAUDE.md` | STAYS |
| re-modeling app | `re-modeling/` | **MOVES to vicinitideals root** |
| re-modeling CI workflow | `.github/workflows/re-modeling-ci.yml` | **DELETE** (recreated in vicinitideals) |
| Debug script | `debug_sizing.py` | **DELETE** (imports vicinitideals) |
| Appsmith skill | `.github/skills/appsmith-skill/` | **DELETE** (already staged) |
| Appsmith doc scraper | `scripts/scrape_appsmith_docs_direct.py` | **DELETE** |
| Appsmith skill builder | `scripts/build_appsmith_skill_from_corpus.py` | **DELETE** |
| Appsmith generated docs | `output-generated/appsmith-docs-curated/` | **DELETE** |

**vicinitideals — current state:**

| Item | Path | Action |
|------|------|--------|
| Appsmith config | `application.json`, `metadata.json`, `theme.json`, `pages/` | **DELETE** |
| Wireframes | `wireframes/` | Move to `docs/wireframes/` |
| README | `README.md` | **REPLACE** with new project README |
| Misplaced agent | `.github/agents/Programmer.agent.md` | **DELETE** |

---

### Target directory layout (vicinitideals after migration)

```
vicinitideals/
├── vicinitideals/          ← from re-modeling/vicinitideals/ (renamed)
├── alembic/                ← from re-modeling/alembic/
├── tests/                  ← from re-modeling/tests/
├── tools/                  ← from re-modeling/tools/
├── data/                   ← from re-modeling/data/
├── docs/
│   ├── wireframes/         ← moved from vicinitideals root
│   ├── security/
│   ├── ops/
│   ├── verification/
│   ├── api/
│   ├── testing-strategy.md
│   ├── ui-plan.md
│   ├── PROJECT_OVERVIEW.md
│   └── devops-migration-plan.md   ← this file
├── .github/
│   └── workflows/
│       └── ci.yml          ← adapted from re-modeling-ci.yml
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── alembic.ini
├── .env.example
├── .gitignore
├── CLAUDE.md               ← new, vicinitideals-specific
├── README.md               ← new project README
└── DEPLOYMENT_PROMOTION_GATES.md
```

---

### Package rebrand map (`vicinitideals` → `vicinitideals`)

**Before executing:** Run the audit first:
```bash
grep -r "vicinitideals\|re-modeling" re-modeling/ --include="*.py" --include="*.toml" --include="*.yml" --include="*.ini" --include="*.md" -l
```
Compare the output against this map. If new files appear that aren't listed here, add their patterns before proceeding.

| Category | Old | New |
|----------|-----|-----|
| Package directory | `vicinitideals/` | `vicinitideals/` |
| All Python imports | `from vicinitideals.xxx` / `import vicinitideals` | `from vicinitideals.xxx` / `import vicinitideals` |
| pyproject.toml name | `name = "re-modeling"` | `name = "vicinitideals"` |
| pyproject.toml build | `packages = ["vicinitideals"]` | `packages = ["vicinitideals"]` |
| Dockerfile COPY | `COPY vicinitideals/ vicinitideals/` | `COPY vicinitideals/ vicinitideals/` |
| Dockerfile uvicorn CMD | `vicinitideals.api.main:app` | `vicinitideals.api.main:app` |
| Docker container names | `re-modeling-api`, `re-modeling-worker-*` | `vicinitideals-api`, `vicinitideals-worker-*` |
| Docker network | `re-modeling-network` (external: true) | `vicinitideals-network` (managed bridge) |
| Celery app flag | `-A vicinitideals.tasks.celery_app` | `-A vicinitideals.tasks.celery_app` |
| Config env var | `RE_MODELING_API_KEY` | `VICINITIDEALS_API_KEY` |
| Config attribute | `vicinitideals_api_key` | `vicinitideals_api_key` |
| Alembic env.py | `from vicinitideals.models import Base` | `from vicinitideals.models import Base` |
| Test imports | `from vicinitideals.xxx` | `from vicinitideals.xxx` |
| Coverage config | `source = ["vicinitideals"]` | `source = ["vicinitideals"]` |
| Ruff per-file-ignores | `vicinitideals/models/*.py` | `vicinitideals/models/*.py` |
| main.py `_is_ui_path` | any `vicinitideals` string references | `vicinitideals` |

**NOT renamed (intentionally):**

| What | Stays as | Why |
|------|----------|-----|
| Docker volume | `re-modeling-postgres-data` | Renaming loses data unless manually copied |
| PostgreSQL database | `vicinitideals` | Requires dump/restore, high risk, invisible to users |
| PostgreSQL user | `vicinitideals` | Same |
| DATABASE_URL in .env | `postgresql+asyncpg://vicinitideals:...@postgres:5432/vicinitideals` | Matches unchanged DB/user |
| Alembic migration files | `0001_initial.py` etc. | Renaming breaks the chain |

---

### Appsmith cleanup (in copied files)

Remove these from re-modeling files when copying:

| File | What to remove/change |
|------|-----------------------|
| `docker-compose.appsmith.yml` | Delete entire file |
| `docker-compose.yml` | Change `re-modeling-network: external: true` to `vicinitideals-network: driver: bridge` |
| `config.py` | Remove `appsmith_disable_telemetry: bool = True` |
| `docs/ops/release-checklist.md` | Remove "Appsmith Gate" section |
| `docs/security/hardening-backlog.md` | Remove P1-1 Appsmith SSO section |
| `docs/ops/observability-slo-dashboard.md` | Remove Appsmith widget spec references |
| `docs/verification/qa-test-matrix.md` | Remove Appsmith exclusion note |
| `.env.example` | Remove `APPSMITH_*` vars |
| `main.py` | Remove `/splash` from `_UI_PATH_PREFIXES` (splash is deprecated with auth work) |

---

### New files to create in vicinitideals

**`CLAUDE.md`** — Create at repo root:
```markdown
# Claude AI Assistant Instructions - vicinitideals

**Purpose**: Context for Claude when working on the vicinitideals real estate financial modeling platform.

## Quick Context

- **Product**: Self-hosted real estate deal modeling platform (FastAPI + HTMX + Celery)
- **Live domain**: `deals.ketch.media` (NGINX on LXC 109 proxies to VM 114 port 8001)
- **Deploy**: `git push origin main` → VM 114 `/root/deploy-vicinitideals.sh` auto-runs
- **Docs**: See `docs/` for full project documentation
- **Infrastructure docs**: `../personalproxmox/documentation/MCP/` for Proxmox/networking

## Key Directories

- `vicinitideals/` — Python package (FastAPI app, engines, scrapers, tasks, models)
- `vicinitideals/api/routers/ui.py` — HTMX UI routes (~6800 lines, most active file)
- `vicinitideals/engines/` — Financial computation (cashflow, draw_schedule, waterfall, etc.)
- `vicinitideals/models/` — SQLAlchemy ORM models
- `alembic/` — Database migrations
- `tests/` — Unit + integration tests
- `docs/` — Project documentation

## Tech Stack

FastAPI 0.110+ · SQLAlchemy 2.0 async · asyncpg · Alembic · Celery 5.3+ · Redis · PostgreSQL · Jinja2 + HTMX · pyxirr · openpyxl

## Deploy Workflow

```bash
git push origin main
# VM 114 runs /root/deploy-vicinitideals.sh:
# git pull → docker compose build → alembic upgrade head → docker compose up -d → health check
```

## Database Safety

- PostgreSQL data lives in Docker named volume `re-modeling-postgres-data`
- **NEVER run `docker compose down -v`** — this deletes the volume and all data
- DB name and user remain `vicinitideals` (intentional — renaming requires dump/restore)

## Critical Do-Nots

- **NEVER use `sudo`** — use Proxmox MCP for system operations
- **NEVER commit credentials** (.env, API keys, secrets)
- **NEVER hardcode infrastructure IPs/ports** — reference docs
- **NEVER run `docker compose down -v`** — destroys database
```

**`.gitignore`**:
```
# Python
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
*.egg-info/
dist/

# Environment
.env
.venv/

# IDE
.vscode/
.idea/

# Data (large/generated)
data/gis_cache/*.geojson

# Claude Code
.claude/
```

**`README.md`** — Minimal project readme pointing to docs/PROJECT_OVERVIEW.md.

---

### docker-compose.yml network section (after migration)

Change this (Appsmith-created external network):
```yaml
networks:
  re-modeling-network:
    external: true
```

To this (managed bridge network):
```yaml
networks:
  vicinitideals-network:
    driver: bridge
```

And update every service's `networks:` reference from `re-modeling-network` to `vicinitideals-network`.

---

### CI workflow (`.github/workflows/ci.yml`)

Adapt from `re-modeling-ci.yml`:
- Remove `paths:` filter — vicinitideals is a single-project repo, every push runs CI
- Remove `working-directory: re-modeling` from all job steps
- Rename workflow: `re-modeling CI` → `vicinitideals CI`
- Update module paths: `vicinitideals.*` → `vicinitideals.*`

The full two-tier CI spec is in Part 2, Phase 2 of this document. Implement the two-tier structure during the DevOps phase, not during migration. For migration, just make the existing CI work in the new repo.

---

### VM 114 cutover steps

**Before cutover (no downtime):**
1. `git clone https://github.com/hahmlet/vicinitideals.git /root/stacks/vicinitideals` on VM 114
2. `cp /root/stacks/ketch-media-ai/re-modeling/.env /root/stacks/vicinitideals/.env`
3. Edit `.env`: rename `RE_MODELING_API_KEY` → `VICINITIDEALS_API_KEY` (same value), remove `APPSMITH_*` vars
4. Keep `DATABASE_URL` unchanged (still references `vicinitideals` DB)
5. Write new deploy script `/root/deploy-vicinitideals.sh`

**Cutover (~5 min downtime):**
1. `pg_dump` backup: `docker exec re-modeling-postgres pg_dump -U vicinitideals vicinitideals > /root/backup-pre-migration.sql`
2. `cd /root/stacks/ketch-media-ai/re-modeling && docker compose down`
3. `docker network rm re-modeling-network`
4. `cd /root/stacks/vicinitideals && docker compose up -d`
5. Verify: `curl -s http://192.168.1.28:8001/health`

---

### Verification checklist (post-migration)

- [ ] `curl -s http://192.168.1.28:8001/health` → `{"code": "ok", ...}`
- [ ] `deals.ketch.media` loads in browser, data intact
- [ ] `docker compose ps` (in vicinitideals) → all 6 services healthy
- [ ] `pytest tests/ -q` passes in the new repo
- [ ] Push a commit → vicinitideals CI triggers and passes
- [ ] ketch-media-ai CI no longer triggers on re-modeling paths
- [ ] `docker volume ls | grep re-modeling-postgres` → volume exists with data

---

## Part 2: DevOps Enhancement (Playwright, Auth & Security)

**Execute in vicinitideals AFTER migration is complete and verified.**

### Phase overview

| Phase | What | Why |
|-------|------|-----|
| 1 | Playwright E2E tests | UI regression safety net — currently zero UI test coverage |
| 1B | Native email/password auth | Remove the placeholder user-selector/cookie pattern |
| 2 | Two-tier CI gates | Light (~2 min) vs full (~8 min) based on scope detection |
| 3 | BugSink error tracking | Catch production errors without Sentry's 20-container overhead |
| 4 | Security scanning (Trivy + Semgrep) | CVE + SAST in CI before deploy |
| 5 | Agent feedback loop | Post-deploy smoke test + auto-ticket creation from BugSink errors |

---

### Phase 1: Playwright E2E Tests

**Goal:** Catch regressions in HTMX UI flows that unit/integration tests miss.

**New files:**
```
tests/e2e/
├── __init__.py
├── conftest.py          ← browser fixture, base_url, seed/teardown
├── helpers.py           ← wait_for_htmx_response(), wait_for_selector_stable()
├── seed_e2e_data.py     ← creates org + deal via API calls before tests run
├── test_smoke.py        ← 8 smoke tests (listed below)
└── test_model_builder.py ← 6 model builder tests (listed below)
```

**pyproject.toml additions:**
```toml
[project.optional-dependencies]
e2e = [
    "playwright>=1.44",
    "pytest-playwright>=0.5",
]

[tool.pytest.ini_options]
# add to existing markers list:
markers = [
    ...,
    "e2e: Playwright browser tests — require running docker-compose stack",
]
```

**HTMX wait strategy (critical — document this in helpers.py):**
- ALWAYS use `page.wait_for_response(lambda r: "/api/" in r.url)` after triggering HTMX
- ALWAYS use `page.wait_for_selector("selector", state="visible")` after swap
- NEVER use `page.wait_for_timeout()` — this is a time bomb
- For form submissions: wait for the response AND the resulting DOM update

**`tests/e2e/conftest.py` structure:**
```python
import pytest
from playwright.sync_api import sync_playwright, Browser, Page

BASE_URL = "http://localhost:8001"  # local docker-compose

@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()

@pytest.fixture
def page(browser):
    ctx = browser.new_context(base_url=BASE_URL)
    pg = ctx.new_page()
    yield pg
    ctx.close()

@pytest.fixture(scope="session", autouse=True)
def seed_data():
    """Create a test org + deal before e2e suite runs. Teardown after."""
    # Call API to create seed data, store IDs in session state
    # Uses same patterns as tests/conftest.py seed helpers
    ...
```

**`test_smoke.py` — 8 tests:**
1. `test_health_endpoint` — GET /health → 200
2. `test_listings_page_loads` — /listings renders table
3. `test_parcels_page_loads` — /parcels renders results
4. `test_deals_page_loads` — /deals renders list
5. `test_deal_detail_page_loads` — /models/{deal_id} renders model builder
6. `test_nav_links_work` — nav links don't 404
7. `test_htmx_uses_module_loads` — click Uses tab → HTMX swap visible
8. `test_htmx_sources_module_loads` — click Sources tab → HTMX swap visible

**`test_model_builder.py` — 6 tests:**
1. `test_add_use_line` — fill form, submit, new row appears
2. `test_add_capital_source` — fill source form, submit, source appears
3. `test_save_scenario_name` — edit name field, blur, HTMX saves it
4. `test_run_cashflow` — click Run → cashflow table renders with rows
5. `test_draw_schedule_renders` — draw schedule tab shows Gantt
6. `test_excel_export_downloads` — export button returns a .xlsx file

**CI integration (add to ci.yml):**
```yaml
e2e:
  runs-on: ubuntu-latest
  needs: [test]   # only run after unit/integration pass
  steps:
    - uses: actions/checkout@v4
    - run: docker compose up -d
    - run: docker compose exec api uv run playwright install chromium
    - run: docker compose exec api uv run pytest tests/e2e/ -m e2e -q
    - run: docker compose down
```

---

### Phase 1B: Native Email/Password Auth

**Goal:** Replace the placeholder `vd_user_id` cookie + splash user-selector with real bcrypt passwords and signed session cookies.

**New dependencies (add to `api` and `dev` groups in pyproject.toml):**
```toml
"bcrypt>=4.0",
# itsdangerous is already a Starlette transitive dep — no need to add
```

**New files:**
- `vicinitideals/api/auth.py` — session helpers
- `vicinitideals/api/routers/auth_routes.py` — login/register/logout/profile routes
- `vicinitideals/templates/login.html`
- `vicinitideals/templates/register.html`
- `vicinitideals/templates/profile.html`

**`vicinitideals/api/auth.py`:**
```python
"""Session cookie auth using itsdangerous signed cookies + bcrypt passwords."""

import bcrypt
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from fastapi import Request, HTTPException
from vicinitideals.config import settings

_signer = URLSafeTimedSerializer(settings.session_secret_key)
COOKIE_NAME = "vd_session"
SESSION_MAX_AGE = 86400 * 7  # 7 days

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def create_session_token(user_id: str) -> str:
    return _signer.dumps(user_id)

def decode_session_token(token: str, max_age: int = SESSION_MAX_AGE) -> str | None:
    try:
        return _signer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

def get_current_user_id(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    return decode_session_token(token)
```

**`config.py` additions:**
```python
session_secret_key: str = "changeme-session-secret"
bugsink_dsn: str = ""  # set in Phase 3
```

**User model additions (`vicinitideals/models/org.py`):**
Add to the existing `User` mapped class:
```python
email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
password_hash: Mapped[str] = mapped_column(String(128), nullable=False)
is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
```
Create an Alembic migration for this: `alembic revision --autogenerate -m "add_auth_fields_to_user"`

**Auth middleware in `main.py`:**
Add to `create_app()` before the API key middleware:
```python
from vicinitideals.api.auth import get_current_user_id, COOKIE_NAME
from vicinitideals.models.org import User

@app.middleware("http")
async def attach_current_user(request: Request, call_next):
    user_id = get_current_user_id(request)
    if user_id:
        async with get_session() as session:
            user = await session.get(User, user_id)
            request.state.user = user
    else:
        request.state.user = None
    return await call_next(request)
```

**Router (`auth_routes.py`) endpoints:**
- `GET /login` → render login.html
- `POST /login` → verify credentials, set signed cookie, redirect to /deals
- `GET /register` → render register.html
- `POST /register` → create user, set signed cookie, redirect to /deals
- `POST /logout` → delete cookie, redirect to /login
- `GET /profile` → render profile.html (requires auth)
- `POST /profile` → update name/email/password

**Remove from `ui.py`:**
- The `_get_user()` helper (all ~57 call sites in ui.py must switch to `request.state.user`)
- Routes: `GET /splash`, `POST /splash/select`
- The `vd_user_id` cookie reads throughout ui.py

**Protected routes:** Any route that currently calls `_get_user()` should instead do:
```python
user = request.state.user
if user is None:
    return RedirectResponse("/login", status_code=302)
```

---

### Phase 2: Two-Tier CI Gates

**Goal:** Fast feedback on every push (~2 min light gate), full coverage on risky changes (~8 min).

**CI file:** `.github/workflows/ci.yml`

**Tier 1 — Light gate (always runs):**
- ruff lint
- pytest unit tests only (`-m unit`)
- ~2 min

**Tier 2 — Full gate (conditional):**
- All unit + integration tests
- Playwright E2E tests
- Trivy scan
- Semgrep scan
- ~8 min

**Scope detection logic (in ci.yml):**
```yaml
- name: Detect scope
  id: scope
  run: |
    CHANGED=$(git diff --name-only HEAD~1 HEAD)
    COMMIT_MSG=$(git log -1 --format=%s)
    FULL=false
    
    # Manual overrides
    if echo "$COMMIT_MSG" | grep -q '\[full\]'; then FULL=true; fi
    if echo "$COMMIT_MSG" | grep -q '\[light\]'; then FULL=false; fi
    
    # Auto-detect: templates, CSS, routers, engines → full
    if echo "$CHANGED" | grep -qE 'templates/|static/|routers/|engines/'; then FULL=true; fi
    
    # >10 files changed → full
    if [ $(echo "$CHANGED" | wc -l) -gt 10 ]; then FULL=true; fi
    
    # workflow_dispatch with input
    if [ "${{ github.event.inputs.tier }}" = "full" ]; then FULL=true; fi
    
    echo "run_full=$FULL" >> $GITHUB_OUTPUT
```

**Full ci.yml structure:**
```yaml
name: vicinitideals CI
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:
    inputs:
      tier:
        description: 'CI tier'
        required: false
        default: 'auto'
        type: choice
        options: [auto, light, full]

jobs:
  scope:
    runs-on: ubuntu-latest
    outputs:
      run_full: ${{ steps.scope.outputs.run_full }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2
      - name: Detect scope
        id: scope
        run: |
          # ... scope detection script above ...

  light:
    runs-on: ubuntu-latest
    needs: scope
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra dev
      - run: uv run ruff check vicinitideals/
      - run: uv run pytest tests/ -m unit -q

  full:
    runs-on: ubuntu-latest
    needs: [scope, light]
    if: needs.scope.outputs.run_full == 'true'
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv sync --extra dev --extra e2e
      - run: uv run pytest tests/ -m "unit or integration" -q
      - name: Playwright E2E
        run: |
          docker compose up -d
          sleep 10
          uv run playwright install chromium
          uv run pytest tests/e2e/ -m e2e -q
          docker compose down
      - name: Trivy scan
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          exit-code: '1'
          severity: 'CRITICAL'
      - name: Semgrep
        uses: returntocorp/semgrep-action@v1
        with:
          config: "p/python p/owasp-top-ten"
```

---

### Phase 3: BugSink Error Tracking

**Goal:** Catch production errors server-side. BugSink is self-hosted, Sentry-SDK compatible, runs in a single process (vs Sentry's 20+ containers).

**Infrastructure:**
- New Proxmox LXC (Ubuntu 22.04, 512MB RAM, 4GB disk)
- Install: `pip install bugsink` → `bugsink-manage migrate` → systemd service
- NGINX proxy: `bugs.ketch.media` → LXC IP:8000
- BugSink project → copy DSN

**`vicinitideals/sentry_setup.py`:**
```python
"""Initialize Sentry-compatible error tracking (BugSink)."""
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

def init_sentry(dsn: str) -> None:
    if not dsn:
        return  # skip in dev/test if DSN not set
    sentry_sdk.init(
        dsn=dsn,
        integrations=[
            FastApiIntegration(),
            SqlalchemyIntegration(),
            CeleryIntegration(),
        ],
        traces_sample_rate=0.1,
    )
```

**`config.py` addition:**
```python
bugsink_dsn: str = ""
```

**Wire into `main.py`** (`create_app()`, first thing in the function body):
```python
from vicinitideals.sentry_setup import init_sentry
init_sentry(settings.bugsink_dsn)
```

**`pyproject.toml` addition** (api and worker groups):
```toml
"sentry-sdk[fastapi]>=2.0",
```

**`scripts/check_bugsink_errors.py`** — agent-callable script:
```python
"""Query BugSink API for unresolved errors. Used by agent feedback loop."""
import httpx, sys
from vicinitideals.config import settings

def main():
    # GET https://bugs.ketch.media/api/issues/?resolved=false
    # Print count + titles
    # Exit 1 if any critical errors
    ...
```

---

### Phase 4: Security Scanning (Trivy + Semgrep)

**Goal:** CVE scanning + SAST in CI. Gate on CRITICAL findings.

**Tools:**
- **Trivy** — scans container image, Python dependencies (requirements/pyproject), and Dockerfile for CVEs
- **Semgrep Community** — SAST for Python: `p/python` + `p/owasp-top-ten` rulesets

Both are wired into the Full CI gate (Phase 2). No additional config files needed beyond what's in the CI workflow.

**Trivy config (add `trivy.yaml` to repo root):**
```yaml
scan:
  skip-dirs:
    - ".venv"
    - "data/gis_cache"
severity:
  - CRITICAL
  - HIGH
exit-code: 1
```

**Semgrep config (add `.semgrep.yml` to repo root):**
```yaml
rules: []  # use Semgrep-managed rulesets from CI action
```

**Trivy to run against:**
1. `fs .` — filesystem scan (dependencies, IaC, Dockerfile)
2. Docker image after build: `trivy image vicinitideals-api:latest`

**False positive suppression:** Add `# trivy:ignore:CVE-YYYY-XXXXX` comments inline for confirmed false positives. Document the reason.

---

### Phase 5: Agent Feedback Loop

**Goal:** After every deploy, run smoke tests automatically and create Plane work items for any errors caught by BugSink.

**`scripts/post_deploy_smoke.py`** — runs after `docker compose up -d` in deploy script:
```python
"""Post-deploy smoke checks. Called by deploy-vicinitideals.sh after containers start."""
import httpx, sys, time

BASE = "http://localhost:8001"

CHECKS = [
    ("GET", "/health", 200),
    ("GET", "/deals", 200),
    ("GET", "/listings", 200),
]

def main():
    time.sleep(5)  # wait for startup
    failures = []
    for method, path, expected in CHECKS:
        r = httpx.request(method, BASE + path, timeout=10)
        if r.status_code != expected:
            failures.append(f"{method} {path} → {r.status_code} (expected {expected})")
    
    if failures:
        print("SMOKE FAILURES:")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)
    
    print("All smoke checks passed.")
```

**`scripts/create_security_tickets.py`** — creates Plane work items from Trivy/Semgrep output:
```python
"""Parse Trivy JSON output and create Plane tasks for CRITICAL/HIGH CVEs."""
import json, sys
import httpx

PLANE_API = "https://api.plane.so/api/v1"
PROJECT_ID = "c8e153db-37cc-4f5d-a6dc-49f546016ef3"

def main(trivy_json_path: str):
    with open(trivy_json_path) as f:
        data = json.load(f)
    
    for result in data.get("Results", []):
        for vuln in result.get("Vulnerabilities", []):
            if vuln["Severity"] in ("CRITICAL", "HIGH"):
                create_plane_task(vuln)

def create_plane_task(vuln: dict):
    # POST to Plane API creating a work item with CVE details
    ...
```

**Deploy script additions** (in `/root/deploy-vicinitideals.sh`):
```bash
# After docker compose up -d:
python /root/stacks/vicinitideals/scripts/post_deploy_smoke.py
if [ $? -ne 0 ]; then
    echo "Smoke check failed — check logs"
    exit 1
fi
```

---

## Cross-Cutting Rules

These apply throughout both phases:

1. **HTMX saves are in-place** — never reload the full page after a form save, only swap the target element.

2. **`afterSwap` handler** — there is a single `htmx:afterSwap` handler in `model_builder.html`. Add new post-swap init code as cases in that handler, not new `MutationObserver` instances.

3. **Tests stay in `tests/` only** — don't add test fixtures or helpers to the main package.

4. **No speculation** — don't add error handling, fallbacks, or abstractions not required by the task. Follow the task description exactly.

5. **Alembic migrations** — every schema change gets its own migration file. Run `alembic revision --autogenerate -m "description"` then review the generated file before applying.

6. **Environment variables** — all secrets go in `.env` (git-ignored). `.env.example` has the key names with placeholder values.

7. **`docker compose down -v` is forbidden** — it destroys the `re-modeling-postgres-data` volume and all deal data.

8. **Import style** — use `from vicinitideals.xxx import yyy` (no bare `import vicinitideals`).

9. **Config validation** — `session_secret_key` must not be the default `"changeme-session-secret"` in non-dev environments. Add a startup check.

10. **Plane project** — REAL (project ID: `c8e153db-37cc-4f5d-a6dc-49f546016ef3`). Create work items for any regressions found during execution.
