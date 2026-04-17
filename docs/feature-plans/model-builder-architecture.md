# Model Builder Architecture Redesign

**Status**: Design phase — not yet started
**Last updated**: 2026-04-16
**Context**: Emerged from CRE model cross-analysis and UX discussion about input/output workflows

---

## Problem Statement

As the financial model grows in sophistication (LTL, renovation strategy, sensitivity analysis, dual-constraint sizing), the number of inputs is increasing. The current architecture — Deal Setup Wizard for initial setup, Model Builder tabs for viewing/editing — creates a constant flip-flop between assumptions and outputs. Users need to see both simultaneously.

---

## Core Architectural Decisions

### 1. Deal Setup Wizard = Single Source of Truth

The wizard is where ALL primary inputs are defined:
- Unit mix (counts, SF, rents, market rents, renovation strategy)
- Timeline (phases, durations, milestones)
- Debt terms (rate, amort, IO, sizing mode, LTV, DSCR)
- Income strategy (LTL catchup, value-add, base escalation per unit type)
- Expense assumptions
- Exit assumptions (cap rate, selling costs, hold period)
- Waterfall structure

### 2. Model Builder Tabs = Computed Views (Mostly Read-Only)

Revenue, Expenses, Cash Flow, Sources & Uses, Waterfall — these show computed results. Limited overrides allowed:
- Adding one-off income streams (cell tower, billboard)
- Adding miscellaneous expense lines
- Manually setting a capital module amount (real term sheet)
- Notes/annotations

**Everything else flows from the wizard.** Users cannot override unit count in Revenue — they go back to Unit Mix.

### 3. No Silent Preservation of Stale Data

When upstream inputs change:
- Derived values auto-update on next Compute
- Overridden values are flagged, not silently preserved
- A persistent banner surfaces ALL items that may need review
- Banner is visible from any tab, clearable only by resolving

---

## Unit-Level Strategy Model

Three strategies assignable per unit type in UnitMix:

| Strategy | Description | Rent Trajectory |
|---|---|---|
| **Base Escalation** | Unit is fine as-is | `in_place` → normal annual escalation (3%/yr) |
| **LTL Catchup** | Deferred maintenance, raise to market | `in_place` → accelerated escalation (capped at `ltl_catchup_cap`) → `market_rent` → normal |
| **Value-Add Renovation** | Full renovation to premium | `in_place` → renovation → `post_reno_rent` → normal escalation |

### LTL Catchup Math

Global hardcoded constant: `ltl_catchup_cap = 10%` (max annual rent increase).

```
annual_increase = min(market_rent - current_rent, current_rent × ltl_catchup_cap)
```

Duration is not user-set — it's a natural consequence of the gap size and cap:
- $1,200 in-place, $1,500 market, 10% cap:
  - Year 1: +$120 → $1,320
  - Year 2: +$132 → $1,452
  - Year 3: +$48 → $1,500 (gap closed)
  - Year 4+: normal 3% escalation

### Renovation Supersedes LTL

If a unit is in the Value-Add pool, it goes directly from `in_place_rent` to `post_reno_rent`. The LTL gap is captured implicitly — there's no intermediate step at `market_rent`.

### UnitMix Fields (Per Unit Type)

```
| Unit Type | Count | Avg SF | In-Place | Market | Post-Reno | Strategy     | % to Reno |
|-----------|-------|--------|----------|--------|-----------|--------------|-----------|
| 1BR/1BA   | 80    | 650    | $1,200   | $1,500 | —         | LTL Catchup  | 0%        |
| 2BR/1BA   | 120   | 850    | $1,400   | $1,700 | $2,000    | Value-Add    | 100%      |
```

"Apply to Model" auto-generates appropriate IncomeStream rows:
- LTL units → stream with `catchup_escalation` parameters
- Value-Add units → stream with `renovation_absorption_rate`
- Base units → stream with normal escalation

---

## Input Authority Map

| Data | Editable In | Read-Only Display In |
|---|---|---|
| Unit mix (count, SF, rents) | Deal Setup / Building Editor | Revenue tab |
| Unit strategy (LTL/value-add/base) | Deal Setup / UnitMix editor | Revenue tab |
| Rent escalation rate | Deal Setup | Revenue tab, Pro Forma |
| Expense line items | Deal Setup (or inline add) | Expenses tab |
| Debt terms (rate, amort, IO) | Deal Setup step 4 | Sources tab |
| Debt sizing mode | Deal Setup step 4 | Sources tab |
| Exit cap rate, hold period | Deal Setup | Divestment tab |
| Waterfall tiers | Deal Setup (or inline add) | Waterfall tab |
| Income stream overrides | Revenue tab (add one-off only) | — |
| Capital module override | Sources tab (manual amount only) | — |

---

## Notification / Model Consistency Center

### Concept

A persistent issue tracker for model state, not toast notifications.

```
🔔 Model Issues (2)
├─ ⚠ Unit count changed: 1BR from 80→72 but "1BR Rent" stream 
│    still uses 80 units. [Go to Unit Mix]
└─ ⚠ Exit cap changed 5.5%→6.0%. Debt was auto-sized at old 
     cap. Re-compute to update. [Re-Compute Now]
```

### Behavior
- Visible from any tab (persistent banner or badge)
- Issues logged with timestamps
- Clearable only by resolving (not dismissing)
- Accessible in a notification center for history
- Triggered by a validation engine that runs after every edit

### Validation Rules (examples)
- Income stream unit_count ≠ UnitMix unit_count for that type
- Debt auto-sized but inputs changed since last compute
- Exit cap changed but not re-computed
- Sources ≠ Uses after manual override
- DSCR below minimum after input change

---

## UX Pattern: Side-by-Side Inputs + Outputs

**Problem:** Users flip between wizard (inputs) and tabs (outputs).

**Solution:** Split-screen or collapsible sidebar showing relevant inputs alongside the output view:

- **Pro Forma tab** → sidebar shows: rent growth, vacancy %, expense escalation, management fee
- **Cash Flow tab** → sidebar shows: debt terms, IO period, DSCR
- **Sources & Uses tab** → sidebar shows: sizing mode, LTV, closing costs
- **Waterfall tab** → sidebar shows: tier structure, pref return, promote splits

Change an input in the sidebar → "Re-Compute" button lights up → outputs update in place.

This eliminates the flip-flop entirely. The wizard remains for initial setup and major changes; the sidebar handles day-to-day tweaking.

---

## Implementation Priority

1. **Input authority enforcement** — prevent edits in wrong location (e.g., no unit_count override in Revenue)
2. **Notification center** — validation engine + persistent issue display
3. **Auto-generate income streams from UnitMix strategy** — "Apply to Model" workflow
4. **LTL catchup escalation** — engine support for accelerated-then-normal curve
5. **Sidebar input panels** — significant UI refactor, do last

---

## Relationship to Other Feature Plans

- [Investor Excel Export](investor-excel-export.md) — exports the output of this model
- [CRE Model Cross-Analysis](cre-model-cross-analysis.md) — identified the gaps this plan addresses
- Sensitivity Analysis tab — read-only what-if explorer, no input feedback
