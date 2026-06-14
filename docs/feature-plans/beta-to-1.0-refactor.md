# Beta → 1.0 Refactor Plan — vicinitideals

**Originally:** 2026-05-11 @ commit `9c10949`
**Re-evaluated:** 2026-06-11 @ HEAD (565 commits later, migrations 0085 → 0112)
**Diff against HEAD** when re-evaluating after feature work lands.

---

## Verdict

Refactor still has real, structural impact — and the case is stronger than in May.
Even after the decommission trimmed it, `ui.py` is **14,559 lines / 133 route handlers** (was
16,036 / 151 pre-decommission, 12,228 / 123 in May). Without restructuring, every feature gets
slower to add and every bug harder to find.

Stack is well-chosen. No migrations needed. FastAPI + HTMX + SQLAlchemy 2.0 + PostgreSQL 16 +
Redis 7 stays as-is. UI overhaul is **out of scope** — design handled separately.

**1.0 is now two tracks:**

1. **Code-structure cleanup** — split `ui.py`, extract a service layer, kill duplication.
2. **Scope reduction** — **the parcel-intelligence decommission shipped** (2026-06). The app is
   now down to the parts that work: Opportunities, Deals, Brokers, Crexi listing import, and KNN
   comps. Everything else (parcel/GIS scraping, the Map, LoopNet, REALie, HelloData, geo matching,
   parcel/building UI) was removed. See the decommission record below.

The security half of the original Phase 1 also shipped (see below), so Phase 1 is now just the
remaining quick wins.

---

## Shipped since this plan was written

> These items were open in the May plan and are **done** — do not re-do them.
>
> - **CSRF protection** — `app/api/csrf.py` + middleware in `app/api/main.py` (signed stateless tokens, HTMX header injection).
> - **Write rate-limiting** — all POST/PUT/PATCH/DELETE (200/min per user, 30/min per IP).
> - **Per-route auth** — `CurrentUserId` dependency in `app/api/deps.py` (raises 401 before handler).
> - **`selling_costs_pct` org-default wiring** — now wired defaults → schema → model → UI → export → engine.
> - **Capital schema settled** — `funder_type` dropped; `vehicle_type` + `equity_role` canonical on `CapitalModule`.
> - **Dev-fee multi-source engine** — `fee_terms` JSONB (migration 0103).
> - **Reserves refactor** — ODR is a first-class UseLine; lease-up merged into interest reserve (0109–0111).
> - **Parcel-intelligence decommission** (2026-06) — LoopNet, HelloData scraper, county-GIS pipeline, the Map, the parcel tables (migration 0113), and the Building-entity stubs all removed; Crexi import + KNN comps retained. Trimmed `ui.py` by ~1,500 lines / 18 routes. Full record in the decommission section below.

---

## Evidence (current state)

### ui.py is 14,559 lines with 133 route handlers

Grew ~7,900 (early) → 12,228 (May) → 16,036 (pre-decommission) → **14,559 (now)**, no `ui/`
subdirectory — the split has not started. Handles deals, model builder, timeline wizard,
portfolio, brokers, Crexi-listing dedup — all in one file. The `handle_form_create_or_update`
hub still fans out to 300+ downstream nodes. The parcel decommission (below) already deleted a
chunk of these routes, shrinking the eventual split.

### Code duplication (still live)

**Gantt chart — now 2 HTML copies + 1 CSS-only copy:**
- `app/templates/deal_detail.html` — CSS + Gantt HTML
- `app/templates/portfolio_detail.html` — CSS + Gantt HTML (near-identical to deal_detail)
- `app/templates/model_builder.html` — **CSS only** (the HTML copy is gone)
- One color change still touches 2–3 files.

**Deal type dropdown — hard-coded in 3+ template locations:**
- `deals_new.html`, `model_builder.html` (×2 — main + Add-Project drawer), `opportunity_wizard.html`
- `ProjectType` enum exists at `app/models/deal.py:36` with matching values. Templates don't use it.

**Property types — now single-source (was 2 drifted files):**
- `opportunities.html` (6): `Multifamily, Office, Retail, Industrial, Land, Mixed Use` — the only
  remaining list. The 8-item `building_form_fields.html` copy was deleted with the parcel/building
  decommission. Promote this to the `ProjectType` enum or a shared partial before it drifts again.

**Python defaults — `offer_made` conflicts:**
- `DEFAULT_DURATIONS` in `app/models/milestone.py` → **14 days**
- `_ACQUISITION_DEFAULT_DAYS` in `ui.py` → **7 days**

**Debt sizing options — duplicated 1:1:**
- `model_builder.html` and `settings_org.html` both hard-code `gap_fill / dscr_capped / dual_constraint`.
- (`debt_structure` options live only in `model_builder.html`.)

### Security

| Issue | Status |
|---|---|
| CSRF protection | **Done ✓** (`app/api/csrf.py` + middleware) |
| Write rate limiting | **Done ✓** (all mutating methods) |
| Route-level auth | **Done ✓** (`CurrentUserId` dep) |
| SQL injection | Safe — parameterized throughout |

### Incomplete stubs

- `equity_multiple` (`ui.py:408`): always `None` — `# TODO: load from SensitivityResult (needs join)`.
- Backward-compat aliases `DealModel = Scenario`, `ScenarioResult = SensitivityResult` — keep, still in use.

---

## Parcel Intelligence: Decommission — DONE (2026-06)

The parcel-intelligence half (scrape county GIS, maintain a living ~446K-parcel inventory,
LoopNet/HelloData/REALie, the Map, parcel/building UI) was built but effectively non-functional;
validating it would have cost ~**3× the effort already invested**. Decision: **rip it out, keep
only what works.** Crexi listing import and the KNN comps engine survive; everything else is gone.

Full record in the `project_parcel_decommission` notes and the **Archive** sections of
`docs/DATA_MODEL.md`, `PROJECT_OVERVIEW.md`, and `MARKET_MODEL.md`.

### What shipped

- **DC-1 — LoopNet deleted.** Scrapers, `app/tasks/loopnet_ingest`, `listing_snapshot` model,
  3 beat entries, `loopnet_*` config removed; 496 orphan LoopNet Opportunity rows purged.
- **DC-2 — HelloData removed.** Scraper / CLI / budget-tracker / config deleted; `market.py`
  decoupled from `hellodata_*` (comps fall back to Crexi fields + manual entry).
- **DC-3 — Parcel + county-GIS pipeline removed.** PortlandMaps / Clackamas / Oregon City /
  Gresham ArcGIS scrapers, parcel seed/enrich, geo matching, jurisdiction tagging deleted.
- **DC-4 — The Map removed.** Leaflet, zone painter, `/tools/listings/map*` deleted.
- **DC-5 — Parcel tables dropped** (migration 0113): `parcels` (446K rows) +
  `parcel_transformations`, and `opportunities.parcel_id` / `parcel_conflicts_ack` /
  `projects.parcel_id`. KNN repointed to `Opportunity` own-fields (jurisdiction→city fallback).
- **Building entity** — orphaned stub routes / helpers / templates removed (the entity itself
  was gone since migration 0072).
- Dead-crumb sweeps + the schema-doc Archive sections.

**Kept live:** Opportunities, Deals, Brokers (+ Oregon eLicense), Crexi import (`scrape-crexi-daily`),
KNN comps, `Opportunity.apn` / `apn_normalized` / `lat` / `lng`, manual jurisdiction.

**Left alone (Steph, 2026-06-14):** the dormant `OpportunitySource.loopnet` enum,
`Broker.loopnet_broker_id`, and the `hellodata_*` / `jurisdiction` columns — "not production
features at the moment." No further parcel-DB drops planned.

### Still pending (carried into Phase 1 / 1.5)

- **DC-6 — Fix the `hide_test` filter** so Crexi Oppos display (the test-data filter currently
  hides them alongside the old LoopNet rows).
- **Crexi listing lifecycle.** A scheduled task moving stale / expired / sold Crexi listings into
  an **Archived** Opportunity status — data retained, hidden from active views. Needs an
  `archived` / lifecycle-status field on `Opportunity` + a Celery beat task with a staleness rule.
- **Opportunity ↔ Broker link.** Broker FK/M2M on `Opportunity` + a broker picker in the Oppo
  create/edit UI so manually-created Oppos can be tied to a Broker. Brokers already have dedup;
  this just wires the relationship + UI. (Schema impact: broker link + archived status on
  `Opportunity` — update `docs/DATA_MODEL.md` when built.)

---

## ui.py Split — 7 Sub-Routers (recomputed for 14.5k / 133)

The 133 routes still divide cleanly by domain. Estimates are approximate; they already **shrank
with the parcel decommission** — `data_intel` lost parcels/map/building, so the whole split is easier.

| New file | Est. lines | What's inside |
|---|---|---|
| `ui/settings.py` | ~900 | Root, splash, `/settings/*`, admin tasks |
| `ui/deals_pipeline.py` | ~2,600 | Deal list/CRUD, opportunities, opportunity wizard, **broker link** |
| `ui/data_intel.py` | ~700 | Brokers + Crexi-sourced Oppos + Crexi dedup — parcels/map/building routes already deleted |
| `ui/model_builder.py` | ~3,800 | Builder page, panel, forms handler, project ops, sensitivity, anchors, source coverage, calc status |
| `ui/wizards.py` | ~1,800 | Timeline wizard, approve timeline, deal setup wizard |
| `ui/model_outputs.py` | ~2,400 | Excel/investor exports, draw schedule, line form, NOI inputs, source vehicle prefill, history |
| `ui/portfolios.py` | ~450 | Portfolios, deal search, saved filters |
| `ui/_helpers.py` | ~700 | Shared: `_get_user`, `_load_builder_data`, `_fmt_currency`, etc. |

`model_builder.py` stays heaviest because `handle_form_create_or_update` (the 300-edge hub)
can't be safely split without a service layer first — that's Phase 2b. `app/services/` **already
exists** (`scenario_factory.py`, `capital_module_milestones.py`, `stabilization_milestone.py`,
…) and is the natural landing zone for that extraction, which lowers 2b risk.

### Blast radius of the split

`ui.py` is imported by only a handful of files (`app/api/main.py`, `app/api/routers/tools.py`,
`app/api/routers/models.py` lazy import, a couple of `tests/api/` files). E2E tests hit via HTTP,
so no import breakage there. Move-code and change-code go in **separate commits**.

---

## Phased Plan

### Phase 0 — Done (for the record)

~~CSRF · write rate-limiting · per-route auth · `funder_type` drop · `selling_costs_pct` wiring~~

### Phase 1 — Quick wins (decommission DONE)

The parcel decommission (DC-1…DC-5) shipped — see the section above. Remaining:

- **DC-6** — `hide_test` filter fix so Crexi Oppos display.
- Deal-type enum in templates (`ProjectType` via Jinja loop, 3+ files).
- Gantt CSS extraction → single shared block in `base.html`.
- Property-type list consolidation (see Open Decisions for canonical list).
- `offer_made` defaults unification (resolve 14 vs 7 — one source of truth).
- `debt_sizing_mode` single-source (model_builder + settings_org).

### Phase 1.5 — New small builds

- Crexi listing lifecycle → Archived status + scheduled purge.
- Opportunity ↔ Broker link (schema + picker UI).

### Phase 2a — ui.py split

Extract `_helpers.py` first, then one sub-router per PR, run E2E after each, delete from `ui.py`.
Do `model_builder.py` last. Smaller than the May estimate thanks to the decommission.

### Phase 2b — Service layer extraction

After 2a. Build on the existing `app/services/` seam. Targets: `CapitalStructureService`,
`TimelineService`, `CashflowService`. Result: a new carry type touches ~3 files, not 6+.

### Phase 2c — Responsiveness fix

Wire HTMX OOB swaps so the cashflow summary / balance bar update immediately after any form
save. No new infrastructure — done alongside 2a/2b since the routes are already being touched.

### Phase 3 — Cleanup (no deadline)

- `equity_multiple` → hide in UI until the SensitivityResult join is built.
- Celery queue simplification (scraping is now Crexi-only — fewer workers warranted).
- HTMX upgrade 1.9.x → 1.10+.
- Backward-compat alias cleanup (`DealModel`, `ScenarioResult`) once all callers updated.

---

## Open Decisions

1. **Canonical property-type list** — the 8-item `building_form_fields` superset was deleted with
   the decommission; `opportunities.html`'s 6-item list (`Multifamily, Office, Retail, Industrial,
   Land, Mixed Use`) is now the only one. Decide the canonical set (keep these 6, or restore the
   wider list) and back it with the `ProjectType` enum. Business confirm before code.
2. **equity_multiple** — *Recommend hide in UI* until the join exists. (Confirm.)

All other May-era open decisions are resolved: LoopNet → delete; HelloData → eliminate;
REALie/county-GIS/Map/parcel UI → decommission; HelloData "keep?" → no.

---

## What We're NOT Doing

- Stack swap (FastAPI/HTMX/SQLAlchemy stays)
- UI redesign (handled separately)
- WebSocket (HTMX OOB swap is sufficient)
- Frontend framework (React/Vue — not justified) · SSO
- **Any parcel / county-GIS data pipeline** — not maintained, not rebuilt
- **New external data sources** — Crexi is the only retained scraper

---

## Sibling plans

- `docs/feature-plans/excel-export-v3.md` — active; the investor-export track of 1.0.
- `docs/feature-plans/Completed/` — shipped slices (dev-fee multi-source, float-earnings Phase B,
  unified-period engine, source-use eligibility, etc.).

This document is the **code-structure + scope-reduction** track of 1.0; it is not superseded by
the export work, which runs in parallel.
