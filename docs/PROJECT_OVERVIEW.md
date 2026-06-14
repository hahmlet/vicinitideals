# RE-Modeling Platform — Project Overview

A self-hosted real estate financial modeling and deal intelligence platform. It combines **Crexi** commercial-listing ingestion and KNN market comps with a full deal underwriting engine and an interactive model builder UI — all running on private infrastructure.

> **Scope (2026-06):** the original parcel / county-GIS intelligence half was **decommissioned** — see the Archive at the end of this doc. Live data intelligence is Crexi listings + KNN comps.

---

## 1. Project Intent

The platform exists to answer two questions for a real estate investment team:

**"What is on the market?"** — A continuously refreshed inventory of **Crexi** commercial listings in the target market (Multnomah + Clackamas County, OR, excluding Portland), with KNN comps to benchmark each against similar properties.

**"Does this deal work?"** — A full financial model for any deal under consideration: uses, sources, debt carry, operating cash flow, equity waterfall, draw schedule, and sensitivity analysis — with all outputs exportable to Excel.

A listing flows into an Opportunity, which a Deal attaches to when the team decides to pursue. (The original county-GIS *parcel* inventory that pre-seeded properties before they were listed was decommissioned — see Archive.)

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
| **Crexi** | Commercial listings (routed through ProxyOn residential proxy) — the one live scraper |
| **ProxyOn** | Residential + datacenter proxy pool for scraping (used by Crexi) |

> LoopNet, Portland Maps, Oregon City, Clackamas County, Gresham ArcGIS, Oregon Address Points, and REALie were **decommissioned** with the parcel subsystem — see Archive.

---

## 3. Major Components

### 3a. Data Ingestion (Crexi Listings)

The platform ingests **Crexi** commercial listings into an Opportunity inventory. Key subsystems:

- **Crexi scraper** (`app/scrapers/crexi.py` + `app/tasks/scraper.py`) — normalizes raw responses into the shared Opportunity schema; daily Celery beat on the scraping queue.
- **Deduplication engine** (`app/scrapers/dedup.py`) — fuzzy matching on address + unit count to flag near-duplicate Crexi listings for human review.
- **KNN comps** (`app/engines/market.py`) — benchmarks an Opportunity against similar listings; see [MARKET_MODEL.md](MARKET_MODEL.md).

> The parcel / county-GIS intelligence layer (multi-source scrapers, parcel enrichment, parcel seeding, GIS cache) was **decommissioned** — see Archive.

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

### 3e. Listings Browser

Full-screen Opportunities table with filter sidebar (status, price, zoning, county, broker, property type) and a dedup comparison UI for resolving near-duplicate Crexi listings.

> The parcel browser, parcel detail drawer (ownership / assessment / geometry / map), and the Map (Leaflet / zone painter) were **decommissioned** — see Archive.

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

---

## Archive — Decommissioned Parcel Intelligence

> **🗄 ARCHIVED — does not reflect the live platform.** The parcel / county-GIS intelligence half was removed in 2026-06 (migrations 0072 building entity, 0113 parcel tables; code removed across DC-1…DC-5). Schema-level detail is in [DATA_MODEL.md → Archive](DATA_MODEL.md). **Kept live:** Crexi ingest, KNN comps, `Opportunity.apn` / `lat` / `lng`, and the manual jurisdiction field.

**Removed external data sources:** LoopNet (subscription cancelled), Portland Maps API, Oregon City assessor, Clackamas County, Gresham ArcGIS, Oregon Statewide Address Points (parcel seed universe), REALie.

**Removed subsystem — Data Ingestion & Parcel Intelligence:**
- Multi-source parcel **scrapers** — one module per county-GIS source (Portland Maps, ArcGIS, Oregon City, Clackamas, plus REALie / HelloData).
- **Parcel enrichment** — owner / assessed value / geometry / zoning from county GIS.
- **Parcel seeding** — bulk stub creation from Oregon Address Points (~430K parcels).
- **GIS cache** — local ArcGIS layer cache with quarterly refresh.
- The original premise that *"a parcel record lives in the system before a deal exists"* — properties now enter only as Crexi listings.

**Removed UI:** the parcel browser, the parcel detail drawer (ownership / assessment / geometry / attached listings), and the **Map** (Leaflet / zone painter).
