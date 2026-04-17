# CRE Model Cross-Analysis: Best-Practices Synthesis

**Status**: Research complete
**Last updated**: 2026-04-16
**Models analyzed**: 5 (stored in `docs/models/`)

---

## Models Analyzed

| # | Model | Source | Focus | Complexity |
|---|---|---|---|---|
| 1 | HelloData MultiFamily | HelloData.ai | Value-add acquisition, refi | Simple (1 sheet, 100 rows) |
| 2 | MF Acquisition v2.41 | Adventures in CRE | Acquisition with unit-level rent roll | Heavy (15 tabs, named ranges) |
| 3 | Apartment Development v2.97 | Adventures in CRE | Ground-up development | Institutional (7 tabs, 139 periods, macros) |
| 4 | PropRise Pro Forma | PropRise.ai | Value-add acquisition | Medium (7 tabs, clean template) |
| 5 | Building_I_Want v5 | A Simple Model | Multi-scenario acquisition | Heavy (8 tabs, 5,125 formulas) |

---

## Consensus Features (present in 3+ models — must have)

| Feature | HD | A.CRE Acq | A.CRE Dev | PropRise | ASimple | We Have |
|---|---|---|---|---|---|---|
| Annual pro forma (GPR to NOI) | Y | Y | Y | Y | Y | Y |
| Vacancy % of GPR | Y | Y (unit-level) | Y | Y | Y | Y |
| Expense escalation (annual %) | Y | Y | Y | Y | Y | Y |
| Rent/income escalation | Y | Y | Y | Y | Y | Y |
| IO to amortizing debt transition | Y | Y | Y (conditional perm) | Y | Y (full amort) | Y (4 carry types) |
| IRR (levered + unlevered) | Y | Y | Y | Y | Y | Y |
| Equity multiple / MOIC | Y | Y | Y | Y | Y | Y |
| DSCR per year | Y | Y | - | Y | - | Y |
| Exit via NOI / cap rate | Y | Y | Y | Y | Y | Y |
| Selling costs at disposition | Y | Y | Y | - | - | Y |
| Closing costs on acquisition | Y | Y | Y | - | Y | Y |
| Management fee (% of EGI) | Y | Y | Y | Y | - | Y |
| CapEx reserve / replacement | - | Y (3 types) | Y | Y | - | Y |
| Lease-up occupancy ramp | Y (linear) | Y (unit-level) | Y (S-curve) | Y (capture rate) | - | Y (linear) |
| Hold period (variable years) | Y (10yr) | Y | Y | Y (10yr) | Y (7yr) | Y |

## Features in 2 Models (strong candidates)

| Feature | Models | We Have | Status |
|---|---|---|---|
| Concessions / rent abatement | HelloData, A.CRE Acq | Y (concessions_pct) | Done |
| Bad debt / credit loss | HelloData, A.CRE Dev | Y (bad_debt_pct) | Done |
| Waterfall with promote tiers | HelloData, A.CRE Acq, A.CRE Dev | Y (N-tier) | Done |
| Sponsor catchup | HelloData, A.CRE Acq | Y | Done |
| Cash-out refi | HelloData, A.CRE Dev | Y | Done |
| Prepay penalty | HelloData, A.CRE Dev | Y | Done |
| AM fee (pre-distribution) | HelloData, A.CRE Dev | Y | Done |
| Dual LTV/DSCR constraint | HelloData | Y (dual_constraint) | Done |
| Balloon balance tracking | HelloData, ASimple | Y | Done |
| Renovation premium phase-in | HelloData, PropRise | Y (renovation_absorption_rate) | Done |
| Sensitivity matrix | PropRise, A.CRE Acq | Engine exists, not on export | Planned |
| Multiple purchase price methods | A.CRE Acq (4 methods) | Manual only | Low |
| Loss-to-lease tracking | A.CRE Acq, ASimple, PropRise | No | **Gap** |
| Unit-level rent roll | A.CRE Acq, ASimple, PropRise | UnitMix model exists | Medium |
| Trailing-12 historical data | ASimple | No | Low-Medium |

---

## Gaps We Should Close (ordered by impact)

### HIGH Priority (affects investor credibility)

1. **Loss-to-lease tracking** — 3 of 5 models track the spread between in-place rents and market rents. Fundamental to value-add underwriting. We have UnitMix but don't compute or expose LTL.

2. **Sensitivity matrix on export** — PropRise's 5x5 (exit cap x rent growth) is table stakes for investor decks. Our engine can compute this; just need it on the export.

3. **Debt yield metric** — `NOI / outstanding_loan_balance`. Simple formula, commonly requested by lenders. We have all inputs; just need to compute and expose it.

### MEDIUM Priority (improves model sophistication)

4. **S-curve lease-up option** — A.CRE Dev has configurable steepness. Linear is conservative but unrealistic for large projects. Add as option alongside linear.

5. **Releasing / turnover costs** — Separate from maintenance CapEx. A.CRE Acq tracks by unit type. Could be a new expense category or CapEx sub-type.

6. **Unit-level rent roll on export** — All institutional models have this. We have UnitMix; should export it prominently.

7. **Capture rate as alternative to continuous absorption** — PropRise uses discrete steps (0%/50%/100%). Simpler to understand, may be preferred.

### LOW Priority (nice-to-have)

8. **Trailing-12 historical data** — Valuable for acquisition due diligence but requires data source we don't have.
9. **Multiple purchase price methods** — PV, cap rate, replacement cost.
10. **Terminal cap rate drift** — Exit cap increases annually by X bps.

---

## Expense Category Consensus

| Category | HD | A.CRE Acq | A.CRE Dev | PropRise | ASimple | Consensus |
|---|---|---|---|---|---|---|
| Real Estate Taxes | Y | Y | Y | Y | Y | **Universal** |
| Property Insurance | Y | Y | Y | Y | Y | **Universal** |
| Utilities | Y | - | Y | Y | Y | **Strong** |
| Repair & Maintenance | Y | Y | Y | Y | - | **Strong** |
| Management Fee (% EGI) | Y | Y | Y | Y | - | **Strong** |
| Payroll / On-Site Staff | Y | Y | Y | Y | - | **Strong** |
| Marketing / Leasing | Y | Y | Y | - | - | Moderate |
| G&A / Admin | Y | Y | Y | - | - | Moderate |
| Contract Services | - | - | Y | Y | - | Moderate |
| Turnover / Make-Ready | - | Y | Y | Y | - | **Moderate** |
| CapEx Reserve | - | Y (3 types) | Y | Y | - | **Strong** |

**Our OperatingExpenseLine model supports all of these.** This is a template/seed issue, not a schema gap. Default expense categories seeded by the deal setup wizard should match this consensus list.

## Income Category Consensus

Our `IncomeStreamType` enum (residential_rent, commercial_rent, parking, laundry, utility_water/electric/gas/internet, storage, pet_fee, deposit_forfeit, other) is **more comprehensive than any single model** in this collection. Good coverage — no schema gaps.

---

## Schema Changes to Consider

| Change | Where | Rationale |
|---|---|---|
| `debt_yield` metric | OperationalOutputs | NOI / loan balance. Lenders want it. Easy add. |
| `loss_to_lease_pct` | UnitMix or IncomeStream | Market vs in-place spread. Fundamental to value-add. |
| `lease_up_curve` option | OperationalInputs | "linear" or "s_curve" with steepness param. |
| Sensitivity matrix storage | New table or JSON on OperationalOutputs | Structured 5x5 grids for export. |

---

## Conclusion

**Our engine is already more sophisticated than any single model in this collection.** The gaps are:
1. **Presentation gaps** — data we can compute but don't surface (LTL, sensitivity, debt yield)
2. **Template gaps** — our schema supports them but we don't seed defaults (expense categories)
3. **One modeling gap** — S-curve lease-up (worth adding as option)

### Immediate Next Actions (before building Excel export)
1. Add `debt_yield` to OperationalOutputs computation
2. Add `loss_to_lease` concept to UnitMix/IncomeStream
3. Include sensitivity matrix in export design
4. Seed default expense categories matching consensus list
5. Consider S-curve lease-up as option alongside linear
