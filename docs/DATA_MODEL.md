# Data Model Reference

This document describes the entity model, data sources, reconciliation
logic, and field-level authority for the **market-data ingest layer** of
Vicinity Deals — parcels, opportunities, and the scrapers / APIs
that populate them. It is the data-layer counterpart of `FINANCIAL_MODEL.md`.

**Scope note**: Deal-side entities (Scenario, Project, OperationalInputs,
IncomeStream, CapitalModule, etc.) are documented in
`FINANCIAL_MODEL.md` alongside the math that consumes them. `unit_mix` is
JSONB on `Project` (not a separate table) — field reference in FINANCIAL_MODEL.md §4.8.

**Deprecated deal fields (2026-04-19):**
- `capital_modules.active_phase_end` — derived at compute time from
  `exit_terms.vehicle` via `_resolve_active_end_rank`.  The DB column is
  retained as a rollback-safety/write-through during the transition;
  drop in a follow-up Alembic migration.
- `draw_sources.active_to_milestone` — derived from the linked capital
  module's Exit Vehicle on save.  Engine ignores the user-supplied value.
  Same rollback posture as above.

**Last updated**: 2026-07-07

---

## 1. Entity Hierarchy

> **⚠️ Parcel intelligence DECOMMISSIONED (migration 0113, 2026-06-14).** The entire
> parcel/county-GIS subsystem was removed: `parcels` (446K rows) and `parcel_transformations`
> tables dropped; `opportunities.parcel_id`, `opportunities.parcel_conflicts_ack`, and
> `projects.parcel_id` columns dropped; parcel scrapers, seeding, enrichment, geo matching,
> and reconciliation code deleted. **Sections 2, 3, and 4 below describe the removed subsystem
> and are retained for historical reference only — they no longer reflect the live schema.**
> Physical attributes now live exclusively on `Opportunity` own-columns (no Parcel fallback).
> Pre-drop data backed up to `/root/backups` on VM 114. Kept: `Opportunity.apn` /
> `apn_normalized` and manual jurisdiction fields. KNN comps + JSON export/import read
> Opportunity own-columns. (See DC-5c in the parcel-decommission roadmap.)

The financial entities link as: Opportunity (opportunity_id FK, nullable) <- Project -> Deal/Scenario

Physical attributes (units, gba_sqft, year_built, lot_sqft, property_type) live as nullable columns on Opportunity. NULL = unknown (no county seed anymore). Non-null = user-entered or scraped (Crexi) value. Access via display_* properties only -- never raw columns.

> **Removed (migration 0072):** Building entity, buildings table, scraped_listings table (renamed to opportunities), deal_opportunities junction, project_parcels junction, opportunity_buildings junction, standalone unit_mix table (JSONB on Project now). ScrapedListing remains as a Python import alias only.
>
> **Removed (migration 0113):** Parcel entity + `parcels` table, ParcelTransformation + `parcel_transformations` table, `opportunities.parcel_id` (+FK), `opportunities.parcel_conflicts_ack`, `projects.parcel_id` (+FK). Parcel/GIS scrapers, seeding, enrichment, and reconciliation modules deleted.

| Entity | Table | Purpose | Key |
|---|---|---|---|
| **Opportunity** | `opportunities` | Unified investment target (scraped or manually created); was scraped_listings | `(source, source_id)` unique |
| **Broker** | `brokers` | Contact from listing source (Crexi/LoopNet) | `crexi_broker_id` (unique) |
| **IngestJob** | `ingest_jobs` | Telemetry record for a scrape run | `id` (UUID) |
| **DedupCandidate** | `dedup_candidates` | Potential duplicate listing pair pending review | `id` (UUID) |
| **MapPolygon** | `map_polygons` | Named geographic polygon for listing filtering (zone painter) | `slug` (unique) |

### 1.0b FLATS — the `flats` schema (migration 0125)

A **second product in the same database**, in its own Postgres schema. Screening, not
underwriting: can a fixed-dimension 4-unit attached townhome be legally and physically
placed on a given lot? Nothing in `public` references it and nothing in it references
`public` except `review_decisions` (org + reviewer). Architecture:
[Lot Analysis/FLATS_PLAN.md](../Lot%20Analysis/FLATS_PLAN.md); ORM:
[app/models/flats.py](../app/models/flats.py).

**This is not a revival of `parcels`.** Different schema, different keying, different
ingest. See the Archive note at the bottom of this document.

| Entity | Table | Purpose | Key |
|---|---|---|---|
| **FlatsRun** | `flats.runs` | One pipeline execution; records code + rule versions, designs and counties in scope | `id` (bigint) |
| **FlatsDesign** | `flats.designs` | Immutable snapshot of a catalog pod as a run used it | `key` = `id@version` |
| **FlatsLot** | `flats.lots` | A taxlot and every **design-independent** fact about it (envelope, fit frontier, slope, sewer, economics — JSONB `facts`) | `(county, tlid)` unique |
| **FlatsLotResult** | `flats.lot_results` | Verdict for one lot × one design × one run: tier, slack, binding constraints, site plan | `(lot_id, design_key, run_id)` |
| **FlatsRule** | `flats.rules` | Per-run snapshot of a resolved zoning value + the citation behind it | `(run_id, jurisdiction, zone, field)` |
| **FlatsClause** | `flats.clauses` | RASE-tagged sentence of code text; drives completeness and drift watch | `id` (clause slug) |
| **FlatsReviewDecision** | `flats.review_decisions` | Durable human verdict, replayed into every later run | partial unique on `(county, tlid, design_key, check_code)` where not superseded |

Three keying decisions, all expensive to retrofit and therefore made up front:

- **`(lot, design, run)` results.** Design-independent work is computed once on
  `flats.lots`; only the site plan and set-access checks fan out. Adding a tenth pod is a
  re-run of two stages, not a migration.
- **Runs are comparable.** Every result names its run, and every run names the code and
  rule-config versions behind it, so "which lots changed tier and why" is a join.
- **Decisions key on TLID, not on a row id.** The pipeline rebuilds `flats.lots` each run;
  a decision keyed on `lots.id` would evaporate with it and the review queue would reset.

Geometry: `SRID 2913` (NAD83(HARN) / Oregon North, **feet**) for working geometry, `4326`
for the display centroid. Requires PostGIS (migration 0124) — the Postgres image is built
from [docker/postgres-postgis.Dockerfile](../docker/postgres-postgis.Dockerfile), not the
upstream `postgis/postgis` image, which would downgrade glibc and invalidate text-index
collations.

### 1.1 Deal / Scenario / Project hierarchy (financial side)

The listing/parcel half of the schema above feeds into the financial half below. The canonical entities:

```
Deal ──┬── Scenario (= "Variant")          ← DB table: scenarios; ORM class: Scenario
       │       │
       │       ├── Project ─────────────── UseLine, IncomeStream, OperatingExpenseLine,
       │       │        │                  OperationalInputs, unit_mix (JSONB), Milestone
       │       │        ├── ProjectAnchor  ← cross-project timeline coupling (0..1)
       │       │        └── CapitalModuleProject ← per-project terms (junction)
       │       │
       │       ├── CapitalModule ───────── per-source identity (scenario-scoped)
       │       │        ├── WaterfallTier       ← per-project (nullable project_id)
       │       │        ├── WaterfallResult     ← per-project (nullable project_id)
       │       │        └── DrawSource          ← per-project (nullable project_id)
       │       │
       │       └── CashFlow, CashFlowLineItem, OperationalOutputs (scenario-level outputs)
```

| Entity | Table | Scope | Notes |
|---|---|---|---|
| **Deal** | `deals` | top-level investment thesis | ORM: `Deal` |
| **Scenario / Variant** | `scenarios` | one financial plan per Deal; carries N Projects | ORM: `Scenario` |
| **Project** | `projects` | individual development effort; own timeline/uses/sources | `scenario_id` FK |
| **CapitalModule** | `capital_modules` | a Source (lender + rate + carry type + exit terms) | scenario-scoped |
| **CapitalModuleProject** | `capital_module_projects` | **junction (added 0048)**: per-project amount, active window, `auto_size` | `(capital_module_id, project_id)` unique |
| **ProjectAnchor** | `project_anchors` | **new (0048)**: anchors one Project's start to another Project's milestone + offset | 0..1 per project |
| **WaterfallTier** | `waterfall_tiers` | per-project (0048); joined at Underwriting-rollup layer | `project_id` nullable during 0048 backfill window |
| **WaterfallResult** | `waterfall_results` | per-project | same |
| **DrawSource** | `draw_sources` | per-project | same |
| **UseLine** | `use_lines` | project-scoped | `source_capital_module_id` (0048) attributes engine-injected reserves to their originating Source; `eligible_module_ids` (0088) whitelists which Sources may fund this use. **Migration 0092** adds `is_auto_dev_fee` (bool), `dev_fee_pct` (Numeric 8,4), `dev_fee_basis` (`purchase_price` \| `tpc_excl_self`) for the auto Developer Fee row seeded on every new deal — engine recomputes `amount` each pass; UI exposes `%` only and locks `$`. See [FINANCIAL_MODEL.md §1.4](FINANCIAL_MODEL.md). |

**Multi-project rule (post-0048).** A Scenario may have N Projects. Each Source is identified once on the Scenario (its `CapitalModule` row) and attached to 1+ Projects via `CapitalModuleProject` junction rows. One junction row = project-scoped Source. Multiple junction rows on the same module = shared Source. Each project owns its own UseLines, IncomeStreams, OpEx, OperationalInputs, Milestones, WaterfallTiers, DrawSources.

**Scenario-level fields on `OperationalInputs` (per-project storage, scenario-wide semantics).** A handful of `OperationalInputs` columns are stored on every Project's row but are conceptually *one decision per Scenario*. The Deal Setup wizard and the Add Project drawer propagate these from the default project's row to every other project's row at write time. Direct edits to a non-default project's row will be overwritten on the next wizard run / drawer add.

| Column | What | Propagated by |
|---|---|---|
| `debt_types` | Selected debt stack (e.g. `["permanent_debt"]`) | Wizard Finish + Add Project drawer |
| `debt_structure` | Derived stack pattern (`perm_only`, `construction_and_perm`, `construction_to_perm`) | same |
| `debt_terms` | **Wizard staging only** — per-funder-type `rate_pct` / `amort_years` / `loan_type` / `ltv_pct` / `hold_term_years` / `dscr_min` JSON. Engine does NOT read this; it reads `CapitalModule.source` directly. Repopulates the wizard form on re-edit. | same |
| `debt_milestone_config` | Per-funder-type active_from / active_to / retired_by | same |
| `debt_sizing_mode` | `gap_fill` \| `dscr_capped` \| `dual_constraint` | same |
| `construction_floor_pct` | % of TPC held during construction | same |
| `operation_reserve_months` | Reserve months at stabilization (default 6) | same |
| `deal_setup_complete` | Wizard gate flag | same |

**Dropped columns (refactor 2026-04-29, alembic 0060).** Moved to per-perm-debt `CapitalModule.source` JSON:

- `OperationalInputs.hold_period_years` → `CapitalModule.source.hold_term_years` (required when `funder_type == "permanent_debt"`, Pydantic-validated)
- `OperationalInputs.dscr_minimum` → `CapitalModule.source.dscr_min` (optional; engine fallback `1.20` if unset)
- `OperationalInputs.perm_rate_pct` → `CapitalModule.source.interest_rate_pct`
- `OperationalInputs.perm_amort_years` → `CapitalModule.carry.amort_term_years` (or `source.amort_term_years` for flat carry)

Engine resolves deal-level horizon (stabilized phase length) via:

1. Exit/divestment milestone with resolvable date → `_apply_milestone_phase_overrides` sets stabilized length from `stabilized_start → exit_date`.
2. Else: `MAX(perm_debt.source.hold_term_years) × 12`.
3. Else: `operation_stabilized` milestone `duration_days // 30`.
4. Else: `60` (final fallback).

See `app/engines/cashflow.py::_resolve_horizon_months`.

**LTV** is *not* a top-level `OperationalInputs` column — it lives on `CapitalModule.source.ltv_pct`. Engine reads from `source` directly; `debt_terms.{funder_type}.ltv_pct` is wizard-staging mirror only. Any code reading `inputs.ltv_maximum_pct` is a bug; that column does not exist.

Per-project fields on `OperationalInputs` (genuinely per-project, never propagated): `unit_count_new`, `noi_stabilized_input`, `noi_escalation_rate_pct`, `asset_mgmt_fee_pct`, and the lease-up / construction / operation duration scalars used as fallbacks when milestones lack trigger chains.

**Shared-Source semantics (per Phase 2 product decision, 2026-04-21).** A Source shared across N Projects is *one contract identity* (one lender, one rate, one carry_type, one exit vehicle) with *per-project sizing*. Each project independently sizes its share against its own uses / DSCR / LTV — no cross-project constraint pooling. The junction row for `(module, project)` holds that project's amount / active window / auto_size flag. Total principal on the loan = Σ per-project junction amounts. Underwriting-layer combined DSCR / LTV across a shared Source are **informational notifications only**, not sizing constraints. UX intent: drag a Source chip onto a second Project to add a junction row; that project gets its own amount.

**Engine coupling (Phase 2, merged 2026-04-21).** The cashflow engine (`app/engines/cashflow.py`) loops per project:

1. `compute_cash_flows(scenario_id)` loads the scenario, resolves compute order via `anchor_resolver.ordered_projects` (topological if any `project_anchors` exist; else sorted by `created_at`).
2. For each project, `_compute_project_cashflow` captures `prev_outputs` for DSCR convergence, purges that project's prior rows only (`_purge_project_outputs`), loads capital modules via the junction (`_per_project_capital_modules`), and writes fresh `CashFlow` / `CashFlowLineItem` / `OperationalOutputs` rows scoped to `project_id`.
3. Engine-injected reserves (bridge IO carry, closing costs) carry `source_capital_module_id` pointing at the originating `CapitalModule` (Phase 2e).
4. `app/engines/underwriting_rollup.py` aggregates per-project rows into a scenario-level view (`rollup_cashflow`, `rollup_draws`, `rollup_sources`, `rollup_waterfall`, `rollup_irr`, `rollup_summary`) — pure aggregation, no new math.

For single-project scenarios (every production deal today) the loop runs once, identical math, byte-identical output (validated against `tests/phase2_baseline/` snapshots on 5 prod scenarios).

**`OperationalOutputs.equity_required` semantics (post 2026-04-25).** Two engines write this field along distinct paths:

- **Cashflow engine (per project, multi-project)**: `equity_required = max(0, Σ UseLines (excluding exit phase) − Σ debt module principal via junction)`. Uses Σ Uses (which includes Interest Reserve, Operating Deficit Reserve, Operating Reserve, capitalized-interest stubs) — *not* TPC. See [FINANCIAL_MODEL.md §3](FINANCIAL_MODEL.md) for the three-reserve tiled-timeline model (post-2026-06-03 reserves-spec-align). This is the target equity check the project's equity stack must bring at close. The cashflow engine writes one row per project; the rollup sums them.
- **Waterfall engine (single-project only)**: overwrites the default project's row with the richer `Σ |negative LP+GP capital calls|` from the actual waterfall allocation. For multi-project deals the waterfall *skips* this overwrite (the scenario-wide sum dumped onto one project's row produced wildly inflated numbers like $7.7M equity for a $2.7M project).

**Sources Gap (Underwriting KPI)** = `Σ Total Uses across projects − Σ junction-scoped Sources (debt + committed equity)`. Distinct from Equity Required:
- Equity Required = the raise target. Stays put as sponsor commits equity.
- Sources Gap = the remaining shortfall. Shrinks toward zero as equity dollars get entered into Owner Equity / Preferred Equity junction rows.

When no equity is yet committed (Owner Equity junction.amount = 0), the two numbers coincide. They diverge once any equity is committed.

**Still deferred (documented, code-visible, no UI yet):**

| Item | Trigger | Notes |
|---|---|---|
| **2c1 junction overlay** | UI coverage editor writes per-project amounts that diverge from `module.source.amount` | `_per_project_capital_modules` currently returns the unmodified module; overlaying `junction.amount` requires routing auto-sizing to read/write the junction directly (deeper refactor) |
| **2d1 anchor-driven date resolution** | Phase-B-follows-Phase-A UI request | `project_anchors` table + `anchor_resolver` exist; order is respected, but milestone-date-offset math is not yet computed |
| **2e1 reserve attribution for aggregates** | Per-Source reserve rollup display wants Operating Reserve + Lease-Up Reserve tagged | These aggregate across multiple modules; attribution needs a split or representative-module decision |
| **2f joint draw cadence** | First actual shared lender pool (>1 junction rows on one module) | At month-level engine resolution, joint vs independent produce identical numbers; meaningful only under day-level modeling. Independent path is correct-but-conservative until then. |

Read-side helpers already in `app/engines/cashflow.py`:

- `is_shared_source(session, capital_module_id) -> bool`
- `junction_amount_for(session, capital_module_id, project_id) -> Decimal | None`
- Rollup row includes `is_shared: bool` and `covered_project_ids: list[str]` for UI consumption.

### Relationship Cardinalities

- One Opportunity <- many Projects (lineage FK; physical data deep-copied at project create)

> Parcel relationships removed in migration 0113 (parcel decommission). Opportunities no
> longer link to a Parcel; physical data lives on Opportunity own-columns.

---

## 5. Ingest Pipeline

### 5.1 Crexi Path

```
CrxiScraper.fetch_all()
  → upsert_brokers()           # Broker + Brokerage tables
  -> upsert_opportunities()  # ON CONFLICT (source, source_id) DO UPDATE
  → deduplicate_batch()        # Address/unit/price scoring → DedupCandidate
  → _flag_saved_search_matches()
  # (building sync removed -- Building entity dropped in migration 0072)
```

### 5.4 Deduplication

`app/scrapers/dedup.py` scores listing pairs:

| Signal | Score |
|---|---|
| Address exact match | +1.0 |
| Address fuzzy (token Jaccard) | up to +0.95 |
| Unit count match | +0.15 |
| Price within 5% | +0.05 |

Results are stored as `DedupCandidate` records with status
`pending`/`duplicate_exact`/`duplicate_fuzzy`/`no_duplicate` for human
review at `/dedup/pending`.

---

## 6. Opportunity Fields

> **Note:** `ScrapedListing` is a Python import alias for `Opportunity` (`ScrapedListing = Opportunity`). Both reference the `opportunities` table (renamed from `scraped_listings` in migration 0072). All new code should import `Opportunity` from `app.models.opportunity`.

### Display-property pattern
Physical attributes live on `Opportunity` own-columns (broker-reported or user-entered). Access them only through the model's `display_*` properties — never read raw columns directly in templates or routes:

| Property | ORM column | Returns when NULL |
|---|---|---|
| `display_units` | `opportunity.units` | `None` |
| `display_sqft` | `opportunity.gba_sqft` | `None` |
| `display_year_built` | `opportunity.year_built` | `None` |
| `display_lot_sqft` | `opportunity.lot_sqft` | `None` |
| `display_property_type` | `opportunity.property_type` | `None` |

`NULL` means unknown. The **Parcel fallback was removed in migration 0113** (parcel decommission) — `display_*` now returns the own-column value or `None`, never a parcel value. Setting a column is a permanent user value. (Historical fallback behavior is in the Archive section.)

### 6.1 All Columns

**Identity**
| Column | Type | Source | Notes |
|---|---|---|---|
| `id` | UUID | Auto-generated | Primary key |
| `source` | String(100) | Ingest pipeline | `"crexi"`, `"loopnet"` |
| `source_id` | String(255) | Listing source | Source-specific listing ID |
| `source_url` | Text | Listing source | DB column name: `listing_url`. Nullable since migration 0123 — user-generated (non-scraped) projects have no listing URL |
| `raw_json` | JSON | Listing source | Complete raw payload |
| `ingest_job_id` | UUID FK | Ingest pipeline | Links to IngestJob telemetry |

**Location**
| Column | Type | Source | Notes |
|---|---|---|---|
| `address_raw` | Text | Listing source | As-scraped address string |
| `address_normalized` | Text | Ingest (`usaddress.tag`) | Normalized via usaddress parser |
| `street` | Text | Ingest | Street portion only |
| `street2` | Text | Listing source | Secondary address line |
| `city` | String(120) | Listing source | **Unreliable** — broker-provided metro name |
| `county` | String(120) | Listing source | Generally correct at county level |
| `state_code` | String(20) | Listing source | e.g., `"OR"` |
| `zip_code` | String(20) | Listing source | Reliable |
| `lat` | Numeric(10,7) | Listing source | Geocoded by Crexi/LoopNet |
| `lng` | Numeric(10,7) | Listing source | Geocoded by Crexi/LoopNet |

**Property Facts**
| Column | Type | Source | Displayed |
|---|---|---|---|
| `property_type` | String(120) | Listing source | List + detail |
| `sub_type` | ARRAY(String) | Listing source | Not displayed |
| `investment_type` | String(120) | Listing source | Not displayed |
| `asking_price` | Numeric(18,6) | Listing source | List + detail |
| `price_per_sqft` | Numeric(18,6) | Listing source | Detail |
| `price_per_unit` | Numeric(18,6) | Listing source | List + detail |
| `gba_sqft` | Numeric(18,6) | Listing source | List + detail (DB: `building_sqft`) |
| `net_rentable_sqft` | Numeric(18,6) | Listing source | Detail |
| `lot_sqft` | Numeric(18,6) | Listing source | List + detail |
| `year_built` | Integer | Listing source | List + detail |
| `year_renovated` | Integer | Listing source | Detail |
| `units` | Integer | Listing source | List + detail (DB: `unit_count`) |
| `buildings` | Integer | Listing source | Detail |
| `stories` | Integer | Listing source | Detail |
| `parking_spaces` | Integer | Listing source | Detail |
| `pads` | Integer | Listing source | Not displayed |
| `number_of_keys` | Integer | Listing source | Not displayed |
| `class_` | String(20) | Listing source | Detail |
| `zoning` | Text | Listing source | Detail |
| `apn` | String(100) | Listing source | Detail |

**Operating Metrics**
| Column | Type | Source | Displayed |
|---|---|---|---|
| `occupancy_pct` | Numeric(18,6) | Listing source | Detail |
| `cap_rate` | Numeric(18,6) | Listing source | List + detail (DB: `asking_cap_rate_pct`) |
| `proforma_cap_rate` | Numeric(18,6) | Listing source | List + detail |
| `noi` | Numeric(18,6) | Listing source | List + detail |
| `proforma_noi` | Numeric(18,6) | Listing source | List + detail |
| `tenancy` | String(50) | Listing source | Not displayed |
| `lease_term` | Numeric(18,6) | Listing source | Not displayed |
| `broker_co_op` | Boolean | Listing source | Not displayed |
| `ownership` | String(120) | Listing source | Not displayed |
| `is_in_opportunity_zone` | Boolean | Listing source | Not displayed |

**Metadata**
| Column | Type | Source | Notes |
|---|---|---|---|
| `listing_name` | String(255) | Listing source | |
| `description` | Text | Listing source | HTML stripped at ingest |
| `status` | String(100) | Listing source | Active, Sold, etc. |
| `listed_at` | DateTime | Listing source | |
| `first_seen_at` | DateTime | Ingest pipeline | DB: `seen_at` |
| `last_seen_at` | DateTime | Ingest pipeline | DB: `scraped_at` |
| `is_new` | Boolean | Ingest pipeline | |
| `archived` | Boolean | User action | |
| `is_favorited` | Boolean | User action | Starred by user; default `false`; auto-set `true` for oppos linked to a Deal via Project at migration 0073 |

**Opportunity metadata** (set when manually created or promoted)
| Column | Type | Source | Notes |
|---|---|---|---|
| `name` | String(255) | User | User-facing name override |
| `promotion_source` | String(20) | Ingest / User | `"manual"` for user-created; `"loopnet"` / `"crexi"` for scraped |
| `org_id` | UUID FK | System | Set on creation; required for visibility in opportunity pipeline |
| `notes` | Text | User | Deal context / seller notes |

**Reconciliation** (legacy parcel-matcher outputs — columns retained, no longer populated after migration 0113)
| Column | Type | Notes |
|---|---|---|
| `jurisdiction` | String(120) | **Live.** Now a manual / `city` copy (was parcel-derived). Powers the Opportunities-page jurisdiction filter. |
| `match_strategy` | String(30) | Dormant — parcel matcher removed. See Archive. |
| `match_confidence` | Numeric(4,3) | Dormant |
| `lot_size_mismatch` | Boolean | Dormant |
| `priority_bucket` | String(30) | Dormant — parcel classifier removed |

**Foreign Keys**
| Column | Target | Notes |
|---|---|---|
| `broker_id` | `brokers.id` | Set during Crexi/LoopNet ingest |
| `org_id` | `organizations.id` | Set on creation |
| `created_by_user_id` | `users.id` | Set on manual creation |

> **Removed FKs (migration 0072):** `property_id → buildings.id` (building entity dropped), `linked_project_id → opportunities.id` (deal_opportunities junction dropped). Deal linkage now flows through `Project.opportunity_id`. **Migration 0113** dropped `parcel_id → parcels.id` (parcel decommission).

---

## 8. Broker Fields

| Column | Type | Source | Displayed |
|---|---|---|---|
| `first_name` / `last_name` | String | Crexi | Listing detail + list |
| `phone` / `email` | String | Crexi | Listing detail |
| `brokerage.name` | String | Crexi | Listing list + detail |
| `crexi_broker_id` | String | Crexi | Internal matching only |

---

## 9. Where Data Appears

### 9.1 Opportunities Page (`/ui/opportunities`)

Three collapsible sub-tables, each with its own search input and "★ Favorited" toggle filter:

| Sub-table | Filter | Columns |
|---|---|---|
| **Active Deals** | Oppos linked to at least one Project/Scenario chain | ★, Name/Address, Units, Sqft, Type, Source, Last Seen, action |
| **Off Market** | `promotion_source = "manual"`, not in a Deal | same |
| **On Market** | `promotion_source IN ("loopnet","crexi","scraper")`, not in a Deal | same |

Physical attribute columns use `display_*` properties (Opportunity own-columns; Parcel fallback removed in migration 0113). Star column toggles `is_favorited` via `PATCH /ui/opportunities/{id}/favorite`.

### 9.2 Listing Detail Panel

All listing table fields plus: price/sqft, price/unit, net rentable sqft, occupancy, buildings, stories, parking spaces, class, zoning, APN, year renovated, description, broker phone/email.

### 9.6 API Endpoints

**`GET /listings`** -> `OpportunityRead` schema (all base fields + reconciliation fields: jurisdiction (live), and the now-dormant match_strategy / match_confidence / lot_size_mismatch).

---

## 12. Financial Entity Field Reference

Field-level schemas for financial entities not fully covered in Section 1.1. All types are Python/SQLAlchemy: Numeric(18,6) = 6-decimal money/pct; dict = JSONB column.

### 12.1 CapitalModule

Scenario-scoped Source identity (lender, rate, carry type, exit terms). Per-project amounts live on the CapitalModuleProject junction.

| Column | Type | Required | Notes |
|---|---|---|---|
| id | UUID | Yes | PK |
| scenario_id | UUID FK to scenarios | Yes | |
| label | str (255) | Yes | e.g. "Permanent Debt - Chase" |
| funder_type | FunderType enum | Yes | Legacy bridge field; `vehicle_type` + `equity_role` are canonical post-0085 |
| vehicle_type | str (50) or None | No | Snapshot from linked SourceVehicle: `equity`, `debt`, `forgivable_loan`, `grant`, `float_earnings`, `deferred_developer_fee` (VARCHAR expanded 20→50 in migration 0108) |
| equity_role | str (10) or None | No | Snapshot from linked SourceVehicle: `gp`, `lp`, or NULL for debt/grant |
| stack_position | int | Yes | Display order (0 = top) |
| source | dict or None | No | JSONB: sizing inputs - see 12.1a |
| carry | dict or None | No | JSONB: construction carry - see 12.1b |
| exit_terms | dict or None | No | JSONB: balloon, prepay, refi cap rate. Validated by `CapitalExitSchema`; `trigger` field is optional (`str \| None`) to accommodate DDF modules that store only `exit_type` + `vehicle` |
| eligible_use_tags | varchar[] | No | Whitelist of use `cost_category` tags this source may fund; empty = permissive (any use) |
| active_phase_start | str (60) or None | No | Legacy phase key; superseded by `active_from_milestone_id` (kept as fallback) |
| active_phase_end | str (60) or None | No | Legacy phase key; superseded by `active_to_milestone_id` (kept as fallback) |
| active_from_milestone_id | UUID FK or None | No | (0095) FK to `milestones.id`, `ON DELETE SET NULL`; rename-safe, trigger-chain aware activation start. When set, overrides `active_phase_start` at engine load time |
| active_to_milestone_id | UUID FK or None | No | (0095) FK to `milestones.id`, `ON DELETE SET NULL`; activation end |
| created_at | datetime | Yes | |
| updated_at | datetime | Yes | |

**12.1a source JSONB keys (perm/senior/bridge debt):**

| Key | Notes |
|---|---|
| amount | Principal (explicit) - overrides auto-sizing when set. For grant/forgivable_loan/tax_credit with `maximum` set, engine writes the resolved cap-consumption value here each compute pass. |
| maximum | Grant cap (grant / forgivable_loan / tax_credit only). When set, engine resolves `amount = min(maximum, sum of eligible Use buckets)` via `app/engines/grant_caps.py`. Set in tandem with `use_lines.eligible_module_ids` per-Use whitelist. See `FINANCIAL_MODEL.md` §2.11.1. |
| interest_rate_pct | Annual rate (%) |
| amort_term_years | Amortization schedule length |
| hold_term_years | IO or balloon period (required for permanent_debt) |
| dscr_min | DSCR floor for sizing; engine fallback 1.20 if absent |
| ltv_pct | LTV cap for sizing; defaults: acq 70%, perm 75% |
| debt_sizing_mode | gap_fill / dscr_capped / dual_constraint |
| refi_cap_rate_pct | Cap rate for refi LTV sizing; defaults to going-in cap if absent |
| loan_type | io_only / interest_reserve / capitalized_interest / pi |
| closing_costs_pct | Origination/closing fee as % of principal |
| draw_type | `fully_drawn` / `draw_down` / null. Overrides default principal-draw assumption for pre-op interest sizing. `fully_drawn` (bond, term note): full principal outstanding from day one → interest factor `rate/12 × N`. `draw_down` (construction loan): principal drawn evenly across pre-op months → interest factor `rate/12 × (N+1)/2`. Null falls back to carry-type convention: IR→draw_down, CI→fully_drawn. Read by both principal solve and IR Use line writer; see `FINANCIAL_MODEL.md` §2.2. |

**12.1b carry JSONB keys:**

Two formats coexist. The engine reads whichever is present; `phases` takes precedence.

*Flat format* (simple two-phase):

| Key | Notes |
|---|---|
| carry_type | `io_only` / `interest_reserve` / `capitalized_interest` / `pi` |
| rate_pct | Annual carry rate (may differ from permanent rate) |
| amort_term_years | Amortization years for `pi` carry type |
| construction_carry_type | If present, overrides `carry_type` during construction window |
| operation_carry_type | If present, overrides `carry_type` during operations window |

*Phases format* (engine multi-phase):

```json
{
  "phases": [
    {"name": "construction", "carry_type": "interest_reserve", "io_rate_pct": 7.0},
    {"name": "operation",    "carry_type": "pi", "io_rate_pct": 6.5, "amort_term_years": 30}
  ]
}
```

Phase `name` is always `construction` or `operation`. See `FINANCIAL_MODEL.md` Appendix C for rate resolution precedence.

**12.1c source JSONB keys — `float_earnings` vehicle type:**

| Key | Notes |
|---|---|
| parent_module_id | UUID of the capital module whose proceeds earn float (must have `draw_type == "fully_drawn"` and `balance_earns_interest == true`) |
| yield_pct | Annual yield %; engine uses linear-depletion model over construction months |
| waterfall_milestone_id | UUID of the milestone at which total earnings hit the GP/LP waterfall as a lump sum. Legacy key `paydown_milestone_id` is also read for backward compat. |
| amount | Written back by engine after each compute (= `FloatEarningsResult.total_earnings`); not user-entered |

`float_earnings` modules are excluded from the Sources = Uses gap and from source-routing eligibility (`source_routing.py`). See `FINANCIAL_MODEL.md` Appendix I.

**12.1d source JSONB keys — `deferred_developer_fee` vehicle type:**

| Key | Notes |
|---|---|
| amount | Auto-sized by `_auto_size_ddf_module()` to fill the residual Sources = Uses gap after debt modules are sized, capped at the total dev fee use line amount. Can also be set manually. |
| auto_size | Bool; when `true`, engine sets `amount` each compute pass (same mechanic as `auto_size` on debt modules) |

The DDF module's `amount` becomes the opening balance for `OperationalOutputs.dev_fee_balance_series` — it represents what was contributed as a capital source and will be repaid from operating cash flows. This is distinct from `dev_fee_binding_context["deferred"]` (total developer fee deferred, which may be larger). See `FINANCIAL_MODEL.md` Appendix I.8.

---

### 12.1c CapitalModuleProject (`capital_module_projects`)

Junction row attaching a `CapitalModule` (scenario-scoped Source identity) to one of the scenario's projects. Single-project deals have one junction row per module; multi-project deals can attach a shared Source to multiple projects, each with its own amount, activation window, and milestone FKs.

| Column | Type | Required | Notes |
|---|---|---|---|
| id | UUID | Yes | PK |
| capital_module_id | UUID FK to capital_modules | Yes | ondelete=CASCADE |
| project_id | UUID FK to projects | Yes | ondelete=CASCADE; `(capital_module_id, project_id)` unique |
| amount | Numeric or None | No | Per-project principal override (Phase 2c1); when null, falls back to `module.source["amount"]` |
| auto_size | bool | No | Per-project auto-size flag |
| active_from | str (60) or None | No | Legacy phase key; overrides module-level `active_phase_start` for this project |
| active_to | str (60) or None | No | Legacy phase key; overrides module-level `active_phase_end` for this project |
| active_from_milestone_id | UUID FK or None | No | (0096) FK to `milestones.id`, `ON DELETE SET NULL`. Per-project activation start that points at a milestone on **this project** (not scenario-wide). Highest-priority source for activation timing at engine load |
| active_to_milestone_id | UUID FK or None | No | (0096) FK to `milestones.id`, `ON DELETE SET NULL`. Per-project activation end |
| created_at | datetime | Yes | |

**Activation timing precedence (engine load, post-0096):**

1. Junction FK (`capital_module_projects.active_from/to_milestone_id`) — per-project override, multi-project aware
2. Module FK (`capital_modules.active_from/to_milestone_id`) — scenario-level default
3. Legacy string field (`active_phase_start` / `active_phase_end`) — fallback for un-migrated deals

`_per_project_capital_modules` in `app/engines/cashflow.py` resolves the FK→milestone_type at load time and writes it into the in-memory `module.active_phase_start` so downstream engine helpers (`_loan_pre_op_months`, `_APS_TO_USE_PHASE` lookups, refi activation) automatically use the rename-safe, trigger-chain-aware value.

---

### 12.2 WaterfallTier

Defines one distribution tier in the waterfall stack. Tiers are evaluated in priority order each period.

| Column | Type | Required | Notes |
|---|---|---|---|
| id | UUID | Yes | PK |
| scenario_id | UUID FK to scenarios | Yes | |
| project_id | UUID FK to projects or None | No | Nullable during Phase 1 backfill window |
| capital_module_id | UUID FK to capital_modules or None | No | Links tier to its funding source |
| priority | int | Yes | Lower = higher priority |
| tier_type | WaterfallTierType enum | Yes | See Section 13.2 |
| irr_hurdle_pct | Numeric or None | No | Required for irr_hurdle_split type |
| lp_split_pct | Numeric | Yes | LP share (0-100) |
| gp_split_pct | Numeric | Yes | GP share (0-100) |
| description | str (500) or None | No | |
| max_pct_of_distributable | Numeric or None | No | DDF only: max % of period cash for this tier |
| interest_rate_pct | Numeric or None | No | DDF only: accrual rate on unpaid balance |
| updated_at | datetime | Yes | |

---

### 12.3 Milestone

Pre-close milestones belong to an Opportunity; post-close milestones belong to a Project. Exactly one of opportunity_id / project_id must be set (DB CHECK constraint).

| Column | Type | Required | Notes |
|---|---|---|---|
| id | UUID | Yes | PK |
| trigger_milestone_id | UUID FK to milestones or None | No | Self-ref. If set: start = trigger.end_date + trigger_offset_days. If NULL: anchor milestone uses target_date. |
| trigger_offset_days | int | Yes | Days after trigger end date this milestone starts. Default 0. |
| opportunity_id | UUID FK to opportunities or None | No | Set for pre-close milestones |
| project_id | UUID FK to projects or None | No | Set for post-close milestones |
| milestone_type | MilestoneType enum | Yes | See Section 13.3 |
| duration_days | int | Yes | Phase length in days; 0 = same day as trigger |
| target_date | date or None | No | Overrides duration-based positioning when set |
| sequence_order | int | Yes | 1-based ordering within the project milestone sequence |
| label | str (255) or None | No | Human-readable display override |
| created_at | datetime | Yes | |
| updated_at | datetime | Yes | |

**Computed methods (not stored, resolved at runtime):**
- computed_start(milestone_map) - walks the trigger chain to a calendar date
- computed_end(milestone_map) - computed_start + duration_days
- is_anchor property - True when trigger_milestone_id is NULL

**Important:** Deals created before commit 5d5caf4 may have milestones with trigger_milestone_id = NULL even though they were intended as chained. Engine falls back to OperationalInputs.*_months scalars when trigger chain is broken. One-shot backfill script needed (see Section 11 / CLAUDE.md known issues).

**Phase plan extraction (`app/engines/phase_plan.py`):**

Per-project phase boundaries are not stored on the Milestone table — they are derived at runtime by `build_project_phase_windows(project_type, inputs, milestones, capital_modules)`. The function wraps the cashflow engine's `_build_phase_plan` to fold cumulative phase durations into a list of `PhaseWindow(period_type, start_month, end_month, duration_months)` records using 1-based absolute month indices. The investor Excel export registers each window as named workbook cells (`p<n>_phase_<phase>_start_month`, `..._end_month`, `..._duration_months`) plus two meta-cells (`p<n>_perm_origination_month`, `p<n>_total_horizon_months`). See `FINANCIAL_MODEL.md` §F.1.8 for the full catalog.

---

### 12.4 UnitMix

> **Removed (migration 0072).** The standalone `unit_mix` DB table is dropped. `unit_mix` is now a **JSONB column on `projects`** — a list of unit-type dicts deep-copied from the Opportunity at Project creation. The `UnitMix` ORM class in `deal.py` is a tombstone stub (no `Base`, no table registration). See §13.7 for strategy values and `FINANCIAL_MODEL.md §4.8` for the full field schema and cashflow engine integration.

**JSONB element shape (Project.unit_mix[]):**

| Field | Type | Notes |
|---|---|---|
| `label` | str | e.g. "1BR/1BA - Renovated" |
| `unit_count` | int | Number of units of this type |
| `avg_sqft` | Numeric | Average square footage |
| `beds` | Numeric(4,1) | 0-4+ in 0.5 increments |
| `baths` | Numeric(4,1) | 0-3+ in 0.5 increments |
| `in_place_rent_per_unit` | Numeric | Current tenant rent |
| `market_rent_per_unit` | Numeric | Market rent (LTL target) |
| `post_reno_rent_per_unit` | Numeric | value_add_renovation only |
| `unit_strategy` | str | base_escalation / ltl_catchup / value_add_renovation |

**Derived building totals (for Excel export and metrics):**

| Total | Source | Notes |
|---|---|---|
| Total units | `Σ unit_mix[].unit_count` | Captured per row at pro forma import or in the unit-mix editor |
| Net rentable sq ft | `Σ (unit_mix[].unit_count × unit_mix[].avg_sqft)` | Computed at read time; no separate column |
| Gross building sq ft | **stubbed** | No active capture path. Previously collected via the wizard's "Building Data Needed" step (removed 2026-05-12). Re-introduce when a workflow needs it; Excel exports currently leave the cell blank or echo net rentable. |

### 12.5 DrawSource

One row per source per project. Drives the self-referential draw-schedule engine.

| Column | Type | Required | Notes |
|---|---|---|---|
| id | UUID | Yes | PK |
| scenario_id | UUID FK to scenarios | Yes | ondelete=CASCADE |
| project_id | UUID FK to projects or None | No | ondelete=CASCADE |
| sort_order | int | Yes | Display + draw order |
| label | str (255) | Yes | |
| source_type | str | Yes | equity or debt |
| draw_every_n_months | int | Yes | Default 1 |
| annual_interest_rate | Numeric | Yes | Default 0 |
| active_from_milestone | str (60) | Yes | Milestone key that activates draws |
| active_to_milestone | str (60) | Yes | Milestone key that deactivates draws |
| active_from_offset_days | int | Yes | Days offset from active_from milestone; default 0 |
| active_to_offset_days | int | Yes | Days offset from active_to milestone; default 0 |
| total_commitment | Numeric or None | No | None = auto-sized to total drawn |
| funder_type | str (60) or None | No | Denormalized from CapitalModule for display |
| capital_module_id | UUID FK to capital_modules or None | No | ondelete=SET NULL |
| created_at | datetime | Yes | |

---

### 12.6 SourceVehicle (`source_vehicles`)

Unified table replacing the former `org_source_vehicles` + `user_source_vehicles` two-table pattern (migration 0085). One row = one reusable funding source template (a lender product, equity fund, grant program, etc.) scoped to an org or individual user.

| Column | Type | Required | Notes |
|---|---|---|---|
| id | UUID | Yes | PK |
| scope | str (10) | Yes | `org` or `user` — ownership level |
| owner_id | UUID | Yes | FK to `organizations.id` or `users.id` depending on `scope` |
| label | str (200) | Yes | Human name; unique per (scope, owner_id) |
| vehicle_type | str (50) | Yes | Canonical 6-value vocabulary (`app/schemas/vocab.py::VEHICLE_TYPES`, derived from the `VehicleType` ORM enum): `equity`, `debt`, `forgivable_loan`, `grant`, `float_earnings`, `deferred_developer_fee`. VARCHAR widened 20→50 in migration 0122 |
| equity_role | str (10) or None | No | `gp` or `lp` — only set when `vehicle_type = equity` |
| eligible_use_tags | varchar[] | No | Whitelist of use `cost_category` tags; empty = permissive |
| interest_rate_pct | Numeric or None | No | Annual rate for debt/forgivable_loan vehicles |
| carry_type | str (30) or None | No | `io_only`, `interest_reserve`, `capitalized_interest`, `pi` |
| day_count_convention | str (20) | Yes | Default `actual_360` |
| source_config | dict or None | No | JSONB sizing defaults (same keys as 12.1a) copied to CapitalModule.source on attach |
| carry_config | dict or None | No | JSONB carry template — see 12.6a below |
| exit_config | dict or None | No | JSONB exit defaults copied to CapitalModule.exit_terms on attach |
| created_at / updated_at | datetime | Yes | |

**12.6a carry_config JSONB structure:**

The wizard stores custom carry schedules under the `schedule` key:

```json
{
  "schedule": [
    {
      "label": "Construction",
      "carry_type": "interest_reserve",
      "duration": {"type": "months", "months": 24},
      "rate_pct": 7.0
    },
    {
      "label": "Operations",
      "carry_type": "pi",
      "duration": {"type": "remainder"},
      "rate_pct": 6.5,
      "amort_term_years": 30
    }
  ]
}
```

`duration.type` is `months` (fixed count), `milestone` (until a named milestone — `duration.milestone_key` set), or `remainder` (balance of loan term). When `schedule` is absent, `carry_config` may hold flat keys matching 12.1b.

The `schedule` array is the UI template stored on the vehicle. When a vehicle is attached to a deal, `carry_config` is copied to `CapitalModule.carry` for engine consumption (engine format uses `phases` — see FINANCIAL_MODEL.md Appendix C).

**Key invariant.** `SourceVehicle` is a *template*; attaching it to a deal creates a `CapitalModule` whose `vehicle_type` and `equity_role` columns are snapshots copied at attach time. Changes to the template do not retroactively update existing modules.

---

### 12.7 CapitalDrawEvent (`capital_draw_events`)

Audit trail of capital draws produced by each engine run (migration 0087). Prior rows for the scenario are purged and re-inserted on every `compute_cash_flows` call.

| Column | Type | Required | Notes |
|---|---|---|---|
| id | UUID | Yes | PK |
| scenario_id | UUID FK to scenarios | Yes | ondelete=CASCADE |
| project_id | UUID FK to projects or None | No | ondelete=CASCADE; NULL = scenario-level event |
| period | int | Yes | Month index within the cashflow timeline |
| period_type | str (60) or None | No | Phase label (e.g. `construction`, `operation_stabilized`) |
| amount | Numeric | Yes | Draw amount (positive = funding in) |
| allocation_reason | str (40) | Yes | Default `period_funding` |
| use_line_label | str (255) or None | No | Use line being funded, if applicable |
| created_at | datetime | Yes | |

---

### 12.8 UseLineSourceFeeBasis (`use_line_source_fee_basis`)

Join table recording per-`(UseLine × CapitalModule)` fee-basis inclusion decisions for **user-added custom Uses** (migration 0103, multi-source dev fee). Standard auto-generated cost categories (acquisition, hard_costs, soft_costs, financing_fees, interest_reserve, operating_reserves, developer_overhead, consulting_fees) are handled by the Source Vehicle's `basis_exclusions` flag list instead — no row here. If no row exists for a pair where the Vehicle has `fee_terms` set, the engine treats it as a *pending decision* and surfaces it in the explainer modal. ORM: `UseLineSourceFeeBasis` in `app/models/capital.py`.

| Column | Type | Required | Notes |
|---|---|---|---|
| use_line_id | UUID FK to use_lines | Yes | Composite PK; ondelete=CASCADE |
| capital_module_id | UUID FK to capital_modules | Yes | Composite PK; ondelete=CASCADE |
| included_in_basis | bool | Yes | Default `false` — is this custom Use included in the module's fee basis |
| set_at | datetime | Yes | Server default NOW() |

---

### 12.9 Gap Adjustment slider rows (no dedicated table)

The Gap Adjustment slider feature stores **no table of its own** — it materializes reserved-label *phantom rows* in three existing tables when the user moves a slider (`POST /api/models/{id}/sliders`, `app/api/routers/models.py`). Reserved labels are the single source of truth in `app/schemas/gap_adjustment_names.py`; the API blocks users from creating/renaming lines into or out of these exact labels:

| Reserved label | Phantom row lives in |
|---|---|
| `Gap Adjustment — Revenue` | `income_streams` |
| `Gap Adjustment — OpEx` | `operating_expense_lines` |
| `Gap Adjustment — Purchase Price` | `use_lines` (acquisition phase; negative amounts allowed) |
| `Gap Adjustment — NOI` | `operating_expense_lines` (NOI income mode only) |

Rows persist (potentially negative) so the adjusted state survives across sessions. Migration 0094 dedupes historical duplicate phantom rows and adds **partial unique indexes** enforcing one phantom row per `(project_id, label)` — concurrent slider POSTs previously raced the SELECT-then-INSERT upsert and produced `MultipleResultsFound`. Identification is exact string match on `label`; UI applies yellow highlighting and the "balanced with adjustments" pill from the same names. See `FINANCIAL_MODEL.md` Appendix E for slider math.

---

## 13. Enum Reference

Complete valid values for all enums in the financial data model.

### 13.1 FunderType

| Value | Meaning |
|---|---|
| permanent_debt | Amortizing long-term loan, no exit trigger |
| senior_debt | Senior secured debt (general) |
| mezzanine_debt | Subordinated to senior debt |
| bridge | Short-term bridge loan |
| construction_loan | Funds construction phase |
| pre_development_loan | Pre-closing costs (entitlements, design, due diligence) |
| acquisition_loan | Funds acquisition phase at LTV%; sized as P = acq_costs x LTV / 100 |
| soft_loan | Below-market governmental/nonprofit debt |
| bond | Construction-to-perm converting loan |
| preferred_equity | Equity with preferred return ahead of common |
| common_equity | Common equity (LP/GP splits apply) |
| owner_loan | Sponsor-provided debt |
| owner_investment | Sponsor equity contribution |
| grant | Non-repayable grant funds |
| tax_credit | Tax credit equity (LIHTC etc.) |
| other | Retained for backend compatibility |

### 13.2 WaterfallTierType

| Value | Meaning |
|---|---|
| debt_service | Debt service payment tier |
| pref_return | LP preferred return (e.g. 7% on committed equity) |
| return_of_equity | Return of LP capital contributions |
| catch_up | GP catch-up after LP pref is met |
| irr_hurdle_split | Split changes at IRR hurdle (e.g. 60/40 above 12%) |
| deferred_developer_fee | Unpaid portion of developer fee paid from distributions |
| residual | Everything remaining after higher-priority tiers exhausted |

### 13.3 MilestoneType

| Value | Phase | Notes |
|---|---|---|
| offer_made | Pre-close | Opportunity-level |
| under_contract | Pre-close | Opportunity-level |
| close | Pre-close | Last pre-close milestone |
| pre_development | Post-close | Entitlements, design, permits |
| construction | Post-close | |
| operation_lease_up | Post-close | Income ramps toward stabilized occupancy |
| operation_stabilized | Post-close | Fully leased; hold period |
| divestment | Post-close | Exit event |

### 13.4 UseLinePhase

| Value | When used |
|---|---|
| acquisition | Purchase price, closing costs |
| pre_construction | Pre-dev costs during entitlement |
| construction | Hard costs, soft costs, contingency |
| renovation | Reno costs for value-add |
| conversion | Change-of-use costs |
| operation | Reserves funded at stabilization |
| exit | Selling costs, payoff penalties at disposition |
| other | Catch-all |

### 13.5 ProjectType / ProposedUse

> **Removed (migration 0072):** `Project.deal_type` (string) and `Scenario.project_type` (enum) are both dropped.

**Current schema (post-0072):**

| Attribute | Column | Location | Notes |
|---|---|---|---|
| What the property *is today* | `project_type` | `Opportunity` | Enum: see values below |
| What this deal *proposes to do* | `proposed_use` | `Project` | String; values include `hold_existing`, `value_add_renovation`, `redevelop`, `ground_up_new`, `land_bank` |

`ProjectType` enum values (for `opportunity.project_type`):

| Value | Strategy |
|---|---|
| acquisition | Stabilized acquisition / pure hold |
| value_add | Acquire + renovate + stabilize |
| conversion | Change-of-use conversion |
| new_construction | Ground-up development |

### 13.6 IncomeStreamType

| Value |
|---|
| residential_rent |
| commercial_rent |
| parking |
| laundry |
| utility_water, utility_electric, utility_gas, utility_internet |
| storage |
| pet_fee |
| deposit_forfeit |
| other |

### 13.7 UnitMix strategy values

| Value | Behavior |
|---|---|
| base_escalation | Rent escalates at escalation_rate_pct_annual; no gap chasing |
| ltl_catchup | Accelerated escalation toward catchup_target_rent; reverts to base rate once target reached |
| value_add_renovation | Post-renovation rent is post_reno_rent_per_unit; pre-reno is in_place_rent_per_unit |

### 13.8 STANDARD_OPEX_CATEGORIES

Defined in `app/models/deal.py`. The investor export groups `OperatingExpenseLine` rows by exact category string. The pro forma import parser maps arbitrary source labels to this vocabulary via LLM confidence scoring.

| Category | Notes |
|---|---|
| Real Estate Taxes | Property tax, special assessments |
| Insurance | Property & liability premiums |
| Jurisdiction Fees | Municipal levies — Gresham Police/Fire/Parks, city assessments |
| Property Management | On-site and off-site management fees |
| Utilities — Water/Sewer | |
| Utilities — Electric | |
| Utilities — Gas | |
| Utilities — Trash | Garbage removal |
| Repairs & Maintenance | |
| Marketing & Leasing | Advertising, leasing commissions |
| Administrative | Office supplies, bank fees |
| Payroll | Salaries, benefits, payroll taxes |
| Landscaping & Snow Removal | |
| Pest Control | |
| Cleaning & Janitorial | |
| Security | |
| Resident Services | Tenant events, social services |
| Legal | Legal fees, professional fees, licenses |
| Source Compliance | Funder monitoring — LIFT, OHCS, bond covenant, HUD compliance |
| Bank/Software Fees | Bank charges, PM software |
| Unit Turnover | Between-tenant make-ready costs |
| Other | Catch-all |

---

## 14. Deal Change History (scenario_snapshots)

### 14.1 Overview

Every explicit Compute run inserts an immutable `scenario_snapshots` row and increments `Scenario.version`. Snapshots enable:
- Audit trail of what inputs were active at each compute
- Diff view (input changes + cascading output metric deltas) between any two consecutive snapshots
- Full revert to any prior snapshot state (wipes current child rows, re-inserts from snapshot JSON)

Snapshot creation is automatic; no manual save button. `Scenario.version` is the canonical version number that appears in both the history drawer and the Excel investor export Version/Audit tab.

### 14.2 scenario_snapshots table

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| scenario_id | UUID FK → scenarios | CASCADE DELETE |
| version | int | Mirrors Scenario.version at snapshot time; 1-indexed, monotonically increasing |
| created_at | timestamptz | Server default NOW() |
| triggered_by | str(20) | `"compute"` (current); `"manual"` reserved |
| label | text or null | Reserved for future named checkpoints |
| inputs_json | JSONB | Full serialized scenario inputs (~20–30 KB). See 14.3 |
| outputs_json | JSONB | Key metric snapshot. See 14.4 |

### 14.3 inputs_json structure

Produced by `app/exporters/snapshot.serialize_inputs()`. Top-level keys mirror the financial entity types:

```
{
  "operational_inputs": { ...scalar fields... },
  "use_lines": [ {id, category, label, amount, phase, ...}, ... ],
  "income_streams": [ {id, label, stream_type, amount_per_unit_monthly, ...}, ... ],
  "expense_lines": [ {id, label, category, amount_annual, ...}, ... ],
  "capital_modules": [ {id, label, funder_type, source, carry, exit_terms, ...}, ... ],
  "waterfall_tiers": [ {id, label, tier_type, ...}, ... ],
  "draw_sources": [ {id, ...}, ... ],
  "unit_mix": [ {id, unit_type, count, ...}, ... ],
  "milestones": [ {id, milestone_type, duration_months, ...}, ... ]
}
```

Amounts serialized as float (Decimal → float at snapshot time). Schema-version fields stripped on revert to avoid forward-compat issues.

### 14.4 outputs_json structure

Captured from `OperationalOutputs` immediately after compute completes:

```json
{
  "dscr": 1.31,
  "project_irr_levered": 0.158,
  "noi_stabilized": 163800.0,
  "equity_required": 487000.0,
  "total_project_cost": 1840000.0,
  "cap_rate_on_cost": 0.062
}
```

### 14.5 Diff format

`app/exporters/snapshot.build_diff(snap_before, snap_after)` returns:

```json
{
  "version_before": 2,
  "version_after": 3,
  "input_changes": [
    {
      "entity": "IncomeStream",
      "label": "Gross Revenue (Unit A)",
      "field": "amount_per_unit_monthly",
      "before": 1200,
      "after": 1450
    }
  ],
  "output_changes": {
    "dscr": { "before": 1.18, "after": 1.31 },
    "project_irr_levered": { "before": 0.142, "after": 0.158 }
  }
}
```

### 14.6 Revert behavior

Revert (`POST /ui/models/{id}/history/{snapshot_id}/revert`) replaces all current scenario inputs with the snapshot's `inputs_json`:
1. Delete CashFlowLineItems, WaterfallResults, OperationalOutputs
2. Delete UseLines, IncomeStreams, ExpenseLines, DrawSources, WaterfallTiers, CapitalModules, UnitMix, Milestones, OperationalInputs
3. Re-insert all entities from `inputs_json`
4. Re-insert `capital_module_projects` junction rows (amount + auto_size flag)
5. Redirect to model builder — user must re-run Compute to regenerate outputs

Partial revert is not supported. `Scenario.version` is not decremented on revert; next Compute will increment to the next sequential version.

---

## 15. Email-to-Deal Pipeline (inbound_emails, email_deal_suggestions)

Tables backing the email ingest feature (`app/models/email_ingest.py`; task in `app/tasks/email_ingest.py`, routes in `app/api/routers/email_ingest.py`). A webhook creates an `InboundEmail` row per email received at `deals@viciniti.deals`; a Celery task extracts fields (local Ollama LLM) into `EmailDealSuggestion` rows and parks at `pending_review` — the task creates **nothing** deal-side (post-migration 0084). Deal/Scenario/Project creation happens only when a user submits the review page. Proforma attachments are staged in **Redis** (`proforma:{task_id}:*` keys, 7-day TTL), not in these tables.

### 15.1 inbound_emails

| Column | Type | Required | Notes |
|---|---|---|---|
| id | UUID | Yes | PK |
| org_id | UUID FK to organizations | Yes | ondelete=CASCADE |
| received_at | timestamptz | Yes | Server default NOW() |
| sender_email | Text | Yes | |
| sender_name | Text or None | No | |
| subject | Text or None | No | |
| body_text | Text or None | No | Extracted plain-text body |
| raw_mime_b64 | Text or None | No | Base64 raw MIME as fetched from the Resend API |
| status | str (30) | Yes | `InboundEmailStatus`: `pending`, `processing`, `pending_review`, `opportunity_created`, `failed`, `spam` |
| opportunity_id | UUID FK to opportunities or None | No | ondelete=SET NULL; set once deal creation runs |
| proforma_task_ids | JSONB (list) | Yes | Task IDs of Redis-staged proforma attachments |
| error_message | Text or None | No | |
| debug_log | Text or None | No | Extraction trace; download gated to `EMAIL_INGEST_DEBUG_EMAIL` operator |
| attachments_meta | JSONB (list) | Yes | Attachment metadata (bytes stripped — payload lives in Redis) |

### 15.2 email_deal_suggestions

One row per extracted field awaiting accept/reject on the review page. Accepted `broker_name` / `broker_email` suggestions resolve to a `Broker` via `find_or_create_broker_by_email` and link the created Opportunity (`broker_id`).

| Column | Type | Required | Notes |
|---|---|---|---|
| id | UUID | Yes | PK |
| inbound_email_id | UUID FK to inbound_emails | Yes | ondelete=CASCADE |
| opportunity_id | UUID FK to opportunities or None | No | ondelete=CASCADE |
| field_path | Text | Yes | Target field (e.g. `address`, `asking_price`, `unit_count`, `property_type`, `broker_name`, `broker_email`) |
| suggested_value | Text or None | No | |
| confidence | float or None | No | LLM extraction confidence |
| source_type | str (40) | Yes | `SuggestionSourceType`: `email_body`, `proforma_xlsx`, `llm_extraction` |
| accepted | bool or None | No | NULL = undecided, true/false = user decision |

---

## 16. Supporting Tables Index

One-line reference for the remaining tables in `Base.metadata` not given a full section above (deal-side entities are detailed in `FINANCIAL_MODEL.md`; this index exists so every live table is discoverable from this doc). ORM module in parentheses.

| Table | Purpose |
|---|---|
| `organizations`, `users` | Org + user auth entities (`org.py`); first registered user auto-creates "Default Organization" |
| `org_invites` | Pending org membership invitations (`org.py`) |
| `project_visibilities` | Per-user visibility grants; NOTE: its `project_id` column references `opportunities.id` — legacy naming from the projects→opportunities rename (`org.py`) |
| `org_settings`, `user_settings` | Org/user field-default system: Type 1 org-set, Type 2 org-default, Type 3 user-override (`settings.py`; see `app/settings/defaults.py`) |
| `org_deal_type_defaults`, `user_deal_type_defaults` | Per-deal-type default bundles at org / user scope (`settings.py`) |
| `scenario_templates` | Reusable scenario templates managed in Settings (`scenario_template.py`) |
| `source_vehicles` | See §12.6 |
| `cash_flows`, `cash_flow_line_items`, `operational_outputs` | Engine outputs: per-period cashflow rows, line-item detail, and computed KPI blob per project — purged and re-written each compute (`cashflow.py`) |
| `operating_expense_lines` | Project-scoped OpEx lines; field detail in `FINANCIAL_MODEL.md` §4 (`deal.py`) |
| `sensitivities`, `sensitivity_results` | Sensitivity-sweep definitions + per-cell results; ORM classes `Sensitivity` / `SensitivityResult`, renamed from the old Scenario naming (`scenario.py`) |
| `portfolios`, `portfolio_projects`, `gantt_entries` | Portfolio grouping of deals + junction + computed Gantt bars (`portfolio.py`) |
| `permit_stubs` | Permit records attached to a Project (`project.py`) |
| `brokerages`, `broker_disciplinary_actions` | Brokerage firms; per-case Oregon disciplinary records scraped onto brokers (`broker.py`) |
| `saved_filters` | Per-user, per-page named query-string snapshots for filter bars (`saved_filter.py`) |
| `saved_search_criteria` | Saved-search match criteria applied at ingest to flag matching listings (`ingestion.py`) |
| `export_jobs` | Async investor-export job tracking: progress states + cached-build resend (`export_job.py`) |
| `field_conflict_log` | Field-level disagreement log written during manual dedup merges (`field_conflict_log.py`) |
| `realie_usage` | Realie.ai monthly API call budget tracking (`realie_usage.py`) |
| `workflow_run_manifests` | Workflow run manifest persistence for agent/test runs (`manifest.py`) |

Coverage is enforced by `tests/docs/test_data_model_coverage.py` — every table name in `Base.metadata.tables` must appear in this document.

---

## Archive — Decommissioned Parcel / GIS / Building Subsystem

> **🗄 ARCHIVED — historical reference only; does NOT reflect the live schema.**
> The entire parcel / county-GIS / building-entity subsystem was decommissioned
> (migrations 0072 building entity, 0113 parcel tables; DC-1…DC-5 code removal,
> 2026-06). Tables `parcels`, `parcel_transformations`, `buildings` and the
> `opportunities.parcel_id` / `parcel_conflicts_ack` / `projects.parcel_id` columns
> are dropped; parcel/GIS scrapers, seeding, enrichment, geo-matching, reconciliation,
> the Map, and parcel/building UI are deleted. The sections below are retained so old
> behavior is recoverable, **not because any of it still runs.**
>
> **This archive is not FLATS.** The `flats.*` Postgres schema is a separate
> product line — parcel screening for fitment, land, and tolerance — and it is
> *not* a revival of the dropped `parcels` table. It does not share that
> schema, its columns, or its ingest path, and nothing in this Archive
> describes it. See [FLATS_PLAN.md](../Lot%20Analysis/FLATS_PLAN.md) for its
> data model. Reading this section as FLATS documentation will be wrong in
> every particular.
>
> **Still live (do not be misled by their appearance here):** **Crexi** listing ingest
> (its source row survives in A1/§2.1 for completeness; the live pipeline is §5.1),
> **KNN comps** (see `MARKET_MODEL.md`), `Opportunity.apn` / `apn_normalized` / `lat` /
> `lng`, and the manual **jurisdiction** field that powers the Opportunities filter.

## 2. Data Sources

### 2.1 Listing Sources (Market Snapshots)

| Source | Module | Data Provided | Refresh |
|---|---|---|---|
| **Crexi** | `app/scrapers/crexi.py` | Address, lat/lng, property type, units, asking price, cap rate, NOI, zoning, APN, occupancy, description, broker contacts | Celery beat (default queue, daily 06:00 UTC) |
| ~~LoopNet~~ | ~~decommissioned~~ | — | — |
| **Realie.ai** | `app/scrapers/realie.py` | Full property data (80+ fields), stored as `realie_raw_json` | 25 calls/month budget, enriches listings post-ingest |
| **HelloData.ai** | `app/scrapers/hellodata.py` | Unit-level market rents, ML-predicted OpEx/NOI, comparables, occupancy | Pay-per-call (~$0.50/endpoint); monthly cost budget; Portland excluded per policy |

### 2.2 Parcel Seeding Sources (GIS Ground Truth)

| Source | Celery Task | Coverage | Fields Provided |
|---|---|---|---|
| **Metro RLIS Taxlots** | `seed_rlis_task` | ~430K Multnomah + Clackamas parcels | APN (TLID), geometry (polygon), lat/lng (first vertex), jurisdiction (JURIS_CITY), county, assessed values, building sqft, GIS acres, year built, sale price/date, state class, RLIS land use |
| **Oregon Address Points** | `seed_parcels_task` | Statewide (insert-only, no overwrite) | APN (PARCEL_ID), lat/lng, postal_city, zip_code, jurisdiction (Inc_Muni), neighborhood, street fields |

### 2.3 Parcel Enrichment Sources (Per-Jurisdiction GIS Scrapers)

These are queried on-demand during listing auto-link or via the drip-enrichment beat task.

| Jurisdiction | Module | Provider | Fields Provided |
|---|---|---|---|
| **Portland** | `app/scrapers/portlandmaps.py` | PortlandMaps API | APN (RNO), state_id, address, owner, owner mailing, lot/building metrics, valuation, zoning code+desc, building details, geometry |
| **Gresham** | `app/scrapers/arcgis.py` | Gresham ArcGIS MapServer | APN (RNO), state_id, address, owner, lot sqft, GIS acres, zoning, current use, assessed values, year built, geometry |
| **Clackamas County** | `app/scrapers/clackamas.py` | Jericho API | APN (parcel_number), address, zoning code+label, current use (landclass) |
| **Oregon City** | `app/scrapers/oregoncity.py` | Jericho API | APN, address, zoning code+desc (comp_plan), GIS acres, year built, building sqft, total assessed value |

### 2.4 GIS Overlay Layers (Map Display + Screening)

These layers are cached as GeoJSON files and displayed on the zone painter and map views. They do not directly populate Parcel or Opportunity columns but are used for spatial screening and visual context.

**Parcel Seeding**
- Metro RLIS Taxlots — primary seed (~430K parcels)
- Oregon Address Points — address enrichment

**Boundary & Routing**
- City Limits (Oregon) — ODOT source, point-in-polygon jurisdiction routing
- County Boundaries (Oregon) — BLM source, county routing fallback
- Urban Growth Boundaries (Oregon) — DLCD source, out-of-market screening

**Incentive Screening**
- Enterprise Zones (Oregon) — statewide EZ polygons → `Parcel.enterprise_zone_name`
- Opportunity Zones (Oregon) — federal OZ census tracts
- NMTC Qualified Tracts — New Markets Tax Credit tracts

**Environmental**
- Wetlands — LWI, NWI, MORE Oregon (three additive layers)

**Street Classifications**
- ODOT State Roads — federal functional class
- ODOT Non-State Roads — county/city roads

**Reference**
- Building Footprints (Oregon) — structural screening
- Oregon ZIP Reference — address routing
- Census Block Groups / Tracts 2020 — demographic context

**Local GIS (per-jurisdiction)**
Jurisdictions with dedicated GIS services: Fairview, Gresham, Wood Village, Troutdale, Happy Valley, Milwaukie, Oregon City, Gladstone, Lake Oswego, West Linn, Tualatin, Wilsonville. Each provides some combination of:
- Zoning layers → used by zone painter for `Parcel.zoning_code` assignment
- City limits → jurisdiction boundary confirmation
- Environmental overlays (wetlands, floodplain, riparian buffers)
- Enterprise zones / urban renewal districts
- Street classifications / transit layers
- Taxlot polygons (RLIS-compatible)

See `/settings/data-sources` in the app for the full live inventory with heartbeat status.

---

## 3. Field Authority: Who Owns What

When an Opportunity is linked to a Parcel, two records describe the
same property from different perspectives.  This table defines which
source is authoritative for each field and how conflicts are resolved.

### Principle

> **Parcel = GIS/assessor ground truth.  Listing = market snapshot.**
>
> Denormalize onto Opportunity only what is needed in list/filter
> queries that run every page load (jurisdiction).  Everything else
> stays on Parcel and is accessed via the `parcel_id` FK in detail views.

### Authority Table

| Field | Authoritative Source | Fallback | Stored On | Notes |
|---|---|---|---|---|
| **Jurisdiction** | `Parcel.jurisdiction` (GIS) | `Opportunity.city` (broker) | Denormalized -> `Opportunity.jurisdiction` | UI uses `COALESCE(jurisdiction, city)` for graceful degradation |
| **Zoning** | `Parcel.zoning_code` (GIS) | `Opportunity.zoning` (broker) | Stay on Parcel | Joined via `parcel_id` in detail views |
| **County** | `Parcel.county` (GIS) | `Opportunity.county` (broker) | Stay on Parcel | Listing county is mostly correct at county level |
| **Assessed Value** | `Parcel.total_assessed_value` (assessor) | None | Stay on Parcel | Land + improvements split also available |
| **Lot Size** | `Parcel.lot_sqft` / `gis_acres` (GIS) | `Opportunity.lot_sqft` (broker) | Both keep theirs | Mismatch >20% flags `lot_size_mismatch` (possible assemblage) |
| **Owner** | `Parcel.owner_name` (assessor) | None | Stay on Parcel | Not available from listing sources |
| **Year Built** | Both sources | N/A | Both keep theirs | Generally agree; parcel is more reliable |
| **Asking Price** | Opportunity (broker) | None | Stay on Opportunity | Only the market knows the ask |
| **NOI / Cap Rate** | Opportunity (broker) | None | Stay on Opportunity | Broker-provided operating metrics |
| **Property Type** | Opportunity (broker) | None | Stay on Opportunity | Market classification (Multifamily, Office, etc.) |
| **Units** | Opportunity (broker) | None | Stay on Opportunity | Broker unit count |
| **Lat/Lng** | `Opportunity.lat/lng` (geocoded by source) | `Parcel.latitude/longitude` (GIS vertex) | Both keep theirs | Listing coordinates used for spatial matching |

---

## 4. Parcel-Listing Reconciliation

### 4.1 Three-Tier Matching Cascade

When a new listing is ingested (or the backfill task runs), the system
attempts to link it to an existing Parcel via a three-tier cascade.
The cascade stops at the first match.

**Module**: `app/reconciliation/matcher.py`

#### Tier 1: APN Normalized Match

```python
normalize_apn(apn)  # strips dashes, spaces, dots, commas; uppercases
```

```sql
SELECT id FROM parcels WHERE apn_normalized = :normalized_listing_apn
```

- Handles format differences between sources (RLIS TLID `1N1E36AC 100` vs broker `1N1E36AC-100`)
- `apn_normalized` is an indexed column on `parcels`, populated at seed/upsert time
- Multi-APN listings (e.g., `R123,R456`) use the first APN only
- Confidence: 1.0 (exact match)

#### Tier 2: Address + Zip Match

```sql
SELECT id FROM parcels
WHERE address_normalized ILIKE :street_pattern
  AND zip_code = :listing_zip
LIMIT 1
```

- Uses street + zip (both reliable) instead of city (broker-provided, unreliable)
- Avoids the circular dependency in the old `detect_jurisdiction(city_text)` approach
- Confidence: 1.0 (address match)

#### Tier 3: Spatial Proximity

```sql
SELECT id FROM parcels
WHERE latitude BETWEEN :lat - 0.002 AND :lat + 0.002
  AND longitude BETWEEN :lng - 0.002 AND :lng + 0.002
ORDER BY ABS(latitude - :lat) + ABS(longitude - :lng)
LIMIT 1
```

- 0.002 degrees ~ 200m bounding box
- Works without PostGIS (pure SQL on indexed numeric columns)
- Parcel lat/lng extracted from RLIS polygon first vertex (centroid proxy)
- Confidence: inverse of distance (1.0 at 0m, 0.0 at ~450m)

### 4.2 Post-Match Reconciliation

After a successful match, `apply_reconciliation()` writes:

| Column | Value |
|---|---|
| `parcel_id` | Matched parcel's UUID |
| `jurisdiction` | Copied from `Parcel.jurisdiction` |
| `match_strategy` | `"apn"`, `"address"`, or `"spatial"` |
| `match_confidence` | 0.0–1.0 score |
| `lot_size_mismatch` | `True` if listing lot_sqft > parcel lot_sqft × 1.20 |

### 4.3 Lot-Size Mismatch Detection

Listings may silently cover multiple parcels (e.g., a 2-acre listing for
a 1-acre addressed parcel plus an empty acre behind it).  When
`listing.lot_sqft > parcel.lot_sqft × 1.20`, the `lot_size_mismatch`
flag is set.  The model builder shows a yellow banner prompting the user
to add additional parcels via the Opportunity detail page (assemblage workflow).

### 4.4 Multi-APN Listing Detection

Separate from lot-size mismatch, listings with comma/semicolon-separated
APNs (e.g., `R123456,R789012`) trigger a multi-parcel banner in the
model builder.  The user can split into separate projects or keep
combined.  This was previously tracked via `Opportunity.multi_parcel_dismissed` (removed in migration 0072).

### 4.5 Priority Classification

After matching (or independently for parcels), the `classify()` function
in `app/utils/priority.py` assigns a `priority_bucket`:

```
Q1: County in {Multnomah, Clackamas, Washington}?  NO → out_of_market
Q2: Portland jurisdiction?                          YES → contextual
Q3: MF-capable zoning?                              NO → ineligible
                                                    UNKNOWN → unclassified
Q4: MF/Hotel/Mixed-Use current use?                 YES → prime
                                                    NO → target
```

Classification prefers parcel fields (authoritative) over listing fields:
`parcel.zoning_code OR listing.zoning`, `parcel.jurisdiction OR listing.city`.

---

### 5.2 LoopNet Path (via Scrapling LXC 134)

```
Scrapling HTTP POST → _scrape_listings()
  → upsert listing rows       # ON CONFLICT (source, source_id) DO UPDATE
  → _auto_link_parcels()       # Three-tier matcher (same as Crexi)
  → _flag_saved_search_matches()
  # (building sync removed -- Building entity dropped in migration 0072)
  → deduplicate_batch()
```

### 5.3 Parcel Seeding (Background)

```
seed_rlis_task()               # ~430K RLIS taxlots → bulk upsert (quarterly)
seed_parcels_task()            # Oregon Address Points → insert-only stubs
classify_parcels_task()        # Assign priority_bucket to unclassified parcels
enrich_prime_target_parcels()  # Beat task: drip-enrich 500 Prime/Target parcels
                               # per tick via county GIS scrapers (90-day stale)
```

---

### 6.2 Parcel Matching Service

`app/services/parcel_matching.py` provides auto-linking for new ingest and manual backfill.

**Strategy (priority order):**
1. **APN exact** — any element of `opp.apn_normalized` (ARRAY) matches `parcel.apn_normalized` (String)
2. **Lat/lng proximity** — within 30 m of `parcel.latitude / longitude` (SQL bounding box + Python haversine)
3. **Address text** — street number equals `parcel.street_number` AND normalized street name equals `parcel.street_full_name`

**Key functions:**
- `find_matching_parcel(session, opp)` → `Parcel | None` — returns best match, no mutation
- `link_parcel_if_unlinked(session, opp)` → `bool` — idempotent; sets `opp.parcel_id` if unlinked

**Backfill:** `uv run python app/scripts/backfill_parcel_links.py` — processes all `parcel_id IS NULL` in batches of 500.

---

## 7. Parcel Fields

### 7.1 All Columns

**Identity**
| Column | Type | Source | Notes |
|---|---|---|---|
| `id` | UUID | Auto-generated | Primary key |
| `apn` | String(100) | RLIS (TLID) or county scraper | Unique, not null |
| `apn_normalized` | String(100) | Computed | Stripped formatting for fuzzy matching |
| `state_id` | String(100) | County scraper | State-assigned property ID |

**Address**
| Column | Type | Source | Displayed |
|---|---|---|---|
| `address_normalized` | Text | RLIS (SITEADDR) or scraper | Detail |
| `address_raw` | Text | Same | Not displayed |
| `postal_city` | String(120) | Address Points (Post_Comm) | Detail |
| `zip_code` | String(20) | RLIS (SITEZIP) or Address Points | Not displayed |
| `street_full_name` | String(255) | Address Points | Not displayed |
| `street_number` | Integer | Address Points | Not displayed |
| `address_unit` | String(100) | Address Points | Not displayed |

**Location**
| Column | Type | Source | Displayed |
|---|---|---|---|
| `latitude` | Numeric(10,7) | RLIS first vertex or Address Points | Not displayed (used for spatial matching) |
| `longitude` | Numeric(10,7) | RLIS first vertex or Address Points | Not displayed (used for spatial matching) |
| `county` | String(120) | RLIS (COUNTY code) | Detail |
| `jurisdiction` | String(120) | RLIS (JURIS_CITY) or Address Points (Inc_Muni) | Detail |
| `neighborhood` | String(120) | Address Points | Not displayed |
| `unincorporated_community` | String(120) | Address Points | Not displayed |
| `geometry` | JSON | RLIS (polygon GeoJSON) | Zone painter / map |

**Owner**
| Column | Type | Source | Displayed |
|---|---|---|---|
| `owner_name` | String(255) | County scraper (Portland, Gresham) | Detail |
| `owner_mailing_address` | Text | County scraper | Detail |
| `owner_street` | Text | County scraper | Not displayed |
| `owner_city` | String(120) | County scraper | Not displayed |
| `owner_state` | String(20) | County scraper | Not displayed |
| `owner_zip` | String(20) | County scraper | Not displayed |

**Physical / Zoning**
| Column | Type | Source | Displayed |
|---|---|---|---|
| `lot_sqft` | Numeric(18,6) | RLIS or county scraper | Detail |
| `gis_acres` | Numeric(18,8) | RLIS (GIS_ACRES) | List (via filter) |
| `zoning_code` | String(50) | County scraper or zone painter | Detail + list badge |
| `zoning_description` | Text | County scraper | Detail |
| `current_use` | String(255) | County scraper | Detail |
| `year_built` | Integer | RLIS (YEARBUILT) or scraper | Detail |
| `building_sqft` | Numeric(18,6) | RLIS (BLDGSQFT) or scraper | Not displayed |
| `unit_count` | Integer | County scraper | Not displayed |

**Assessment / Tax**
| Column | Type | Source | Displayed |
|---|---|---|---|
| `assessed_value_land` | Numeric(18,6) | RLIS (LANDVAL) or scraper | Detail |
| `assessed_value_improvements` | Numeric(18,6) | RLIS (BLDGVAL) or scraper | Detail |
| `total_assessed_value` | Numeric(18,6) | RLIS (ASSESSVAL) or scraper | Detail |
| `tax_code` | String(50) | RLIS (TAXCODE) | Not displayed |
| `legal_description` | Text | County scraper | Not displayed |

**Classification**
| Column | Type | Source | Displayed |
|---|---|---|---|
| `priority_bucket` | String(30) | `classify()` function | Detail badge |
| `state_class` | String(10) | RLIS (STATECLASS) | List filter |
| `enterprise_zone_name` | String(120) | Spatial join at seed | Not displayed |
| `cultural_sensitivity` | String(120) | Manual (zone painter) | Not displayed |

**RLIS-Specific**
| Column | Type | Source | Notes |
|---|---|---|---|
| `sale_price` | Integer | RLIS (SALEPRICE) | Not displayed |
| `sale_date` | String(6) | RLIS (SALEDATE, YYYYMM) | Not displayed |
| `ortaxlot` | String(50) | RLIS (ORTAXLOT) | Not displayed |
| `primary_account_num` | String(20) | RLIS (PRIMACCNUM) | Not displayed |
| `rlis_land_use` | String(10) | RLIS (LANDUSE) | Not displayed |

**Address Points-Specific**
| Column | Type | Source | Notes |
|---|---|---|---|
| `is_residential` | Boolean | Address Points | Not displayed |
| `is_mailable` | Boolean | Address Points | Not displayed |
| `place_type` | String(100) | Address Points | Not displayed |
| `elevation_ft` | Integer | Address Points | Not displayed |

---

### 9.3 Parcels Table (`/ui/parcels`)

Columns per row: APN, address (street / city state zip), zoning code badge, priority bucket badge, lot sqft, GIS acres, state class, total assessed value, year built.

Filters: text search (APN/address), zoning codes (multi-select), jurisdiction (exact match), use group (state class), min/max acres, min/max year.

### 9.4 Parcel Detail Panel

All parcel table fields plus: postal city, jurisdiction, owner name, owner mailing address, current use, zoning description, assessed value (land), assessed value (improvements), last enriched date.

### 9.5 GeoJSON Map Endpoints

**Listings map** (`/tools/listings/map.geojson`): id, lat/lng, address, property type, asking price, units, cap rate, year built, source, status, priority bucket, building sqft, price per unit. Max 5,000 features.

**Zone painter** (`/tools/zone-painter/parcels.geojson`): parcel polygons with zoning_code/enterprise_zone_name/cultural_sensitivity. Max 3,000 features per viewport.

### (archived) 9.6 API — `GET /parcels`

**`GET /parcels`** → `ParcelRead` schema (all base fields). Route removed with the parcel subsystem.

---

## 10. Reconciliation Results (Production, 2026-04-16)

Initial backfill against 207 listings with 445,936 parcels:

| Strategy | Matched | Match Rate |
|---|---|---|
| Address + zip | 49 | — |
| Spatial proximity | 31 | — |
| APN normalized | 5 | — |
| **Total matched** | **85** | **41% overall** |
| **In-market matched** | **80 of 82** | **98%** |
| Unmatched (out-of-market) | 122 | Expected — no parcel coverage |
| Lot-size mismatches flagged | 17 | Potential assemblages |

The 122 unmatched listings are primarily out-of-market (Salem, Eugene,
coast) where no parcel data is seeded.  These fall back to
broker-provided city via `COALESCE(jurisdiction, city)` in UI filters.

---

## 11. Known Issues

1. **RLIS jurisdiction edge cases**: Some parcels near city boundaries
   have RLIS `JURIS_CITY` values that may not match expectations (e.g.,
   East Portland parcels near Gresham border classified as "portland").
   These reflect actual annexation boundaries, not data errors.

2. **Parcel deduplication**: The same physical property can exist as both
   an RLIS TLID (e.g., `1N1E36AC 100`) and a county RNO (e.g.,
   `R123456`) from the enrichment pipeline.  These are separate Parcel
   rows with different APNs.  Address-match may link to the enrichment
   parcel while the RLIS parcel has better jurisdiction data.

3. **Address Points not seeded**: The `seed_parcels_task()` (Oregon
   Address Points) has not been run in production.  Parcel lat/lng is
   currently derived from RLIS polygon first vertex rather than
   authoritative address point coordinates.

4. **Out-of-market coverage**: Listings outside Multnomah/Clackamas/
   Washington counties have no parcel data.  Expanding coverage requires
   seeding parcel data for the target county AND updating
   `METRO_COUNTIES` + `MF_ZONING_CODES` in `app/utils/priority.py` for
   classification to work.


---

---

## Document Room (`documents`)

Per-project file store backing the document-room module (Phase 1). A
`Document` is one uploaded file scoped to a **Project** (sub-component of a
Deal). File *bytes* live on disk under `settings.document_storage_path`
(`/app/data/doc_room/{org_id}/{project_id}/{uuid}{ext}`); the row holds only
metadata + the `storage_key` pointer. See `app/storage/documents.py`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `org_id` | UUID FK → organizations (CASCADE) | denormalized from Scenario→Deal for org-scoped queries |
| `project_id` | UUID FK → projects (CASCADE) | owning project |
| `filename` | str(512) | original upload name |
| `content_type` | str(255) | from the upload, nullable |
| `size_bytes` | bigint | |
| `sha256` | str(64) | hex digest computed on save |
| `storage_key` | str(1024) | path relative to the storage root |
| `status` | enum `active`/`archived` | archive hides from default view; recoverable |
| `archived_at` | timestamptz | set when archived |
| `uploaded_by_user_id` | UUID FK → users (SET NULL) | null for guest uploads (Phase 3) |
| `preview_status` | enum `none`/`pending`/`ready`/`failed` | Office→PDF conversion (Phase 1b) |
| `preview_key` | str(1024) | storage key of the converted PDF when `ready` |
| `created_at` / `updated_at` | timestamptz | |

Index `ix_documents_project_status` on `(org_id, project_id, status)`.

`projects` has no `org_id` of its own — org is resolved through
Scenario→Deal (`app/api/routers/ui_documents.py:_project_org_id`), so each
Document denormalizes `org_id` to allow direct org-scoped access checks.

Migration: `0115_document_room.py`. `document_tasks` (task view) and
`document_shares` (per-project external links) followed. `document_shares`
gained a short random `slug` (base58, no 0/O/I/l) in `0119`, replacing the old
signed-token URL. `deal_shares` (`0120`) is the deal-wide variant: one revocable
slug grants guests access to **every** project under a deal — the guest landing
page (`/d/{slug}`) lists the projects and each opens the shared room at
`/d/{slug}/p/{project_id}`. Both share types are validated entirely in the DB
(revoked flag + `created_at` age check vs `doc_share_token_max_age_seconds`).
`document_task_templates` (`0118`) seeds org-default tasks onto new projects.
`0121` adds the enforced naming scheme: `documents.name_label` (user-entered
name component) + `documents.stage` (draft/final). The *stored* `filename` is
now the original upload name (audit); the *displayed/downloaded* name is
computed at render time as `Project - Task - Label - Stage - MM-DD-YYYY.ext`
(sanitized for iOS/Windows), so toggling stage or moving a doc between tasks
renames it for free. Every document now lives in a task — task-less docs are
auto-filed into a per-project "Misc." task (also backfilled by `0121`). Whole-
deal downloads stream a zip foldered `Project/Task/file`. `document_tasks.notes`
now holds a sanitized rich-text subset (bold/italic/strike + bullet/numbered
lists, allow-list HTML) edited via the per-task Notes button; downloads flatten
it to indented plain text as `notes.txt`.
