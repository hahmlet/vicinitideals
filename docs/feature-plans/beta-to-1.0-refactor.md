# Beta → 1.0 Refactor Plan — vicinitideals

**Originally:** 2026-05-11 @ commit `9c10949`
**Re-evaluated:** 2026-06-11 @ HEAD (565 commits later, migrations 0085 → 0112)
**Diff against HEAD** when re-evaluating after feature work lands.

---

## Verdict

Refactor still has real, structural impact — and the case is stronger than in May.
The monolith grew: `ui.py` is now **16,036 lines / 151 route handlers** (was 12,228 / 123).
Without restructuring, every feature gets slower to add and every bug harder to find.

Stack is well-chosen. No migrations needed. FastAPI + HTMX + SQLAlchemy 2.0 + PostgreSQL 16 +
Redis 7 stays as-is. UI overhaul is **out of scope** — design handled separately.

**1.0 is now two tracks:**

1. **Code-structure cleanup** — split `ui.py`, extract a service layer, kill duplication.
2. **Scope reduction** — **decommission the parcel-intelligence subsystem** down to the parts
   that work: Opportunities, Deals, Brokers, Crexi listing import, and KNN comps. Everything
   else (parcel/GIS scraping, Map, LoopNet, REALie, HelloData, jurisdiction tagging, geo
   matching, parcel/building UI) gets archived and removed.

The security half of the original Phase 1 already shipped (see below), so this plan's Phase 1
is now decommission + the remaining quick wins.

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

---

## Evidence (current state)

### ui.py is 16,036 lines with 151 route handlers

Grown from ~7,900 (early) → 12,228 (May) → **16,036 (now)**, no `ui/` subdirectory — the split
has not started. Handles deals, model builder, timeline wizard, portfolio, parcels, dedup,
brokers — all in one file. The `handle_form_create_or_update` hub still fans out to 300+
downstream nodes. The parcel decommission (below) deletes a chunk of these routes, making the
eventual split smaller.

### Code duplication (still live)

**Gantt chart — now 2 HTML copies + 1 CSS-only copy:**
- `app/templates/deal_detail.html` — CSS + Gantt HTML
- `app/templates/portfolio_detail.html` — CSS + Gantt HTML (near-identical to deal_detail)
- `app/templates/model_builder.html` — **CSS only** (the HTML copy is gone)
- One color change still touches 2–3 files.

**Deal type dropdown — hard-coded in 3+ template locations:**
- `deals_new.html`, `model_builder.html` (×2 — main + Add-Project drawer), `opportunity_wizard.html`
- `ProjectType` enum exists at `app/models/deal.py:36` with matching values. Templates don't use it.

**Property types — 2 files, drifted:**
- `opportunities.html` (6): `Multifamily, Office, Retail, Industrial, Land, Mixed Use`
- `partials/building_form_fields.html` (8): `Multifamily, Mixed Use, Commercial, Retail, Industrial, Single Family, Vacant Land, Other`

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

## Parcel Intelligence: Decommission

The parcel-intelligence half (scrape listings + county GIS, maintain a living ~446K-parcel
inventory, KNN comps) was built but is effectively non-functional, and validating it against
real-world data would cost roughly **3× the effort already invested**. Decision: **rip it out,
archive the code, keep only what works.** Crexi listing import and the KNN comps engine survive;
everything else is removed.

### Keep / Kill

| Keep | Kill / archive |
|---|---|
| **Opportunities** (manual + Crexi) | LoopNet (subscription cancelled) — `app/scrapers/loopnet.py`, `loopnet_broker.py`, `app/tasks/loopnet_ingest.py`, `app/models/listing_snapshot.py`, 3 beat entries, 6 config fields (~1,944 lines) |
| **Deals** | HelloData — `app/scrapers/hellodata.py`, `app/scripts/enrich_hellodata.py`, `app/models/hellodata_usage.py`, config + `market.py` read paths |
| **Brokers** (+ Oregon eLicense) | REALie enrichment |
| **Crexi** import (`app/scrapers/crexi.py`, daily `scrape-crexi-daily`) → Oppos | County GIS scrapers — PortlandMaps, Clackamas, Oregon City, Gresham ArcGIS (`app/scrapers/{portlandmaps,clackamas,oregoncity,arcgis}.py`) |
| **KNN comps** (`app/engines/market.py`) — repointed to Oppo-native inputs | Parcel seeding/enrichment (`app/tasks/parcel_seed*`, `app/scrapers/parcel_enrichment.py`) |
| | Jurisdiction tagging + geo parcel matching (`app/services/parcel_matching.py`) |
| | The **Map** (`app/templates/listings_map.html`, `/tools/listings/map*`) |
| | Parcel/building UI — `app/templates/parcels.html`, `partials/parcel_detail.html`, `partials/building_form_fields.html`, `dedup.html`, `app/models/parcel.py`, and `/parcels`, `/ui/parcels/*`, `/dedup*` routes |

**Why these two roots failed (for the record):** jurisdiction tagging was wrong (scraped `city`
often the metro name — Gresham listings tagged "Portland"), which poisoned both comps and the
browse filter; and county GIS was only ever wired as per-address *lookup*, never as a batch
feeder, so the "living inventory" was an RLIS snapshot plus a slow ≤500/tick drip. Crexi was the
only live ingest path actually working.

### Decommission steps (low-risk → high)

- **DC-1 — Delete LoopNet.** Remove code, 3 Celery beat entries, `loopnet_*` config fields, and
  **delete LoopNet Opportunity rows** from the DB. Subscription is already cancelled.
- **DC-2 — Remove HelloData.** Delete scraper/CLI/budget-tracker/config. Decouple
  `app/engines/market.py:154–276` from the `hellodata_*` fields so comps fall back gracefully to
  scraped Crexi fields + manual entry. Defer dropping the now-dead `hellodata_*` columns to a
  later migration (cheap to leave nullable).
- **DC-3 — Remove parcel + GIS pipeline.** County-GIS scrapers, parcel seed/enrich, geo
  matching, jurisdiction tagging. **Archive the code first** — tag a branch (e.g.
  `archive/parcel-intelligence`) or move to an `archive/` dir before deletion, so it can be
  resurrected without git spelunking.
- **DC-4 — Remove parcel/building/map/dedup UI.** Routes + templates listed above. Trim the nav.
- **DC-5 — Repoint KNN.** `market.py` currently keys on `jurisdiction` + parcel-derived sqft.
  After removal, source its inputs from Oppo-native fields (`unit_count`, `year_built`, building
  sqft, and a manually-entered jurisdiction/city). Also replace the bare `except Exception: pass`
  so a KNN failure is logged, not silent. Goal: comps keep working on the leaner data.
- **DC-6 — Fix the `hide_test` filter** so Crexi Oppos display (the test-data filter currently
  hides them alongside LoopNet).

### New builds (small follow-ons)

- **Crexi listing lifecycle.** A scheduled task that moves stale / expired / sold Crexi listings
  into an **Archived** Opportunity status — data retained, hidden from active views. Needs an
  `archived` (or lifecycle-status) field on `Opportunity` + a Celery beat task with a staleness
  rule (e.g. not seen in N days, or source marks sold).
- **Opportunity ↔ Broker link.** Add a broker association to `Opportunity` (FK or M2M) and a
  broker picker in the Oppo create/edit UI so **manually-created Oppos can be tied to a Broker**.
  Brokers already exist with normalization + dedup; this just wires the relationship + UI.

### Schema impact (update `docs/DATA_MODEL.md` when executed)

- `Opportunity`: add broker link; add archived/lifecycle status.
- Delete LoopNet `Opportunity` rows (data migration / one-shot script).
- Drop `parcel`, `listing_snapshot`, `hellodata_usage` models and their tables (staged).
- Defer dropping dead `hellodata_*` / GIS / jurisdiction columns on `Opportunity`.

---

## ui.py Split — 7 Sub-Routers (recomputed for 16k / 151)

The 151 routes still divide cleanly by domain. Estimates are approximate and **shrink after the
parcel decommission** — `data_intel` loses parcels/map/dedup/building; the whole split gets easier.

| New file | Est. lines | What's inside |
|---|---|---|
| `ui/settings.py` | ~900 | Root, splash, `/settings/*`, admin tasks |
| `ui/deals_pipeline.py` | ~2,600 | Deal list/CRUD, opportunities, opportunity wizard, **broker link** |
| `ui/data_intel.py` | ~900 (post-decommission) | Brokers + Crexi-sourced Oppos only — parcels/map/dedup/buildings deleted |
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

### Phase 1 — Decommission + quick wins

- **DC-1…DC-6** (parcel-intelligence decommission, above).
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
- Celery queue simplification (fewer workers once scraping shrinks to Crexi only).
- HTMX upgrade 1.9.x → 1.10+.
- Backward-compat alias cleanup (`DealModel`, `ScenarioResult`) once all callers updated.

---

## Open Decisions

1. **Canonical property-type list** — *Recommend the 8-item `building_form_fields` superset*
   (`Multifamily, Mixed Use, Commercial, Retail, Industrial, Single Family, Vacant Land, Other`)
   and map `opportunities.html` onto it. Business confirm before code.
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
