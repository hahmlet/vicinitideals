# UI Needs — Known Challenges and Refactor Requirements

**Status**: Tracking document — updated as issues are identified
**Last updated**: 2026-04-16
**Context**: The engine and data model are being refined first. This document captures UI work to inform a future refactor once the model stabilizes.

---

## Philosophy

An accurate model that is hard to use is a good problem to have. A pretty app that lost function over form is a bad problem to have. The UI refactor happens AFTER the data model is stable.

---

## Architectural Issues

### 1. Input/Output Flip-Flop
**Problem**: Users constantly switch between Deal Setup Wizard (inputs) and Model Builder tabs (outputs). No way to see both simultaneously.
**Solution**: Side-by-side layout — collapsible sidebar showing relevant inputs alongside the output view. Pro Forma tab shows rent/vacancy/escalation sidebar. Cash Flow tab shows debt terms sidebar.
**See**: [model-builder-architecture.md](feature-plans/model-builder-architecture.md)

### 2. Input Authority Confusion
**Problem**: Some fields are editable in multiple places (e.g., unit count appears in UnitMix AND Income Streams). No enforcement of where edits should happen.
**Solution**: Input authority map — each field has ONE canonical edit location. Other views are read-only displays. Example: unit count editable in Building Editor only, displayed (not editable) in Revenue tab.

### 3. No Model Consistency Validation
**Problem**: When upstream inputs change (unit count, exit cap, debt terms), downstream values may become stale. No notification. User discovers inconsistencies accidentally.
**Solution**: Persistent notification center with model validation rules. Issues visible from any tab. Clearable only by resolving, not dismissing. Logged with timestamps for audit trail.

### 4. Building Editor Not Always Visible
**Problem**: UnitMix editor is hidden for single-parcel/single-building deals. Need to always show the building editor — it's where market rent, in-place rent, and unit strategy assignments live.
**Solution**: Always render building editor regardless of parcel/building count.

---

## Visual / Styling Issues

### 5. CSS Inconsistencies
**Problem**: Styles vary across pages — different spacing, font sizes, border treatments. No design system.
**Solution**: Define a component library (stat cards, form fields, tables, panels, buttons) with consistent tokens. Apply globally.

### 6. Color Scheme
**Problem**: No deliberate color palette. Mix of hardcoded colors and CSS variables. Investor-facing exports use a separate palette from the app.
**Solution**: Define primary/secondary/accent/surface palette. Dark mode consideration. Professional CRE aesthetic (deep navy, clean whites, muted accents — similar to investor export palette).

### 7. Labeling Inconsistencies
**Problem**: Terminology varies. "Deal Model" vs "Scenario" vs "Model". "Revenue" vs "Income". "Sources" vs "Capital Stack". Phase names don't always match between wizard and builder.
**Solution**: Terminology audit. Define canonical names in CLAUDE.md and enforce across all templates.

### 8. Project Type Language
**Problem**: "Minor Renovation" actually means "Deferred Maintenance" (not adding value, just catching up to market). "Major Renovation" means "Value-Add." These labels mislead users.
**Solution**: Rename project types to match business intent:
- `acquisition` → `acquisition_deferred_maintenance` or `acquisition_ltl_catchup`
- `value_add` → `acquisition_value_add`
- Keep internal enum values for backward compat, change display labels.

---

## Missing UI Components

### 9. New Fields Without UI (from April 16 engine work)

| Field | Model | Has Backend | Has UI | Priority |
|---|---|---|---|---|
| `asset_mgmt_fee_pct` | OperationalInputs | Yes | No — needs location decision (user/org setting vs deal-level) | Medium |
| `lease_up_curve` | OperationalInputs | Yes | Partial — needs wizard integration | High |
| `lease_up_curve_steepness` | OperationalInputs | Yes | Partial — needs wizard integration | High |
| `market_rent_per_unit` | UnitMix | Yes | No — needs building editor integration | High |
| `in_place_rent_per_unit` | UnitMix | Yes | No — needs building editor integration | High |
| `renovation_absorption_rate` | IncomeStream | Yes | No — needs income stream form addition | Medium |
| `renovation_capture_schedule` | IncomeStream | Yes | No — decided not to expose in UI (continuous ramp only) | N/A |
| `refi_cap_rate_pct` | CapitalSourceSchema | Yes | No — show only when dual_constraint sizing | Low |
| `sensitivity_matrix` | OperationalOutputs | Yes (storage) | No — needs dedicated tab with compute trigger | High |

### 10. UnitMix Strategy Assignment UI
**Problem**: No way to assign per-unit-type strategies (base escalation, LTL catchup, value-add renovation).
**Solution**: Strategy dropdown per row in UnitMix editor. "Apply to Model" button auto-generates income streams.
**See**: [model-builder-architecture.md](feature-plans/model-builder-architecture.md)

### 11. Sensitivity Analysis Tab
**Problem**: No sensitivity analysis visualization.
**Solution**: New tab below Cash Flow. Two-axis dropdown (default: exit cap × rent growth). Target metric dropdown (default: Levered IRR). 5×5 color-coded grid. "Run Sensitivity" button triggers 25 compute cycles. Read-only — does NOT feed back into model.

### 12. Refi/Prepay Line Items in Cash Flow View
**Problem**: Refi net proceeds and prepay penalty line items are generated by the engine but not explicitly called out in the cash flow table display.
**Solution**: These already appear as CashFlowLineItem rows. The CF table template may need to style them distinctly (e.g., indented, different color) so the refi event is visible.

---

## Deal Setup Wizard Improvements

### 13. Step 4 (Debt Terms) Growing Complex
**Problem**: Three sizing modes (gap-fill, DSCR-capped, dual-constraint), LTV input, DSCR minimum, per-loan terms. Getting crowded.
**Solution**: Consider splitting debt into sub-steps or a tabbed layout within step 4.

### 14. No Wizard Step for Waterfall / Partnership Terms
**Problem**: Waterfall tiers are configured in the model builder, not the wizard. AM fee has no home.
**Solution**: Add a wizard step for partnership structure: waterfall tiers, AM fee, sponsor/LP splits.

### 15. Default Expense Categories
**Problem**: Deal setup doesn't seed a standard set of expense lines matching industry consensus.
**Solution**: Auto-seed from consensus list: RE Taxes, Insurance, Utilities, R&M, Management Fee, Payroll, Marketing, G&A, Turnover/Make-Ready, CapEx Reserve. User deletes what doesn't apply.

---

## Data Display Issues

### 16. Cash Flow Table — Monthly vs Annual Toggle
**Problem**: Cash flow shows monthly detail. Investors want annual summaries. No toggle.
**Solution**: Add monthly/annual toggle. Annual view sums 12-month buckets. This is also needed for the investor Excel export.

### 17. Sources & Uses — No Reconciliation Display
**Problem**: No visible "Sources - Uses = Gap/Surplus" line. User has to mentally check balance.
**Solution**: Add reconciliation row at bottom of S&U panel with color indicator (green = balanced, red = gap).

### 18. Waterfall Distribution Timeline
**Problem**: No visualization of LP/GP cash flows over time.
**Solution**: Per-period distribution chart or table showing LP vs GP cash flows, cumulative distributions, and return metrics per period.

---

## Performance / Technical

### 19. ui.py at 8,000+ Lines
**Problem**: Single monolithic route file. Hard to navigate, slow linting.
**Solution**: Split into sub-routers (auth, listings, deals, model_builder, parcels, etc.).

### 20. Template Includes vs Components
**Problem**: Templates use `{% include %}` for partials but no component abstraction. Repeated patterns (stat cards, form fields) are copy-pasted.
**Solution**: Jinja2 macros for common components. Or evaluate a lightweight component approach.

---

*This document is a living tracker. Add items as they're identified. Remove items when resolved. Don't wait for the UI refactor to fix critical usability blockers.*
