# 01 — Deal Evaluation Mental Models

## Why This Matters for Viciniti

Viciniti Deals already does the hard math: monthly cashflow with four carry types, self-referential draw sizing, multi-tier waterfalls, DSCR-capped auto-sizing. But a tool that only computes numbers forces the operator to supply the *judgment* — the mental scaffolding that tells them whether a 7.0% IRR is a green light or a red flag, whether an 86% OER is a local quirk or an existential problem, whether a deal is "stabilized" or just "not broken." Practitioners don't evaluate deals by running the model top-to-bottom. They run a short, opinionated sequence of sanity checks against benchmarks they carry in their heads, and they stop the moment a number fails a check.

This document captures that sequence — the *thinking framework* beneath the formulas. If Viciniti surfaces the right benchmarks, archetype expectations, and diagnostic ratios in the right order, it can compress a seasoned underwriter's judgment into the UI itself. That's the difference between a model that returns an IRR and a tool that tells an operator whether to keep going, renegotiate, or walk.

---

## 1. The Core Mental Stack: Risk-Free → Cap Rate → IRR → Spread

Practitioners evaluate every deal against a layered benchmark stack, each layer adding a specific risk premium (see `52_from_risk_free_to_irr.md`):

- **Risk-free rate** (10Y UST) — the absolute floor. If you can't beat T-bills meaningfully, stop.
- **Cap rate** — stabilized, unlevered, untrended yield. The spread *over* the risk-free rate is the compensation for illiquidity and real-estate operational risk. Historically this premium runs ~150 bps for core, stable assets.
- **IRR / Discount rate** — total expected return including growth, appreciation, and exit. The spread *over* the cap rate is compensation for cash-flow variability and execution risk (~200 bps for core-plus).
- **Lender spread** — mortgage rate minus risk-free; signals how lenders currently price the same risk. If your IRR spread over risk-free is narrower than the lender's spread, you're taking equity risk for debt returns.

The mental model: every deal is a *stack of spreads*. When an underwriter looks at a pro forma, they are subconsciously asking "is each layer of spread big enough for the risk at that layer?" A 7.0% unlevered IRR on a Chicago industrial warehouse is defensible as core-plus; the same 7.0% on a ground-up development is not.

## 2. IRR Is an Output; the Discount Rate Is an Input

The single most mis-stated concept in CRE underwriting is the relationship between IRR and the discount rate (see `66_irr_vs_discount_rate.md`). They are not interchangeable:

- **Discount rate** = what you *require*. It comes from the investor's cost of capital plus a risk adjustment based on the deal archetype. It is an assumption brought to the deal.
- **IRR** = what the deal *produces*. It is calculated from the cash flows and the price you pay.

The purchase price is the mechanism that aligns them. Set price = PV of cash flows discounted at your required return, and IRR will equal the discount rate exactly. Pay less and IRR > discount rate (value creation, positive NPV). Pay more and IRR < discount rate (value destruction, negative NPV). This reframes the deal question from "what's the IRR?" to "at what price does this asset meet our hurdle, and how far is the ask from that price?"

## 3. Deal Archetypes Map Cleanly to Spreads and Structure

Archetype is not a label, it's a coupled set of expectations for **return, risk, and capital structure**:

| Archetype | Unlevered IRR Band | Risk Character | Typical Capital Stack |
|---|---|---|---|
| Core | ~cap rate to cap + 100bps | Stabilized, leased, low execution | Senior debt + single LP tranche |
| Core-plus | Cap + 150–250 bps | Modest lease-up or light capex | Senior debt + LP + possible mezz |
| Value-add | Cap + 300–500 bps | Reposition, re-tenant, renovate | Senior + LP + GP with promote |
| Opportunistic / Development | Cap + 500+ bps | Entitlement, ground-up, recapitalization | Pursuit equity → dev equity → takeout |

The GreenShield warehouse at 7.0% unlevered (see `52_from_risk_free_to_irr.md`) is explicitly described as "core-plus" — this is how practitioners back-solve risk classification from the return spread. Keystone Ridge at 10.0% required return (see `66_irr_vs_discount_rate.md`) is flagged as value-add because of the 80% occupancy and planned renovations.

Opportunistic / development deals carry a distinct structural tell: they require **pursuit capital**, and the capital comes in *phases* not rounds (see `55_modeling_pursuit_capital.md`). Best practice is three clean raises — pre-entitlement, development, stabilization/sale — with logic-based triggers between them. Raising outside those phases is a red flag to institutional investors.

## 4. Stabilization Is Four Pillars, Not an Occupancy Number

"Stabilized" is the most load-bearing word in a pro forma and the most abused. A property is stabilized only when **all four** hold (see `56_stabilization_through_operating_expense_ratio.md`):

1. **Sustained occupancy** signaling durable market demand (not concession-inflated)
2. **OER benchmarked to market** — operational efficiency relative to comps
3. **NOI sufficient to fund debt service AND capex reinvestment** with a buffer (DSCR)
4. **Positive distributable cash flow after debt** — the levered reality

An asset that is "leased and functioning" but fails pillar 2 or 3 occupies the gray zone between core and value-add. The OER is the diagnostic — a property with 35% market OER and 85% actual OER is not stabilized no matter what the rent roll shows. Sierra Ridge (85.3% OER → 51.9% after repositioning) is the canonical case of a deal marketed as stabilized when it was actually value-add.

## 5. The Practitioner's Question Sequence

Across these articles, a consistent diagnostic sequence emerges:

1. **What's the cap rate, and what's the spread over the 10Y UST?** (Is the deal even in the right neighborhood?)
2. **What archetype is this — and does the return target match?** (Core returns for core-plus risk = mispriced.)
3. **Is the "stabilized" NOI actually stabilized?** (Check OER against market comps; check the four pillars.)
4. **At what price does this meet my hurdle?** (Back-solve from discount rate, don't forward-solve from asking price.)
5. **Does the capital structure match the risk phase?** (Pursuit / dev / stabilization raises aligned with milestones.)
6. **Have I been on site?** (Models hide what eyes catch — see `71_the-real-estate-site-visit-checklist.md`.)

## 6. Red Flags and Deal Killers

Extracted across all six articles:

- **OER materially above market norm** even at full occupancy (operational problem masquerading as a stabilized deal)
- **Razor-thin NOI margin** that cannot absorb capex or debt stress
- **IRR barely above discount rate** — no room for execution slippage
- **Required return doesn't match archetype** (e.g. 6% IRR on a development deal)
- **Capital raised outside the three clean phases** — confuses waterfall, spooks institutional LPs
- **Site-visit red flags**: ingress/egress problems invisible on satellite, loitering/safety issues, "hair" that kills placemaking (A.CRE's Chick-fil-A power-center anecdote)
- **Circular references / iterative calcs in the model itself** — hidden instability that erodes confidence in every output (see `68_best-practices-in-real-estate-financial-modeling.md`)
- **Falling in love with the deal before the site visit** — confirmation bias is the meta-killer

## 7. Model Hygiene Signals Judgment Quality

The A.CRE best-practices conventions (see `68_best-practices-in-real-estate-financial-modeling.md`) — blue=input, black=calc, orange=optional-input-needing-review, red=overridden-formula — are not cosmetic. They encode a mental model: **the analyst owns every blue cell.** A deal review is really a walk through the blue cells, asking "why this number?" A tool that cannot clearly distinguish "assumption you own" from "derived output" forces the reviewer to do that separation mentally on every screen.

---

## Viciniti Implications

- **Surface the spread stack, not just the IRR.** On every scenario screen, show: risk-free rate (current 10Y UST), cap rate, spread-over-risk-free, IRR, spread-over-cap. Let the operator see instantly whether the stack makes sense for the archetype.
- **Make archetype a first-class field on `Scenario`** with expected IRR bands baked in. Flag when the modeled IRR sits outside the band for the selected archetype ("modeled 6.2% IRR for value-add; expected 10–14%"). This turns archetype from a label into a guardrail.
- **Add a "Stabilization Quality" panel** driven by the four-pillar test: occupancy vs. market, OER vs. comp OER, DSCR, and post-debt cash flow margin. Each pillar green/yellow/red. This is more useful than a single "stabilized Y/N" flag.
- **Reframe the price-setting workflow** around the discount-rate-first pattern: let the operator enter a required return and back-solve the maximum purchase price, then show the delta between that and the ask. This mirrors how institutional shops actually decide.
- **Phase capital raises, not just sources.** Tie `CapitalModule` activation to milestone triggers (pre-entitlement / development / stabilization). Warn when a source comes online outside a recognized phase — the same "red flag" institutional LPs raise.
- **Build a site-visit checklist artifact per deal** — a structured list the operator completes during the visit, stored on the deal, surfacing any unchecked items in the underwriting summary. The gut-check belongs inside the tool, not in a separate notebook.
