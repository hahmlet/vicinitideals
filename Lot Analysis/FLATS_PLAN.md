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

**A file states the figure a reader will find, never the one arithmetic makes of it.** A
value therefore has carriers for each shape a code states a standard in, and the loader
does the conversion where it can be read: `per_dwelling` and `acres_per_dwelling` for a
lot area stated per unit, `sqft_per_unit` for a density stated as area, `per_units` for a
parking rate stated as a share, `per_height_ft` for a setback stated off the building.
`spaces_total` is the same bargain for parking a code counts rather than rates — Oregon's
middle-housing rule caps a quadplex at “one space in total”, “two spaces in total” and so
on, and prints 0.25 and 0.5 nowhere; the denominator is the word *Quadplex*, which is the
`DWELLINGS` constant said in English. Each carrier is what the citation check looks for,
so an encoding that invented nothing is never reported as a misquote.

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

**The same rule runs the other way, and it is how the corpus says a city imposes
nothing.** A standard a city does not have is encoded as `value: 0`, cited, rather than
omitted — because omitting it inherits whatever a broader layer states, and a state or
county figure charged to a city that repealed its own is a requirement invented out of
silence. The readiness check has to be able to *see* the zero in the cited text, and codes
spell it four ways: a table cell reading `None`, `N/A` or an em dash; a sentence like
Fairview's "There is no minimum off-street parking requirements"; the word "zero"; and —
added 2026-08-27 for West Linn — a **repeal**. Ord. 1754 deleted CDC 46.080 and 46.100 and
left the heading `OFF-STREET PARKING SPACE REQUIREMENTS` standing over a subsection that
states only a maximum. That is the strongest way a city can impose nothing and the only
one that leaves nothing on the page to read: the sentence that used to require parking is
gone, and no sentence arrived saying so. A citation resting on a repeal has to quote the
repealed section's **heading** as well as the repeal, because the check can confirm that
something was repealed and never which thing.

### The ledgers

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

**Cross-reference ledger** (`flats/encode/crossrefs.py` → `crossrefs.csv`) — *which
sections our own documents point at that we cannot open.* Every other check starts from a
document in the store; this one starts from the documents they reference. One row per
unresolved reference, ranked three ways: `mentions` (how loud), `binding` (it stands
within twelve lines of a citation an encoded value was read from), and **the standards it
stands beside, named**. Proximity alone cannot tell a design chapter that moves a setback
from a use table's "Signs — see Chapter 19.170", so a reference beside a standard that
carries a *distance* (`FieldDef.has_slack`) outranks one beside a use permission.

A row leaves the queue by being read, not only by being fetched. A jurisdiction file
records a `crossrefs:` ruling — an outcome (`other_building`, `narrows_only`, `procedure`,
`preempted`, `other_path`, `misread`) and the argument for it. Two outcomes do **not**
close a row: `fetch` is work ordered and `later` is work deferred, and a queue that hid
either would report a decision as a disposal. Rulings are checked the other way too: one
on a reference the corpus no longer makes is reported as stale.

`later` earns its place on the land-division chapters. Portland's 33.613 and 33.614 and
Wood Village's 450 are each reached by the same pair of sentences — no minimum lot size
for *development*, and lot *creation* goes to the land-division chapter — so they cannot
touch a pod that sits on the lot it was handed. That is true only while no pod declares
`plat: unit_lots`, which is a fact about `flats/config/pods/` and not about any code, so
a test asserts it rather than a note claiming it. Declare a splitting pod and all three
become fetches the same day.

The failure it exists for: Gresham's rear setbacks were read from Table 4.0130, and the
sentence that makes a 26 ft building stand five feet further back lives in 7.0420, a
design-standards chapter nothing in the encoding cited. It was found by reading, a year
late, across roughly 21,000 lots.

The failure *it* had: a document is matched to the chapters it holds by the leading number
in its filename, and four Clackamas County files are named for the ordinance instead
(`zdo.1012.txt`). They claimed no chapter, so every reference to a section they hold read
as unfetched — the county's own Section 1012, the loudest reference in that layer, led the
queue while sitting in the store. 252 rows were the store failing to recognise itself.

**Column ledger** (`flats/encode/columns.py`) — *which encoded numbers came out of the
wrong column.* A dimensional table prints one row per kind of building and one column per
district, and a citation names the row. Every other check in this system asks whether the
encoded number appears on the line the citation names, which is true of every district in
that row that happens to share it. This one splits the row into cells, takes the column
order from the nearest header above it, and reads the district’s own cell by position.

It counts cells rather than character offsets. Reading by offset was tried and does not
work on these extractions: they align body rows with each other but not with the header,
and Gresham prints its district codes thirty characters right of the values beneath them.
A row that has dropped an empty cell is skipped rather than indexed, because the dropped
cells are exactly the ones that shift every column after them.

It follows a citation onto every line the citation names and asks agreement of **one** of
them, not all — the other lines are context by design, a header row quoted to pin a column
or a second row the corpus chose between. And a citation that reaches past the table is
not judged at all. That is the rule that keeps it quiet: what a citation reaches past the
table for is routinely the thing that *replaces* the cell. Gresham CC’s maximum front
setback is “10 feet” in the cell and five feet by note 3c, on a street class this screen
cannot read; Happy Valley’s lot width is “100 feet” in the cell and exempt by note 2 four
hundred lines down. Both encodings are right and neither matches its own cell. What stays
judged is the citation that names the row and nothing else — which is the shape the
townhouse frontage misread had. A citation naming its own *header* is the exception to
the exception: that is the corpus being careful about which of six columns a number came
from, not reaching for an override, and counting it as a reach left Troutdale and Happy
Valley almost entirely unjudged. It reaches 751
citations and judges 378 of them.

Two buckets, because they are different work. A **mismatch** is a cell stating one number
where another was encoded. A **vacancy** is a cell stating no standard — “None”, “NA” —
with a number encoded against it, and it is ruled per field rather than per city. A
setback is *subtracted*: zero and no-standard both let the building stand on the line, so
Portland writing `0` where Table 130-2 reads “none” is not a finding. A minimum lot size
is *tested*: a floor of zero is a claim the table does not make, and that is what the
Gresham row turned on.

The direction it does **not** answer is an exemption encoded over a cell printing a
figure — the only kind of error in this corpus that produces a false GREEN. Counting cells
cannot separate the dangerous version from the innocent one: Happy Valley's density row
prints *4.4 du/net acre* in R-40's own column and the exemption is correct, because the
row is headed “Townhome maximum density” and a quadplex is not a townhouse. The exemption
ledger reads the words instead and files all seven as `numeric`, a citation a reviewer
cannot read the exemption out of. Two ledgers, one question each.

The failure it exists for: Gresham Table 4.0130 G.1, the townhouse street-frontage row,
reads *16 ft. / 16 ft. / 16 ft. / None / None / 16 ft. / None* across LDR-5, LDR-7, TR,
TLDR, MDR-12, MDR-24 and OFR. 16 was encoded for all six held districts, two of which
state no frontage minimum at all. The quoted line contains “16 ft.” three times, so the
citation checked out; the number was simply somebody else’s. The same pass found five
more of the species — a minimum lot size encoded as `0` where Table 4.0130 B prints
`None` in all seven columns, which the screen treats identically and a signer does not.

The failure *it* had, twice, and both invisible in its own output: the first version read
29 citations and pronounced the corpus clean, missing Happy Valley entirely because its
layer keys `R40` where its table prints `R-40`, and missing every table whose header
carries its own row-label cell. The second version compared numbers only, so `None` was
unjudgeable — it would have walked past the misread it was built for. Both are why
`reach()` is pinned by a test: **a reader that has stopped seeing rows reports a clean
corpus in exactly the words of a corpus that is clean.**

Two more of the same species surfaced while widening it, and neither showed as an error.
Four Wood Village zones are keyed with a space — `LR 7.5`, `MR 2` — and the key pattern
stopped at the space, which did not skip them: it kept attributing their fields to the
zone declared above, so each was checked against another district's columns, found no
cell, and passed in silence. And a `quote:` nested one level deeper than the value it
follows is not that value's citation. `measured_on:` and `like:` open a block carrying
their own cite, and that cite names the *denominator* or the borrowed-from zone — Happy
Valley's density quotes 16.63 there for what a net acre is, and read as the density's own
citation it compares a number against a land-division definition. 103 citations in the
corpus sit inside such a block; a depth guard now drops them, taking the parsed total from
2,249 to 2,142 without moving reach or judged.

It reads 751 of 2,142 cited values, and its docstring names the five shapes of the rest so
that a clean report is not read as a clean corpus. Three of the five are nothing to check —
prose, a table with one district in it, a header whose columns are housing types. The other
two were real gaps and both are now read where the shape can be confirmed.

The fourth is the table printed one cell per line, down the page, and it was the dangerous
one. Happy Valley prints its three attached districts that way, and the reader had been
looking them up in the nearest header *above* the line — which in that file belongs to the
single-family table. A header that does not carry the district returns nothing, and nothing
is exactly what a table with no error in it returns. 78 citations sat in that silence.
`_vertical` reads them by recovering the one thing the horizontal form gives away for free,
which is where a row ends: the run of district codes under the caption is taken as the
header and then made to prove itself, since at least two rows below must come out that many
lines long. No row may come out *longer* — a run past the district count means the boundary
between two rows has been lost, and once it is lost anywhere in the table a run of exactly
the right length has stopped being evidence. That divides Happy Valley and unincorporated
Clackamas, which are read, from Fairview, which is refused whole: Fairview numbers its row
labels — “1. Minimum Lot Size (sq. ft.)” — so every label reads as a value and its rows run
together eighteen lines at a stretch under a header of three.

The fifth was a gap and is now read. Where a table comes out with its columns one space
apart, splitting on whitespace returns the whole row as one cell, so `sparse_cells` reads it
by grammar instead: a cell opens on a figure or on a word meaning no standard, runs through
the units behind it, and stops dead at a word that is neither. That takes Gresham's two plan
districts whole, and the cleanly extracted half of Oregon City's scanned chapter with them —
92 more citations, 57 more judged, no new findings. Two guards keep it from producing the
error the module exists for. Every cell of a row must state the same *kind* of quantity, or
a row label carrying a measurement — “Lots over 5,000 sq. ft.” — hands its own number to the
first district and shifts the row one column left. And a single-space header is accepted only
once a line below it reads as a row of that many values: nothing in the shape separates
`USES LDR-PV MDR-PV HDR-PV` from `Schools P/SUR15 SUR L/SUR15`, and a use row promoted to a
header does not fail to find a row, it finds one belonging to a different table.

What refuses is the rest of Oregon City, where the scan puts the same single space between
the columns and between the halves of the broken words — *Quad pl ex a nd co t tage 1 0 ,
000 squ are* — so the reading stops where the extraction did. All of it was read by hand on
2026-09-02, every dimensional value against its own column, and all of it is correct. Everywhere the
check now reads, that hand audit has become a floor under it; for Fairview and the scanned
rows it remains a reading of a corpus at a moment, not a check that will notice if it moves.

**Redirect ledger** (`flats/encode/routing.py` → `routing.csv`) — *which sentences hand a
standard to a section nobody opened.* One row per sentence that replaces a standard
("is subject to the standards of Section X instead", "does not apply", "supersede")
where the sentence sits in a section an encoded value was read from and points at a
section held in the store. A row closes on evidence, not on a note: it is `followed`
when some value in that layer was read from inside the section pointed at.

The failure it exists for: Portland's 33.266.120 states a stall and no aisle, and
33.266.120.B.1 — four lines above the sentence that was quoted — sends parking in a
parking tract to 33.266.130, which states one. "Portland states no aisle width" was
encoded and shipped. The cross-reference ledger was silent because the section was in a
document already fetched; the readiness ladder was silent because the citation rendered;
the refusal ledger was silent because the refusal was counted.

An open row here has, until now, always been somebody else's building or a rule that can
only loosen. Clackamas County's ZDO 315.04 → 845 → 845.02 broke that: the pointer out of
the district chapter was followed, and the one inside Section 845 was not. 845.02,
*Triplexes And Quadplexes*, is this building exactly — street-facing windows at 15
percent, entry orientation, driveway entries capped at 32 feet total, and garages and
off-street parking barred from between a building and a public street. The last two are
geometry this screen places, and the field registry has no way to say where parking sits
relative to the street: Gresham's equivalent rule lives in the site-plan generator as a
hard-coded rear-court typology rather than as a standard. So it is a **modelling gap, not
a reading gap**, and the row stays open until a field can hold it. Both Clackamas rows
appeared the day `_doc_ids` learned to read a filename that opens with the code's own
abbreviation — before that `zdo.845.txt` claimed no chapter, so its own sections read as
unfetched and neither redirect could be scored.

Fairview made it three, from the other direction. FMC 19.162.020(L), *Driveway Openings*,
states two numbers and the registry has nowhere to put either: L.1 gives “single-unit
dwelling, duplex, triplex, quadplex, and townhouse uses” a minimum driveway width of 10
feet and a maximum of 24, and L.2 gives “multiple-unit uses and cottage clusters with
between four and seven dwelling units” a minimum of 20 and the same maximum. Both rows
reach this building on their face — this layer has already established that Fairview’s
“multi-unit dwelling” means five or more, which argues L.1 — and a 10-foot drive and a
20-foot drive are ten feet of lot apart. **Access geometry is the one thing this screen
places that no field can express**: where parking sits relative to the street (Clackamas
ZDO 845.02), how a court is reached (Gresham, hard-coded), and now how wide the drive to
it has to be. Fairview alone adds a fourth: 19.163.030(E)(3)(b) requires at least four
feet between a building and any parking, maneuvering area or driveway beside it, and
where the building is residential ground-floor living space that four feet must be
landscaped rather than a raised pathway — so a rear court here is four feet deeper than
its stalls and its 24 ft aisle. Three jurisdictions, one missing field family, recorded
rather than fixed.

The gap is wider than the ledgers can see, and Fairview is where that became obvious.
**A city can require no parking and still regulate parking completely**, and the rules
that do the regulating never surface in a cross-reference queue, because they are not
references — they sit in a chapter already fetched, already read for other values, in
sections no field exists for. FMC 19.30.040(E) bars parking between a building and a
public street unless a dwelling screens it or the garages and paving stay under half the
frontage. 19.30.040(F)(1) caps every driveway approach on a frontage at 32 feet, the same
number as Clackamas ZDO 845.02 because both are the state middle-housing model code.
19.30.050(D) gives the townhouse branch a 12-foot ceiling on outdoor parking and
maneuvering per lot, or sends the parking to the rear yard outright. None of that was
recorded until somebody asked what applies *if we build parking anyway* — which this
product will, regardless of what a code requires. **"Required" and "regulated" are
different questions, and only the first one has a field.**

Run over a city already finished, the question keeps producing. Wilsonville requires no
parking and caps none — both fields have read `exempt` since 2026-08-22 — and Section
4.113(.14) subsection D is titled *Standards applicable to Triplexes and Quadplexes* and
regulates the parking anyway. D.3 holds all garages plus outdoor parking and maneuvering
to half of any street frontage. D.4 caps driveway approaches at 32 feet per frontage —
the same 32 feet again, from the same model code — and forces access to the lowest-
classification street, or to the alley where a paved one abuts. Subsection E is the same
building on unit lots, and it is far tighter: **12 feet of outdoor parking and
maneuvering per lot**, around a stall Wilsonville defines at nine feet wide. Three feet
of maneuvering is a single-file driveway, not a court. What the city *does* dimension it
dimensions in its definitions rather than its parking chapter — 4.001(220) makes a
parking space “not less than nine feet wide and 18 feet long” — and what it never
dimensions anywhere in Chapter 4 is the drive aisle. Holding a stall and no aisle is not
the same object as an aisle of zero, and 4.113(.14)D.4.c.ii sends the question to the
Public Works Standards, which is the Gresham 9.0200 shape a third time.

And the state says the whole family may be the wrong family. OAR 660-046-0220(2)(e)(E):
a Large City “must apply the same off-street parking surfacing, dimensional, landscaping,
access, and circulation standards that apply to single-family detached dwellings in the
same zone.” Every stall width, stall depth and aisle width in this corpus was read from a
general parking table; this sentence says the ones that bind a quadplex are whichever
ones bind a house on the same ground. It is a rule whose entire content is a pointer, and
unlike the other three it puts a live question over geometry **already encoded**, in
every Large City at once. Nothing can follow it today: no zone here records what its
single-family parking standards are, because until now nothing asked. Recorded in the
state layer as a refusal so the next reader meets it before a site plan does.

Three more cities read on 2026-08-27 — Milwaukie, Oregon City, Happy Valley — took the
corpus from four layers holding stall geometry to seven, and each one failed in a
different way, which is more useful than the numbers.

**Milwaukie states an aisle this building may not use.** Table 19.606.1 gives a 22-foot
aisle at 90 degrees and it is not Milwaukie's answer for a quadplex: the purpose
paragraph of Section 19.606 applies the section "to all types of development where
parking is provided, except for middle housing, single detached dwellings, and adult
foster/care homes", and Table 19.605.1 files quadplexes under Middle Housing. What
survives is Section 19.607, which names the building — "single detached dwellings,
duplexes, triplexes, quadplexes, townhouses, cottage clusters" — and dimensions the space
at 9 by 18 and no aisle at all. So Milwaukie is Wilsonville's shape a second time, a stall
with no aisle, and the number that looked like an aisle was a trap two lines above the
table. It also caps a quadplex at **one space per unit**, the tightest cap in the corpus
outside Portland, off the same Table 19.605.1 that states no minimum for anybody: the only
vehicle minimum in the chapter is footnote 1, half a space per unit where the frontage is
an arterial or collector, which is the number this file carries because street
classification is unmeasured.

**Oregon City states a number whose unit is missing.** Table 17.52.020 asks a triplex or
quadplex for a minimum of "2.00" and a maximum of "4", under a header declaring the
table's figures to be per 1,000 square feet of net leasable area unless otherwise stated,
one row below "Multi-family residential — 1.00 per unit". Per 1,000 square feet, per unit
and in total are three different buildings, and only the last is lawful, because OAR
660-046-0220(2)(e)(B) caps a Large City at four spaces in total. Choosing the reading that
survives preemption is an argument, not a citation, so both cells are refused and the
state cap governs. The geometry beside them is unambiguous and encoded — 9 by 19 off a
24-foot aisle — but it stands down under `unit_lots`, because OCMC 17.52.010 excludes
"single-family detached residential dwellings, duplexes, townhouses, and cottage clusters"
from the whole chapter and leaves triplexes and quadplexes in it. That is the first time
in this corpus a city's **stall dimensions depend on how the land is divided** rather than
on what is built.

**Happy Valley answers everything and bans the site plan.** One chapter, LDC 16.43.030,
requires one space per dwelling, states no maximum, dimensions the stall at 9 by 18.5 off
a 24-foot aisle — and then 16.43.030.E.4 says "Parking areas shall be set back from a lot
line adjoining a street the same distance as the required building setbacks." In a city
whose residential front setback is twenty feet, that does not cap front-yard parking the
way Milwaukie and Wilsonville cap it; it removes it. 16.43.030.F.5 requires forward entry
to the right-of-way for any group of more than three spaces, which is every arrangement
this pod has. Both were refusals for want of a field; the first is now encoded — see
**A standard stated as equal to another** below — and the second still is one.

Seven layers of nineteen now hold stall geometry. What the three have in common is that
none of the missing pieces is a missing *number* — they are a missing field family:
driveway approach width, share-of-frontage, placement relative to a façade or a street,
manoeuvring-area width, parking setback. Six jurisdictions have now been transcribed
rather than encoded against that gap, all of them printing the state middle-housing model
code in local words, so that building the fields is a copy job and not a re-read.

**That family was built on 2026-08-27**, and the copy job was the copy job it looked
like. Twelve fields — `driveway_approach_min_width_ft`, `driveway_approach_max_width_ft`,
`driveway_min_width_one_way_ft`, `driveway_min_width_two_way_ft`,
`parking_maneuvering_max_width_ft`, `parking_area_max_frontage_pct`,
`parking_area_max_width_ft`, `parking_front_yard_max_pct`, `parking_front_prohibited`,
`parking_street_setback_ft`, `parking_building_buffer_ft`, `open_space_min_sqft` — all
optional, because they are sentences in an access chapter that name a housing type rather
than rows of a zone table. Eight layers encoded against them, twenty-one values, and
twenty-three refusals recorded alongside.

Three things came out of the reading that were not the reason for it.

*The six cities really are one code.* Fairview, Wilsonville, Oregon City, Milwaukie and
unincorporated Clackamas each cap outdoor parking and manoeuvring at **twelve feet** on a
townhouse lot — ten in Milwaukie — and at **fifty percent of the street frontage** on one
lot, in near-identical sentences, because all of them are printing OAR 660-046. Twelve
feet around a nine-foot stall is a single-file driveway, not a court: on the split plat,
the parking arrangement this product draws is not permitted in any of them. The one-lot
path is the one that works, which is the path the design catalog already defaults to.

*A ban and a cap are not the same rule.* Portland and Milwaukie forbid parking between
the building and the street outright; the other five permit it and cap it at half the
frontage. Both carve the driveway out in the same sentence, so what is banned is a
front-yard **court**, not the drive that reaches a rear one — which is why one bool could
not carry both and `parking_front_prohibited` is three-valued.

*Happy Valley's driveway is twenty feet.* LDC 16.41.030.B.1, in a chapter that had to be
fetched because 16.43 states no width at all: a two-way drive is improved a minimum of 20
feet. Every other city here states nine or states nothing. It is a **minimum**, so unlike
an approach ceiling it cannot be traded down, and on a narrow lot it is the difference
between a site plan and none. 16.43.030.E.4 stayed refused in that pass: it sets parking
back from a street by "the same distance as the required building setbacks" and prints
only a ten-foot floor, so the only number on the page is half the real standard and wrong
in the permissive direction. A field that could hold "the same as another field" would
hold it; none did, and `qualified_by` could not, because it names a site fact rather than
a field.

### A standard stated as equal to another

**Built 2026-08-27**, and it is one carrier, `Value.same_as`, plus the `floor_ft` the
height ratio already had. A value names the field its sentence points at; the loader
resolves the pair against the number the SAME block holds with its own citation. Nobody
types the answer. It is the `per_height_ft` bargain with a different second operand: a
height ratio multiplies by a property of the *building*, and this one reads another
standard in the same zone.

Two conditions make a borrowing sound, and both are checked rather than listed: the two
standards answer in the same **unit**, and they bind in the same **direction**. There is
deliberately no allowlist of fields that may borrow — an allowlist would be a guess about
which sentences codes write, and these two are the actual invariant. The lender must sit
in the same zone block rather than be inherited from a parent layer, which is also not an
implementation limit: a borrowed standard is only as readable as the row it borrows from,
and a reviewer holding one screen should see both numbers and both citations.

Happy Valley's is the first, on eleven zones. One sentence, three answers — 22 ft in the
six lower-density districts, 20 in R-5 and MUR-S, 10 in the three attached ones — and the
printed ten is the standard in three of them and twelve feet loose in six. MUR-M and
MUR-X state "Variable ... determined through the master plan process" and so lend nothing
and get nothing; R20CC gets it through `like: R20`, which is what adoption by reference
is for.

**What it comes to for this building is nothing, and that is the finding.** Every Happy
Valley district that permits a quadplex sets a building back at least twenty feet from a
street; the site-plan generator lays out inside an envelope already cut to that setback;
so a court that clears the building setback clears the parking setback, by the same
sentence that created it. s6s enforces the rule as arithmetic on the excess over that
inset rather than as an assertion, because the next city to print one may print a bigger
number, and it now says out loud, per city, what is asked and whether the envelope
already answers it. A rule encoded and never mentioned again is indistinguishable from
one nobody wired up.

Two neighbours in the same subsection stayed refused, and for the old reason rather than
this one. E.1 bans off-street parking "in the landscaped yard areas of any lot" — a
landscaped yard *area* is not a yard, and `min_landscaped_pct` is a share of the lot
rather than a place on it. E.3 sends a parking area abutting a residential district to
"the setback of the most restrictive adjoining residential zoning district", which is the
**neighbour's** standard applying to our lot: `same_as` reaches another field in this
zone, not another zone's field, and what would answer it is the zoning of the parcel next
door.

What the family was built **for** was the site-plan generator, which had been drawing
every city's driveway to five constants taken out of Gresham's townhouse chapter. Two of
the five were not Gresham's law either: on the one-lot plat s6s draws, GDC
7.0420(B)(2)(b)(ii) caps a garage-less fourplex's approach at **ten feet**, not the
eighteen of 7.0431(B)(2)(b); and the fifteen percent open-space reserve charged against
every lot in seven cities is 7.0420(D)(1), which **four of the seven never wrote**.
Fairview's open space is an RM-district multi-unit standard, Wilsonville's is the
Villebois village zone, Oregon City's was a cottage-cluster rule about impervious cover,
and Happy Valley's footnote points at a section that does not contain it. Portland states
it by zone — 250 square feet, 200 in R2.5 — and is the only city in the corpus that does,
which is why the quadfit mirror carries a per-zone map for it alone.

The same chapter carries the corpus’s second refusal of the Gresham 9.0200 shape, and a
worse one. 19.162.020(O) is the qualifier on an exemption this layer *encodes* — FMC
19.70.020.A.3 waives the side setback “except that buildings shall conform to the vision
clearance standards in Chapter 19.162 FMC” — and it states a height and no extent:
nothing over three feet in a “vision clearance area, as shown above”. FMC 19.13 closes
the loop by defining the term as “the shaded area as shown on the following figure”. Two
documents, no number, because the number is a drawing. Gresham’s equivalent at least
named the manual it deferred to; this one defers to a picture, which is a document class
no extractor in this system can read at all.

**Exemption ledger** (`flats/encode/exemptions.py` → `exemptions.csv`) — *which
exemptions cite a page that does not state one.* `exempt: true` is the only value that
removes a test rather than narrowing it, so it is the only one that can turn a lot GREEN
with no margin to soften the error. One row per exempt value and variant, classified by
what a reviewer opening its citation would actually find: **stated** (exemption language
is there), **numeric** (the page prints a figure and no exemption), **marker** (the
citation resolves to `[2]` and nothing else — a pointer to a pointer), **dash** (an
em-dash cell, which is how these tables print "no standard here"), **silent**.

The failure it exists for: all seven of Lake Oswego's density exemptions cited the
footnote marker rather than the note one line below it, which says "Duplexes, triplexes,
quadplexes, and cottage clusters are exempt from maximum density standards" in as many
words. The readings were right and no reviewer signing those cards could have seen why.
`marker` is now a hard zero; the other counts are pinned and move deliberately.

Coverage ledger catches "we never looked at this zone." Clause ledger catches "we looked
but missed the exception." Cross-reference ledger catches "the sentence that changes this
number is in a chapter nobody fetched." Redirect ledger catches "we read the section that
says this section does not apply." Exemption ledger catches "we wrote down that there is
no standard and cited a page that never says so." Stale-reason ledger
(`flats/encode/stale.py`, 2026-09-07) catches "we wrote down *why* a footnote does not
apply and the why has since become false." Missed-standard ledger
(`flats/encode/missed.py` → `missed.csv`, 2026-09-08) catches "the standard is printed
in a document we hold, on a page we read, and nobody ever took it." All seven are needed;
none substitutes for another.

The sixth is a different animal from the other five and the difference is worth naming.
Those five ask whether we read Oregon correctly, and their answers are as durable as the
page. A dismissal reason may instead argue about **this repository** — "a district this
layer does not encode" — and that is a true statement with a shelf life, falsified the
day somebody encodes the district, with the note still dismissed and nothing watching.
Of 784 dismissals, 49 argue about the corpus rather than the code; those 49 are the only
ones that can rot, and they are the only ones this ledger reads. It over-reports on
purpose: a reason that names a live zone for its own reasons ("120 feet from a lot zoned
R-6" is a measurement) is visible as such in a second, whereas a stale reason reads
exactly like a sound one.

**It is also one of only two that rank themselves by consequence, and that is not
decoration.** The other five audit a number against a page, so every row is worth the
same. Here a row's cost depends on something outside the reason entirely: what the note
stands over. A false claim about a district where `quadplex_allowed` is already `False`
cannot produce a wrong GREEN, because the lot is RED on use before a footnote is reached.
So each row carries its zones and the subset that permits the building, and `bites` marks
the intersection — 7 of the 10 contradicted on the run this was built for. It is a screen
and not a finding: reading those 7, five gave a second ground that stands on its own
(the note is about cottage clusters, it loosens rather than tightens, the pod is not the
building type named) and one changed what a lot must satisfy. `_permits` treats absence
as permission — only a recorded `False` closes a district — because the conservative
error here is to over-report, exactly as everywhere else in this project.

The seventh is the reading ledger's sharp end. `uncited.py` already lists every line in
our documents that states a measure nothing quotes — 1,206 of them name a field we screen
on, which is a true count and an unworkable queue, because read end to end it is mostly
the industrial column of a table whose residential column we took. So this compares the
figure on the line against every figure the jurisdiction holds for that field: 542 state
a number this corpus has never held. It is a sort and not a verdict, and it is ranked by
two keys in this order — how near the line sits to reading somebody already did (a figure
in a section we took *this same standard* out of is a skipped row; the same figure in a
chapter nobody opened is a different job), then how many lines print it. Sorting by count
alone put fences, parapets and cistern heights at the top of the first run.

Two gates decide what counts as a number and both are load-bearing. The **unit** gate
says the sentence meant this figure as a measure of this kind: Milwaukie says a building
"can utilize up to 2 of the development incentive bonuses", and two feet is a perfectly
plausible height, so no magnitude window catches that and only the missing "ft" does. The
**window** says the measure is of a size the unit can have, and it belongs to the unit
rather than to the field because an area is 5,000 square feet or 80 acres. Nothing is
converted: what is compared is the figure a reader will find against the figure the file
records having found, which is the bargain `readiness._printed` already makes and is
reused here rather than re-derived — so a new derived form has one place to be taught.

**The reading queue drops what the ledger keeps counting, and the first run paid to
learn it.** `work_list` builds one card per line and somebody reads a page of code to
answer it, so a card is *work* in a way a row in a ranked feed is not — and 26 of the
first 185 cards, with 8 of the 29 findings, were Lake Oswego and Rivergrove, which the
screen does not cover. `triage.feed` deliberately keeps excluded layers and marks them,
because it ranks on lots at stake and a second invisible sort would make it
unexplainable. The reading queues drop them (`eligible_only`, `include_off`), and this
one now joins them, while `render` keeps them in the count: a list that hides what it
excluded cannot be told from a list that has finished.

The first blind reading of it ran 2026-09-08: **29 of 185 said the line binds, 150 said
it does not, 6 could not tell**, and 25 of the 29 closed against the corpus the same day
— a footnote block belonging to a table whose districts we do not encode, a column for a
zone we do not hold, an affordable-housing option nobody has to take, a city already RED
on use. Two need a human ruling and two are real in a switched-off city. That ratio is
the ledger working: the cost of closing 25 is minutes, and the thing it buys is that a
standard printed on a page we have held for months cannot stay invisible.

**A card is a section when nothing in the chapter has ever been quoted.** The
`read_section` tier — a line whose *document* we take numbers from but whose section we
have never opened — cannot be answered one line at a time, because the sentence above a
line is usually what says which building it governs. `chapter_list` groups those rows by
`(layer, path, section)` and hands over the section entire, with `>>` on every measuring
line and the nearest table caption and heading above the first of them; `score_chapters`
verdicts them `missing / agree / unclear / seen_elsewhere / worth_reading`, the split
being whether the reader's figure is printed anywhere in that layer's own file. 347 lines
in screened cities collapsed to **144 sections** (89 of them a single line, the largest
Gresham 4.1252 at 34), and the run of 2026-09-08 returned **116 agree, 26 binding, 2
unclear** — of which 25 closed the same day. The recurring false positives are worth
naming, because each is a shape no per-line card could have shown: a district *purpose*
paragraph read as a standard (all four Gresham density findings — the dimensional table
prints no maximum against "Duplex, Triplex, Quadplex, Cottage Cluster"), a design *menu*
read as a requirement (Gladstone's "at least four of the following" out of eleven), an
applicant's *choice* read as a floor (Portland's tree area, Option B being whatever the
building does not cover), and a chapter belonging to a district the layer does not hold.
The three that survived include a whole missing zone: Oregon City R-2, whose own table
names "Triplex, quadplex and multi-family" at 6,000 sqft, excluded from the corpus in a
one-word aside — the `project_flats_zone_gap` shape, which no field-counting ledger sees.

**Oregon City R-2, closed the same day, on the code's own dictionary.** The district was
excluded on the note *"NOT the multi-family zone (that is R-2 / Ch 17.12, excluded)"* —
a category, not a measurement, and therefore checkable against the definitions the city
itself prints. 17.04.989: *"'Quadplex' means four attached dwelling units on a lot."*
17.04.780: multi-family residential is *"five or more"* total dwelling units. The pod is
the first and is excluded from the second by count, and 17.12.020.D lists *Quadplexes*
among R-2's **permitted** uses. The premise was wrong, not the judgement. **R-2 is
encoded**, 14 values off Table 17.12.040 / 17.12.050 quoting the rows, in this corpus and
in quadfit's `rules.yaml` (as `needs_verification`, so its lots route to REVIEW until the corpus signatures land — the same treatment the 35 ported zones got), and both stale notes are corrected in place. The general
lesson is cheap and reusable: *an exclusion recorded as a category can be adjudicated by
the code's own glossary, without a human ruling* — the same instrument the word-review
queue was built on, pointed at a zone list instead of a value.

It brings one shape the corpus had never held. R-2 states a **minimum** density of 17.4
du/acre (17.12.050.A) and, uniquely among Oregon City's residential districts, states no
"a quadplex counts as one unit" exception — the other five carry it at 17.08.050.B.2 /
17.10.050.B.2, which is why `max_density_du_per_acre` is encoded nowhere else in the
file. Four units at 17.4 wants net area **at or under** ~10,000 sqft, so **an R-2 lot can
be too LARGE for a fourplex**, the first standard here that binds in that direction; the
window is roughly 6,000–10,000 sqft of net developable area. Its 21.8 du/acre partner
would have squeezed from below, and R-2 is the one district where the state layer's
`OAR 660-046-0220(2)(b)` (`exempt: true, preempts: always`) does real work rather than
duplicating a city's own exception — `_state.yaml`'s note names "Oregon City's exception
B.2" among the cities that restated the rule, true of the five districts that have a B.2
and not of the one that does not. Reach is unmeasured: `read_coverage()` holds no Oregon
City rows, so nobody can count R-2 lots until the inventory extends past Multnomah.

**Porting it into `rules.yaml` is what found the third dark gate.**
`Lot Analysis/quadfit/tests` was named by no CI job — the light gate runs
`tests/ -m unit` and `flats/tests`, the full gate runs `tests/` and `tests/e2e` —
so its 160 tests ran only when somebody remembered. `test_zone_mirror.py` had
been red since `8a6924a5` (three `setback_garage_entrance_ft` values withdrawn,
67 → 64) and `c9ed261f` (three `setback_front_max_ft` values encoded, 23 → 26),
and both shipped over it. The audit that went dark is the one that matters most:
the mirror is the **only** check comparing what the screen RUNS on against what
was READ; every other ledger checks the corpus against itself. The light gate now
syncs `--extra gis --extra tools` (quadfit's `s0_acquire` imports pyshp at module
scope, its overlay stage imports rasterio) and runs the directory, with no
per-file ignore. `UNEXPRESSIBLE` records all three moves attributed to the
commit that made each. The check that would have found it earlier is the same
shape as the mirror itself: *diff the paths every `pytest` line names against
the directories that hold tests.*

**Then the same question was asked of every city at once, and R-2 turned out to
be the small version of it.** `flats/encode/districts.py` reads the stored
corpus for the designations a jurisdiction *prints* and compares them to the
zone list we hold. It is a lead generator, not a ledger of debt — a designation
it reports is a question, and most of the answers are "that is not a zone". The
answers live in `flats/tests/test_districts.py`, one line each, and **the test
fails when a designation appears that nobody has ruled on.** That is the only
property worth having, because every one of the five zone-gap findings so far
was silence rather than error.

It takes three harvests, and the second and third exist because the first one
misses exactly the thing that matters. A parenthesis is how a code *introduces*
a district, but a use table names its columns bare — Milwaukie's Table 19.303.2
heads three columns `GMU`, `NMU`, `SMU` and never spells SMU inside a
parenthesis anywhere in Title 19. So the second harvest takes any line that is
*nothing but* a designation, printed that way at least twice, within 25 lines of
a sentence about zones. That found SMU and all eight of the Clackamas County
districts the first harvest saw only as one long parenthesis. The third exists
because **Lake Oswego's use table is printed exactly once**, so nine of its
fifteen column heads were still invisible to a rule that wants to see a
designation twice — a run of three or more consecutive designation-shaped lines
is a column-head block and running prose never is. A fourth fix, smaller and
just as necessary: a column head **carries its footnotes with it**
(`NC [8], [9]`, `HC [9]`, `OC [8]`), and stripping the trailing marker run was
the difference between finding one of Lake Oswego's commercial zones and
finding all of them.

**Seventy-nine designations across twelve layers, and the queue behind them is
fourteen districts to encode and five to fetch.** Not one of them needs a human
ruling; every one was settled by the city's own use table.

- **Oregon City's commercial land permits our building nearly everywhere.**
  `17.29.020.M` (MUC-1, MUC-2), `17.32.020.S` (C), `17.34.020.L` (MUD) and
  `17.35`'s `R.` (WFD) each permit "Multi-family residential, triplexes and
  quadplexes" outright. Two of the seventeen districts in `17.06.010` refuse
  it, and both refuse it in writing: HC prohibits "Triplexes and quadplexes"
  at `17.26.035.B`, and NC — which would inherit the MUC permission through
  `17.24.020.A`'s "any use permitted in the mixed-use corridor" — strikes
  "Residential use that exceeds fifty percent of the total square footage of
  the development", and a residential pod is all of it. MUC-1 carries the same
  17.4 du/acre **minimum** density that makes an R-2 lot able to be too large,
  and a **5 ft maximum** front setback.
- **Clackamas County holds nine of the eleven columns of Table 315-1 and the
  pod is permitted in ten of them.** The one X is R-2.5. `PMD`, `MR-1`, `MR-2`
  and `VA` have complete Table 315-4 rows and are encodable today; `HDR`, `SHD`
  and `RCHDR` answer rear setback, side setback and building separation with
  "See Subsection 1005.02(L)" and **no ZDO 1005 is in the store**; `VTH`'s
  Table 315-3 prints two cells in several three-column rows, which is a column
  question before it is a reading.
- **Tualatin's RMH chapter is not in the store at all.** `40-41.residential.txt`
  is 646 lines long and line 645 is the heading `CHAPTER 42 / MEDIUM HIGH
  DENSITY RESIDENTIAL ZONE (RMH)`. The file ends there. A whole medium-high
  density residential chapter, missing at the last line of the document that
  should have carried it.
- **Wilsonville has a seventh PDR.** `4.113(.01)C` divides Planned Development
  Residential into PDR-1 through **PDR-7**; we hold six.
- **Lake Oswego's two WLG zones.** `WLG R-2.5` is called *Townhome
  Residential* and `WLG RMU` *Residential Mixed Use*; both have yard-setback
  tables in `50.04` and neither is in the corpus.
- **Gresham's two centre sub-districts.** `TC-PV` "permits a wide range of
  housing types, including … adjacent townhouses and apartments" and `VC-SW`
  sits beside the `THR-SW` townhouse land we do hold. We hold five of Pleasant
  Valley's six sub-districts and five of Springwater's six.

**A refusal here is a use-table cell, not a category.** Milwaukie's GMU, NMU and
SMU are `CU` in Table 19.303.2 — conditional, so refused for the same reason
R-2 was *accepted*: the question is whether the use is permitted outright, not
whether it is imaginable. DMU and MUTSA carry no quadplex row at all while
listing "Multifamily" separately, and Milwaukie keeps those two use categories
apart wherever it lists both. Happy Valley's FU-10 permits "One single-family
dwelling … per lot". Fairview's MH permits homes *in a park*, one per 2,500 sqft
space.

**And one verdict the vocabulary did not have.** Lake Oswego's `50.03.002` is
held, its only household-living row is found — "Residential use at R-5 density
or greater" — and the cell still cannot be read, because the extractor prints
eleven cells against fifteen column heads. That is neither a fetch (there is
nothing to fetch) nor a reading (there is nothing readable), and calling it
either would hide the only work that closes it. `column` is its own verdict, and
ten of Lake Oswego's columns carry it. It is the same failure the column ledger
already names — *a number can be on the cited line and still be the wrong
column* — arriving this time as a permission rather than a dimension.

**What the ledger cannot see, written down rather than assumed.** Oregon City's
general commercial district is called `C`. One character, and a single capital
letter is noise everywhere else in the corpus, so no harvest can ever surface
it. It permits our building. `NC` and `HC` were found the same way — by hand,
while ruling the rows the ledger *did* report. `test_districts.py` keeps those
three in a `BY_HAND` table beside the rest, because a reading that is not
written down is a reading that will be done again.

**Then the sort by lots said all fourteen were worth nothing, and the sort was
reading the wrong ledger.** `_lots_by_zone()` returns zero lots for every one of
them, and the first draft of this section said so — that Oregon City, Clackamas
County unincorporated, Tualatin and Wilsonville contribute nothing and the queue
is coverage work for a day that has not come.

**That was wrong, and it was wrong in the way this project has been caught
before: a ledger answered for a reality it cannot see.** `read_coverage()` reads
`data/flats/coverage.csv`, built 2026-09-02 from a **Multnomah-only** parcel
corpus — 236,889 lots, of which 195,708 are Portland and the only Clackamas
entry is 758 Lake Oswego parcels. The quadfit pipeline that actually screens
land runs on **291,971 lots across fourteen cities**, and its green list is
Portland 12,678, Gresham 1,820, **Oregon City 735**, **Milwaukie 622**, West
Linn 288, Troutdale 125, **unincorporated Clackamas 113**, Wood Village 95,
**Wilsonville 53**. Four of the five jurisdictions this audit found districts in
are screened today and hold greens today. The coverage ledger simply cannot see
the county they are in.

So the honest reading is the opposite of the first draft. These fourteen
districts are not worth zero; **nobody can say what they are worth, because the
one ledger that would say is county-blind relative to the screen it serves.**
That is its own finding and it belongs above the encoding queue: regenerating
`coverage.csv` over the Clackamas parcels quadfit already holds is what turns
this audit's output from a list into a ranking.

The rule the mistake breaks is one already written down here — *lots is a sort,
not a filter*. Used as a filter, a stale ledger reading zero would have closed
all fourteen cards. Used as a sort it merely put them last, which is why the
error was recoverable and why the rule is worth keeping even when the ledger is
right.

**So the ledger was rebuilt, the same day, and it changes the size of
everything above.** `python -m flats.encode.backlog` on the two-county parcel
corpus that lives beside the pipeline on LXC 137: **333 (jurisdiction, zone)
pairs over 334,959 lots**, against 155 pairs over 236,889. Fourteen
jurisdictions became eighteen. `unweighed()` — the mirror check that reports
encoded layers no lot has ever been counted against, written precisely because
the corpus was Multnomah-only — **now returns an empty list.**

The queue this audit produced acquired a ranking the moment it could be asked:

| lots | verdict | district |
|---:|---|---|
| 839 | encode | unincorporated Clackamas `MR-1` |
| 402 | encode | Oregon City `MUC-1` |
| 278 | encode | Oregon City `MUD` |
| 253 | fetch | unincorporated Clackamas `HDR` |
| 120 | encode | unincorporated Clackamas `MR-2` |
| 115 | fetch | unincorporated Clackamas `VTH` |
| 40 | encode | Oregon City `MUC-2` |
| 32 | fetch | unincorporated Clackamas `RCHDR` |
| 9 | encode | unincorporated Clackamas `PMD` |
| 5 | fetch | Tualatin `RMH` |
| 1 each | encode / fetch | unincorporated Clackamas `VA`, `SHD` |

**2,095 lots**, and unincorporated Clackamas holds more than half of them.
Gresham's `TC-PV` and `VC-SW`, Wilsonville's `PDR-7` and Oregon City's `WFD`
stay at zero and stay in the queue — the same unbuilt-sub-district shape the
Gresham notes file already pins, a standard written before anyone built under
it.

**And where the gap bites, whole: 11,520 lots sit on a zone code no rule
matches**, across 141 zones — where the county-blind ledger said 536. The
largest are unincorporated Clackamas `RRFF5` at 2,082, `MR1` at 839, `FU10` at
693 and `RA2` at 491.

**The ten `column` verdicts are all Lake Oswego's, and Lake Oswego is switched
off.** This is the finding the rebuild was worth having. The old ledger said 93
lots rode on the unreadable commercial table — `NC/R-0` at 84, `NC` at 4, `PNA`
at 5. The rebuilt one says Lake Oswego has **16,300 lots and a zone on none of
them**, arriving as a single row named `(unzoned in parcel data)`, 14,256 lots
after the ledger drops condominium and air parcels.
`Lot Analysis/quadfit/config/rules.yaml` marks the jurisdiction `eligible:
false` — an owner decision of 2026-07-24 — and
[s2_assign.py:109](Lot%20Analysis/quadfit/s2_assign.py#L109) joins zoning only
`if j.eligible`, so an excluded city's lots never receive a zone at all and are
dropped before scoring. The 93 were Lake Oswego's **Multnomah** parcels, 6% of
the city, counted by a run made before the switch bit.

Two things wore that number and only one of them was about a table. The
unreadable table still costs the city's whole commercial half; what is gone is
any claim about how much land that is. And the exclusion's own written reason —
*"the Multnomah slice is the Mountain Park PUD"* — is scoped to the 9% of the
city that a Multnomah-only corpus could see, which makes it the same mistake as
the ledger it was reasoned from. That one is not ours to fix: it is an owner
decision, and it is on [docs/HUMAN_TODO.md](docs/HUMAN_TODO.md) as one.

**The brief for the top of that queue, gathered but not spent.** Table 315-4
governs PMD, MR-1, MR-2, HDR, VA, SHD and RCHDR, prints seven cells in every
row, and `ragged.py` puts it at zero — so the columns are readable by position
and were checked that way on every row, not just the one being quoted. What
they say:

| | PMD | MR-1 | MR-2 | VA |
|---|---|---|---|---|
| min lot | None`[1]`/`[2]` | None | None | None |
| front | 15, garage 20 | 15, garage 20 `[3,4]` | 15, garage 20 `[4]` | 10 `[6,7]`, max 18 |
| rear | 30 `[10]` | 20 `[5,10,11,12]` | 20 `[5,10]` | None `[6,7]` |
| side | 30 `[10]` | 5 / 7 / 15 by storey `[…14,15]` | 5 / 7 / 15 by storey `[…14,15]` | None |
| height | None | None | None | 45 |
| separation | 10 | None | None | 20 between multifamily |

`min_lot_sqft` is not the table's "None": ZDO 845.01 states *"7,000 square feet
for a quadplex"* with no district limitation, and the stored `zdo.845.txt` runs
from `845.01` to its ordinance history with no applicability clause above it —
so the section reaches every district, which is the reading the eight already
encoded R-zones use. Table 315-1's note `[8]` signposts Section 845 on the
`R-5 – R-30` and VR cells only; PMD through RCHDR read a bare `P`, which
signposts nothing and excludes nothing.

**The one question that needs deciding before MR-1 is written, and it is worth
deciding carefully because MR-1 is 839 lots.** The side setback prints a storey
ladder — five feet at one storey, seven at two, fifteen at three — and note
`[14]` adds: *"If the side lot line abuts an Urban Low Density Residential,
VR-5/7, or VR-4/5 District, the minimum side setback for a two-story building
is 10 feet."* The pod is two storeys, so the binding figure is seven or ten
depending on who the neighbour is, and who the neighbour is is a site fact
nothing measures.

`abuts_nonresidential_zone` is the same shape and its handling is the
precedent: `assume=None`, and the restrictive number sits in the **base** so
that an unknown leaves it binding. Here the restrictive number is in the
*variant*, and the vocabulary has no negation to invert it — a variant of ten
`when: [multi_story, abuts_low_density_zone]` would simply not fire on an
unknown and leave seven standing, which is the false-GREEN direction. So the
conservative encoding puts **ten** on `when: [multi_story]` and says in the
comment that seven is the figure where the side line does not abut low-density
land. That is the Milwaukie side-yard result again — *the five foot side yard
is really eleven* — and it is a decision about which of two printed numbers the
screen carries, so it belongs in a commit of its own rather than at the end of
this one.

**Two zones now owe a required standard, and both owe deliberately.** The guard
`test_no_observed_zone_owes_a_required_field` asserted `owing == []` for months
and went red on the rebuild, correctly: Wilsonville `OTR` (103 lots) owes
`max_height_ft` because `4.123(.06)A` hands height to an Old Town design book
the corpus does not hold, and Happy Valley `MURX` (14 lots) owes five standards
because Table 16.22.060-2 is headed MUR-M1/M2/M3 and carries no MUR-X column at
all. Neither is new; both were written months ago with the deferral spelled out
in the zone's notes. What was new is a ledger that could see the lots and
therefore ask. The guard is now a declared-exception test in the shape the
reach ledger uses — a silent gap and a declared one look identical in a ledger,
so the declaration has to be somewhere a change breaks, and `== []` had become
a lie in the other direction.

**Chasing that one table down produced a check worth more than the table.** Lake
Oswego's own preamble says *"a blank cell in a use table indicates that the land
use is prohibited"*, and the extractor drops blanks: `Cemetery` arrives as one
cell, `Group care home` as two, `Dwelling, live-work` as seven, `Residential use
at R-5 density or greater` as eleven — all against sixteen column heads. **A
dropped cell is worse than a missing one**: it does not merely lose a
prohibition, it shifts every cell after it, so a permission read off such a
table can silently be the neighbouring zone's. That is the question worth asking
of the whole corpus, and `flats/encode/ragged.py` asks it — a use table
linearises to runs of consecutive verdict-cell lines, and if extraction kept
every cell then every run in a table is exactly as wide as the table.

**The corpus separates cleanly, and only one document is broken.** Lake Oswego
`50.03.002` at 64 percent of its rows short of its own widest; every other
document in the store at zero. No threshold was tuned — that is simply what the
numbers do, which is why `flats/tests/test_ragged.py` can be a test rather than
a report. It fails in both directions: a second ragged document means something
was fetched that nothing may be encoded from, and Lake Oswego falling to zero
means the re-fetch worked and the ten `column` rulings are owed a re-read.

The version of this check that got the answer wrong is worth recording, because
it got it wrong in the direction that matters. A first pass matched a cell as a
single verdict letter with footnote markers, and reported **ZDO 315 as 26
percent ragged** — the very table the nine Clackamas districts' `quadplex_allowed`
is read from. It was the *pattern* that was short, not the rows: a limited use
prints `L[1],C[2]`, the pattern missed it, and each miss broke one eleven-cell
row into two short ones. Table 315-1 is whole, all eleven wide, and the test now
asserts that specifically. **A reader that cannot spell a cell reports the page
as damaged**, which is the same failure as a reader that cannot see one
reporting the page as clean — both are the reader, and only the second one is
quiet about it.

**The cause is one word, and it is not Lake Oswego's.** `_Table.render()` in
[flats/provenance/fetch.py](flats/provenance/fetch.py) has two paths. The grid
path lays a table's cells out in aligned columns and an empty cell survives as
padding — that is the path the extractor was taught in `/6` precisely so table
geometry would stop dying. The flow path is the fallback, taken when a table
renders wider than `_GRID_LINE_MAX` (400 characters), and it writes one cell per
line:

```python
body = "\n".join(
    part for r in grid for c in r for part in c.split(_CELL_BLOCK) if part
)
```

`if part` is the bug. It drops an empty cell rather than emitting an empty line,
so on the one path where alignment is already given up, the count goes too.
Lake Oswego's use table has sixteen zone columns plus a use-specific-standards
column carrying strings like "WLG zones: § 50.03.003.1.a; NC, GC, EC and CI
zones: § 50.03.003.2" — comfortably past 400 — so it takes the fallback, and a
code that says a blank means *prohibited* loses every prohibition it states that
way.

**Fixing it is one line and re-fetching is not.** The store hashes extracted
text, so changing the algorithm moves the hash of every document holding a wide
table with a blank in it, and a citation is a line number. The corpus is
already carrying this debt: 173 of its 178 documents were extracted by
`flats-html-text/7` and the code is at `/8`, so nothing has been re-extracted
since the footnote-separation change. 129 of the 178 came from HTML and could be
affected; 49 came from PDFs, where this code never runs. How many actually move
cannot be known without doing it, because the raw HTML is not kept — only the
extracted text is.

What *can* be said is the shape of the exposure, and it is worth saying because
"unmeasurable" is the kind of word that stops work. The two paths leave
different fingerprints: a grid row is one line carrying several cells separated
by runs of two or more spaces, a flow cell is a line to itself. Counting runs of
consecutive short lines with no internal double space finds **44 documents
holding flow-path tables at all, 20 of them with uneven runs** — the largest
being unincorporated Multnomah's `39.cfu` (158 runs) and `39.efu` (139). That is
a hint and not a count, and the proof is in this list itself: it flags ZDO 315
at 18% uneven, and ZDO 315 is the table the nine Clackamas quadplex values are
read from, which `ragged.py` — the check that knows what a cell looks like —
puts at zero. A heuristic that cannot tell a table cell from a short line of
prose overcounts, and this one does. So: **one document proven damaged, and at
most 44 that could be, of 129 that could have been.** That makes this a decision
rather than a fix, and it is on [docs/HUMAN_TODO.md](docs/HUMAN_TODO.md) as one.

**`orphans` asks the question from the neighbours' side.** For each `(layer, field)` where
the layer holds the field in no zone and in no default, while at least half the other live
layers hold it, the pair is an asymmetry worth explaining. Seven rows on first run, two
real, and both were `setback_garage_entrance_ft` — which `consumed.py` already reports as
the largest silently-unread field in the system (66 values, 10 jurisdictions), while both
catalog pods are `config: rear_court` and have no garage. **Ruled 2026-09-08: no
garage.** `setback_garage_entrance_ft (the pod has no garage)` is now a literal in
`PaperFit.excluded`, which `consumed.py` reads as a *declared* exclusion rather than a
silent one, and `orphans()` takes the declared set as its `declared` argument and stops
asking. The worry that made this a question rather than a default — that a ruling about
our product goes silently wrong when the product changes — is answered by
`test_no_catalog_design_has_a_garage`, which fails the day a `tuck_under` design is
added. The general shape: a ruling about the design is only safe when a test binds it to
the design.

**A rear court is depth, and until 2026-09-08 nothing charged a lot for it.** Both pods
park six cars behind the building; `Parking` now carries `stall_depth_ft` (18) and
`aisle_ft` (24) and exposes `court_depth_ft`. `paper.court_depth(design, rules)` raises
either from the zone where it states one — `parking_stall_depth_ft`,
`parking_aisle_two_way_ft`, `max()` in both cases, never substituting a one-way aisle —
and returns the standards it actually used, so a court resting on the design's assumption
is distinguishable from one the code supplied. **A missing aisle width is not a missing
standard**: Portland, Milwaukie and Wilsonville each dimension a stall for this building
and state no aisle, all three refused on the record with the exclusion sentence quoted
(ORS 197A.400 clear-and-objective), and the pod still has to turn round. The 24 ft is
what quadfit's site-plan generator already draws.

The court and a required rear yard **overlap rather than stack** — parking in a rear yard
is permitted in every Oregon code read for this — so the charge is `max(rear, court)` in
`paper_fit` and `max(0, court - rear)` on top of the fit threshold in `screen`. A zone
stating no rear setback pays the whole court. Measured impact: **all 120
quadplex-permitting zones need 12–42 ft more depth, mean 27, none exempt**
(court resolves to 42.0 / 42.5 / 43.0 ft across 61 / 32 / 27 zones). What is still uncharged is the
court's *width* (six stalls ≈ 54 ft across) and the driveway reaching it; both can only
raise the requirement, so the paper fit remains the optimistic bound.

**`Fit.required_ft`, and the false GREEN it closes.** `Fitter.fit` tries the flipped
orientation by searching the envelope at the design's *depth* and needing its *width*,
but records `width_ft`/`depth_ft` unrotated. `screen._checks` compared `best_depth_ft`
against `depth_ft`, so whenever the flip won it measured the found run against the wrong
dimension: a 40×50 envelope against a 56×36 pod reads 50 ft found versus 36 ft needed and
passes, on a lot holding no 56 ft run at any angle. `Fit.required_ft` recovers the real
requirement as `best_depth_ft - slack_ft` — from the slack the search actually set, so it
cannot drift — and the fit check now reads it. `Screening.fit_slack_ft` likewise reports
the check's slack, not the raw geometry's, because the number a developer argues with has
to be the number the verdict turned on.

**Footnote scope, and the one way to narrow it.** A footnote governs every value quoted
from its *region* — the run of lines between the previous notes block and this one's
heading — not the cell its marker sits on. That is wider than the truth on purpose:
telling a marker on a cell from a marker on a row from a marker on a column head, out of
extracted PDF text, is exactly the judgement that gets made wrong silently, and an
under-scoped footnote is a false GREEN.

The cost is real and it points the other way. Gresham's Table 4.0420 note 2 is one
sentence about the CMF district; it shares a notes block with all seven Corridor
columns, so it sat over every one of them. Two of those columns prohibit the pod
outright with no marker of any kind on the cell — and an unanswered note over a use row
is precisely what stops the resolver treating a prohibition as *settled*, so both read
as districts whose gate might open and both were owed twelve standards behind a gate
that is shut.

So `zones:` on an `unmeasured` disposition records the narrowing, written against the
note's own words and checked against the layer — a narrowing naming a zone the
jurisdiction does not have is refused, because a cap cancelled by a typo is
indistinguishable in every report from a note that never qualified anything. No
narrowing is the default and it stays the safe one.

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

**Preemption has a direction.** `preempts: true` answers the question outright — ORS
92.031(2)(b) settles which standards a middle housing land division is measured against
and a city may not decide that differently either way. `preempts: cap` states the
*strictest* a local layer may be and lets a looser local number through: OAR
660-046-0220 bars a city from requiring more than one parking stall per unit but does
not oblige one to require any, and Portland requires none. Reading the cap as a
substitute handed every Portland lot four stalls the city does not ask for — about 1,300
sq ft of a site that has to fit the pod, its parking and its access. Which way "looser"
runs is read off `FieldDef.is_maximum` rather than written into the preemption, because
it is a property of the standard: a minimum gets looser as it falls, a maximum as it
rises.

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
| ✅ | `score/screen.py` — GREEN/YELLOW/RED/UNKNOWN with split attribution (tightest vs dominant) |
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

---

## 13. Conditional verdicts — configurations, not answers

*Added 2026-08-12, after the first real chapter was read. It corrects §4 and §5: the
screen does not emit a verdict per lot. It emits which **configurations** clear, and
under what conditions.*

### There is no unconditional GREEN

Portland's Table 110-4 states `30 ft. [3]`, and footnote 3 says additional height may be
allowed. Table 110-7's lot-area gate has its own footnotes. Almost every number in a real
code is a base case with exits attached. A screen that reads only the base case is not
conservative — it is wrong in both directions at once: too strict where a footnote loosens
the standard, too generous where one tightens it.

So a result reads *"GREEN under affordable"*, *"GREEN under 2 stories"*, *"GREEN with
design variant 2"*. Never bare GREEN.

A **configuration** is three things at once:

| Part | Example | Who decides |
|---|---|---|
| Building variant | pod design 2 of 10 | the catalog (§5) |
| Elective conditions | affordable at 60% AMI, mixed use, bonus program | the developer |
| Assumed site facts | corner lot, abuts alley, on sewer, slope band | our data — **overridable** |

**Site facts are not deterministic from the UI's point of view.** On a single lot the user
may override any of them, because they have been there and we have not. At two or more
lots the screen uses our best understanding, because there is nothing to override against.

### What the three colours mean now

> **Superseded by §14.** REVIEW below covers two unrelated things — a path the
> developer can apply for, and a gap in our own encoding — and merging them hid
> the first. There are four colours, not three.

**RED — no configuration in the catalog produces a legal fit.** That is the only honest
red, and it is deliberately hard to earn. Anything that clears *somehow* is not red.

**GREEN — at least one configuration clears, and everything under it is solid:** signed
rules, confirmed site facts, conditions the developer controls.

**REVIEW — a configuration clears but something under it is not solid:** an unsigned rule,
a site fact we are guessing at, a condition we cannot confirm from data, or a check inside
tolerance (§4). Tolerance still never manufactures a GREEN.

This preserves the recall bias at a larger scale than §4 stated it. A lot buildable only
under an affordability program *has a legal path*, and burying it in RED deletes exactly
the deal the screen exists to find.

### Ranking, when several configurations clear

Fewest concessions first, then most units. A configuration that needs nothing from the
developer beats one that needs an affordability covenant, even if the second yields more
doors — the first is the one that can close without a program. The ranking is a policy
knob like tolerance, not a constant.

### The search, not the sweep

Ten designs × a handful of binary conditions × 400k lots is hundreds of millions of
evaluations. It is also almost entirely wasted, because the screen already reports **which
constraint is binding**.

    1. Evaluate the baseline configuration.
    2. Read the binding constraint.
    3. Explore only conditions that move that number.
    4. Repeat until the lot clears or the catalog is exhausted.

A lot blocked by minimum lot area never explores the height toggles. Typical lots resolve
in one or two evaluations. This is what makes single-lot override instant — the same
search on different inputs — and what makes county scale affordable at all.

### Surfacing levers for a batch

A lever is worth showing when flipping it would change a verdict **for at least one lot in
the selection**. That falls out of binding-constraint attribution: collect the binding
constraints across the batch, map them back to the conditions that move them, and offer
only those. Selecting 400 R5 lots offers "affordable?" only if affordability touches a rule
that actually binds one of them.

### What this changes in the encoding

1. **Footnotes are evidence, not decoration.** The marker on a cell and the text of the
   note are captured together and attached to the value they modify.
2. **Conditions are named once**, in a registry with the same discipline as
   `flats/rules/fields.py` — a condition is elective or a site fact, and nothing else may
   invent one inline.
3. **A value carries variants.** `5 ft., or 10 ft. when affordable`, each variant with its
   own citation and its own signature. A variant nobody read is untrusted exactly like a
   base value nobody read (§2).
4. **The screen takes a configuration** and returns slack and binding constraints for it.
5. **Storage is per lot per qualifying configuration**, not one row per lot.

Items 1–3 are foundation and do not depend on the web app existing.

---

## 14. Yellow is an ask, not a doubt

*Added 2026-08-12. It corrects §13's colour table, which used REVIEW for two
unrelated things and so made one of them invisible.*

### The conflation

§13 said REVIEW means "a configuration clears but something under it is not solid."
That covers an unsigned rule, a guessed site fact, and a measurement inside tolerance
— all of which are **our** failures, and all of which are supposed to disappear as the
encoding finishes. Review is not a destination; it is a work queue with a burn-down.

It does not cover the case that is not a failure at all: **we know the answer, and the
answer is "you would have to ask."** A pod one foot over a front setback is not
uncertain. It is certain, and it is an adjustment application. Filing it under the same
colour as an unencoded standard hides a real, common, and usually-granted path behind a
label that says "we are still working on it."

### Four outcomes

| | Means | Whose queue |
|---|---|---|
| **GREEN** | Clears as-of-right under some configuration. No ask. | nobody's |
| **YELLOW** | Clears, but only with a discretionary approval. Labelled with which. | the developer's — file for it |
| **RED** | No configuration clears, and no relief the code offers can close the gap. | nobody's. Dead. |
| **UNKNOWN** (grey) | We cannot answer yet. | **ours** — encode it, fetch it, verify it |

Grey carries a reason code and is meant to shrink. Yellow is not, and should not: it is
what the regulatory world actually looks like. Counting them together makes the encoding
backlog unmeasurable, which is the reason for the split.

### Relief is an elective condition, not a colour

Applying for an adjustment is something the developer chooses, exactly like electing
affordability or picking design variant 2. So it needs no new machinery — it is a third
`kind` in the condition registry (§13 item 2), and the colour falls out of the existing
configuration search:

* best configuration needs no relief → **GREEN**
* best configuration needs relief → **YELLOW**, labelled with the tier and the gap
* nothing clears even with the deepest relief available → **RED**
* we could not evaluate → **UNKNOWN**

### Yellow is a scale, not a bucket

The size of the miss selects the tier, and the tier is what the code says, not what we
wish:

| Tier | Meaning |
|---|---|
| `as_of_right` | no approval needed |
| `administrative` | staff-level decision, no hearing |
| `discretionary` | public review, hearing, appealable |
| `unavailable` | nobody may waive this — state building code, fire access, floodplain |

Only `unavailable` earns a RED. A dimensional miss essentially never does on its own,
which is the correction §13 needed: today a one-foot setback miss beyond tolerance is
RED, and that is wrong.

### Tolerance and relief are different uncertainties

They were both REVIEW, and they are not the same thing at all:

* **Tolerance** is epistemic — the raster is conservative to half a foot, the DEM has a
  three-foot noise floor. We may be measuring wrong. → **UNKNOWN**.
* **Relief** is legal — we measured correctly, and the code offers a path. → **YELLOW**.

### Two guardrails, same recall bias as everything else

1. **Relief is encoded, not assumed to be absent.** Portland's adjustment chapter gets
   fetched into the provenance store and read like any other rule, so a yellow can say
   *why* it is yellow and cite it.
2. **Unknown waivability defaults to available.** A dimensional standard with no encoded
   relief path is treated as `discretionary`, not `unavailable`, and the result carries
   `RELIEF_UNCONFIRMED` so the claim names its own gap. A false red deletes a target
   silently; a false yellow costs one review.

   **Use permission is the exception.** A zone that bars the use is RED, not yellow,
   unless a conditional-use path is encoded. Codes enumerate conditional uses explicitly,
   so silence there is evidence of absence in a way that silence about adjustments is not.

### Posture — which asks are worth making

Tier availability is a fact about the code. Whether the team will *pursue* an ask is a
policy knob, `posture` in `flats/config/relief.yaml`, exactly parallel to tolerance:

    posture: administrative     # as-of-right | administrative | discretionary

It filters the buy list; it never changes a colour. Re-running the county at
"as-of-right only" versus "we will file for adjustments" is a report-time sweep, seconds,
not a rebuild.

---

## 15. The source layer — what a breadth probe found

*Added 2026-08-12. Six real fetches across five codifiers, run to discover what the
framework must support rather than to encode anything. The result changed the
provenance layer.*

### One in six

| Jurisdiction | Platform | Plain HTTP result |
|---|---|---|
| Gresham | own PDF | 114 KB of code text |
| Portland (33.805) | portland.gov HTML | 3.5 KB of nav bar and footer, no code |
| Troutdale | Municode | **empty** — renders in JavaScript |
| West Linn | Zoneomics | table of contents, and a third-party restatement |
| Fairview | Code Publishing | 403 |
| Milwaukie | eCode360 | 403 |

**The provenance store accepted all six.** The subsystem whose entire purpose is
making evidence checkable would have let a reviewer sign over an empty file. That is
the worst failure mode available to this project, because it does not look like a
failure — it looks like coverage.

### Three requirements, now built

**A strategy ladder, not a single client.** Browser impersonation recovers both 403s;
Code Publishing accepts `chrome124` and refuses `chrome131`, which is not something
anyone could have reasoned out. Treating a blocked host as an unavailable one would
have restricted the project to jurisdictions with friendly web servers and made it
look like a data gap. `flats/provenance/sources.py`.

**A plausibility guard.** A document is refused unless it reads like regulation —
measured as lines carrying a section number or a dimensioned standard, by count and
by share. Validated against all six samples: it refuses the empty file and the nav
bar, accepts both real chapters. The character floor is deliberately low, because
single sections are genuinely short and a floor high enough to catch a nav bar would
teach everyone to pass `--allow-thin`.

**Source authority.** A city's own site and its contracted codifier publish the
ordinance. An aggregator publishes *its reading* of the ordinance. Both are storable;
only the first may back a verified value. Quadfit cited an aggregator for West Linn.

### Still open

**Municode is JavaScript-only.** It serves a large share of Oregon cities and no
amount of impersonation helps — it needs the underlying API or a rendered fetch. Until
then those jurisdictions fail loudly instead of silently, which is the improvement;
the coverage gap itself remains.

**Landing pages are not documents.** Portland's HTML route for a chapter is furniture;
the PDF is the artifact. Which URL holds the real text is per-jurisdiction knowledge
and belongs in the layer file rather than in whoever is running the command.
**Built — see §18.**

### A structural gap the reading surfaced

Fairview's VSF zone does not state its own dimensional standards. It says the R-6
standards apply, in a different chapter, *and* carries a conflict clause naming which
chapter wins where they disagree. The rule model has state → county → city layering
with `preempts`, and nothing for **zone-to-zone incorporation inside one
jurisdiction**. Encoding VSF by copying R-6's numbers into it would produce values
that silently stop tracking their source the first time R-6 is amended.

This is exactly the kind of change the encoding UI depends on: a reviewer must be
able to see that VSF's front setback *is* R-6's, not a duplicate of it. **Built — see
§17.**


---

## 16. One standard, more than one number

Half the numbers in a zoning table have a footnote marker on them. *"Front setback:
10 ft. — 5 ft. where the development is affordable."* *"Minimum lot area: 3,000 sq.
ft.; 2,500 sq. ft. on a corner lot."* This is not an edge case in the code, it is the
ordinary shape of the code, and until this pass the rule model could not hold it.

The old behaviour was to refuse the whole value. That is safe in the sense that
nothing wrong gets encoded, and useless in the sense that the most common shape in
real zoning becomes unencodable — which is the same as saying the jurisdiction cannot
be finished.

### The three wrong ways to do it

**Encode the base and drop the footnote.** Every project that takes the incentive is
screened against a standard that does not apply to it. Silently.

**Encode the footnote and drop the base.** The same error, reversed, for every project
that does not.

**Encode both as separate fields.** `setback_front_ft` and
`setback_front_ft_affordable`. Now the screen has to know which to read, that
knowledge lives in code rather than in the rule file, and the field registry grows a
combinatorial tail nobody can review.

### What a variant is

One `Value`, one field name, one base number, and a list of exceptions — each with
the conditions it applies under and its own citation:

```yaml
setback_front_ft:
  value: 10
  variants:
    - value: 5
      when: [affordable]
      cite: "PCC 33.120.205"          # inherited if omitted
      quote: "pdx/33.120.txt#L12"
    - value: 4
      when: [affordable, corner_lot]
```

Reading it is `value.under(conditions)`, and the rules are:

* a variant applies when **every** condition it names is active;
* the **most specific** match wins — `affordable + corner_lot` beats `affordable`,
  because a code that wrote both meant the pair to differ from either alone;
* two **equally specific** matches are *not* resolved. Picking one would be guessing
  between two encoded rules on no basis, and the guess would be invisible in the
  output. The tie is reported, the resolution verdict becomes `ambiguous`, and the
  lot goes to UNKNOWN.

That last rule is the recall bias applied to our own encoding: not knowing which of
two numbers governs is a gap in our work, so it lands on our backlog rather than in
a colour that reads like an answer.

### An exception is signed on its own

A reviewer who confirmed *"10 ft."* has not confirmed *"5 ft. where affordable."*
Those are different sentences, usually in different chapters. So the fingerprint
includes the variant's conditions, and the base and each exception hash apart:

* `flats-review sign … setback_front_ft` signs the base;
* `flats-review sign … setback_front_ft --when affordable` signs that exception;
* the queue lists them as separate rows, so a standard with a verified base and a
  draft footnote reads as the half-finished thing it is rather than as done;
* amending the chapter an exception cites withdraws that signature and leaves the
  base standing, and vice versa;
* `Effective.trusted` is false when the exception that applied is unsigned — a
  verified base cannot certify a number the reviewer never read.

### Levers fall out of it

`Value.levers` is the set of conditions that change *this* standard, and
`ZoneResolution.levers` the union across a zone. That is exactly what the batch view
needs: offering every registered condition as a toggle on every selection would bury
the two or three that actually move a number some lot in the selection is bound by.
The lever list is derived from the encoding, so it grows as the encoding does and
never needs maintaining separately.

### What this does not do

It does not handle **zone-to-zone incorporation** — one zone adopting another's
standards by reference. A variant is one field with several numbers; incorporation is
one zone with another zone's fields. That is §17.

---

## 17. A zone with no standards of its own

Fairview's VSF zone states no dimensional standards. It says the R-6 standards apply,
in a different chapter, *and* carries a conflict clause naming which text governs
where the two disagree. §15 flagged this as a structural gap; it is now encodable.

### Why copying is the wrong fix

Pasting R-6's numbers into VSF produces an encoding that is correct exactly once. The
copies carry R-6's citation but not its identity, so the first time R-6 is amended the
fetch layer flags R-6's document as changed, withdraws the signatures on *R-6's*
values, and leaves VSF sitting there verified against a sentence that no longer says
what it did. Nothing in the system can notice, and nobody reviewing VSF has any reason
to look at R-6 at all.

The reference has to *be* the encoding.

```yaml
zones:
  R-6:
    setback_front_ft: 20
    min_lot_sqft: 6000

  VSF:
    like: R-6                      # shorthand: inherits the zone's cite_default
    setback_front_ft: 10           # what VSF states for itself

  MUR:
    like:
      zone: R-6
      wins: referenced             # the adopted chapter governs on conflict
      cite: "FMC 19.117.020(C)"    # where the incorporation itself is stated
```

### How it resolves

The reference is followed, not flattened. Zone blocks apply least-authoritative
first — the referenced zone, then the borrowing one, reversed when `wins:
referenced` — and each resolved value keeps the provenance of the block it was
actually read from. So VSF's `min_lot_sqft` cites *FMC 19.105.040 Table 1*, and
`Resolved.via` says `R-6`. The detail page can state the thing that is true: VSF's
lot minimum **is** R-6's.

Chains are followed to the end (`VSF → R-7 → R-6`), and the zone code is looked up
in the layer and then up the hierarchy, so a city adopting a county zone is the same
shape as adopting one of its own.

Two ways it can fail, both ours and both on the backlog rather than in a colour:

| | reason code | what it means |
|---|---|---|
| referenced zone not encoded | `ZONE_REFERENCE_MISSING` | coverage gap — encode R-6 |
| zones adopt each other | `ZONE_REFERENCE_CYCLE` | encoding bug — no standards exist to resolve |

### The claim to borrow is itself a rule

`like:` is a sentence somebody read, and an unread one can point at the wrong zone —
which hands an entire zone the wrong numbers, with every individual value verified
and nothing on screen to suggest a problem. So it is signed like any other rule,
under the pseudo-field `like`:

```
flats-review show or/…/fairview VSF like     # prints the clause and its evidence
flats-review sign or/…/fairview VSF like --reviewer sjk
```

It queues while unread, it blocks the zone from being trusted, and its fingerprint
covers both the zone code *and* the conflict rule — flipping `wins` changes exactly
which numbers govern wherever the two texts disagree, and is far easier to edit
unnoticed than the zone code is.

Asking to review a borrowed field where it is not printed is refused with a pointer
rather than a "no such field", because the number is not missing; it is somewhere
else, and reviewing it here would mean reviewing a copy.


---

## 18. A jurisdiction says where its code is

§15 found that one document in six came back usable, and that the knowledge of
*which URL serves the actual ordinance* — as opposed to a landing page, a table of
contents, or a JavaScript shell that renders one — lived nowhere but the shell
history of whoever was encoding that week. Two consequences, both quiet:

* a coverage gap someone already solved gets re-solved, or does not;
* **nothing could re-fetch the corpus**, so nothing watched it for amendments. The
  encoding was a snapshot of what the web looked like the week it was made, and its
  signatures would go on standing over sentences that had since changed.

So the layer file declares it, beside the rules it backs:

```yaml
code:
  # Portland's HTML route for a chapter serves navigation furniture; the PDF is
  # the artifact.
  - id: "33.110"
    url: https://www.portland.gov/sites/default/files/code/110-sd-zone_2.pdf
    title: Chapter 33.110 Single-Dwelling Zones

  # Code Publishing refuses a plain request and accepts curl-cffi impersonating
  # chrome124 — measured, not reasoned about. See flats/provenance/sources.py.
  - id: "19.115"
    url: https://www.codepublishing.com/OR/Fairview/html/Fairview19/Fairview19115.html
    start: "19.115.010"     # slice to the section actually read
    nth: 2                  # a chapter PDF lists its sections before printing them
```

The store path is derived — `{layer}/{id}.txt`, with the Census GEOID prefix dropped,
because a quote is something a person reads in a review queue and
`or/multnomah/portland/33.110.txt#L454` is legible where the GEOID form is not. So a
quote written by hand and a document fetched by the registry land in the same place
without anybody coordinating.

```
python -m flats.provenance.fetch --layer or/multnomah          # a county brings its cities
python -m flats.provenance.fetch --all --check                 # the corpus watch: report drift, store nothing
python -m flats.provenance.fetch --audit                       # reconcile without fetching
python -m flats.provenance.fetch <path> <url> --refresh --repoint   # accept a shift, move the citations
```

A sweep does not stop on a bad document. The point of a corpus watch is the report at
the end, and a run that halts on the first 403 tells you about one city instead of
eighty.

### When a document is renumbered rather than amended

A citation here is a line number, which is what makes provenance checkable and also
what makes it brittle. Gresham republished Section 4.1400 with one sentence inserted at
line 612. Every quote below it still *resolved* — to the wrong words. Nothing crashed
and nothing went red; the store's hash said the document changed, and the only two
choices were to refuse the refresh forever or accept it and re-read a hundred citations.

`--repoint` (2026-08-27, `flats/provenance/repoint.py`) is the third choice, and it
turns on one distinction: **a line number is a pointer; the evidence is the words.**

- Aligns old text against new with `difflib`, keeping only the lines that survive
  **byte for byte**.
- Rewrites every citation into that document across `config/jurisdictions/` and
  `config/footnotes/` — as a substring swap on the raw file, never a YAML round-trip,
  so the comments those files are mostly made of survive intact.
- A quote naming even one line whose words changed is **stranded whole** and reported.
  A half-migrated citation is worse than a stale one, because it looks migrated.
- A span with a line inserted inside it **widens** to cover it. The reviewer sees the
  new sentence; a citation may show more than it did and never less.
- Verifications follow. A signature's fingerprint hashes the quote string, so a
  re-point would orphan every review on the document — making a renumbering
  indistinguishable from an amendment. `readdress()` re-issues the spared ones with the
  same reviewer and date and a note saying what moved, appended to the append-only log
  so both entries stay on disk. Only where every cited line survived verbatim, and only
  where the standing signature still matched before the move: a review already orphaned
  for another reason stays orphaned, because repairing it as a side effect of an
  unrelated refresh is the one thing this whole apparatus exists to prevent.
- Test files that pin quotes are **reported, never rewritten**. A tool that edits an
  assertion so it passes has deleted the assertion.

On the run that motivated it: 100 citations moved, 0 stranded, 62 values would have kept
their review.

**Two ways the watch cries wolf, both fixed the same day.** A declaration without an
`end:` marker swallowed the page furniture below the code — Clackamas ZDO 202 carried an
upcoming-meetings panel, so it "changed" every week with no amendment behind it. And
`--allow-thin` typed at the keyboard and not written into the `code:` entry left Gresham
9.0200 refusing on every sweep for a document nobody was going to change their mind
about. **A flag used once at a prompt is a flag somebody has to remember forever.** Put
it in the declaration.

### Three sets that ought to agree

`--audit` reconciles what is **declared**, what is **stored**, and what values actually
**cite**. Each mismatch is a different job, and one "coverage" number would hide which:

| | meaning | who owns it |
|---|---|---|
| `UNDECLARED` | a value cites a document nobody declared | **the loud one** — nothing will re-fetch it, so an amendment passes unnoticed while every value on it reads as verified |
| `UNFETCHED` | declared, never stored | ordinary work: run the fetch |
| `uncited` | stored, nothing points at it | usually a chapter fetched ahead of the encoding |

Only the first two fail the audit. Fetching ahead of encoding is the normal order of
work.

---

## 19. What blocks a jurisdiction, and what unblocks it

The encoding surface is 603 values across 19 jurisdictions, and the only status
line over it read **`0.0% verified`**. True, and useless. It cannot tell apart:

* a city nobody has found a code URL for — hours of hunting, no reviewing possible;
* a city where every number is written, quoted and waiting on a signature — one sitting.

A queue that cannot distinguish those sends work to people who cannot do it. So
readiness is a **ladder**, and a jurisdiction sits on the *first rung it fails*:

| rung | means | who owns it |
|---|---|---|
| `no_zones` | nothing encoded here at all | encoder |
| `no_source` | zones written, no document declared to read them from | whoever hunts URLs |
| `unfetched` | documents declared, not in the store | one command |
| `unquoted` | values pointing at no text — unreviewable as written | encoder |
| `no_evidence` | quotes that do not resolve to stored text | fetch, or a moved line range |
| `unsigned` | everything present; waiting on somebody to read it | **reviewer** |
| `stale` | read, but the source has moved since | reviewer, re-read |
| `ready` | every value verified against text that still says it | nobody |

**Ordered by what blocks what, not by severity.** Signing a value whose evidence
was never fetched is not possible, so `unfetched` outranks `unsigned` however few
documents are missing. That ordering is the whole product: it turns "603 drafts"
into one sentence per jurisdiction naming the next command.

```
python -m flats.encode.review plan                       # the whole queue, worst first
python -m flats.encode.review plan --layer or/multnomah --verbose
```

Real output, unedited:

```
19 jurisdiction(s): no_zones=1, no_source=16, unquoted=2

no_zones     or/multnomah/maywood-park    0/0    verified  -> encode this jurisdiction's zones: nothing is written yet
no_source    or/clackamas/happy-valley    0/61   verified  -> find the URL that serves the ordinance text, and declare it under `code:`
unquoted     or/multnomah/portland        0/42   verified  -> add quotes: a value pointing at no text cannot be reviewed
```

That is the finding, and it is not the one the percentage implied. The corpus is
not *under-reviewed* — **16 of 19 jurisdictions have no declared source at all.**
No amount of reviewing moves them. §18's `code:` block is the unblocking work,
and it is a different job than reading numbers.

### Two things the counts refuse to hide

**Exceptions and borrowings count as values.** A footnote (§16) and an
incorporation clause (§17) are each a number somebody has to read. Counting only
base values would report a jurisdiction finished with unread rules inside it — the
exact failure the variant work existed to prevent, reintroduced at the status
layer.

**Ties break on how much is already verified, descending.** Among cities on the
same rung the one closest to done comes first, because a half-encoded city screens
no lots at all: finishing one jurisdiction is worth more than advancing three.

This is the surface the two remaining consumers read. A review UI renders the
ladder as its landing page; an agent picking up encoding work asks it what to do
next. Neither has to be told the order of operations, because the order is in the
data.

---

## 20. A number with no sentence behind it

The ladder put Portland and Fairview on `unquoted`: 93 values stating a standard
and pointing at no text. They arrived through the quadfit port, which carried
numbers and not citations. In that state a value is not merely unverified — it is
**unreviewable**, because the reviewer has nothing to read.

Re-reading a chapter to re-find a number somebody already read is the wrong shape
of work when the document is in the store and §12's corroborator is already
matching encoded values against it. So `flats.encode.attach` closes that loop:
where corroboration says *the document states this number for this zone*, the line
it matched on is written into the file.

```
python -m flats.encode.attach or/multnomah/portland \
    --doc or/multnomah/portland/33.110.txt --apply
```

**It attaches a quote. It does not verify anything.** A quote is where to look,
not evidence that somebody looked; the value stays a draft and stays on the review
queue. The whole gain is that the queue entry is now answerable in thirty seconds
instead of an afternoon.

### The refusals are the module

A wrong quote is worse than no quote, because the number and the sentence get
checked against each other and against nothing else — a citation aimed at the
wrong line manufactures agreement. So:

| refusal | why |
|---|---|
| never overwrites an existing quote | that is a reading somebody made; repointing it moves a citation with nobody deciding to |
| zone-keyed evidence only | a sentence in a fifty-page chapter does not say which zone it belongs to. Table columns and single-zone chapters do |
| refuses when the document states two numbers | that is a base case and an exception (§16). Quoting the base hides the exit |
| refuses footnoted numbers | same, even when the number itself agrees |
| refuses when the document contradicts the file | and says so loudly — one of the two is wrong, which is a reading question, not a citation to staple on |

**Comments in the rule file survive.** The edit is textual rather than a re-dump of
parsed YAML, because those comments record things nothing else holds — why *this*
URL is the one serving the ordinance and not the landing page above it. The edited
text is parsed and compared against the same transform applied to the parsed
document before anything is written; a mis-aimed edit fails loudly instead of
quietly rewriting a rule file.

### What it reached, and what it could not

Portland: **20 of 31** unquoted values now cite the table row that states them —
Table 110-3's setback rows and the triplex/fourplex minimum-lot-area table. The
11 it left are `quadplex_allowed` and `coverage_curve`: a boolean and a tiered
table, neither of which any reader can state as one number, so no machine gets a
vote on them.

Fairview: **1 of 51.** Chapter 19.115 is the VSF chapter, and VSF's dimensional
standards are *in Chapter 19.30* — the incorporation §17 exists for. Attaching
cannot invent evidence that is in a document nobody has fetched. It refused VSF's
rear setback outright, correctly: the chapter states 15 ft. basic and 50 ft. from
Fairview Creek's centerline, which is a variant pair and not a number.

That split is the honest picture of where the corpus is. Roughly a fifth of the
unquoted backlog was mechanical and is done; the rest is either a document nobody
has declared yet (§18) or a rule that needs a person.

---

## 21. Sixteen cities, one search

The ladder's loudest finding was not that the corpus is under-reviewed. It is that
**sixteen of nineteen jurisdictions have zones encoded and no `code:` block** — no
document declared, so nothing to fetch, so nothing to quote, so nothing that can
ever be signed. Reviewing harder does not move any of it.

Hunting those URLs by hand is the same search sixteen times, because Oregon cities
publish through a short list of codifiers whose URL shape follows from the city's
name. `flats.provenance.discover` runs it:

```
python -m flats.provenance.discover --all
```

**A hit is a lead, not a source.** What comes back is a code *index* — the front
door — and a `code:` entry needs the chapter carrying the zoning standards. Naming
the platform and proving it answers is the part that cost an afternoon per city;
picking the chapter still means reading a table of contents, and the tool says so
rather than guessing a chapter number into a rule file.

### Four verdicts, because they are four different next actions

| verdict | means | what to do |
|---|---|---|
| `index` | answered, and reads like a code index | follow it: pick the zoning chapter |
| `shell` | answered with a JavaScript frame | the code is there and a plain fetch will never see it |
| `missing` | 404 — the name guess was wrong, or the city is on another platform | try the next platform |
| `blocked` | every impersonation strategy refused | a fetching problem, not a coverage one |

The `missing`/`blocked` split is §15's finding turned into a report. A 404 says the
URL is wrong; a 403 says the fetcher is. They are opposite problems that look
identical in a log, and collapsing them sends somebody hunting for an
impersonation fix for a city that simply uses a different codifier. `fetch` now
carries what each strategy got, so the caller can tell.

`shell` earns its own verdict for the same reason. Municode's empty frame carries
"Municode Library" in its `<title>`, so a classifier that asks "does this mention
chapters?" *before* asking "is this a JavaScript shell?" calls the frame a code
index — a lead that is not there, which costs more than no lead.

### Municode is asked, not probed

The first sweep reported a Municode lead for all ten remaining cities, and it was
wrong. `library.municode.com/or/<anything>/codes/code_of_ordinances` returns the
same 6,095-byte frame whether the city is a client or not — the "not found" renders
in JavaScript. Every byte-identical response was being read as a hit.

That is the project's own failure mode wearing different clothes: a confident
answer produced by a tool that could not see. So Municode is asked a question its
URL cannot answer — **its client registry**, a plain JSON list of every jurisdiction
it publishes in a state:

```
https://api.municode.com/Clients/stateAbbr?stateAbbr=OR   → 55 Oregon clients
```

Gresham is not among them. Six of the ten "Municode leads" did not exist.

The registry distinguishes three states where the URL distinguished none: on the
list (a real lead, with its client id), not on the list (definitively elsewhere),
and *list unreadable* — which is a fetching failure and must never be reported as
"this platform publishes nobody here".

### What the sweep found

**9 of 15 have a lead. Six have none.**

```
index   codepublishing   Gladstone, Lake Oswego, West Linn, Wood Village
index   qcode            Milwaukie
index   municode         Oregon City, Troutdale, Tualatin, Wilsonville   (registry-confirmed)
—       no lead          Gresham, Happy Valley, Rivergrove, Johnson City,
                         Multnomah unincorporated, Clackamas unincorporated
```

The six with no lead are the ones publishing on their own municipal sites, which no
URL template reaches — Gresham's Community Development Code and Happy Valley's are
each a one-off. That is hand work, and now it is *six* pieces of hand work with
names on them rather than sixteen of unknown shape.

The four Municode cities needed a rendered fetch or that platform's content API to
read. §22 gets them without either.


---

## 22. The document a city adopted, not the page that renders it

Municode's library needs a token: `library.municode.com/api/CodesContent` answers
401 to anything without one, and its content renders through an OIDC-authenticated
SPA. The obvious next move was a headless browser — a dependency, a container, and
a rendering step between the ordinance and the citation.

It was not necessary. Reading the library's own JavaScript found a **public**
publication endpoint, and what it hands back is better than the rendered HTML:

```
GET  api.municode.com/Clients/stateAbbr?stateAbbr=OR   -> 55 Oregon clients
GET  api.municode.com/ClientContent/4976               -> publicationId 1951
GET  api.municode.com/PublicationPdfDownload/1951      -> a signed blob URL
                                                       -> 17.5 MB, %PDF-1.5
```

That is **the adopted code as a single PDF** — the document the council voted on,
not a page assembled from it. A citation promises a reader can go and check; that
promise is strongest against the artifact itself.

### Two details that decide whether the citation survives

**The declared URL is the unsigned one.** The blob URL carries a SAS signature that
expires in minutes. Writing it into a rule file would produce a citation that stops
working before anybody follows it, so `code:` holds
`https://api.municode.com/PublicationPdfDownload/1951` — stable, official — and the
fetcher follows the hop. One host answers a document request with the document's
*address*; that is now handled once, in `fetch`, for every caller.

**Authority stays with the declared URL.** The blob lives on
`mcclibrary.blob.core.usgovcloudapi.net`, which no registry classifies, so judging
the hop would demote an official document to `unknown` and block every value citing
it from ever being signed (§15). The hop preserves the authority of the URL a rule
file actually declares.

```
python -m flats.provenance.municode --all   # prints a paste-ready `code:` block
```

Which turns the platform gap from "two thirds of the corpus is unreachable" into
four `code:` blocks and a fetch — and makes every *other* Oregon Municode city
reachable the same way, which matters more than the four, because statewide
coverage is the standing goal.
### First city through the whole chain

Wilsonville, end to end: discovered → declared → fetched → on the ladder.

```yaml
code:
  - id: "4.planning"
    url: https://api.municode.com/PublicationPdfDownload/1951
    start: "PLANNING AND LAND DEVELOPMENT"     # Chapter 4, sliced out of a 3.5M-character code
    end: "Chapter 5"
```

22,352 lines stored; the jurisdiction moved `no_source` → `unquoted`. The slice is
deliberately generous — the whole land-use chapter rather than the zoning sections
alone — because over-slicing drops a standard the screen then never applies, and a
lot passing a test it was never given is the failure this project exists to avoid.
A document stored unsliced now says so, since a whole code costs megabytes and puts
a reviewer a thousand pages from the setback they are checking.

**And attaching found nothing.** That is the finding, not a failure: Wilsonville
states its standards in *prose under a per-zone section heading* — "Section 4.122.
Residential Zone", then paragraphs — where Portland states them in a table with a
column per zone. Corroboration only counts zone-keyed readings (§12), and a
paragraph is only zone-keyed by the heading above it, which nothing currently
tracks.

That is the next structural piece, and it is not one city's problem: Fairview's
19.115 has the same shape, and so does most of the state. **Section scope** —
binding every clause to the zone whose section encloses it — is what makes
prose-organised codes readable at all, and it is worth more than any individual
city's encoding.

---

## 23. Section scope — how a prose code says whose standard this is

Portland states its standards in a table with a column per zone, so a reading is
zone-keyed by the column it came from. **Most of Oregon does not.** Wilsonville
writes "Section 4.122. Residential Zone." and then paragraphs; Fairview's 19.115
is a chapter for one zone. In those codes a sentence is bound to a zone by the
*heading above it* and by nothing else, and corroboration — which counts only
zone-keyed readings — heard none of it. Wilsonville's first attach pass found
zero quotable values out of 71 for exactly this reason.

So a zone may declare the sections that state its standards:

```yaml
zones:
  R:
    section: ["4.122", "4.113"]   # its own zone section, plus the standards
                                  # applying to residential development in ANY zone
```

**Declared, not inferred.** Guessing which heading means which zone — matching "R"
against "Residential Zone" — would attribute one zone's setback to another
silently, and silently is the direction that turns lots red. A section number is
one line, and a reviewer can check the claim in a glance. A prefix match covers
subsections, so `4.113` reaches `4.113(.02)` without listing every paragraph.

One reader fix came with it: `_SECTION` only recognised headings that *start* with
the number, which is Portland's shape ("33.110.220 Development Standards"). Every
heading in a "Section  4.122." code went unrecognised, so every paragraph in the
chapter was attributed to whatever section was last seen — 586 of Wilsonville's 781
candidates were filed under one wrong section. With the prefix read, they land under
18 sections, and the numbers appear where the code puts them.

### What it reached, and the honest limit

Wilsonville now sees candidates per zone where it saw nothing. It still attaches
**zero**, and the refusal is right: a section is coarse, so the reader hands back
every number in it — `setback_front_ft` "states more than one value (15, 20)" —
and quoting one of those would be a guess wearing a citation.

That is the next reader problem, and it is a reader problem rather than a scoping
one: binding a number to a *subject* ("front yard setback shall be 20 feet") inside
a section that also discusses lot widths, heights and driveway aprons. Section scope
was the prerequisite — without it the numbers were not even in the room.

## 24. The grid most of the corpus is written in

### Where this came from

The three Municode declarations (§22's chain, now run for Oregon City, Tualatin and
Troutdale) put Troutdale's Chapter 3 in the store, and its dimensional standards
turned out to be the table family most small Oregon cities use: one grid per
**housing type** — detached, attached single-family, townhouse, cottage cluster —
each with zones across the top and standards down the side. Table C, "Townhouse
dwellings," is the pod's own typology. The reader saw none of it, for four separate
reasons, each of which is a property of the family rather than of Troutdale:

1. **The zone-code shape.** `_ZONE` accepted `R5`, `R2.5`, `MDR-PV` — and not the
   hyphen-digit shape, `LDR-1`, `R-10`, `R-3.5`, which is how Oregon City and
   Troutdale write every zone they have. Every column header failed to read as a
   zone, so the grid was invisible.
2. **A real splitter bug, live since Portland.** The cell splitter's middle group
   was greedy, so a *single-character* cell reached across its own gap and glued
   itself to the next cell: "5  5  5" read as pairs. Portland never surfaced it
   because its cells carry units — "20 ft." stops at its own word end either way.
   Troutdale prints bare digits.
3. **Alignment drift beats offsets.** Each row right-aligns its numbers to their own
   width, drifting further than the column pitch, so nearest-offset placement read
   LDR-1's 70 as LDR-2's — the neighbouring zone's number wearing this zone's
   citation, the exact error the table reader exists to prevent. The fix reads a
   structurally complete row (one cell per header slot, counting the "(TC)"
   sub-columns that are real columns but not zones) by *position*; offset matching
   remains only the fallback for ragged rows.
4. **The unit and the subject live in the headings.** Cells are bare digits; the
   unit is printed once in the row label ("Minimum lot width **(ft.)**") or the
   group heading ("Setbacks **(ft.)**:"), and the rows under that heading are
   labelled only "Front yard", "Side yard". The reader now carries the group on
   each row, resolves those labels through it, and measures bare digits in the
   declared unit. A bare number with no declared unit anywhere still produces
   nothing — guessing feet is how an acreage becomes a setback.

### Evidence has a hierarchy

With the grid readable, one more thing was needed: Troutdale's declared `3.130`
also contains a density/lot-size grid whose every number the prose reader files
under lot size — 25 values for one field, drowning the one cell that answers. The
rule that resolves it was already written in the Candidate docstring: a table cell
is *written for* a zone; a sentence under the declared section is merely near it.
`check_zone` now lets cells win outright when both speak to one field.

Troutdale went from 0 quotable to **10 applied**: lot sizes, frontages, and the
setbacks the tables state unambiguously. What still refuses is refusing correctly —
`setback_side_ft` "states more than one value (5, 10)" is the detached table and
the townhouse table disagreeing, which is not noise but the **housing-type
dimension**: one zone, one standard, a different number per building form. The pod
is a townhouse; the encoding should one day say "read the townhouse column of the
right grid." That is the named next problem for this family, alongside §23's
subject binding for prose.

### What the other two cities measured

Oregon City and Tualatin also moved to `unquoted` and still attach zero, and each
names its own blocker honestly. Tualatin's PDF extraction **fuses words**
("areasintheCitythatareappropriatefordwellings") — section headings survive, so
scope works, but no subject phrase can match. Oregon City's extraction pads and
breaks words ("authori z ed") — a different pathology, same effect. Both are
*extraction* problems, not scoping ones: the fetch layer needs a readability
measurement so a document that cannot be read stops looking like a document with
nothing in it. Municode product choice also matters and is now measured: a client
can publish several products, and two of these three keep zoning in a
separately-published Development Code the "first listed" heuristic passed over.
`publication()` prefers a development/zoning product and says what it passed over.

## 25. The shapes HTML codifiers linearise to

### Where this came from

Declaring the five platform-lead cities (Gladstone, West Linn, Lake Oswego,
Milwaukie, Wood Village) put the first *HTML-native* documents in the store —
Code Publishing per-chapter pages, eCode360 `/print/<code>?guid=` output,
municipal.codes leaf sections. None of them contain a spatial grid: the codifier
renders the dimensional table as an HTML `<table>`, and `html_to_text`
linearises it one cell per line. Two new shapes, two new readers, and the same
lesson as §24 — each shape is a property of the platform, so one reader pays
for itself across every city that platform hosts.

### The fourth shape: stacked pairs (`read_pairs`)

A per-zone chapter (Code Publishing gives every West Linn zone its own chapter)
prints its table as label-line over value-line:

    Front yard
    20 ft
    Except for steeply sloped lots ...

The prose reader cannot see this — `paragraphs()` joins the stack into one
clause, where the note's "Except" tags the standard an exception (Gladstone's
20 ft front vanished exactly this way) or a run of cells reads as one sentence
stating five side setbacks. The pair reader works on the *unjoined* lines: a
line that is exactly a label over a line that is exactly one measurement.
Grouped labels ("Front yard" under a setbacks heading) resolve the way §24's
grouped rows do. Two hazards earned their guards: a value line is consumed
whole or not at all ("7.5 ft or 5 ft due to irregular shaped lots" is a
two-tier standard, not a 7.5), and repeated value lines are exempt from
furniture detection — in a linearised grid the repetition *is* the data, and
frequency-based furniture removal ate West Linn's whole setback block before
the exemption.

A pair is **near-cell** evidence: nothing in the stack names a zone, so it
counts only under a declared section or a single-zone document — but it
outranks prose there. The hierarchy in `check_zone` is now
**table > pair > prose**: Gladstone's cottage-cluster sentences no longer
outvote the base-zone row they are the exception to.

### The fifth shape: stacked grids (`read_stacked_grids`)

A multi-zone table linearises to a header block of zone codes, then each row
as its label followed by one value line per zone, in header order:

    Standard
    LR12
    LR7.5
    - Min. lot area(2)
    12,000 sq ft
    7,500 sq ft

Position in the run says whose column a value is, so — unlike a pair — what
reads here is real cell evidence. Three refusals keep the positional claim
honest, each earned on a live document:

1. **A one-zone header is never read.** Milwaukie prints lot-size *tiers*
   under a single zone code (R-MD), and n positional values under one zone is
   exactly what a tier row looks like. Reading them would encode the smallest
   lot's standards as the zone's.
2. **A row is all-or-nothing.** Every one of its n lines must be a
   measurement, a dash, or a footnoted measurement; one prose cell refuses the
   whole row rather than shifting the columns.
3. **More values than zones refuses the row** — the geometry is not what the
   reader assumed, and nothing positional survives that.

Wood Village's Table 210-3 also carries a **Corner Lots** block — the street
side setback's natural home (the standard only exists on corners) whose other
rows are corner *variants* of the base standards above. Where the block ends
is not printed, so the guard is scoped by field: inside a corner block only
`setback_street_side_ft` is read, and a coverage row after the corner rows is
recognised as a sibling because coverage has no corner variant.

### What refused, and what it names

Lake Oswego's Table 50.04.001-1 nests three levels — Primary Structure /
Accessory Structure blocks repeating identical row labels, street side split
Arterial vs Local — and its labels ("Front (ft.)") deliberately match no
subject, so the whole table refuses rather than risk an accessory setback
wearing the zone's citation. Milwaukie's tiers and Wood Village's MR table
(columns are housing types under a combined "MR4 and MR2" header) refuse the
same way. All three land in the same two named dimensions this plan already
carries: the **housing-type dimension** (§24) and the **lot-size/context tier**
(Wilsonville §4.113's variant pair). The readers' job was never to interpret
those — it is to make the refusal name the row it could not claim.

Net effect of the two readers: 66 quotes attached in one session — Gladstone
12, West Linn 40, Wood Village 14 — every one pointing at the line its number
is printed on.

## 26. The housing-type dimension, row-level

Three cities named the same missing axis before it was built: a table that
states one standard per heading and one row per *housing type* under it.
Gresham's Table 4.0130 is the pure case — "B. Minimum Lot Size" over rows
labelled Duplex, Townhouse, All other uses — and it is now the first shape of
that dimension the readers handle. Getting there took four reader facts, each
a property of how Gresham prints the table rather than of the dimension:

1. **The bare header.** The zone columns have no label cell over the row
   labels — the header line is nothing but district names. A header of ≥2
   cells that are all zone codes, at least one carrying a digit, now anchors
   a table (the digit rule keeps a wrapped row of "NA NA NA" from becoming
   three districts).
2. **Lettered group headings.** "B. Minimum Lot Size2" ends with no colon, so
   it used to glue onto the previous row as a label continuation. A lettered
   or numbered heading with no cells beside it (≤12 words, no trailing
   period — footnotes are longer and close like sentences) now scopes the
   rows below it, exactly as a colon heading does.
3. **Glued footnotes.** A PDF superscript loses its baseline: "35 ft.12",
   "16 ft.7". The number after the unit is now a footnote mark, the value
   stays conditional, and a mark whose definition was not captured yields a
   placeholder note rather than a silent promotion to unconditional.
4. **Corner sub-groups.** "2. Width at building line: Corner lot" is the
   corner variant of a standard this system states once; the stacked reader's
   corner rule now applies here too — inside a corner block only the
   street-side setback is at home.

The framework piece is **selection**, and it encodes a fact about the pod that
no reader can: a 4-unit attached townhome can be permitted as a *quadplex on
one lot* or as *four townhouse lots*, and jurisdictions file the same building
under either word. Both classifications speak for the pod. "All other uses"
speaks too — quadplexes are usually in it implicitly — *until* some row of the
same field names quadplexes explicitly, at which point "other" provably
excludes them and falls silent. A row naming only other types (a duplex's lot
width) is never evidence. And when the two plat paths state different numbers
— Gresham's townhouse lot width is 16 ft. where the quadplex compound row says
35 — both survive, the field reads as multi-value, and attach refuses: the
plat-path choice is a decision for a person, not a coin flip in a reader.

What it bought immediately: Gresham's minimum lot sizes corroborated and
quoted for LDR-5, LDR-7, MDR-12, TR off the "All other uses" row (quadplexes
unnamed in that group, so the row is theirs), with MDR-24 honestly unsupported
— its default cell reads "None". What refuses now names the dimension's next
two shapes: Troutdale's grid-per-type family ("read the townhouse *table*")
and Wood Village's MR columns ("read the townhouse *column*"), plus Gresham's
own Table 4.0131, a third arrangement (housing-type blocks over zone-group
rows under two-tier column headers) that no reader claims yet.

A limitation worth stating: a "None" cell produces no candidate, so a
townhouse row whose standard is *no minimum* cannot veto the default row
beside it. The encoded file's plat-path choice is what makes that safe —
Gresham's values model the quadplex path, for which the default row is the
right one — and the reviewer, not the reader, owns that choice.

### §26 addendum — table-level, same session

Troutdale's grid-per-type family ("read the townhouse *table*") followed the
row-level shape immediately. Two reader facts made it work: the heading that
names who a grid is for — "C. Townhouse dwellings:" — is printed *above* the
grid's header line, just outside its span, so the reader now looks back a few
lines for a heading-shaped line naming a housing type and seeds the grid's
`block` with it; and a wrapped "see note 1" cell that drifts off its column
glues onto the row label, so "Front yard see note 1 see note 1" now still
reads as the front yard row, with the refs conditioning every value in the
row — the direction that refuses a quote rather than quoting a conditional
number clean. Rows with no type of their own inherit the grid's.

Result: Troutdale's three standing `differs` (front setbacks, file 10 vs
doc "1, 2, 20" — shredded note prose outvoting nothing) resolved to `agrees`,
and the layer went from 12 agrees / 3 differs to **18 agrees / 0 differs**,
every value corroborated against the triplex/quadplex block's own rows.
Nothing new attaches — the remaining unquoted values refuse by name
(conditional see-notes, townhouse-vs-quadplex side setbacks that genuinely
disagree) — but the review gate is clean. Still unclaimed: Wood Village's MR
columns (column-level) and Gresham's Table 4.0131 (type blocks over
zone-group rows under two-tier headers).

---

## 27. The corner-lot audit — one row every table prints twice

Gresham's Table 4.0130 runs each dimension twice: an interior-lot row, then a
corner-lot row. Only the interior row was encoded. That is not a small
omission in one direction — the corner row is routinely the larger number (40
feet of width in LDR-5 where the interior row asks 35, 70 in MDR-12 where it
asks 16), so every corner lot in the city was screened against a standard the
code does not state for it, in the direction that certifies lots. Fixed
2026-08-19 across six residential zones, with the corner + `unit_lots` pair
stated too so a corner townhouse lot resolves one variant instead of tying
two, and `exempt` rather than a number where the table prints "None".

**The audit that follows from it.** Corner variants encoded, per jurisdiction:
Gresham 26, Wood Village 4, Wilsonville 1, and **zero everywhere else** — 14
of 17 layers. Eleven of those cities define "corner lot" in their own code,
and their held documents pair the word "corner" with a dimension and a number
on this many lines:

| jurisdiction | such lines | corner variants |
|---|---:|---:|
| or/clackamas/oregon-city | 13 | 0 |
| or/clackamas/wilsonville | 9 | 1 |
| or/multnomah/fairview | 4 | 0 |
| or/clackamas/milwaukie | 4 | 0 |
| or/clackamas/rivergrove | 2 | 0 |
| or/clackamas/west-linn | 2 | 0 |
| or/clackamas/_unincorporated | 2 | 0 |
| or/multnomah/_unincorporated | 1 | 0 |
| or/clackamas/gladstone | 1 | 0 |
| or/clackamas/lake-oswego | 1 | 0 |

A zero is not proof of a hole: most Oregon codes handle a corner with a
street-side setback rather than a second dimensional row, and
`setback_street_side_ft` is encoded widely. What the table says is where to
look, jurisdiction by jurisdiction, and Oregon City at thirteen lines is the
next one to read.

The reason this is worth a section rather than a bug: the failure was silent.
A zone with no corner variant hands back the interior number and looks exactly
like a zone somebody read and found nothing in. The test added with the fix
asserts the opposite for Gresham — that `corner_lot` appears in every
residential zone's levers — which is the shape of assertion the rest of the
corpus needs.
## 28. The first districts encoded off the back of a ledger that could see them

Written 2026-09-08, hours after the coverage ledger was rebuilt over two
counties. The rebuild's whole claim was that it turns a blind queue into a
ranked one. This section is the first work taken off the top of that queue, and
it is here because of what came back with it rather than because five zones were
encoded.

**What was encoded.** Unincorporated Clackamas held nine zones — the eight urban
low-density districts of Table 315-2 and the two village districts of Table
315-3 — while the parcel corpus assigns thirty-one. Five more are written now:

| zone | lots | what it is |
|---|---:|---|
| MR-1 | 839 | Medium Density Residential. The largest single unencoded zone in either county. |
| MR-2 | 120 | Medium High Density Residential. |
| R-2.5 | 77 | **Refused.** Table 315-1 reads `X` in the Quadplexes row. |
| PMD | 9 | Planned Medium Density Residential. |
| VA | 1 | Village Apartment. |

1,046 lots, of which 969 can hold the building. Three more districts are
deliberately left alone and the reasons are the interesting part.

### The table said the opposite of what binds

Table 315-4 reads, at a glance, like the loosest table in the county: PMD, MR-1
and MR-2 print **no maximum building height at all**, where every R zone in the
layer is capped at 35 feet. Section 845, which governs how a quadplex is
designed here, states no height either. So `max_height_ft` is `exempt: true` in
three districts, and it is the correct use of that value rather than the
dangerous one — the cell is printed and it is empty of any ceiling, in a table
whose VA column prints 45.

And it reads, at a second glance, like the tightest: these four districts each
carry a **district land area**, and ZDO 1012.04(A) — the sentence that exempts a
quadplex from DLA — names the nine districts it reaches and none of them is one.
So by the county's own text a quadplex in MR-1 wants 3,630 square feet of net
site area per unit, which is 14,520 for four, against the 7,000 Section 845.01
asks. Twice the lot size standard, on 839 lots.

**Neither glance is what happens, and the density figure is not encoded — for
two reasons, the first of which is ours.**

The county does not print a density. It prints a *lot area per dwelling unit*,
and this model has one density field, in units per acre. 43,560 ÷ 3,630 = 12 is
arithmetic we would be doing. The column ledger — the check written after Gresham
printed `16 ft.` in seven columns and we took it for six — refused it in exactly
those words: *"encoded 12.0, its own column reads '3,630 square feet'."* It was
right to. The number was in the corpus for about twenty minutes and the guard
caught it before the suite did, which is the second time in two days a check
built for one misreading has caught a different one.

So the standard is refused in writing, per zone, with the cell quoted. **The
missing thing is a field for a minimum lot area per dwelling unit**, and MR-1 is
the first zone that would need it.

The second reason it could not have bound anyway: OAR 660-046-0220(2)(b) forbids
applying a density maximum to a quadplex, and it reaches this layer — which was
nearly called wrong in the other direction. The applicability rule states the
division's reach in one sentence: *"A local government that is a Medium City or
Large City must comply with this division."* An unincorporated county is neither.
That is the wrong answer, and the right one is in the definitions rule:

> "A Large City includes unincorporated areas of counties within a metropolitan
> service district that are provided with sufficient urban services."

Urban unincorporated Clackamas is inside Metro. **Reading the applicability
sentence and stopping there would have produced a REVIEW on 969 lots for a
standard no jurisdiction may apply.** This corpus has a standing lesson about
definitions hiding the answer to a question the main text appears to settle; this
is that lesson arriving from the other direction, where the definition *widens*
what a rule reaches.

What actually binds in MR-1, then, is a lot-size floor, three setbacks and
parking — looser than any R zone in the county, which is the opposite of what
Table 315-4 reads like.

The state file's own measured claim was re-measured rather than trusted, because
a measured claim about the corpus expires whenever somebody encodes a zone. The
density exemption now reaches **201 zones against 88** in August and strikes out
a real ceiling in **27 against 26**; the seven of those that sit in zones the
rule arguably never entered are the same seven, every zone added since being
plainly zoned for residential use, so the applicability gap still moves no
verdict.

### The state parking cap bites for the first time

Table 1015-2's Quadplex row sends all four districts to the Multifamily Dwelling
rows, which price parking **per bedroom**: 1 for a studio or one-bedroom, 1.25
for a two-bedroom, 1.5 for a three-bedroom. The design catalog holds units,
storeys, footprint and parking geometry and no room schedule, so the
discriminator is unmeasured and the largest printed figure is the one encoded.

In every R zone in this county the county's own figure is 1 per unit, which is
exactly what OAR 660-046-0220(2)(e)(B) allows, so the cap and the requirement
have always landed on the same number and the cap has never been observed doing
anything. Here the county asks six spaces for four units and the state allows
four. The resolved 1.0 is the state's number overriding the county's — the first
place in the corpus where that is true. Six stalls against four is roughly 200
square feet of court, which on a small lot is the difference between a pod that
fits and one that does not.

### Sixteen dismissals decayed exactly as predicted, and one week early

The dismissal re-read of 2026-09-07 read all 784 waved-away footnotes and found
that 49 of them argue about *our corpus* rather than about the code — a reason
of the form "this layer does not hold that district", which stops being true the
moment somebody encodes the district, and stops being true silently, because a
dismissal is never re-derived. `stale.py` was written as the standing check.

Sixteen of those 49 were the Table 315-4 notes in this layer, dismissed as a
block on 2026-08-21 with: *"This layer holds none of them."* This layer holds
four of them from today. All sixteen are re-read and re-ruled against the
building rather than against our file list, and two of them are not dismissals
at all:

- **Note 14 TIGHTENS the number this commit encoded.** MR-1 and MR-2 print a
  storey ladder for the side setback — five feet at one storey, seven at two,
  fifteen at three — and the pod is two storeys, which the design catalog knows,
  so seven is the figure. Note 14 then says: *"If the side lot line abuts an
  Urban Low Density Residential, VR-5/7, or VR-4/5 District, the minimum side
  setback for a two-story building is 10 feet."* No adjacency layer is held for
  Clackamas County. So the note is ruled `unmeasured` on
  `abuts_lower_density_zone` and narrowed to those two zones, which caps the
  value: **959 lots carry a side setback we can state and cannot confirm.** The
  same treatment Oregon City's nearly identical note 1 already gets.
- **Note 6 TIGHTENS in VA.** A front or rear lot line abutting Sunnyside Road
  takes a 65-foot minimum and 75-foot maximum setback *measured from the road
  centerline*, which is a geometry no field in this model holds, against VA's
  own 10 feet and none. Ruled `unmeasured` on `site_specific_limitation` and
  narrowed to VA.

Narrowing matters here in a way worth recording. A footnote governs its whole
notes block by default — deliberately, because an over-scoped note costs a
review and an under-scoped one costs a false GREEN — so before `zones:` was
written, note 6 capped every value in all four districts and PMD could never
certify on a road it does not touch. Two `zones:` keys took the cap from 397
values to 390 and freed PMD entirely.

### What is not encoded, and the second cost of the empty-box bug

**HDR (253 lots), RCHDR (32) and SHD (1)** print `See Subsection 1005.02(L)`
where their rear and side setbacks belong. ZDO 1005 is not in the store. A zone
whose setbacks are a cross-reference nobody has read is not a zone this project
guesses at, so the three stay `zone_missing` — which is now a queue entry with a
lot count on it rather than an absence.

This section first said fetching ZDO 1005 was *"the single cheapest 286 lots
left in this layer"*, written before anybody had read the chapter. **That was
wrong, and the correction is more interesting than the claim.** The page is
live and the subsection is on it, so it took a read rather than a fetch to
find out:

> "The minimum distance on a north-south axis between any building and a site
> area line north of said building shall be the horizontal distance calculated
> by drawing a 60-degree angle line from the top of the structure to the
> natural ground elevation north of the structure."

and, for the other axis, with the county doing its own trigonometry:

> "Formula: Separation = b x .267 (tan 15 degrees)"

**It is a solar-access rule, and it is measured off compass north.** One lot
line wants a large separation because a building shades the land behind it;
two want a small one; the fourth is not regulated at all. Which line is which
depends on where the lot is pointing, and **FLATS holds no bearing for any lot
line** — `orientation` in the screen means which way the *pod* sits in its
envelope, not which way the lot faces. So `setback_rear_ft` and
`setback_side_ft`, which are directionless in this model, cannot carry it: rear
would have to mean "the north one" and it does not.

The forms to hold the arithmetic already exist — `per_height_ft` is a divisor
over `DESIGN_HEIGHT_FT`, `step_back` takes a `slope_degrees` and converts it,
and all three of the fields involved accept them. What is missing is not a
value form. It is the fact. So this joins the fourth-footnote-state list beside
transit, corner, alley and sewer, with one difference worth noting: unlike
those, **the fact is computable from geometry we already hold** — the parcel
polygons are in PostGIS and a lot line's bearing is arithmetic on two points.
That makes it a measurement to build rather than a datum to buy, and it is the
first item on that list of which that is true.

The same chapter answers the maximum front setback these four districts defer
to, and it lands in the same place: 1005.02(H) caps the setback at 20 feet, but
only for a building *"located at a major transit stop"* — frontage on the
transit street and any part of the building within a 200-foot radius. Another
unmeasured site fact, and a second word question underneath it, because the row
reaches *"retail, office, mixed use, multifamily, and institutional
buildings"* and this county's own use table lists Quadplexes as a separate
line from Multifamily Dwellings.

**VTH (115 lots)** is refused for a worse reason, and it is HUMAN_TODO item 15
appearing in a second document with a name attached. Table 315-3 heads three
columns — VR-5/7, VR-4/5, VTH — and its Minimum Rear Setback row prints **two
cells**. So does its lot size row, its coverage row, its maximum lot size row.
Its height, front, maximum-front and side rows print three. Either VTH has no
rear setback or VTH's cell was eaten by the extractor's habit of dropping empty
table cells, **and the stored text cannot tell which** — every cell after a
dropped blank slides left, so a short row is unreadable by position and a
position read is all a flow-path table offers.

Item 15 said this exactly: *"A table of measurements with a blank in it would be
damaged the same way and would not show up."* It does not show up — `ragged.py`
scores this document at zero, because it only inspects tables full of one-letter
answers. This is the first measurement table in the corpus known to be affected,
it costs 115 lots today, and unlike Lake Oswego we cannot even confirm it is
damaged without re-fetching the page. Re-fetching is the decision item 15 exists
to ask for, so nothing here was fetched.

### Where the layer stands

**Nine tests went red, and all nine for the same reason.** Every one pins a
measured claim about the corpus, and encoding a district changes the corpus.
The list is worth keeping because the directions are not all obvious:

| census | was | is | why it moved |
|---|---:|---:|---|
| encoded zones | 196 | 201 | five districts |
| exemptions | 189 | 196 | seven printed cells that state no standard |
| declared refusals | 252 | 258 | **+6, and up is correct** |
| districts owed | 14 | 10 | the queue was worked |
| governed values, this layer | 74 | 107 | Table 315-4's sixteen notes reach everything in it |

The refusal count is the one that reads backwards, and `test_refusals` already
warned about it in its own header: *"closing a zone gap RAISES this count. A
district nobody encoded refuses nothing."* Four of the six are the four
districts each declining the district land area; the other two are one block
header counted twice, because the refusal has two independent reasons and each
is stated as its own refusal — the missing field, and the state preemption. Both
are recorded on purpose. The state one could be repealed and the model one could
be fixed, and on the day either happens the other still has to be answered.

Three of the nine were the same `len(rows) == 74` in three different files, and
all three are now a floor. What that line guards is a governed value quietly
becoming an ungoverned one; it cannot guard against somebody encoding a zone,
because that is the work. The note census beside it stays an equality, because
that one is a claim about how much of a chapter has been read, and reading is
not something that should happen by accident.

Fourteen zones held against nine this morning. The districts audit for this
layer now returns four real districts owed — HDR, RCHDR, SHD, VTH, all four
named above with their reasons — and eleven acronyms it cannot tell from zone
codes (DLA, HRA, MRA, NR, BD and the habitat-district abbreviations), which is
the known false-positive shape and not work.

---

## 29. Eleven districts in one pass, and a setback that is a question about the neighbour

Written 2026-09-08, later the same day as §28 and off the same queue. Oregon
City had 1,162 lots in `zone_missing` across twelve districts — its entire
non-residential side, untouched since the port. Eleven are encoded now. The
twelfth is `County`, twelve lots on seven acres that the parcel layer labels
with the county's zoning rather than the city's; that is a join question and
not a reading, and it is left where it is.

They were read in one pass because they are one reading. Chapters 17.24
through 17.39 print the same nine-paragraph dimensional standard over and
over with the numbers changed, so the interesting part is never the number.
It is which paragraph reaches a four-unit building, and that turns out to
differ district by district in ways no table would show.

**What was encoded.**

| zone | lots | acres | verdict |
|---|---:|---:|---|
| MUC-1 | 402 | 134 | permitted — 40 ft / 3 storeys, 80% coverage |
| MUD | 278 | 566 | permitted — 58 ft, 90% coverage |
| C | 74 | 163 | permitted — 60 ft, 85% coverage |
| MUC-2 | 40 | 100 | permitted — 60 ft, 90% coverage |
| WFDD | 4 | 23 | permitted — 80 ft, 100% coverage |
| MUE | 133 | 165 | **refused** — no residential use listed |
| I | 93 | 434 | **refused** — no residential use listed |
| GI | 57 | 225 | **refused** — "all other residential uses are prohibited" |
| HC | 37 | 5 | **refused** — 17.26.035.B |
| CI | 31 | 174 | **refused** — 17.37.060.C.6, six named tax lots, detached only |
| NC | 1 | 12 | **refused** — 17.24.035.L caps residential at half the floor area |

798 lots on 986 acres can hold the building; 352 cannot. The six refusals are
written into the file rather than left out, and that is not bookkeeping: an
unencoded zone is a hole, and a hole is invisible to every ledger in this
project that counts fields. A refusal is a reading, and it is the only form
of reading that a coverage ledger can otherwise never distinguish from
neglect.

### The setback is stated twice, and the hinge had no name

Every mixed-use and commercial chapter in this city writes its setbacks the
same way: *"Minimum required setbacks if not abutting a residential zone:
None"*, then twenty feet where it does abut one. Four of the five permitting
districts print exactly that, and the fifth prints zero with no limb at all.

Zero is the loosest number anywhere in this corpus and it must not be held
flat. Encoding the zero alone greens a lot the city would refuse; encoding
the twenty alone reds a downtown block the city would permit. So the
condition decides, and the condition needed a name.

`abuts_lower_density_zone` was the closest thing already registered and it is
the wrong question. That one compares two residential districts by intensity.
This one asks which side of the residential/non-residential line the
neighbour sits on, and a *denser* neighbour trips it. `abuts_residential_zone`
is registered for it, with `assume=None` — nobody has measured it, the
registry refuses to guess, and so every lot in these four districts leans on
an unobserved fact and routes to review instead of certifying on the zero.

That is the correct answer and not a defect. It is also the fifth entry on
the list of site facts that block a verdict, and — like ZDO 1005's compass
bearing from §28 and unlike transit, corner, alley and sewer — it is
**computable from data already held**: it is a polygon adjacency between the
parcel layer and the zoning layer, not a purchase.

### A paragraph somebody did not copy

OCMC 17.29.050.I reads: *"Standalone residential development of fewer than
five units are exempt from maximum setbacks and minimum density requirements
of the underlying zone."* Our pod is four units. The same sentence appears at
17.34.060.K and 17.34.070.K and stops one clause earlier — *"exempt from
maximum setbacks"*, no density limb. And it is simply absent from 17.29.060
and 17.32.050, four lines and one chapter away respectively.

Four districts, three different answers, from one sentence printed three
times:

| district | max front setback | minimum density |
|---|---|---|
| MUC-1 | exempt (17.29.050.I) | exempt (17.29.050.I) |
| MUD | exempt (17.34.060.K / .070.K) | **17.4 du/ac binds** |
| MUC-2 | **5 ft binds** | **17.4 du/ac binds** |
| C | **5 ft binds** | **17.4 du/ac binds** |

A five-foot maximum front setback pushes a building to the street line, so
this is not a rounding difference — it decides whether a pod with parking
behind it is legal. Copying MUC-1's block across the chapter, which is what
a table-driven reading would have produced, would have been wrong in three
districts out of four.

The 17.4 is a *minimum* density measured on net developable area, the city's
own denominator and not gross lot area. `measured_on` carries it, which is
what stops the screen dividing four units by a number this project does not
hold and reporting a pass.

### The word was on the permitted list and the use is prohibited

Historic Corridor's 17.26.020.C permits *"conversions of an existing
single-family detached residential unit or duplex into a triplex or
quadplex"*. Sixty lines below, 17.26.035.B prohibits *"Triplexes and
quadplexes"*.

Chapter 17.26 contains the word "quadplex" exactly twice, and a keyword
search returns the first one. A factory-built pod on a bare lot converts
nothing, so HC is closed — 37 lots that a search would have called open.
`test_oregon_city_commercial.py` pins both line numbers, because the next
district read this way will be read by whoever trusts the search.

### The layer's own parking defaults are residential-only

OCMC 17.16.060.D opens *"In residential zones"*, and its two limbs — forty
feet of parking width, fifty percent of frontage — sit in this file's
`defaults:` with no such limit on them. In these five districts they are
over-strict rather than wrong-headed, which is the safe direction, so they
are left inherited and named in the file instead of quietly unset.

The paragraph that *does* reach here is 17.16.060.E: parking behind the
facade closest to the street, below the building, or beside it. So
`parking_front_prohibited` is `true` in each of the five against `exempt`
citywide, restated per district from E rather than borrowed from D — because
D is a prohibition, and inheriting a prohibition from the wrong paragraph is
how a district gets refused for a rule that does not apply to it.

### The state preemption does not reach here, and the screen applies it anyway

This is the case `or/_state.yaml` warned about in writing, arriving.

OAR 660-046-0010(2)(a) excuses a Large City for *"Lots or Parcels that are
not zoned for residential use, including but not limited to Lots or Parcels
zoned primarily for commercial, industrial, agricultural, or public uses"*,
and (b) for residential lots that do not allow a detached house. MUD
prohibits detached houses outright (17.34.040.D); MUC-1, MUC-2 and C never
permit one, and 17.06.010.A turns that silence into a prohibition; WFD
reaches residential only at 17.35.020.R, *"Residential units—Multi-family,
triplexes and quadplexes"*. All five sit outside the division.

The state layer applies its defaults to every zone regardless, which was
harmless while the corpus held only residential districts and is not harmless
now. Two things ride on it:

* `max_density_du_per_acre: exempt` is inherited and cancels nothing — none
  of these districts states a density maximum. Harmless.
* `parking_min_per_unit` is inherited as the state's four-spaces-total cap.
  If the division does not reach here, **Oregon City's own Table 17.52.020
  governs unrelieved** — and this file already refuses that row in writing,
  because it states no unit: read as totals it asks two spaces, read per unit
  it asks eight. Four is the middle reading and it is what the screen now
  uses in five districts where the ceiling that justified it may not apply.

That is written down rather than fixed, because fixing it needs the adopted
ordinance text rather than the codified table. It is the first thing to read
at signing, and `test_oregon_city_commercial.py` pins the current behaviour
so that scoping the state layer produces a red test rather than a silent
change of verdict on 798 lots.

### Three model gaps, and only one of them bites

* **No minimum-FAR field.** MUC-2 asks 0.25 and MUD asks 0.30/0.5, and both
  are refused *on scope* rather than for want of a field: 17.29.070.A and
  17.34.080.A say in their own words that minimum FARs reach *"all
  nonresidential and mixed-use building development"*, and a standalone
  quadplex is neither. WFDD is the exception — Chapter 17.35 states no such
  confinement, so its minimum FAR of 1.0 is a real hole. Four lots.
* **No minimum-building-height field.** Three districts ask twenty-five feet
  or two storeys. The pod is two storeys at twenty-six feet and clears both
  limbs of all three, so the gap cannot bite anywhere in this city.
* **No maximum street-side setback field.** MUC-2's 17.29.060.G.3 caps the
  corner side yard at twenty feet. One district, forty lots, and only on
  corners.

Refusing on scope where scope is available is worth the extra reading every
time: it is what keeps the model-gap list from filling up with standards that
were never going to reach this building.

### Three correctly cited numbers the reader could not read

The corroboration check flagged three of these values as misquotes — a
citation pointing at text that does not state its number — and all three
were the check being blind rather than the encoding being wrong. Worth
writing down because they are three *different* blindnesses and none of them
had been seen before:

| value | what the page says | why it was invisible |
|---|---|---|
| MUC-1 `max_height_stories` = 3 | "Forty feet or three sto-<br>ries, whichever is less" | the **unit** is hyphenated across a line |
| MUC-1 `max_coverage_pct` = 80 | "Eight y percent" | the scan put a space **inside a spelled number** |
| WFDD `max_coverage_pct` = 100 | "One hundred percent" | the spelled vocabulary stopped at ninety-nine |

The first is the subtlest. A spelled number only counts when a unit follows
it — otherwise "one" and "two" would corroborate anything — and the unit here
is `sto-\nries`, which no pattern for `stor(y|ies)` can match. So the guard
that makes spelled numbers safe is exactly what made this one unreadable.

The second is not repairable by the letter-spacing repair that already runs
over this document, and cannot be: `1 0 , 000` is visibly broken, and
`Eight y` is two real English words. The fix is to let the letters of a
spelled number be interrupted **when the document is already declared
spaced**, with the unit guard still standing behind it. "eight years" does
not become eighty, because after the `y` comes an `e` and the word boundary
refuses it.

The third had no reason behind it at all. Ninety-nine was as far as anything
had needed to count. It is a maximum site coverage, so the number that could
not be corroborated was the one that lets a building take the whole lot.

Corpus-wide the misquote count is **zero** after the repair, and the three
guards are pinned alongside the three repairs in `test_readiness.py`: a
spelled number with no unit behind it is still not evidence, and closing up
a hyphenated line break must never invent a number — `20-\n30` is two
numbers, not two thousand and thirty.

This is the same shape as every other entry on the reader-blindness list. A
blind reader reports the corpus clean, and the only way these three surfaced
is that somebody encoded values into the part of the page it could not see.

### Where the city stands

| census | was | is | why it moved |
|---|---:|---:|---|
| encoded zones, corpus-wide | 201 | 212 | eleven districts |
| exemptions | 196 | 201 | five printed "Minimum lot area: None." cells |
| declared refusals | 258 | 267 | nine, and up is correct |
| districts owed an encode | 10 | 5 | the queue was worked |
| Oregon City zones held | 6 | 17 | — |

The nine refusals are nine separate readings of nine separate paragraphs,
which is itself the finding: no block header stands over a family of related
ones. Three are exempted by the code itself, two are out of scope, and four
have nowhere to go in this registry — of which three cannot bite and one
does.

Oregon City's districts audit now returns three undeclared acronyms and no
work: `NROD` is an overlay, `MUC` is the parent name the corridor chapter
prints over MUC-1 and MUC-2, and `WFD` is the ordinance's spelling of the
district the parcel layer calls `WFDD` — a real base zone that is encoded,
under the other spelling. `test_districts.py` gained an `aliased` verdict for
exactly that case, because it is not work owed and calling it `encode` would
have kept a closed question open forever.

One district left in this city, and it is a join.
