# Enhanced Developer Fee Modeling

## Context

Developer Fee is currently a single auto-managed UseLine (`is_auto_dev_fee=True`) with one global basis choice (`purchase_price` or `tpc_excl_self`) and one global %, defaulted from Org/User settings per deal type. Engine in `app/engines/dev_fee.py`. The fee is treated as a fixed Use paid at closing; no notion of deferred fee, milestone-based release, or per-Source rules.

This breaks down in any deal with mixed capital — regulated/affordable Sources (LIHTC, tax-exempt bonds, HUD, HFA) alongside private debt or equity — because **each Source imposes a different rule about what TPC means and what fee it allows**. Tax-exempt bonds may exclude reserves and the interest reserve; LIHTC excludes land; HUD has per-unit caps; private equity is negotiated. With multiple Sources, no single basis is correct — the binding fee is the **minimum allowable across all Sources**, and which Source binds drives sponsor economics, deferred-fee sizing, and partner negotiations.

This plan also adds the structural pieces that go hand-in-hand with Source-driven sizing: **funded-at-close vs deferred fee split**, **milestone-based release schedule**, and **final holdback %**. Without them, capping the fee from Sources is half a feature — the remainder needs somewhere to go (deferred) and a schedule to come out on (milestones).

User direction on scope and UX (confirmed):
- V1 includes Source caps + funded/deferred split + milestone schedule + **deal-type variant** (Acquisition vs Acquisition+Construction vs Ground-Up).
- No hardcoded fee templates per vehicle type at the table level — Vehicle Type defaults exist as an Org-editable registry but ship empty; user fills them in for their shop.
- Overage behavior is surfaced through a **new explainer modal**: clicking the Dev Fee line in the capital stack opens a modal showing how the fee was calculated (per-Source caps, binding constraint, funded vs deferred split, milestone release).
- **Compute auto-pops the explainer modal** whenever a structural diff (Source or UseLine added/removed) or a pending custom-Use decision is detected.

## Architecture: Where Each Piece of Config Lives

Four layers. Each answers a distinct question. The structure supports the iterative "adjust Dev Fee as the deal evolves" UX the user described: Vehicle Type defaults handle standard cases, per-Vehicle-row instances handle deal-specific tuning, per-`(UseLine × Source Vehicle)` overrides handle custom Uses, and Compute auto-pops the explainer modal whenever a structural diff (Source or UseLine added/removed) is detected.

| Layer | Question it answers | What it holds |
|---|---|---|
| **Org / User defaults** | "What does our shop usually do?" | Default elected %, default scenario basis when no Source Vehicle binds, default milestone weights template, default holdback %. Already partially exists in `org_settings` / `user_settings` (`dev_fee_pct_*`, `dev_fee_basis_*`, `dev_fee_timing_*`, `dev_fee_phase_*`). Extend with milestone-weight defaults + holdback default. |
| **Source Vehicle Type defaults** (new) | "What does this kind of capital usually demand?" | New `capital_vehicle_fee_defaults` table keyed by `vehicle_type` (+ optional `equity_role`). Carries default `fee_terms` block (max_pct, per_unit_cap, absolute_cap, basis_exclusions over the system's **standard auto-generated cost categories**, regulated flag, notes). Empty rows = no opinion. Editable in a new "Capital Vehicle Defaults" Org-settings screen. Standard cost categories the defaults can reference: `acquisition`, `hard_costs`, `soft_costs`, `financing_fees`, `interest_reserve`, `operating_reserves`, `developer_overhead`, `consulting_fees`. |
| **Source Vehicle row (CapitalModule)** | "What rule does THIS capital source impose on THIS deal?" | `fee_terms` JSONB on CapitalModule. On Vehicle creation, **inherits** from the Vehicle Type defaults. User can override per instance. Also carries `fee_terms_inherited_from_type: bool` flag so UI can show "Using Vehicle Type defaults · Override" affordance and so re-running the inheritance is safe when the user edits Vehicle Type defaults. |
| **Per-`(UseLine × Source Vehicle)` overrides** (new) | "For this custom Use on this deal, which Source Vehicles include it?" | New `use_line_source_fee_basis` join table: `(use_line_id, capital_module_id, included_in_basis: bool, set_at: timestamp)`. Only written for UseLines whose `cost_category` isn't one of the standard auto-generated categories handled by Vehicle Type defaults — i.e. **custom Uses** the user added. Engine reads this for any UseLine not covered by category-level inclusion logic. Required entries are surfaced in the explainer modal as "Decide inclusion" prompts when a custom Use exists. |
| **Scenario (Dev Fee UseLine)** | "What fee am I taking, and how does it release?" | Elected `dev_fee_pct` (target), basis (kept for unregulated path / backward compat), `dev_fee_release_schedule` (list of `{milestone_id, weight}` summing to 1.0 less holdback), `final_holdback_pct`. Binding constraint, funded/deferred split, and structural-diff signal all computed at engine time and persisted on the UseLine (`dev_fee_binding_context`) for UI display. |

**Engine reducer** ("most-restrictive binds"): for each Source Vehicle with `fee_terms` populated (any non-null cap field), compute its allowable fee = `min(max_pct × Vehicle's basis, per_unit_cap × units, absolute_cap)`. Each Vehicle's basis = `sum(use_lines − basis_exclusions − auto dev fee row)`, where inclusion of each UseLine is decided by:
1. If the UseLine's `cost_category` is one of the standard auto-generated categories, follow the Vehicle's `basis_exclusions` flags for that category.
2. If the UseLine is a custom Use, read the `use_line_source_fee_basis` row for `(use_line_id, capital_module_id)`. If missing, the engine flags it as a **pending decision** in `dev_fee_binding_context.pending_custom_use_decisions` and conservatively excludes it from the basis until resolved.

Engine takes the min across all constrained Vehicles; that's the maximum allowable fee. If no Vehicle has terms, fall back to the existing scenario-level basis × elected pct path. **Overage handling**: engine always returns the elected fee (caps are surfaced in the modal, not silently applied) — user is the decision-maker. Iterative solve for fee-on-fee is already required since Dev Fee is a Use.

**Structural-diff detection**: each compute snapshots `(set of CapitalModule IDs, set of UseLine IDs)` post-run and writes it to `dev_fee_binding_context.last_compute_signature`. Next compute compares against the previous signature. If the symmetric difference is non-empty (Source or UseLine added or removed), the engine sets `dev_fee_binding_context.structural_diff_detected = True` and surfaces the deltas. UI uses this flag to auto-open the explainer modal post-compute. Pure amount changes do NOT trigger it.

**Funded vs deferred split**: after the fee dollar amount is fixed, the engine asks each Source how much of the fee it will fund at close (using its own basis allocation and pct-of-fee allocation rules). Total funded = sum across Sources. Deferred = elected fee − funded. Deferred portion is paid from operating cash flow as a subordinate claim — position in `app/engines/waterfall.py` to be confirmed during execution (typically below debt service, above sponsor equity returns; may interact with the recent Cash Flow Support Reserve work).

**Milestone release**: existing `app/models/milestone.py` milestones are the source of truth for dates. Dev Fee release schedule references existing milestone IDs (Scenario-scoped) with a weight per milestone summing to `1 − final_holdback_pct`. Holdback releases at a designated milestone (delivery / CO / conversion — user picks). Engine produces a monthly Dev Fee receipt schedule from the milestone dates × weights, separate from the funded-at-close UseLine treatment.

**Deal-type variant (Acquisition treatment)**: Dev Fee structure differs by deal archetype. Variant resolved at Scenario seed from `deal_type` (the existing per-deal-type settings keying — `dev_fee_pct_<deal_type>`, `dev_fee_basis_<deal_type>`, etc. — extends to acquisition treatment), with per-Scenario override allowed.

| Deal type | Acquisition treatment | What's modeled |
|---|---|---|
| `acquisition` (acq-only, no construction) | **Separate Acquisition Fee** | A second auto-managed UseLine `is_auto_acquisition_fee=True` carries `acquisition_fee_pct × purchase_price`. Standard Dev Fee can be zero, small, or fully disabled per Org/User default. Both fees are independently capped by their respective Source Vehicle rules and sit in the explainer modal as two distinct rows. |
| `value_add` (acquisition + rehab) | **Split-rate Dev Fee** | One auto Dev Fee UseLine, but the basis is partitioned: full `dev_fee_pct` applies to the construction/rehab portion; reduced `dev_fee_acquisition_pct` applies to the acquisition portion. Net fee = `dev_fee_pct × construction_basis + dev_fee_acquisition_pct × acquisition_basis`. Both basis halves still honor each Source Vehicle's `basis_exclusions`. |
| `ground_up_construction` (or any "construction-only") | **Full exclusion** (today's behavior) | Standard Dev Fee on TPC excl. land/acquisition. Acquisition fully excluded from the basis. No separate acquisition fee. |

Variant choice is a new field `dev_fee_acquisition_treatment` ∈ `{"separate_fee", "split_rate", "excluded"}` on the Dev Fee UseLine, defaulted from `org_settings`/`user_settings`.`dev_fee_acquisition_treatment_<deal_type>`. User can override per Scenario via the UseLine drawer.

**Edit flow after deal creation**:
- **Source Vehicle fee rule** edited on the Source Vehicle drawer (the existing capital stack panel where the user adds/edits each CapitalModule row), in a new "Developer Fee Rule" section. Starts collapsed and empty; user expands and fills the relevant fields. Each Source Vehicle on the deal carries its own rule independent of other Vehicles, even of the same `vehicle_type`.
- **Elected fee %** edited on the Dev Fee UseLine drawer (existing form).
- **Milestone release schedule + holdback** edited on the Dev Fee UseLine drawer in a new "Release Schedule" section.
- **Calculation explainer modal**: clickable from the Dev Fee row anywhere it's listed (capital stack panel, Uses table). Single canonical place where the math is shown. See UI section.

## Phase 1 (V1, shippable)

### Schema

- **New migration `0103_dev_fee_multi_source.py`** (next free slot; 0102 is the most recent in `alembic/versions/`):
  - `capital_modules.fee_terms` JSONB, default `'{}'`.
  - `capital_modules.fee_terms_inherited_from_type` Boolean, default `True`.
  - New table `capital_vehicle_fee_defaults` `(id, org_id, vehicle_type, equity_role, fee_terms JSONB, created_at, updated_at)` with `UNIQUE(org_id, vehicle_type, equity_role)`. Org-scoped so different orgs can carry different opinions.
  - New table `use_line_source_fee_basis` `(use_line_id, capital_module_id, included_in_basis Boolean, set_at)` with composite PK.
  - `use_lines.dev_fee_release_schedule` JSONB, default `'{}'` (list of `{milestone_id, weight}` + `final_holdback: {milestone_id, weight}`).
  - `use_lines.dev_fee_binding_context` JSONB, default `'{}'` (engine-written: `binding_source_id`, `binding_dollar_cap`, `headroom_by_source`, `funded_at_close`, `deferred`, `per_source_allocation`, `last_compute_signature`, `structural_diff_detected`, `pending_custom_use_decisions: list[{use_line_id, capital_module_id}]`). Display-only.
  - `use_lines.is_auto_acquisition_fee` Boolean, default `False` — new flag analogous to `is_auto_dev_fee` for the separate Acquisition Fee UseLine.
  - `use_lines.dev_fee_acquisition_treatment` VARCHAR(16) nullable — `{"separate_fee", "split_rate", "excluded"}` on the Dev Fee UseLine only; null on other lines.
  - `use_lines.dev_fee_acquisition_pct` Numeric(8,4) nullable — used only when `dev_fee_acquisition_treatment="split_rate"`.
  - `use_lines.acquisition_fee_pct` Numeric(8,4) nullable — used only on the auto Acquisition Fee UseLine.
  - `org_settings` / `user_settings`: add `dev_fee_milestone_weights_<deal_type>`, `dev_fee_final_holdback_pct_<deal_type>`, `dev_fee_acquisition_treatment_<deal_type>`, `dev_fee_acquisition_pct_<deal_type>`, `acquisition_fee_pct_<deal_type>`.
- **New Pydantic schemas** in `app/schemas/capital.py` and `app/schemas/deal.py`:
  - `CapitalFeeTermsSchema { max_pct, per_unit_cap, absolute_cap, basis_exclusions: list[str], basis_inclusions_override: Optional[list[str]], regulated: bool, notes: Optional[str] }`. `extra="allow"`.
  - `DevFeeReleaseScheduleSchema { weights: list[{milestone_id: UUID, weight: Decimal}], final_holdback: {milestone_id: UUID, pct: Decimal} }`.
  - `DevFeeBindingContextSchema` (read-only display schema).
- Attach `fee_terms` to `CapitalModuleSchema` alongside existing `source`/`carry`/`exit_terms`.

### Engine (`app/engines/dev_fee.py`)

New helpers:
- `_inherit_vehicle_fee_terms(module, session) -> CapitalFeeTermsSchema` — when `fee_terms_inherited_from_type=True`, resolve the live default from `capital_vehicle_fee_defaults` for this Vehicle's `vehicle_type`/`equity_role`. Override returns the stored `fee_terms` directly.
- `_use_in_vehicle_basis(use_line, module, fee_terms, overrides_index) -> tuple[bool, bool]` — returns `(included, decision_pending)`. For standard categories: apply `basis_exclusions`. For custom Uses: look up `use_line_source_fee_basis`; if missing, return `(False, True)`.
- `_vehicle_basis(module, use_lines, fee_terms, overrides_index, inputs) -> Decimal` — sum of `included` UseLines.
- `_vehicle_allowable(module, use_lines, units, inputs) -> Decimal | None` — apply `max_pct`, `per_unit_cap`, `absolute_cap`; return `None` if no terms set.
- `_binding_constraint(modules, use_lines, units, inputs) -> tuple[Decimal | None, UUID | None]` — min allowable across constrained Vehicles.
- `_split_funded_deferred(elected_fee, modules, use_lines, inputs) -> dict` — per-Vehicle allocation of the fee, summed to `funded_at_close`; remainder is `deferred`.
- `_build_release_schedule(use_line, milestones) -> list[{date, amount}]` — translate milestone weights × elected_fee into dated receipts; holdback emitted at its assigned milestone.
- `_compute_structural_signature(modules, use_lines) -> str` — deterministic hash of `(sorted CapitalModule IDs, sorted UseLine IDs)`. Used for structural-diff detection.

`compute_dev_fee` extended to:
1. Resolve effective `fee_terms` for every CapitalModule via inheritance.
2. Index `use_line_source_fee_basis` overrides for fast lookup.
3. **Apply deal-type variant**:
   - `excluded` → existing behavior. Acquisition Use lines excluded from basis. No Acquisition Fee UseLine.
   - `split_rate` → partition basis into acquisition portion (Use lines with `cost_category="acquisition"`) and construction portion (everything else, less standard exclusions). Elected fee = `dev_fee_pct × construction_basis + dev_fee_acquisition_pct × acquisition_basis`. Both halves still honor each Vehicle's `basis_exclusions` (a Vehicle that excludes land just won't count it in the acquisition portion).
   - `separate_fee` → standard Dev Fee computed as in `excluded` mode (acquisition fully out). Additionally, compute the auto Acquisition Fee UseLine: amount = `acquisition_fee_pct × purchase_price`. Acquisition Fee participates in the binding constraint as its own fee target — engine runs `_binding_constraint` once per fee (Dev Fee and Acquisition Fee separately), so a Vehicle can cap either or both. Funded/deferred split applies to both.
4. Compute per-Vehicle allowables and binding constraint(s); collect `pending_custom_use_decisions`; populate `dev_fee_binding_context` without overriding the elected fee(s).
5. Compute funded vs deferred split for each fee; store in `dev_fee_binding_context` (split-rate keeps a single context; separate-fee keeps two parallel blocks).
6. Build release schedule from `dev_fee_release_schedule` + milestone dates (Acquisition Fee released at closing/first milestone by default in `separate_fee` mode).
7. Compute structural signature, compare against `last_compute_signature`, set `structural_diff_detected` accordingly, then write new signature.

Cashflow engine integration (`app/engines/cashflow.py`):
- Funded-at-close portion remains in the auto UseLine for sizing (today's behavior).
- Deferred portion becomes a subordinate operating-cash claim. Add `_deferred_dev_fee_payments` to the cashflow loop, drawn from monthly cash post-debt-service, ahead of equity distributions. Final position vs Cash Flow Support Reserve and waterfall preferred return to be confirmed during execution — likely subordinate to operating reserves but senior to sponsor equity.
- Milestone-based release schedule populates a separate `_dev_fee_receipts` series for cash-flow timing display (does not affect Uses sizing).

### Cash Flow Support Reserve & Waterfall interaction

Recent work (May 2026) added bank-account proof + Cash Flow Support Reserve. The deferred Dev Fee payment slot must be sequenced clearly relative to the CFS draw logic. Execution step must:
- Read `app/engines/cashflow.py` deferred-claim ordering.
- Confirm placement: typical CRE order is debt service → operating reserve replenishment → deferred Dev Fee → preferred return → promote. Validate against existing waterfall.py tiers.
- Update Appendix G (FINANCIAL_MODEL.md) if ordering changes.

### UI

**Capital Vehicle Defaults screen** (new — Org settings area, route TBD during execution): table of vehicle types × equity roles with editable `fee_terms` per row. Save persists to `capital_vehicle_fee_defaults`. Updating a row does NOT retroactively change Vehicle rows on existing deals (the inheritance flag on each row is the source of truth — only "Reset to Type defaults" re-applies). Note added in UI: "These defaults apply to NEW Source Vehicles. Existing deals are unaffected until you click 'Reset to Type defaults' on the Vehicle row."

**Source Vehicle drawer — "Developer Fee Rule" section** (new collapsible block on the CapitalModule form, locate template path during execution — likely `app/templates/partials/capital_module_form.html`):
- Header shows inheritance state: "Using Tax-Exempt Bond defaults · [Override]" or "Custom override · [Reset to defaults]".
- Fields shown when expanded: `max_pct` (number with % suffix), `per_unit_cap` ($), `absolute_cap` ($), checkbox list for `basis_exclusions` over standard categories (land/acquisition, interest_reserve, operating_reserves, developer_overhead, consulting_fees, financing_fees, soft_costs, hard_costs), `regulated` toggle, `notes` textarea.
- When `fee_terms_inherited_from_type=True`, fields display the resolved Type defaults greyed out. Clicking Override copies them in as editable instance values.
- Form post → `app/api/routers/capital.py` updates `fee_terms` JSONB and flips inheritance flag.

**Dev Fee UseLine drawer — extended** (`app/templates/partials/model_builder_line_form.html`):
- Existing fields kept (`dev_fee_pct`, basis radio).
- New **Acquisition Treatment** picker at the top of the form: three radios (`Separate Acquisition Fee`, `Split-Rate`, `Excluded`). Default pulled from `dev_fee_acquisition_treatment_<deal_type>` org/user setting at seed; overridable per Scenario.
  - When `Split-Rate` selected → reveal `dev_fee_acquisition_pct` field.
  - When `Separate Acquisition Fee` selected → reveal a notice "An Acquisition Fee UseLine has been added. Edit its % on the Acquisition Fee row." (and engine ensures the auto Acquisition Fee row exists, or removes it on switch away).
  - When `Excluded` → no extra fields.
- New section "Release Schedule": list of Scenario milestones with a weight input next to each. Validation: weights + `final_holdback_pct` sum to 100%. Holdback milestone picker.
- New small inline summary: "Funded at close: $X · Deferred: $Y · Capped at: $Z by [Source name]" with a "Show calculation →" link that opens the explainer modal.

**Acquisition Fee UseLine drawer** (auto-created when `dev_fee_acquisition_treatment=separate_fee`):
- Read-only "Current Amount" (engine-computed).
- Editable `acquisition_fee_pct` field. Basis is always `purchase_price` (locked).
- Same "Show calculation →" link opens the same explainer modal scrolled to the Acquisition Fee section.

**Calculation Explainer Modal** (new HTMX partial — `app/templates/partials/dev_fee_explainer_modal.html`, route in `app/api/routers/ui.py`):
- Triggers:
  - Manual: clicking the Dev Fee row in the capital stack panel, the Dev Fee line in the Uses table, or the "Show calculation" link from the UseLine drawer.
  - Auto: post-Compute, when the compute response carries `structural_diff_detected=True` or `pending_custom_use_decisions` is non-empty. Modal HTMX-swaps in as a modal overlay with a banner: "Capital stack changed. Confirm Dev Fee treatment before relying on these numbers."
- Sections:
  1. **Pending decisions** (only when present): per-`(custom UseLine × constrained Source Vehicle)` toggle "Include in basis?". Saving writes `use_line_source_fee_basis` rows.
  2. **Acquisition treatment summary**: shows the active variant (Separate / Split-Rate / Excluded) with a small "Change on Dev Fee drawer" link. In Split-Rate mode, shows the construction basis $ × full rate and acquisition basis $ × reduced rate, each on its own line.
  3. **Elected fee(s)**: in `separate_fee` mode, two rows (Dev Fee + Acquisition Fee), each with its own target % × basis = $X. Otherwise one row.
  4. **Per-Vehicle allowance table**: one row per Vehicle per fee. Columns: Vehicle name, vehicle type, basis included summary, basis $ value, max %, per-unit cap, absolute cap, allowable $. Bold the binding row. In `separate_fee` mode the table is grouped: "Caps on Dev Fee" then "Caps on Acquisition Fee".
  5. **Binding result(s)**: "Strictest Vehicle allows $X. Your elected fee is $Y. Overage: $Z." (or "within all caps"), shown per fee in `separate_fee` mode.
  6. **Funded vs deferred**: stacked bar — funded at close (by Vehicle breakdown) + deferred. Per fee in `separate_fee` mode.
  7. **Release schedule**: table of milestone, date, weight, $ amount, final holdback row at bottom. Acquisition Fee released line shown alongside in `separate_fee` mode.
- Edits in section 1 (Pending decisions) trigger an HTMX recompute on save. Other sections are read-only — clicking a Vehicle name routes to the Vehicle drawer, clicking the elected fee row routes to the UseLine drawer.

**Capital stack panel** (locate during execution): Dev Fee row should be clickable to open the modal. May already render as a Use — confirm.

### Tests

- `tests/engines/test_dev_fee_multi_source.py` (new):
  - Single Vehicle with `max_pct=5.5` and `basis_exclusions=["land"]` → binding_dollar_cap = 5.5% × (TPC − land).
  - Two Vehicles with caps → min binds, `binding_source_id` populated.
  - Vehicle with `per_unit_cap=25_000` and 100 units → allowable = $2.5M.
  - Vehicle with `absolute_cap=$2M` → allowable = $2M.
  - No Vehicles with `fee_terms` → behavior matches today, `binding_context.binding_source_id is None`.
  - User-elected % above binding cap → elected wins (per UX direction), overage reported in context.
- `tests/engines/test_dev_fee_inheritance.py` (new):
  - Create Vehicle with `fee_terms_inherited_from_type=True`, ensure engine reads live defaults from `capital_vehicle_fee_defaults`.
  - Override on instance → engine uses instance, ignores Type defaults.
  - Updating Type defaults does NOT change a Vehicle row whose flag is False (override).
- `tests/engines/test_dev_fee_custom_use_decisions.py` (new):
  - Custom UseLine + constrained Vehicle, no `use_line_source_fee_basis` row → custom Use excluded from basis, `pending_custom_use_decisions` lists the pair.
  - With override row `included=True` → Use included in basis.
  - With override row `included=False` → Use excluded, no pending entry.
- `tests/engines/test_dev_fee_structural_diff.py` (new):
  - Initial compute writes signature.
  - Second compute with no structural changes → `structural_diff_detected=False`.
  - Add a new CapitalModule → `structural_diff_detected=True` with delta listing the new module.
  - Remove a UseLine → `structural_diff_detected=True` with delta listing the removed line.
  - Pure amount change on existing rows → `structural_diff_detected=False`.
- `tests/engines/test_dev_fee_acquisition_variants.py` (new):
  - `excluded` mode → Use lines with `cost_category=acquisition` not in basis; no Acquisition Fee row.
  - `split_rate` mode with `dev_fee_pct=4.0`, `dev_fee_acquisition_pct=1.5`, construction basis $20M, acquisition basis $5M → fee = $0.875M ($0.8M + $0.075M).
  - `separate_fee` mode with `acquisition_fee_pct=2.0`, `purchase_price=$8M`, `dev_fee_pct=5.0`, construction basis $15M → Dev Fee = $0.75M, Acquisition Fee = $0.16M, both auto rows present.
  - Switching from `separate_fee` to `excluded` removes the Acquisition Fee row.
  - Vehicle with `max_pct=3.0` and `regulated=True` caps Acquisition Fee independently from Dev Fee in `separate_fee` mode.
  - Split-rate respects per-Vehicle `basis_exclusions` (e.g. Vehicle that excludes land → land removed from acquisition portion).
- `tests/engines/test_dev_fee_funded_deferred.py` (new):
  - Sources fund $1.5M of $2M fee → `funded_at_close=1.5M`, `deferred=0.5M`.
  - Deferred portion paid from operating cash in correct waterfall position; assert payment timing matches release schedule.
  - All-equity deal with full fee → deferred = 0 if sponsor equity covers it.
- `tests/engines/test_dev_fee_release_schedule.py` (new):
  - Weights {pre_dev: 0.1, const_start: 0.2, completion: 0.3, stabilization: 0.3} + 10% holdback at conversion → 5 dated receipts summing to elected fee.
  - Missing milestone → engine reports error, doesn't silently zero out.
  - Weights don't sum to 1 − holdback → validation error.
- `tests/api/test_capital_module_fee_terms.py` (new): POST/PATCH `fee_terms`, assert JSONB round-trips.
- `tests/api/test_dev_fee_explainer_modal.py` (new): GET the explainer endpoint, assert all sections render correctly for both bound and unbound cases.
- Extend `tests/engines/test_dev_fee.py` for regression guard: no `fee_terms` anywhere → behavior identical to pre-change.

### Critical Files (Phase 1)

- `app/models/capital.py` — `CapitalModule.fee_terms`, `CapitalModule.fee_terms_inherited_from_type` (new columns); new `CapitalVehicleFeeDefaults` model; new `UseLineSourceFeeBasis` join model.
- `app/models/deal.py` — `UseLine.dev_fee_release_schedule`, `UseLine.dev_fee_binding_context` (new columns).
- `app/schemas/capital.py` — `CapitalFeeTermsSchema`, `CapitalVehicleFeeDefaultsSchema`; attach `fee_terms` to `CapitalModuleSchema`.
- `app/schemas/deal.py` — `DevFeeReleaseScheduleSchema`, `DevFeeBindingContextSchema`, `UseLineSourceFeeBasisSchema`.
- `alembic/versions/0103_dev_fee_multi_source.py` — new migration (capital_modules + use_lines + capital_vehicle_fee_defaults + use_line_source_fee_basis + settings columns).
- `app/engines/dev_fee.py` — new helpers (inheritance, structural-diff, custom-Use overrides) and extended `compute_dev_fee`.
- `app/engines/cashflow.py` — deferred Dev Fee subordinate claim in operating cash loop; integrate with CFS / waterfall ordering.
- `app/engines/waterfall.py` — confirm deferred Dev Fee tier position.
- `app/api/routers/capital.py` — accept/persist `fee_terms` on Source Vehicle create/update; CRUD for `capital_vehicle_fee_defaults`; CRUD for `use_line_source_fee_basis`.
- `app/api/routers/ui.py` — new route for explainer modal HTMX partial; auto-open trigger from compute response; new "Capital Vehicle Defaults" settings screen route; extended UseLine save route for release schedule.
- `app/templates/partials/capital_module_form.html` (or equivalent — confirm during execution) — "Developer Fee Rule" section with inheritance affordance.
- `app/templates/settings/capital_vehicle_defaults.html` — new Org settings page.
- `app/templates/partials/model_builder_line_form.html` — "Release Schedule" section + "Show calculation" link.
- `app/templates/partials/dev_fee_explainer_modal.html` — new modal partial with "Pending decisions" section.
- `tests/engines/test_dev_fee.py` — regression guard.
- `tests/engines/test_dev_fee_multi_source.py` — new.
- `tests/engines/test_dev_fee_inheritance.py` — new.
- `tests/engines/test_dev_fee_custom_use_decisions.py` — new.
- `tests/engines/test_dev_fee_structural_diff.py` — new.
- `tests/engines/test_dev_fee_acquisition_variants.py` — new.
- `tests/engines/test_dev_fee_funded_deferred.py` — new.
- `tests/engines/test_dev_fee_release_schedule.py` — new.
- `tests/api/test_capital_module_fee_terms.py` — new.
- `tests/api/test_capital_vehicle_fee_defaults.py` — new.
- `tests/api/test_dev_fee_explainer_modal.py` — new.
- `docs/FINANCIAL_MODEL.md` — append Dev Fee multi-source section + update Appendix G if waterfall ordering changes.

## Phase 2+ Roadmap (deferred)

- **Risk & Tax Layers**: scenario haircuts for overruns / lease-up delay; related-party flag + conservative-scenario haircut; separated tax-recognition vs cash-receipt timelines (handoff doc sections 7, 8, 10).
- **Construction-Fund Reinvestment Module**: draw curve × reinvest rate × instrument × indenture release timing; realized surplus routed to deferred fee / debt redemption / other Uses per indenture (handoff doc section 11).

## Verification

1. **Unit tests** (all new + regression):
   ```
   uv run pytest tests/engines/test_dev_fee.py tests/engines/test_dev_fee_multi_source.py tests/engines/test_dev_fee_funded_deferred.py tests/engines/test_dev_fee_release_schedule.py tests/api/test_capital_module_fee_terms.py tests/api/test_dev_fee_explainer_modal.py -v
   ```
   All green.
2. **Phase B regression** (Sources = Uses invariant must hold with new fee logic):
   ```
   uv run python scripts/test_phase_b_debt.py --base-url https://viciniti.deals --auth tests/e2e/auth-state.json
   ```
3. **E2E**: extend or add `tests/e2e/test_dev_fee_explainer.py` to:
   - Create a deal with two Sources, give each different fee_terms.
   - Open the Dev Fee explainer modal, confirm per-Source allowance table, binding row, funded/deferred breakdown, release schedule.
   - Edit one Source's `max_pct`, confirm modal recalculates without page reload.
   ```
   $env:E2E_BASE_URL="https://viciniti.deals"; uv run pytest tests/e2e/test_dev_fee_explainer.py -v
   ```
4. **Manual smoke on staging**: bond+LIHTC deal — confirm binding row matches expected (lower of the two), milestone schedule shows correct dates, deferred portion appears in operating cash flow at the right time and ahead of equity distributions, CFS proof still passes.
5. **Bank account proof regression**: ensure adding deferred Dev Fee as a subordinate claim doesn't cause CFS sizing to under-cover. Run `python -m app.scripts.backfill_bank_account_proof` against a representative sample and confirm scenarios that were solvent pre-change remain solvent.
