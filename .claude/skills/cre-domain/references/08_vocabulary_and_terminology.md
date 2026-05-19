# 08 — Vocabulary and Terminology: Aligning Viciniti Labels with Industry Convention

Commercial real estate is a high-context discipline where the same concept is called three different things by a lender, an appraiser, and a GP — and where picking the wrong label on a UI field can silently mislead a user into modeling the deal with the wrong mental model. Viciniti is a server-rendered underwriting tool used by practitioners who also read broker OMs, lender term sheets, and LP memoranda; every field name, dropdown value, and metric label should match what those documents say. This document catalogs the canonical terms (and their synonyms) that show up in the underwriting workflow, flags where conventions diverge, and ends with concrete naming implications for the Viciniti schema and templates.

---

## 1. Return & Valuation Metrics

**Cap Rate (Capitalization Rate).** Stabilized NOI divided by property value. A snapshot of untrended, unlevered yield at a point in time. Synonyms: "going-in cap rate" (entry), "exit cap" / "terminal cap" / "reversion cap" (exit), "market cap rate" (comp-derived). Corpus 52 is explicit: `Property Value = Stabilized NOI / Cap Rate`. Usage note: a "5 cap" and a "5.0% cap rate" are the same thing spoken vs. written.

**NOI (Net Operating Income).** EGI minus operating expenses, before debt service, CapEx, leasing commissions, and tenant improvements. Always unlevered. Use "stabilized NOI" when the property is at steady-state occupancy and market rents; use "in-place NOI" for the current trailing figure.

**EGI (Effective Gross Income).** Gross potential rent minus vacancy and credit loss, plus other income (parking, reimbursements, laundry). Synonym: "effective gross revenue" (EGR) — corpus 56 uses EGR interchangeably.

**OER (Operating Expense Ratio).** `OER = Operating Expenses / EGI`. A diagnostic ratio; corpus 56 positions it as the real test of stabilization beyond occupancy.

**IRR (Internal Rate of Return).** The discount rate that sets NPV to zero on a cash-flow stream. Always an output, never an input (corpus 66). Distinguish unlevered IRR (project-level) from levered IRR (equity-level). For GP/LP contexts: deal IRR, LP IRR, GP IRR are all different views.

**Discount Rate.** An input: the required return used in DCF. Synonyms: "hurdle rate", "required rate of return", "opportunity cost of capital", "target IRR". Corpus 66 and 67 both emphasize: investor sets it, property cash flows produce IRR; they align only at the "right" price.

**NPV (Net Present Value).** PV of future cash flows minus initial outlay, using the discount rate. `NPV > 0` = value creation; `NPV = 0` = breakeven; `NPV < 0` = value destruction.

**Yield-on-Cost (YoC).** Stabilized NOI divided by total project cost (Uses). Also: "development yield", "untrended return on cost". The spread between YoC and market cap rate is "development spread" or "developer's profit margin" — a core development-deal metric.

**Equity Multiple (EM / MOIC).** Total distributions divided by total contributions. Time-agnostic — hence corpus 67 pairs it with "weighted equity multiple" to respect TVM.

**Cash-on-Cash (CoC).** Annual levered cash flow divided by equity invested. A single-year levered yield, distinct from IRR.

**Risk Premium / Spread.** Basis-point difference between a return metric and a benchmark. Corpus 52 catalogs three: `cap rate − risk-free`, `IRR − cap rate`, `mortgage rate − risk-free`. Quoted in bps ("one-fifty over the ten-year" = 150bps over the 10Y UST).

---

## 2. Debt & Capital Stack

**Senior Debt.** First-lien mortgage, lowest cost, lowest LTV tolerance alone but highest in priority. Synonyms depend on source: "senior loan", "first mortgage", "perm loan" (post-stabilization), "construction loan" (during build).

**Mezzanine Debt ("Mezz").** Subordinate debt secured by equity pledge rather than property lien. Sits above common equity, below senior.

**Preferred Equity ("Pref Equity", "Pref").** Equity with a fixed coupon and priority over common. Distinct from the **preferred return** (see below) — same word, different meaning.

**Common Equity.** Residual equity; takes losses first, gets upside last (after waterfall).

**GP / Sponsor / General Partner.** The operator who sources, underwrites, executes. "Sponsor" and "GP" are used interchangeably in most LP memoranda (corpus 54). In JV structures, Viciniti may see "Co-GP" — the early-risk GP layer that funds pursuit capital (corpus 55).

**LP / Limited Partner.** Passive capital — institutional (insurance, pension, endowment, sovereign, family office) or HNW. Typically contributes 80–95% of equity.

**Pursuit Capital.** Pre-development "first dollars in" — zoning, design, legal, earnest money. Corpus 55 explicitly names the Co-GP layer as the usual source. Synonyms: "seed capital", "pre-development equity", "at-risk capital".

**CMBS.** Commercial Mortgage-Backed Securities — securitized senior debt. One of the funder archetypes in corpus 54.

**Agency Debt.** Fannie Mae / Freddie Mac / HUD loans — almost exclusively multifamily. Distinct funder category from CMBS, bank, life-co, bridge, private.

**Life-Co Debt.** Life insurance company senior lending — long-term, low-LTV, stabilized assets.

**LTV / LTC.** Loan-to-Value (debt / as-is or as-stabilized value) vs. Loan-to-Cost (debt / total project cost). LTV for acquisitions; LTC for construction/development. Both are sizing constraints.

**DSCR (Debt Service Coverage Ratio).** `NOI / Debt Service`. Lender sizing constraint and a stabilization pillar (corpus 56).

**Debt Yield.** `NOI / Loan Amount`. A cap-rate-free lender metric used to prevent over-sizing during low-cap-rate markets.

---

## 3. Carry, Promote, and Waterfall

**Preferred Return ("Pref").** A minimum return to LPs before any promote splits kick in. Typically 7–10% IRR or compounded accrued return. Not the same as "preferred equity".

**Promote / Carried Interest / Carry.** The GP's disproportionate share of profits above the pref. All three terms mean the same thing; "promote" dominates real-estate usage, "carry" dominates PE usage. Corpus 55 uses "promote" exclusively.

**Waterfall.** The rule set for distributing cash between LP and GP across return tiers. "European waterfall" = deal-level catch-up; "American waterfall" = distribute-as-you-go.

**Catch-up.** The tier that hands the GP its full promote share after the pref has been paid, often 50/50 or 100/0 until GP is "caught up" to its promised split.

**Carry Type (loan interest treatment).** Viciniti-specific term for how a loan's pre-operating interest is handled: `io_only` (true interest-only), `interest_reserve` (reserved and drawn against average balance), `capitalized_interest` / PIK (added to principal), `pi` (amortizing P&I). Industry synonyms: "IO", "interest reserve", "capitalized interest" or "PIK interest", "amortizing".

**Double Promote.** Nested waterfalls where a Co-GP layer splits promote separately from the LP waterfall (corpus 55).

**Imputed Equity.** Value created pre-closing (e.g., entitlement lift) credited as GP equity contribution (corpus 55). Also called "value-creation credit" or "promote credit".

---

## 4. Deal Archetypes / Risk Profiles

| Archetype | Description | Return Expectation |
|---|---|---|
| **Core** | Stabilized, institutional-quality, long-lease, low-leverage | Low IRR, steady pref |
| **Core-Plus** | Mostly stabilized with light upside (minor lease-up, modest capex) | Moderate IRR |
| **Value-Add** | Operational or physical upside — reposition, renovate, re-tenant | Mid-to-high IRR |
| **Opportunistic** | Ground-up, distressed, entitlement plays — highest risk | Highest IRR, binary outcomes |

Corpus 67 explicitly ties these archetypes to discount-rate adjustments. "Build-to-Rent (BTR)" and "ground-up development" are opportunistic sub-categories. "Lease-up" is a phase, not an archetype — it can appear inside value-add or opportunistic.

---

## 5. Property Types & Subtypes

Five majors (corpus 54): **Multifamily, Retail, Office, Industrial, Hotel**. Plus emerging: Mixed-use, Data Center, Self-Storage, Senior Housing, Medical Office (MOB), Life Sciences, Student Housing, Sustainable/Green.

- **Multifamily subtypes**: Garden, Mid-rise, High-rise, BTR (Build-to-Rent), Affordable/LIHTC, Market-rate, Senior, Student.
- **Retail subtypes**: Freestanding/NNN, Strip, Neighborhood Center, Community Center, Power Center, Regional Mall, Lifestyle Center.
- **Industrial subtypes**: Bulk Distribution, Last-Mile, Flex, Manufacturing, Cold Storage, IOS (Industrial Outdoor Storage).
- **Office subtypes**: CBD, Suburban, Medical, Creative/Loft, Life Sciences.
- **Hotel subtypes**: Limited-Service, Select-Service, Full-Service, Extended-Stay, Resort.

---

## 6. Deal Stage / Lifecycle Vocabulary

**LOI (Letter of Intent).** Non-binding term sheet exchanged before PSA.
**PSA (Purchase and Sale Agreement).** Binding contract; triggers due-diligence and earnest-money clock.
**DD (Due Diligence).** Physical inspection, title, survey, environmental (Phase I / Phase II), financial review, zoning confirmation.
**Hard / Go-Hard.** When earnest money becomes non-refundable.
**Closing / COE (Close of Escrow).** Funding, deed transfer, loan closing.
**Lease-Up / Absorption.** Period between delivery and stabilization.
**Stabilization.** Beyond occupancy — sustained occupancy, market OER, DSCR buffer, distributable levered cash flow (corpus 56's four pillars).
**Refi / Recap.** Refinance the senior loan (or restructure the equity stack) — often the point at which promote crystallizes.
**Disposition / Exit / Reversion.** Sale of the asset. "Reversion" is the DCF term for terminal-year sale proceeds.
**RTI (Ready-to-Issue).** Permits in hand; the moment institutional LPs typically enter (corpus 55).

---

## 7. Interest & Day-Count Conventions

From corpus 57: **30/360**, **Actual/365** (aka 365/365), **Actual/360** (aka 365/360). Identical nominal rates produce different effective rates depending on day-count. Viciniti should label these exactly as lenders do — no invented synonyms.

---

## Viciniti Implications

1. **`funder_type` is a Viciniti-internal label; the UI should surface industry-standard values.** The enum should read: `senior_debt`, `mezzanine`, `preferred_equity`, `common_equity`, `bridge`, `cmbs`, `agency`, `life_co`, `bank`, `private_debt` — not generic buckets like "debt" / "equity". Pursuit-capital deals also need a `co_gp_equity` option to match corpus 55's structure.

2. **Disambiguate "preferred return" vs. "preferred equity" in the capital module UI.** These are different things and "pref" alone is ambiguous. Suggest: `preferred_return_pct` on the carry schema, `preferred_equity` as a `funder_type` value.

3. **Standardize `carry_type` labels to industry terms.** Current values (`io_only`, `interest_reserve`, `capitalized_interest`, `pi`) are good but UI labels should read "Interest-Only", "Interest Reserve", "Capitalized Interest (PIK)", "Amortizing (P&I)" — not the raw enum.

4. **Expose "Yield-on-Cost" and "Development Spread" as first-class metrics alongside cap rate and IRR** for development deals. Today Viciniti underwrites them but doesn't label them prominently; practitioners expect these callouts on development pro formas.

5. **Pick one exit-cap label and use it consistently.** Industry uses "exit cap", "terminal cap", and "reversion cap" interchangeably — Viciniti should pick one (recommend **"Exit Cap Rate"** for plain-English UI, keep `terminal_cap_rate` as the schema field for DCF-adjacent audiences).

6. **Property-type taxonomy needs subtypes.** Current parcel/listing schema likely stores high-level type only; industry-grade underwriting distinguishes MOB vs. suburban office, last-mile vs. bulk industrial, BTR vs. garden multifamily. These drive cap-rate comps and market-rent assumptions materially.
