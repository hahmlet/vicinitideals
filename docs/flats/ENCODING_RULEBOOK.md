# FLATS encoding rulebook

The standing rules and owner rulings for turning a jurisdiction's zoning code
into a FLATS layer. Most of them were learned by getting them wrong once.
Until 2026-09-28 they lived only in one machine's agent memory. This file is
now the copy that counts.

## Purpose and how to use this

- **Who it is for:** an engineer or agent who is new to this repo and is
  about to encode a county or city that FLATS has not screened before.
- **How to read it:** read it once before you start. Then work the checklist
  in §11 and come back to the stage you are in.
- **What it adds to the plan:** [Lot Analysis/FLATS_PLAN.md](../../Lot%20Analysis/FLATS_PLAN.md)
  is the design, over 5,000 lines with the reasoning in full. This file holds
  the rules and the rulings that decide what to do. Where the plan already
  says something at length, this file links to the section instead of
  repeating it.
- **Other references:**
  - Footnote file format: [flats/config/footnotes/README.md](../../flats/config/footnotes/README.md)
  - Refreshing the county copy and promoting a run: [docs/ops/flats-county-refresh.md](../ops/flats-county-refresh.md)
  - Running the suites: [docs/TESTING.md](../TESTING.md)
- **Every name here was checked** against the tree when this file was written.
  If a name has since moved, the code wins. Fix this file in the same commit.

## 1. Mental model

FLATS answers one question per lot: can a fixed-dimension, factory-built
four-unit attached townhome pod (`flats/config/pods/`) be placed legally and
physically on this lot, with its parking and vehicle access?

- **The answer:** GREEN, REVIEW or RED, with continuous slack and the binding
  constraint named. UNKNOWN is used where a fact we need is unmeasured.
- **Where the rules live:** each jurisdiction is a YAML layer under
  `flats/config/jurisdictions/or/<county>/<city>.yaml`. The layer inherits
  from `or/_state.yaml`, and state caps are applied in `flats/rules/caps.py`.
- **Every value carries provenance:** a citation into a stored copy of the
  code (`path#Lx-Ly`), the quote, the retrieval date and a status
  (draft, verified or stale).
- **Nothing verifies itself.** Signing is a human act, recorded in
  `flats/config/verifications.jsonl` (the file does not exist until someone
  signs).
- **Bias is toward recall.** A false RED silently deletes an acquisition
  target. A false GREEN costs one human review. Tolerance can move RED to
  REVIEW, never to GREEN.
- **Encoding is the project.** Every reader blind spot found so far was found
  by encoding a new district, not by looking for bugs. Encoding a district is
  also an audit of the reader.
- **The financial engine is off limits.** Nothing in `flats/` imports
  `app.engines` (`scripts/check_flats_firewall.py`, `flats/tests/test_firewall.py`).

## 2. Gathering the documents

| Rule | Why | Enforced by / where |
|---|---|---|
| Store the document the city **adopted** (the ordinance PDF or the codifier's leaf page), not a page that renders it | Citations are line numbers into stored text. A page that re-renders moves every citation | FLATS_PLAN §22; `flats/provenance/fetch.py` |
| Every `code:` entry declares its own `end:` marker. Reader switches (`extraction: plain`, `allow_thin: true`, `spaced: true` for letter-spaced PDFs) go in the declaration, never only at a command prompt | A re-fetch must reproduce the same text without anyone remembering a flag. Letter-spacing is **declared, never detected** | `flats/provenance/fetch.py`, `flats/tests/test_fetch.py`, `test_despace.py` |
| `allow_thin` is for sections that are really prose or Y/N tables (few numbers). Record why in a comment | The plausibility gate refuses thin text because that is usually a failed extraction | `code:` blocks in e.g. `or/multnomah/wood-village.yaml` |
| Read the whole title, not the zoning chapter only. Streets and public-places titles (driveway approach widths, access management) and public-works standards hold standards the zoning chapter points at by name | A driveway width once sat for weeks in Title 12 while the layer claimed "no encodable width" | `python -m flats.encode.crossrefs` lists unread references. Work the rows flagged BINDING before writing any absence |
| The store hashes **extracted** text. A reader or library change looks exactly like a city amendment | A library upgrade once faked dozens of "amendments". Diff old vs new extraction before deciding a city changed anything | `flats/provenance/pdf_hold.py` (holds PDF extraction to the version the corpus was read under). `fetch.py --repoint` follows a quote to its new lines. `--loose` is for a change of publisher. The option is `--docs`, not `--doc` |
| A jurisdiction can have **two** glossaries, or a glossary hidden inline in a chapter | Terms defined off the definitions chapter decide which noun the pod is | Declare the span with `definitions_at:` (`flats/encode/glossary.py`) |

## 3. Reading and citing

| Rule | Why | Enforced by / where |
|---|---|---|
| **Read the middle-housing / invalidation clause first.** Oregon HB 2001 cities often void or redirect standards for middle housing in one sentence | It can move a whole table off this building | OAR 660-046 is quoted in `or/_state.yaml` |
| **Definitions decide which noun a quadplex is.** "Multifamily" may start at 5 units (the pod is outside it), at 3 (inside it), or be undefined (decide by elimination). Count, don't assume | The wrong noun loads the wrong parking and setback rows | Record the definition's cite in the layer's `definitions:` block |
| Hold the **quadplex / townhouse row**, not the detached-house row. Hold the **rule**, not its exception sentence | These are the two most common wrong-row errors | `flats.encode.columns`, `test_columns.py`, `test_housing_type.py` |
| Name the **column** before claiming a finding. A header shorter than its rows files numbers under the neighbour's name | Right line, wrong column is a real, recurring error | `test_short_header.py`, `test_mark_column.py` |
| A **purpose paragraph** is not a standard. A **design menu** is not a requirement. An **applicant's choice** is not a floor | Each has been misread as binding | reading |
| Citations are line spans `path#Lx-Ly`. Multiple spans are a comma list `#L13405-L13414,L13416-L13420`. Cite sections as a comma list, **never a range** like `19.30.010.D/.020` | A range breaks attribution and once stored a 7,750-line hull | `test_citations.py`, `test_wrapped_citations.py` |
| **A paraphrase cannot be a citation** (Steph). Capture exhaustively, judge later | The quote is what a signer checks | `flats/encode/cite.py` |
| **"We hold nothing" is an extraordinary claim.** Before writing an absence: grep the whole corpus for the city, not just the section; read every cross-reference out of the section; name the outside standard that would fill the gap; check both ends of a stored range | Absence claims have been wrong in both directions. A presence claim needs the same sweep, including the applicability paragraph above the table | `flats/encode/unheld.py` re-asks every "document not in store" claim (`test_unheld.py`) |
| Search **our own corpus** before calling something an unread gap | A table reported as "unread" was already refused, with its reason quoted, in three layers | `grep` the layer files |
| A flat **prohibition** states no number, so no number-driven ledger will ever surface it. Grep prohibition grammar ("shall not", "prohibited", "no … may") in every chapter you encode | This is where false GREENs hide | `flats/encode/missed.py`, `flats/encode/orphaned.py` ("a height of feet": a standard whose number vanished) |
| Compare the layer's **zone list against the use table and the zoning map legend**, not against a coverage ledger. A missing zone is invisible to every field-counting ledger | Three layers once held fewer zones than their codes print, including a city's largest zone | `flats/encode/districts.py` + `test_districts.py` (fails on an unruled designation). One-letter zones no harvest can see go in its `BY_HAND` table. `unweighed()` in `flats/rules/ledger.py` |
| A **refusal is a use-table cell**, not a category: permitted outright or not. Conditional use is a refusal | Keeps the use gate honest | `quadplex_allowed` |

## 4. Encoding values

| Rule | Why | Enforced by / where |
|---|---|---|
| **Conservative default.** When a standard has two numbers, the binding one is the base value. The permissive one is a variant behind a registered condition | An unmet condition must never unlock the lenient number | `flats/rules/conditions.py`, `test_variants.py` |
| **A quote is not the right row.** If a note argues for a number, the argument belongs in the variant's `when:`, not in the base value | A correctly quoted wrong row is still a false GREEN | reading |
| **Never hand-copy a zone.** Use `like:` with its own cite and quote. The claim to borrow is itself a rule | Copies drift apart silently | FLATS_PLAN §17 |
| **A rule about one of two lot lines needs its own per-line field**, never a variant on the shared number. Examples: `setback_alley_side_ft`, `setback_street_side_ft`, `front_lot_line_corner`, `setback_street_off_corridor_ft`, `setback_street_across_nonresidential_ft` (Portland 33.130.215.B.1.b: the across-the-street 5 is the base on every street line; the plain none goes back only to a line read clear across the street and off the corridor) (a lot-level ANY-line variant may stay as the tight reading for edgeless readers; the per-line field gives lines back, and only lines read surely off) | An unread field is merely conservative. A misread variant is a false GREEN | `flats/rules/fields.py` |
| **New fields are required by default** (`REQUIRED_FIELDS = FIELDS - OPTIONAL_FIELDS`). Decide `OPTIONAL_FIELDS` in the same edit, with a reason | A new standard nobody filled must block, not pass | `flats/rules/fields.py`, `test_unsettled_gates.py` (`test_every_zone_that_owes_a_required_field_says_why`) |
| **`exempt: true` means "this standard does not reach", never a quantity.** It is the one value that can only produce a false GREEN, so cite the line stating the exemption, not a footnote marker | A cell holding an em dash is not an exemption | `flats/encode/exemptions.py`, `test_exemptions.py` (`test_no_citation_in_this_corpus_points_at_a_footnote_marker`) |
| A **deliberate absence** (the city states nothing) is different from exempt. Leave the field absent and say so in a comment. A **repeal** is how a code states zero | Absence lets the state layer's cap inherit | `flats/rules/caps.py` |
| **Required is not regulated.** Zero parking required still leaves stall, aisle and placement regulated. When a count resolves to zero, still encode the geometry, and encode `min: 0` rather than omitting it | An omitted minimum makes the state cap resolve as if it were a requirement | `parking_*` fields in `fields.py` |
| **State the printed figure only.** The loader derives the rest. Value forms: `per_dwelling`, `sqft_per_unit`, `acres`, `acres_per_dwelling`, `per_units`, `per_height_ft` (+ `floor_ft`), `step_back` (`rise_per_ft` **or** `slope_degrees`, never both), `qualified_by` (fact must be a registered site fact), `spaces_total` (parking only), `same_as` (lender in the same block), `reduce_pct` and `pct_of_lot_width` (variants only), multi-band `bands` with `less_than` / `more_than` / `at_most` | A hand-computed number has no sentence behind it | `flats/rules/loader.py`, `flats/rules/model.py`. **Every new form must be taught to `readiness._printed` / `_printed_variant`** |
| **Overlapping bands are refused.** A lot with no measurement under a banded standard resolves ambiguous, not to the easy band | Banded standards (by lot size) are common | `test_variants.py`, `test_landscape_levels.py` |
| A density "net acre" is the **city's own definition**. `measured_on` needs `measured_on_cite` + `measured_on_quote` | The corpus holds several different "net acres" | `test_denominator.py` |
| A number that exists only in a **CAD drawing** is `drawn: true` with `read_by` + `read_on` and **no quote** | Nothing to quote. The flag keeps it visible in the ledger rather than cleared | `test_drawn.py` |
| **Height is a dial**, not a constant. The design height is `DESIGN_HEIGHT_FT` in `fields.py`. Never bake it into a derived number | Eleven numbers once had the design height baked in and nothing recomputed them | `python -m flats.encode.height --at 26 --at 30`, `test_height.py` |
| `min_building_height` is the one field where an unheld value buys a false GREEN (a building can fail by being too short) | "Or" is not a form the model holds | `test_min_height.py` |
| Every value you write is `draft`. Say **NOT ENCODED** in a YAML comment, leading with the marker and giving the reason, for every standard you deliberately refuse | The refusal ledger counts them | `flats/encode/refusals.py`. `EXPECTED` in `test_refusals.py` moves with every refusal you add |

## 5. Footnotes and variants

Full format: [flats/config/footnotes/README.md](../../flats/config/footnotes/README.md).

- **States.** A footnote is `unread` (never written; it blocks), `dismissed`,
  `encoded` or `unmeasured`. `zones:` narrowing is allowed only on
  `unmeasured`. `encoded` names what it became (`encoded_as`).
- **Scope.** A footnote governs its whole notes-block region. Before refusing
  "use not listed", walk each marker back up its column to the row it sits
  in. Footnote markers are specific to a column.
- **Rulings bind to words.** The key is `flats.encode.dispositions.digest`,
  so a ruling travels wherever the same sentence is reprinted.
  - The reason must be true everywhere the sentence appears.
  - The reason must argue about the page, not about our corpus. "That zone
    is not encoded" goes stale the day it is encoded, and nothing flags it.
  - Guards: `flats/encode/stale.py`, `flats/encode/travelled.py`
    (`partial` / `shadowed`).
- **Splitting a body splits its ruling.** Any reader change moves digests
  and silently un-reads rulings.
  - Dump the unread list before and after, and diff it.
  - Census counts will not show the change.
- **An `unmeasured` prohibition is not settled.** The zone still owes its
  dimensions. A settled `quadplex_allowed: false` owes none
  (`test_unsettled_gates.py`).
- **Check both directions.**
  - Value → note: `flats/encode/qualified.py`. Run `--write-caps` to
    regenerate `flats/config/caps.json`.
  - Note → value: `flats/encode/applied.py`.
  - Dismissals: `flats/encode/waved.py`.
- **A closing reason that quotes a sub-clause** must show the parent
  sentence does not reach. A parking chapter declined on a quantity or cap
  argument has not addressed geometry (stall, aisle, placement). This
  happened in two layers.
- **Read the branch before adding a state.** A width "ceiling" on townhouse
  parking turned out to be a condition on the front-parking option, which
  the pod does not take. It is bound to the catalog by
  `test_the_townhouse_lane_ceiling_is_a_condition_of_a_branch_the_pod_does_not_take`
  (`test_paper.py`).

## 6. Site facts

- **Unknown facts stay unknown.** A condition nothing measures is a site fact
  with no assumed value, and the screen answers UNKNOWN. Never guess a site
  fact to unlock a variant.
- **Measured per lot line** (`flats/geom/`):
  - `abuts_alley`, which entails `alley_at_rear` / `alley_at_side`
  - `fronts_cul_de_sac` (a bulb lot is one front)
  - corner fronts (`front_lot_line_corner`)
  - corridors
  - neighbour zoning (`abuts_lower_density_zone` and siblings)
  - `abuts_park` (Metro ORCA unit types across each line)
- **Parks.** They are a `parks:` block naming which ORCA unit types the
  code's own definition of a park covers. A type on neither list leaves the
  line unresolved. Encode a park row one condition deeper than the zero it
  overrides (`[abuts_nonresidential_zone, abuts_park]`), because there is
  no negation. Guard: `test_park.py`.
- **Neighbour zones.** They are a `neighbours:` block with
  `true_for` / `false_for` lists.
  - Write `yes` / `no` quoted: bare, YAML reads them as booleans.
  - A condition that tightens on any line is settled by one residential
    point. A condition that relaxes on every line needs every line read.
- **The caps trap.** Declare a neighbour condition only where no state cap
  applies to that value. Guard:
  `test_neighbour.py::test_no_declared_condition_caps_a_value_on_that_layer`.
- **One geometric test at real coordinates.** Any new geometric reading gets
  one test at state-plane coordinates.
  - For a new reading, the check is the diff on the population that was
    already measured.
- **A measurement must rule in both directions.** A measurement that can only
  rescue lots is an amnesty.
  - Where it declines to measure, the lot keeps exactly its old treatment.
- **An absent overlay layer grades as clear land.** Close the data gap
  before trusting a new county's GREENs.
  - Only the city's code decides whether an overlay carves, flags or kills.
  - "Other than those allowed by this section" is not yet a prohibition.
  - Applicability is not restriction.
  - Guards: `Lot Analysis/quadfit/tests/test_overlay_reach.py`,
    `UNSCREENED` in `test_zone_mirror.py`.

## 7. Parking and fit rulings

- **Charge the court on both axes.** The court is charged as depth and as
  width (`flats/score/paper.py`: `court_depth`, `court_across`). The screen
  fits through `screen.fit_for`.
  - The court stands off the rear wall. Depth is the gap, plus the stall,
    plus the two-way aisle.
  - A one-row court is still two-way: a car reaches it down one lane and
    leaves the way it came.
- **A city asking less does not shrink the design.** Only a city asking more
  raises it. This is the `max()` rule for stall, aisle and buffer.
- **A narrower search is not evidence either way.** A fit searched narrower
  than the zone asks gives `COURT_WIDTH_UNMEASURED`, which screens UNKNOWN,
  never RED.
- **A city that dimensions a stall but states no aisle:**
  - Assume the ULI/NPA 24 ft two-way aisle at 90° and flag it
    `geometry_assumed`.
  - Never borrow an aisle table the city excepted this building from. That
    is the borrowed dimension the layers exist to refuse.
  - Under ORS 197A.400 (clear and objective standards only), silence may go
    GREEN (Steph, 2026-08-31).
- **The unit-lot path is a variant.** The screen draws `one_lot`, and
  `unit_lots` standards are variants. A shared court on the building's own
  lot is not a "tract".
- **No garage.** `setback_garage_entrance_ft` is declared excluded. Guard:
  `test_no_catalog_design_has_a_garage`.
- **An alley along part of a line (Steph, 2026-09-28).** s4 calls a line an
  alley line on three rays of five, and `alley_cover_json` records how much
  of it the alley really runs.
  - Setbacks: the alley's number applies only to the covered stretch. A side
    line is cut stretch by stretch (`flats.geom.envelope.buildable`). So is a
    rear line: the rules' rear variant (exempt or alley number) switches on
    only when the alley runs the whole rear line
    (`flats.geom.alley.registry_alley`); on a part-covered rear line the
    bridge resolves the lot again with `alley_at_rear` and the covered
    stretches take that rear, the rest the larger of the two
    (`flats.ingest.quadfit.part_rear_alley`). The court is then charged
    against the smaller strip, and the screen keeps whichever of the two
    cuts (stretch, or whole line at the ordinary rear) answers better. No
    cover on record = no stretch = the whole line at the ordinary rear.
  - Two rear lines, one on the alley (a corner lot's line opposite the side
    street, a jogged rear): the rear variant reaches only the rear line on
    the alley; the other keeps the ordinary rear setback. The bridge resolves
    the lot twice, with and without `alley_at_rear`
    (`flats.ingest.quadfit.rear_off_alley`, `Setbacks.alley_rear_ft`).
  - Back-out aisle: a part-covered rear alley still reaches the court (no
    street lane). It is the court's aisle only where the longest covered
    stretch with the envelope right behind it (`usable_run_ft`) is at least
    the row of stalls: stalls × stall width, no end clearance, since
    `court_across` charges none (`Alley.rear_aisle_for`).
  - The fit does not place the court along the rear line, so only the
    length is compared. Missing or unreadable cover means no alley aisle.

## 8. Verification and second reading

- **Second readings are blind.** A second reading re-reads numbers without
  seeing our answer.
  - This puts the whole checking burden on triage afterwards. Never skip
    triage.
  - Too little context fakes disagreements.
  - Tools: `flats/encode/reread.py`, `flats/encode/corroborate.py`.
- **Accuracy and completeness are two rates.** Never report them as one
  (`flats/encode/reading_rate.py`).
- **Ledgers to regenerate before trusting** (all under `flats/encode/`):
  - `crossrefs`, `uncited`, `missed`, `consumed` (standards no screen reads)
  - `qualified`, `applied`, `waved`, `stale`, `travelled`, `unheld`
  - `refusals`, `exemptions`
- **A ledger's own size can be the tell.** A blind reader, or a regex that
  is dead, reports a clean corpus. Zero markers is not proof of nothing.
- **Tests assert the mechanism, not the inventory.** A test that pins a
  corpus condition is designed to go red the day the corpus is fixed.
  - That is the test working: re-rule, don't re-pin.
  - The guard for a known gap is a test that fails when the gap closes.
- **Before any commit that encodes zoning values**, run
  `uv run pytest flats/tests -q -n auto` and `pytest "Lot Analysis/quadfit/tests"`.
  The second compares what the county map runs on against what was read
  (`test_zone_mirror.py`).
  - Then read CI. A red CI has been pushed past before.
- **A bound run is not clean until the lots it loses and the lots it gains
  have been read one by one.**
  - Read the LOST and GAINED lots and replay them.
  - A stricter search needs its own read of what it loses.
- **The county-map copy is refreshed quarterly and by hand.** A new zone
  code screens `unknown / ZONE_NOT_ENCODED` and warns; it does not block.
  See [flats-county-refresh.md](../ops/flats-county-refresh.md).

## 9. What not to do

- **Evidence.**
  - Don't guess a site fact, a column or a noun to unlock a variant.
  - Don't let an assumption stand in for a stated number without flagging
    it.
- **Provenance.**
  - Don't cite a paraphrase, a footnote marker or a section range.
  - Don't mark anything `verified` yourself.
- **Copying.**
  - Don't hand-copy a zone.
  - Don't borrow a number from a table the city took off this building.
- **Absence claims.** Don't write "the code states nothing" without a
  whole-corpus grep and a cross-reference read.
- **Test pins.** Don't re-pin a corpus-inventory test to make it green.
  Change the ruling or the mechanism.
- **Drift.** Don't treat drift as an amendment until the old-library
  extraction has been diffed.
- **Screening scope.** Don't switch a jurisdiction back on by editing
  `eligible:` without the owner. `eligible: false` (Lake Oswego) is Steph's
  decision, tracked in [docs/HUMAN_TODO.md](../HUMAN_TODO.md).
- **Firewall.** Don't touch `app/engines/` in the same commit as `flats/`.
- **Heredocs.** Don't write test rewrites with a bash heredoc. One once put
  a literal backspace into a regex. Use a file-writing tool.

## 10. Steph's standing rulings

| Date | Ruling | Consequence |
|---|---|---|
| 2026-08 (standing) | "Encoding is where this project lives or dies." Provenance is exhaustive capture, deferred judgement; a paraphrase cannot be a citation | §3–4 |
| 2026-08-26 | "We want to know what we would have to do if we do parking." | Parking geometry is encoded even where the count is zero |
| 2026-08-31 | A published-nowhere aisle may be **assumed** at the national 24 ft minimum and may go GREEN (ORS 197A.400: silence is the stronger position) | `geometry_assumed` is a provenance column, not a verdict |
| 2026-09-03 | No accessible stall is owed for a 2-storey, no-elevator pod (OSSC 1106.3 / 1108.6.2.2.2 / 1108.7.2) | A single-storey product would change this. Some cities trigger an accessible stall if guest parking is provided |
| 2026-09-08 | No garage. Yes to the 10% open space. Charge the parking aisle | §7 |
| 2026-09-10 | Height is a dial, band 25–30 ft; price it, don't fix it | `flats.encode.height --at` |
| 2026-09-13 | **The alley is the aisle.** A stall standing on an alley backs out into it | Alley lots need no court aisle |
| 2026-09-18 | "Same as the county map. **4 is enough to sell.**" Charge the floor; report the seat count beside the colour | `StallBands(floor, target, preferred)` in `flats/designs/model.py`. `parking_cap` fails a lot whose cap is below the floor |
| 2026-09-19 | **More parking is not a goal.** Tie-break: GREEN > preferred band > least street exposure. Never "most stalls" | Plan ranking |
| 2026-09-19 | County data source: the county copy lives in the app DB, refreshed quarterly by hand. Promote: "me, when clean; you, when warned" | [flats-county-refresh.md](../ops/flats-county-refresh.md) |
| 2026-09-22 | A new zone code warns, does not block, and screens UNKNOWN until ruled (within the week) | same runbook §8 |
| 2026-09-25 | Batch re-screens. Partial re-screens (splice) are allowed | runbook §4c |
| 2026-09-26 | Corner lot front: "abide if Portland has guidance". Follow each code's own corner-front definition | `front_lot_line_corner`, `flats/geom/corner.py` |
| 2026-09-28 | **An alley along part of a lot line.** "Careful reading agreed. And we can use the portion the alley abuts for our travel lane only if the lane is actually long enough to accommodate" | §7. Setbacks: the alley's number reaches only the stretch the alley covers; a rear variant needs the whole rear line. Back-out aisle: the stretch the alley covers, with the envelope behind it, must be at least as long as the row of stalls (stalls × stall width), else the court keeps its own aisle. No cover on record = no alley aisle |
| standing | All of Oregon is the acquisition market. Data coverage is a separate task | CLAUDE.md |

## 11. Checklist: a new county's first pass

1. **Set the county up.**
   - Create `flats/config/jurisdictions/or/<county>/`. Add one layer per city
     plus `_unincorporated.yaml`.
   - Start every layer `eligible: true`. Record who decided otherwise if any
     layer is switched off.
2. **List the documents.**
   - Declare every chapter in `code:`, each with an `end:` marker and any
     reader switches.
   - Include the definitions, parking, access, streets and public-works
     titles.
   - Fetch with `python -m flats.provenance.fetch --layer or/<county>/<city>`.
3. **Read the definitions first.**
   - Middle-housing clause, housing-type nouns, lot-line and corner
     definitions, net acre.
   - Record them in `definitions:`, plus any `definitions_at:` spans.
4. **Build the zone list** from the use table and the map legend.
   - Run `flats/encode/districts.py`.
   - Add rulings to `test_districts.py` (and `BY_HAND` for anything no
     harvest can see).
5. **Rule the use gate per zone** (`quadplex_allowed`, a use-table cell).
6. **Encode the dimensions.**
   - Conservative base, variants behind registered conditions.
   - Per-line fields for per-line rules.
   - `like:` for twins.
   - A NOT ENCODED comment for every refusal.
7. **Encode parking.** Count, stall, aisle, driveway, placement, corner
   access. Encode them even when the count is zero.
8. **Rule every footnote.** Write the rulings to
   `flats/config/footnotes/or/<county>/<city>.yaml`. Walk each marker to its
   row and column.
9. **Run the ledgers:**
   - `crossrefs` (the BINDING rows first), `missed`, `uncited`, `consumed`
   - `qualified --write-caps`, `applied`, `stale`, `travelled`, `unheld`
10. **Grep for prohibitions** in every stored chapter.
11. **Check the overlay and environmental layers** exist for the county
    before trusting any GREEN.
12. **Tests.**
    - Run `uv run pytest flats/tests -q -n auto` and the quadfit tests.
    - Update `EXPECTED` in `test_refusals.py`.
    - Add one test per surprising reading.
13. **Re-screen and read the losses.** Bound the change, re-screen, then
    read the lost and gained lots before promoting.
14. **Leave signing to a human.** Record anything owed in
    [docs/HUMAN_TODO.md](../HUMAN_TODO.md).

## 12. Where things are

| What | Where |
|---|---|
| Design and full reasoning | [Lot Analysis/FLATS_PLAN.md](../../Lot%20Analysis/FLATS_PLAN.md): §2 encoding problem, §16 variants, §17 zones with no standards, §18 where a code lives, §22 adopted document, §26 housing type, §27 corner lots |
| Field registry, required/optional | `flats/rules/fields.py` |
| Loader, value forms, model | `flats/rules/loader.py`, `flats/rules/model.py`, `flats/rules/resolver.py` |
| State caps / `caps.json` | `flats/rules/caps.py`, `flats/config/caps.json` |
| Conditions (variant `when:`) | `flats/rules/conditions.py` |
| Layers | `flats/config/jurisdictions/or/<county>/*.yaml`, `or/_state.yaml` |
| Footnote rulings | `flats/config/footnotes/or/<county>/<city>.yaml` |
| Pod designs | `flats/config/pods/`, `flats/designs/model.py` |
| Fetch / store / drift | `flats/provenance/fetch.py`, `store.py`, `repoint.py`, `pdf_hold.py` |
| Reading tools and ledgers | `flats/encode/` (`readiness`, `columns`, `glossary`, `districts`, `crossrefs`, `missed`, `qualified`, `applied`, `refusals`, `exemptions`, `height`, …) |
| Lot geometry (site facts) | `flats/geom/` (`alley`, `corner`, `culdesac`, `neighbour`, `corridor`, `envelope`) |
| Screen and paper lot | `flats/score/screen.py`, `flats/score/paper.py` |
| County map pipeline | `Lot Analysis/quadfit/` (+ `tests/`), bridge in `flats/ingest/quadfit.py` |
| Refresh / promote runbook | [docs/ops/flats-county-refresh.md](../ops/flats-county-refresh.md) |
| Test commands and the census rules | [docs/TESTING.md](../TESTING.md) |
| Human decisions owed | [docs/HUMAN_TODO.md](../HUMAN_TODO.md) |
