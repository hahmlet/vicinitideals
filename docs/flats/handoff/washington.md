# Handoff: Washington County draft (cloud session)

Branch `flats/washington-draft`. Written for the local agent, who has not
seen the cloud session. Scope and traps: [counties/washington.md](../counties/washington.md).
Rules: [ENCODING_RULEBOOK.md](../ENCODING_RULEBOOK.md), [CLOUD_COUNTY_BRIEF.md](../CLOUD_COUNTY_BRIEF.md).

Last updated: 2026-09-29, checkpoint 4. The unincorporated layer is
finished as a draft: every one of the 42 codes on the county's zoning map
is encoded, and rulebook steps 1-10 and 12 are done for it. The cities
have not been started. Every value is `draft`; nothing is `verified`.

## 1. Cities

| Jurisdiction | State |
|---|---|
| Unincorporated (county CDC) | Draft done, steps 1-10 and 12. 34 documents, 42 zones. Step 8 (footnote rulings) could not be run by the tool; the notes were read by hand, see Documents |
| Hillsboro | Next, in progress. Municode publication 4450 (Community Development Code). Nothing for it is committed yet |
| Beaverton | Not started. Not on Municode; city site reachable |
| Tigard | Not started. Not on Municode or codepublishing under that name |
| Forest Grove | Not started |
| Sherwood | Not started. Municode publication 3865 (Code of Ordinances) |
| Cornelius | Not started. City site did not answer from the cloud |
| King City | Not started. Municode publication 3913; city site did not answer |
| Durham | Not started |

## 2. Documents

Unincorporated: 34 slices of the CDC PDF, Municode publication 3090
(`https://api.municode.com/PublicationPdfDownload/3090`), Supplement No. 3,
September 2026, through Ordinance No. 914. Stored under
`flats/provenance/docs/or/washington/_unincorporated/`. All `extraction: plain`.
Sections held: 106, 300, 302-309 (R-5 to FD-10), 311-314, 320, 330, 340-356
(rural), 375 (transit-oriented), 377 (SID), 390 (North Bethany), 391 (Bonny
Slope West), 392 (mixed use), 413 (parking), 418-419 (setbacks, height),
430-84 (Middle Housing), 501 (public facilities).

Eight slices are declared `allow_thin`: 106, 300, 342, 354, 377, 391, 430-84,
501. Each was read before the flag went on. The cause is the same in all
eight: `fetch._SECTION_NO` counts only dotted section numbers ("19.30.010"),
and the CDC writes "302-7.1". The gate sees almost no section numbers in this
code. Worth a look locally: teaching `_SECTION_NO` the hyphenated form would
let the gate judge this county properly. It is a reader change, so it was not
made here.

**The footnote census cannot see this code's notes.** `flats/encode/footnotes.py`
recognises "Notes:" headings, numbered or lettered runs and bracket runs. The
CDC prints its table notes as "Reference Key:" blocks (392), as unheaded
lettered runs (A)-(H) under 375 Table B(2), and as `*`, `**`, `***` under
Table B(1). The census finds none of them, so no
`flats/config/footnotes/or/washington/_unincorporated.yaml` was written and
`qualified` / `applied` report zero for the county. Every one of those notes
was read by hand and is either encoded, refused in a layer comment, or a
doubt below:

- 375 B(1): `*` measures from the parent lot before right-of-way dedication;
  `**` appurtenances; `***` separation for Middle Housing Land Divisions.
- 375 B(2): (A) step-back above the third floor; (B) a community-plan height;
  (C) accessory buildings 15 ft; (D) height modification; (E) Section 418;
  (F), (G) the front-yard maximum; (H) interior yards under 411 and 431.
- 375 C(2): FAR notes (1)-(3).
- 392 Reference Key (1)-(4).

Teaching the census "Reference Key:" is a reader change for local review.

Not stored: the eleven Community Plans, 404 (Planned Development), 406
(building design), 411 (buffering), 430 outside 430-84 (special uses,
including 430-37), 431 (transit-oriented design) and the CWS Design and
Construction Standards.

Failed fetches: none yet.

## 3. Zones

Unincorporated. The zone list comes from the county's own zoning layer
(`gispub.co.washington.or.us/.../Open_Data_AGOL/MapServer/2`, field `LUD`),
which carries 42 codes. All 42 are encoded. The zone keys are the LUD
spellings, which is how a lot finds its zone: the layer writes `MA-E` where
the CDC heading writes MAE.

**The pod on one lot (15).** `quadplex_allowed: true`:

- R-5, R-6, R-9, R-15, R-24, R-25+: Middle Housing per 106-124 (Type I, or
  Type II on large lots).
- R-6 NB, R-15 NB: `like:` the base district, with 390's own density and
  unit counts.
- R-9 NB, R-24 NB: through 390's "Attached Dwelling Units" row, with
  dimensions from 304 and 306; see Doubts.
- TO:R9-12, TO:R12-18, TO:R18-24: Middle Housing, 375 Table A, Tables B(1)
  and C(1). TO:R12-18 and TO:R18-24 are `like:` TO:R9-12.
- NMU, CCMU (392): attached dwellings, Type II. 6,000 sq ft, 85 ft average
  width, 40 ft at the access point, 50 ft depth, 10 ft front and street side
  with a 20 ft front maximum, parking kept out of the front and 5 ft back
  from the street. Height 65 (NMU) and 100 (CCMU). Density 20-25 (NMU) and
  20-40 (CCMU) units per acre.

**Only on unit lots (3).** TO:R24-40, TO:R40-80, TO:BUS: four units on one lot
`false`; a townhouse split onto lots of its own is the `unit_lots` variant.

**Only through a Planned Development (1).** CBD: `false`, with the variant
`true` behind `planned_development`; 20-40 units per acre; every dimension
owed.

**Refused (23).** `quadplex_allowed: false` with a cite and no dimensions:

- North Bethany: R-25+ NB, NCC NB, NCMU NB, INST NB.
- Transit-oriented: TO:RC, TO:EMP.
- Commercial and institutional: NC (dwellings only over a commercial ground
  floor), OC (only inside a Type III mixed-use office development), GC,
  IND, INST, SID.
- Holding: FD-20, FD-10 (one detached dwelling). The use gate is ruled from
  the CDC use lists; neither district is named in 106-124.
- Rural: EFU, EFC, AF-20, AF-10, AF-5, RR-5, R-COM, R-IND, MA-E.

**Ruled, not encoded.** TO:R80-120 is named in 375-2 and has a Table A
column, but carries no lot on the county's zoning layer. It is ruled
`not-listed` in `test_districts.py` `BY_HAND`: Table A has no row for four
units on one lot there, the same reading as TO:R24-40. ASC 2 (overlay), RPZ,
THPRD and TVWD (not zones) are ruled in `RULINGS`.

## 4. Refusals and absences

Layer-wide NOT ENCODED entries in `_unincorporated.yaml`, each with its quote
in the layer comment:

- the porch front-yard figure;
- yards measured from a sidewalk or public-travel easement;
- right-of-way dedication;
- the 419-1 height step-down beside a lower district, and 419-7 airport
  heights;
- 30X-5.6, "high density residential" prohibited in airport approach zones;
- the 430-37 future-development plan;
- the eleven Community Plans;
- the Bonny Slope West overlay (391), including its driveway ban at the
  rural edge (Area of Special Concern 18);
- a parking maximum (413-6.3 has no row for four non-studio units);
- the 430-84.3 B(4) driveway-spacing rules by street class.

On districts:

- Transit-oriented: a Middle Housing height that needs "does not abut R-5 or
  R-6"; minimum FAR; the unstored 431 design standards.
- Mixed use (392): frontage occupancy; the 392-9 facade standards; the
  higher density ranges bought with plazas and open space; the per-dwelling
  outdoor area (307 via 392), on which even the base range depends.
- North Bethany: 390-20 facade and siding standards; 390-22.1 windows and
  roof equipment; 390-18.5 and 390-19.2 A, the mapped Natural Features
  Buffer and the driveway ban at the rural edge.

The step-10 prohibition grep found one more rule that reaches toward the pod
and stops: every R district's X-5.2 prohibits living in a "manufactured
dwelling", and 106-131 defines that by highway transport and trailer,
mobile-home or federal HUD construction. The pod is none of those. Recorded
as a layer comment, and pinned in `test_washington_unincorporated.py`.

"The code states nothing": corner lot is not defined anywhere in the 34
stored chapters (grep for "corner lot", "lot, corner", "corner parcel");
parking placement for a quadplex is silent in 430-84.3 and 413.

## 5. Doubts

Each is written the conservative way in the layer, with a comment.

- **Type II procedure.** On larger lots Middle Housing is Type II, still an
  administrative approval with standards; read as allowed. NMU and CCMU are
  Type II too.
- **Yards from a sidewalk easement** (each district's 7.1 B). Nothing measures
  it.
- **Right-of-way dedication** changes where the front yard starts.
- **419-1 height step-down** beside a district capped under 26 ft.
- **Airport approach zones** (30X-5.6, 419-7).
- **Street-class driveway rules** (430-84.3 B(4), 501-8.5): corner access held
  as `lowest_class`.
- **Sufficient Infrastructure** (106-124 B, 106-210): read as something the
  applicant may provide, not a use gate.
- **430-37.1 B shadow plat** on large lots.
- **Townhouse front-yard parking** on collectors (430-84.4 B(5)).
- **North Bethany:** 390-3 makes the Bethany Community Plan control; not read.
- **R-9 NB:** the Middle Housing path is only on lots approved for a detached
  house by a Standard Subdivision or Partition (390-9.2 E, 390-9.3 B). Read
  instead as "Attached Dwelling Units" (390-9.3 A), with R-9's dimensions
  through 390-16.2. `min_lot_sqft` is owed.
- **R-24 NB:** side yard held at 10, not the 7 offered beside "a lower density
  district", because the lower district is not listed. `min_lot_sqft` owed.
  The Kaiser Road (ASC 2) setbacks at 390 L933-L938 are not held.
- **Density rounding** (300-2.5).
- **Transit-oriented side and rear yards (Middle Housing).** Table B(1)
  gives a front yard, a front maximum and a building separation, and no side
  or rear yard. B(2) says "no minimum interior yard" for other development.
  The side and rear fields are left absent (owed) rather than borrowing B(2).
- **Transit-oriented height held at 35.** B(1) allows 40 (TO:R9-12,
  TO:R12-18) or 50 (TO:R18-24), "or 35 feet if abutting R-5 or R-6"; the
  higher figure needs a "does not abut" condition, which cannot be written.
- **Table C(1) "N/A" for the plex rows** read as a cell merged across the
  duplex-to-quadplex rows, so no maximum density applies to a quadplex.
- **Four units on one lot in TO:R24-40, TO:R40-80, TO:BUS (and TO:R80-120).**
  Not listed in Table A (triplexes stop at three; apartments are five or more
  under 106-143), so refused by 375-5.2. Townhouses are listed (Type II).
- **Minimum FAR** (C(2)) and the FAR alternative to minimum density are not
  held; the density minimum is held without its FAR escape.
- **Section 431 design standards** (non-Middle-Housing paths in TO) are not
  stored; those paths' yards are owed.
- **NMU and CCMU frontage.** 392-8 has no frontage row; it prints "Lot
  Width at the Access Point, Minimum 40 feet", held as `min_frontage_ft` 40.
  Its average depth (50 ft) is held as `min_lot_depth_ft`.
- **NMU and CCMU interior yards.** 392-8 prints "Zero feet (3)", and (3)
  makes the yard the abutting district's wherever the lot abuts a
  residential district. Zero needs "does not abut", which `when:` cannot
  say, so side and rear are owed rather than zero.
- **NMU and CCMU facades.** 392-9 sets ground-floor window shares, entries
  and materials on every street-facing facade. The pod's facade is fixed; if
  it fails them the district refuses it in practice. Not held.
- **The Required Outdoor Area.** 392-7 Reference Key (1) makes even the base
  density range depend on the Required Outdoor Area of 307-7.5: 250 sq ft on
  each lot, no dimension under 10 ft. Not held.
- **CBD dimensions.** 313-3.40 A(1) sends dwellings in a Planned Development
  to 307-7 to 307-10 (R-25+), while 313-6 prints CBD's own (8,500 sq ft, a
  20 ft front yard for buildings without multi-dwelling units, 100 ft). Which
  governs is not settled from the text, so every dimension is owed. 404
  (Planned Development) is not stored.
- **OC.** Dwellings only "as part of a mixed use Office Commercial
  Development" through a Type III Planned Development, at most half the
  floor area. A four-unit residential building is not that; refused.
- **FD-10 typo.** 309-5.1 prohibits what is "not specifically authorized in
  Section 308", which is FD-20's number. Read as a typo for 309; the answer
  is the same either way.
- **SID.** The CDC calls it the Special Industrial *Overlay* District (377),
  but the county's zoning layer carries it as the lot's LUD code, so it is
  encoded as a zone and refused (377-1.3 limits development to industrial,
  office and industrial-park uses). The overlay data should say whether a
  base district sits under it.
- **The footnote census** could not see this code's notes; see Documents.

## 6. Questions for Steph

- **North Bethany R-25+.** The county's densest North Bethany district allows
  only "multi-dwelling" housing, which the code defines as five or more units,
  and live/work units with a ground-floor business. A four-unit building fits
  neither, so it is refused. The other reading treats four units as a small
  apartment building and would open every lot in that district. The same
  question decides the three densest transit districts, where the draft
  allows the building only if each unit sits on its own lot.
- **Transit-oriented side and rear yards.** In the three transit districts
  that allow middle housing, the code gives a front yard and a gap between
  buildings but no side or rear yard for middle housing. For other buildings
  it says there is no minimum. Should a fourplex there be screened with no
  side or rear yard, or held back until someone confirms?
- **Community Plans.** Eleven county community plans can change setbacks and
  other standards by named area. None was read. Should they be read before
  the county screens, or screened now and read later?
- **Facade rules.** North Bethany and the two mixed-use districts have
  design rules for the front of the building: window shares, garage
  placement, siding materials. The screen has no way to describe the
  building's front. Should those districts screen now, with the design rules
  left for the building design to satisfy, or wait?

## 7. Tests

Last full run before this commit (`uv run pytest flats/tests -q -n auto`,
checkpoint 4, all 42 unincorporated zones), 2026-09-29:

**1 failed, 3609 passed, 5 skipped in 320 s.**

The one failure is expected and is not fixed here:

- `test_unweighed_layers.py::test_no_encoded_layer_is_outside_the_corpus_that_ranks_the_work`
  lists `or/washington/_unincorporated`. The coverage ledger that ranks the
  work has no Washington County lots, because building it needs the county
  map and quadfit, which are local work (Owed locally). It will fail for
  every Washington layer this branch adds, until the ledger is regenerated
  with the county in it. Nothing in the layer can make it pass, and the test
  is not edited.

Earlier runs on this branch had five more failures (ledger currency, pinned
counts). They were closed by regenerating `gaps.json` and `exemptions.csv`
and by updating the pinned counts below.

Pinned counts moved here, each with a dated paragraph in its test:

- `test_port.py`: 20 layers, 314 zones.
- `test_refusals.py`: comments 148 (from 127), notes 122, tests 17.
- `test_exemptions.py`: stated 272, numeric 55, marker 0, dash 2, silent 2.
- `test_districts.py`: four unincorporated rulings (ASC 2 overlay; RPZ,
  THPRD, TVWD not zones) and TO:R80-120 in `BY_HAND`.
- `flats/config/gaps.json` and `data/flats/exemptions.csv` regenerated.

New: `test_washington_unincorporated.py` (8 tests): the fifteen one-lot
districts, the three unit-lot-only districts, the five-unit multi-dwelling
definition behind R-25+ NB, CBD's Planned Development variant, the rural
refusals carrying nothing but the cite, the manufactured-dwelling definition,
the LUD spelling MA-E, and nothing `verified`.

Ledgers (step 9), unincorporated only:

- `crossrefs`: 152 unfetched BINDING references. The loudest: 411
  (buffering), 430 (special uses), 431-8, 375-7.32, 207-5, 300-2, 422-11,
  430-2.1, 421, 430-53.2.
- `uncited`: 290 statements of 790 measured lines not cited. Mostly
  standards on paths the pod does not take (detached houses, townhouse lots,
  commercial buildings).
- `missed`: values the harvest found that the layer does not hold, all on
  other paths, e.g. the R-24 townhouse lot widths (14 and 23 ft), NC's
  8,500 sq ft, IND's 200 ft average width.
- `consumed`, `stale`, `travelled`, `unheld`: no Washington rows.
- `qualified`, `applied`: zero, because no footnote rulings exist (see
  Documents). `qualified --write-caps` left `caps.json` unchanged.

## 8. Owed locally

- quadfit rules for Washington County, the county map, and the overlay data
  (including Clean Water Services vegetated corridors, which 300-3.1 counts as
  unbuildable; the North Bethany Natural Features Buffer and Density
  Restricted Lands; airport approach zones; Areas of Special Concern).
- The blind second reading, re-screen and promotion.
- The coverage ledger regenerated with Washington lots, so
  `test_unweighed_layers` and `DECLARED_OWING` can see the county. Thirteen
  admitting zones owe required fields, and each will need a
  `DECLARED_OWING` entry in `test_unsettled_gates.py` once the ledger sees
  them. Drafted reasons:
  - R-9 NB, R-24 NB: `min_lot_sqft`. 304-7.2 A and 306-7.2 A state a lot
    area for detached units and for attached units "on individual lots"
    (2,400 and 1,300 sq ft per unit) and none for attached units sharing
    one lot, which is the pod. The density maximum sizes the lot.
  - TO:R9-12, TO:R12-18, TO:R18-24: `setback_side_ft`, `setback_rear_ft`.
    375 Table B(1) gives Middle Housing a front yard and a separation only;
    B(2)'s "no minimum interior yard" is for other development.
  - TO:R24-40, TO:R40-80, TO:BUS: `setback_front_ft`, `setback_side_ft`,
    `setback_rear_ft`. The townhouse path takes B(2), which prints "None"
    and whose notes (E) and (H) keep 418, 411 and 431; only 418 is stored.
  - NMU, CCMU: `setback_side_ft`, `setback_rear_ft`. 392-8 prints "Zero
    feet (3)", and (3) makes the yard the abutting residential district's.
  - CBD: `max_height_ft`, `min_lot_sqft`, `setback_front_ft`,
    `setback_side_ft`, `setback_rear_ft`. 313-3.40 A(1) and 313-6 conflict.
- Fetching 404, 411 and 431 would close most of those.
- Pointing the Tualatin, Portland, Wilsonville, Lake Oswego and Rivergrove lots
  in Washington County at their existing layers (county-map work).
- HB 2138 (2025) requires middle housing on every residential lot from
  2027-01-01. It may bring North Plains, Banks and Gaston into scope. Not acted
  on here.

## Reader changes (before and after)

- `flats/encode/glossary.py` learned the CDC's hyphenated section numbers
  ("106-173"). Before: 24 of the county's 225 numbered definitions found,
  quadplex and corner lot not among them. After: 204. No other layer's
  glossary changed.
- `flats/encode/readiness.py` accepts "exempt from minimum" as a zero
  statement (only for a value of 0). Before: one misquote across the corpus,
  `or/washington/_unincorporated` `defaults.parking_min_per_unit`. After:
  none. `test_readiness.py` 41 passed.
