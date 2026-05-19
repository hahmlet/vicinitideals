---
name: cre-domain
description: "Commercial real estate domain expertise for the Viciniti Deals underwriting platform. Use when designing features, naming fields, or making product decisions that depend on how CRE practitioners actually think about deals, metrics, models, workflows, and vocabulary. Covers: deal evaluation mental models, metrics hierarchy (cap rate, IRR, DSCR, OER, yield-on-cost), modeling conventions (day counts, waterfall, pursuit capital), sensitivity and Monte Carlo, data architecture for comps and demographics, AI workflow patterns practitioners expect, UX expectations, and industry vocabulary."
---

# CRE Domain Knowledge for Viciniti Deals

This skill is the **"how CRE people think"** brain for the Viciniti Deals project. It is not a formula reference — the financial math lives in `app/engines/` and `docs/FINANCIAL_MODEL.md`. This skill captures the *judgment, vocabulary, and expectations* that should shape product decisions.

## When to Use This Skill

Use this skill when you are:
- Naming fields, labels, or UI elements (vocabulary matters — practitioners will judge the tool by its terms)
- Deciding which metrics to surface where (cap rate, IRR, DSCR, OER, spreads, yield-on-cost)
- Designing workflows that map to what analysts actually do (deal screening, IC memo, site visit packet, sensitivity analysis)
- Structuring capital stack, waterfall, or debt inputs (day-count conventions, tranches, pursuit capital)
- Choosing between `core`, `core-plus`, `value-add`, `opportunistic` semantics
- Building AI-adjacent features (MCP endpoints, skills, comp database exposure)
- Evaluating whether a feature matches how practitioners approach uncertainty (sensitivity vs scenarios vs Monte Carlo)

**Do not** use this skill for:
- Implementing financial formulas — use `docs/FINANCIAL_MODEL.md` and the `cashflow.py` / `draw_schedule.py` / `underwriting.py` engines
- Infrastructure, deploy, or test strategy — use `CLAUDE.md`

## What This Skill Optimizes For

- **Practitioner alignment**: field names, labels, and defaults that match how CRE analysts talk and think
- **Decision-driving UI**: surface what matters at each deal stage, not a comprehensive data dump
- **Traceable guidance**: every claim references a topical synthesis in `references/`, which cites the underlying corpus in `docs/Best Practices Corpus/`

## Fast Routing by Goal

| If you are working on… | Read first |
|---|---|
| Judging whether a deal is "good" or how practitioners sequence their analysis | `references/01_deal_evaluation_mental_models.md` |
| Deciding which metric to surface, input vs output, spread semantics, debt day counts | `references/02_metrics_hierarchy.md` |
| Capital stack, waterfall, pursuit capital, day-count conventions, model structure | `references/03_modeling_conventions.md` |
| Sensitivity tables, scenario analysis, Monte Carlo, uncertainty UX | `references/04_sensitivity_and_simulation.md` |
| Comp databases, radius demographics, MCP vs API, data as a moat | `references/05_data_architecture_for_cre.md` |
| AI workflows, Multiplier Framework, Musk's 5 principles, skills vs data | `references/06_ai_workflow_patterns.md` |
| IC memos, deliverable-driven workflows, UI conventions, site visits | `references/07_ux_and_workflow_expectations.md` |
| Field names, synonyms, industry terms, deal archetype vocabulary | `references/08_vocabulary_and_terminology.md` |

## Core Mental Models to Keep in Mind

These recurring ideas show up across multiple reference docs. Internalize them before reading any specific doc:

1. **Spreads, not absolute rates, carry the signal.** Cap rate minus risk-free, IRR minus cap rate, mortgage minus treasury — practitioners evaluate deals by the *premium*, not the nominal number.
2. **Discount rate is an input; IRR is an output.** They're equal only when the investor pays exactly the present value. Divergence signals value creation or destruction.
3. **Stabilization is four-dimensional, not just occupancy.** Sustained occupancy + market-benchmark OER + strong NOI margin + positive levered cash flow. Missing any pillar means "not stabilized."
4. **Pursuit capital is a distinct tranche.** It carries pre-entitlement risk, gets a Co-GP promote, and often earns imputed equity from entitlement lift. Modeling it as generic equity loses signal.
5. **Automation comes LAST.** Musk's 5 principles: question requirements → delete → simplify → accelerate → automate. Most product mistakes come from automating a bad process.
6. **Data is the moat, not the AI.** Raw AI produces confident-sounding wrong answers. Structured data lets the agent know what it doesn't have.
7. **Model hygiene is judgment hygiene.** Color grammar (blue=input, black=calc, green=link), monthly granularity, XIRR over IRR, no circular refs — these are the industry "tells" for trustworthy work.
8. **Site visits don't automate.** Build the packet, don't replace the visit.

## How to Use the References

Reference files in `references/` are hard-linked to `docs/Best Practice Synthesis/` — editing either location updates both. The full-text source articles (27 files from Adventures in CRE via Wallabag) live in `docs/Best Practices Corpus/` and can be grep'd when a reference doc doesn't have enough detail.

Cite source articles inline when making a product claim (e.g., "A.CRE recommends a single IC memo template per strategy, see `references/07_ux_and_workflow_expectations.md`").

## Viciniti-Specific Anchors

Use these references to resolve common product questions:

- **"What should we call this field?"** → `08_vocabulary_and_terminology.md`
- **"Should we add Monte Carlo?"** → `04_sensitivity_and_simulation.md`
- **"What would an analyst expect here?"** → `07_ux_and_workflow_expectations.md`
- **"How should this metric be presented?"** → `02_metrics_hierarchy.md`
- **"Does this match how practitioners actually evaluate deals?"** → `01_deal_evaluation_mental_models.md`
- **"How should we expose Viciniti to AI tools?"** → `06_ai_workflow_patterns.md`, `05_data_architecture_for_cre.md`
- **"Is our waterfall/capital stack model industry-standard?"** → `03_modeling_conventions.md`

## What This Skill Does NOT Replace

- `CLAUDE.md` — project setup, deploy, infrastructure, tech stack, testing policy
- `docs/FINANCIAL_MODEL.md` — the actual cashflow/waterfall/debt math
- The underlying source articles in `docs/Best Practices Corpus/` — consult when a reference doc is too terse

If a question depends on a specific A.CRE article's nuance, grep `docs/Best Practices Corpus/` by keyword and read the relevant file(s) directly.
