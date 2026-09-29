# Handoff: Washington County draft (cloud session)

Branch `flats/washington-draft`. Written for the local agent, who has not
seen the cloud session. Scope and traps: [counties/washington.md](../counties/washington.md).
Rules: [ENCODING_RULEBOOK.md](../ENCODING_RULEBOOK.md), [CLOUD_COUNTY_BRIEF.md](../CLOUD_COUNTY_BRIEF.md).

Last updated: 2026-09-29, checkpoint 3. The unincorporated layer is partly
built: the urban residential, North Bethany and transit-oriented districts
are encoded; the mixed-use, commercial, industrial, holding and rural
districts are not yet. This commit exists so the work survives a
session ending; it is not a finished city.

## 1. Cities

| Jurisdiction | State |
|---|---|
| Unincorporated (county CDC) | Partly done. Steps 1-2 done (34 documents). Steps 3-7 done for R-5, R-6, R-9, R-15, R-24, R-25+, the eight North Bethany districts and the eight transit-oriented districts; the other 20 LUD codes not yet encoded. Steps 8-10 and 12 not yet run |
| Hillsboro | Not started. Municode publication 4450 (Community Development Code) found |
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

Not stored: the eleven Community Plans, 430-37 (the future-development plan
Type II Middle Housing cites), and the CWS Design and Construction Standards.

Failed fetches: none yet.

## 3. Zones

Unincorporated. The zone list comes from the county's own zoning layer
(`gispub.co.washington.or.us/.../Open_Data_AGOL/MapServer/2`, field `LUD`),
which carries 42 codes: AF-10, AF-20, AF-5, CBD, CCMU, EFC, EFU, FD-10, FD-20,
GC, IND, INST, INST NB, MA-E, NC, NCC NB, NCMU NB, NMU, OC, R-15, R-15 NB,
R-24, R-24 NB, R-25+, R-25+ NB, R-5, R-6, R-6 NB, R-9, R-9 NB, R-COM, R-IND,
RR-5, SID, TO:BUS, TO:EMP, TO:R12-18, TO:R18-24, TO:R24-40, TO:R40-80,
TO:R9-12, TO:RC. The CDC also names TO:R80-120 (375-2); it is not in the LUD
layer and will be ruled rather than encoded.

Encoded so far (22):

- R-5, R-6, R-9, R-15, R-24, R-25+: `quadplex_allowed: true` (Middle Housing
  per 106-124; Type I, or Type II on large lots).
- R-6 NB, R-15 NB: `like:` the base district, with 390's own density and
  unit counts.
- R-9 NB, R-24 NB: allowed through 390's "Attached Dwelling Units" row, with
  dimensions from 304 and 306; see Doubts.
- R-25+ NB, NCC NB, NCMU NB, INST NB: `quadplex_allowed: false`.
- TO:R9-12, TO:R12-18, TO:R18-24: `quadplex_allowed: true` (Middle Housing,
  375 Table A, Tables B(1) and C(1)). TO:R12-18 and TO:R18-24 are `like:`
  TO:R9-12, which B(1) prints as one set of columns.
- TO:R24-40, TO:R40-80, TO:BUS: four units on one lot `false`; a townhouse
  split onto lots of its own is the `unit_lots` variant (`true`). See Doubts.
- TO:RC, TO:EMP: `false`.

Not yet encoded: the other 20 LUD codes.

## 4. Refusals and absences

Layer-wide NOT ENCODED entries in `_unincorporated.yaml`, each with its quote
in the layer comment: the porch front-yard figure; yards measured from a
sidewalk or public-travel easement; right-of-way dedication; 419-1 height
step-down beside a lower district; 419-7 airport heights; 30X-5.6 "high
density residential" in airport approach zones; the 430-37 future-development
plan; the eleven Community Plans; a parking maximum (413-6.3 has no row for
four non-studio units); the 430-84.3 B(4) driveway-spacing rules by street
class.

"The code states nothing": corner lot is not defined anywhere in the 34
stored chapters (grep for "corner lot", "lot, corner", "corner parcel");
parking placement for a quadplex is silent in 430-84.3 and 413.

## 5. Doubts

- **Type II procedure.** On larger lots Middle Housing is Type II, which is
  still an administrative approval with standards; read as allowed.
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
  gives the Middle Housing districts a front yard, a front maximum and a
  building separation, and no side or rear yard. B(2) says "no minimum
  interior yard" for other development. The side and rear fields are left
  absent (owed) rather than borrowing B(2). Also a question for Steph.
- **Transit-oriented height held at 35.** B(1) allows 40 (TO:R9-12,
  TO:R12-18) or 50 (TO:R18-24), "or 35 feet if abutting R-5 or R-6"; the
  higher figure needs a "does not abut" condition, which cannot be written.
- **Table C(1) "N/A" for the plex rows** read as a cell merged across the
  duplex-to-quadplex rows, so no maximum density applies to a quadplex.
- **Four units on one lot in TO:R24-40, TO:R40-80, TO:BUS.** Not listed in
  Table A (triplexes stop at three; apartments are five or more under
  106-143), so refused by 375-5.2. Townhouses are listed (Type II).
- **Minimum FAR** (C(2)) and the FAR alternative to minimum density are not
  held; the density minimum is held without its FAR escape.
- **Section 431 design standards** (non-Middle-Housing paths in TO) are not
  stored; those paths' yards are owed.
- **TO:R80-120** is named in 375-2 but not on the county's zoning layer, so
  it is neither encoded nor ruled.

## 6. Questions for Steph

- **North Bethany R-25+.** The county's densest North Bethany district allows
  only "multi-dwelling" housing, which the code defines as five or more units,
  and live/work units with a ground-floor business. A four-unit building fits
  neither, so it is refused. The other reading treats four units as a small
  multi-dwelling building and would open every R-25+ NB lot.
- **Transit-oriented side and rear yards.** In the three transit districts
  that allow middle housing, the code gives a front yard and a gap between
  buildings but no side or rear yard for middle housing. For other buildings
  it says there is no minimum. Should a fourplex there be screened with no
  side or rear yard, or held back until someone confirms?
- **Community Plans.** Eleven county community plans can change setbacks and
  other standards by named area. None was read. Should they be read before
  the county screens, or screened now and read later?

## 7. Tests

Last full run before this commit (`uv run pytest flats/tests -q -n auto`,
checkpoint 3, 22 unincorporated zones): **6 failed, 3596 passed, 5 skipped**
in 4 min 50 s. The six:

- `test_gaps` (written ledger behind the YAML): `flats/config/gaps.json` not
  yet regenerated. `python -m flats.encode.gaps` runs more than twelve
  minutes with this county's documents, so it is regenerated once the layer
  is finished rather than at each checkpoint.
- `test_districts` (unruled designations): county districts not yet encoded
  or ruled.
- `test_exemptions` and `test_refusals`: the ledgers' pinned counts have not
  yet been moved for this county.
- `test_port` (layer and zone counts): still 19 layers and 272 zones.
- `test_unweighed_layers`: Washington has no lots in the home-network
  coverage corpus. Expected until the local agent regenerates the coverage
  ledger with Washington lots; not re-pinned here.

The readiness failure of checkpoint 2 is fixed (reader change below).

## 8. Owed locally

- quadfit rules for Washington County, the county map, and the overlay data
  (including Clean Water Services vegetated corridors, which 300-3.1 counts as
  unbuildable).
- The blind second reading, re-screen and promotion.
- The coverage ledger regenerated with Washington lots, so
  `test_unweighed_layers` and `DECLARED_OWING` can see the county.
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
