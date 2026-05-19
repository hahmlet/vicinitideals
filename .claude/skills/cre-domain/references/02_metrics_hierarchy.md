# 02 — Metrics Hierarchy: What CRE Practitioners Measure and When It Matters

## Why the Hierarchy Matters for Viciniti

Real estate underwriting is not a single-number exercise. A deal is evaluated through a stack of interrelated metrics where each layer answers a different question: *Is the price fair? Is the income durable? Does the debt clear? Will the equity earn its target?* Practitioners move up this stack as a deal progresses — a broker's flyer gets a cap-rate sanity check, a letter-of-intent triggers DSCR and yield-on-cost math, a committee memo demands IRR and NPV sensitivity. Confusing the layers (e.g., comparing an unlevered IRR to a levered cash-on-cash, or treating a cap rate as a return) is the single most common source of bad decisions in CRE.

For Viciniti, the hierarchy is the product. Every screen, export, and sensitivity table maps to one of these metrics, and the app's value proposition is that it correctly distinguishes what the *user asserts* (discount rate, exit cap, hold period) from what the *engine derives* (IRR, NPV, DSCR, effective interest rate). Getting the input/output boundary right — and showing the spreads between metrics at each stage — is what turns a spreadsheet replacement into a decision tool.

---

## 1. Return Metrics (Output — calculated from cash flows)

| Metric | Definition | When It Matters |
|---|---|---|
| **Cap Rate** | Stabilized NOI / Purchase Price | Screening, valuation, exit assumption |
| **IRR (Unlevered)** | Discount rate that sets NPV of property-level cash flows to zero | Comparing deals on asset merits, before capital structure |
| **IRR (Levered)** | IRR on equity cash flows after debt service | Final committee metric, LP return |
| **NPV** | Σ CFt / (1+r)^t − initial investment | Accept/reject test when a target discount rate is fixed |
| **Equity Multiple** | Total distributions / total equity invested | Absolute-dollar return; blind to timing |
| **Weighted Equity Multiple** | Equity multiple adjusted for the timing of inflows/outflows | Corrects the "magnitude-only" blindspot (see `67_deep-dive-understanding-the-time-value-of-money-in-commercial-real-estate.md`) |
| **Cash-on-Cash (CoC)** | Annual pre-tax levered cash flow / equity invested | In-place year-over-year return; not a full-life metric |
| **Yield-on-Cost (YoC)** | Stabilized NOI / Total Project Cost | Development/value-add; compare to market cap rate to see "development spread" |

**IRR ↔ Discount Rate relationship.** These are two sides of the same coin (see `66_irr_vs_discount_rate.md`). The discount rate is an *input* the investor brings — their required return given risk and opportunity cost. The IRR is the *output* the cash flows produce. If IRR ≥ discount rate, NPV ≥ 0 and the deal clears the hurdle. The discount rate "does not come from the property" (see `67_deep-dive-understanding-the-time-value-of-money-in-commercial-real-estate.md`) — it is the price of capital the investor asserts.

---

## 2. Valuation Metrics

**Direct Cap vs DCF** — two lenses on the same income stream (see `67_deep-dive-understanding-the-time-value-of-money-in-commercial-real-estate.md`).

- **Direct Cap**: `Value = Stabilized NOI / Cap Rate`. A market-anchored snapshot. Fast, but hinges on two judgment calls: what counts as "stabilized" NOI, and what cap rate the market pays for comparable streams.
- **DCF**: explicit, period-by-period discounting. Makes timing, lease-up, CapEx, and reversion visible. Required for value-add, development, and any non-stabilized pattern.

Practitioners triangulate with both. Direct cap gives the "what would it trade for today"; DCF gives the "what is it worth to *this* investor with *this* strategy."

---

## 3. Risk Metrics and Spreads

Spreads are where the real story lives — they quantify why one rate is higher than another.

| Spread | Formula | What It Measures |
|---|---|---|
| **Cap Rate − Risk-Free Rate** | e.g., 5.0% − 3.5% = 150 bps | Illiquidity + operational risk premium for holding real estate vs Treasuries |
| **IRR − Cap Rate** | e.g., 7.0% − 5.0% = 200 bps | Expected income growth + appreciation + exit proceeds |
| **IRR − Risk-Free Rate** | e.g., 7.0% − 3.5% = 350 bps | Total real estate risk premium |
| **Mortgage Rate − Risk-Free Rate** | e.g., 5.5% − 3.5% = 200 bps | Lender's credit spread |
| **YoC − Market Cap Rate** | e.g., 7.0% − 5.5% = 150 bps | Development/value-add "created spread" |

A.CRE's framing: the discount rate is built from blocks — `base rate + inflation premium + country risk + liquidity + operational risk + execution risk` (see `67_deep-dive-understanding-the-time-value-of-money-in-commercial-real-estate.md`). Each spread in the table above exposes one of those blocks to scrutiny.

**Operating Expense Ratio (OER)** — `OpEx / Effective Gross Revenue`. A diagnostic, not a return. Typical range 20–50% depending on property type and market. An OER that deviates from market norms signals either operational dysfunction or that the property is not truly stabilized (see `56_stabilization_through_operating_expense_ratio.md`). OER is the litmus test for the "stabilized NOI" input that feeds everything else in the stack.

---

## 4. Debt Metrics (Output — derived from cash flow and loan terms)

| Metric | Definition | When It Matters |
|---|---|---|
| **DSCR** | NOI / Annual Debt Service | Sizing, lender covenants, stabilization test |
| **LTV** | Loan Amount / Appraised Value | Acquisition sizing, refi test |
| **LTC** | Loan Amount / Total Cost | Construction loan sizing |
| **Debt Yield** | NOI / Loan Amount | Lender's "how quickly do I get my money back if I foreclose" |
| **Effective Interest Rate** | Actual dollar interest / principal over period | True cost — *differs from stated rate* depending on day-count method |

### Day-Count Conventions (from `57_interest_calculation_methods_cre_loans.md`)

Three methods, same stated rate, different actual cost:

| Method | Daily Rate Basis | Monthly Interest | Effective Rate on 4% loan |
|---|---|---|---|
| **30/360** | rate / 360, × 30 days | annual rate / 12 | 4.000% (true) |
| **Actual/365** | rate / 365, × actual days | varies by month | ~4.003% |
| **Actual/360** | rate / 360, × actual days | larger, varies | ~4.058% |

For a stated 4.0% loan, Actual/360 produces ~5.8 bps more annual cost than 30/360 — legal, fully disclosed, but material. **Always defer to loan documentation.** This is an often-missed detail that affects DSCR, carry, and IRR alike.

---

## 5. Input vs Output: What the User Asserts vs What Viciniti Calculates

This distinction is the backbone of the product. Blue-font cells in A.CRE Excel templates (see `68_best-practices-in-real-estate-financial-modeling.md`) are *inputs the user owns*; black-font cells are *calculations*. Viciniti's UI must enforce the same boundary.

| **INPUTS** (user sets) | **OUTPUTS** (engine calculates) |
|---|---|
| Purchase Price | Cap Rate at purchase |
| Rent assumptions + growth | Effective Gross Revenue |
| OpEx line items | NOI, OER |
| Vacancy / lease-up schedule | Stabilized NOI |
| Loan amount, rate, term, amortization, day-count, carry type | Debt Service, Effective Rate, DSCR, LTV, Debt Yield |
| Discount Rate (target IRR / hurdle) | NPV, whether IRR clears hurdle |
| Exit Cap Rate | Reversion Value |
| Hold Period | Timing of cash flows |
| Equity waterfall tiers | LP/GP IRR, CoC, Equity Multiple |
| Risk-Free Rate (benchmark) | Spreads (Cap − RFR, IRR − Cap, etc.) |

**Key principle from `67_deep-dive...md`:** "In practice, many models do not 'solve' the price with a discount rate; instead, the purchase price is assumed, the model calculates the resulting IRR, and the analyst reviews inputs until the target IRR is reached." Viciniti must support both directions — price-in / IRR-out (default) and target-IRR / max-price-out (solver mode).

---

## 6. Metrics by Deal Stage

| Stage | Primary Metrics | Purpose |
|---|---|---|
| **Screening** (flyer, 15 min) | Cap Rate, price/SF, YoC, OER sanity | Kill-or-advance decision |
| **LOI / Underwriting** | DSCR, LTV, Debt Yield, unlevered IRR, NPV | Sizing debt, proving the deal clears |
| **Committee** | Levered IRR, Equity Multiple, CoC year 1-stabilized, sensitivity tables | Approval narrative |
| **Closing / Execution** | Sources = Uses, draw schedule, carry type | Funding mechanics |
| **Asset Management** | Actual vs proforma NOI, OER drift, DSCR covenants, refi triggers | Operational health |
| **Exit / Refi** | Exit Cap, reversion, realized IRR vs proforma | Performance measurement |

A metric that dominates one stage is often noise at another. Cash-on-cash is useless at screening (no debt yet) but central in asset management. IRR is table stakes at committee but misleading at screening (assumptions dominate the output).

---

## 7. Viciniti Implications

- **Font-color discipline in the UI.** Adopt the A.CRE blue/black/green/orange convention visually — user-asserted inputs must look different from engine outputs. Today's UI blurs this line in places (e.g., auto-sized debt modules); users need to see at a glance which numbers they own.
- **Expose spreads as first-class outputs.** Alongside cap rate and IRR, surface Cap − Risk-Free, IRR − Cap, and YoC − Market Cap. These spreads are the actual decision drivers; showing only absolute rates hides the risk premium narrative.
- **Day-count selector matters.** Carry calculations already support `io_only`, `interest_reserve`, `capitalized_interest`, `pi` — but effective rate should be displayed alongside stated rate, and the day-count convention (30/360 vs Actual/360) should be an explicit loan input with the computed effective rate shown next to it.
- **Stabilization indicator, not just occupancy.** Add an OER-vs-market-norm diagnostic to the Scenario dashboard. A deal that pencils on underwriting but has an OER 15 points above market comps should throw a visible warning — it's a Sierra Ridge (see `56_stabilization_through_operating_expense_ratio.md`) until proven otherwise.
- **Stage-aware views.** The same scenario viewed at "screening" vs "committee" should foreground different metrics. Today Viciniti shows everything; a mode switch (or a collapsible default layout per stage) would reduce noise and match how practitioners actually work up a deal.
