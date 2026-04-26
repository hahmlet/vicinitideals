# Opportunities + Buildings + Parcels Refactor — Implementation Plan

**Status**: Draft, pre-implementation
**Owner**: Steph
**Created**: 2026-04-24
**Companion docs**: `docs/DATA_MODEL.md`, `docs/PROJECT_OVERVIEW.md` — these MUST be updated as the final step of implementation (see §11). They are not modified during planning because decisions may shift during the work, but they are not optional and the refactor is not complete until they reflect shipped reality.

**Sequencing relative to the investor export.** The investor Excel export
plan in [`investor-excel-export-v2.md`](./investor-excel-export-v2.md)
is being built **before** this refactor. Its commits 0–3 ship against
the current schema; once this refactor lands, its **commit 4** (the
"post-refactor patch," ~50 LOC) updates the four touchpoints that move:
`unit_mix` shape (table → JSONB), `Project.acquisition_price` source,
`deal_type` → `proposed_use` + `property_type` (via opportunity lineage),
and `unit_mix` table-iterator → list-comprehension. See §5.5 below for
the full list of exporter changes that this refactor will trigger in
the investor export's commit 4.

---

## 1. Intent

Untangle the Listing → Opportunity → Project → Deal chain so that:

1. **Listings and Opportunities collapse into one entity.** A "listing" (scraped) and a manually-created opportunity become the same kind of row, distinguished only by `source`. The standalone `Opportunity` ORM model is deleted.
2. **Every Opportunity has a Parcel** (1:1, required at creation). The 446k-row `parcels` table is the authoritative source of what can be attached.
3. **Buildings are auto-seeded on the Opportunity** from parcel + listing data (1 building per opportunity, unless raw land). Buildings are severable from listings — a manually-created opportunity gets a building too.
4. **Project = a snapshot of an Opportunity inside a Deal.** A Project deep-copies the opportunity's buildings, unit mix, and proposed-use fields at creation time. Edits inside a Deal/Project stay there and never write back to the Opportunity.
5. **Deal = N Projects** (1+). Each Project carries its own copy of physical and assumption data so the Deal is a true sandbox for iteration.

The user has confirmed they are willing to **purge all existing Deals, Opportunities, Projects, Scenarios, and downstream rows** to enable a clean cutover. Parcels and ScrapedListings are preserved.

### Future vision (not in scope here, but should not be blocked)
Buildings as first-class manipulable objects (demolish, renovate, duplicate, split square footage), driven by richer geometry / image-recognition data. The schema we ship should leave room for that without baking it in now.

---

## 2. Current State (concise)

Class inventory at start of refactor:

| File | Classes |
|---|---|
| `app/models/project.py` | `OpportunityStatus`, `OpportunityCategory`, `OpportunitySource`, **`Opportunity`** (49), **`Project`** (141), **`ProjectBuildingAssignment`** (231), **`ProjectParcelAssignment`** (255), `PermitStub`, **`ProjectAnchor`** (298) |
| `app/models/property.py` | `BuildingStatus`, **`Building`** (26), **`OpportunityBuilding`** (102) |
| `app/models/scraped_listing.py` | **`ScrapedListing`** (27) — has `linked_project_id`, `parcel_id`, `property_id` |
| `app/models/parcel.py` | `ProjectParcelRelationship`, `ParcelTransformationType`, **`Parcel`** (27), **`ProjectParcel`** (126), `ParcelTransformation` |
| `app/models/deal.py` | `ProjectType`, **`Deal`** (83), **`DealOpportunity`** (124), **`Scenario`** (154), `OperationalInputs`, `OperatingExpenseLine`, `IncomeStream`, **`UnitMix`** (441), `UseLine` |

Key observations from prior audits (claude-mem obs IDs in parentheses):
- `Building.scraped_listing_id` is a **unique** FK — one-to-one promotion (777). Severing requires nullable.
- `OpportunityBuilding` is M2M with `sort_order`/`role` (777). Becomes 1:N after refactor.
- `ProjectParcel` and `ProjectParcelAssignment` are both junction tables — one is opp↔parcel, the other is project↔parcel; we collapse both to direct FKs.
- `Project.deal_type` is `String(60)`; `Deal.project_type` is enum-typed (`ProjectType`). Naming chaos; resolve. (1743)
- `unit_mix` exists on both `Deal/Scenario` and `Project` (1138). Collapse to Project only.
- `asking_price` lives on ScrapedListing + Building, never on Opportunity. `opp_asking_price` is a transient template var (2697). Remove the transient; ScrapedListing keeps it; Project gets its own deal-specific `acquisition_price`.
- Migration 0048 already added `CapitalModuleProject` junction + `ProjectAnchor` for multi-project compute, but cashflow still hardcodes `scenario.projects[0]` (2024). Out of scope for this refactor.
- Multi-parcel split logic exists at `ui.py:5117` and uses `Project.multi_parcel_dismissed`. **Removed** by this refactor — assemblages become "add another opportunity to the deal."

---

## 3. Target Architecture

### Entity diagram (new)

```
Parcel  ◀── (FK, required) ── Opportunity ◀── (FK, lineage only) ── Project ──▶ Deal
                                  │                                    │
                                  │  (1:N, owner=opp)                  │  (1:N, owner=project)
                                  ▼                                    ▼
                               Building ─── (deep-copy on project create) ──▶ Building
                                  │                                    │
                                  └──────── unique-FK to ScrapedListing (nullable) ─── kept on opp-owned only
```

### Edit-flow rules (load-bearing)

- **Opportunity edits** (parcel reassignment, unit mix, building add/edit/archive): write directly to opportunity-owned rows. Do NOT propagate to existing Projects.
- **Project edits** (anything inside Model Builder / Deal context): write to project-owned rows only. NEVER touch opportunity rows.
- **New Project creation**: deep-copy from Opportunity → Project (buildings, unit mix, proposed-use, default acquisition price). After creation, Project is independent. The `Project.opportunity_id` FK is preserved for lineage display only.

### Cardinalities (final)

| From | To | Cardinality | Notes |
|---|---|---|---|
| Opportunity | Parcel | N:1, required | `opportunity.parcel_id NOT NULL` |
| Opportunity | Building | 1:N | Typically 1; raw-land = 0; user can add more |
| Opportunity | ScrapedListing | 1:0..1 | Manual opps have no listing; scraped opps have one |
| Deal | Project | 1:N (≥1) | Replaces the old Deal↔Opportunity M2M |
| Project | Opportunity | N:1, required | Lineage; never sourced from at runtime |
| Project | Parcel | N:1, required | Copied from Opportunity at creation |
| Project | Building | 1:N | Copied from Opportunity at creation |
| Building | Opportunity | N:1 (nullable) | XOR with `project_id` |
| Building | Project | N:1 (nullable) | XOR with `opportunity_id` |

---

## 4. Data Model Changes

### 4.1 Tables removed

| Table / Class | Reason |
|---|---|
| `opportunities` (`Opportunity`) | Folded into `scraped_listings` which becomes the unified Opportunity table. |
| `deal_opportunities` (`DealOpportunity`) | Deal→Project supersedes Deal→Opportunity. |
| `opportunity_buildings` (`OpportunityBuilding`) | Replaced by direct FK `Building.opportunity_id`. |
| `project_parcels` (`ProjectParcel` in `parcel.py`) | Replaced by direct FK `Project.parcel_id` (and `Opportunity.parcel_id`). |
| `project_parcel_assignments` (`ProjectParcelAssignment` in `project.py`) | Same; the duplicate junction is removed too. |
| `project_building_assignments` (`ProjectBuildingAssignment`) | Replaced by direct FK `Building.project_id`. |

### 4.2 Tables renamed / restructured

**`scraped_listings` → `opportunities`** (table rename; ORM class becomes `Opportunity`):
- Keep `source`, `source_id` columns; values now include `manual` and `user_generated` (already in `OpportunitySource` enum) for non-scraped rows.
- For `source=manual` rows, `source_id` can be `manual:{uuid}` or null with a check constraint that scraped sources require non-null source_id.
- Add `parcel_id` as **NOT NULL** FK to `parcels` (scraped rows already have this populated for most rows).
- Migrate the small set of "useful" fields from the old `Opportunity` model (status, category, name override, notes) onto the new opportunity row.
- Add `project_type` (enum, copied from old `Project.deal_type` / `Opportunity.project_type` — pick the cleaner of the two; see §4.5).
- Keep `asking_price`, `asking_cap_rate_pct`, raw_json, scraper metadata as-is.
- Add `archived_at` and `dismissed_at` if they aren't already present, to replace any old "soft delete" patterns on `Opportunity`.

**`buildings`**:
- Add `opportunity_id UUID NULL` (FK → `opportunities.id`).
- Add `project_id UUID NULL` (FK → `projects.id`).
- Add CHECK constraint: exactly one of `opportunity_id` or `project_id` is non-null.
- Make `scraped_listing_id` **nullable** (was unique NOT NULL). Keep the unique partial index for the case where it IS set, so we don't double-promote a listing.
- Remove the FK from `OpportunityBuilding` after that table is dropped.

**`projects`**:
- Add `opportunity_id UUID NOT NULL` FK → `opportunities.id` (lineage, indexed).
- Add `parcel_id UUID NOT NULL` FK → `parcels.id` (copied from opportunity at create).
- Add `unit_mix JSONB` column (array of unit-type objects — see §4.6). Drop the standalone `unit_mix` table entirely.
- Add `acquisition_price NUMERIC(18,2)` (default-copied from opportunity asking_price at create, then editable).
- Add `proposed_use` enum (string) — what the deal *plans* to do with the property; distinct from `opportunity.project_type` which is the property's *current* type.
- Drop `multi_parcel_dismissed` column. Drop `deal_type` column (replaced by lineage to `opportunity.project_type` + project's own `proposed_use`).

**`opportunities`** (additional fields beyond §4.2):
- Add `unit_mix JSONB` column (same shape as Project's; this is the canonical seed).

**`scenarios` / `deals`**:
- Remove `unit_mix` linkage (now Project-only).
- Resolve `Deal.project_type` enum vs `Project.deal_type` string by removing both and relying on Opportunity-level `project_type` + Project-level `proposed_use`. (See §4.5 for the naming decision.)

### 4.3 Tables retained as-is

- `parcels` — no changes
- `parcel_transformations` — no changes (kept for future split/combine work)
- `project_anchors` — no changes (forward-compat for multi-project compute)
- `capital_modules`, `capital_module_projects`, `waterfall_*`, `draw_*`, `use_lines`, `cashflow_*`, `operational_*` — no changes; they're scenario/project-scoped already
- All scraper-side tables (`ingest_jobs`, `dedup_candidates`, `field_conflict_log`, `listing_snapshots`, etc.) — no changes

### 4.4 Migrations

User has approved a **purge-and-cutover** approach. Implementation creates one Alembic migration (next available number, currently 0059):

1. **Pre-purge**: snapshot/export DB if needed (operator decision; default: skip — this is intentional data loss).
2. **Purge data** (in order, respecting FKs):
   - `cashflow_*`, `operational_outputs_per_project`, `waterfall_results`
   - `use_lines`, `income_streams`, `operating_expense_lines`, `unit_mix` rows
   - `draw_sources`, `capital_module_projects`, `capital_modules`, `waterfall_tiers`
   - `project_anchors`, `project_building_assignments`, `project_parcel_assignments`
   - `projects`
   - `scenarios`
   - `deal_opportunities`
   - `deals`
   - `opportunity_buildings`
   - `opportunities` (old table — about to be dropped)
   - `buildings` rows that came from manual flows (preserve scraped-listing-promoted rows; will be re-attached to scraped_listings under the new schema if useful, or also purged — operator choice)
3. **Schema changes** (DDL):
   - DROP `deal_opportunities`, `opportunity_buildings`, `project_parcel_assignments`, `project_parcels`, `project_building_assignments`
   - DROP old `opportunities` table (was `Opportunity` model)
   - RENAME `scraped_listings` → `opportunities`. Update all FK references in the same migration.
   - ALTER `opportunities`: add `parcel_id NOT NULL`, `project_type`, optional fields lifted from old Opportunity model.
   - ALTER `buildings`: add `opportunity_id`, `project_id`, CHECK constraint, make `scraped_listing_id` nullable.
   - ALTER `projects`: add `opportunity_id`, `parcel_id`, `acquisition_price`, `proposed_use`, drop `multi_parcel_dismissed`, drop `deal_type`.
   - ALTER `scenarios` / `deals`: drop `project_type` / `unit_mix` linkage where applicable.
4. **Reseed**: re-run scraper backfills if any opportunity-level enrichments need to populate the new `opportunities` table fields. Scraped listings already have parcel_id populated for most rows; rows missing parcel_id should be flagged and excluded from "promote to opportunity" UI until reconciled.

### 4.6 `unit_mix` JSONB shape

Decision locked: `unit_mix` is a JSONB array column on both `opportunities` and `projects`. The standalone `unit_mix` table (created in migration 0020, extended in 0046) is dropped. Rationale: deep-copy on project create becomes a single column copy instead of an N-row insert loop, which materially reduces correctness risk on the load-bearing flow.

**Element shape** (Pydantic-validated; no DB constraints):

```json
{
  "label": "1BR/1BA",
  "beds": 1,
  "baths": 1.0,
  "sqft": 600,
  "rent_monthly": 1500,
  "unit_count": 12,
  "notes": null
}
```

Implementation requirements:
- Pydantic v2 models in `app/schemas/unit_mix.py` for validation on read/write.
- Helpers `app.models.opportunity.Opportunity.unit_mix_total_units()` and `.unit_mix_total_sqft()` to keep template code clean.
- Migrations 0020 and 0046 are NOT reverted; the new migration drops the table outright (purge approved).
- Exporters (`json_export.py`, `deal_export.py`, Excel exporter) emit the array directly under `project.unit_mix`. Importer validates with the Pydantic schema and rejects malformed payloads.

### 4.7 Naming + enum cleanup

- **`project_type` (Opportunity-level)** — what the property is today. Use the `ProjectType` enum from `deal.py`. Move the enum definition to `app/models/opportunity.py` (new file) or keep in `deal.py` and import.
- **`proposed_use` (Project-level)** — what this deal proposes to do. New enum `ProposedUse` in the same file. Initial values: `hold_existing`, `value_add_renovation`, `redevelop`, `ground_up_new`, `land_bank`. (Confirm with Steph during implementation.)
- **Building model**: keep the `Property = Building` alias for now to avoid touching every importer; add deprecation comment and remove in a follow-up cleanup PR.
- **Drop**: `Project.deal_type` (string), `Deal.project_type` (enum) — both eliminated by the move described above.

---

## 5. Application Code Changes

### 5.1 Models (`app/models/`)

- **New**: `app/models/opportunity.py` — the new `Opportunity` ORM class (was `ScrapedListing`). Re-export from `app/models/__init__.py`. Keep `ScrapedListing = Opportunity` alias for the duration of the refactor; remove in a follow-up.
- **Rewrite**: `app/models/project.py` — drop `Opportunity`, `OpportunityCategory`, `OpportunityStatus`, `ProjectBuildingAssignment`, `ProjectParcelAssignment`. Add `opportunity_id`, `parcel_id`, `acquisition_price`, `proposed_use` to `Project`. Drop `multi_parcel_dismissed`, `deal_type`. `OpportunitySource` enum stays (move to `opportunity.py`).
- **Rewrite**: `app/models/property.py` — `Building.opportunity_id` and `Building.project_id` columns, CHECK constraint, nullable `scraped_listing_id`. Drop `OpportunityBuilding`.
- **Rewrite**: `app/models/parcel.py` — drop `ProjectParcel` and `ProjectParcelRelationship`. Keep `Parcel` and `ParcelTransformation`.
- **Rewrite**: `app/models/deal.py` — drop `DealOpportunity`. Drop `UnitMix.deal_id` (or the table itself, depending on whether unit_mix becomes JSONB on Project or stays a separate table keyed by `project_id`). Drop `Deal.project_type`.

### 5.2 Schemas (`app/schemas/`)

- `app/schemas/deal.py` — remove unit_mix from Deal/Scenario import/export shape. Move to `app/schemas/project.py`.
- `app/schemas/opportunity.py` (new) — Pydantic schemas for the unified Opportunity. Manual-create input, scraped-import payload, edit payload, response shape.
- `app/schemas/scraped_listing.py` — keep for the scraper layer's internal payloads, but re-target output to the new `Opportunity` shape.

### 5.3 API routers (`app/api/routers/`)

- `app/api/routers/listings.py` and `app/api/routers/projects.py` and `app/api/routers/deals.py`:
  - Delete the standalone Opportunity-create flow.
  - Redirect "create opportunity from listing" to "this listing IS the opportunity" (no-op or just navigates).
  - Add manual-opportunity creation endpoint (`POST /opportunities`) that requires `parcel_id`.
  - Add "create deal from opportunity" endpoint that creates Deal + first Project + deep-copies buildings/unit_mix/etc.
  - Add "add project to deal" endpoint that accepts `opportunity_id` and deep-copies into a new Project under the existing Deal.
- `app/api/routers/ui.py` (~7900 lines, most-active file):
  - Delete or rewrite all opportunity-wizard handlers.
  - Delete the multi-parcel-split flow (~ui.py:5117 and ~ui.py:6405; banner template too).
  - Update Model Builder route to load `deal_projects` keyed by `Project.opportunity_id` lineage rather than today's intermediary.
  - Anchor wizard, Add Project drawer (added in obs 2914), Cash Flow filter — adjust their data fetches.

### 5.4 Engines (`app/engines/`)

- `cashflow.py` already uses `scenario.projects[0]`; no functional change here. Confirm no engine code reads `scenario.unit_mix` directly — if it does, repoint to `project.unit_mix`.
- `underwriting.py`, `waterfall.py`, `sensitivity.py`, `draw_schedule.py`: audit for any references to the dropped tables/columns; expected to be minimal since these are scenario/project-scoped.

### 5.5 Exporters (`app/exporters/`)

- `deal_export.py`, `json_export.py`: drop unit_mix from the Deal-level shape; include from Project. Drop Opportunity-level export blob; add the lightweight lineage pointer (`{opportunity_id, source, source_id}`) to each Project block.
- Excel exporter (`excel_export.py`, the round-trip exporter): same — unit mix moves to a per-project sheet. This exporter is on a deprecation path per the investor export plan, so minimal-surface updates only; don't add new features here.
- **Investor export (`investor_export.py`)**: this is the canonical investor artifact going forward. It will exist in production by the time this refactor ships (per [`investor-excel-export-v2.md`](./investor-excel-export-v2.md) commits 0–3). When this refactor lands, the investor export's **commit 4 — Post-refactor patch** is the corresponding update on the export side. The four touchpoints (full detail in `investor-excel-export-v2.md` §8 commit 4):
  1. `_load_all` / `ctx["unit_mix"]` — change from joined `UnitMix` rows to JSONB-backed `list[UnitMixItem]` Pydantic models.
  2. Assumptions Block B — point `acquisition_price` row at the new persisted `Project.acquisition_price` column.
  3. Assumptions Block B — convert unit-mix-derived rows (unit count, rents) from row-iterator to list-comprehension over the JSONB.
  4. Per-project sheet header — replace the `deal_type` cell with two cells (`p<n>_property_type` from `project.opportunity.project_type`, `p<n>_proposed_use` from `project.proposed_use`). Update `FINANCIAL_MODEL.md` glossary entries so the bidirectional validator stays green.

  The bidirectional doc/export validator (delivered in the investor export's commit 0) will fail CI on any drift introduced by this refactor that isn't picked up in commit 4 — that's the intended forcing function.

### 5.6 Tasks (`app/tasks/`)

- Scraper tasks (`tasks/scraper.py`): adjust the post-ingest step that today populates `scraped_listings` to also (a) ensure `parcel_id` is set via lat/lng nearest-parcel reconciliation if missing, and (b) auto-seed a Building for non-land listings. The auto-seed lives at the **opportunity layer**, not at deal-creation time.
- Backfill task (one-shot, after migration): for every existing scraped listing without a building and without raw-land project_type, create a seeded Building.

### 5.7 Tests (`tests/`)

- Drop tests for the removed tables/junctions.
- Add: `tests/models/test_opportunity_invariants.py` — parcel_id required, Building XOR FK, project deep-copy contract.
- Add: `tests/api/test_opportunity_to_deal.py` — full round-trip from "create manual opportunity → create deal → add second project from another opportunity → edit unit mix in project doesn't change opportunity".
- Update: every fixture in `tests/conftest.py` that uses `seed_deal_model_with_financials` — the parent entity tree changes shape.
- Phase B regression script (`scripts/test_phase_b_debt.py`): expected to keep passing because cashflow math doesn't change. If it breaks, fix the seed in the script, not the engine.

---

## 6. UI Changes

### 6.1 Listings page (`app/templates/listings.html`, `listings_map.html`)

- **Rename** the page to "Opportunities" in nav, headers, and breadcrumbs. URL stays `/listings` for now and gets an alias `/opportunities` (302 redirect from `/listings`).
- Add a "**+ New Opportunity**" button that opens an inline form (or modal): pick a parcel via search/map, set name, project_type, optional asking_price. Submits to `POST /opportunities` with `source=manual`.
- Manual rows render alongside scraped rows. Source column shows the badge (`crexi`, `loopnet`, `realie`, `manual`).
- Saved filters and the cross-tab persistence work added in S219 carry over without changes.
- Existing parcel-bounds highlight on map carries over (from S219).

### 6.2 Listing detail / Opportunity detail (`opportunity_detail.html` + `partials/listing_detail.html`)

- Merge into a single "Opportunity Detail" page. Sections: Header (name, source, parcel, project_type), Parcel Summary, Buildings (auto-seeded list, edit inline, add new), Unit Mix (per-building or aggregated — confirm with Steph), Notes, Linked Deals.
- Edit unit mix here = canonical edit (does NOT propagate to existing Projects).
- "**Create Deal from this Opportunity**" button — primary CTA. Lands user in Model Builder with one Project preloaded.
- "**Add to existing Deal**" secondary action — picker shows user's recent deals; creates a new Project under the chosen deal.

### 6.3 Buildings page (`app/templates/buildings.html`)

- Becomes a read-mostly inventory view. Today it's used for manual building creation in the deal flow (per user's complaint); after refactor, building creation happens at Opportunity level only.
- Keep it for the inventory/audit use case. Add a filter for "buildings without an opportunity" to spot orphans.

### 6.4 Opportunity Wizard (`opportunity_wizard.html`)

- **Delete** the wizard entirely. Replaced by:
  - The inline create-form on the listings/opportunities page (for manual creation).
  - The "Create Deal" CTA on the opportunity detail page (for deal creation).
- Wizard state machine, step partials, and `opp_asking_price` template variable all go away.

### 6.5 Model Builder (`app/templates/model_builder.html`)

- Tab row continues to show one tab per Project (the work in obs 2933–2942 stays).
- "**Add Project**" drawer (obs 2914, 2936):
  - Step 1: pick an Opportunity (search + recent list).
  - Step 2: anchor dates (already exists from this session).
  - On submit: backend creates Project, deep-copies opportunity buildings + unit mix + project_type → proposed_use default, sets anchors.
- The multi-parcel split banner is removed.
- Unit mix editor stays at project level. Edits don't write through to Opportunity (per §3 edit-flow rules).
- Per-project Sources gating from S220 stays.

### 6.6 Deal list / dashboard

- Each deal row shows N projects, each with its lineage (opportunity name, parcel APN). No M2M-junction queries needed anymore.

### 6.7 Templates that get touched (best estimate)

| Template | Change |
|---|---|
| `listings.html`, `listings_map.html` | Rename, add manual-create button |
| `opportunity_detail.html` | Becomes canonical opportunity edit page |
| `opportunity_wizard.html` | DELETE |
| `opportunities.html` | Likely DELETE or merge into listings.html |
| `partials/listing_detail.html` | Fold into opportunity_detail.html |
| `partials/listings_*_row.html` (new/promoted/unpromoted/archived) | Update to opportunity-row partials, drop "promote to opportunity" CTA |
| `partials/buildings_rows.html`, `partials/building_detail.html` | Show owner badge (opp / project), add "edit at source" link |
| `model_builder.html` | Remove multi-parcel banner, update Add Project drawer |
| `deal_detail.html` | Update to read from Project lineage, remove DealOpportunity references |

---

## 7. Out of Scope / Deferred

- Multi-building per opportunity (user defers; ship 1 building per opportunity, allow add later).
- Building manipulation operations (demolish/renovate/duplicate). `BuildingStatus` enum stays available; UI for it ships later.
- Multi-parcel assemblage at the opportunity level. Future assemblage = "deal with multiple projects, each on its own parcel."
- Splitting a parcel (`ParcelTransformation` table stays in place but is not exercised by this refactor).
- Multi-project cashflow compute (Phase 2 of migration 0048).
- Listing-jurisdiction backfill (known issue #5 in CLAUDE.md). This refactor does NOT solve it but should not block it.
- Opportunity-level financial commentary fields beyond simple notes.

---

## 8. Open Questions (decide during implementation)

1. **`ScrapedListing = Opportunity` alias.** Keep for one release cycle, or remove in the same migration? Recommendation: keep, deprecate in the next refactor pass.
3. **`OpportunityBuilding.role` field.** Today supports `primary`/`adjacent`. With 1:N direct FK, do we need `role` on Building, or is it dropped entirely? Recommendation: drop now; reintroduce only if assemblage UI ships.
4. **`Property = Building` alias.** Old name still used in some imports per obs 777. Drop now or in follow-up? Recommendation: follow-up.
5. **What does "raw land" mean for auto-seed gate?** Detection logic options: (a) `project_type == ProjectType.land`, (b) `parcel.building_sqft IS NULL OR == 0`, (c) both. Recommendation: (a) primarily, (b) as a fallback when project_type is missing on scraped rows.
6. **Manual opportunity numbering.** What's the human-readable name shown by default? Recommendation: `{address} ({apn})` derived from parcel; user can override.

---

## 9. Risks

- **Scope creep into the cashflow engine.** The engine still uses `scenario.projects[0]`. This refactor must NOT try to fix that — keep it boxed. If a test in `tests/engines/` breaks, root-cause it as a fixture/seed mismatch before touching engine code.
- **Hidden FKs to dropped tables.** `ui.py` is ~7900 lines and references many models. A grep sweep for `Opportunity`, `ProjectParcel`, `OpportunityBuilding`, `DealOpportunity`, `ProjectBuildingAssignment`, `ProjectParcelAssignment` is mandatory before declaring code complete.
- **Scraper writes during cutover.** Pause Celery scraping queue during the migration window. Resume after the new schema's compatibility shim is verified by a smoke run.
- **E2E suite regression.** The current E2E suite (43/43 green per memory) traverses opportunity/deal flows. Expect to update most fixtures and several test specs.
- **Excel export round-trip.** The exporter and importer must agree on the new Project-shaped unit_mix; if a customer has an exported file from before the refactor, the importer should error cleanly rather than silently lose data.

---

## 10. Acceptance Criteria

A reviewer should be able to verify all of these from the live app and the codebase:

1. Listings page is renamed "Opportunities" and supports manual-create with a required parcel pick.
2. `Opportunity` ORM class no longer exists in `app/models/project.py`. The unified opportunity ORM lives in `app/models/opportunity.py` and is the renamed `ScrapedListing`.
3. `Building.opportunity_id` and `Building.project_id` are both present, with a CHECK constraint that exactly one is set.
4. Creating a Deal from an Opportunity deep-copies buildings, unit_mix, and project_type→proposed_use into the new Project. Editing those fields inside the Deal does not modify the Opportunity (verified by a test).
5. Adding a second Project to an existing Deal works via the Add Project drawer and accepts an Opportunity selection.
6. The multi-parcel split banner and `Project.multi_parcel_dismissed` column are gone.
7. `unit_mix` no longer exists at the Deal/Scenario level; only at Project level.
8. `Deal.project_type` and `Project.deal_type` columns are gone; `Opportunity.project_type` and `Project.proposed_use` replace them.
9. Migration 0059 runs cleanly on a fresh DB and on a purged production DB.
10. Phase B debt regression suite (`scripts/test_phase_b_debt.py`) passes against a post-migration deploy.
11. Live deploy to `viciniti.deals` is successful and the smoke checks in `deploy-vicinitideals.sh` pass.
12. `docs/DATA_MODEL.md` and `docs/PROJECT_OVERVIEW.md` are updated to match shipped reality. **This is the final acceptance criterion — the refactor is not done until the docs match the schema.** Done in the same PR series, not deferred to a follow-up.

---

## 11. Suggested Sequencing (advisory only — agent may reorder)

1. **Migration 0059** drafted (DDL + purge SQL). Run against a local copy first.
2. **Models** rewritten to match new schema. ORM-level tests green locally with SQLite.
3. **Schemas + exporters** updated. JSON export round-trip test green.
4. **API routers** updated. Integration tests green.
5. **Engine smoke** — Phase B debt suite green against local seed.
6. **UI templates** updated. Playwright E2E suite updated.
7. **Tasks** — scraper post-ingest step updated; backfill task written.
8. **Deploy** to staging DB if available; otherwise straight to production after a manual purge confirmation.
9. **Update `docs/DATA_MODEL.md` and `docs/PROJECT_OVERVIEW.md`** to match shipped reality. This is a required final step, not a deferrable follow-up. Any drift between the plan in this document and what actually shipped (renamed columns, different enum values, deferred sub-features) must be reflected in the schema docs before the refactor closes out.

End of plan.
