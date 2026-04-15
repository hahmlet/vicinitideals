# RE-Modeling Platform — Project Overview

A self-hosted real estate financial modeling and deal intelligence platform. It combines proactive parcel/listing ingestion from multiple data sources with a full deal underwriting engine and an interactive model builder UI — all running on private infrastructure.

---

## 1. Project Intent

The platform exists to answer two questions for a real estate investment team:

**"What is out there?"** — A continuously refreshed inventory of all qualifying parcels in the target market (Multnomah + Clackamas County, OR, excluding Portland), pulled from commercial listing platforms and county/GIS sources, whether or not the property is actively listed for sale.

**"Does this deal work?"** — A full financial model for any deal under consideration: uses, sources, debt carry, operating cash flow, equity waterfall, draw schedule, and sensitivity analysis — with all outputs exportable to Excel.

The two halves share a common data model: a parcel record lives in the system before a deal exists, and a deal attaches to it when the team decides to pursue.

---

## 2. Tech Stack

### Infrastructure

| Layer | Detail |
|---|---|
| **Host** | Proxmox homelab |
| **VM 114 (dockervm)** | Primary application VM — runs all Docker containers |
| **LXC 109** | NGINX reverse proxy (routes `*.ketch.media` subdomains) |
| **LXC 112** | MCP servers (Proxmox, Home Assistant, Node-RED, Wallabag) |
| **PostgreSQL** | Docker container on VM 114, persistent volume |
| **Redis** | Docker container on VM 114, Celery broker + backend |

### Application

| Component | Technology |
|---|---|
| **API** | FastAPI 0.110+ (async, Python 3.12+) |
| **ORM / DB** | SQLAlchemy 2.0+ (async) + asyncpg + Alembic migrations |
| **Task queue** | Celery 5.3+ (3 worker queues: default, scraping, analysis) |
| **Templates** | Jinja2 3.1+ rendered server-side, progressive enhancement via HTMX |
| **Financial math** | pyxirr (IRR/XIRR), custom engine modules |
| **HTTP / scraping** | httpx, curl-cffi (TLS fingerprint spoofing), ProxyOn proxy pool |
| **Address parsing** | usaddress 0.5.10 |
| **Excel I/O** | openpyxl 3.1 |
| **Validation** | Pydantic v2 |
| **Package manager** | uv (fast pip replacement) |
| **Container** | Docker + docker-compose; Python 3.12-slim base image |

### External Data Sources

| Source | Data |
|---|---|
| **Crexi** | Commercial listings (routed through ProxyOn residential proxy) |
| **LoopNet** | Commercial listings |
| **Portland Maps API** | Property assessment, zoning, ownership |
| **Oregon City assessor** | Property records |
| **Clackamas County** | Property/tax records |
| **ArcGIS (Gresham OR)** | Parcel geometry, zoning layers |
| **Oregon Statewide Address Points** | Bulk parcel seed universe (~300-400k features filtered to Multnomah + Clackamas) |
| **REALie** | Real estate listing data API |
| **ProxyOn** | Residential + datacenter proxy pool for scraping |

---

## 3. Major Components

### 3a. Data Ingestion & Parcel Intelligence

The platform maintains a living inventory of parcels, not just listings. Key subsystems:

- **Scrapers** (`vicinitideals/scrapers/`) — one module per source (Crexi, LoopNet, Portland Maps, ArcGIS, Oregon City, Clackamas, REALie, Redfin enrichment). Each normalizes raw API/HTML responses into the shared schema.
- **Parcel enrichment** (`parcel_enrichment.py`) — enriches raw parcel stubs with owner, assessed value, geometry, zoning from county GIS after initial ingest.
- **Deduplication engine** (`dedup.py`) — cross-source fuzzy matching on APN + address to merge listing records onto the canonical parcel.
- **Celery task pipeline** (`vicinitideals/tasks/`) — `scraper.py` (main ingest), `parcel_seed.py` (bulk stub creation from Oregon Address Points), scheduled via Celery beat.
- **GIS cache** (`data/gis_cache/`, `tools/gis_cache/`) — local ArcGIS layer cache with quarterly refresh policy; avoids hitting external APIs on every request.

See: [docs/ops/](docs/ops/) for operational runbooks, [docs/verification/](docs/verification/) for QA baselines.

### 3b. Financial Analysis Engines

All computation is pure Python, no spreadsheet backend. Located in `vicinitideals/engines/`:

| Engine | Purpose |
|---|---|
| `cashflow.py` | Monthly cash flow projection: revenue, OpEx, debt service, NOI |
| `draw_schedule.py` | Auto-sized construction draws; self-referential formula so each draw fully funds its own carry cost |
| `waterfall.py` | Equity distribution waterfall (LP/GP splits, IRR hurdles, preferred return) |
| `underwriting.py` | Deal-level underwriting metrics (cap rate, CoC, IRR, DSCR, LTV) |
| `sensitivity.py` | Multi-variable sensitivity tables |

The draw schedule engine handles the self-referential sizing problem: `D = (uses + B×r×n) / (1 - r×n)`, ensuring each draw covers carry on its own outstanding balance without iteration.

See: [docs/testing-strategy.md](docs/testing-strategy.md) for engine test coverage approach.

### 3c. Deal & Scenario Data Model

`vicinitideals/models/` — 34 Alembic migrations define the schema:

- **Deal** → Opportunity → Project → Milestones (timeline)
- **Scenario** → UseLines, CapitalModules, IncomeStreams, ExpenseLines, DrawSources, WaterfallTiers
- **Parcel** → ScrapedListings (many listings per parcel)
- **Portfolio** → Portfolio entries linking deals to portfolios
- **Output** — `OperationalOutputs` (computed cashflow, stored as JSON blob)

### 3d. Model Builder UI

An HTMX-driven interface (`vicinitideals/templates/`) that lets a user build and run a full deal model without leaving the browser. Modules load progressively; each saves immediately via HTMX partial swaps.

| Module | What it does |
|---|---|
| **1 · Uses** | Construction costs, soft costs, reserves by phase |
| **2 · Sources** | Debt and equity capital stack |
| **3 · Revenue** | Income streams (rent rolls, laundry, parking, etc.) |
| **4 · OpEx** | Operating expense lines |
| **5 · Carrying** | Debt service (I/O or P&I by phase) |
| **6 · Owners & Profit** | Equity ownership, deferred developer fee, profit share |
| **7 · Divestment Uses** | Exit costs |
| **8 · Divestment Waterfall** | Sale proceeds distribution |
| **Cash Flow** | Computed monthly output table |
| **Draw Schedule** | Auto-sized draws, carry, reserve floors, source Gantt |

See: [docs/ui-plan.md](docs/ui-plan.md) for the full UI specification.

### 3e. Listings & Parcel Browser

Full-screen listings table with filter sidebar (status, price, zoning, county, broker, property type). Parcel detail drawer shows ownership, assessment, geometry, attached listings, and linked deals. Dedup comparison UI for resolving near-duplicate listings.

---

## 4. Deployment

```
git push origin main
  └─► VM 114: /root/deploy-re-modeling.sh
        git pull → docker build → alembic upgrade head → docker-compose up -d → health check
```

Domain: `viciniti.deals` (proxied by LXC 109 NGINX)

Docker services defined in `docker-compose.yml`:
- `re-modeling-api` (FastAPI, port 8001)
- `re-modeling-worker` (Celery, default queue)
- `re-modeling-scraper` (Celery, scraping queue)
- `re-modeling-analysis` (Celery, analysis queue)
- `re-modeling-postgres`
- `re-modeling-redis`

See: [docs/ops/](docs/ops/) for release checklist and rollback runbook.

---

## 5. Key Docs

| Document | Contents |
|---|---|
| [docs/testing-strategy.md](docs/testing-strategy.md) | Test architecture, unit vs integration, engine coverage |
| [docs/ui-plan.md](docs/ui-plan.md) | Model builder UI specification, module breakdown |
| [docs/ops/](docs/ops/) | Release checklist, rollback runbook, observability SLO spec |
| [docs/verification/](docs/verification/) | QA test matrix, model output drift baselines |
| [docs/security/](docs/security/) | Security considerations |
| [docs/api/](docs/api/examples/) | API payload examples |
