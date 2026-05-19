# UX and Workflow Expectations for CRE Underwriting Tools

## Introduction

CRE underwriting software is not used in a vacuum — it lives inside a deliverable-driven workflow that begins with an Offering Memorandum (OM) and ends, if things go well, with closing documents and quarterly asset reports. Between those bookends, a professional analyst produces a cascading chain of artifacts (fit checks, rent roll cleanups, T-12 normalizations, comp sets, pro formas, sensitivity tables, IC memos) each of which feeds the next. Understanding this workflow is the single biggest lever a web app like Viciniti has over a generic Excel template: the app can be opinionated about *what comes next* rather than presenting the user with an empty grid.

For Viciniti, this matters because the team is not hiring a 20-person acquisitions shop — it is a small Portland-area operator that wants the tool to carry the weight that a mid-market IC, analyst bench, and broker CRM would normally carry. That means the tool needs to respect the conventions practitioners are trained on (color-coded inputs, version tabs, auditable formulas), surface the decision-driving subset of the data, and know where to stop. A tool that tries to replicate a 60-page IC memo loses; a tool that produces a tight 20-page decision document and links back to its assumptions wins (source: `53_automation_principles_multiplier_framework.md`).

## 1. Who Actually Uses These Tools

CRE is a big tent — "over 2.9 million jobs are tied to commercial real estate" and a practitioner's value is largely tied to "deal seasoning," i.e. how many deals they have closed in a given geography and property type (source: `54_careers_in_commercial_real_estate.md`). The roles that live inside an underwriting tool day-to-day are a small subset of that tent:

- **Acquisitions analysts/associates** — screen OMs, build pro formas, pull comps, pass IC memos up the chain. Compensation $120K analyst to $500K MD total — a salaried bench that chews through deals.
- **Asset managers** — take over after close. Track performance against the underwritten business plan, rebuild budgets, refresh hold/sell analysis.
- **Development teams** — manage use/source budgets, draw schedules, construction carry, lease-up. Viciniti's 4-carry-type engine and draw-schedule logic is squarely in this lane.
- **Dispositions** — rebuild a model for sale, produce a BOV package (Broker Opinion of Value), stress exit cap.
- **Portfolio managers** — roll up per-asset models to portfolio-level risk and return views.
- **Brokerage analysts** — pump out OMs and BOVs at volume; their output is the *input* to every acquisitions shop.

What is NOT in scope for an underwriting tool: property management (day-to-day ops), loan servicing (admin), investor relations communications, appraisal. These adjacent roles consume model *outputs* but do not do modeling themselves.

## 2. The Deliverable-Driven Workflow

The workshop #2 breakdown (source: `60_the-multiplier-framework-workshop-2-double-underwriting-speed-with-ai.md`) frames underwriting not as a single deliverable but as "a collection of dozens of repeatable micro-tasks":

| Stage | Artifact | Micro-tasks |
|---|---|---|
| 1. Screening | Fit check / "buy box" pass | Read OM, check location/size/price/strategy against criteria |
| 2. Data capture | Cleaned rent roll + T-12 | Parse rent roll, map to unit mix, normalize T-12 to standard chart of accounts, generate T1/T3/T6/T12 trailing views |
| 3. Market work | Comp set | Pull rent comps, sale comps, cap rate comps, expense benchmarks |
| 4. Model build | Pro forma + scenarios | Input revenue/expense assumptions, size debt, run sensitivity, build waterfall |
| 5. Physical | PCR/Phase I summary | Digest condition reports, flag capex, site visit |
| 6. Decision | IC memo | Synthesize story + numbers into a 15–25 page document |
| 7. Close | Closing docs | Legal, loan closing, equity funding |
| 8. Post-close | Asset management plan | Budget vs. actual, business plan tracking |

Each arrow between stages is a friction point. AI workshops consistently found these micro-tasks are where time leaks: rent roll parsing, T-12 cleanup, and fit check each run 20 minutes manually vs. ~7 minutes automated, and the multiplier compounds when running three properties in parallel — a 60-minute task becomes 11 minutes (source: `60_the-multiplier-framework-workshop-2-double-underwriting-speed-with-ai.md`).

## 3. The IC Memo Problem

The IC memo is the single most-complained-about deliverable in CRE. The legacy pattern, as documented in `53_automation_principles_multiplier_framework.md`:

- **Legacy IC memo**: 60–80 pages, 100+ man-hours, comprehensive data dump, slow decisions, manual copy-paste from the model.
- **"Algorithm" IC memo**: 15–25 pages + targeted appendices, 20–30 man-hours, decision-driving variables only, fast decisions, linked model outputs and AI-generated summaries.

The principle behind this is Musk's "make the requirements less dumb" — ask *who reads this and which sections change their decisions?* Investors usually care about "6 charts and 2 paragraphs" of a quarterly report, not 25 pages. The same logic applies to IC memos: legacy appendices that are "never discussed in committee" should be deleted before anything is automated.

This has a direct product implication: a tool that auto-generates the 80-page memo is solving the wrong problem. A tool that auto-generates the 20-page decision memo — with links back to the model — is doing the real work.

## 4. Time-Sink Workflows Analysts Actually Perform

Five workflows consume disproportionate analyst time and are the places a tool earns its keep:

1. **Rent roll cleanup + unit mix tables.** Rent rolls "arrive in inconsistent spreadsheets and messy PDFs" and normalizing them into a standard schema is "one of the fastest underwriting wins" (source: `60`).
2. **T-12 cleanup + trailing summaries.** Messy historicals mapped to a standard chart of accounts, producing T1/T3/T6/T12 views.
3. **Comp pulling.** Most market data sits behind paywalls (CoStar, CompStak, RCA). The practical approach is "building your own comp database over time, for example by extracting standardized fields from incoming OMs" (source: `60`). Viciniti's parcel + listings scraper is directly on this path.
4. **Sensitivity tables + debt sizing.** Two-variable data tables (cap rate × rent growth, LTV × DSCR), stress testing, residual land value solves.
5. **Error checking / validation.** A separate validation pass catching inconsistencies, missing assumptions, or mismatches between the story and the numbers (source: `60`).

## 5. UI Conventions Practitioners Expect

Practitioners come to any new tool with Excel conventions pre-wired into their brains. `68_best-practices-in-real-estate-financial-modeling.md` spells out the conventions explicitly:

- **Blue font = required input.** Analyst owns the cell and must justify its value.
- **Black font = calculation/output.** Never edit directly.
- **Green font = link from another worksheet.** Never edit.
- **Red font = a change to a base calculation.** Flags that the template methodology has been overridden.
- **Version tab first.** Every A.CRE model opens with a "Version" tab containing update notes, compatibility warnings, and resource links. This is the analyst's audit trail — they will look for it.
- **Template discipline.** Keep a clean original, never work in the template itself, rename copies per deal.
- **No circular references.** Iterative calc is treated as a bug, not a feature — it "obscures the audit trail" and causes "model instability." Engines should resolve self-referential sizing algebraically (which Viciniti already does).
- **Standard keyboard shortcuts.** Ctrl+Shift+D (dollar), Ctrl+Shift+C (percent), Ctrl+Shift+Y (yellow highlight) — the `62_supercharge-excel-with-the-excel-4-cre-add-in.md` shortcut list is essentially the baseline muscle memory of a CRE analyst.
- **Standardized date headers.** Period Ending / Analysis Month/Quarter/Year / Analysis Year rows — analysts expect to see these structured consistently.
- **Standard output formats.** DSCR and equity multiple formatted as `0.00"x"`, cap rates as percentages, dollars with no decimals for summary rows.

A web app cannot replicate Excel key bindings, but it can replicate the *semantics*: color-code input vs. calculated vs. overridden fields, surface a version history, keep a read-only audit view, and refuse to let users corrupt calculated outputs.

Standardized IC templates are a related expectation. Per `53`, "one IC memo template per strategy with fixed section order" is a prerequisite before automating anything. Standardized inputs (rent rolls, T-12s, OM inputs in consistent formats) are an analyst's precondition for batching work.

## 6. Site Visit — The Workflow That Cannot Be Digitized

The site visit is the single workflow practitioners universally agree cannot be replaced by software (source: `71_the-real-estate-site-visit-checklist.md`). Its explicit purpose is to "assess perception vs. reality" — to challenge the desk-bound assumptions in the model. A site visit is a snapshot in time, ideally repeated (morning/evening, weekday/weekend).

What a site visit covers, organized by category:

1. **Location and access** — drive the market at different times, assess ingress/egress, signage, delivery access, curb cuts, transit proximity, nuisance sources.
2. **Exterior condition** — walk the perimeter, inspect roof/facade/parking, stormwater, fencing, ADA, loading docks.
3. **Interior inspection** — tour every space (including ones *not* in marketing materials), check deferred maintenance, HVAC, WiFi/cellular, fire/life safety.
4. **Community fit and user behavior** — observe at different dayparts, talk to tenants/managers, note competitors and complementary uses.
5. **Tour the market and comps** — physically visit rent and sale comps, confirm "top of market" claims with your eyes.

The tool's job here is not to replace the visit — it is to *support it*: generate the checklist, store photos and notes against the parcel/deal, flag which comps need to be visited in person, and push findings back into the model as assumption overrides.

## Viciniti Implications

- **Do produce a tight, templated IC memo** — but make it the 20-page decision document, not the 80-page data dump. Sections should be fixed per strategy (acquisition, development, value-add), and every number on the page should link back to the assumption that produced it.
- **Do own comp database workflows** — Viciniti's parcel + listings scraper already collects the raw material. The missing layer is structured fields extracted from OMs (rent, cap, price/unit, strategy, buyer) so the comp set becomes queryable rather than a folder of PDFs.
- **Do replicate Excel color-coding semantics** — input vs. calculated vs. override, a version/changelog tab per scenario, and a read-only audit view. This is the lowest-cost trust builder with any CRE user who has ever opened an A.CRE model.
- **Don't try to replace the site visit** — but do produce a site-visit packet (checklist, map, adjacent parcels, comp locations, photos from scraped listings, known nuisance sources) that an analyst carries into the field. Let findings flow back as annotations on the deal.
- **Don't try to handle everything** — skip property management ops, loan servicing, and investor relations comms. Those are downstream consumers of model outputs, not modeling workflows. The scope that matters is screening → model → IC → post-close business plan tracking, with strong export lanes (Excel, PDF memo, JSON) so the tool plays nicely with whatever the team uses next.
