# 03 — Modeling Conventions & Best Practices

## Why These Conventions Matter for Viciniti

CRE financial modeling is a professional discipline with deeply entrenched conventions — not because spreadsheets demand them, but because deals change hands across sponsors, lenders, LPs, and appraisers who all need to audit the math at 2am without calling the analyst. When a capital partner opens a model, they are scanning for *tells* within the first thirty seconds: Does blue font mean input? Is the debt day-count declared? Are pursuit dollars split from development equity? Is there a circular reference lurking in the closing-cost fold-in? Models that follow convention get funded. Models that don't get re-underwritten by the LP's analyst from scratch, which usually means the deal dies.

For Viciniti — a self-hosted, web-based replacement for the Excel underwriting workflow — adherence to these conventions is load-bearing. Users coming off A.CRE templates, Rob Beardsley books, or any mid-market PE shop will evaluate Viciniti against the Excel muscle-memory they already have. The product wins not by *replacing* conventions but by *encoding* them: input/output separation enforced by the data model, day-count methods declared per loan, pursuit capital as a first-class tranche, waterfalls that cascade the way LPs expect. This document captures those conventions so the engine, schemas, and UI can reflect them faithfully.

---

## Model Structure Conventions

Every credible CRE model — whether a one-off acquisition pro forma or the A.CRE All-in-One — is built on four structural rules (see `68_best-practices-in-real-estate-financial-modeling.md`):

**1. Inputs and outputs are visually and logically separate.** The industry-standard color convention is strict:

- **Blue font** = required input. The user "owns" this cell and must justify the value.
- **Black font** = calculation or output. Never edit unless you mean to.
- **Green font** = cross-sheet link back to an original calculation.
- **Red font** = an intentional override of a black/green cell (a flag to future readers).
- **Orange font** = optional input (A.CRE convention, 2015+). The formula is *usually* right but deserves a look.

This color grammar is how a reviewer instantly distinguishes assumptions from math. Any model that mixes hard-coded values into formula cells without flagging them is treated as suspect.

**2. Version tab / audit trail.** Professional templates lead with a Version tab documenting every change since first release, compatibility notes, and links to documentation. Reviewers check it first.

**3. Templates are sacrosanct.** Never start a new deal by copying last deal's file — too many site-specific tweaks bleed forward. Always start from the clean template, and replace hypothetical inputs deliberately (see `68_best-practices-in-real-estate-financial-modeling.md`).

**4. No circular references.** A.CRE explicitly rejects Excel's "enable iterative calculation" workaround because it causes model instability, approximation error, and obscured audit trails. Closing-cost fold-ins, capitalized interest, and DSCR-capped sizing are all places circulars *want* to appear — the professional answer is algebraic fold-in or macro resolution, not iterative calc.

Secondary hygiene rules: never use plain CTRL-C / CTRL-V (it carries formatting and creates cross-workbook links that trigger "Update Links" warnings); use Paste-Values for inputs and Paste-Formulas for calculations (`68_best-practices-in-real-estate-financial-modeling.md`).

---

## Capital Stack Conventions

CRE capital stacks are layered by *risk timing*, not just seniority. The canonical order from riskiest to safest is:

1. **Pursuit capital** (pre-entitlement) — the "first check in, first at risk." Funds zoning studies, site plans, legal, due diligence, earnest money. Written by the Co-GP or a small high-trust syndicate before the deal is even a deal (see `55_modeling_pursuit_capital.md`).
2. **Development equity** (post-entitlement, often at RTI — Ready-To-Issue permits) — larger, institutional LP money that arrives once core risk is retired.
3. **Senior debt** — construction or perm loan, funded against committed equity.
4. **Mezz / preferred equity** — occasionally layered in for gap financing.

**The pursuit-capital tranche has modeling implications most amateur models miss:**

- It should be a separate equity tranche with its own contribution timing, preferred return, and promote treatment — *not* folded into GP equity from day one.
- Best-practice modelers use either (a) two explicit equity line items (Pursuit Equity + Development Equity) or (b) logic-based triggers on a single equity source that activate contribution at the right milestone (`55_modeling_pursuit_capital.md`).
- Entitlement "lift" (e.g. $1M of pursuit work takes land from $3.25M to $4.1M) can be treated as *imputed equity*, allowing the GP to negotiate a higher promote or reduced LP pref in exchange for value delivered (`55_modeling_pursuit_capital.md`).
- Only three clean capital raises are recommended: Pre-Entitlement, Development, and Stabilization/Sale. Raising between these phases signals disorganization to investors.

---

## Debt Conventions: Day Count Matters

Three day-count methods dominate CRE debt. They produce materially different interest totals on identical-sounding loans (see `57_interest_calculation_methods_cre_loans.md`):

| Method | Daily rate | Days multiplied | Effect |
|---|---|---|---|
| **30/360** | Annual / 360 | 30 per month | Cleanest; true stated rate. Simplest: annual ÷ 12. |
| **Actual/365** (365/365) | Annual / 365 | Actual days in month | Slightly higher than 30/360 due to 31-day months + leap years. |
| **Actual/360** (365/360) | Annual / 360 | Actual days in month | Highest total interest — combines the larger daily rate of 30/360 with the longer day counts of Actual/365. |

On a $1M loan at stated 4% over 4 years, 365/365 produces an effective ~4.003%; 365/360 produces ~4.058%. That ~5.5 bps looks trivial until you apply it to a $50M construction loan over a 36-month draw — the difference is real dollars.

Actual/360 has faced legal challenges from borrowers arguing it was deceptive; lenders have consistently prevailed because the methodology was disclosed in loan docs. The professional convention: **defer to the loan documentation, always — the method is explicit in the term sheet and promissory note** (`57_interest_calculation_methods_cre_loans.md`).

Related debt conventions that show up in every well-built model:
- Interest during construction is calculated on the *average outstanding balance*, typically approximated as `(N+1)/2` of the commitment during an interest-reserve draw period, or on full commitment for capitalized interest / PIK.
- DSCR sizing is *capped*, not solved — when DSCR binds, the gap between Uses and debt sizing is real and must be backfilled with equity.
- Closing costs are algebraically folded into the loan amount, not iteratively solved (avoids circulars).

---

## Time Value of Money Conventions

TVM is the foundation of every CRE valuation: *a dollar today is worth more than a dollar tomorrow*, and the engine that captures this is discounted cash flow (see `67_deep-dive-understanding-the-time-value-of-money-in-commercial-real-estate.md`, `72_learning-real-estate-financial-modeling-in-excel.md`).

**Conventions worth encoding:**

- **Monthly cash flows, not annual.** Development deals have lumpy, phase-specific cash flows (draws, interest accrual, lease-up) that annualizing obliterates. Professional models run on monthly granularity and roll up to annual for display.
- **XIRR over IRR.** `IRR()` assumes evenly-spaced periods; `XIRR()` takes explicit dates. For any deal with irregular closings, staged equity contributions, or non-month-end exits, XIRR is the correct tool. IRR is a shortcut, not a convention.
- **Discount rate `r` is an investor input, not an asset output.** The property generates cash flows; `r` reflects the investor's opportunity cost, risk tolerance, and cost of capital. The "building blocks" framing: `r = base rate + inflation premium + country/liquidity/operational/execution risk premiums` (`67_deep-dive-understanding-the-time-value-of-money-in-commercial-real-estate.md`).
- **Nominal vs real consistency.** If flows include inflation, the discount rate must be nominal. If flows are real, rate must be real. Mixing them is the single most common junior-analyst error.
- **Direct Cap and DCF should triangulate.** Direct cap (NOI / cap rate) gives a market-anchored snapshot; DCF makes timing explicit. Professionals run both and reconcile.
- **Weighted Equity Multiple > raw Equity Multiple.** Two deals with the same 2.0x multiple are not equally attractive if one returns capital in year 3 and the other in year 10. Weighting captures this (`67_deep-dive-understanding-the-time-value-of-money-in-commercial-real-estate.md`).
- **In acquisitions, price is the input and IRR is the output** — not the other way around. The market sets price; the investor decides whether the resulting IRR clears their hurdle.

---

## Waterfall Conventions

Professional-grade waterfalls are tiered and *nested* when there's both a Co-GP and an LP (see `55_modeling_pursuit_capital.md`):

**Single-tier (GP-LP) waterfall** — the simple case:
1. Return of capital (pari passu or LP-first)
2. Preferred return to LP (commonly 7-9%)
3. Catch-up to GP
4. Promote splits (e.g., 80/20, 70/30, 60/40 at escalating IRR hurdles)

**Double promote (Co-GP + GP-LP)** — the professional structure when pursuit capital is involved:
1. **Co-GP waterfall:** Early investors (pursuit capital contributors) receive a preferred return (often 8% on pursuit dollars), then split residual with the sponsor (commonly 50/50).
2. **GP-LP waterfall:** Once the LP funds at RTI, the combined GP entity (sponsor + Co-GP) sits opposite the LP in the standard tiered promote structure.
3. **Cascade:** Promote dollars earned by the GP entity cascade back down into the Co-GP waterfall, where pursuit capital investors capture their share of the sponsor's upside.

This structure is why pursuit capital "earns twice" — once through its Co-GP pref and once through its share of the cascading promote. Models that collapse pursuit into generic GP equity lose this economic signal entirely.

---

## Quality Signals: How to Spot a Professional Model

The following tells separate a model built by a working professional from a model built by someone who watched one YouTube video:

- **Version tab leads.** Change log, compatibility notes, documentation links.
- **Font color grammar is strict and consistent** (blue inputs, black math, green cross-sheet, red override, orange optional).
- **No circular references** — iterative calc is disabled. Closing costs are folded in algebraically.
- **Day-count method is declared per loan**, not assumed.
- **Pursuit capital is a distinct tranche**, not lumped into GP equity.
- **Monthly cashflow engine with annual rollups**, not an annualized pro forma pretending to handle a development deal.
- **XIRR, not IRR**, for anything with irregular timing.
- **Direct cap and DCF both present** and reconciled.
- **Equity waterfall is tiered with explicit preferred return, catch-up, and promote hurdles** — not a single "80/20 after 8%" line item.
- **Inputs have sanity checks / data validation**; hypothetical placeholder values are visibly flagged, not silently left as defaults.
- **Sources = Uses invariant holds to the penny**, even with DSCR caps and closing-cost fold-ins active.

Amateur tells (the inverse): plug numbers in black font, circular refs silently enabled, one equity line for everything, annual-only cashflows, IRR on irregular periods, waterfalls that don't cascade, and the classic "the hypothetical 4.5% interest rate must be right because it came with the template."

---

## Viciniti Implications

- **Viciniti must support all three debt day-count conventions (30/360, Actual/365, Actual/360) as a per-loan declared enum.** Lenders specify the method in term sheets; silently assuming 30/360 will produce dollar-level disagreements with lender amortization schedules on every deal.
- **Pursuit capital deserves first-class modeling as a distinct equity tranche with its own Co-GP waterfall, preferred return, and cascade linkage to the GP-LP promote.** A single generic "equity" source will force users back to Excel the moment they structure a double-promote deal with seed investors.
- **The engine must remain monthly, XIRR-based, and free of circular references.** Our existing `cashflow.py` algebraic fold-in for closing costs and per-loan `_loan_pre_op_months` windowing are correct by convention — these are not implementation details, they are *the professional standard*. Do not "fix" them by enabling iteration.
- **The UI should replicate color-coded input/output separation even though it's a web app, not Excel.** Required inputs, calculated outputs, cross-module links, and optional inputs should be visually distinct so Excel-native users map Viciniti onto their existing muscle memory within minutes.
- **Every deal should present Direct Cap and DCF side-by-side with reconciliation, and every return table should include both raw and weighted equity multiple.** These dual views are the professional-grade quality signal; presenting only one makes Viciniti feel like a retail tool.
