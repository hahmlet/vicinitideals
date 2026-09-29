# Handoff: Washington County draft (cloud session)

Branch `flats/washington-draft`. Written for the local agent, who has not
seen the cloud session. Scope and traps: [counties/washington.md](../counties/washington.md).
Rules: [ENCODING_RULEBOOK.md](../ENCODING_RULEBOOK.md), [CLOUD_COUNTY_BRIEF.md](../CLOUD_COUNTY_BRIEF.md).

Last updated: 2026-09-29, checkpoint 5. Two layers are finished as drafts,
rulebook steps 1-10 and 12 done for each: the unincorporated county (all 42
codes on the county's zoning map) and Hillsboro (all 37 zones of Table
12.01.200-1, plus four rulings for the map's other codes). The other seven
cities have not been started; section 1 says what the scout found for each.
Every value is `draft`; nothing is `verified`.

## 1. Cities

| Jurisdiction | State |
|---|---|
| Unincorporated (county CDC) | Draft done, steps 1-10 and 12. 34 documents, 42 zones. Step 8 (footnote rulings) could not be run by the tool; the notes were read by hand, see Documents |
| Hillsboro | Draft done, steps 1-10 and 12. 23 documents, 37 zones, 4 map codes ruled (ANX, CO, SID I-P, SC-BP). Community Development Code, Municode publication 4450 |
| Beaverton | Not started. Code found: the Development Code on encodeplus, a whole-code PDF of 820 pages through Ord. 4879 of 2026-04-02 (`https://online.encodeplus.com/regs/beaverton-or/export2doc.aspx?pdf=1&tocid=001&file=doc-001-pid-607.pdf`, generated on request). City zoning layer `gisweb.beavertonoregon.gov/server/rest/services/Public_SharedServices/pubZoning/MapServer/0`, field `ZONE_NAME`, including 90 `WAcnty` features (county zoning kept under BDC 10.40.1). `apps2.beavertonoregon.gov` refused (CONNECT 502) |
| Tigard | Not started. **Refused:** the code is on eCode360 (`https://ecode360.com/43691505`), which answered 403 (Cloudflare) to curl and WebFetch; the city site answered 403 (Akamai). City GIS unreachable: `maps.tigard-or.gov` and `svr.tigardmaps.com` fail TLS (legacy renegotiation, then an untrusted chain), `gis.tigard-or.gov` CONNECT 502. No workaround was tried. Metro's regional zoning layer (`CITY='Tigard'`) carries the current code names |
| Forest Grove | Not started. **Refused:** the code is only on American Legal (`https://codelibrary.amlegal.com/codes/forestgrove/latest/forestgrovedev_or/0-0-0-4`), which answered 403 to curl and WebFetch; there is no whole-code PDF. City zoning layer reachable (`maps.forestgrove-or.gov/server/rest/services/ForestGrove/Zoning/FeatureServer/16`, field `zoning_code`) |
| Sherwood | Not started. Code found: Municode publication 3865, Supplement 24, through Ord. 2026-001 (932 pages). City zoning layer `services5.arcgis.com/ikEzR7lqVIlrcVFn/.../Planning/FeatureServer/2`, field `CODE`, with interim `UGA` and `Unannex` and county codes on unannexed land |
| Cornelius | Not started. **Refused:** Code Publishing now points to eCode360 (`https://ecode360.com/CO4396`), which answered 403 (Cloudflare); `www.ci.cornelius.or.us` failed TLS. No city zoning layer; Metro's is stale (no R-10). The city's Zoning Map 2025 PDF is reachable. The AGOL "Cornelius Zoning Map" is Cornelius, North Carolina |
| King City | Not started. Code found: Municode publication 3913, Supplement 16, August 2026 (742 pages). City zoning layer on AGOL (`King_City_Current_and_Future_Zoning_Map_WFL1/FeatureServer/1`, field `ZONECLASS`); the `(WC)` codes are county zoning kept. The single-use residential table (16.84.010) has no triplex or fourplex row; Kingston Terrace (16.114) does |
| Durham | Not started. Code found: Development Code revised 2025-11-13, a 137-page PDF (`https://durham-oregon.us/wp-content/uploads/2025/11/Development-Code-Revised-11.13.2025.pdf`). No city GIS; Metro has five codes. Middle housing is permitted in SDR with no quadplex rows |

The seven "not started" rows come from a scout run on 2026-09-29 that
looked for each city's code and zoning map. It committed nothing. The
copies it downloaded were in the cloud session's scratchpad and are not on
the branch. The refusals in the table were recorded, not worked around.
For Tigard's GIS, a TLS workaround was proposed; the permission check
refused it, and it was not retried.

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

**Hillsboro.** 23 slices of the Community Development Code (Municipal Code
Title 12), from Municode publication 4450
(`https://api.municode.com/PublicationPdfDownload/4450`), Supplement No. 1,
May 2026, through Ordinance No. 6508 of 2025-11-04. They are stored under
`flats/provenance/docs/or/washington/hillsboro/`. All are `extraction:
plain`, and none is `allow_thin`; the gate accepted every slice as it came.

Held:

- 12.01 (general, definitions at 12.01.500);
- 12.10 (use categories);
- the zone subchapters 12.21 to 12.27;
- 12.40 (special uses: flag lots, accessory structures);
- 12.50, in four slices: lot and site (100-270), parking (300), circulation
  (400-640) and design (700-920);
- the plan districts 12.60 to 12.68: Downtown, Orenco, Hawthorn Farm,
  AmberGlen, South Hillsboro, North Hillsboro Industrial, and the two Witch
  Hazel Villages;
- 12.80 (applications).

Not stored:

- 12.30 (nonconforming situations);
- 12.70 (procedures, Types I to IV, and the transportation studies).

Neither sets a base-zone standard.

The 12.01 slice declares `definitions_at: L422-L1677`, which bounds the
glossary to 12.01.500, the definitions section. Without it the glossary
read the whole subchapter, including general provisions that are not
definitions, and "skimmed" (see Reader changes).

Figures the layer cannot read, all drawings:

- 12.61.400-A to -D (Downtown front setbacks, frontages, heights);
- 12.50.320-A (the parking zone map);
- 12.50.360-B (stall dimensions);
- 12.64.640-A (AmberGlen Retail Focus Frontage Areas);
- the South Hillsboro Center Cores (12.65.030).

Each is named where it matters in the layer.

The CDC puts in a table's Clarifications column what another code would put
in a footnote. The footnote census therefore found only three things to
rule, all rows of Table 12.40.160-1 (flag-lot access) that begin with a
digit. All three are dismissed in
`flats/config/footnotes/or/washington/hillsboro.yaml`, with the reason for
each. The file also names three tables whose rows end in a number that the
census reads as a marker with no body.

The zone spellings come from the city's zoning layer (LandUseGallery_Prod
MapServer layer 23, field `DESCRIPTIO`, domain `D_LU_ZoningDesc`). It spells
two zones differently from the code, "SID I-P" and "SC-BP", and carries two
labels that are not zones, "ANX" and "CO". All four are ruled in the layer's
`zone_rulings`. ESID is in the code's zone table but was not on the map as
read.

The fetcher warned that the PDF has 3 characters with no Unicode mapping,
stored as �. All three were found and none is cited:

- `cdc.12.50.400-640...txt` L596, a foot mark in "13 feet 6 inches (13'6")",
  an accessway's vertical clearance;
- `cdc.12.66...txt` L564 and L566, a tree-caliper sentence in North
  Hillsboro Industrial.

Failed fetches for Hillsboro: none.

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

### Hillsboro

The zone list is Table 12.01.200-1, which has 37 zones, and all 37 are
encoded. Every zone prints a Housing Types Permitted table with a Quadplex
row, and that row is the use gate. The CDC defines a Quadplex as four units
"on a single lot or parcel" or on four child lots (12.01.500), so the pod is
a Quadplex. A Multiple Dwelling Structure starts at five units. Every density
is per net acre (12.01.500 "Acreage, Net"), so each carries
`measured_on: net_developable_area`.

Layer-wide values (`defaults`):

- no parking minimum at all (12.50.310 A.2);
- a parking maximum of 2 a unit (Table 12.50.320-1, Zone A);
- parking and garages on at most 50% of a street frontage (12.50.715 C.1);
- 32 ft of driveway approach per frontage (C.2.a);
- corner access from the lowest-class street, and from the alley where there
  is one (C.2.c.i);
- both street lines of a corner lot are front lines (12.01.500 "Lot Line,
  Front").

A corner lot is defined (12.01.500, an interior angle of 135 degrees or
less).

**The pod on one lot (22).** `quadplex_allowed: true`:

- The middle-housing zones (12.21): R-10, R-8.5, R-7, R-6, R-4.5, SCR-LD,
  SCR-OTC, SCR-DNC. Lots run from 10,000 sq ft (R-10) down to 7,000 for a
  quadplex. Maximum density is switched off for quadplexes ("Maximum density
  does not apply to ... quadplexes"). Height is 35 ft. SCR-OTC needs
  7,500 sq ft and 50 ft of frontage.
- The multi-dwelling zones (12.22): MR-1, MR-2, MR-3, SCR-MD, SCR-HD. In MR-2,
  MR-3 and SCR-HD the density maximum applies to a quadplex, because those
  tables print no exemption.
- The station-community commercial zones (12.23): SCC-DT, SCC-SC, SCC-MM.
  None has a minimum lot area.
- The mixed-use and urban-center zones (12.24): MU-N, MU-VTC, SCR-V, UC-RM,
  UC-MU, UC-RP.

Flag lots:

- 12.40.160 allows "1 triplex, quadplex or cottage cluster on 1 flag lot" with
  a 25-ft flagpole. So every zone that prints a minimum frontage under 25 ft
  carries a `flag_lot` variant of 25.
- **SCR-OTC and MU-VTC** refuse a flag lot outright. Table 12.21.750-1 says
  "flag lots not permitted", and 12.65.540 says "flag lots are prohibited
  within" MU-VTC. The variant is `quadplex_allowed: false` behind `flag_lot`.

**Only on some of the zone's land (4).** The base value is `false`, with one
variant that admits:

- **MU-C**, behind `local_street`. 12.24.250 G wants 60% of the street-level
  frontage on arterials and collectors in active pedestrian uses, which a
  four-unit residential building cannot give.
- **UC-AC, UC-NC, UC-OR**, behind `inside_mapped_use_area`. The Quadplex row
  bars ground-floor dwellings on a primary street frontage that is wholly or
  partly within a Retail Focus Frontage Area (Figure 12.64.640-A). The
  mapped use area is the land where the use is turned **on**: the complement
  of the Retail Focus Frontage Area. Whoever cuts that map must cut the
  complement, not the figure. Until then the variant cannot fire, so these
  zones refuse everywhere.

**Minimum building heights the pod cannot meet.** The pod is 26 ft and two
storeys. These zones print floors above that:

| Zone | Minimum height | Held where |
|---|---|---|
| MU-C | 45 ft | unqualified, every lot |
| UC-MU | 35 ft | every lot |
| UC-AC | 35 ft | every lot |
| SCC-SC | 30 ft | printed for lots within 800 ft of a light-rail station, held on every lot |
| MU-VTC | 3 stories | printed for the Center Cores (2 outside), held on every lot |

In those five zones the use is admitted and the pod then fails on height.
They are pinned in `test_min_height.py` and `test_height.py`, and each one is
a doubt.

**Refused (11).** `quadplex_allowed: false` with the use row's cite and no
dimensions:

- C-N and C-G;
- I-G, I-P, I-S, SCI, ESID, HSID and SCFI (a caretaker's dwelling only);
- SCBP and SSID.

**Ruled, not encoded (4)**, under `zone_rulings`:

- **ANX** ("Recent Annexation", 7 polygons, 13.75 acres) is `unencodable`.
  See Questions for Steph.
- **CO** ("County", 26 polygons) is a `pocket` of
  `or/washington/_unincorporated`, with the zone read off the county's map.
- **SID I-P** is an alias of I-P. The SID overlay (12.27.600) adds nothing
  that admits a dwelling.
- **SC-BP** is an alias of SCBP.

The zoning layer's other tokens are ruled in `test_districts.py` `RULINGS`:

- overlays: CRO, RFO, SID and SNRO;
- not zones: FAR, GFA, ROW, TIA, UC, WHVS and ZC.

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

### Hillsboro

Layer-wide NOT ENCODED entries in `hillsboro.yaml`. Each is quoted in a
comment between `defaults` and `zones`:

- stall and aisle dimensions (Figure 12.50.360-B, a drawing);
- surface parking placement in the standard zones (12.50.350 C.1), which
  does not reach a rear court;
- 12.50.350 D.1, which requires SCC-DT free-standing residential parking to
  be inside the structure;
- setbacks that yield to wider utility easements (12.50.130 D.2);
- 12.50.130 J: extra setbacks beside alleys under 20 ft and on the fifty-odd
  street segments of Table 12.50.130-1;
- the story count behind "2 ½ stories or 35 feet";
- 12.50.210 usable open space, except in MU-N and MU-C;
- 12.40.104 B.3, which allows up to 10% more lot coverage;
- lot variation "permitted in some subdivisions";
- the plan districts 12.61 to 12.68, each read for what it adds;
- from 12.50.715 C.2, the local-street separation and the collector and
  arterial spacing rules;
- the alley in the front-lot-line definition (see Doubts).

In the zones:

- minimum FAR (MU-C, MU-VTC, SCR-V, SCC-DT);
- "Front Property Line Coverage" and the SCC-DT ground-floor frontage share;
- the MU-N and MU-C height transition of 12.50.140 C;
- SCR-HD's maximum lot size (1,800 sq ft a unit) and its maximum side
  setback of 5 ft;
- MU-VTC's density, which is a count per plan area, not per lot;
- every row that turns on distance to a light-rail station, or on a named
  street or a neighbour's building. The conservative row is held and the
  others are listed in Doubts.

Step 10, the prohibition grep for "quadplex", "plex" and "middle housing"
over all 23 documents. What reaches a four-unit building on one lot:

- each zone's housing-type row;
- the Orenco lot-size sentence (12.62, no quadplex under 7,500 sq ft, which
  SCR-OTC's minimum already says);
- the SCC-DT parking sentence;
- the flag-lot rule and the two zones that ban flag lots;
- the UC zones' Retail Focus Frontage Area clause.

Nothing else prohibits it.

Unlike the county's, Hillsboro's "manufactured dwelling" is no trap. The
definition is "a single detached dwelling unit ... built on a permanent
chassis" (cdc.12.01.general.txt L898-L901), which the pod is not. The
middle-housing zones also list it as L (limited), not N.

"The code states nothing": Zone B in Table 12.50.320-1 has no parking
maximum for a quadplex, and UC-NC's Lot Frontage row has a blank
Requirement cell.

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

### Hillsboro

Each doubt is written the conservative way, with a comment at its line in
`hillsboro.yaml`.

Use and height:

- **MU-C minimum height 45 ft**, printed unqualified in the Requirement
  column, so the pod fails it on every MU-C lot. It reads like a misprint.
- **MU-VTC 3 stories.** Three stories applies inside the Center Cores
  (12.65.030) and two outside. No condition says "outside a core", so the 3
  is held everywhere.
- **UC-MU and UC-AC 35 ft; SCC-SC 30 ft.** SCC-SC's floor is printed for
  lots "within 800 feet of an LRT station", with none beyond, and nothing
  measures that distance.
- **MU-C and arterials.** The 60% active-use frontage (12.24.250 G) is read
  as refusing a four-unit building on an arterial or collector. The use is
  admitted only behind `local_street`.
- **The Retail Focus Frontage Area** (UC-AC, UC-NC, UC-OR). The admitting
  variant sits behind the complement of Figure 12.64.640-A, which nobody
  holds.
- **2 ½ stories or 35 feet.** 12.50.140 B.6 makes a residential story "not
  more than 10 feet". Read that way, 2 ½ stories is 25 ft and the 26-ft pod
  fails. Read as a count, the pod is two stories and passes. The layer holds
  the feet only, as the Fairview precedent does.
- **SCC-DT parking inside the structure** (12.50.350 D.1). The code refuses
  the pod's surface court, but no field can say so, so SCC-DT screens it as
  allowed.
- **The flag-lot variant is missing** where a zone prints no frontage row:
  SCC-DT, SCC-SC, SCR-V, UC-NC, UC-OR and UC-RP.

Distances the screen cannot measure. In each case the stricter row is held
everywhere:

- SCR-DNC density: 15 du/na is printed within 1,300 ft of a light-rail
  station and 9 beyond. The 15 is held.
- SCC-SC density: the floor is 30 within 1,300 ft (24 beyond) and the
  ceiling is 30 beyond (36 within), so the band held is exactly 30.
- SCC-DT density ceiling: 36 du/na inside a Residential Compatibility Area
  and 90 outside one. The 36 is held everywhere, because the 90 would need a
  negated condition.
- SCR-V density: 24 du/na is held. The code prints 24 within 1,300 ft, 15 to
  2,600 ft, and 7 beyond.
- SCR-DNC front setback: 20 ft is printed for Main Street between 5th and
  10th, with 15 elsewhere. The 20 is held.
- SCR-DNC side setback: 10 ft is printed where the lot abuts SCC-DT, with 5
  elsewhere. The 10 is held. See Questions.
- SCC-MM maximum front setback: 15 ft, which the code applies only within
  50 ft of a transit or pedestrian route.
- UC-MU side setback: 10 ft is printed "adjacent to an existing building",
  with none otherwise.
- UC-NC setback: 15 ft is printed along frontage shared with UC-RM.
- UC-RP: the cell is printed "15 feet/none" and the 15 is held.
- R-6 and MR-1 corner lots: 10 ft is allowed "on 1 frontage", but both fronts
  are held at 20.
- SCR-HD density: within 100 ft of a developed standard neighbourhood, the
  code limits density to "7.0 du/na or the adjacent density". The layer holds
  this as `abuts_lower_density_zone`, which is narrower than 100 ft.

What the code prints:

- **Parking maximum.** Zone B's quadplex cell is blank; the Zone A figure of
  2 a unit is held.
- **UC-NC's Lot Frontage row** is blank and left absent.
- **SCR-HD** prints its frontage rows the other way round from its width
  rows; the larger figure is held. Its maximum lot size of 1,800 sq ft a unit
  has no field, so a larger lot passes the screen and fails the code. The
  code gives no maximum front setback row for a quadplex.
- **SCC-DT** gives its front setback and height as figures (12.61.400). It
  has no `max_height_ft`, no front setback, and no frontage share.
- **MU-C open space** is 100 sq ft a unit in the zone table and 200 in Table
  12.50.210-1. The larger figure is held, and the D exemption is not encoded.
- **UC density** is stated in du/na with no formula (12.24.030 G.2). It is
  read on the 12.01.500 net acre like every other zone.
- **MU-VTC density** is a count per plan area, not per lot; not encoded.
- **Minimum FAR and front property line coverage** have no field.
- **The 12.50.140 C height transition** beside existing low buildings is not
  measured.
- **Lot coverage.** 12.40.104 B.3 allows up to 10% more coverage for middle
  housing, but whether that applies without an accessory structure is
  unclear. Every coverage figure held is the table's own.
- **Coverage stated as floor area.** MU-N limits the primary building to
  12,000 gsf and MU-C to 30,000 gsf (40,000 with structured parking). No
  field holds a floor-area cap, so neither is encoded. The pod is far under
  both.
- **12.50.130 J** adds setbacks on substandard right-of-way.
- **12.50.210 D** exempts some middle housing from open space.
- **Misprints.** The Triplex definition is a copy of the Quadplex sentence
  ("4 dwelling units", L924-L926). R-6's standards table is titled "SR-6",
  a zone that does not exist; it is read as R-6. A cross-reference to
  "15.50.715" means 12.50.715 (cottage-cluster height, not the pod). None of
  these decides anything for the pod.

Access and lot lines:

- **The alley as a front lot line.** 12.01.500 makes the line on an alley a
  front lot line. The envelope reads an alley line as a rear or side line,
  so the front setback is not applied to an alley. NOT ENCODED.
- **Alley improvement.** The rule is alley access "improved according to the
  Hillsboro Design and Construction Standards". Improvement is not measured,
  so the rule is applied to every alley.

Map and ledger:

- **ESID** is in Table 12.01.200-1 but not on the city's zoning map as read.
- **CO** footprint: how many of the 26 "County" polygons fall inside the
  JURIS_CITY footprint was not measured.
- **Attribution.** `python -m flats.encode.attribution --layer
  or/washington/hillsboro` reports that 121 of 425 values cite a section
  their text is not in. A script checked every one: the nearest section
  heading above each quote is the section cited. This is Municode's running
  page header lagging the section; no row is wrong.
- **The footnote census** found only the three misread flag-lot rows; see
  Documents.

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

### Hillsboro

- **Recently annexed land ("ANX").** Seven pieces of land, about 14 acres
  in total, have joined the city but have not yet been given a city zone. The
  city's code does not say what rules apply to them in the meantime. My
  understanding of state law, which I did not check this session, is that
  the county's zoning stays in force until the city zones the land. If that
  is right, these lots screen under the county's rules, and the draft can say
  so. For now they are left unscreened. Is that the right reading?
- **Zones that require taller buildings than the pod.** Five zones set a
  minimum building height the 26-foot, two-storey pod cannot meet:
  - MU-C, 45 feet on every lot. This looks like it might be a misprint.
  - UC-MU and UC-AC, 35 feet.
  - SCC-SC, 30 feet near a light-rail station.
  - MU-VTC, three stories in the town-centre cores.

  The draft fails the pod in all five everywhere, because it cannot tell
  "near a station" or "in a core" from the rest. Do you know whether
  Hillsboro enforces these minimums on a small residential building, and
  whether the MU-C figure is real?
- **Busy streets in MU-C.** MU-C wants most of the ground floor along
  arterial and collector streets to be shops or similar active uses. A
  building that is only four homes cannot do that, so the draft allows the
  pod in MU-C only on a local street. Is that too strict, or right?
- **Retail frontage in the AmberGlen urban-center zones.** Three zones ban
  ground-floor homes along streets marked on a city map as retail frontage,
  and allow them elsewhere. Nobody has drawn that map for the screen yet,
  so for now the pod is refused in all three. Should the map be drawn first,
  or is refusing them for now acceptable?
- **"2½ stories."** Several residential zones limit height to "2½ stories or
  35 feet, whichever is less", and say a residential story is "not more than
  10 feet". If that means 2½ stories is 25 feet, the 26-foot pod is a foot
  too tall. If it only counts floors, the pod's two stories pass. The draft
  uses the 35 feet. Which reading does the city use?
- **Downtown parking.** In the downtown zone (SCC-DT), the code says parking
  for a stand-alone residential building must be inside the building. The
  pod parks in an open court, so downtown lots should fail, but the screen
  has no way to say so and will pass them. Should SCC-DT be excluded by hand
  until the screen can express this?
- **Next to the downtown zone.** In SCR-DNC, the side setback is 10 feet
  where a lot borders the downtown zone and 5 feet elsewhere. The screen
  cannot yet tell which neighbour a lot has, so it uses 10 feet everywhere.
  Adding "borders a named zone" would be a change to the rules, which this
  session could not make. Is it worth making?

## 7. Tests

Last full run before the Hillsboro commit (`uv run pytest flats/tests -q
-n auto`, both layers, 2026-09-29):

**1 failed, 3620 passed, 5 skipped in 320 s.** `uv run ruff check flats/`:
all checks passed.

The one failure is expected and is not fixed here:

- `test_unweighed_layers.py::test_no_encoded_layer_is_outside_the_corpus_that_ranks_the_work`
  lists `or/washington/_unincorporated` and `or/washington/hillsboro`. The
  coverage ledger that ranks the work has no Washington County lots, because
  building it needs the county map and quadfit, which are local work (Owed
  locally). It will fail for every Washington layer this branch adds, until
  the ledger is regenerated with the county in it. Nothing in a layer can
  make it pass, and the test is not edited.

Earlier runs on this branch had more failures (ledger currency, pinned
counts, and the Hillsboro values the floors and ceilings tests had never
seen). They were closed by regenerating `gaps.json` and `exemptions.csv`
and by updating the pinned tests below, each with a dated paragraph.

### quadfit's tests (rulebook step 12)

`uv run pytest "Lot Analysis/quadfit/tests" -q`, same tree, 2026-09-29:
**4 failed, 312 passed in 200 s.** All four are in `test_corner_variants.py`
and all four are Hillsboro's corner-lot variants. quadfit is off limits to
this session, so none was edited:

- `test_no_corner_rule_the_screen_could_reach_adds_buildable_room`,
  `test_every_loosening_corner_rule_is_gated_behind_a_plat_we_do_not_draw`
  and `test_the_reachable_corner_rules_are_the_ones_that_take_room_away`.
  Hillsboro is the first city whose corner rule loosens by right: the
  coverage row of the single-dwelling zone tables prints a corner lot 5
  points more than an interior one (R-10 40 to 45, R-7 and R-8.5 45 to 50,
  R-6 and R-4.5 55 to 60), with no land-division gate. The test's own
  docstring calls this good news and asks to be read before it is changed.
  The screen does not compute corner status, so today the interior figure
  binds everywhere, which is the conservative side.
- `test_only_twelve_reachable_corner_rules_can_move_a_building`: 14, not
  12, and a third jurisdiction. Hillsboro adds two corner setbacks that
  tighten: MR-1's front from 15 to 20 ft and R-8.5's side from 6 to 8 ft.

The unincorporated layer adds no corner variant, so these four are
Hillsboro's alone. See Owed locally.

### Pinned counts and sets moved on this branch

- `test_port.py`: 21 layers (20 jurisdictions and the state layer), 351
  zones. Unincorporated took it to 20 and 314; Hillsboro to 21 and 351.
- `test_refusals.py`: notes 129, comments 194, tests 18 (unincorporated
  had taken comments from 127 to 148 and notes to 122).
- `test_exemptions.py`: stated 338, numeric 55, marker 0, dash 2, silent 2
  (272 after unincorporated).
- `test_districts.py`: four unincorporated rulings (ASC 2 overlay; RPZ,
  THPRD, TVWD not zones), TO:R80-120 in `BY_HAND`, and the Hillsboro
  rulings (ANX, CO, and the two alias spellings "SID I-P" and "SC-BP").
- `test_alley.py`: lines keyed to the rear line 28 + 19 + 1 (Hillsboro
  SCR-OTC's rear-loaded yard), and Hillsboro added to the layers whose
  alley access is required (12.50.715 C.2.c.i).
- `test_routing.py` `OPEN`: two Hillsboro rows, 12.61.400 to 12.23.300 and
  12.61.400 to 12.50.845. Why they stay open is under Owed locally.
- `test_height.py`: `STOREY_FLOOR_ABOVE_TWO` = Hillsboro MU-VTC (3 stories
  inside a Center Core, held everywhere).
- `test_min_height.py`: `FLOORS_ABOVE_THE_POD` pins the five Hillsboro
  floors a 26-foot, two-storey pod misses: MU-C 45 ft, SCC-SC 30 ft,
  UC-MU and UC-AC 35 ft, MU-VTC 3 stories. It is pinned both ways, so a new
  floor fails it, and so does one of these that stops binding. A ceiling
  held as exempt (UC-AC's "None") is skipped as no ceiling.
- `test_gresham_last_notes.py`: the silent-maximum pair is now Wilsonville
  OTR and Hillsboro SCC-DT (Figure 12.61.400-D).
- `test_definitions_register.py`: Hillsboro added to the layers that define
  a corner lot (12.01.500, not greater than 135 degrees).
- `test_clackamas_unincorporated_height.py`: the parking-ceiling layers are
  now four, with Hillsboro (Table 12.50.320-1, "Quadplex 2" in Zone A).
  The test was renamed from "the three" to "the four".
- `test_readiness.py`: 42 passed, with the new
  `test_a_city_that_has_no_standards_requiring_parking_states_zero` (see
  Reader changes).
- `flats/config/gaps.json` and `data/flats/exemptions.csv` regenerated with
  both layers.

### New test files

- `test_washington_unincorporated.py` (8 tests): the fifteen one-lot
  districts, the three unit-lot-only districts, the five-unit multi-dwelling
  definition behind R-25+ NB, CBD's Planned Development variant, the rural
  refusals carrying nothing but the cite, the manufactured-dwelling
  definition, the LUD spelling MA-E, and nothing `verified`.
- `test_washington_hillsboro.py` (9 tests): every zone the code lists is
  encoded, the pod on one lot in 22 zones, MU-C only off an arterial, the
  Retail Focus Frontage zones only outside it, the two zones that refuse a
  flag lot (SCR-OTC and MU-VTC, two parametrised cases), refusals carrying
  the use row and nothing else, the ruled map codes, no parking minimum,
  and nothing `verified`.

### Ledgers (step 9)

Unincorporated:

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
- `qualified`, `applied`: zero; the county has no footnote rulings.

Hillsboro:

- `crossrefs --binding`: 4 unfetched. Two are false alarms: the "Minimum
  FAR" figures 0.4 and 1.00 read as section numbers. 12.61.700 G is the
  Arterial Exception Area's 3-storey height, a plan-district section not
  fetched; the draft holds the zone's own figure. 15.50.715 E.4 is the
  cottage-cluster height, a path the pod does not take (the "15." looks
  like a misprint for 12.50.715). Unbound, the loudest are 12.70 and 12.80
  procedure sections.
- `uncited`: 143 statements of 822 measured lines not cited. Mostly tree
  diameters, fence heights, townhouse lot widths and garage-door setbacks.
- `missed`: 143 statements naming a screened field; 82 state a figure the
  layer holds nowhere, 41 one it already carries, 20 no comparable figure.
  Of the 82, 64 sit in sections nothing has been quoted from, e.g. the
  12.40.120 standards for a use the pod is not (15,000 sq ft, 120 and 180
  ft frontage) and fence heights read as building heights.
- `consumed`, `stale`, `travelled`, `unheld`: no Washington rows.
- `applied`: 0 encoded. The three footnote rulings in
  `flats/config/footnotes/or/washington/hillsboro.yaml` are dismissals.
- `qualified`: 14 zones carry the flag-lot frontage qualification from
  12.40 (MR-1, MU-C, MU-N, R-10, R-4.5, R-6, R-7, R-8.5, SCR-DNC, SCR-HD,
  SCR-MD, UC-AC, UC-MU, UC-RM), each "0 unread of 3".
  `qualified --write-caps` left `caps.json` unchanged.

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

### Hillsboro

- **quadfit's corner-variant tests.** Four tests in
  `Lot Analysis/quadfit/tests/test_corner_variants.py` fail on Hillsboro
  (see Tests). Someone local has to decide whether a corner-lot computation
  now has upside (five coverage bonuses that loosen by right) and re-pin
  the count of reachable corner setbacks (12 to 14, adding Hillsboro MR-1
  and R-8.5).
- **`DECLARED_OWING`.** When the coverage ledger sees Hillsboro, one zone
  will owe. The resolver was run directly on 2026-09-29, and SCC-DT owes
  `max_height_ft` and `setback_front_ft`. Drafted reason: "12.61.400 prints
  SCC-DT's front setbacks, minimum and maximum, and its building heights as
  Figures 12.61.400-A to -D, 'Specified in Plan District'; the zone table
  states no figure, and the drawings are unread." Every other admitting zone
  states every required field or exempts it.
- **Map ingest for the four ruled codes.** ANX, CO, "SID I-P" and "SC-BP"
  are ruled in the layer, but the county-map work has to carry them. CO is a
  pocket read off the county's own zoning map lot by lot, and ANX waits on
  the question to Steph.
- **Overlay data:**
  - the Clean Water Services vegetated corridors (the net-acre definition
    subtracts them);
  - the SNRO, CRO and RFO overlays;
  - SID, which is carried as an alias.
- **Map data the variants wait on:**
  - the complement of the Retail Focus Frontage Areas (Figure 12.64.640-A),
    for `inside_mapped_use_area` in UC-AC, UC-NC and UC-OR;
  - the South Hillsboro Center Cores (12.65.030);
  - distance to a light-rail station (800, 1,300 and 2,600 ft);
  - the Downtown Residential Compatibility Area and Arterial Exception Area;
  - the parking zone map (Figure 12.50.320-A).
- **Figures to read by hand:**
  - 12.61.400-A to -D, the SCC-DT front setbacks, frontages and heights,
    which would close the SCC-DT owing;
  - 12.50.360-B, stalls and aisles.
- **The routing reader and sibling numbering.** Two rows in
  `test_routing.py` `OPEN` (12.61.400 to 12.23.300, and 12.61.400 to
  12.50.845) are open only because `routing._is_followed` counts a row as
  followed when the section is the reference or begins with it. Hillsboro
  numbers a standard's subsections as siblings (12.23.360 under 12.23.300),
  so the reader cannot see that they were read. This is a reader limitation,
  not an unread section. It was pinned rather than changed.
- **`Lot Analysis/FLATS_PLAN.md`** mentions
  `test_both_catalogued_pods_clear_every_floor_on_file`. That test no longer
  says "every floor": it now pins the five Hillsboro floors the pods miss
  (`FLOORS_ABOVE_THE_POD`, see Tests). The plan's sentence is stale. It was
  not edited here, because that file is off limits to this session.

## Reader changes (before and after)

- `flats/encode/glossary.py` learned the CDC's hyphenated section numbers
  ("106-173"). Before: 24 of the county's 225 numbered definitions found,
  quadplex and corner lot not among them. After: 204. No other layer's
  glossary changed.
- `flats/encode/readiness.py` accepts "exempt from minimum" as a zero
  statement (only for a value of 0). Before: one misquote across the corpus,
  `or/washington/_unincorporated` `defaults.parking_min_per_unit`. After:
  none. `test_readiness.py` 41 passed.
- `flats/encode/readiness.py` (Hillsboro) adds one more zero statement to
  `_NO_STANDARD`: `\bdoes\s+not\s+have\s+standards\s+which\s+require\b`.
  That is the whole of Hillsboro CDC 12.50.310 A.2: "The City of Hillsboro
  does not have standards which require mandate the provision of parking";
  the stray "require" is the code's. Before: one misquote across the corpus,
  `or/washington/hillsboro` `defaults.parking_min_per_unit`. After: none.
  The pattern is scoped to "does not have standards which require", not to
  "does not have". New test
  `test_a_city_that_has_no_standards_requiring_parking_states_zero`, which
  also checks that the sentence does not quote a 2 and that "does not have a
  front setback line" does not quote a 0. `test_readiness.py` 42 passed.
- Not a reader change, but it changes what a reader sees. Hillsboro's 12.01
  slice declares `definitions_at: L422-L1677`, so the glossary reads only
  12.01.500. Before: 344 entries, 28 out of order, and the chapter was read
  as skimmed. After: 308 entries, 11 out of order, read whole.
  `glossary.py` itself is unchanged.
