# re-modeling — Appsmith UI Plan

**Platform:** Appsmith (viciniti.deals)  
**Auth model:** No auth. User selected on splash screen, stored in `localStorage`, sent as `X-User-ID` header on all API calls.  
**Navigation:** Appsmith sidebar or top nav. Pages are distinct Appsmith pages. Sub-navigation within a page uses tabs or drawer panels.

---

## Page 0 — Splash / User Select

**The entry point.** Loads before anything else. Lets the user pick their identity from the org's user list.

- Fetches `GET /orgs/{id}/users` and renders user cards (name + display color avatar)
- On select: writes `user_id` to `localStorage`, navigates to Projects Dashboard
- No API key required for this page — it's purely a selector
- If `localStorage` already has a valid `user_id`, auto-skip to Projects Dashboard with a "not you?" link

---

## Page 1 — Projects Dashboard

**The home page.** Overview of all projects in the org with quick-access KPIs.

- Filterable/searchable table or card grid of projects
- Filters: status (active / hypothetical / archived), source (loopnet / crexi / user_generated), has active model (yes/no)
- Per-project row: name, address, status, active model name, NOI, levered IRR, equity multiple (pulled from `GET /projects/{id}/summary`)
- "New Project" button → modal or drawer to create a project (name, status, source)
- "Hide" toggle per project (calls `PATCH /projects/{id}/visibility`) — hidden projects filtered out by default with a "show hidden" toggle
- Click project → navigates to Project Detail (Page 2)
- Badge on projects with new/unreviewed listings that matched saved criteria

---

## Page 2 — Project Detail

**The project anchor page.** Shows everything tied to a specific project: property info, linked parcels, deal models list, and permit stub.

Tabs:
- **Overview** — project name, address, source, status, notes. Edit inline.
- **Parcels** — list of linked parcels (`GET /projects/{id}/parcels`). Per-parcel: APN, address, zoning, lot sqft, assessed value. Add parcel (search by APN or address), unlink, update relationship type (unchanged / merged_in / split_from). Parcel Transformation section below: transformation type, input APNs, output APNs, effective lot sqft, status.
- **Deal Models** — list of all deal models for this project. "Active" badge on is_active model. Click to open Deal Model page. "New Model" button (clone from existing or start fresh). "Set Active" action.
- **Permit** — permit stub: permit number, URL, notes. Edit inline. (Phase 1 only — no full permit UI yet)

---

## Page 3 — Deal Model: Inputs

**The core underwriting form.** Where all assumptions are entered and edited.

- Header: model name, version, project type selector (acquisition_minor_reno / acquisition_major_reno / acquisition_conversion / new_construction), is_active toggle
- **Section: Acquisition** — purchase price, closing costs %
- **Section: Project-specific inputs** — dynamically shown based on project_type:
  - Renovation cost, months (minor/major reno)
  - Conversion cost per unit, change of use permit cost (conversion)
  - Hard cost/unit, soft cost %, contingency %, construction months (new construction)
  - Hold phase toggle + hold months (new construction only)
  - Entitlement months + cost (new construction)
- **Section: Lease-up** — lease-up months, initial occupancy %
- **Section: Operating** — opex/unit/year, mgmt fee %, property tax, insurance, capex reserve/unit
- **Section: Exit** — hold period years, exit cap rate %, selling costs %
- **Income Streams** — table: label, type, units, amount/unit/month or fixed, occupancy %, escalation %, active phases. Add / edit / delete rows inline.
- **Expense Lines** — table: label, annual amount, escalation %, active phases, notes. Add / edit / delete rows inline.
- Save button calls `PATCH /models/{id}/operational-inputs`. If `compute_stale` is true after save, a "Recompute" banner appears.
- "Compute" button calls `POST /models/{id}/compute` and navigates to Outputs page.

---

## Page 4 — Deal Model: Capital Stack

**Where funders and waterfall tiers are configured.** Separate from inputs because it's a distinct configuration layer.

- **Capital Modules** panel (left or top): list of modules ordered by stack_position. Per module: label, funder_type badge, stack position, source amount or % of cost, carry type, exit type. Add / edit / delete. Edit opens a drawer with full source/carry/exit fields.
- **Waterfall Tiers** panel (right or bottom): ordered list of tiers. Per tier: priority, tier_type, IRR hurdle (if applicable), LP/GP split. Drag to reorder (or up/down arrows). Add / edit / delete.
- "Compute Waterfall" button → calls `POST /models/{id}/waterfall/compute`, then navigates to Outputs.
- Visual stack diagram (optional Phase 2): horizontal bar showing capital stack layers by stack_position and funder_type color-coded.

---

## Page 5 — Deal Model: Outputs

**The results page.** Shows what the engine computed — KPIs, cash flow table, waterfall distribution, and investor report.

Tabs:
- **Summary KPIs** — total project cost, equity required, total timeline months, NOI stabilized, cap rate on cost, levered IRR, unlevered IRR, DSCR, equity multiple. Sourced from `GET /models/{id}/outputs`.
- **Cash Flow** — period table: one row per month across the full lifecycle. Columns: period, period_type, gross revenue, vacancy loss, EGI, opex, capex reserve, NOI, debt service, net cash flow, cumulative. Click any cell → drill-down drawer showing `CashFlowLineItem` rows for that period (label, base amount, adjustments, net amount).
- **Waterfall** — tier distribution table. `GET /models/{id}/waterfall`. Per tier: priority, type, LP distributed, GP distributed. Below: per capital module totals.
- **Investor Report** — `GET /models/{id}/waterfall/investor-report`. Per funder: total contributed, total distributed, equity multiple, IRR. Expandable row shows distribution by period.
- **Export** — "Download JSON" and "Download Excel" buttons (calls `GET /models/{id}/export/json` and `GET /models/{id}/export/xlsx`).

---

## Page 6 — Scenarios

**Variable sweep analysis.** Create, run, and compare scenario results for a deal model.

- Scenario list for the current project/model: status badge (pending / running / complete), variable swept, range
- "New Scenario" form: select variable from allowed list (`GET /scenarios/variables`), set range_min, range_max, range_steps → `POST /projects/{id}/scenarios`
- Status polling: for in-progress scenarios, poll `GET /scenarios/{id}/status` every 5s; show progress indicator
- Results view: line chart or table of variable_value vs. project_irr_pct / lp_irr_pct / gp_irr_pct / equity_multiple
- Compare toggle: select 2 scenarios side-by-side to see how a different variable range produces different IRR curves

---

## Page 7 — Portfolio

**Multi-project rollup.** Group projects together and see combined metrics and timeline.

- Portfolio list: `GET /portfolios` with pagination. Per portfolio: name, project count, quick rollup badge.
- "New Portfolio" button → name input → creates portfolio.
- Portfolio detail (click through or inline expand):
  - Project list with contribution amounts and start dates
  - Add / remove projects (`POST /portfolios/{id}/projects`)
  - Summary metrics: aggregate equity, blended IRR (from `GET /portfolios/{id}/summary`)
  - **Gantt view**: horizontal bars per project per phase, color-coded by phase type (`GET /portfolios/{id}/gantt`). Read-only Phase 1; computed from deal model timelines.

---

## Page 8 — Listings

**Scraped listing feed.** Review new listings from LoopNet and Crexi, filter by criteria match, convert to projects.

- Listing table: address, source, asking price, unit count, cap rate, scraped_at, is_new badge, matches_criteria badge
- Filters: source (loopnet / crexi / all), is_new only, matches_criteria only
- "Trigger Ingest" button → `POST /ingest/trigger` with source selector. Shows task_id and polls for completion.
- Per listing: "Convert to Project" button → `POST /listings/{id}/convert` → navigates to new Project Detail
- Per listing: "View Raw" → JSON drawer showing raw scraped data
- Saved Search Criteria section (collapsible): list of active criteria per user. Add/edit/delete criteria (min/max units, max price, zip codes, sources).

---

## Page 9 — De-duplication

**Manual review queue for near-duplicate listings.** Surfaces flagged pairs for human resolution.

- Table of `DedupCandidate` rows with status=pending: `GET /dedup/pending`
- Per candidate: confidence score badge, match signals (address_fuzzy, unit_count_match, etc.), record A and record B summaries side-by-side
- Action buttons per row: **Merge**, **Keep Separate**, **Swap** (calls `PATCH /dedup/{id}/merge|keep-separate|swap`)
- Confidence score color coding: 0.85+ (green, auto-handled), 0.60–0.84 (yellow, needs review), <0.60 (not shown here)
- "Resolved" tab: past decisions with resolved_by and resolved_at

---

## Page 10 — Parcels

**Authoritative property data browser.** Search, view, and link parcels to projects.

- Search bar: by address or APN (R-number). Calls `GET /parcels?query=...`
- Results table: APN, normalized address, owner name, zoning, lot sqft, assessed value, year built
- Parcel detail drawer: all fields + geometry info (lat/lon centroid from GeoJSON; map embed Phase 2)
- "Link to Project" button from parcel detail → project selector → calls `POST /projects/{id}/parcels`
- Parcel freshness indicator: `scraped_at` timestamp; "Refresh" button to trigger `POST /parcels/{apn}/refresh`

---

## Oddball Features — Doesn't Fit a Page Cleanly

These features exist in the API but don't have a natural home as a standalone Appsmith page. Recommended treatment noted for each.

### Workflow Run Manifest (`GET /models/{id}/runs`, `POST /models/{id}/runs/{run_id}/replay`)
**Problem:** This is developer/debug tooling — a log of every engine run with inputs/outputs and a replay button. Not useful for end-users doing underwriting.  
**Recommendation:** Surface as a collapsible "Run History" panel at the bottom of the Outputs page (Page 5), visible only when a debug mode toggle is on. Not a standalone page.

### API Payload Examples (`docs/api/examples/`)
**Problem:** These are developer reference docs, not a UI feature.  
**Recommendation:** Not surfaced in Appsmith at all. They live in the repo under `docs/api/examples/` for agent/developer consumption.

### Security Hardening Backlog (`docs/security/hardening-backlog.md`)
**Problem:** Ops document, not a UI concern.  
**Recommendation:** Not surfaced in Appsmith. Reviewed by humans in the repo.

### Deployment Gates / Rollback Runbook / Release Checklist
**Problem:** Ops process documents.  
**Recommendation:** Not surfaced in Appsmith. Referenced during release cycles only.

### Observability Baseline / SLO Dashboard
**Problem:** Monitoring belongs in Grafana, not Appsmith.  
**Recommendation:** Not surfaced in Appsmith. Grafana dashboard is a separate infra task; the requirements live in `docs/ops/observability-slo-dashboard.md`.

### QA Test Matrix / Excel Parity Suite
**Problem:** Developer tooling.  
**Recommendation:** Not surfaced in Appsmith. These run in CI/dev environment. Reference docs live in `docs/verification/qa-test-matrix.md` and `docs/verification/baseline-2026-04-03.md`.

---

## Navigation Structure (Summary)

```
viciniti.deals
├── [0] Splash / User Select        ← entry point, no sidebar
├── [1] Projects Dashboard          ← home after login
├── [2] Project Detail              ← tabs: Overview / Parcels / Deal Models / Permit
├── [3] Deal Model: Inputs          ← operational assumptions + income + expenses
├── [4] Deal Model: Capital Stack   ← funders + waterfall tiers
├── [5] Deal Model: Outputs         ← KPIs / Cash Flow / Waterfall / Investor / Export
├── [6] Scenarios                   ← sweep + compare
├── [7] Portfolio                   ← rollup + Gantt
├── [8] Listings                    ← feed + ingest trigger + saved criteria
├── [9] De-duplication              ← review queue
└── [10] Parcels                    ← search + link
```

Pages 3, 4, and 5 share a deal model context and should have a sub-header showing the project name → model name breadcrumb with a tab bar to switch between Inputs / Capital Stack / Outputs without going back to the project list.
