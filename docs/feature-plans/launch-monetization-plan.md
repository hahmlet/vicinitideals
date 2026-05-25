# Launch Plan: Viciniti Deals → Paid SaaS

**Drafted:** 2026-05-24
**Status:** Draft for review
**Owner:** Steph
**Pricing model:** $200/seat/month, individual user billing (no org-level billing at launch)
**Target ceiling:** ~100 paid users over ~12 months ($240k ARR cap)
**Customer profile:** Small CRE teams, strangers (no personal onboarding)
**Asset class at launch:** Multifamily only. Commercial + Mixed-Use tier ships Q3 2026 (see Asset Class Scope).

---

## Strategy

Launch a self-serve, paid SaaS without personally onboarding users. Reduce scope by deferring data-acquisition features (parcels, scraped listings) until revenue justifies paid data sources. Lean on existing homelab infrastructure (Proxmox VM 114, Ollama VM 104, Plane Cloud, LiteLLM) — no new hardware. Use existing AI subscriptions (Claude Max, Copilot Pro) for bug triage automation — no API credits.

---

## Product Scope at Launch

### In scope (paid features)
- Deal underwriting: Uses, Sources, capital stack, monthly cashflow, draw schedule, waterfall, sensitivity, Excel/JSON exports
- Milestone timeline + wizard
- Email ingest (broker email attachments → opportunity creation) — **file attachments only, no body parsing**
- Proforma .xlsx parser
- Portfolios
- Auth / billing / org membership / invites
- **Multifamily asset class only** — see Asset Class Scope

### Out of scope at launch (feature-flag off, retain code)
- Parcel inventory + browser
- Scraped listings (Crexi, LoopNet, REALie)
- County GIS scrapers (Portland Maps, Clackamas, Oregon City, Gresham)
- Map view
- Broker pipeline + dedup
- HelloData enrichment
- Most of [data_intel.py](app/api/routers/) sub-router from refactor plan (~2,600 lines, 28 routes)
- Email body parsing (cut — keep attachment-only path)

**Re-enable trigger:** when revenue justifies paid data subscription (Reonomy ~$500/mo, ATTOM ~$1k/mo, CompStak ~$2k/mo). Customers fund it.

**Marketing reframe:** "Bring your deals. We model them." (not "We find deals for you.")

---

## Critical Path to Paid Signups

### Security (must complete before any paid customer)
- CSRF middleware on all writes (~1 day) — currently missing
- Rate limiting on all POST/PUT/PATCH/DELETE (~1 day) — currently auth-only
- Multi-tenant data isolation audit (~3 days) — remove "first org" fallback patterns in `ui.py:2414`, `ui.py:12582`, `scraper.py:534`
- Hard email verification gate (~half day) — currently soft (yellow banner only)
- Two-factor authentication via TOTP (`pyotp`) (~2 days) — optional for users, mandatory for org admins
- Audit log inside org workspace (~3-5 days) — `audit_log` table, write on key mutations

### Multi-user / org
- Org invite flow with tokenized email links (~3 days) — none currently exists
- Account delete + lightweight data export (~1 day)
- Remove org-list dropdown from public register page — switch to: invite-link-only join, public signup creates fresh org

### Billing — Stripe (not Paddle)
- Stripe + Stripe Tax integration (~5 days)
- Stripe Customer Portal for self-serve cancel/manage (~1 hour)
- Subscription status → middleware that blocks paid features when inactive
- Account suspension flow on payment failure (~2 days): banner → 7-14 days read-only → write lock
- Webhook handler with idempotency keys

**Why Stripe over Paddle:** at $48-240k year-1 ARR, US-focused, solo founder, Stripe is ~$4k/yr cheaper. Stripe Tax + a fractional CPA handles compliance for less than Paddle's 2% MoR premium. Re-evaluate at $250k+ ARR.

**Why not Stax:** crossover at ~$250k revenue. Stripe wins below that. AmEx-heavy customers further erode Stax's advantage (interchange passthrough = AmEx hurts you, not Stripe). Stax also requires underwriting application (1-2 week delay) and weaker subscription tooling.

### Legal
- Oregon LLC formation: Viciniti Deals, LLC ($100 state fee)
- Registered agent (Northwest Registered Agent, ~$125/yr) for privacy
- EIN from IRS (free, direct, ~10 min)
- Business bank account (Mercury or Relay, free)
- ToS / Privacy Policy / AUP via Termly (~$120/yr)
  - Custom clause required: **"Not financial advice"** disclaimer
  - Liability cap at 12 months of fees paid
  - Customer accepts full responsibility for underwriting decisions
- Optional lawyer review of ToS (~$500-1,000 one-time, recommended)
- DPA template ready (Termly) for B2B customers who ask

### Insurance
- E&O (Errors & Omissions) + cyber liability — non-negotiable at $200/seat B2B underwriting tool
- Quote from Vouch, Founder Shield, or Hiscox: ~$800-1,500/yr
- Get policy bound **before** first paid customer

### Infrastructure
- Cloudflare Tunnel in front of VM 114 (~1 day) — hides home IP
- Cloudflare WAF + edge rate limiting (free tier)
- Cloudflare Email Routing (free) for inbound `support@viciniti.deals`
- DKIM / SPF / DMARC records on `viciniti.deals` — required for Resend deliverability
- Off-VM Postgres backups, daily to Backblaze B2 or S3 (~half day setup, ~$50-120/yr storage)
- Cost ceiling alerts on every paid vendor (Stripe, Resend, Groq fallback, Cloudflare) — prevents runaway-bill incidents

### Beta / Production environment split
- **Option B chosen:** separate LXC on Proxmox host for beta (not a second compose stack on VM 114)
- Reasoning: cleaner VS Code workflow (separate SSH targets = separate windows = no risk of `docker compose down` on wrong stack), better isolation, deploy script already takes container_id parameter
- New LXC: ~3 days setup
- Promotion flow: merge to `main` → auto-deploy to beta LXC → smoke test → tag release → manual deploy to prod LXC

### Email ingest hardening
- **Cut body parsing entirely.** File attachments only (`.xlsx` proforma + PDF). Email without attachments tagged "no_attachment" — manual user trigger if desired.
- Add timeout to every Ollama call via `httpx.AsyncClient(timeout=60.0)`
- Add Celery `time_limit=120` on `parse_proforma` and `email_ingest` tasks
- Per-user rate limit: max 20 emails processed per user per hour at launch
- Ollama health check + retry-with-backoff on failure
- Fixes the existing 66% hang bug at `app/tasks/proforma_parse.py:~565`

### LiteLLM routing (use existing LXC 125)
- Configure: primary = local Ollama (VM 104, RTX 3070), fallback = Groq Cloud
- Point vicinitideals' `ollama_base_url` at LiteLLM (192.168.1.161) instead of Ollama directly
- Sign Groq's zero-retention agreement (free, by email) before pointing customer data at them
- Result: $0 most months, transparent failover during local outages, no SPOF
- Effort: ~1 day

### Bug capture pipeline
- In-app "Report a problem" widget → modal form (~3 days)
- Auto-attach: scrubbed scenario JSON, current URL, browser console log, last 50 server log lines (filtered to user's org), optional screenshot
- POST to GitHub issues in private `vicinitideals-bugs` repo
- GitHub Action labels `bug-triage`, assigns `@copilot`
- Copilot coding agent (Copilot Pro perk, no API credits) posts first-pass triage comment
- Escalation tier: tag `deep-triage` → manual run of Claude Code (Max plan auth, no API credits) for richer analysis
- **JSON export resurrection required first** (~3-5 days) — current export not touched in a month, drifted with migrations 0094-0097, broken round-trip likely
  - Add round-trip test in CI: export → wipe → import → assert deep-equal
  - Add `--scrub` mode: redact address + project name + city + zip (financials preserved — needed for bug repro)

### Onboarding
- Demo deal seeded on org creation: "Sample: 24-unit Multifamily, Gresham" with realistic capital stack, milestones, financials
- Empty-state CTAs across all major pages: "No deals yet — start one"
- 3-5 short Loom videos linked from in-app "Help" menu (you record, ~half day per video)
- Foolproof top 2-3 friction points: wizard step labels, error messages, inline help text
- **Not building:** guided tour library (Shepherd.js / Intro.js) — rots with UI changes, high maintenance
- Effort: ~2 weeks

### Support stack
- Inbound email: Cloudflare Email Routing (free) → forward `support@viciniti.deals` → Plane intake (or via API webhook if Plane "One" tier doesn't include email intake)
- Ticket tracking: Plane (existing subscription, "One" tier)
- Public roadmap: Plane public view of "Roadmap" project, statuses (Planned / In Progress / Shipped), linked from app footer
- Public changelog: Plane Pages (published)
- Bug status visibility: shareable Plane issue links so customers can follow their reports

### Marketing surface
- `/pricing` page (FastAPI-rendered or static)
- `/about`, `/features`, `/contact`
- Landing page at root (currently login screen) — public, not requiring auth
- Effort: ~3-5 days

### Pricing strategy (decisions open — see Open Decisions)
- $200/seat/month — confirmed
- Free trial: TBD (recommend 14 days, card up front, auto-convert)
- Annual plans: TBD (recommend 20% discount)
- Refund window: TBD (recommend 14-day full refund)
- Grandfathering policy: TBD (recommend honor current price for existing customers on future raises)

---

## Asset Class Scope

### Launch tier: Multifamily ($200/seat/month)

Current platform readiness: ~95% for multifamily of any size. Engine, schema, UI, proforma parser, defaults all multifamily-tuned. Replacement reserves gap (see [memory #9380](https://example/9380)) is small, fixable as part of launch hardening.

### Deferred to Q3 2026 tier: Commercial + Mixed-Use ($300/seat/month, separate plan)

Commercial = general office / retail / industrial / mixed-use. Specialized commercial (hotel, self-storage, medical office, senior living) remains permanently out of scope.

**Pre-launch posture for commercial interest:**
- `/pricing` page lists Commercial tier as "Coming Q3 2026"
- Email-capture form for waitlist on Commercial tier (signals demand, marketing list)
- Sales conversations: honest "Commercial Q3" answer, no scope creep into MF launch

**Q3 2026 commercial readiness work** (not pre-launch):

| Hole | Effort | Notes |
|---|---|---|
| `ProjectType` enum extension + property-type-aware defaults | ~2 days | Foundation |
| `tenant_roll` JSONB on Project (mirror `unit_mix` pattern) | ~3 days | Per-tenant: name, suite, SF, lease start/end, base rent, CAM type, TI, LC, renewal option |
| Tenant roll UI (entry, edit, view) | ~1 week | Mirror unit-mix UI |
| Per-tenant rent step schedule (fixed steps, not just %/yr) | ~3 days | Office/retail leases use explicit schedules |
| CAM reimbursement engine math (pro-rata share, gross-up, expense stops) | ~1 week | `non_recoverable_pct` already planned per [argus-cre-schema-improvements.md](argus-cre-schema-improvements.md) |
| TI/LC at lease rollover (recurring, not just acquisition Use) | ~3 days | New first-class OpEx-or-CapEx category |
| Re-leasing assumptions: rollover downtime, free rent, market-vs-in-place, renewal probability | ~1 week | Argus core feature |
| Per-tenant vacancy / occupancy state | ~3 days | Replaces single vacancy % for commercial deals |
| Proforma parser commercial branch (LLM prompt + rent-roll extraction) | ~3 days | Different layout from MF proformas |
| Mixed-use combined modeling (MF unit-mix + commercial tenant-roll on same Project) | ~1 week | Both income structures coexist, single capital stack + exit |
| Property-type-specific exit cap rate defaults | ~1 day | MF 4-5%, Office 6-8%, Retail 6-7%, Industrial 5-6% |
| Documentation + testing scenarios | ~1 week | Scenario Library expansion |

**Total commercial readiness:** ~6-8 weeks solo dev. Self-funded by MF tier revenue once stable.

**Explicitly NOT in commercial tier:**
- Percentage rent (retail % of gross sales above breakpoint) — niche even within retail
- Hotel / self-storage / medical office / senior living — fundamentally different economics
- Full Argus parity — focus on the 80% of commercial deals that have simple-to-moderate complexity

### What this affects upstream

- Marketing reframe (already noted): "Bring your multifamily deals. We model them." Tighter than generic CRE.
- Onboarding demo seed: multifamily examples only at launch
- Scenario Library (see Testing Strategy): MF scenarios only at launch; commercial scenarios added during Q3 work
- Pricing page: two tiers visible — MF live, Commercial waitlist
- Existing [argus-cre-schema-improvements.md](argus-cre-schema-improvements.md) plan = commercial readiness work, executed Q3, not pre-launch

---

## Testing Strategy

Three layers, each cheap-to-build, multiplying value together. Focus: cover more deal varieties, make tests easier to engage with, catch edge cases humans miss.

### Layer A: Scenario Library

Build admin-only page in the app: `/admin/scenarios`. Lists curated deal templates, each with a "Seed" button that materializes a full deal into the DB. Same templates double as Playwright fixtures AND onboarding demo seeds.

**Initial library (MF launch):**

```
[MF — Garden, 24 units, lease-up]
[MF — Mid-Rise, 80 units, stabilized]
[MF — LIHTC w/ grant cap]
[MF — Acquisition + light reno]
[MF — Ground-up construction]
[Edge: DSCR-capped scenario]
[Edge: Source-Use eligibility binding]
[Edge: Replacement reserves stress test]
[Edge: Multi-source waterfall promote crossover]
```

**Q3 2026 additions (commercial tier):**

```
[Office — NNN, single-tenant, 50k SF]
[Office — multi-tenant, CAM reimbursement]
[Retail — strip, 3 tenants, gross lease]
[Retail — anchor + inline, rollover]
[Industrial — single-tenant warehouse]
[Mixed-Use — Ground retail + 12 apts]
```

**Why this design:**
- Same fixtures power manual exploration + Playwright tests + onboarding demos (single source of truth)
- One-click reproduction of tricky deal shapes
- New bugs ship with a permanent scenario that reproduces them (regression triage tool)
- Subset visible to all users as "Examples" — drives onboarding (no empty-DB experience)
- Replaces hand-written fixtures scattered across `tests/conftest.py`

**Architecture:**
- One Python function per scenario, returns full deal definition (Project + Scenario + UseLines + IncomeStreams + CapitalModules + Milestones + OpEx + DrawSources + WaterfallTiers)
- Reuses real app constructors (same path as `seed_e2e_user.py`)
- Registered in central `app/scripts/scenario_library.py`
- Admin page loads list dynamically

**Pre-launch effort:** ~1 week to build page + 8-10 starter scenarios.

### Layer B: Playwright tests parameterized over Scenario Library

```python
@pytest.mark.parametrize("scenario", SCENARIO_LIBRARY.keys())
def test_underwriting_summary_renders_for_all_scenarios(page, scenario):
    deal_id = seed_scenario(scenario)
    page.goto(f"/builder?deal={deal_id}")
    expect(page.locator(".underwriting-summary")).to_be_visible()
    expect(page.locator(".dscr-pill")).not_to_have_text("Error")
```

Each new scenario added to library → automatic coverage across every parameterized test. ~3-5 days to wire parameterization across existing E2E suite + add 3-4 new test families covering: deal create, builder render, capital stack edit, export.

### Layer C: Playwright Trace Viewer (free, built-in, currently underused)

Add `--tracing on` to pytest-playwright config. Every E2E run produces a `.zip` trace with time-travel debugging — every DOM snapshot, network call, console log per step. Open with `playwright show-trace trace.zip`.

**Pre-launch effort:** ~1 hour config change. Massive ROI when chasing flaky failures from stranger-customer bug reports.

### Layer D: Hypothesis property-based engine tests

Add to engine tests only (not E2E). Hypothesis generates thousands of random valid deal configurations and checks invariants the human-written tests miss.

```python
@given(deal=valid_deal_strategy())
def test_sources_equals_uses_always(deal):
    result = run_cashflow(deal)
    assert abs(result.total_sources - result.total_uses) < Decimal("0.01")

@given(deal=valid_deal_strategy())
def test_dscr_cap_binds_correctly(deal):
    if deal.has_dscr_cap and not deal.has_grant:
        result = run_cashflow(deal)
        assert result.min_dscr >= deal.target_dscr - Decimal("0.001")
```

**Pre-launch effort:** ~3-5 days to add 10 invariant tests + define `valid_deal_strategy()` generator.

### What we're NOT building

- Visual regression (Percy, pixelmatch) — overkill for HTMX server-rendered UI, churn-heavy
- Selenium IDE / Cypress — already on Playwright, no reason to swap
- Manual test management platforms (TestRail, Zephyr) — overkill for solo dev
- Mutation testing (mutmut, cosmic-ray) — promising but high false-positive rate

### Total testing strategy pre-launch effort: ~2.5-3 weeks

Slot into Week 6-7 of sequence (before onboarding work — Scenario Library is a prerequisite for the onboarding "demo seed" piece).

---

## Style Guide + Agent Workbook

Standalone artifact, broader than UI, lives forever past launch. Ranks alongside `FINANCIAL_MODEL.md` and `DATA_MODEL.md` as a top-level reference doc — but distinguished by being explicitly designed for AI-agent consumption.

### Why this exists

Every AI session that touches UI currently re-guesses conventions. Multiplied across 100+ PRs → drift. The workbook eliminates the guess. From the 2026 emerging standard: "be simple, explicit, and boring — cover all edge cases so there are no decisions for the AI to make." Conflicting sources (docs vs. tokens vs. components) are catastrophic — agents pick whichever they saw first.

### Four tiers (build all four)

#### Tier 1: `DESIGN.md` at repo root (the 2026 emerging standard)

Not `docs/STYLE_GUIDE.md` — adopt the `DESIGN.md` convention that AI agents are starting to expect natively. Lives at repo root, version-controlled, markdown.

Structure:
- **Colors** — hex + intended use (primary CTA, destructive, neutral, surface)
- **Typography** — families, sizes, weights, line heights per text style (h1/h2/body/caption)
- **Spacing** — base unit + scale (--space-1, --space-2, --space-4, --space-8)
- **Motion** — duration values + cubic-bezier easing
- **Components** — canonical macros + when to use each
- **Terminology / Glossary** — canonical names table from UI Polish section (Deal, Source, Use, OpEx, DSCR, CoC, cap rate, carry types, vacancy/occupancy)
- **Button + field conventions** — labels, validation message patterns, required markers, currency/percentage/date formats, focus management
- **Empty / loading / error state patterns**
- **Accessibility minimums** — alt text, label associations, keyboard nav, ARIA on HTMX targets
- **Pattern catalog (recipes)** — "How to add a wizard step" / "How to add a form field" / "How to add an export format" — code recipes showing canonical macros in action
- **Philosophy** — tone, density, what we don't do (no animations beyond HTMX defaults, no custom JS frameworks, no dark mode at launch)

#### Tier 2: Jinja2 macro library (`app/templates/macros/`)

Code that exists — agents call these instead of hand-rolling HTML. Single source of truth.

```
app/templates/macros/
  buttons.html     # primary, secondary, destructive, icon-only, link
  fields.html      # text, currency, percentage, date, dropdown, textarea, checkbox, radio
  states.html      # empty, loading, error, success
  forms.html       # form_row, form_section, form_actions, validation_message
  pills.html       # status pills, badges (consolidate 3-4 drifted variants)
  tooltips.html    # jargon-term tooltip with (i) icon
  tables.html      # data table, sortable header, empty-table state
  dialogs.html     # modal, drawer, confirmation
```

**Build approach:** write from scratch in plain Jinja2, matching your existing template aesthetic.

**Use [basic-components](https://github.com/basicmachines-co/basic-components) (MIT, archived April 2026) as a reference book only** — read their Tailwind class choices, ARIA patterns, accessibility decisions. Do NOT port their JinjaX source or migrate your app to JinjaX. Vanilla Jinja2 throughout.

#### Tier 3: CSS tokens (`app/static/tokens.css`)

Single source for color, spacing, typography. Custom properties.

```css
:root {
  --color-primary: #...;
  --color-primary-hover: #...;
  --color-destructive: #...;
  --color-text: #...;
  --color-text-muted: #...;
  --color-surface: #...;
  --color-border: #...;
  --space-1: 0.25rem;  --space-2: 0.5rem;  --space-4: 1rem;  --space-8: 2rem;
  --font-h1: 1.875rem;  --font-h2: 1.5rem;  --font-body: 1rem;  --font-caption: 0.875rem;
  --weight-regular: 400;  --weight-medium: 500;  --weight-bold: 600;
  --radius-button: 0.375rem;  --radius-card: 0.5rem;
  --motion-fast: 150ms;  --motion-base: 250ms;
  --easing-standard: cubic-bezier(0.4, 0, 0.2, 1);
}
```

Existing templates currently hard-code colors + pixel values in multiple places. Tokenize once, reference everywhere.

#### Tier 4: Agent integration hooks

Make agents actually use the workbook. Three mechanisms:

1. **`CLAUDE.md` directive** — add:
   ```
   ## UI work: consult DESIGN.md before touching templates.
   Use macros from app/templates/macros/. Do not write raw <button> or hand-style controls.
   Terminology must match the Glossary section of DESIGN.md.
   ```
2. **Pre-commit hook** (custom Ruff or grep) — flag raw `<button>` in `*.html` templates, flag inline hex colors, flag drifted terms (e.g. "Cost" when canonical is "Use")
3. **Pattern catalog as copy-pasteable recipes** in DESIGN.md — agents prefer cloning working examples to inventing. Show the canonical form for every common task.

### One-time use of Claude Design as accelerator

Claude Design's onboarding reads your codebase + design files and **auto-extracts a design system**. Use this once to seed initial color/typography/spacing tokens for `DESIGN.md`. Then iterate in Claude Code.

Not a substitute for the four-tier setup — Claude Design generates visual designs, not the markdown/macro/CSS artifacts agents need. But its extraction step accelerates Day 1.

### Why this beats "just write the doc"

A doc tells the agent what to do. The macro + token + hook layers make the wrong thing mechanically harder than the right thing. Same principle as "make illegal states unrepresentable" — make off-style UI harder to produce than on-style UI.

### Effort

| Tier | Effort |
|---|---|
| Tier 1: `DESIGN.md` (seed with Claude Design extraction, then refine) | ~3-4 days |
| Tier 2: Jinja2 macro library (8 macro files) | ~3-5 days |
| Tier 3: `tokens.css` | ~1-2 days |
| Tier 4: CLAUDE.md update + pre-commit hook + pattern catalog | ~2 days |
| **Subtotal** | **~10 days** |
| First sweep applying macros + tokens across existing templates | rolls into UI Polish Week 8-9 |

### Sequence placement

**Style Guide work is prerequisite to UI Polish.** UI Polish applies the conventions; the conventions must exist first. Insert as Week 7-8, UI Polish becomes Week 8-9 sweep.

### Ongoing value beyond launch

- Q3 2026 commercial tier ships with consistent UI from day one (no second wave of drift)
- Customer-reported "the UI is inconsistent" feedback drops to zero
- Onboarding Looms have stable surface (don't re-record when buttons rename)
- Bug-triage Copilot agent reads the same DESIGN.md when proposing fixes → consistent fixes
- Marketing surface (landing page, /pricing) reuses same tokens — visual identity carries

### Adopted from 2026 industry patterns

- **`DESIGN.md` naming convention** — emerging standard, agents are starting to expect this filename
- **Shadcn-style "copy don't depend"** — components live in your repo, you own them, no upstream dep
- **"Plant seeds, not trees"** — start with naming conventions + token structure + component descriptions; expand iteratively
- **Token-first architecture** — tokens > components > patterns > philosophy (dependency direction)
- **Agent Experience (AX) formats** — parseable markdown, explicit type definitions, llms.txt-style summaries

### References

- [DESIGN.md article — Better Stack](https://betterstack.com/community/guides/ai/design-md-ai/)
- [Expose your design system to LLMs — Hardik Pandya](https://hvpandya.com/llm-design-systems)
- [Coding guidelines for AI agents — Stack Overflow Blog](https://stackoverflow.blog/2026/03/26/coding-guidelines-for-ai-agents-and-people-too/)
- [basic-components (reference only, do not port)](https://github.com/basicmachines-co/basic-components)
- [Claude Design help center](https://support.claude.com/en/articles/14604416-get-started-with-claude-design)

---

## UI Polish

Currently the app shows its homemade origins — drifted terminology, inconsistent buttons, jargon-heavy labels. At $200/seat to strangers, polish stops being optional. **Not a redesign** — keep current layout + HTMX architecture. Targeted hygiene pass.

### Scope

#### 1. Terminology normalization (canonical names + glossary)

Pick one term per concept, apply everywhere. Document in [docs/GLOSSARY.md](../GLOSSARY.md) (the same one being published open-source).

| Concept | Current state (drift) | Canonical |
|---|---|---|
| Underwriting entity | "Deal" / "Scenario" / "DealModel" / "Model" | **Deal** in UI, `Scenario` in code (alias retained) |
| Pre-deal target | "Opportunity" / "Listing" / "Property" | **Opportunity** |
| Building shell | "Project" / "Property" / "Building" | **Project** in code, **Property** in UI (more familiar to CRE) |
| Capital piece | "Source" / "Funding" / "Capital Module" / "Loan" / "Vehicle" | **Source** in UI, `CapitalModule` in code |
| Cost line | "Use" / "Cost" / "Line Item" / "Expense" | **Use** in UI |
| Recurring expense | "OpEx" / "Operating Expense" / "Expense" | **Operating Expense** |
| Property type list | drifted across 2+ templates | Single canonical list from `ProjectType` enum |
| Carry types | `io_only` / `interest_reserve` / `capitalized_interest` / `pi` | Display: "Interest-Only", "Interest Reserve", "Capitalized Interest (PIK)", "Amortizing" |
| Funder vs Vehicle vs Equity Role | three overlapping fields | Use `vehicle_type` + `equity_role` (canonical post-0085); `funder_type` legacy bridge only |
| Coverage ratio | "DSCR" / "Debt Service Coverage" / "D.S.C.R." | **DSCR** with tooltip expanding it on first use per page |
| Return metric | "CoC" / "Cash-on-Cash" / "Cash on Cash Return" | **Cash-on-Cash** in labels, "CoC" in column headers |
| Cap rate | "Cap Rate" / "Capitalization Rate" / "Going-In Cap" / "Exit Cap" | **Going-In Cap Rate** and **Exit Cap Rate** explicit |
| Vacancy/Occupancy | inconsistent which one is the input | Per [argus-cre-schema-improvements.md](argus-cre-schema-improvements.md) — flip to **Occupancy %** as the input |

#### 2. Button + control normalization

Single source of truth for button styling + labels. Defined as Jinja2 macros in `app/templates/_buttons.html`.

**Canonical button labels** (no more "Submit" vs "Save" vs "Update"):

| Action | Label | Style |
|---|---|---|
| Save form, stay on page | **Save** | Primary |
| Save + move forward in wizard | **Continue** | Primary |
| Save + close drawer/modal | **Save and Close** | Primary |
| Discard changes | **Cancel** | Secondary |
| Wizard back | **Back** | Tertiary/link |
| Destructive action | **Delete <thing>** | Destructive (red) |
| Open form to create | **Add <thing>** | Primary |
| Open form to edit | (pencil icon) | Icon-only |
| Export action | **Export <format>** | Secondary |
| Run computation | **Compute** | Primary |

**Field normalizations:**
- Required marker: red asterisk `*`, consistent placement (right of label)
- Currency input: thousands separators auto-formatted, `$` prefix in label not in input
- Percentage input: trailing `%` in label, value as raw number (5.0 not 0.05) — pick one convention, apply everywhere
- Date input: ISO format internal, display as `Jan 5, 2026` style
- Tooltips: `(i)` icon on every jargon term first time it appears on a page
- Validation messages: plain English, never raw Pydantic errors (`Field required` → "Please fill in the Loan Amount")
- Focus management: after HTMX swap, focus next logical input
- Tab order: explicit `tabindex` on wizard forms

#### 3. Deal Creation flow specifically

Most visible flow for new customers — biggest first-impression impact.

| Stage | Current friction | Fix |
|---|---|---|
| Opportunity Wizard | Step 1-3 button labels inconsistent | "Back" / "Continue" / "Create Deal" (terminal step) |
| Deal Setup Wizard | "Save Draft" vs "Save" vs "Continue" | Auto-save on field blur; "Continue" button advances |
| Timeline Wizard | Two-pass milestone creation hidden complexity | Single visible step list, "Approve Timeline" as terminal |
| Builder landing | Empty state shows raw "no data" | Empty state with CTA: "Add your first capital source" / "Add your first use" |
| Capital Module form | Carry type dropdown labels = code values | Display labels per canonical table above |
| Compute button | "Compute" / "Run" / "Calculate" used variously | Single "Recompute" button, always visible at top of builder |

#### 4. Empty + loading + error states

- Every list/table has a designed empty state with CTA (not "No rows")
- HTMX swaps show a loading indicator on the affected region (skeleton or spinner)
- Errors never show stack traces in production; show a user-friendly message + "Report this" button (wired to the in-app bug widget from launch plan)
- 404, 403, 500 pages: branded, consistent, with link back to dashboard

#### 5. Spacing + hierarchy

- One pass over typography scale: 4 sizes max (h1, h2, body, caption)
- Section spacing consistent (one CSS variable, applied via utility class)
- Color: primary action color used only on primary actions (currently overused)
- Pill / badge styles consolidated (currently 3-4 variants drift across templates)

### Out of scope (defer)

- Full design system (Storybook, component library)
- Dark mode
- Mobile responsiveness (desktop-first for $200/seat B2B; mobile audit deferred until Q4)
- Animation polish beyond what HTMX provides natively
- Custom illustrations / mascot
- Brand refresh (logo, color palette beyond current)

### Effort

Single focused 2-week pass, sequenced after onboarding work (Week 8-9). Onboarding's "foolproof top 2-3 friction points" partially overlaps — combine into one effort.

**Suggested execution pattern:**
1. Day 1-2: Write [docs/GLOSSARY.md](../GLOSSARY.md) + canonical button/field macros in `app/templates/_buttons.html`
2. Day 3-5: Terminology sweep — grep + replace across `app/templates/`, `app/api/routers/ui.py`
3. Day 6-8: Deal Creation flow polish (wizards, buttons, empty states)
4. Day 9-10: Empty/loading/error state pass
5. Day 11-12: Spacing/hierarchy + pill/badge consolidation
6. Day 13-14: Cross-page consistency audit (one full walkthrough screenshotting each page, fix outliers)

**Verification:** Scenario Library admin page (from Testing Strategy) provides the test bed — seed 8-10 deals, click through every page on each, screenshot diff.

---

## What We're Explicitly NOT Doing

- Phase 2a/2b refactor (ui.py split into 7 sub-routers, service layer extraction) — pure internal velocity, defer indefinitely
- Full UI redesign — handled separately, not justified by 100-user ceiling
- Migration to Cloudflare Workers — Python stack doesn't run there, full rewrite not justified
- Migration to managed hosting (Fly.io, Railway, Render) — VM 114 handles 100 users 20x over
- Open-sourcing the engine code under permissive MIT — too much moat lost for a solo operator
- Org-level billing — defer until customer asks
- SOC 2 — defer until a customer is willing to pay annual contract gated on it
- Status page (UptimeRobot etc.) — Plane public roadmap doubles as status communication
- Sentry / Bugsink — Copilot triage + GitHub issues serve the same need
- Guided product tour library — too brittle for the value
- Scraper reliability work, jurisdiction backfill, parcel hardening — feature-flagged off

---

## AI Infrastructure Assessment

**Current state:**
- VM 104 `docker-ai` (192.168.1.184): RTX 3070, 8 GB VRAM, 15 GB RAM, 8 vCPU
- LXC 120 `ollama` (192.168.1.34): secondary, available
- LXC 125 `litellm` (192.168.1.161): routing layer, currently idle

**Workload at launch scope (file-only ingest, 5-10 emails/wk per user, 100 users):**
- ~750 emails/wk → ~500 LLM jobs/wk → ~1000 LLM calls/wk
- Peak: ~100 calls/hr Monday morning
- Per call on RTX 3070 with 8B Q4 model: ~5-10 sec
- **3070 has 10-20x headroom for this workload**

**Constraints of RTX 3070 (8 GB VRAM):**
- Fits Llama 3.1 8B Q4, Qwen2.5 7B Q4 comfortably
- Does NOT fit 8B Q8 (better quality) or any 14B+ model
- No room for parallel jobs

**Rented GPU cost reference** (for future scaling decisions):

| Option | Cost at our volume (~6M tokens/mo) |
|---|---|
| Groq Cloud (per-token) | ~$0.30/mo |
| DeepInfra (per-token) | ~$0.90/mo |
| Together.ai (per-token) | ~$1.20/mo |
| Modal A100 (serverless) | ~$2.50/mo |
| RunPod RTX 4090 dedicated | $245/mo (wasteful at this volume) |

**Conclusion:** no new hardware purchase. Stay local with Groq fallback via LiteLLM.

---

## Open-Sourcing Strategy

**Publish (CC BY 4.0 license):**
- [docs/FINANCIAL_MODEL.md](docs/FINANCIAL_MODEL.md) — math, formulas, day-count conventions, carry types
- New `docs/GLOSSARY.md` extracted from existing docs — CRE term definitions

**Keep private:**
- [docs/DATA_MODEL.md](docs/DATA_MODEL.md) — ORM schema reveals storage internals
- [docs/MARKET_MODEL.md](docs/MARKET_MODEL.md) — comp methodology / KNN
- [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) — infrastructure references
- All engine code

**Mechanism:**
- New public repo: `vicinitideals/financial-model-spec` (or similar)
- GitHub Action: one-way sync of whitelisted `.md` files from private repo to public on push to `main`
- Issues + Discussions enabled on public repo for expert engagement
- README: "Reference spec for the math behind viciniti.deals. Software is closed-source; math is open."
- Timing: publish at launch, not before (nobody to engage with pre-launch)
- Effort: ~1 day

**Why docs-only over engine source-available license:**
- Lower implementation effort (~1 day vs. weeks of licensing work)
- Same marketing benefit (trust + credibility + SEO + expert engagement)
- Zero moat risk (math is industry knowledge; implementation is the moat)

---

## Cost Projections

### One-time launch costs

| Item | Cost |
|---|---|
| Oregon LLC filing | $100 |
| Northwest Registered Agent (first year) | $125 |
| Lawyer review of ToS (optional) | $500-1,000 |
| Trademark search + filing (USPTO, optional) | $0-350 |
| **Total** | **$725-1,575** |

### Year 1 recurring (assume 50-user midpoint = $120k ARR)

| Item | Cost |
|---|---|
| Oregon LLC annual report | $100 |
| Registered agent | $125 |
| Stripe + Stripe Tax fees | ~$4,260 (3.4% effective) |
| Termly (ToS/Privacy/AUP) | $120 |
| E&O + cyber insurance | $800-1,500 |
| CPA (taxes + S-corp election advice) | $500-1,500 |
| Domain renewal | $10-30 |
| Plane subscription (existing) | ~$100 |
| Resend (likely free tier) | $0-200 |
| Cloudflare (free tier) | $0 |
| Backblaze B2 backups | $50-120 |
| Misc analytics + monitoring | $0-300 |
| Groq fallback (failover only) | ~$10 |
| **Total** | **~$6,075-8,265** |

**Year 1 break-even:** ~3-4 paying customers. Trivially achievable.

---

## Sequence (Solo Dev, ~13-14 Weeks)

1. **Weeks 1-2:** Security (CSRF, rate limiting, isolation audit, 2FA, audit log) + Cloudflare Tunnel + off-VM backups + DKIM/SPF/DMARC
2. **Week 2-3:** LLC + EIN + business bank + insurance + Termly setup + lawyer review (parallel with code work)
3. **Week 3-4:** Stripe + Stripe Tax integration + email verification hard gate + org invite flow + suspension flow
4. **Week 4-5:** Feature-flag off parcels/listings + email ingest cutover (file-only + hardening) + LiteLLM routing config + replacement reserves OpEx gap fix
5. **Week 5-6:** JSON export resurrection + scrub mode + in-app bug widget + GitHub issues integration + Copilot triage wiring
6. **Week 6-7:** Testing strategy — Scenario Library admin page + 8-10 MF scenarios + Playwright parameterization + Trace Viewer enabled + Hypothesis property-based invariants
7. **Week 7:** Beta env setup on separate LXC + deploy promotion flow
8. **Week 7-8:** **Style Guide + Agent Workbook** — `DESIGN.md` (seeded via Claude Design codebase ingestion) + Jinja2 macro library + `tokens.css` + CLAUDE.md directive + pre-commit hook + pattern catalog (prerequisite to UI Polish)
9. **Week 9-10:** **UI polish pass** — apply DESIGN.md conventions across all templates: terminology sweep + Deal Creation flow polish + empty/loading/error states + spacing/hierarchy + cross-page consistency audit
10. **Week 10-11:** Onboarding (demo seed leveraging Scenario Library subset + empty states + 3-5 Looms + foolproof friction points — partially overlapping with UI polish)
11. **Week 11-12:** Marketing surface (landing page + /pricing with MF + Commercial-waitlist tiers + /about + /features — uses Claude Design for hero visuals) + Plane support project + public roadmap + Commercial-tier waitlist capture
12. **Week 12-13:** Invite-only beta from waitlist, $0 for first 3-5 customers, gather feedback
13. **Week 13-14:** Fix top friction from beta cohort
14. **Week 14:** Open paid signups publicly (MF tier)
15. **+3 months post-launch:** publish open docs repo as press moment
16. **+Q3 2026:** Commercial + Mixed-Use tier ship ($300/seat, ~6-8 weeks dedicated work) — ships consistent UI from day one thanks to existing DESIGN.md

---

## Operational Posture Post-Launch

### Bug triage flow
```
in-app bug widget
  → POST creates GitHub issue with scrubbed JSON + logs + screenshot + URL
  → GitHub Action labels "bug-triage", assigns @copilot
  → Copilot coding agent posts triage comment (~5 min)
  → Steph reviews; accepts triage or escalates with "deep-triage" label
  → (optional) manual Claude Code run for deep-triage tickets
  → Fix locally → PR → deploy to beta → smoke → deploy to prod
  → Plane public issue link shared with customer for status
```

### Deploy flow (two-environment)
```
git push origin main
  → auto-deploy to beta LXC
  → smoke checks pass
  → manual tag + deploy to prod LXC (VM 114)
  → verify smoke checks
```

### On-call posture (solo)
- Plane public roadmap doubles as status communication
- Cost ceiling alerts catch runaway-bill incidents overnight
- Daily off-VM backups catch data-loss scenarios
- Cold-spare LXC standby on Proxmox = <1 hr restore time if VM 114 dies
- DR runbook written before launch, not during a fire

---

## Open Decisions (Pre-Launch)

1. **Free trial mechanics:** 14 days vs 30 days? Card up front yes/no? Auto-convert to paid?
   - Recommendation: 14 days, card up front, auto-converts
2. **Annual plan discount:** offer at launch or defer?
   - Recommendation: offer 20% off annual at launch (improves cash flow + reduces churn)
3. **Refund window:** 14-day full refund? 30-day? prorated cancellation mid-cycle?
   - Recommendation: 14-day full refund, no proration after that (industry standard)
4. **Grandfathering policy:** lock-in current price for existing customers when raising prices?
   - Recommendation: yes, indefinite grandfather for first 50 customers (good early-adopter signal)
5. **S-corp election:** form 2553 election to save self-employment tax?
   - Decision: defer to CPA conversation; election can be retroactive if filed by March 15 of following year
6. **Trademark filing:** federal trademark on "Viciniti Deals" (~$350 USPTO)?
   - Recommendation: do free USPTO TESS search now; defer paid filing until ~10 paying customers
7. **Pricing tier strategy:** single $200 tier, or introduce Starter/Pro/Enterprise tiers?
   - Recommendation: single $200 MF tier at launch + $300 Commercial tier on waitlist; revisit further segmentation at 25+ customers based on feedback
8. **Org-level billing:** add when?
   - Recommendation: defer until first customer with 5+ seats asks for consolidated billing

---

## Open Questions to Resolve

1. **Plane "One" tier features:** does it include email intake? Or use Cloudflare Worker → Plane API webhook fallback?
2. **AmEx exposure:** any sense of likely card mix among target B2B customers? Affects Stripe-vs-Stax future decision.
3. **Onboarding video stack:** Loom subscription needed ($15/mo for unbranded), or use free tier?
4. **Marketing site stack:** FastAPI-rendered, Cloudflare Pages static, or separate Next.js?
5. **DR target:** acceptable RTO (recovery time objective)? 1 hour? 4 hours? Affects whether cold-spare LXC is sufficient or need warm-standby with streaming replication.

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Cashflow engine bug causes customer financial loss | Low | Critical | E&O insurance + "not financial advice" disclaimer + extensive engine test coverage |
| Cross-tenant data leak | Low (post-audit) | Critical | Multi-tenant isolation audit (week 1) + audit log + 2FA |
| VM 114 hardware failure | Low | High | Daily off-VM backups + documented DR runbook + cold-spare LXC |
| Ollama hang blocks email ingest queue | Medium | Medium | Hard timeout + Celery time_limit + LiteLLM Groq fallback |
| Runaway-bill incident (Stripe/Resend/Groq/CF) | Medium | Medium | Cost ceiling alerts on every vendor |
| Stranger customer cannot self-onboard | High | Medium | Demo seed + empty states + Looms + foolproof top friction |
| Phishing or auth bypass | Low | Critical | CSRF + rate limiting + 2FA + hard email verification |
| Chargebacks from confused customers | Low | Medium | 14-day refund window + self-serve Customer Portal + clear ToS |
| Bot signups exhaust quotas | Medium | Low | Hard email verification + rate limiting on register + Cloudflare bot protection |
| Customer leaves due to missing feature | High | Low | Plane public roadmap + responsive support + NPS tracking |

---

## Deferred to Post-Launch (Month 1-3)

- Product analytics (PostHog free tier)
- NPS / churn tracking
- Centralized logging (Loki + Grafana, or Better Stack)
- Bookkeeping setup (Wave free, QBO, or Xero)
- Trademark filing (after USPTO search)
- Public docs open-source repo launch
- DPA template for B2B customers

## Deferred to Year 2+

- SOC 2 Type 1 (only if customer requires)
- Phase 2a/2b refactor (ui.py split, service layer)
- Parcel + listing re-enablement (when paid data subscriptions justified)
- Org-level billing
- International / EU pricing (would trigger Paddle reconsideration)
- HelloData and other paid enrichment

---

## Success Metrics

### Launch (week 0-12)
- 3+ paying customers signed up via self-serve (no personal onboarding)
- Zero security incidents
- Zero cross-tenant data leaks
- <5% trial-to-paid drop-off due to onboarding friction (target measured via PostHog funnels post-launch)

### Year 1
- 20-50 paying customers
- <10% monthly churn
- Net Promoter Score >40
- Year-1 revenue >Year-1 costs

### Year 2 ceiling
- 100 paying customers (~$240k ARR)
- Re-evaluate scope, scale, pricing, hardware

---

## References

- [docs/feature-plans/beta-to-1.0-refactor.md](beta-to-1.0-refactor.md) — pre-existing refactor plan (Phase 1 security items merged into this launch plan; Phase 2 deferred indefinitely)
- [docs/feature-plans/argus-cre-schema-improvements.md](argus-cre-schema-improvements.md) — Q3 2026 commercial readiness work (non_recoverable_pct, market_rent_monthly rename, vacancy/occupancy label flip)
- [docs/FINANCIAL_MODEL.md](../FINANCIAL_MODEL.md) — math reference (proposed public publication)
- [CLAUDE.md](../../CLAUDE.md) — project conventions
- Memory: launch-monetization context as of 2026-05-24
