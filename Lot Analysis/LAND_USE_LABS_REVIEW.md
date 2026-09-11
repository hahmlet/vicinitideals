# Land Use Labs, and what the zoning-AI paper says we should fix

Research note, 2026-09-11. Not a procurement evaluation — Land Use Labs covers
Portland proper, which FLATS already encodes, so in our footprint they are a
strict subset of us. This reads their published schema for *method*, reads the
paper they link for *critique*, and scores FLATS against both.

**Handling note.** The paper (Bronin, *Keeping AI in Its Zone*, Yale L. & Pol'y
Rev., expected 2027) is watermarked **DO NOT CITE WITHOUT PERMISSION**. Its
findings are summarised here for internal use and are not quoted. Nothing from
it should be reproduced outside this repo without asking the author.

**Sourcing note.** `landuselabs.com` is egress-blocked from the session this was
written in. Everything below about their *schema* comes from their published
data dictionary, which I read. Product and pricing claims come from web search,
not from the site.

---

## 1. What they are

Land Use Labs is the commercial arm of the National Zoning Atlas — Sara Bronin's
manually-coded, district-level dataset, ~200 fields, 500+ trained human coders.
FLATS_PLAN §1 already names NZA as "field list as encoding checklist only. Not a
source of truth," and `FieldDef.nza` implements that: 21 of our 50 fields carry
an NZA counterpart.

They sell four products: Parcel Reports, Districts, Slices, and Rasters, plus
pre-aggregated Zoning Tables at five geographies. Marketing claims 96M+ parcels
nationally. Read that against the paper's own number — 11,200 of 33,296
jurisdictions fully analysed — and "a parcel report is available" is not the same
claim as "this jurisdiction has been analysed."

## 2. What their schema reveals about their method

Three things worth knowing.

**The "slice."** Their unit of analysis is not the district. It is the polygon of
a unique *base district + overlay combination*. That is a real modelling
decision and it is one we have not made: FLATS resolves state → county → city and
has **no overlay layer at all** (`resolver.py`'s docstring promises one; grep the
module and `overlay` appears only in that docstring). We flatten overlays into
unanswerable site facts instead — `civic_corridor`, `hillside_or_resource_overlay`,
`willamette_historic_district` — each with evidence "none held," so the lot comes
back UNKNOWN. That is a *refusal* defence, not a modelling one. It is correct and
it is not the same thing.

**Four columns per number.** Every numeric standard ships as
`field` / `field_min` / `field_max` / `field_method`, where `_method` ∈
`direct_number | estimation | indeterminate | not_applicable`, with `-1` as the
indeterminate sentinel. Two observations:

- The `_method` enum is the same idea as our `Status` lifecycle plus `exempt` /
  `unless` / `qualified_by` / `Wanted` — an explicit taxonomy of *why there is no
  number*. `refusals.py`'s own docstring says the durable fix for a declined
  standard "is a declared field on the model." They declared it. Convergent
  design, independently reached, and worth noting as corroboration that the
  taxonomy is the right shape.
- But their taxonomy is **four values wide and ours is nine** (see §4). Where we
  distinguish "the code was read and states no such standard" from "this layer
  stands down" from "the rule moves and we can't say how," they have one
  `indeterminate`.

**The Abbreviations Guide is the tell.** Their Districts and Parcel Reports type
every numeric field as `character`, not numeric, and the guide explains why: the
cell holds a micro-DSL, e.g. `1 w/sewer; 3 w/out`, `2/2br; 1/add'l br`,
`0.5/elderly`, `30' + 1' add'l ft in height/add'l ft in side yard over 10'`.
Conditional regulations are preserved **as strings a human must read**, and the
Slices sheet's `_min`/`_max`/`_method` is a lossy numeric projection of them.

This is where FLATS is straightforwardly stronger, and it is the paper's own
headline problem: it reports ~58% of jurisdictions use alternative regulations in
their housing provisions. Our `Variant` keeps the *condition* (`when:`), resolves
by specificity, carries its own citation and its own signature — because a
reviewer who confirmed the base has not confirmed the exception, which is usually
in a different chapter — bands by lot size with exclusive/inclusive bounds so
adjacent table columns meet exactly, refuses overlapping bands, and refuses ties
outright as `Verdict.ambiguous`, which a signature cannot fix. The corpus has
**467 variant blocks and 572 `when:` clauses**. A `_min`/`_max` pair cannot
represent any of that; it can only bound it.

## 3. What the paper argues

That AI cannot do the *substantive* work of zoning encoding, with numbers:

| Trial | Task | Result |
|---|---|---|
| Urban Institute (CT) | district-name extraction | **55%** against an 89% design cap |
| " | district classification | **74%** |
| Cornell Tech / Rush | min lot size | **80%** |
| " | min unit size | **20%** |
| " | max height | **83%** |
| " | NC district names | 54% correct of 3,702 |

The Cornell result that matters most is not an accuracy number: locating a
standard dropped from 1.5 min to 10 sec, but *verification* made the pipeline
**net slower than manual coding**. A fast wrong answer costs a reader the same
minute and returns nothing.

Structural findings behind the base rates: codes average ~191 pages; ~1 in 7 is
not online at all; ~36% of jurisdictions audited had major map/text
discrepancies; **3.15% of districts are extinct** (3,071 of 98,913) and **14.7%
are unmapped** (14,348 of 98,913).

Part IV is not anti-AI. It endorses five uses: extracting *words and phrases*
rather than numbers; **flagging map-to-text discrepancies for humans**; map
digitisation; **webscraping to monitor amendments**; and mining manually-coded
datasets. Two of those five we already do (drift watch in `flats/provenance/`;
NZA as gap-finder). One of them is recommendation #1 below.

## 4. FLATS scored against the failure modes

| Failure mode | FLATS | Evidence |
|---|---|---|
| Alternative / conditional regulations | **Stronger than LUL** | 467 variants, own cite + own signature per exception, bands, `Verdict.ambiguous` |
| Hallucinated numbers | **Defended** | sweep is blind to our encodings, `format:json`, `temperature:0`, line-range filter drops any citation outside the passage shown |
| A machine's answer treated as truth | **Defended** | nothing in the sweep writes to a rule file; `corroborate.py` explicitly cannot promote — "agreement between two machines is still nobody having read the sentence" |
| Null vs. missing | **Stronger** | nine distinct shapes: `zone_missing`, `jurisdiction_missing`, `missing_required`, untagged clause, unresolved R/E, `Wanted`, `exempt`, `UNZONED`, `UNMAPPED/` |
| Terminology drift between codes | **Defended, and the best thing in the repo** | per-jurisdiction word cards; definitions deliberately **do not inherit**; `undefined` outranks `unsigned` on the readiness ladder, so signing is *mechanically* gated behind vocabulary |
| Amendment tracking | **Defended** | nightly hash re-fetch → `stale` → REVIEW within 24h. This is the paper's Part IV.C.3 recommendation, already shipped |
| Silent omission of a whole zone | **Defended** | coverage ledger; the 88,947-lot quadfit failure is the founding story |
| Wrong number producing a false RED | **Defended** | draft/stale/missing → UNKNOWN, never RED |
| **Map vs. text reconciliation** | **Half-defended** | `districts.py` audits *text names we don't hold*. The reverse direction is uncovered — see #1 |
| Extinct / unmapped districts | **Not modelled** | no `extinct` disposition anywhere in `flats/` |
| Overlays | **Not modelled** | refused into UNKNOWN, never resolved |
| "Or" disjunctions | **No form** | degrade to prose in `notes:` |
| Second reader / spot audit / golden suite | **Absent** | one signature per field; a second overwrites rather than accumulates |

One state-of-play fact that frames all of it: **`flats/config/verifications.jsonl`
does not exist.** Zero signatures. 0 of 333 coverage rows are `verified` (206
partial, 127 zone_missing). The machinery is built and the signing pass has not
run, so today every lot routes UNKNOWN. That is the system behaving correctly,
but it means gate #1 is currently load-bearing for everything.

---

## 5. Recommendations, ranked

### 1. A zone-granularity mirror of `unweighed()` — and it has already found 472 lots

`ledger.py:184` reports encoded **jurisdictions** the parcel corpus holds no lot
for. It returns empty, correctly, and the docstring says so. There is no
equivalent at zone granularity, and that is where the misses are. I ran the join:

> **14 of 220 encoded (layer, zone) pairs have never had a single lot weighed
> against them, and `unweighed()` reports zero**, because every one of their
> jurisdictions does appear in the ledger.

They split into exactly three causes, each needing a different action:

**(a) UNZONED passthrough — 14,485 lots.** Lake Oswego (14,256), Rivergrove
(222), Johnson City (7). In all three the *only* ledger row is
`(unzoned in parcel data)`, so every encoded zone in the city has zero lots while
the city itself looks weighed. `ledger.py:216` names the Lake Oswego case and
calls it "a different hole... named in the plan, not fixed here" — but it frames
it as a *jurisdiction* hole. At zone granularity the check catches all three
cities automatically, including the two nobody has named.

**(b) A label-join failure — 472 lots, and the question was already asked.**
Happy Valley. We encode one zone, `MURM`. The zoning layer prints **`MURM1` (172
lots)** and **`MURM2` (300 lots)**, both sitting in the `zone_missing` queue as
"go encode this." The code text prints four districts — MUR-M, MUR-M1, MUR-M2,
MUR-M3. And `happy-valley.yaml:2838` already contains the reading:

> *"Those three codes are not carried as zones here: nothing confirms the zoning
> layer prints them... If the layer does print them, they are three `like`
> entries and this note is the reading behind them."*

The layer does print them. The answer to that open question has been sitting in
the committed coverage ledger the whole time. Nothing joins a prose note that
says *"if the layer prints X"* to the ledger, which says whether the layer prints
X — because `zone_missing` rows carry no hint that a sibling zone in the same
file already holds the reading. This is a FLATS-native instance of the one AI use
the paper actually endorses: **flag the map-to-text discrepancy for a human.** It
does not need a model. It needs a near-miss string match between encoded zone
keys and `zone_missing` zone strings within one layer.

**(c) Possibly extinct or unmapped.** Tualatin `RML` — encoded, absent from the
GIS entirely (the city's observed residential is `RL` and `RMH`). The paper's base
rates say 3.15% of districts are extinct and 14.7% unmapped, so this will recur.
`Coverage` has no disposition for it: an extinct district surfaces as
`zone_missing` and gets worked as "encode this," when the right answer is "this
district was deleted — find the superseded text, or rule it extinct." Add
`extinct` to the `Coverage` enum with a required ruling, the way footnote
dispositions already work.

Cost: a function beside `unweighed()`, an `UnweighedZone` dataclass, a near-miss
comparator, one enum member, and a row in the backlog report. Payoff today: 472
lots move out of a queue they do not belong in, and 14,485 stop hiding behind a
jurisdiction that looks covered.

### 2. Put the use-permission vocabulary in `GOVERNS`

`words.py:72` maps 26 words to the fields whose meaning they set, derived from the
32 fields actually encoded. It already includes `dwelling unit`, `middle housing`
and `townhouse`, all governing `quadplex_allowed` — so this is narrower than it
first looks, and the earlier framing that the queue is dimension-only was wrong.

What is missing is the rest of the use-category vocabulary: **`multifamily`,
`multi-family`, `multi-dwelling`, `apartment`, `attached house`, `duplex`,
`triplex`.** Those words appear in 37, 30, 16, 37, 15, 93 and 82 of the 181 corpus
documents respectively. They are not in `GOVERNS` and not in `SPELLINGS`, so no
card asks whether any city defines them unusually.

This is the paper's §I.B.2 trap aimed at our single most consequential field — a
"multi-family" definition that requires 5+ units, or a "townhouse" definition that
caps at three attached. And we have already been bitten by it and caught it *by
hand*. From that same Happy Valley encoding:

> *"16.12 defines multifamily as 'five or more families' and the parenthetical
> after attached dwellings enumerates three types a quadplex is not."*

Verified in the corpus: `16.12.definitions.txt:561` — a multifamily dwelling is
for "five or more families." So "Multifamily dwellings: P" in the MUR-M use table
does **not** permit our fourplex. One careful reader caught that. Thirty-six other
corpus documents write the word `multifamily`, and there is no card asking the
same question of any of them. The mechanism that would generalise the catch does
not exist; the catch was a person.

Adding seven entries to `GOVERNS` (each → `quadplex_allowed`, plus `max_units`
where apt) generates cards only where the word is actually written and the
jurisdiction actually holds an encoded value — the existing weight test — so this
is a small, self-limiting change to the highest-consequence field we have.

### 3. Publish the blind-re-read rate as a number

Blind re-reads are already institutionalised — `stale.py:15` records that the
blind re-read of 2026-09-07 found three live ones; `missed.py --out` measures the
sweep against what we hold; the sweep banks its own recall (48.4% / 50.0% / 61.3%
across three qwen2.5:7b configurations) precisely so the measurer is measured.
This is not a gap in practice. It is a gap in *reporting*: the paper's whole
rhetorical method is that a defence is only credible with a denominator attached,
and our re-read findings are prose in docstrings rather than a tracked rate. One
line in the backlog summary — reads done, discrepancies found, rate — makes the
claim auditable by someone who did not write it.

### Not recommended yet

- **Overlays as a resolution layer.** Correct eventually, large, and the current
  refusal is safe. The 451 capped (zone, field) pairs in `caps.json` are doing
  real work.
- **A second-reader requirement.** Premature while zero first signatures exist.
  Revisit after the signing pass runs.
- **Buying anything from Land Use Labs.** In our footprint they hold less than we
  do, with a lossier conditional model.

---

## 6. One framing correction

"They only cover PDX proper, so it isn't for us" understates our position. FLATS
encodes Portland *plus 18 other Oregon jurisdictions* across Multnomah and
Clackamas, with variants, preemption, per-city definitions and per-value
provenance that their schema has no column for. In our market they are not a
narrower alternative — they are a subset, and a flatter one. The coverage
question that actually constrains us is the one in CLAUDE.md's market policy:
statewide acquisition intent against two-county data coverage. That is a data
problem, and Land Use Labs does not solve it either.
