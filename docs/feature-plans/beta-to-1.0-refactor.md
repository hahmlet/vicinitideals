# Beta → 1.0 Refactor Plan — vicinitideals

**Evaluated:** 2026-05-11  
**Codebase snapshot:** commit `9c10949`, graph built 2026-05-11T10:36:44 UTC  
**Diff against this snapshot** when re-evaluating after feature work lands.

---

## Verdict

Refactor has real, measurable impact. Problems are structural, not cosmetic. Codebase has outgrown its original shape — one file is 12,228 lines. Without restructuring, every feature addition gets slower and every bug hunt gets harder.

Stack is well-chosen. No migrations needed. FastAPI + HTMX + SQLAlchemy 2.0 + PostgreSQL 16 + Redis 7 stays as-is.

UI overhaul is **out of scope** — design handled separately. This plan covers code structure, reliability, and maintainability only.

---

## Evidence

### ui.py is 12,228 lines with 123 route handlers

Previously measured as ~7,900 — it's grown. Handles deals, model builder, timeline wizard, portfolio, parcel browser, brokers — all in one file. When an AI agent or human debugs the timeline, the entire 12,228-line file loads to find context. Adding a feature means locating the right spot in a wall of code.

The `handle_form_create_or_update` function alone connects to 300+ downstream nodes in the call graph.

### Code duplication

**Gantt chart — 3 copies, ~836 total lines:**
- `app/templates/deal_detail.html` lines 109–437 (329 lines)
- `app/templates/model_builder.html` lines 559–900 (342 lines)
- `app/templates/portfolio_detail.html` lines 6–170 (165 lines)
- Same 9 color rules copied 3×. One color change = 3 files.

**Deal type dropdown — hard-coded in 4 templates:**
- `deals_new.html`, `deal_detail.html`, `model_builder.html`, `opportunity_wizard.html`
- `ProjectType` enum already exists in `app/models/deal.py:36`. Templates don't use it.

**Debt structure/sizing options — 2 separate hard-coded locations:**
- `model_builder.html` and `settings_org.html` — can drift independently.

**Property types — 2 files, already drifted:**
- `opportunities.html`: `Multifamily, Office, Retail, Industrial, Land, Mixed Use, Hospitality, Medical`
- `partials/building_form_fields.html`: `Multifamily, Mixed Use, Commercial, Retail, Industrial, Single Family, Vacant Land, Other`

**Python defaults — defined in 3 places with conflicting values:**
- `DEFAULT_DURATIONS` in `app/models/milestone.py:39` → offer_made = **14 days**
- `_ACQUISITION_DEFAULT_DAYS` in `ui.py` → offer_made = **7 days**
- `_DEFAULT_LOAN_COSTS` in `app/engines/cashflow.py` with a "keep in sync" comment pointing to `ui.py`

### Pages don't update after saving

No WebSocket, SSE, or polling exists. After saving a capital module or income stream, the cashflow summary does not update. User must manually refresh. The existing `refreshPanel()` is pull-based — user must trigger it.

**Target:** after hitting Save, summary updates immediately. No manual refresh.

### Security gaps

| Issue | Severity | Status |
|---|---|---|
| CSRF protection | High | Missing entirely |
| Rate limiting | Medium | Auth endpoints only — no coverage on writes |
| Auth at route level | Medium | Middleware-only; no per-route fallback |
| SQL injection | — | Safe — parameterized throughout |

Note: The legacy `vd_user_id` unsigned cookie auth bypass was fixed in commit `a495420` (Phase 1 security, May 2026). CSRF was not addressed in that phase.

### Dead code

**LoopNet infrastructure — safe to delete (~400+ lines):**
- Disabled via `loopnet_experiment_enabled: False` in config with no re-enablement path
- `app/scrapers/loopnet.py`
- `app/scrapers/loopnet_broker.py`
- `app/tasks/loopnet_ingest.py` (~424 lines, 3 dead Celery tasks)
- `app/models/listing_snapshot.py` — only populated by LoopNet; 0 production rows
- 3 Celery beat schedule entries
- 4 config fields (`loopnet_*`)

**HelloData enrichment — evaluate for removal:**
- CLI-only, not wired into the normal scraping pipeline
- `app/scrapers/hellodata.py`, `app/scripts/enrich_hellodata.py`

**Incomplete stubs — needs decision:**
- `equity_multiple` field (`ui.py:359`): always returns `None`; join logic never implemented
- Soft warning (`ui.py:9393`): warning computed but never surfaced to user
- Org defaults wiring (`app/settings/defaults.py:47`): `selling_costs_pct` from org defaults never wired into new deal creation

**Backward-compat aliases — keep (still in use):**
- `DealModel = Scenario` — heavily used throughout codebase
- `ScenarioResult = SensitivityResult` — same
- Legacy debt structure paths in `cashflow.py` — needed for existing production deals

---

## ui.py Split — 7 Sub-Routers

The 123 routes divide cleanly by domain into 7 files plus a shared helpers module.

| New file | Est. lines | Routes | What's inside |
|---|---|---|---|
| `ui/settings.py` | ~800 | 12 | Root, splash, all `/settings/*`, admin tasks |
| `ui/deals_pipeline.py` | ~2,100 | 24 | Deal list/CRUD, opportunities, opportunity wizard |
| `ui/data_intel.py` | ~2,600 | 28 | Buildings, parcels, listings, map, brokers, dedup |
| `ui/model_builder.py` | ~3,200 | 23 | Builder page, panel, forms handler, project ops, sensitivity, anchors, source coverage, calc status |
| `ui/wizards.py` | ~1,500 | 5 | Timeline wizard, approve timeline, deal setup wizard (3 steps) |
| `ui/model_outputs.py` | ~1,800 | 20 | Excel/investor exports, draw schedule, line form, NOI inputs, source vehicle prefill, history |
| `ui/portfolios.py` | ~400 | 9 | Portfolios, deal search, saved filters |
| `ui/_helpers.py` | ~600 | — | Shared: `_get_user`, `_load_builder_data`, `_fmt_currency`, etc. |

`model_builder.py` stays heaviest at ~3,200 lines because `handle_form_create_or_update` (the 300-edge hub) can't be safely split without a service layer first. That's Phase 2b.

### Blast radius of the split

Only 4 files import from `ui.py`:

| File | Import | Update needed |
|---|---|---|
| `app/api/main.py:266` | `router as ui_router` | Register 7 sub-routers instead of 1 |
| `app/api/routers/tools.py:15` | Helper functions | Update import path |
| `app/api/routers/models.py:588` | `_run_draw_schedule` (lazy import — circular import already flagged in comment) | Update import path when moved to `model_outputs.py` |
| `tests/api/test_gap_adjustment_pill_override.py:98,125,149,186` | `_has_any_gap_adjustment`, `_render_calc_status_pill_html` | Update import paths |

43 Playwright E2E tests hit via HTTP — no ui.py imports. Zero breakage there.

---

## Migration Feasibility

**Low pain.** The split is mechanical — move code, don't change it.

| Phase | Pain | Risk | Notes |
|---|---|---|---|
| Phase 1 (quick wins) | Very low | Very low | Independent changes, all reversible |
| Phase 2a (ui.py split) | Low | Low | Mechanical file moves, tiny blast radius |
| Phase 2b (service layer) | Medium | Medium | Logic changes — needs test coverage before starting |
| Phase 3 (cleanup) | Low | Very low | Optional polish |

**Golden rule:** move code and change code in separate commits. Never both at once.

---

## Phased Plan

### Phase 1 — Quick wins (~1 week)

Independent. Safe to do in any order. No structural risk.

1. **CSRF middleware** — single middleware addition, ~30 min
2. **Extend rate limiting** to all POST/PUT/PATCH/DELETE endpoints
3. **Deal type enum in templates** — 4 hardcoded files → use `ProjectType` enum via Jinja2 loop
4. **Gantt CSS extraction** — 9 color rules × 3 files → single shared stylesheet block in `base.html`
5. **Property type list consolidation** — decide canonical list, apply to both files
6. **Python defaults unification** — resolve `_ACQUISITION_DEFAULT_DAYS` vs `DEFAULT_DURATIONS` conflict; one source of truth
7. **LoopNet dead code removal** — 400+ lines, 0 production rows, disabled flag, safe to delete

### Phase 2a — ui.py split (~2 weeks)

Sequence matters. Extract helpers first so sub-routers can import them.

```
1. Create app/api/routers/ui/_helpers.py — move shared helpers
2. Create ui/settings.py      — move routes, update main.py, run E2E, delete from ui.py
3. Create ui/data_intel.py    — same pattern
4. Create ui/deals_pipeline.py
5. Create ui/portfolios.py
6. Create ui/model_outputs.py
7. Create ui/wizards.py
8. Create ui/model_builder.py — last, because it has the most shared dependencies
9. Delete ui.py
```

One PR per file. Run E2E suite after each. Rollback = delete new file + revert `main.py`.

### Phase 2b — Service layer extraction (~2 weeks)

Do this **after** Phase 2a. Splitting first reveals the natural service boundaries; extracting logic before splitting creates circular imports.

Target services:
- `CapitalStructureService` — carry type validation, auto-sizing, module operations
- `TimelineService` — milestone seeding, trigger chain resolution, defaults
- `CashflowService` — cashflow computation orchestration

Result: adding a new carry type touches ~3 files instead of 6+.

### Phase 2c — Responsiveness fix

Wire HTMX OOB (out-of-band) swaps so the cashflow summary and balance bar update immediately after any form save. No new infrastructure — uses existing HTMX capability. Should be done as part of Phase 2a/2b since the routes are being touched anyway.

### Phase 3 — Cleanup (as-needed, no deadline)

- Evaluate HelloData removal
- Resolve incomplete stubs (equity_multiple, soft warning, org defaults wiring)
- Celery queue simplification (3 workers → 1–2; only if causing operational pain)
- HTMX upgrade 1.9.12 → 1.10+
- Backward-compat alias cleanup (`DealModel`, `ScenarioResult`) once all callers updated

---

## Open Decisions

1. **HelloData** — keep or cut? CLI-only, not in normal pipeline. Removing = ~200 lines, 2 files.
2. **equity_multiple** — implement the join (near-term priority?), or remove from UI until ready?
3. **Soft warning at ui.py:9393** — what was this supposed to warn about? Surface to user or delete?
4. **Canonical property type list** — which list is correct? Needs business decision before code consolidation.

---

## What We're NOT Doing

- Stack swap (FastAPI/HTMX/SQLAlchemy stays)
- UI redesign (handled separately)
- WebSocket (HTMX OOB swap is sufficient for the stated responsiveness need)
- Frontend framework (React/Vue — not justified)
- SSO
