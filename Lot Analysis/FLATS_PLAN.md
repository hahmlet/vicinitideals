# FLATS — Fitment, Land, and Tolerance Screening

**Owner:** Stephen Ketch · East County Housing (Rockwood CDC)
**Status:** planning · supersedes the "Pod Screen" spec and the `quadfit/` prototype
**Home:** inside `vicinitideals` — shared database, separate service
**Last updated:** 2026-08-12

---

## 0. What changed from the Pod Screen spec

The Pod Screen spec was written without knowledge of this environment and assumed
greenfield. It is not greenfield: `Lot Analysis/quadfit/` is a working 7,155-line
pipeline with 18 jurisdictions encoded and a full Multnomah + Clackamas run on disk.

FLATS keeps quadfit's *proven logic* and replaces its *structure*. Five decisions
override the original spec:

| Pod Screen said | FLATS does | Why |
|---|---|---|
| Build stages 0–10 fresh | Port quadfit's s0–s7 logic into the new package | The geometry works and is tested; only packaging and coverage are wrong |
| Permit back-test is the go/no-go gate (≤10% false negatives) | Back-test is a **diagnostic**, not a gate; filtered to post-HB-2001 permits only | Historic buildings were approved under superseded code. Wrong yardstick for a screen encoding today's rules |
| Rule files flat per jurisdiction | **State → County → City/Unincorporated** hierarchy, keyed on Census GEOID | Counties get added over time. Flat naming collapses the moment two states have a "Springfield" |
| Slack is an output | Slack is **reported always** and **tolerated configurably** | Two different things: the margin you record, and how much failure you forgive |
| Standalone app, own LXC | **Inside vicinitideals** — shared DB and auth, separate service | The FLATS→Opportunity→Deal handoff is the point. Shared DB makes it a foreign key, not an integration |

**The thesis: encoding is where this project lives or dies.** Geometry is a few hundred
lines and already works. Rule encoding and its verification are the entire risk surface,
and get the majority of the engineering.

---

## 1. Standards alignment

Two distinct layers. Do not conflate them.

### Layer 1 — data schema (what fields, what shape)

| Standard | Granularity | Status | FLATS verdict |
|---|---|---|---|
| **OZFS** (Open Zoning Feed Spec) — Harvard GSD + Cornell Tech | Parcel | Research-stage, no public repo found | **Shape toward it.** Explicitly scoped to missing middle + small-scale infill = our exact domain. GTFS-modeled. Adopt if mature, mirror if not |
| **National Zoning Atlas** — Cornell (Bronin) | District, ~200 fields | Mature, human-coded, no Oregon | **Field list as encoding checklist only.** Not a source of truth |
| **zoning.space** | Zone specfiles | Dormant, CA-only | Read the specfile format. Take nothing else — its README disclaims parcel-level use |
| **Zoneomics / Regrid** (commercial) | Zone polygon + attributes | Sold county-by-county | Audit fill rate before paying. Expect `-5555` sentinels wherever standards vary by housing type *within* a zone — exactly our case |

**Practical rule:** our field names live in one module (`rules/schema.py`) with an
`ozfs_map.yaml` beside it. When OZFS publishes, migration is a mapping file, not a
refactor. Do not guess OZFS field names now.

**NZA as a gap-finder.** Its ~200 fields answer "what standards exist that we never
thought to encode." Quadfit's own blind-spot list already names several — Gresham and
Fairview *maximum* front setbacks, Gresham 15% private open space, Wood Village 5/12
roof pitch, Portland maintained-street-frontage and visitability, alley setback
reductions. Run the NZA list against our schema and every unmatched field becomes a
backlog row instead of a surprise.

### Layer 2 — rule encoding (how text becomes logic)

**Runtime format: plain versioned YAML DSL + decision tables.** Fast to write, diffable,
debuggable, reviewable by a human who is not a programmer.

**Not LegalRuleML.** It is a real OASIS standard with genuine advantages — defeasibility
models state-preempts-local natively, deontic operators separate required / permitted /
prohibited. But it is verbose XML, picks no reasoner, and reported extraction accuracy is
poor (~48% F1). We have **one housing type across ~18 jurisdictions**, not a general
automated-code-compliance platform. Escalate only if we start writing rules *about* rules
— that is the signal flat rules have failed.

### RASE tagging — the extraction discipline

Every clause of code text gets tagged as exactly one of:

| Tag | Meaning | Zoning example |
|---|---|---|
| **A** — Applicability | When does this clause apply at all | "In the R5 zone" · "for a fourplex" |
| **S** — Selection | Which subset within applicability | "on a corner lot" · "where the lot exceeds 10,000 sq ft" |
| **R** — Requirement | The normative constraint itself | "the front setback shall be at least 10 feet" |
| **E** — Exception | Negates or overrides a requirement | "except where an alley abuts the rear lot line" |

RASE maps onto zoning almost too cleanly, and provenance becomes *structural* — a rule
stays tied to its source clause because the tag lives on the clause.

**The reason this matters is completeness, not tidiness.** Tag every sentence in a code
section and you can assert coverage: 100% of §33.110.220 is accounted for as A/S/R/E or
explicitly marked non-normative. **Any unclassified sentence is a gap** → the zone drops
to REVIEW until someone resolves it. That converts "did we miss an exception?" from a
worry into a query.

Silent omission is the failure mode that already cost this project 40,500 lots (§2). The
clause ledger is the control for it.

---

## 2. The encoding problem, stated plainly

Quadfit's current encoding is **insufficient** and is being redone. Three failures:

**1. Silent omission.** Any zone with no rule row is dropped into `zone_not_in_rules` and
disappears. That bucket holds 88,947 lots — 31% of the universe and the single largest
constraint by 4.6×. Inside it:

| zone group | lots | developable | p25 $/door | ≤$45k/door | verdict |
|---|---:|---:|---:|---:|---|
| *R5/R7 — encoded baseline* | *108,258* | *103,588* | *$113,399* | *1,199* | *reference* |
| Portland **RM1 / RM2** | 32,425 | 19,832 | $106,217 | 303 | **IN — Phase 1, same track** |
| Portland RM3 / RM4 / RX | 8,140 | 1,867 | $124,010 | 32 | IN, low priority |
| Portland CM1 / CM2 / CM3 | 13,501 | 9,095 | $116,429 | 300 | REVIEW-only track |
| Portland CX / CE / EX | 19,951 | 3,821 | $139,458 | 150 | Encode as REVIEW, no rule detail |
| Gresham MDR-PV / HDR-PV, misc | ~1,000 | — | — | — | IN — Phase 1 |
| industrial, open space, true non-residential | ~14,000 | — | — | — | out of scope |

*Developable = ≥2,000 sqft with a real assessed value. $/door assumes 4 doors at county
RMV, the same basis as quadfit's `acq_estimate`.*

Nobody decided to exclude 40,500 of Portland's densest lots. Nobody wrote the rows, and
the pipeline had no way to say so. Reasoning behind each verdict is in §12.

**2. Provenance too coarse.** Citation lives on the zone row, not the value. One
`source_url` covers eight numbers pulled from four different code tables. Unverifiable in
practice — a reviewer cannot check a setback without re-deriving which table it came from.

**3. No drift detection.** `retrieved:` dates exist but nothing re-checks them. A code
amendment silently invalidates an encoding and the pipeline keeps reporting green.

### The value standard

Every encoded value is an object carrying its own proof, tied to a RASE-tagged clause:

```yaml
setback_front_ft:
  value: 10
  clause: pdx-33.110.220-t110-4-r03      # → clause ledger entry, RASE tag R
  cite: "PCC 33.110.220, Table 110-4"
  url: "https://www.portland.gov/code/33/100s/110"
  quote: provenance/or/multnomah/portland/33.110-table-110-4.txt#L42-L48
  retrieved: 2026-08-12
  status: verified          # draft | encoded | verified | stale
  reviewer: sjk
  reviewed: 2026-08-14
```

Verbosity is the point. Mitigated by inheritance — a zone declares a `cite_default:` block
covering the common case, and individual fields override only when they come from a
different table. Cuts roughly 80% of the repetition without losing per-value traceability.

**Status lifecycle, enforced by the loader:**

```
draft ──(human confirms against quote)──> verified
  │                                            │
  │  extraction output                         │  source text hash changed
  │  NEVER enters a production run             ↓
  └──────────────────────────────────────── stale ──> re-verify
```

`draft` and `stale` values are loadable but poison their zone: any lot in that zone routes
to REVIEW with `RULE_UNVERIFIED`, never GREEN, never RED.

### Absence is explicit, never inferred

A zone that prohibits fourplexes must say so **with a citation**:

```yaml
quadplex_allowed:
  value: false
  cite: "PCC 33.110.200, Table 110-2"
  ...
```

A zone simply *missing* from config is `ZONE_NOT_ENCODED` → REVIEW → and appears on the
coverage backlog. Never silently dropped, never treated as prohibited. This one rule would
have surfaced the 40,500 RM lots on day one.

### Two ledgers

**Coverage ledger** — *which zones are missing.* Every run enumerates every
`(state, county, jurisdiction, zone)` pair **present in the GIS data**, joins against
encoded rules, writes `coverage.csv`:

| column | meaning |
|---|---|
| geoid, jurisdiction, zone | the pair |
| lots, acres | how much inventory rides on it |
| status | encoded / draft / stale / **missing** |
| verified_fields, total_fields | encoding completeness |
| blocking | lots that would leave REVIEW if this row were verified |

Sorted by `blocking` descending, this **is** the encoding work queue — generated, not
hand-maintained.

**Clause ledger** — *within an encoded zone, which sentences of code are unaccounted for.*
One row per code clause: source ref, RASE tag, the value or predicate it produces, and
whether it is resolved. Unresolved clauses block the zone from `verified`. This is the
RASE completeness check from §1.

Coverage ledger catches "we never looked at this zone." Clause ledger catches "we looked
but missed the exception." Both are needed; neither substitutes for the other.

### Drift watch

Nightly Celery beat job re-fetches each distinct `url:`, hashes the extracted text,
compares to the hash stored at `retrieved:`. Change → every value citing that URL flips to
`stale` → its zones drop to REVIEW → coverage ledger surfaces it. Code amendments become a
visible work item within 24 hours instead of a silent false green.

### How rows get made

Three lanes, in order:

1. **Extract** — LLM-assisted first pass over fetched code text, producing RASE-tagged
   clauses and `status: draft` values, each with the excerpt it derived from. Fast, wrong
   sometimes, never trusted. NZA (500+ trained human contributors) and the Urban Institute
   both concluded automated parsing cannot hit the required accuracy. This lane saves
   typing, not judgment.
2. **Verify** — human reads the quote beside the extracted value and approves, edits, or
   rejects. CLI first (work starts immediately), web tool second (§6). Queue ordered by
   `blocking` lots, so the highest-leverage rows get reviewed first.
3. **Watch** — drift detection above.

**A silent encoding error fails identically across all 40,000 parcels at once.** The
golden test suite is the only control that catches it. Commit golden results with every
rule-set change.

---

## 3. Municipal hierarchy

```
flats/config/jurisdictions/
  or/                                   # state — ORS/OAR preemption layer
    _state.yaml                         # OAR 660-046, ORS 197A.400 clear-and-objective
    multnomah/
      _county.yaml                      # applies to all cities in county
      _unincorporated.yaml              # county code — rural/unincorporated only
      portland.yaml
      gresham.yaml
      ...
    clackamas/
      ...
```

**Plain slugs, no GEOID prefix.** An earlier draft prefixed directories with the Census
GEOID (`41051-multnomah/`), which put an identifier in the one place nothing validates it
— a typo there is invisible until a join silently returns nothing. The GEOID is joined
from the TIGER places layer at ingest and stored in the layer's `ingest.geoid` field, where
it can be checked. Paths are for humans; the layer id is the path (`or/multnomah/portland`).

**Resolution order — most-specific-wins:**

```
OAR 660-046 (state)  →  county  →  city base zone  →  overlay  →  bonus
```

Every resolved value carries the layer it came from. A lot detail page therefore shows
*"front setback 10 ft — Portland 33.110 Table 110-4"* next to *"parking 1/unit —
OAR 660-046-0220 (state, preempts city 2/unit)"*. Provenance survives resolution. This is
what makes the system auditable end to end.

**Adding a county** = one directory, one `_county.yaml`, N city files, plus GIS sources in
`config/pipeline.yaml`. No code change. Washington County next (RLIS already covers it).

**Jurisdiction toggles stay cheap.** On/off is a policy flag applied at report time from
stored columns — seconds, not a full re-run. Hard constraint on the rewrite, inherited from
quadfit's structural/policy split, and the reason that split exists.

---

## 4. Slack — configurable

Two distinct concepts, deliberately separate:

**Report slack** — the margin on every check, recorded always, even on passes. *"passes
coverage by 340 sqft"*, *"fails front setback by 1.4 ft"*. Costs nothing; every check
already computes it. Feeds ranking and the design sweep.

**Tolerance** — how much failure is forgiven before a check counts as failed. A policy
knob, not a measurement.

```yaml
# flats/config/slack.yaml
report: always                # every check, every lot, pass or fail

tolerance:                    # within this margin -> REVIEW, not RED
  setback_ft:          0.0
  fit_ft:              0.5    # raster is conservative to +/-1 cell
  coverage_pct:        0.0
  min_lot_area_sqft:   0
  min_frontage_ft:     0.0
  slope_pct:           2.0    # 3 ft DEM noise floor

overrides:                    # per-jurisdiction, most-specific wins
  or/multnomah/portland:
    fit_ft: 0.25
```

**Tolerance never manufactures a GREEN.** A check inside tolerance moves RED → REVIEW,
never → PASS. That is the recall bias the project runs on: a false red silently deletes an
acquisition target and nobody learns it existed, while a false green costs one review.
Exclusion has to be unambiguous; inclusion only has to be plausible.

Both are report-time — seconds to re-run. Sweeping tolerance to find where lot counts move
is a first-class operation, not a rebuild. Implemented in `flats/score/slack.py`.

---

## 5. Design catalog — many pods, not one

A screen that only answers for one building is a screen with a one-building shelf life.
The catalog is a first-class entity from day 0.

### What a design costs

The trick is already latent in quadfit: **design-independent facts are computed once;
only design-dependent results fan out.**

| Computed once per lot — free across all designs | Fans out per (lot × design) |
|---|---|
| Buildable envelope (setbacks, carves, overlays) | Site plan: parking layout, driveway, open space |
| **Fit frontier** — max depth per width, every orientation | Set access: crane reach, truck route, module size |
| Slope, sewer, frontage class, lot type | Non-rectangular footprints (L-shape, courtyard) |
| Owner propensity, acquisition economics | |

The frontier is the load-bearing piece. Quadfit already stores, per lot, the deepest
rectangle that fits at each width — so **any W×D rectangle is a lookup, not a re-run.**
Design #11's fit result is a table join. Scalar checks (coverage, FAR, height, density)
are arithmetic at report time and equally cheap.

Only site plan and set access genuinely scale with design count, and only those two
stages. Ten designs ≈ 10× those stages, ~1× everything else.

Storage: 300k lots × 10 designs = 3M result rows. Trivial for Postgres.

### Cost of building it in vs. retrofitting

| | Cost |
|---|---|
| Built into Phase 0 schema | ~1 week across schema + views |
| Retrofitted after Phase 3 | Schema migration + rewrite of every view + full re-run. 3–4 weeks |

**And it is not new scope.** The plan already carried a design sweep (Phase 6). The
catalog *is* that infrastructure — this promotes the data model earlier and makes it a
product surface instead of an offline analysis.

### Shape

```yaml
# config/pods/base_36x60.yaml
id: base_36x60
version: 3
label: "Base pod — 4 × 9ft units"
typology: townhome_rear_court        # drives which site-plan generator runs
footprint: {width_ft: 36, depth_ft: 60}
stories: 2
height_ft: 26
parking: {stalls_per_unit: 1.5, config: rear_court}
delivery: {method: panelized, module_max_width_ft: 14, crane_required: false}
status: active                       # active | archived — archived stays queryable
```

`flats.designs` holds the catalog. `flats.lot_results` is keyed
`(lot_id, design_id, run_id)`. `flats.lots` holds only the design-independent facts.

### Product surface

- **Per-lot:** which designs fit, ranked by slack. "This lot takes design B or D."
- **Per-design:** lots unlocked, median slack, binding-constraint histogram.
- **Compare:** N designs side by side over the same lot set — the "which design green-lights
  the most lots" question, answered in the browser.
- **Best-fit rollup:** each lot carries its best design + tier so map and list views stay
  one-row-per-lot.

Designs are **versioned and immutable once run** — bump `version` rather than editing, so
a run's results stay reproducible and two runs stay comparable.

### Where it stops

Arbitrary runtime geometry is out. The catalog is a curated set evaluated in batch, and a
new design means a re-run of the two design-dependent stages. That is the deliberate line
between this and a generative design tool.

---

## 6. Home — inside vicinitideals

**Shared database and auth, separate service.**

| Concern | Decision |
|---|---|
| Repo | Same repo. `flats/` pipeline package + `app/flats_web/` routers |
| Runtime | New `vicinitideals-flats` container in the VM 114 compose stack. **Not** a new LXC |
| Database | Same Postgres, **plus the PostGIS extension** |
| Auth | Existing session + org scoping. No second auth system |
| Queue | Existing Celery `analysis` queue |
| Deploy | Existing `deploy-vicinitideals.sh`. One deploy, one backup, one monitoring surface |
| Mount | `/flats` path first (session cookie just works). `flats.viciniti.deals` later if wanted — needs cookie scoped to `.viciniti.deals` |

### Why a separate container, not new routes on the API

- **Dependency weight.** shapely + rasterio + pyproj + geopandas are heavy. Keep them out
  of the API image, which has to restart fast.
- **Blast radius.** A FLATS bug must not 500 the model builder.
- **Cheap to collapse, expensive to split.** Merging two containers later is an afternoon.
  Splitting a fused monolith is not.

### Why shared DB is the whole argument

Whatever the eventual handoff is, it lives in one database. `Opportunity → Project → Deal
→ Scenario` already exists and `convert_listing_to_project` is a precedent for promoting
an external record into it — but **the FLATS→financial seam is deliberately undecided.**
Promoting to an Opportunity is one candidate; a FLATS-native record the wizard reads, or a
thinner link, are others. That choice gets made once the FLATS data model is real.

What matters now: shared DB keeps every option open and costs nothing. Standalone would
force us to pick the seam early *and* build a sync layer for it.

### PostGIS

Prod runs plain `postgres:16`. The `postgis/postgis:16-3.x` image is built on the same
postgres:16 base, so the data directory is compatible: swap the image, then
`CREATE EXTENSION postgis` in an Alembic migration. **Ship it as its own change with
nothing else in it, backup first.**

Alternative if we want to defer: store WKB in `bytea` and do all geometry in Python
(quadfit already stores WKB in parquet). Cost is no spatial index and no `ST_AsMVT` tile
serving — the map ships GeoJSON, which gets unpleasant at 300k lots. **Take PostGIS.**

### Naming guardrail — this is the successor, not a revival

Migration 0113 (2026-06-14) irreversibly dropped 446K rows from `parcels`, deleted the
county-GIS scrapers and the Map, and two follow-up crumb sweeps ran *specifically* so
agents would stop believing parcels still exist. The stated reason was that the parcel
pipeline never worked — wrong jurisdiction tags, lookup-only rather than batch-fed.

FLATS is the version that works: batch-fed, validated, already run at scale. But it must
be **unmistakable in the schema** or every future session re-fights this:

- **FLATS owns a Postgres schema, not a table prefix.** `flats.lots`, `flats.designs`,
  `flats.lot_results`, `flats.rules`, `flats.clauses`, `flats.runs`,
  `flats.review_decisions`. App tables stay in `public`. A real namespace makes the
  product boundary structural rather than a naming convention — and makes the §6 firewall
  visible in the schema itself. **Never `parcels`, never `public.lots`.**
- `docs/DATA_MODEL.md` Archive section gets a forward pointer: *"the dropped `parcels`
  table is not FLATS; FLATS replaces it — see Lot Analysis/FLATS_PLAN.md."*
- `CLAUDE.md` gains a FLATS section stating the repo now holds two products.

### Web views

| View | Contents |
|---|---|
| **Map** | Vector tiles via `ST_AsMVT`, lots colored by triage. Leaflet or MapLibre. Click → lot detail |
| **Lot detail** | Every check: value, threshold, slack, pass/fail, **and the citation the threshold came from**. Site plan where generated. Acquisition economics. Owner propensity. Promote-to-Opportunity button |
| **Filters / saved views** | Jurisdiction, zone, triage, binding constraint, slack range, lot size, land cost per door, propensity. Saved and named |
| **Review queue** | `triage == review`, ordered by value. Reviewer marks green/red with a reason. **Decisions persist across pipeline re-runs**, keyed on TLID |
| **Rule verification queue** | Side-by-side quoted code text ‖ RASE-tagged clauses ‖ extracted values ‖ approve / edit / reject. Ordered by blocking lots. The tool that unblocks production |
| **Coverage dashboard** | Both ledgers from §2 — missing zones ranked by lots, unresolved clauses per zone, per-jurisdiction data grades, stale-rule alerts |
| **Run history** | Every run versioned. Diff two runs: which lots changed tier, and which rule change caused it |
| **Reports** | Binding-constraint histogram, design-sweep curves, exportable candidate lists |

**Durable review decisions.** A human verdict must outlive the run that prompted it.
`flats_review_decisions` keyed on TLID + check, replayed into every subsequent run, with
reviewer, date, and reason carried forward. Without this the queue resets every run and
nobody works it.

---

## 7. Firewall — the financial engine is untouchable

**No FLATS change may modify any of these paths.** Enforced by a CI check that fails any
FLATS-scoped change touching the protected list.

```
app/engines/**                     # all 24 modules — cashflow, waterfall, draw,
                                   #   underwriting, sensitivity, interest, newton_solve,
                                   #   dev_fee, float_earnings, tax_credit_delivery, ...
app/models/deal.py                 app/models/capital.py
app/models/scenario.py             app/models/milestone.py
app/models/cashflow.py             app/models/capital_draw_event.py
app/schemas/capital.py             app/schemas/deal.py
app/exporters/**
app/api/routers/ui_model_builder.py    app/api/routers/ui_model_outputs.py
app/api/routers/capital.py             app/api/routers/scenarios.py
tests/engines/**                   tests/e2e/test_phase_b_debt.py
```

The FLATS↔financial seam is one-directional whatever shape it takes: FLATS produces, the
financial side consumes. Nothing in `flats/` imports from `app/engines/`.

---

## 8. Vestige removal (authorized)

**Remove and replace:**
- `Lot Analysis/quadfit/` → rewritten as `flats/`. Delete the old tree once parity is proven.
- Stale parcel/GIS references in `docs/` that describe removed features as if live —
  `DATA_MODEL.md` Archive, `PROJECT_OVERVIEW.md`, `beta-to-1.0-refactor.md` parcel sections.
  Replace with forward pointers to FLATS.
- `Opportunity.jurisdiction` — kept in June with no real source. FLATS gives it an
  authoritative one; repoint it to the FLATS jurisdiction resolution.

**Audit before touching (may be live):**
- Deferred June scraps: `OpportunitySource.loopnet` enum, `Broker.loopnet_broker_id`,
  HelloData columns, `RecordType.parcel`. Steph's June call was "leave alone." Re-confirm
  before removing.

**Confirmed KEEP — do not remove:**
- `app/models/map_polygon.py` + `map_polygons` — **live and reusable.** Read by
  `app/scrapers/geo_utils.py` for Crexi scraper filters. FLATS reuses it directly for
  study areas, market boundaries, and geographic jurisdiction toggles instead of adding a
  parallel polygon store.
- `app/scrapers/dedup.py`, `apn_utils.py`, `geo_utils.py` — the Crexi pipeline calls these.
- `Opportunity.apn` / `apn_normalized` / `lat` / `lng` — dedup uses them.
- `app/engines/market.py` — KNN comps.

---

## 9. Package layout

No `src/` layer — the package is importable from the repo root (`pythonpath = ["."]`
in pyproject), which keeps `python -m flats.encode.backlog` working without an install
step. Directories marked ✅ exist.

```
flats/                             # pipeline (offline, heavy GIS deps)
├── config/
│   ├── pipeline.yaml              # data sources per county
│   ├── slack.yaml                 # §4
│   ├── pods/                   ✅ # design catalog — one YAML per pod
│   └── jurisdictions/or/...    ✅ # §3 hierarchy, 19 layers / 96 zones
├── provenance/or/...              # quoted code text, hashed
├── rules/                      ✅ # fields, model, loader, resolver, ledger
├── designs/                    ✅ # catalog model + loader (§5)
├── encode/                     ✅ # port_quadfit, backlog; RASE extraction and
│                                  #   drift watch land in Phase 1
├── normalize/                  ✅ # condo/air-parcel detector (§12)
├── ingest/  frontage/  envelope/
├── fit/     scalar/   parking/  access/
├── propensity/  score/  sweep/
├── io/                            # parquet cache + PostGIS writer
└── tests/                      ✅ # 113 tests, runs in the CI light gate

app/flats_web/                     # FastAPI routers + templates, own container
app/models/flats.py             ✅ # flats.runs, flats.designs, flats.lots,
                                   #   flats.lot_results, flats.rules,
                                   #   flats.clauses, flats.review_decisions
scripts/check_flats_firewall.py ✅ # §7, runs in CI
```

**Table names are schema-qualified, not prefixed** — `flats.lots`, never `flats_lots`.
An earlier draft of this section said otherwise; §6 is the decision.

---

## 10. Build order

### Phase 0 — Foundation

| | |
|---|---|
| ✅ | Rule model with per-value provenance and a `draft → verified → stale` lifecycle |
| ✅ | State→County→City config tree, loader, resolver with `preempts` |
| ✅ | Coverage ledger + clause ledger (§2) |
| ✅ | Condo / air-parcel detector (§12) |
| ✅ | Firewall script + CI check (§7); naming guardrails and doc forward-pointers |
| ✅ | Port of all 96 quadfit zone rows — **all demoted to `draft`**, none inherit trust |
| ✅ | Generated encoding backlog: 150 observed pairs, 236,558 lots, 100% blocked |
| ✅ | Design catalog (§5) — versioned, immutable, two pods shipped |
| ✅ | PostGIS (migration 0124, its own change) and the `flats.*` schema (0125) |
| ✅ | `provenance/` store — quoted code text, hashed; staleness derived, never stored |
| ✅ | `config/slack.yaml` (§4) and the slack/tolerance policy |
| ✅ | `geom/` — edge classification and the buildable envelope |
| ✅ | `fit/` — 0–180° rotation sweep, rasterizer, fit-with-a-margin (Phase 2 pulled forward) |
| ✅ | `score/screen.py` — GREEN/REVIEW/RED with split attribution (tightest vs dominant) |
| | Ingest: `config/pipeline.yaml` (data sources per county) and the acquire/normalize/assign stages |

**On "100% blocked".** That is the correct reading of the first ledger, not a
regression. Every ported value is `draft` by design, so no zone can produce GREEN until
verification runs — which is Phase 1, and is the point.

*Exit: pipeline reproduces quadfit's numbers, everything in REVIEW pending verification,
backlog visible, financial engine provably untouched.*

### Phase 1 — Encoding engine ← **the project**
RASE extraction harness. Provenance store with text hashing. Drift watch. Verification CLI.
NZA field-list gap audit. Then encode by lots-blocked: Portland RM1–RM4 and RX first
(~40,500 lots), then Gresham MDR-PV/HDR-PV, then remaining residential zones across all 18
jurisdictions, then re-verify the 96 ported rows.

*Exit: every residential zone in Multnomah County encoded and verified; zero missing
residential rows; zero unresolved clauses in verified zones.*

### Phase 2 — Geometry and scoring — **landed early, in Phase 0**

Built alongside the foundation rather than after it, because the encoding work in Phase 1
needs something to feed. Shipped: the 0–180° sweep (folded from 360° — a rectangle is
unchanged by a half turn), the conservative rasterizer, slack on every check with
configurable tolerance, minimum density, height, FAR, coverage curves, parking, and reason
codes. Still open: edge-aligned candidate angles and a vector inner-fit path as a faster
alternative to rasterizing, plus the site-plan generator (parking, access) from quadfit s6s.

### Phase 3 — Web
`vicinitideals-flats` container, PostGIS writer, map, filters, lot detail. Rule
verification queue. Review queue with durable decisions. Coverage dashboard.
**Design comparison views** (§5): per-design lots-unlocked, per-lot which-designs-fit,
N-way compare, best-fit rollup.

### Phase 4 — New stages
Stage 8 prefab set access (truck route, crane footprint, overhead lines, staging, grade).
Stage 9 owner propensity (absentee, entity type, tenure, equity proxy, improvement-to-land
ratio). Both genuinely new — no quadfit equivalent.

### Phase 5 — Handoff
Decide and build the FLATS→financial seam (§6). Candidates: promote to Opportunity, a
FLATS-native record the wizard reads, or a thinner link.

### Phase 6 — Expansion
Automated design sweep over the catalog: pod dimensions vs lots-unlocked curve, marginal
lots per inch. Washington County. Then outward.

---

## 11. Conventions

- No unsourced numbers. Every value carries `clause`, `cite`, `url`, `quote`, `retrieved`.
- Every code clause carries a RASE tag. Unclassified text blocks the zone from `verified`.
- `draft` and `stale` values never produce GREEN or RED. Only REVIEW.
- A missing zone is `ZONE_NOT_ENCODED` → REVIEW → coverage backlog. Never a silent drop.
- Explicit failure over silent default. Never fall back to a "typical" setback.
- Log slack on every check, always, including passes.
- Raw ingested data is immutable. Every stage output reproducible from raw + config.
- Jurisdiction toggles and policy knobs are report-time only — seconds to re-run.
- Golden test results committed with every rule-set change.
- Every geometric operation gets a unit test with a hand-drawn polygon fixture.
- Nothing in `flats/` imports from `app/engines/`.

---

## 12. Action items and open questions

**Action items (external, start now — they gate design):**
1. **Contact the Open Zoning team re: OZFS maturity + public schema.** Entry point Paul
   Salama (EIR, ex-Envelope employee #1). We are the use case their spec is written for —
   a real infill builder with a real pipeline. Their answer decides adopt vs mirror.
2. **Audit Regrid / Zoneomics fill rate** on setback and FAR for Multnomah + Clackamas
   *before* any purchase. Check the `-5555` sentinel rate specifically.
3. **Pull the NZA field list** as an encoding checklist and diff against our schema.

**Resolved — Portland mixed-use and multi-dwelling (evaluated 2026-08-12):**

*Multi-dwelling* **RM1/RM2 are IN, Phase 1, same track as R5/R7.** 19,832 developable lots
with economics indistinguishable from the encoded baseline (p25 $106k/door vs $113k;
303 lots under the $45k ceiling vs 1,199 on a base 5× larger). Straight residential — no
ground-floor active-use requirement, no design overlay by default, fourplex is a
conforming use. Largest single win available.

*RM3/RM4/RX are IN but low priority.* Only 1,867 of 8,140 are developable — 75% are under
2,000 sqft, i.e. condominium air parcels and downtown slivers. Three more zone rows, cheap
to add, small payoff.

*Mixed-use* **CM1/CM2/CM3 get a REVIEW-only track, not GREEN.** The economics genuinely
work — 9,095 developable lots, p25 $116k/door, statistically the same as the baseline,
which surprised me. But these zones carry ground-floor active-use and window standards and
commonly sit in design-overlay (`d`) districts, which means **discretionary design review**.
That is precisely what ORS 197A.400's clear-and-objective guarantee does not cover, and
what §9 routes to a human. An automated screen cannot produce a defensible GREEN there.
Encode them, cap them at REVIEW, work them as a queue.

**CX/CE/EX are effectively out.** Worst economics (p25 $139k/door), only 3,821 of 19,951
developable, and the heaviest design-review exposure. Encode a single citation-backed
`review` verdict so they leave `ZONE_NOT_ENCODED`, and stop there.

**Bug surfaced by this analysis — condo/air parcels are not being caught.** 75% of
RM3/RM4/RX and 80% of CX/CE/EX "lots" are under 2,000 sqft, yet `stack_count > 1` flags
**0.0%** of them and the funnel reports `condo_stack: 0 dropped`. Quadfit's dedupe looks
for coincident geometry stacks; these are distinct small air parcels and slip through.
They inflate every count in those zones. Needs a different detector (`PROP_CODE` /
`STATECLASS`, or area vs `BLDGSQFT` ratio). **Phase 0.**

**Open questions:**
1. Which jurisdictions publish **recorded easements**? Determines where the screen can ever
   produce a hard GREEN rather than REVIEW.
3. Panelized vs volumetric prefab — locks the transport envelope and the pod width ceiling.
4. Which funding sources are BOLI prevailing-wage-exemption safe? Sets the cost target,
   which sets the viable pod design.
