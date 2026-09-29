# Handoff: Washington County draft (cloud session)

Branch `flats/washington-draft`. Written for the local agent, who has not
seen the cloud session. Scope and traps: [counties/washington.md](../counties/washington.md).
Rules: [ENCODING_RULEBOOK.md](../ENCODING_RULEBOOK.md), [CLOUD_COUNTY_BRIEF.md](../CLOUD_COUNTY_BRIEF.md).

Last updated: 2026-09-29, checkpoint 8. Five layers are finished as
drafts, with rulebook steps 1-10 and 12 done for each:

- the unincorporated county (all 42 codes on the county's zoning map);
- Hillsboro (all 37 zones of Table 12.01.200-1, plus four rulings for the
  map's other codes);
- Beaverton (all 28 districts of BDC 10.25, plus two rulings for the map's
  other codes);
- Sherwood (21 zones, the codes on the city's zoning map that the code sets
  standards for, plus 14 rulings for the map's other codes);
- King City (all 14 districts of KCMC 16.80.020, plus 12 rulings for the
  map's other spellings and the county codes it keeps).

Durham is next. Tigard, Forest Grove and Cornelius refused the fetch and
are recorded, not drafted; section 1 says what the scout found for each. Every value is `draft`; nothing is `verified`.

**Read this first about Beaverton.** No Beaverton lot can come back GREEN
as drafted. The county brief asks for the annexation condition (UPAA §V.D)
to be declared rather than guessed, and it is declared on every admitting
zone's setbacks, lot size and height. The fact it turns on
(`site_specific_limitation`) is one nothing measures and the registry does
not assume, so every lot the pod otherwise fits reads UNKNOWN. That is
deliberate; see Questions for Steph.

**Read this first about Sherwood.** Two readings decide most Sherwood
lots, and both are the strict one:

- 16.68.030 ("Building Design on Infill Lots") is applied to every lot,
  not only to infill lots. Its first sentence names every structure over
  24 feet, and the pod is 26. That brings a floor area ratio in LDR, MDRL,
  MDRH and HDR, and a side setback of 6 feet instead of 5. At LDR's
  7,000 sq ft minimum lot the ratio allows 3,500 sq ft of floor, and the
  pod has 4,000 to 4,032, so an LDR lot needs about 8,064 sq ft.
- A lot in a residential PUD never comes back GREEN. The PUD permits middle
  housing only as its approved plan allows, and nothing reads the plan.

See Doubts and Questions for Steph.

**Read this first about King City.** Only the four Kingston Terrace
zones (KTTC, KTBB, KTC, KTRC) admit the pod. The six older residential
districts refuse it: their shared housing-type table (16.84.010) has no
triplex or fourplex row. King City is a Large City under the state's
middle housing rule, so that refusal is a question for Steph, not a
settled answer. Two more things decide lots:

- **No Kingston Terrace lot reaches the screen yet.** The city's zoning
  layer 1 paints the older districts; the Kingston Terrace neighbourhoods
  are on layer 4 of the same service, by name. The names are aliased in
  the layer, but a lot only arrives once layer 4 is ingested (Owed
  locally). About 404 King City taxlots and 98 unincorporated ones touch
  a Kingston Terrace polygon.
- **The minimum density is a lot-size ceiling.** Table 16.114-3 asks 22,
  18, 10 and 8 homes a net acre. Four homes at 22 an acre cap a Town
  Center lot near 7,900 sq ft; a larger lot fails the floor. The draft
  reads "each development" as reaching one fourplex on an existing lot,
  the stricter way.

## 1. Cities

| Jurisdiction | State |
|---|---|
| Unincorporated (county CDC) | Draft done, steps 1-10 and 12. 34 documents, 42 zones. Step 8 (footnote rulings) could not be run by the tool; the notes were read by hand, see Documents |
| Hillsboro | Draft done, steps 1-10 and 12. 23 documents, 37 zones, 4 map codes ruled (ANX, CO, SID I-P, SC-BP). Community Development Code, Municode publication 4450 |
| Beaverton | Draft done, steps 1-10 and 12. 17 documents (16 slices of the Development Code and the county's Urban Planning Area Agreement), 28 zones, 2 map codes ruled (WAcnty, ROW). Development Code as the encodeplus export printed it on 2026-09-28, through Ord. 4879 of April 2026. `apps2.beavertonoregon.gov` refused (CONNECT 502); nothing needed was there |
| Tigard | Not started. **Refused:** the code is on eCode360 (`https://ecode360.com/43691505`), which answered 403 (Cloudflare) to curl and WebFetch; the city site answered 403 (Akamai). City GIS unreachable: `maps.tigard-or.gov` and `svr.tigardmaps.com` fail TLS (legacy renegotiation, then an untrusted chain), `gis.tigard-or.gov` CONNECT 502. No workaround was tried. Metro's regional zoning layer (`CITY='Tigard'`) carries the current code names |
| Forest Grove | Not started. **Refused:** the code is only on American Legal (`https://codelibrary.amlegal.com/codes/forestgrove/latest/forestgrovedev_or/0-0-0-4`), which answered 403 to curl and WebFetch; there is no whole-code PDF. City zoning layer reachable (`maps.forestgrove-or.gov/server/rest/services/ForestGrove/Zoning/FeatureServer/16`, field `zoning_code`) |
| Sherwood | Draft done, steps 1-10 and 12. 18 documents (15 slices of the Zoning and Community Development Code, Municode publication 3865, Supplement 24, through Ord. 2026-001; 3 slices of Ordinance 2022-004, for pages the Municode PDF drops), 21 zones, 14 map codes ruled (Old Town, OS, UGA, Unannex and ten county or neighbouring-city codes on unannexed land). City zoning layer `services5.arcgis.com/ikEzR7lqVIlrcVFn/.../Planning/FeatureServer/2`, field `CODE`. Nothing refused |
| Cornelius | Not started. **Refused:** Code Publishing now points to eCode360 (`https://ecode360.com/CO4396`), which answered 403 (Cloudflare); `www.ci.cornelius.or.us` failed TLS. No city zoning layer; Metro's is stale (no R-10). The city's Zoning Map 2025 PDF is reachable. The AGOL "Cornelius Zoning Map" is Cornelius, North Carolina |
| King City | Draft done, steps 1-10 and 12. 12 documents (slices of the Community Development and Zoning Code, Municipal Code Title 16, Municode publication 3913, Supplement 16, August 2026, through Ord. O-2025-02), 14 zones (4 admit the pod, 10 refuse), 12 map codes ruled (6 aliases, 5 county pockets, 1 unencodable). City zoning layer on AGOL (`King_City_Current_and_Future_Zoning_Map_WFL1/FeatureServer/1`, field `ZONECLASS`; Kingston Terrace on layer 4, field `Zoning_Designations`). `www.kingcityoregon.gov` refused (CONNECT 502); `www.ci.king-city.or.us` answered, and nothing needed was only on the first |
| Durham | Not started. Code found: Development Code revised 2025-11-13, a 137-page PDF (`https://durham-oregon.us/wp-content/uploads/2025/11/Development-Code-Revised-11.13.2025.pdf`). No city GIS; Metro has five codes. Middle housing is permitted in SDR with no quadplex rows |

The "not started" rows, and the first facts in the Sherwood and King
City rows, come from a scout run on 2026-09-29 that
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

**Beaverton.** 17 documents, stored under
`flats/provenance/docs/or/washington/beaverton/`. All are `extraction:
plain`.

Sixteen are slices of one PDF, the whole Beaverton Development Code (BDC).
encodeplus generates it on request from
`https://online.encodeplus.com/regs/beaverton-or/export2doc.aspx?pdf=1&tocid=001&file=doc-001-pid-607.pdf`,
and the city's own development-code page links to that address. Every page
footer reads "Date Printed: September 28, 2026". The latest ordinance
cited is 4879, of April 2026.

The seventeenth is the Washington County - City of Beaverton Urban
Planning Area Agreement (UPAA), as amended by county Ordinance 839A in
2018. It comes from the county's Land Use & Transportation site
(`https://www.washingtoncountyor.gov/lut/planning/documents/beaverton-upaa/download?inline`).
It is stored for its §V.B (quoted by BDC 10.40.3.A) and §V.D (the
annexation condition).

Slices held:

- Chapter 10 (general provisions: the zone list at 10.25, the map at 10.30,
  annexation at 10.40);
- the zoning chapters 20.05 (residential), 20.10 (commercial), 20.15
  (employment and industrial), 20.20 (multiple use) and 20.22 (Cooper
  Mountain);
- 20.25 and 20.30 together (density and bulk; the RMB and RMC height
  plane);
- 40.21 (single-detached and middle housing design review) and 40.45
  (land division);
- 60.05 (design review standards, including the 60.05.60 middle housing
  standards), 60.15 (land division standards), 60.30 (parking), 60.50
  (special uses) and 60.55 (transportation);
- Chapter 70 (the Downtown Design District: RC-BC, RC-OT, RC-MU, RC-DT);
- Chapter 90 (definitions).

How the slices are cut:

- The PDF prints a table of contents first, so every heading appears
  twice. Each slice takes `nth: 2`, the body copy. Chapter 90 is printed
  three times (the contents, its own contents page and the body), so it
  takes `nth: 3`.
- Chapter 70 has no following chapter heading in the body (Chapter 80 is
  reserved and not printed). Its slice ends at the running footer of the
  first Chapter 90 page, "Chapter 90, DF-1".
- Chapter 90 ends at "ADDITIONAL ORDINANCES - PART 1". After the last
  definition, the export prints tables of zoning map amendments by
  ordinance number. Read as part of the glossary, they made it "skimmed"
  (see Reader changes).
- `glued_markers: true` on 20.05, 20.10, 20.20, 20.22 and 70. Their tables
  print a footnote marker hard against the figure: "158" is 15 feet with
  note 8, and "2018" is 20 feet with note 18.
- `allow_thin: true` on Chapter 90 and on the UPAA. The fetch check counts
  regulatory verbs, and a glossary or an intergovernmental agreement has
  few. Both were read whole before the flag went on.

Warnings from the fetcher:

- `fetch.py` printed "unknown source — a lead, not evidence. No value
  citing this may be verified." for every document it fetched. The
  `OFFICIAL` set in `flats/provenance/sources.py` lists neither
  `encodeplus.com` nor `washingtoncountyor.gov` (the UPAA's host). The
  export is the city's own code, linked from the city's page, so this is
  a list to extend, not a doubt about the text. Until it is extended, no
  Beaverton value can be promoted to `verified`. That file is off limits
  here; see Owed locally.
- No character came out unmapped (no �).

Not stored:

- Chapter 30 (nonconforming uses);
- the rest of Chapter 40, including 40.10 (adjustment), 40.30 (zero yard
  setbacks), 40.55 (parking determination) and 40.95 (variance);
- the other Chapter 60 sections: 60.07 (drive-through), 60.10
  (floodplain), 60.11 (food cart pods), 60.12 (habitat friendly
  development), 60.20 (manufactured homes), 60.25 (loading), 60.33 (parks),
  60.35 and 60.36 (planned unit development), 60.37 (Resource Overlay),
  60.40 (signs), 60.60 and 60.61 (trees), 60.65 (utility undergrounding),
  60.67 (significant natural resources) and 60.70 (wireless);
- the Comprehensive Plan;
- the Engineering Design Manual, which 60.30.15 note 8(b) (driveways)
  and a 20.05 note (corner sight clearance) send the reader to;
- the Clean Water Services Design and Construction Standards.

None of these sets a base-zone figure the pod is screened on. The
references into them are listed under Ledgers.

Figures the layer cannot read, all drawings:

- Figure 70.15.10.2.3 (where RC-OT's minimum density is 18 instead of 24);
- the Chapter 70 setback figures (70.15.10.1.1 and the like);
- the parking zone map behind the Zone A and Zone B columns of Table
  60.30.10.5.A. Both columns print the same quadplex figures, so the map
  does not move the pod.

**The footnote census.** It found 305 notes in the Beaverton documents,
254 distinct sentences, after four reader changes (see Reader changes;
before them it found 14). Every one is ruled in
`flats/config/footnotes/or/washington/beaverton.yaml`:

- 229 dismissed, with a reason each;
- 21 encoded, and every one confirms against the layer (`applied`);
- 4 unmeasured:
  - 20.05 note 7 and 20.22 note 7, "In no case shall a building encroach
    into a Public Utility Easement", on `utility_easement` (MR, RMA, RMB,
    RMC, CM-MR, CM-RM), ruled as Oregon City's easement notes were;
  - 20.10 note 1, the NS district's 50 percent residential share, on
    `site_specific_limitation` (NS);
  - 20.22 note 25, the setback from Cooper Mountain Nature Park, on
    `site_specific_limitation` (CM-CS, CM-HDR, CM-MR, CM-RM).

`qualified --write-caps` wrote a Beaverton block into
`flats/config/caps.json` from those four.

The file's header lists what the census still misses. None of it
reaches the pod:

- 20.15 use notes 15 to 26: note 14 runs across a page and restarts its
  own list, and the block ends there. They are about uses in OI, OI-NC and
  IND, which have no dwelling row.
- Chapter 70 use notes 14 and 15 of Table 70.15.20.A (emergency shelters;
  exempt from minimum FAR). Note 16, which the ADU row cites, is not
  printed at all.
- The UPAA's "Page II ofl2", a page number read as a marker.

Failed fetches for Beaverton: none. `apps2.beavertonoregon.gov` refused
the scout (CONNECT 502) and was not needed.

### Sherwood

Eighteen documents, stored under
`flats/provenance/docs/or/washington/sherwood/`, all `extraction: plain`,
all retrieved 2026-09-29.

Fifteen are slices of the Sherwood Zoning and Community Development Code
(Municipal Code Title 16), Municode publication 3865
(`https://api.municode.com/PublicationPdfDownload/3865`), Supplement No. 24,
May 2026, "Covering Ordinances through 2026-001, passed February 3, 2026".
The PDF is the whole municipal code (932 pages); Title 16 starts near page
267. Slices held:

- 16.04 (the district list at 16.04.010, the urban growth area at
  16.04.040) and 16.10 (definitions);
- 16.12 (residential: uses 16.12.020, standards 16.12.030) and 16.14
  (residential building design);
- 16.22 (commercial), 16.31 (industrial) and 16.36 (institutional and
  public);
- 16.40 (planned unit development);
- 16.50 (accessory structures), 16.58 (vision clearance) and 16.68
  (infill);
- 16.94 (parking), 16.96 (on-site circulation) and 16.106
  (transportation facilities);
- 16.162 (the Old Town overlay).

**The Municode PDF drops pages.** It leaves out printed pages 296.1-296.2
and 296.18.1-296.18.10. They carry 16.12.030 A and B (the general standards
and the Sufficient Infrastructure rule), the "Minimum lot areas" heading of
the 16.12.030 C table, and all of 16.14.030 A after A.2 (the triplex and
quadplex driveway and access rules). The Municode history notes name
Ordinance 2022-004 as the latest amendment to both sections. So the other
three documents are slices of Ordinance 2022-004, "Amending Code Housing
Choices", Exhibit 1 (the clean text), from the city's own site
(`https://www.sherwoodoregon.gov/wp-content/uploads/2025/03/ordinance-2022-004-amending-code-housing-choices.pdf`):

- `ord.2022-004.16.12.030` (16.12.030 A and B);
- `ord.2022-004.16.12.030-c` (the first page of the C table, with its
  "Minimum lot areas" heading);
- `ord.2022-004.16.14.030` (16.14.030, the additional triplex and quadplex
  design standards).

The ordinance PDF is a scan with an OCR text layer, so the quotes carry OCR
artefacts ("lnfrastructure", "sta¡rs"). The words are the ordinance's. It
is the text as adopted in 2022, not as it stands now; whether anything
later amended those pages is a doubt.

How the slices are cut:

- Each Municode slice runs from a chapter heading the PDF prints once to
  the next chapter's. A plain "Chapter 16.12" is not unique ("Chapter
  16.120" contains it, and the text cites chapters by number), so most
  slices start on the chapter's title line in capitals.
- `allow_thin: true` on four slices, each read whole before the flag went
  on: 16.04 (sixty lines, a list of district names), 16.94 (a two-column
  table that breaks every cell to a word a line), and the two short
  ordinance slices of 16.12.030.

Warnings from the fetcher:

- `api.municode.com` is in `OFFICIAL`. `www.sherwoodoregon.gov` is not:
  `authority_for` returns `unknown` for the ordinance URL, so the values
  quoting the three ordinance slices (the driveway, corner-access and
  alley-access defaults, and every minimum lot area) cannot be promoted
  to `verified` until it is added. `sources.py` is off limits here; see
  Owed locally.

Not stored:

- 16.46 (manufactured home parks), 16.82 (conditional uses), 16.88 (use
  classifications and interpretations), 16.89 (the residential design
  checklist) and 16.90 (site planning). Each is ruled in the layer's
  `crossrefs:` block; none sets a figure the pod is screened on.
- 16.134 (floodplain). Ruled `narrows_only`: it can take ground from a lot,
  not give it.
- The Transportation System Plan, which the street definitions of 16.10
  defer to for street classes, and which sets the right-of-way widths
  16.106 dedicates.
- The Sherwood Comprehensive Plan, named in the definitions.

Figures the layer cannot read:

- the CFEC Parking Delineated Area map at the end of 16.94.020;
- the 16.68.030 side yard plane drawing ("see example below"), whose text
  is read;
- the 16.14.030 driveway figure.

**The footnote census.** It found 7 notes in the Sherwood documents, all
in one block, under the 16.12.030 residential standards table. Every one is
ruled in `flats/config/footnotes/or/washington/sherwood.yaml`:

- 5 dismissed, with a reason each: note 1 (townhome lot averaging), note 2
  (narrower cul-de-sac lots, a relief), note 4 (chimneys and similar over
  the height), note 5 (no front-yard reduction for architectural features
  in MDRL, MDRH and HDR), note 7 (townhome side yards);
- 2 encoded, and both confirm against the layer (`applied`): note 3 ("the
  lesser of feet or stories", so both are held) and note 6 (no adjustment or
  variance to the interior side yard, quoted on it);
- none unmeasured, so Sherwood adds nothing to `caps.json`.

The table prints each note's marker at the head of the row it qualifies
("5 30 20 20 14 14 14" is note 5 and six front yards), so the census reads
the bodies as unmarked. The row each note sits on was read off the table
by eye, and the ruling names it.

The file's header lists what the census still misses. None of it reaches
the pod:

- the notes of the commercial use and dimensional tables (16.22, L448-L469
  and L606-L622). Their markers are glued to the column heads ("OCNC1RC");
- six markers in the industrial use table (16.31, L107-L200), none on a
  dwelling row;
- "D. Detailed design1" in 16.14, a heading's marker;
- two labels of the 16.14.030 driveway figure read as markers.

Failed fetches for Sherwood: none.

### King City

Twelve documents, stored under
`flats/provenance/docs/or/washington/king-city/`, all `extraction: plain`,
all retrieved 2026-09-29. All twelve are slices of the King City
Community Development and Zoning Code (Municipal Code Title 16), Municode
publication 3913 (`https://api.municode.com/PublicationPdfDownload/3913`),
Supplement No. 16, August 2026, through Ordinance O-2025-02. The PDF is the
whole municipal code (742 pages); Title 16 starts near page 270. Slices
held:

- 16.24 (definitions: 16.24.020 the glossary, 16.24.030 the land use
  types, 16.24.040 the solar figures);
- 16.80 (the district list at 16.80.020, annexed areas at 16.80.050, yards
  on short rights-of-way and projections at 16.80.060) and 16.82 (unlisted
  uses);
- 16.84 (R-9, and the housing-type table 16.84.010 that all six older
  residential districts share), and 16.88 to 16.100 in one slice (SF, AT,
  R-12, R-15, R-24);
- 16.102 (NMU), and 16.104 to 16.112 in one slice (LC, CF, ROS);
- 16.114, the Kingston Terrace District Code (Ordinance 2023-04, amended
  through O-2025-02), 3,284 lines: the use table 16.114-2, the density
  table 16.114-3, the dimensional table 16.114-4, the design standards, the
  Habitat Conservation Area standards, streets, parking (16.114.130) and
  procedure (16.114.150);
- 16.132 (the citywide parking chapter, which Kingston Terrace is exempt
  from), 16.136 (circulation and access, which applies there except
  16.136.030, .040 and .050 C.6), 16.144 (vision clearance, which applies)
  and 16.146 (density calculation, which Kingston Terrace replaces).

How the slices are cut:

- Plain chapter numbers are not unique in this PDF: the definitions cite
  "Chapter 16.114" before the chapter prints, and 16.114 cites 16.132. So
  the later slices start and end on a chapter's title line in capitals
  ("KINGSTON TERRACE DISTRICT CODE", "PARKING AND LOADING").
- `allow_thin: true` on four slices, each read whole before the flag went
  on: 16.24 (a glossary, few section numbers), 16.80 (a list of districts
  and two short sections), 16.82 (56 lines) and 16.144 (70 lines).
- `glued_markers: true` on 16.114. Table 16.114-4 glues its note markers to
  the figures: "1,50016" is 1,500 with note 16, "2017" is 20 with note 17.
- `definitions_at: L20-L1117` on 16.24, so the glossary reader takes
  16.24.020 alone. See Tests and Reader changes for why, and for what it
  costs.

Warnings from the fetcher: none. `api.municode.com` is in `OFFICIAL`.
`www.kingcityoregon.gov` refused (CONNECT 502); the city's older domain
`www.ci.king-city.or.us` answered and was used only to confirm the
Municode publication is the current code (its municipal code page links
to it). Nothing stored comes from either city domain.

Not stored:

- the Article IV and V chapters Table 16.114-1 applies in Kingston
  Terrace but that set no figure the pod is screened on: 16.120
  (manufactured homes), 16.124 (landscaping), 16.128 (tree removal), 16.140
  (floodplain, which can only narrow a lot), 16.148 (signs), 16.156
  (conditional uses), 16.160 (nonconforming situations), 16.164
  (variances), 16.168 (temporary uses), 16.172 (home occupations), 16.176
  (accessory structures), 16.178 (accessory dwellings), 16.179
  (communication facilities) and 16.180 (fences). The ones the binding
  ledger stood beside a value (16.156, 16.160, 16.172) are ruled in the
  layer's `crossrefs:` block, with 5.05 (liquor licences) and 8.04.130
  (noise);
- the King City Transportation System Plan, which sets the street classes
  and right-of-way widths 16.80.060 A and 16.114.120 lean on;
- the unlisted-use list 16.82.030 A tells the city manager to keep (not
  published with the code, and not found; Doubts).

Figures the layer cannot read:

- Figure 16.114-1, the Kingston Terrace Plan District map, and the
  16.114.070 Regulating Plan;
- the Habitat Conservation Area maps (16.114.080);
- the street section drawings of Table 16.114-11;
- the solar-access figures at the end of 16.24 (their OCR text is noise,
  which is part of why the glossary is bounded).

**The footnote census.** It found 6 notes in the King City documents, all
in one block: the applicability notes "[1]" to "[6]" of Table 16.114-5,
the Kingston Terrace design standards (L358-L370). Every one is ruled
`dismissed` in `flats/config/footnotes/or/washington/king-city.yaml`,
because each says which elevation a design standard reaches and the layer
holds no design standard. None encoded, none unmeasured, so King City adds
nothing to `caps.json`. Until the file existed, every Kingston Terrace
value quoted above L358 read "6 unread of 6" in `qualified`.

**What the census misses**, read by eye and written in the file's header
so the next reader need not repeat it: the dimensional table's notes 14 to
24 and the use table's notes 1 to 13 print with no period after the number
("16 The minimum lot size ...") and their markers are glued to the
figures, so the census sees neither block. Each is ruled in the header.
The ones that move a value: note 16 (lot size "may be reduced to 1,000"),
read the stricter way, 1,500 held; note 17 (width "may be reduced to 15"),
20 held; note 18 (zero side yard only if attached or six feet from a
neighbour), 3 held; note 19 (Rural Character, 10 feet for two stories),
10 held. Notes 25 to 38 (commercial ground floors, the Upland HCA and the
street sections) do not reach the pod.

Failed fetches for King City: none. The whole Municode PDF fetched first
time.

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

### Beaverton

The zone list is BDC 10.25, which classifies 28 districts, and all 28 are
encoded. The keys are the spellings on the city's own zoning layer
(`gisweb.beavertonoregon.gov/server/rest/services/Public_SharedServices/pubZoning/MapServer/0`,
field `ZONE_NAME`). That layer prints `SC-E` where 10.25 lists "SC-E1 &
3", and both SC-E columns of the use table print N, so one key serves.
Lots reach the layer by the taxlots' `JURIS_CITY` = `BEAVERTON`.

What the pod is here. Chapter 90 defines a Quadplex as "Four dwelling units
total on a single lot in any configuration", or on four child lots of a
middle housing land division, so the pod is a Quadplex everywhere. In MR,
CM-MR and the commercial and multiple-use districts it is also a
Multi-Dwelling ("attached dwellings in any number or configuration"). In
RMA, RMB, RMC and CM-RM a multi-dwelling starts at five units. Every zone
cites its own use table's Triplex and Quadplex row.

Every density is per net acre. Chapter 90 "Acreage, Net" deducts streets,
common driveways, environmentally constrained land (including water
quality facilities and wetlands), public tracts and steep slopes, so each
density carries `measured_on: net_developable_area`.

Layer-wide values (`defaults`):

- no parking minimum (60.30.10.3.A.1, "No minimum parking is required for
  any use");
- a parking maximum of 1.8 a unit (Table 60.30.10.5.A, the one-bedroom
  row of "Duplex, Triplex, Quadplex, or Townhouse in Other Zone"; Zone A
  and Zone B print the same). For four units that is 7.2, rounded to 7
  stalls under note 4;
- stalls 8.5 by 18.5 ft (60.30.10.7);
- aisles 24 ft two-way and 20 ft one-way (60.30.15 note 5). Note 8(c)
  gives middle housing 22 and 20 in RMA, RMB, RMC and CM-RM, which
  override the default there;
- the front lot line of a corner lot is the owner's choice (Chapter 90
  "Lot Line, Front", "as determined by the applicant").

A corner lot is defined (Chapter 90 "Lot, Corner": two streets, or a
curved street whose lines meet at an interior angle "of less than 135
degrees"). It is encoded as `intersecting_frontages` with
`curve_at_or_below_deg: 135`; see Doubts.

**The pod on one lot (22).** `quadplex_allowed: true`, with no variants:

- Residential (20.05): MR, RMA, RMB, RMC.
  - RMA, RMB and RMC need 3,000, 4,000 and 5,000 sq ft and 14, 20 and 20 ft
    of width. Yards are 10 / 5 / 15. Heights are 40, 35 and 35 ft, and
    FAR 1.60, 1.20 and 0.90 on net area.
  - RMB and RMC carry the 20.30 height plane as a step-back: 25 ft at the
    rear setback line (RMC also the front), rising 1:1.
  - MR admits the pod only with its units attached (note 8). It has no
    minimum lot, no height limit (60 ft by a residential lot line) and
    FAR 4.0.
- Cooper Mountain (20.22): CM-RM (4,000 sq ft, 45 ft), CM-MR, CM-HDR and
  CM-CS. The last three admit the pod with its units attached.
- Commercial (20.10): NS, CS, CC, GC, with units attached (note 11).
  **NS** also carries note 1: only half of the contiguous area of any NS
  district may be developed residentially. That is a share of the whole
  district, which nothing measures, so the footnote ruling holds it
  unmeasured and every NS lot is capped at UNKNOWN.
- Multiple Use (20.20): RC-E, TC-MU, TC-HDR, SC-MU, SC-HDR, SC-S. No row
  states a minimum lot, a width or a height.
- Downtown (Chapter 70): RC-BC, RC-OT, RC-MU, RC-DT. 70.05.15.7 exempts
  Downtown development from Chapter 20 except 20.25, and from 60.05 except
  lighting, so only Chapter 70's own tables and 60.30 reach these four.
  The pod has ground-floor units, so the "with ground floor residential
  units" rows are read.

The middle housing standards of 60.05.60 are encoded in RMA, RMB, RMC and
CM-RM:

- S4, open area by lot size;
- S11, parking at most 50 percent of the street frontage;
- S13, 32 ft of driveway approach a frontage, and access from the street
  of lowest classification.

The commercial and multiple-use districts carry the 60.05 design standards
instead:

- parking kept out of the Primary Frontage and 20 ft off the right-of-way;
- vehicle areas on at most 35 percent of the frontage;
- 15 percent open space;
- a 16-ft front maximum where the zone lists none (60.05.15.6.A).

Beside a residential zone, 21 values take a stricter figure behind
`abuts_residential_zone`: 10 side and rear setbacks, and 11 heights
(60 ft by a residential lot line where the zone has no limit, 60.05.15.7,
and 45 ft in CM-CS). Downtown runs the other way round. RC-BC, RC-OT and
RC-MU owe side 10 and rear 20 (RC-OT rear 10) beside "property zoned
residential and/or Downtown Transition (DT)", and no condition says "the
neighbour is zoned RC-DT". So that stricter row is the base value, and
the interior 0 is a variant behind `abuts_nonresidential_zone`, as
Fairview holds its C zones. RC-DT's own table names only residential
and keeps the first shape.

**Minimum density is where most of these zones stop the pod.** Every
admitting zone prints a minimum density, and the draft holds it as a
hard floor (see Doubts). Four units meet it only on a net lot no larger
than:

| Minimum (du per net acre) | Zones | Largest net lot for four units |
|---|---|---|
| 7 | RMC | 24,891 sq ft |
| 10 | RMB, CM-RM | 17,424 sq ft |
| 12 | RC-E | 14,520 sq ft |
| 17 | RMA | 10,249 sq ft |
| 24 | TC-MU, TC-HDR, RC-OT | 7,260 sq ft |
| 30 | SC-MU, SC-HDR, SC-S, RC-DT | 5,808 sq ft |
| 34 | MR, CM-MR, CM-HDR, CM-CS, NS, CS, CC, GC | 5,125 sq ft |
| 43 | RC-MU | 4,052 sq ft |
| 60 | RC-BC | 2,904 sq ft |

In the twelve zones at 30 and above, few lots big enough for the pod and
its parking court will pass.

**Refused (6).** `quadplex_allowed: false` with the use row's cite and no
dimensions:

- OI, OI-NC and IND: the Employment/Industrial use table (20.15) has no
  dwelling row at all.
- SC-E: N in both the SC-E1 and SC-E3 columns of Table 20.20.20.A.
- **OI-WS and C-WS**, the two Washington Square districts. Row 1.C
  (Triplex and Quadplex) prints N. Row 1.F (Multi-Dwelling) prints P with
  a note: note 2 (OI-WS) admits only units on the "second story and
  above" of a non-residential building, and note 3 (C-WS) only "in
  conjunction with mixed-use developments" that are majority commercial
  at the ground. The pod is neither. The Chapter 90 multi-dwelling
  definition also excludes a number of units "prohibited in that zoning
  district", which row 1.C does. Pinned in `test_washington_beaverton.py`.

**Ruled, not encoded (2)**, under `zone_rulings`:

- **WAcnty** (90 features, 646.4 acres) is a `pocket` of
  `or/washington/_unincorporated`, with the zone read off the county's
  own map. It marks annexed land that keeps its county zoning until the
  city rezones it (BDC 10.40.1). Two doubts go with it; see Doubts.
- **ROW** (29 features, 73.2 acres) is `unencodable`: right-of-way, which
  10.35.1 zones as the land beside it to the centreline.

The code's other district-like tokens are ruled in `test_districts.py`
`RULINGS`, all not-a-zone:

- the prefixes and fragments C-, CM-, HDR, MU, RM, SC-, TC- and WS;
- FB-5, FB-10, FBN-10 and FBN-20, landscape buffer types of Table
  60.05.25.13.D;
- THPRD, the Tualatin Hills Park & Recreation District.

### Sherwood

The zone keys are the codes on the city's own zoning layer
(`services5.arcgis.com/ikEzR7lqVIlrcVFn` Planning FeatureServer layer 2,
field `CODE`), spelled as the layer spells them (`LDR_PUD` but
`MDRH-PUD`). The layer prints 35 codes: 21 are encoded as zones and 14 are
ruled. Lots reach the layer by the taxlots' `JURIS_CITY` = `SHERWOOD`.

What the pod is here. 16.10.020 defines a Quadplex as "Four (4) attached
dwelling units, in any configuration, located on a single lot or parcel".
The residential use table (16.12.020 A) prints "Triplex and Quadplex P" in
all five residential districts. The commercial, industrial and IP use tables
have no such row, and each ends "Uses listed in other sections of this
code, but not within this specific table are prohibited".

Layer-wide values (`defaults`):

- a parking minimum of 1 a unit. 16.94.020 Table 1 counts a quadplex's
  stalls by lot area, "4 spaces total" at 7,000 sq ft or more, and every
  residential zone asks at least 7,000 sq ft of a quadplex lot;
- no parking maximum: Table 1 prints "None" for a quadplex in both parking
  zones, held `exempt`;
- a driveway approach of at most 20 ft (16.14.030 A.3, a shared approach);
- access from the street of lowest classification, and from the alley
  where there is one (16.14.030 A.5.a);
- no parking in the front yard (16.14.010 F). The front yard is the whole
  ground between the front lot line and the building (16.10.020 "Yard"), not
  just the setback;
- a corner lot has as many front lot lines as it has street frontages
  (16.10.020 "Lot Line, Front"), held as `front_lot_line_corner: both`.

A corner lot is defined (16.10.020 "Lot, Corner": "at the intersection of
two or more streets, other than an alley"). A street includes "a public or
private road, easement or right-of-way", so a private drive counts
(`drives_count: true`) and an alley does not. No angle test.

**The pod on one lot (10).** `quadplex_allowed: true`, with no variants:

- VLDR, LDR, MDRL, MDRH, HDR, and VLDR_PUD, which the dimensional table
  prints as a column of its own:

  | Zone | Min lot (sq ft) | Width / frontage / depth (ft) | Front / street side / garage / rear (ft) | Height | Max FAR |
  |---|---|---|---|---|---|
  | VLDR | 40,000 | 60 / 25 / 80 | 30 / 20 / 35 / 20 | 30 ft or 2 stories | none |
  | VLDR_PUD | 10,000 | 60 / 25 / 80 | 20 / 20 / 20 / 20 | 30 ft or 2 stories | none |
  | LDR | 7,000 | 60 / 25 / 80 | 20 / 20 / 20 / 20 | 30 ft or 2 stories | 0.50 |
  | MDRL | 7,000 | 50 / 25 / 80 | 14 / 15 / 20 / 20 | 30 ft or 2 stories | 0.55 |
  | MDRH | 7,000 | 50 / 25 / 80 | 14 / 15 / 20 / 20 | 35 ft | 0.60 |
  | HDR | 7,000 | 50 / 25 / 80 | 14 / 15 / 20 / 20 | 40 ft or 3 stories | 0.65 |

- The interior side setback is 5 ft in the table and **loads as 6**. It
  carries 16.68.030 B.1 as a step-back: half a foot further in for every
  foot over 24 ft (`height_ft: 24`, `rise_per_ft: 2`), and the loader
  applies it to the pod's 26 ft (`before_step_back` keeps the 5). Note 6
  forbids adjusting or varying the side yard, and is quoted on it.
- MDRH prints "35 feet or 2.5 stories" and holds the 35 ft only. The stories
  field takes whole numbers, and the pod is two stories (the Hillsboro
  precedent).
- The floor area ratios are 16.68.030 A's, which VLDR is not on. The pod's
  4,000 to 4,032 sq ft of floor needs a lot of about 8,064 sq ft in LDR and
  7,331 sq ft in MDRL. In MDRH and HDR the 7,000 sq ft minimum lot is
  larger than the ratio needs.
- No density figure reaches the pod. 16.12.010 F.1: "Maximum density
  standards shall not be applied to duplex, triplex, quadplex or cottage
  cluster development", and each district's minimum is stated "except
  middle housing types". Both density fields are `exempt` in every zone.

**Only as a PUD's plan allows (5).** VLDR_PUD, LDR_PUD, MDRL_PUD,
MDRH-PUD and HDR_PUD admit the pod, with the permission qualified by
`site_specific_limitation`. 16.40.050 A permits "middle housing dwelling
types" in a Residential PUD "when approved as part of a Final Development
Plan", and 16.40.040 C makes a change of use a major change, heard as a new
application. Nothing measures what a plan approved, so no PUD lot comes back
GREEN. LDR_PUD, MDRL_PUD, MDRH-PUD and HDR_PUD are `like:` their base zone
(16.40.050 C.3: lot size and setbacks "consistent with" the underlying
zone) and carry only the use row. VLDR_PUD has its own column in the table.

**Refused (11).** `quadplex_allowed: false` with the use table's cite and
no dimensions:

- Commercial (16.22): OC, NC, RC, GC. No triplex or quadplex row; the
  Multi-Family row (five or more units) is "only permitted on one or more of
  the upper floors of a building and only when a non-residential use ... is
  located on the ground floor".
- Industrial (16.31): LI, GI, EI. One dwelling for security only.
- IP (16.36): one security dwelling, conditional.
- Non-residential PUDs: OC_PUD, RC_PUD, LI_PUD. 16.40.060 A permits what the
  underlying zone permits outright. C.2 lets the plan waive "type of
  dwelling unit ... and use restrictions", which is the plan's choice, not
  the lot's right. The refusal quotes both.

**Ruled, not encoded (14)**, under `zone_rulings`, all `unencodable`:

- **Old Town** (1 feature, 44.7 acres): the Old Town Overlay (16.162) over
  RC, HDR and MDRL. The map prints no base zone under it, so which of the
  three governs a lot cannot be read.
- **OS** (1 feature, 4.3 acres): open space, not a district of 16.04.010.
- **UGA** (2 features, 14.0 acres) and **Unannex** (34 features, 190.3
  acres): unannexed land inside the growth boundary, with no code.
- Ten codes painted on unannexed land: county AF-5 (11 features, 272.0
  acres), AF-10 (5, 219.2), AF-20 (5, 560.0), EFU (1, 106.1), FD-10 (5,
  6.0), FD-20 (8, 325.1) and R-9 (1, 5.9); Clackamas County's RRFF5 (2,
  31.0); and Tualatin's MG (1, 1,156.0) and MBP (2, 50.2).

None is a `pocket` of the county layer. Beaverton keeps the county's
zoning after annexation (BDC 10.40.1); Sherwood does not. 16.04.040 leaves
unannexed land to the Urban Planning Area Agreement and gives annexed land
an interim city zone. So a lot under one of these codes is either outside
the city (and not this layer's) or waiting for a zone. See Doubts and
Questions.

The code's other district-like tokens are ruled in `test_districts.py`
`RULINGS`: OT (the overlay's own abbreviation), CIVIC (a use-table heading)
and TEA (the Tonquin Employment Area, a plan area named in an industrial
note).

### King City

The zone keys are the district designations of KCMC 16.80.020, as the
code spells them (`R-9`, `KTTC`). Two maps paint the city, both on one
AGOL service (`services8.arcgis.com/NsUn9YuPFCjrkDe3`,
`King_City_Current_and_Future_Zoning_Map_WFL1`):

- layer 1, field `ZONECLASS`, carries the older districts (AT, R12, R9,
  R-24, SF, NMU, LC, CF, ROS) and five county codes marked "(WC)";
- layer 4, field `Zoning_Designations`, carries the Kingston Terrace
  neighbourhoods by name ("Town Center", "Beef Bend Neighborhood",
  "Central Neighborhood", "Rural Character Neighborhood") and one
  "Neighborhood Mixed Use" polygon (11 polygons in all).

Lots reach the layer by the taxlots' `JURIS_CITY` = `KING CITY`.

What the pod is here. 16.24.030 C defines a Fourplex as "a structure that
contains four primary dwelling units on one lot. The units may share
common walls, floors or ceilings". "Dwelling, multi" starts at five units,
and a single-family attached dwelling is "located on its own lot". The
Kingston Terrace use table points its housing rows at these words (note 1,
"As defined by 16.24.030.C").

Layer-wide values (`defaults`). Every one is Kingston Terrace's, because
only Kingston Terrace admits the pod, and Table 16.114-1 exempts Kingston
Terrace from the citywide parking chapter (16.132, "Superseded by Section
16.114.130"):

- no parking minimum: 16.114.130 C.1, "There are no minimum vehicle
  parking requirements in the Kingston Terrace District". Held as 0,
  because the code says none;
- no parking maximum: Table 16.114-13 prints "Duplex, Triplex, Fourplex
  Not Applicable". Held `exempt`;
- no surface parking in front: C.4.c, "Surface parking areas shall occur to
  the side or rear of buildings";
- the 90-degree Standard stall row of Table 16.114-14: 9 ft wide, 16 ft
  deep (including bumper overhang), 16 ft one-way aisle, 20 ft two-way;
- a corner lot has a front lot line on every street: "A 'front lot line'
  is a lot line that abuts a street", with no corner exception. Held as
  `front_lot_line_corner: both`.

A corner lot is defined (16.24.020 "Lot, corner": "located at the
intersection of two or more public street rights-of-way"). A private drive
does not count, nor does an alley; no angle test. `test: intersecting_frontages`,
`drives_count: false`, `alleys_count: false`.

**The pod on one lot (4).** `quadplex_allowed: true`, with no variants and
no qualifier, in the four Kingston Terrace zones. Table 16.114-2 prints
"Duplex, Triplex, Fourplex1 Y Y Y Y", Y meaning allowed outright, and
16.114.150 B.2 says middle housing on an existing lot is "exempt from
development plan review" (a building permit). Table 16.114-4, the
"Residential Use Types" block, column order Town Center, Beef Bend,
Central, Rural Character:

| Zone | Min lot (sq ft) | Width / depth (ft) | Front min / max (ft) | Side / street side / rear / garage (ft) | Height | Coverage | Min density (units a net acre) |
|---|---|---|---|---|---|---|---|
| KTTC | 1,500 | 20 / 45 | 10 / 26 | 3 / 8 / 10 / 18 | none (N/A) | 90% | 22 |
| KTBB | 1,500 | 20 / 45 | 10 / 26 | 3 / 8 / 10 / 18 | 45 ft | 90% | 18 |
| KTC | 2,400 | 20 / 60 | 10 / 26 | 3 / 8 / 10 / 18 | 35 ft | 90% | 10 |
| KTRC | 2,400 | 20 / 60 | 10 / 26 | 10 / 8 / 10 / 18 | 35 ft | 80% | 8 |

- **Lot size and width are the printed figures.** Notes 16 and 17 say the
  lot size and width for these housing types "may be reduced" to 1,000 sq
  ft and 15 ft. Held at the printed figures, the stricter reading. Neither
  can bind a pod whose footprint is 2,000 sq ft and whose narrow side is 25
  ft or more.
- **The front yard is a range**, 10 minimum and 26 maximum ("10/26"), both
  held (`setback_front_max_ft`).
- **The interior side is 3** in three zones ("0 or 3"; note 18 allows zero
  only for a building attached at the line or six feet from its
  neighbour). **Rural Character prints 5 and holds 10:** note 19, "10 feet
  for two-story structures", and the pod is two stories.
- **The street side is 8**, from the "Corner lot setback -- front yard/side
  yard, minimum 8" row, the stricter of the two rows that reach a street
  side yard (the other prints 5). The same row would let a corner lot's
  front come in to 8; that relief is not encoded.
- **Town Center's height is "N/A"**, held `exempt`. Height is measured to
  the highest point (16.24.020), so the pod's 26 ft is its ridge.
- **Coverage is held as building coverage, which is looser than the code.**
  The row is "Maximum coverage of buildings and impervious surfaces", and
  the pod's court, drive and walks count against it too. No field holds an
  impervious share. Every value's cite says "looser than the code". A
  doubt, and a proposed field (Owed locally).
- **The minimum density is a ceiling on lot size.** Four homes at 22 a net
  acre need a lot of at most about 7,900 sq ft in Town Center (Beef Bend
  9,680, Central 17,424, Rural Character 21,780). The screen fails a larger
  lot on the floor. Read the stricter way ("each development" reaching one
  fourplex); a doubt. No maximum is printed, and the neighbourhood-wide
  unit targets (1,870 / 1,260 / 350 / 320) bind no lot.

**Refused (10).** `quadplex_allowed: false` with the use table's cite and
no dimensions:

- the six older residential districts, R-9, R-12, R-15, R-24, SF and AT.
  16.84.010, the housing-type table all six share, prints "R-9 R-12 R-15
  R-24 SF AT" with rows for single dwellings, accessory dwellings, duplexes
  ("Duplex P P P P P P"), manufactured homes and "Multi-dwelling N P P P N
  P" (five or more units). There is no triplex and no fourplex row, and
  each district's own permitted-use list names none. **King City is a
  Large City under OAR 660-046, so whether the state's rule reaches these
  districts is a question for Steph** (Questions). The conservative reading
  is the city's printed table. R-15 is held although the city's map shows
  it only as "R-15 (WC)", because 16.80.020 lists the district and it has a
  chapter;
- NMU: permitted uses name a duplex and multi-family dwellings (five or
  more), no fourplex;
- LC: multi-family dwellings only; CF and ROS: community services, parks
  and open space only.

**Ruled, not encoded (12)**, under `zone_rulings`:

- **Aliases (6):** `R9` and `R12` (layer 1's spellings of R-9 and R-12),
  and the four Kingston Terrace names of layer 4 ("Town Center" to KTTC,
  "Beef Bend Neighborhood" to KTBB, "Central Neighborhood" to KTC, "Rural
  Character Neighborhood" to KTRC).
- **County pockets (5):** "R-6 (WC)", "R-9 (WC)", "R-15 (WC)", "CBD (WC)"
  and "INST (WC)", each a `pocket` of `or/washington/_unincorporated` with
  the county zone named (R-6, R-9, R-15, CBD, INST). 16.80.050 A: the
  zoning that applied before annexation "shall continue to apply and shall
  be enforced by the city until a zone change for the area has been
  adopted by the city council". So a lot under one of these codes is
  screened under the county's rules. This answers, for King City, the county brief's
  unverified item about annexed land keeping county zoning. Map counts
  (layer 1): R-6 (WC) 1 polygon, R-9 (WC) 5, R-15 (WC) 1, CBD (WC) 1,
  INST (WC) 2.
- **Unencodable (1):** "Neighborhood Mixed Use", the one layer-4 polygon
  that is not a Kingston Terrace neighbourhood. Table 16.114-1 leaves only
  16.80, 16.82, 16.84.060 and 16.114 of Article III in force inside
  Kingston Terrace, and 16.114 has no Neighborhood Mixed Use zone, so
  which district governs the polygon cannot be read. The city's NMU
  district (16.102) has the same name, but reading the polygon as NMU would
  apply a chapter Kingston Terrace exempts. Question for Steph.

Layer 1's own polygon counts on 2026-09-29: AT 24, SF 23, R9 25, R12 14,
ROS 6, LC 4, R-24 1, NMU 1, CF 1.

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

### Beaverton

Layer-wide entries in `beaverton.yaml`, each quoted in a comment between
`defaults` and `zones`:

- NOT ENCODED: minimum FAR (Multiple Use row B.1, 0.30 to 0.60; Cooper
  Mountain row I.1, 0.4 in CM-CS and CM-HDR). No field holds a floor on
  FAR.
- NOT ENCODED: the frontage occupancy of 60.05.15.6.A, "At least 60
  percent of the site's Primary Frontage ... shall be occupied by a
  building", and the lower shares after it. No field holds it.
- Held as a hard floor: minimum density, without the 20.25.05.1.A escape
  for a project that shows how the site could later reach the minimum,
  or the three routes D.2 gives RMA, RMB, RMC and CM-RM. See Doubts and
  Questions.
- NOT ENCODED: rounding of the minimum unit count (20.25.05, up at 0.5).
  The screen compares density, not a rounded count.
- NOT ENCODED: the choice 60.05.11.3 gives between the design standards
  (60.05.15 to 60.05.30) and the guidelines (60.05.35 to 60.05.50). The
  guidelines have no numbers; the standards, the stricter track, are
  encoded.
- NOT ENCODED: garage setbacks. The pod has no garage.
- NOT ENCODED: the 60.05.60 middle housing design rules beyond the
  figures encoded (entries, windows, articulation).
- NOT ENCODED: unit lots. A quadplex split by a middle housing land
  division keeps the parent lot's standards (20.05 and 20.22), so the pod
  is screened as a quadplex on one lot. The townhouse lot rows are a
  different path.
- NOT ENCODED: the 10.32 overlays, Historic (HO), Resource (RO) and
  Cooper Mountain Parks (CMPO). They are not in `ZONE_NAME`, so they are
  overlay data.
- Clean Water Services: the net acre deducts water quality facilities,
  wetlands and natural resource areas. The vegetated corridors behind
  them are in Clean Water Services' standards, not the BDC. Overlay work.
- Declared, not encoded: UPAA §V.D, as `qualified_by:
  site_specific_limitation` on every admitting zone's setbacks, minimum
  lot and height. Beaverton prints no lot coverage standard, so the
  coverage clause has nothing to qualify.

In the zones:

- the FAR bonuses: 6.0 near Frequent Transit Service in MR, the
  commercial zones and the multiple-use zones (20.05.16, 20.10.16,
  20.20.16), and 20 percent more on heavily constrained sites (note 24,
  20.25.10.3). The base 4.0 is held;
- 60.05.60 S4.b (the outdoor area as a 12-ft square reachable from every
  unit, and not in a front setback) and S11.a (cul-de-sac frontage
  measured 20 ft back), in RMA, RMB, RMC and CM-RM;
- the share of frontage a building must occupy (60.05.15.6.A), in every
  commercial and multiple-use zone; only its 16-ft front maximum is held;
- the 25-ft setback from Cooper Mountain Nature Park (Table 20.22.15 G.6
  and note 25). It is ruled unmeasured, which caps CM-CS, CM-HDR, CM-MR
  and CM-RM;
- the NS district's 50 percent residential share (20.10 note 1), ruled
  unmeasured, which caps NS;
- the lower density rows that turn on distance: SC's 24 beyond 400 ft of
  a light-rail platform, and RC-OT's 18 where Figure 70.15.10.2.3 says so;
- in Chapter 70:
  - S5.c, surface parking 5 ft from all property lines, on side and rear
    lines;
  - the street-facing side maximums;
  - the reduced minimums for small sites of before 1999 (70.15.10.5).

Step 10, the prohibition grep for "quadplex", "plex" and "middle housing"
over all 17 documents. The hits are:

- the use tables (20.05, 20.10, 20.20, Chapter 70);
- the definitions;
- the parking tables and yard rules of 60.30;
- the middle housing standards of 20.22 and 60.05;
- the procedures of 40.21 and 40.45.

None prohibits the pod in a zone this layer admits it in. The only N is
the use-table cell each refusing zone cites. The OI-WS and C-WS
Multi-Dwelling rows admit dwellings only above or within a commercial use
(see Zones).

"The code states nothing":

- No lot coverage standard in any district.
- No side setback row for a quadplex on one lot in 20.05. The rows are
  written for townhouses and for land divisions, and the perimeter figure
  (5 ft) is held.
- No minimum lot area in 18 zones: MR, CM-MR, CM-HDR, CM-CS, the four
  commercial, the six multiple-use and the four downtown districts
  (downtown through 70.05.15.7, which takes Chapter 20 away). These are
  held `exempt`. Some still print a width (MR and CM-MR 14 ft, NS 70 by
  100).
- No height limit in MR, CS, CC, GC, RC-E, TC-MU, TC-HDR, SC-MU, SC-HDR
  and SC-S. They are held `exempt`, with the 60-ft figure by a residential
  lot line as the variant.
- No parking maximum ("N/A") for a quadplex in RMA, RMB, RMC and CM-RM.
  These are held `exempt`.

### Sherwood

Layer-wide NOT ENCODED entries in `sherwood.yaml`, each quoted in a comment
beside `definitions` or `defaults`, or between `defaults` and `zones`:

- **The alley as a front lot line.** A corner lot has as many front lines as
  street frontages, and a street includes an alley, so by the words an alley
  line is a front line too. The envelope reads an alley line as a rear or
  side line, as in Hillsboro. A doubt.
- **The CFEC parking relief** (16.94.020 A). No parking is required within
  half a mile of a frequent transit corridor, or in the Sherwood Town Center
  and a quarter mile around it (a map). No condition carries either
  distance, so the stricter Table 1 minimum is held everywhere.
- **Driveways at most 50 percent of the street frontage** (16.14.030 A.2).
  No field holds a driveway share of frontage. `parking_area_max_frontage_pct`
  counts garages, parking and manoeuvring together, which is a different
  measure. Two 20 ft approaches on the 25 ft minimum frontage are over it,
  and one shared 20 ft approach needs 40 ft of frontage.
- **Driveway spacing** (16.14.030 A.4) and the collector and arterial
  access standards (A.5.b). Both turn on the street's class and the
  neighbours' driveways.
- **Sufficient Infrastructure** (16.12.030 B.3). A middle housing building
  permit needs the City Engineer's verification of sewer, water, emergency
  access and storm drainage. As in the county layer, the applicant may
  provide it; it is not a use gate. A doubt for lots far from a main.
- **Garages at most 60 percent of the street-facing elevation** (16.14.010
  B.2). A share of the building's own face, and the pod parks in a rear
  court. The rest of Table 16.14-1 (windows, entrances, detail) is design.
- **The cul-de-sac lot width note** (note 2). It states no figure, and the
  table's width is held on every lot.
- **The clear vision area** (16.58.010, 20 ft along each street from a
  corner). The smallest pair of street yards (14 and 15 ft) puts the
  building's corner outside the triangle, so it never reaches the pod.
  The 25 ft between a corner curb and a driveway places the curb cut, which
  nothing draws.
- **The infill relaxations** (16.68.020 and 16.68.050: lot area and
  dimensions to 85 percent, the front yard by up to 6 ft). Each is the
  Approval Authority's finding on a land division, not a right.
- **16.68.030 B.2 and C**: side elevations over 750 sq ft broken into
  planes, and garage orientation on lots 60 ft wide or less. Design.
- **Right-of-way dedication and street improvements** (16.106). They push
  the building back by a width the Transportation System Plan sets, which
  nothing measures. A doubt, as in the county layer.
- **Projections into yards** (16.50). Nothing here reads a projection
  allowance, and note 5 refuses front-yard reductions for architectural
  features in MDRL, MDRH and HDR.

Held, the strict reading: 16.68.030 A and B.1 on every lot, not only on
infill lots (Zones, Doubts, Questions).

Step 10, the prohibition grep for "quadplex", "fourplex", "plex" and
"middle housing" over all 18 documents. The hits are:

- the residential use table and dimensional table (16.12);
- the definitions (16.10);
- the residential design standards (16.14 and the 16.14.030 ordinance
  slice);
- the parking table (16.94) and on-site circulation (16.96);
- one line each in 16.40 (the Residential PUD's permitted uses), 16.106
  (street improvements) and the ordinance's 16.12.030 (Sufficient
  Infrastructure);
- three "complex" in 16.162, which are not the word.

None prohibits the pod in a zone this layer admits it in. The commercial,
industrial and IP chapters never name it; their refusal is the closing
"not within this specific table are prohibited".

"The code states nothing":

- No lot coverage standard in any residential district.
- No density figure for a quadplex (16.12.010 F). Both density fields are
  held `exempt`.
- No parking maximum for a quadplex ("None"). Held `exempt`.
- No floor area ratio in VLDR or VLDR_PUD (16.68.030 A lists LDR to HDR).

### King City

Layer-wide NOT ENCODED entries in `king-city.yaml`, each quoted in a
comment beside `defaults` or between `defaults` and `zones`:

- **No backing into the street** (16.114.130 C.4.e). A rear court served
  by a drive does not back into the street; nothing measures a design that
  would.
- **Compact stalls** (C.9.b, up to half the stalls at 8.0 by 15.0). The
  standard stall is held, the stricter reading, as in the other layers.
- **The curb length** of Table 16.114-14's 90-degree row (8.5 ft under a
  9.0 ft stall). It cannot be a side of the same rectangle; the width is
  held (Doubts).
- **Vehicle access** (Table 16.114-12). It prints rows for "Dwelling,
  single detached or attached" (one 10 ft driveway) and "Dwellings, multi"
  (30 ft of access, 15 or 20 ft paved, curbs and a walkway), and none for
  a duplex, triplex or fourplex. Neither row names the pod (Doubts).
- **Vision clearance** (16.144.030 A.2): 20 ft on each side of every
  intersection in Kingston Terrace, measured from the curb line or
  pavement edge, clear between 3 and 8 ft. Only driveways serving two homes
  or fewer are excepted, and the pod's serves four. Where the triangle
  lands on the lot depends on the planting strip and sidewalk, which
  nothing holds (Doubts).
- **Yards on a short right-of-way** (16.80.060 A). The yard grows by the
  right-of-way still owed: 33 ft from the centreline on Beef Bend Road,
  131st Avenue and Fischer Road, 25 ft on other city streets. Nothing
  measures the existing width. The same kind of rule as in the county and
  Sherwood layers.
- **Projections into yards** (16.80.060 B). An allowance; nothing reads
  one.
- **The unlisted-use list** (16.82.030 A). The city manager keeps a list
  of unlisted uses the planning commission has approved, with the force of
  a use-table amendment. It is not published with the code and was not
  found (Doubts).
- **Rows of Table 16.114-4 the pod does not use:** the porch row ("5/15",
  "6/15"; the catalog pod has no porch), the alley rows (3 ft to a
  building, "0-6" or more than 18 ft to a garage entry; the envelope reads
  an alley line as a rear or side line and holds the 10), the corner lot's
  front relief to 8 ft, and note 14 (the Oregon Building Code's own
  separations).
- **The neighbourhood-wide unit targets** of Table 16.114-3 (1,870 /
  1,260 / 350 / 320). They bind no lot.
- **The design standards** (16.114.060, Table 16.114-5): articulation,
  eyes on the street, a main entrance facing the street within 8 ft of the
  longest street-facing wall, detailed design, transitional space. Design,
  not placement.
- **The Habitat Conservation Area standards** (16.114.080 to .090). A
  mapped overlay nothing measures; its own relief (lot size down 1,000 sq
  ft, yards by half, height up 10 ft) is looser and not encoded either.
- **Streets and dedication** (16.114.120). They take ground from a lot by
  a width nothing measures.

Held, the strict readings: the printed lot size and width under notes 16
and 17's "may be reduced"; the minimum density on one fourplex; coverage
held as building coverage, which is the one place the layer is looser
than the code (Doubts).

Step 10, the prohibition grep for "quadplex", "fourplex", "plex" and
"middle housing" over all 12 documents. The hits are:

- 16.114: the use table row (L150), notes 16 and 17 (L291-L294),
  the design standards' applicability (L386, L434), the common open space
  exemption (L620), the parking maximum (L2568) and bicycle parking
  (L2753), and 16.114.150 B.1 and B.2 (L3014-L3016, middle housing exempt
  from development plan review);
- 16.132: the citywide parking maximum, "Middle Housing" and
  "Triplex/Quadplex Not applicable" (L221-L222);
- 16.146: "Density maximums may not apply to duplexes, quadplexes,
  triplexes, or cottage clusters" (L30-L31);
- 16.24: the Duplex, Fourplex and Triplex definitions;
- the rest are "Duplex" lines, which the "plex" pattern also catches: the
  duplex rows of 16.84, 16.88-16.100 and 16.102, duplex access in 16.136
  (16.136.030, exempt in Kingston Terrace) and a 16.132 bicycle row.

None prohibits the pod in a zone this layer admits it in. None admits it
in a zone the layer refuses: 16.132 and 16.146 name quadplexes, but only
to relieve a parking maximum and a density maximum, and no use table
outside Kingston Terrace lists one (Questions).

"The code states nothing":

- No parking minimum in Kingston Terrace (stated, held 0) and no parking
  maximum for a fourplex ("Not Applicable", held `exempt`).
- No maximum density in Kingston Terrace.
- No maximum height in Town Center ("N/A", held `exempt`).

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

### Beaverton

Each doubt is written the conservative way, with a comment at its line in
`beaverton.yaml` or its ruling in the footnote file.

The ones that decide the most lots:

- **UPAA §V.D, declared on every admitting zone.** When a partly built
  development approved by the county is annexed, the city "may, at its
  discretion, continue to apply the COUNTY's development standards relating
  to setbacks, lot sizes, lot coverage and heights". Nothing measures which
  lots those are. The brief says to declare it, so every admitting zone's
  setbacks, minimum lot and height carry `qualified_by:
  site_specific_limitation`, citing §V.D. The effect is that no Beaverton
  lot screens GREEN; one the pod otherwise fits reads UNKNOWN. A list of
  those developments, from the city or the county, would lift it.
- **Minimum density as a hard floor.** 20.25.05.1.A lets a project below
  minimum density proceed if it shows "how, in all aspects, future
  intensification of the site to the minimum density or greater can be
  achieved". D.2 gives RMA, RMB, RMC and CM-RM three routes, one of them a
  plan for future partitioning. No field holds a "may fall short if it
  shows" path, so every minimum is a floor. With minimums of 30 to 60 an
  acre in twelve zones, this fails the pod on most lots there (see the
  table under Zones). Rounding (up at 0.5) is not encoded either; on
  small lots it can lower the floor.
- **NS 50 percent.** Note 1 caps residential development at half the
  contiguous area of each NS district. `site_specific_limitation` is the
  nearest registered fact, though the share belongs to the district, not
  the parcel. The ruling is unmeasured, so NS lots cap at UNKNOWN.
- **Public utility easements.** 20.05 note 7 and 20.22 note 7: "In no case
  shall a building encroach into a Public Utility Easement". Ruled as
  Oregon City's were, on `utility_easement`, which caps MR, RMA, RMB, RMC,
  CM-MR and CM-RM. Without an easement layer those zones cannot reach
  GREEN either, which the UPAA already does to every zone.
- **The parking maximum, 1.8 a unit.** The "Other Zone" row rises with
  bedrooms (1.8 for one, 2.0 for two or more), and the pod's bedroom count
  is not a site fact. The lowest row is held: 7.2, rounded to 7 stalls
  (note 4). A design that draws 8 stalls would be over the cap if its
  units have one bedroom and within it if they have two.

Rows that turn on something the screen does not measure. In each case the
stricter figure is held everywhere:

- **SC-MU, SC-HDR, SC-S minimum density:** 30 within 400 ft of a
  light-rail platform, 24 beyond (note 2). 30 is held.
- **RC-OT minimum density:** "18 or 24" by Figure 70.15.10.2.3, a map.
  24 is held.
- **The commercial front maximum (20.10 note 2).** The 16-ft maximum is
  limited to parcels over 60,000 sq ft "pursuant to Section 60.05.15.6",
  but 60.05.15.6.A states no such threshold. It is held on every lot.
- **The 60-ft height by a residential lot line** (60.05.15.7.A) applies
  "within 30 feet"; it is held behind `abuts_residential_zone`, which is
  about the neighbour, not the distance.
- **Downtown beside RC-DT.** The RC-BC, RC-OT and RC-MU setback tables
  add a side and rear setback on "property zoned residential and/or
  Downtown Transition (DT)". No condition says "the neighbour is zoned
  RC-DT", so the stricter row is held as the base on every lot in those
  three zones, and the interior 0 sits behind `abuts_nonresidential_zone`.
  Beaverton declares no neighbour lists yet, so every such lot screens at
  the stricter row until one is declared, and that list must leave both
  the residential zones and RC-DT off the condition. RC-MU's row reads
  "residential and Downtown Transition" without the "or"; it is read as
  RC-BC's "and/or", the stricter reading. (An earlier draft of this layer
  had it the other way round, the 0 as the base, and was corrected before
  commit.)
- **RC-DT maximum density on net acres.** 20.25.05 speaks only of the
  minimum; the maximum is read on net like the minimum beside it, the
  stricter reading.

Readings of the text:

- **The side setback row (20.05).** F.2 is written for townhouses and for
  land divisions; a quadplex on one lot has no row. The perimeter figure
  (5 ft) is held.
- **Corner lot "less than 135 degrees".** The field takes the figure as
  at-or-below, so a curve of exactly 135 degrees counts as a corner here
  and not in the code. A one-degree gap.
- **Corner sight clearance.** A 20.05 note says corner lots "may need" a
  greater width for the Engineering Design Manual's sight clearance
  areas. The manual was not fetched and no figure is stated, so the note
  is dismissed. On a small corner lot the sight triangle may reach into
  the pod's footprint.
- **Driveways (60.30.15 note 8(b))** go to the Engineering Design Manual.
  Not read.
- **Standards or guidelines (60.05.11.3).** An applicant may take the
  guidelines track instead of the standards. The standards are encoded;
  a guidelines application could pass where the screen fails it.
- **Minimum FAR** is not held, so a small pod on a large Multiple Use or
  Cooper Mountain lot passes the screen and may fail the code.
- **C-WS beside a commercial building.** If the pod were part of a larger
  development that is majority commercial at the ground, note 3 might
  admit it as a multi-dwelling. The pod on its own lot is not that, so C-WS
  refuses.
- **20.05.16.1.b** refers to "20.10.16.1.a", which looks like a misprint
  for 20.05.16.1.a. MR's FAR of 4.0 is the same either way.
- **The 20.20 WCF marker.** The tower-height row of the Multiple Use
  wireless table carries the marker of the OI-WS yard note before it,
  apparently misnumbered for note 6 ("Inclusive of antenna"). A wireless
  tower is not the pod; dismissed.

Annexed county land (WAcnty):

- **Supersession.** BDC 10.40.1 keeps the county's zoning on annexed land
  "except that the provisions of Chapters 30 through 80 of this Code shall
  supersede comparable provisions". So the city's parking (60.30) and
  design review (60.05) replace the county's on these lots. The pocket
  screens them under the unincorporated layer, county figures and all.
  Which of those give way is not ruled.
- **Map coverage.** Whether the county's zoning map still shows a district
  on a lot after annexation was not checked. If it does not, the pocket
  resolves to nothing.

Ledgers and readers:

- **Attribution.** `python -m flats.encode.attribution --layer
  or/washington/beaverton` reports that 80 of 341 values cite a section
  their text is not in. A throwaway script (not committed) checked every
  one. It looked for the nearest encodeplus section heading above each
  quoted span (the shape "60.05.15. Building Design and Orientation
  Standards.") and compared it with the sections the cite names. All 80
  sit under a cited section, so the reader's idea of which section a line
  is in does not fit this layout. Why was not traced. The blind re-read
  should look again.
- **The census's misses** (Documents): 20.15 notes 15 to 26, Chapter 70
  notes 14 to 16, and the UPAA's page number. None reaches the pod.
- **A false close in the routing ledger.** `test_routing.py` `FOLLOWED`
  pins `70.15.10 -> 70.15.10.5` as followed. It is not: a wrapped "See
  Section / 70.15.10.5 ..." in RC-OT's Table 70.15.10.2.A note 2 is read
  as a heading, because a number from the chapter's own series skips the
  wrapped-line guard. 70.15.10.5 (small sites of before 1999) was not
  read. Pinned so it is seen; the reader fix is under Owed locally.

### Sherwood

Reading the code:

- **How far 16.68.030 reaches.** The chapter is "Infill Development
  Standards" and the section "Building Design on Infill Lots". 16.68.020
  A.5 names it for lots created below the zone's minimum area in a
  land division of under five acres, which reads narrower. But the
  section's own first sentence is "Structures exceeding twenty four (24)
  feet in height shall conform to the following standards", and the
  residential table sends MDRH and HDR multi-family side yards over 24 ft to
  "§ 16.68 Infill" with no infill test. The layer takes the wide reading:
  the floor area ratio in LDR, MDRL, MDRH and HDR, and the side yard plane
  in every residential zone. If the narrow reading is right, the ratio
  goes, and the side setback is 5 ft, not 6. The ratio is the one that
  decides lots: in LDR it needs about 8,064 sq ft where the zone asks
  7,000, and in MDRL about 7,331. Question for Steph.
- **The ordinance text may not be current.** 16.12.030 A and B, the
  "Minimum lot areas" heading, and 16.14.030 A.3 onward are read from
  Ordinance 2022-004 as adopted. The Municode history notes name 2022-004 as
  the latest amendment to 16.12.030 and 16.14.010. 16.14.030's own history
  note is on a dropped page, so a later amendment to it cannot be ruled out
  from what was fetched.
- **The district list in 16.04.010 is stale.** It was printed in Supplement
  6 (April 2007). It still lists Office Retail (OR), which the 2012
  consolidation of 16.22 removed (the commercial table has OC, NC, RC and
  GC columns only), and it omits EI, which 16.31 and the map both carry.
  The zone list was taken from the map and the chapters instead.
- **Reading the dimensional table.** In the setback rows a leading digit is
  a note marker, not a column: "5 30 20 20 14 14 14" is note 5 and six front
  yards, in the column order "VLDR VLDR-PUD LDR MDRL MDRH HDR" that the
  Municode reprint's header prints. The Municode PDF drops the table's first
  page, so its lot-area rows print without their heading. The heading and
  the rows were matched against the ordinance's copy.
- **MDRH's "35 feet or 2.5 stories".** Only the 35 ft is held. The pod's two
  stories are under 2.5 either way, so this moves no lot.
- **The alley as a front lot line** (Refusals). If an alley line is a front
  line, an alley-backed lot owes a front yard at the back as well, and the
  screen passes lots the code might not.
- **Driveways at most 50 percent of frontage** is not held, so a lot on a
  frontage under 40 ft can pass the screen and fail the code.
- **CFEC.** The stricter parking minimum is held everywhere. Lots near a
  frequent transit corridor or in the Town Center may owe no parking at all,
  so the screen can fail a lot the code passes. Never the reverse.
- **Sufficient Infrastructure** (16.12.030 B.3) is not a use gate here. A
  lot far from a sewer or water main may not get a permit.
- **Similar-use interpretations.** 16.22.020 C, 16.31.020 C and 16.36.020 C
  let the city admit an unlisted use "consistent or associated with" the
  listed ones through Chapter 16.88. That is a discretionary finding, not a
  right, and the refusals stand.

PUDs:

- **Final Development Plans.** Every residential PUD admits the pod only as
  its plan allows, so no PUD lot comes back GREEN. A plan may name the
  housing types it allows. Nobody has read one.
- **16.40.050 C.3** lets interior PUD lots use the development's average lot
  size, and C.1 lets density pool across a PUD that spans zones. Neither is
  encoded; the PUD blocks take the base zone's figures.
- **16.40.060 C.2** lets a non-residential PUD's plan waive "type of
  dwelling unit ... and use restrictions". The three non-residential PUDs
  refuse. A plan that did waive them would be the plan's, not the lot's.

The map's other codes:

- **Unannexed land and `JURIS_CITY`.** The 14 ruled codes include 11 painted
  on land the city's map calls unannexed (Unannex, and ten county and
  neighbouring-city codes). If those taxlots' `JURIS_CITY` is not
  `SHERWOOD`, this layer never sees them and the rulings are never reached;
  the county layer screens them. If it is `SHERWOOD`, they stay open. Not
  checked against the taxlots; that is county-map work.
- **MG, 1,156 acres,** is the largest feature on the map. It reads as
  Tualatin's General Manufacturing code, which suggests land the
  neighbouring city plans for. It is not Sherwood's code.
- **Old Town** (44.7 acres) covers downtown HDR and MDRL lots the pod might
  fit. The map prints no base zone under the overlay, so they stay open
  until the base zone is mapped. 16.162's own use and height exceptions are
  not encoded.

Ledgers and readers:

- **Exemptions stated on the wrong sentence.** The exemptions ledger reads
  four of the twelve density exemptions as `stated`, but on a neighbouring
  sentence ("Minor land partitions shall be exempt from the minimum density
  requirement"), not on the clause that does the work. The other eight read
  `numeric`. A reviewer signing a density exemption should read 16.12.010 F
  and the zone's purpose clause, not the ledger's line.
- **Attribution.** `attribution --layer or/washington/sherwood` reports that
  44 of 109 values cite a section their text is not in. All 44 were checked
  by hand, and none is a wrong cite:
  - 29 cite 16.12.030 and are read as 16.12.010. The reader goes by the
    page's running header, and the one printed above the table
    (`sdc.16.12.residential.txt` L130) reads "16.12.010". The 16.12.030
    heading itself is on a page the Municode PDF drops (296.1);
  - 12 are read as 16.12.030 and 16.68, because the setback rows print "§
    16.68 Infill" in their cells;
  - 2 parking values quote across the 16.94.010 and 16.94.020 boundary;
  - 1, `parking_front_prohibited`, is read as "296.11", a page number the
    reader takes for a section.
- **Fractions printed as digits.** The PDF prints "one-half (1/2)" with the
  "1/2)" on the next line, and "two and one-half (21/2) feet" in 16.58.010.
  The `missed` ledger reads the second as a 2 ft height. Neither is a
  figure the layer holds.

### King City

Reading the code:

- **The older districts refuse on a table with no fourplex row.** 16.84.010
  lists housing types for all six older residential districts and stops at
  duplexes and "Multi-dwelling" (five or more). King City is inside Metro
  and over a thousand people, a Large City under OAR 660-046, and every
  one of the six permits a detached house. The code names quadplexes twice
  outside Kingston Terrace (16.146.030 A relieves their density maximum,
  16.132.040 their parking maximum) and never admits one in a use table.
  Whether the state rule applies directly where the city's own table is
  silent is a legal question. The draft refuses (the city's printed table)
  and asks Steph. If the answer is that the state rule governs, the six
  districts need dimensions read from 16.84.040 and the district chapters,
  and the older parking chapter (16.132) read for them.
- **Coverage is looser than the code.** Table 16.114-4 caps "buildings and
  impervious surfaces" together (90, 90, 90 and 80 percent), and 16.24.020
  counts "buildings, driveways, sidewalks and parking areas". The layer
  holds the figure as `max_coverage_pct`, which the screen compares with
  the building footprint alone. The pod's rear court, drive and walks
  count against the same cap, so the screen will pass lots the code may
  not. It is the one place the layer errs toward GREEN. Each value's cite
  says so, and Owed locally proposes an impervious-share field.
- **The minimum density on one fourplex.** Table 16.114-3 prints "Minimum
  net density assigned to each development". 16.114.150 B.2 sends middle
  housing on an existing lot straight to a building permit, with no
  development plan review, so "each development" may mean a plan-reviewed
  development, not one fourplex. The draft applies the floor to every lot,
  the stricter reading. Under it a Town Center lot over about 7,900 sq ft
  fails (four homes at 22 a net acre), and the others at 9,680, 17,424 and
  21,780 sq ft. Net acres exclude streets, parks, storm facilities and
  natural resources, so a lot with a mapped resource has a smaller net
  area and a looser ceiling than the screen computes.
- **Notes 16 and 17.** The lot size and width "may be reduced" to 1,000 sq
  ft and 15 ft for these housing types. Held at 1,500 and 20. Neither
  figure can bind the pod, so this moves no lot.
- **The curb length.** Table 16.114-14's 90-degree Standard row prints
  "9.0 ft. 8.5 ft." for stall width and curb length. At 90 degrees the two
  should be equal. The 9 is held as the width; if the 8.5 is the true
  width and the 9 a misprint, the layer is 0.5 ft strict per stall.
- **Vehicle access.** Table 16.114-12 has a row for single dwellings (one
  10 ft driveway) and one for multi-dwellings (30 ft of access, 20 ft paved
  two-way, curbs, a walkway), and none for a fourplex. If the city applies
  the multi-dwelling row to a fourplex's four-home drive, the access width
  is 30 ft, which the screen does not hold.
- **Vision clearance at the pod's own driveway.** 16.144.030 excepts only
  driveways serving two homes or fewer, so the pod's drive gets a 20 ft
  triangle each side, measured from the curb. Where the lot line is within
  10 ft of the curb the triangle reaches the building face. At a street
  corner, the 10 ft front and 8 ft street side put the building's corner
  18 ft along each line, inside a 20 ft triangle drawn at the lot lines.
  Not encoded; the curb position is unknown.
- **The unlisted-use list.** 16.82.030 A gives the city manager's list of
  approved unlisted uses the force of a use-table amendment. It was not
  found. If it names a fourplex in an older district, that refusal is
  wrong. A new request could not add one: 16.82.040 A requires a use "not
  specifically listed in another zone", and Kingston Terrace lists it.
- **The street side yard.** Two rows reach it: "Corner lot setback -- front
  yard/side yard, minimum 8" and "Side yard -- to public street, minimum
  5". The 8 is held. If the city reads the 5 as the street side and the 8
  as a corner front, the layer is 3 ft strict on a corner.

Slips in the source, recorded so a reader does not stop on them:

- 16.96.020 (R-15) and 16.100.020 (R-24) both open "Permitted uses in the
  AT zone are", under their own chapter headings. Read as their own
  districts.
- 16.132.050's stall table lost its foot and inch marks in the Municode
  PDF (ten replacement characters, `kcc.16.132.parking.txt` L268-L277).
  Kingston Terrace is exempt from 16.132, so no value reads it; it matters
  only if an older district is opened to the pod.
- 16.102.060 A.3.a (NMU) reads "A maximum depth between the clear zone and
  building façade of 20 width of feet;". The 20 is there and the words
  around it are out of order; plain extraction of the PDF page agrees.
  Pinned in `test_orphaned.py` (Tests). NMU refuses the pod.

The map:

- **Kingston Terrace is on a second map layer.** Layer 1 of the city's
  service paints the older districts; the four neighbourhoods are only on
  layer 4, by name. Until layer 4 is ingested no lot reaches a zone that
  admits the pod. About 404 King City taxlots and 98 unincorporated ones
  touch a Kingston Terrace polygon (a spatial count on 2026-09-29, not a
  screen run). Some of the 98 may be land Kingston Terrace plans for but
  the city has not annexed; the county layer screens those.
- **"Neighborhood Mixed Use" on layer 4.** One small polygon carries a name
  that is not a Kingston Terrace neighbourhood. Left `unencodable`
  (Zones), and asked.
- **The county pockets.** "(WC)" codes are sent to the county layer under
  16.80.050 A. The county blocks they name (R-6, R-9, R-15, CBD, INST) are
  the county's current districts; whether the county zoning a parcel had
  at annexation is the county's zoning today was not checked.
- **Habitat Conservation Areas** (16.114.080). A mapped overlay inside
  Kingston Terrace that limits disturbance. Not encoded, and no screen
  layer has it.

Ledgers and readers:

- **The glossary is bounded, and four use words read "silent".**
  `definitions_at: L20-L1117` makes the glossary reader take 16.24.020
  alone. Read whole, the chapter showed 15 of 199 entries out of order,
  because 16.24.030 sorts use types by category, not by letter, and the
  chapter ends in OCR noise from the solar figures; it read as skimmed and
  failed `test_glossary`. Bounded, it reads 154 entries, 1 out of order,
  whole. The cost: the words ledger now reads multifamily, quadplex,
  duplex and triplex as `silent`, where unbounded they were `defined` at
  16.24.030 (L1204, L1268, L1229, L1348). The code defines them; the span
  cannot say so, because `definitions_at` holds one range. Proposal under
  Owed locally.
- **Attribution.** 1 of 70 values cites a section its text is not in:
  `parking_front_prohibited`, cited 16.114.130 and read as 16.114.120.
  Checked by hand: 16.114.130's heading prints at L2523 and no other
  section heading falls between it and the quoted L2612. The cite is
  right.
- **The exemptions** are both `stated` on their own sentence: Table
  16.114-13's "Not Applicable" parking maximum, and Town Center's "N/A"
  height.

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

### Beaverton

- **Developments the county had partly approved.** Beaverton's agreement
  with the county says that when the city annexes a development the county
  had already approved and part-built, the city may keep applying the
  county's setbacks, lot sizes and heights to it. Nothing in the data says
  which lots those are. So the draft never passes a Beaverton lot outright:
  a lot the building fits comes back as "needs a closer look", never as a
  plain yes. Does the city or county keep a list of these developments? With
  one, those lots could be marked and every other lot could pass normally.
- **The minimum number of homes per acre.** Every Beaverton zone that
  allows the building also sets a minimum number of homes per acre. Four
  homes meet it only on a small lot: at most about 5,100 sq ft in most of
  the apartment and commercial zones, 2,900 sq ft downtown, and about
  25,000 sq ft in the lowest-density zone. The draft fails anything larger.
  The code lets a project fall short if it shows how the site could reach
  the minimum later, for example by leaving room to split off more lots.
  Should a larger lot where that is plausible count as a fit, or is failing
  it the right starting point?
- **The neighbourhood service zone (NS).** Only half of each NS district's
  area may be used for homes, and whether that share is already taken
  depends on the neighbours, not the lot. The draft never passes an NS lot
  outright. Is that acceptable, or should NS be left out entirely?
- **Utility easements.** In six residential zones (the multi-unit and
  mixed residential zones, two of them at Cooper Mountain) the code says a
  building may never sit on a public utility easement. There is no easement
  map, so those lots cannot pass outright either. Is there an easement
  source worth buying or asking the county for?
- **County zoning kept after annexation.** About 650 acres inside Beaverton
  still carry county zoning, which the city keeps after annexation. The
  city's own parking and design rules replace the county's on that land;
  the rest is the county's. The draft screens these lots under the county's
  rules, and has not worked out which of those the city's rules replace. Is
  screening them under the county's rules good enough for now?
- **Next to the downtown transition zone.** In three downtown zones the
  side and rear setbacks are 10 or 20 feet next to houses or the downtown
  transition zone, and nothing next to anything else. The screen cannot yet
  tell which neighbour a lot has, so it uses the larger figures everywhere.
  This is the same question as Hillsboro's SCR-DNC above.

### Sherwood

- **The infill design section: every lot, or only infill lots?** Sherwood
  has a section headed "Building Design on Infill Lots". Its first sentence
  applies it to every building over 24 feet tall, but the section before it
  says it is for small lots created in small land divisions. The draft
  applies it to every residential lot. That has two effects. The side yard
  grows from 5 feet to 6, because the pod is 26 feet tall. And the section's
  cap on floor area to lot area applies: the pod's two floors need a lot of
  about 8,064 sq ft in LDR, where the zone's own minimum is 7,000, and
  about 7,331 sq ft in MDRL. If the section only covers infill lots, lots
  between 7,000 sq ft and those figures would pass. Which reading does the
  city use?
- **Planned developments.** Every residential planned development on the
  map allows middle housing only if its approved plan does. Nobody has read
  those plans, so the draft never passes a lot in one outright: a lot the
  building fits comes back as "needs a closer look". Does the city keep the
  approved plans somewhere they could be read, or a list of which allow
  four-unit buildings?
- **Parking near transit.** Under the state's climate rules, Sherwood
  requires no parking within half a mile of a frequent transit corridor, or
  in and around the Town Center. The draft asks for one space per home
  everywhere, so it can fail a lot near transit that the city would pass,
  never the reverse. Is there a map of those corridors and the Town Center
  worth drawing for the screen?
- **Driveways and narrow lots.** Driveways may take up at most half of a
  lot's street frontage. A shared 20-foot driveway needs 40 feet of
  frontage, and the zones allow lots as narrow as 25 feet along the street.
  The screen cannot yet say this, so it will pass some narrow lots the city
  would not. Is it worth adding, or is this rare enough to leave for the
  closer look?
- **An alley as a front.** Read word for word, Sherwood's code makes a lot
  line along an alley a front line, so a lot backed by an alley would owe
  a front yard on both sides. The draft treats an alley line as a side or
  rear, as in Hillsboro. Is that how the city reads it?
- **Land the city's map shows but has not annexed.** Sherwood's zoning map
  paints county zones, and the codes of neighbouring cities, on land it
  marks as not yet annexed. The largest piece, about 1,156 acres, carries
  what looks like Tualatin's industrial code. The draft leaves those lots to
  the county's rules if the county's records put them outside Sherwood,
  and unscreened if they put them inside. Nobody has checked which. Is that
  the right approach?
- **Sewer and water.** A middle housing permit in Sherwood needs the city
  engineer to confirm the lot has enough sewer, water, storm drainage and
  emergency access. The draft does not screen for this. Is there a utility
  map worth adding, or is this left for the closer look, as in the county?
- **Old Town.** About 45 acres of downtown are in the Old Town overlay. The
  map shows the overlay but not the residential zones under it, so those
  lots are left unscreened for now. Does the city have a map of the zones
  under Old Town?

### King City

- **The older neighbourhoods.** King City's code has two halves. The new
  Kingston Terrace area allows fourplexes outright. The older residential
  zones share one table of housing types that stops at duplexes and
  apartment buildings of five or more homes; it has no triplex or fourplex
  line at all. King City is big enough that the state's middle housing
  rule applies to it, and the code mentions fourplexes twice elsewhere
  (to excuse them from a density cap and a parking cap), but never allows
  one in those zones. The draft follows the city's table and says no in
  all six older residential zones. Should it, or does the state rule allow
  a fourplex anywhere a house is allowed, whatever the city's table says?
- **Does the minimum density apply to one fourplex?** Kingston Terrace
  sets a minimum number of homes per acre for "each development": 22 in
  the Town Center, down to 8 in the Rural Character area. The draft
  applies it to a single fourplex on an existing lot, so four homes can
  only go on a Town Center lot up to about 7,900 sq ft (Beef Bend about
  9,700, Central about 17,400, Rural Character about 21,800); a bigger lot
  fails. The same code sends a fourplex on an existing lot straight to a
  building permit, with no development review, which suggests the minimum
  may be meant for larger developments. Which reading does the city use?
- **Paved area counts against coverage.** Kingston Terrace caps buildings
  and paved surfaces together (90 percent, 80 in Rural Character). The
  screen can only compare the building, so it will pass some lots where
  the building plus its parking court, drive and walks go over. Is that
  acceptable for a first pass, or is it worth measuring paved area?
- **A small "Neighborhood Mixed Use" patch on the Kingston Terrace map.**
  The Kingston Terrace map shows one small area with that name, which is
  not one of the area's four zones. The older part of the city has a zone
  with the same name, but its rules do not apply inside Kingston Terrace.
  The draft leaves the patch unscreened. Does the city say what it is?
- **The city's list of approved "similar uses".** King City's code tells
  the city manager to keep a list of uses the planning commission has
  approved in zones that do not list them. It was not found online. If it
  exists and names a fourplex in an older zone, that zone's "no" is wrong.
  Is it worth asking the city for it?

## 7. Tests

Last full run before the King City commit (`uv run pytest flats/tests -q
-n auto`, all five layers, 2026-09-29):

**1 failed, 3683 passed, 5 skipped in 394 s.** `uv run ruff check flats/
scripts/`: all checks passed. (Before the Sherwood commit it was 1 failed,
3668 passed, 5 skipped; before the Beaverton commit 1 failed, 3641 passed,
5 skipped; before the Hillsboro commit 1 failed, 3620 passed, 5 skipped.)
The King City run came after the pins and the reader change below were in
place; the failures they closed are described under Pinned counts and
Reader changes.

The first Sherwood run had 4 failed, 3663 passed: the expected one below,
the alley pin (Sherwood is a sixth city that sends the drive to an alley),
and two reader checks that misread Sherwood's text (a floor area ratio
printed as a percent, and "the lesser of feet or stories" read as a lost
number). Those three were closed by the pin update and two reader changes;
see Pinned counts and Reader changes.

The one failure is expected and is not fixed here:

- `test_unweighed_layers.py::test_no_encoded_layer_is_outside_the_corpus_that_ranks_the_work`
  lists `or/washington/_unincorporated`, `or/washington/hillsboro`,
  `or/washington/beaverton`, `or/washington/sherwood` and
  `or/washington/king-city`. The
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

Re-run on the Beaverton tree (2026-09-29): **4 failed, 312 passed.** The
same four tests, failing on the same Hillsboro rows. Beaverton adds no
corner variant and no new failure.

Re-run on the Sherwood tree (2026-09-29): **4 failed, 312 passed in 247 s.**
The same four tests, failing on the same Hillsboro rows. Sherwood holds no
corner variant (its corner lot changes no figure) and adds no failure.

Re-run on the King City tree (2026-09-29): **4 failed, 312 passed in 240 s.**
The same four tests, failing on the same Hillsboro rows (still 14 reachable
rules, not 12). King City holds no variant of any kind: its street-side
yard is held as a single figure and its corner lot changes no other number,
so it adds no failure.

### Pinned counts and sets moved on this branch

- `test_port.py`: 24 layers (23 jurisdictions and the state layer), 414
  zones. Unincorporated took it to 20 and 314; Hillsboro to 21 and 351;
  Beaverton to 22 and 379; Sherwood to 23 and 400; King City to 24 and
  414.
- `test_refusals.py`: notes 134, comments 241, tests 18 (unincorporated
  had taken comments from 127 to 148 and notes to 122; Hillsboro to 194
  and 129; Beaverton added 21 comments and 5 notes; Sherwood 12 comments;
  King City 14 comments, each listed in the test. King City's projections
  paragraph runs on into the unlisted-use one, so that one is counted
  twice).
- `test_exemptions.py`: stated 377, numeric 63, marker 0, dash 2, silent 2
  (272 after unincorporated, 338 after Hillsboro, 375 after Sherwood). King
  City's 2 are both `stated`: Table 16.114-13's parking maximum and Town
  Center's "N/A" height. Beaverton's 32 are all
  `stated`: 18 minimum lot areas, 10 maximum heights, 4 parking maximums.
  Sherwood's 13 are 12 densities and the quadplex parking maximum. The 8
  `numeric` are the six density maximums and VLDR's and VLDR_PUD's
  minimums; the 5 `stated` are the parking maximum and four density
  minimums, and those four are stated on a neighbouring sentence, not the
  one that does the work (Doubts).
- `test_districts.py`: four unincorporated rulings (ASC 2 overlay; RPZ,
  THPRD, TVWD not zones), TO:R80-120 in `BY_HAND`, and the Hillsboro
  rulings (ANX, CO, and the two alias spellings "SID I-P" and "SC-BP").
  Beaverton adds 13 `RULINGS`: eight halves of column heads the encodeplus
  export breaks across two lines ("C-" over "WS", "CM-", "SC-", "TC-",
  "HDR", "MU", "RM", "WS"), four landscape buffer types of Table
  60.05.25.13.D (FB-5, FB-10, FBN-10, FBN-20), and THPRD, the park district.
  Sherwood adds three: OT (the Old Town overlay's own abbreviation), CIVIC
  (a use-table heading) and TEA (the Tonquin Employment Area, a plan area
  in the industrial table's note 1).
- `test_alley.py`: lines keyed to the rear line 28 + 19 + 1 (Hillsboro
  SCR-OTC's rear-loaded yard), and Hillsboro added to the layers whose
  alley access is required (12.50.715 C.2.c.i). Sherwood joined that set
  as the sixth (16.14.030 A.5.a, Ordinance 2022-004: "For lots or parcels
  abutting an alley, access must be taken from the alley").
- `test_routing.py` `OPEN`: two Hillsboro rows, 12.61.400 to 12.23.300 and
  12.61.400 to 12.50.845. Why they stay open is under Owed locally.
  Beaverton adds two: 20.05.15 to 20.25.05 (the single-room-occupancy
  note, not the pod's path) and 20.15.15 to 60.50.05 (accessory structures
  in the three zones that refuse). `FOLLOWED` gains five Beaverton rows:
  the four food-cart notes pointing at their own tables, and
  70.15.10 to 70.15.10.5, a false close pinned so it is seen (Doubts).
  Sherwood adds one `OPEN` row, 16.40.050 to 16.40.040: a Residential PUD's
  density may be pooled across the zones it spans (16.40.040 D). The PUD
  blocks take the base zone's figures, a quadplex's density is exempt, and
  every PUD lot is qualified on its plan, so no value quotes it.
  King City adds two `OPEN` rows: 16.114.040 to 16.84.060 (note 2 sends
  cottage clusters to 16.84.060; the pod is not one) and 16.114.130 to
  16.132 (16.114.130 B says 16.132 does "not apply" in Kingston Terrace, a
  pointer that shuts a chapter out; 16.132 is stored and read, and no value
  quotes it).
- `test_height.py`: `STOREY_FLOOR_ABOVE_TWO` = Hillsboro MU-VTC (3 stories
  inside a Center Core, held everywhere).
- `test_min_height.py`: `FLOORS_ABOVE_THE_POD` pins the five Hillsboro
  floors a 26-foot, two-storey pod misses: MU-C 45 ft, SCC-SC 30 ft,
  UC-MU and UC-AC 35 ft, MU-VTC 3 stories. It is pinned both ways, so a new
  floor fails it, and so does one of these that stops binding. A ceiling
  held as exempt (UC-AC's "None") is skipped as no ceiling.
- `test_clackamas_unincorporated_height.py`: the silent-maximum pair is
  now Wilsonville OTR and Hillsboro SCC-DT (Figure 12.61.400-D).
- `test_definitions_register.py`: Hillsboro added to the layers that define
  a corner lot (12.01.500, not greater than 135 degrees), then Beaverton
  (Chapter 90, "less than 135 degrees"; the one-degree gap is a doubt),
  then Sherwood (16.10.020, two or more streets "other than an alley"; no
  angle test), then King City (16.24.020, two or more public street
  rights-of-way; no angle test).
- `test_gresham_last_notes.py`: the parking-ceiling layers are now four,
  with Hillsboro (Table 12.50.320-1, "Quadplex 2" in Zone A). The test was
  renamed from "the three" to "the four", and to "the five" with
  Beaverton (Table 60.30.10.5.A, 1.8 a unit on the "Other Zone" row).
  (Checkpoint 5 of this note named these two files the wrong way round;
  corrected at checkpoint 6.)
- `test_readiness.py`: 45 tests, with the new
  `test_a_city_that_has_no_standards_requiring_parking_states_zero`
  (Hillsboro), `test_a_two_digit_marker_is_cut_only_where_its_note_is_quoted`
  (Beaverton), `test_a_ratio_printed_as_a_percent_still_reads`
  (Sherwood) and `test_a_marker_glued_to_a_thousands_group_is_read_by_the_grouping`
  (King City). See Reader changes.
- `test_orphaned.py`: 5 tests, with the new
  `test_a_comparison_is_not_a_measurement` (Sherwood). The scan now finds
  two lines and both are pinned: Happy Valley's (`KNOWN_ORPHAN`, a lost
  numeral) and King City's NMU frontage sentence (`KNOWN_MISPLACED`,
  16.102.060 A.3.a, "of 20 width of feet": the numeral is on the line, the
  words around it are out of order). Pinned rather than excused, because a
  rule that let any number on the line clear the hole would also clear the
  next real one. The module docstring says so. A test change, not a reader
  change.
- `test_glossary.py` was not edited for King City. Its
  `test_no_chapter_in_the_corpus_is_only_skimmed` failed on the first King
  City run (199 entries, 15 out of order); the layer's `definitions_at`
  span closed it (Doubts, Reader changes).
- `test_footnotes.py`: five new tests for the Beaverton reader changes:
  `test_footnotes_is_a_notes_heading`,
  `test_the_beaverton_page_footer_does_not_end_a_notes_list`,
  `test_a_lead_line_may_name_the_section_instead_of_the_table`,
  `test_a_number_wrapped_to_the_start_of_a_line_is_not_the_next_note`,
  `test_a_list_that_goes_back_further_than_one_still_ends`.
- `test_applied.py`: 60 to 85 rows, Beaverton's 21 encoded sentences in
  25 printings, every one confirmed. Three first read `broken` or
  `unreadable` and their claims were rewritten (the test says which).
  Then 87 with Sherwood's notes 3 and 6. Note 3 first read `broken`, because
  its claim named MDRH's 2.5 stories, which the layer holds nowhere; the
  claim was rewritten in words.
- `test_glossary.py`: `test_an_encoded_definition_lands_on_a_captured_entry`
  now takes the first span of a comma-separated quote. Sherwood's corner-lot
  quote is "L488,L885-L886" (the definition, then the street definition its
  private drives come from), and the test's `int()` failed on the comma. A
  test change, not a reader change.
- `test_crossrefs.py`: the Washington County-Beaverton Urban Planning Area
  Agreement joins the documents that answer for no code section (it numbers
  its parts in Roman numerals).
- `flats/config/gaps.json` and `data/flats/exemptions.csv` regenerated with
  all three layers. `gaps.json` gains a Beaverton section with 80
  `misattributed` rows and no gaps (Hillsboro's section, committed earlier,
  has 121). That ledger guesses a quote's section from the nearest heading
  above each span, so a quote that pairs a table row with its note, or a
  heading with a paragraph under it, reads as naming two sections. One row
  was checked by hand (NS `setback_front_max_ft`, cited 60.05.15, "found"
  60.05.35): the quoted lines are 60.05.15.6, and the cite is right. The
  rest are unread; a reviewer signing a value should check its row.
- Sherwood commit (2026-09-29): `gaps.json` and `exemptions.csv`
  regenerated again. `gaps.json` gains a Sherwood section with 44
  `misattributed` rows and no gaps; nothing else in the file moved but the
  digest. The run reports 3 gaps across 23 layers, all `unmapped`, all
  from before this branch. One row was checked by hand (HDR
  `max_height_ft`, cited 16.12.030, "found" 16.12.010): the `16.12.010` the
  ledger found is the Municode page running head printed at line 130 of
  the 16.12 document, directly above the table, and the table is 16.12.030's.
  The cite is right. Most of the Sherwood rows are this running head or a
  quote that joins a table row to a note in 16.68 or 16.94; the rest are
  unread.
- King City commit (2026-09-29): `gaps.json` and `exemptions.csv`
  regenerated again, `caps.json` rewritten and unchanged. `gaps.json` gains
  a King City section with 1 `misattributed` row and no gaps (corpus total
  290 to 291); nothing else in the file moved but the digest. The run
  still reports 3 gaps across 24 layers, all `unmapped`, all from before
  this branch. The one row (`parking_front_prohibited`, cited 16.114.130,
  "found" 16.114.120) was checked by hand and the cite is right (Doubts).
  `exemptions.csv` gains King City's two `stated` rows. The whole-corpus
  gaps run took about 40 minutes this time, sharing the machine with the
  quadfit tests; King City alone takes 22 s.
- `data/flats/crossrefs.csv` regenerated over the whole corpus (`python -m
  flats.encode.crossrefs --binding`). Besides the Washington rows it
  rewrites some Clackamas, Fairview and Portland rows. Those come from
  store text that changed on main before this branch; none of those layers
  is edited here.

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
- `test_washington_beaverton.py` (11 tests, 15 cases): the 28 districts
  10.25 classifies, the pod on one lot in 22 zones, the two Washington
  Square districts refusing though Multi-Dwelling says P, refusals carrying
  the use row only, NS capped by its district share, WAcnty and ROW
  ruled, the UPAA qualifier on every admitting zone's setbacks, lot and
  height, the parking maximum (1.8 and the four N/A zones), RMB and RMC's
  height plane, downtown holding the setback owed beside RC-DT, and nothing
  `verified`.
- `test_washington_sherwood.py` (13 tests, 25 cases): the 35 map codes as
  21 zones and 14 rulings, the pod on one lot in the five residential zones
  and their PUDs, each PUD admitting it only as its plan allows (five
  parametrised cases), each PUD taking its base zone's standards (four
  cases), the base zones not qualified, refusals carrying the use row only,
  the 5 ft side yard loading as 6 under 16.68.030 B.1 (six cases), the
  floor area ratios, MDRH holding feet only, the quadplex parking minimum
  and exempt maximum, the corner lot, no map code sent to the county, and
  nothing `verified`.
- `test_washington_king_city.py` (14 tests): the 14 districts and 12
  rulings the maps need; only the four Kingston Terrace zones admit the
  pod, on the use table row and the B.2 exemption from plan review; the
  six older districts refuse on the 16.84.010 table ("Multi-dwelling N P P
  P N P", no triplex or fourplex); the other four refuse on their
  permitted uses; the glued lot size is the printed 1,500 with note 16's
  "may be" quoted beside it; Rural Character's side yard is 10; the front
  yard is a 10/26 range; density and height; coverage held as building
  coverage with "looser than the code" in the cite; no parking minimum or
  maximum; the 90-degree stall row; the corner lot; the five county pockets
  name county zones the county layer holds; and nothing `verified`.

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

Beaverton (all run on 2026-09-29, before the downtown setback fix, which
moves quotes between two lines of the same tables and changes no count
below):

- `crossrefs --binding`: 40 unfetched, all beside a number the screen
  uses, 35 of them beside a distance. Checked one by one:
  - 19 are in stored documents. encodeplus prints a heading as
    "60.05.15. Building Design…" and numbers subsections inside the
    text, and the ledger does not see that as the section: 20.10.16.1,
    20.25.10.4, 60.05.15.6 and .7, 60.05.25.4 and .17, 60.05.35.5,
    60.30.10.5 and .11, 60.55.35.3, 70.10.1, .2, .6, .7 and .8, and the
    four downtown tables 70.15.10.1 to .4.
  - 10 are figures, drawings nobody has read: the eight Chapter 70
    setback figures (70.15.10.1.1 to 70.15.10.4.2), Figure 70.15.10.2.3
    (RC-OT's density), and Figure 70.20.10.6.2 (Active Frontages Map).
  - 11 are not stored: 40.30 (zero yard setbacks), 40.55.15.1 (parking
    determination), 60.35.10 (more FAR with a planned unit development),
    60.11 (food carts), 60.20.20 (manufactured homes), 60.50.25.14
    (vehicle camping), 60.70.35.14 (wireless), 10.70.10 (emergency
    shelters), OAR 845, the Comprehensive Plan's 1.5.2, and "30", which
    is 10.40.1's "Chapters 30 through 80". None is on the pod's path;
    40.30, 40.55.15.1 and 60.35.10 are reliefs an applicant could ask for.
- `uncited`: 160 statements of 607 measured lines not quoted by any value.
  Mostly standards on paths the pod does not take (detached and townhouse
  lots, single-room occupancy, commercial buildings, wireless towers).
- `missed`: 160 statements naming a screened field; 37 state a figure the
  corpus has never held (the ledger's own caution: most are another use's
  column).
- `applied`: encoded 25, confirmed 25.
- `qualified`: 315 Beaverton rows, none unread. `qualified --write-caps`
  wrote the Beaverton caps into `caps.json` (Zones).
- `attribution`: 80 of 341 values cite a section their text is not in. All
  80 were checked by hand against the section headings above the quoted
  lines, and all sit under a cited section (Doubts).
- `waved`: 258 Beaverton dismissal cards over 3,753 qualified values, in
  the corpus-wide set of 1,049. None was re-read blind; that is the local
  second reading.
- `stale`, `travelled`, `unheld`: no Washington rows (run after the fix).
- `consumed` (corpus-wide, by field): 70 Beaverton values sit in fields the
  screen does not read, so none of them can change an answer today: front
  maximums (16), parking kept off the frontage (17) and off the street
  (17), vehicle frontage share (16), and driveway approach widths (4). They
  are the 60.05 and Chapter 70 design standards; a wrong one would not show.

Sherwood (all run on 2026-09-29):

- `crossrefs --binding`: none open. The first run found 14 beside a number
  the screen uses; all 14 are closed in the layer's `crossrefs` block, each
  with a note:
  - 4 are not references: "2022106.13.2022" and "06.13.2022" are the file
    path printed in the ordinance's page footer, and 16.22.080 and
    16.31.100 are editor's notes on repealed chapters;
  - 46 is OAR 660 Division 46, the state's middle housing rule, which
    caps what the city may require;
  - 16.68.020 A is in the store; the ledger did not match the letter to
    its heading. It is the infill land division's own test (Refusals);
  - 16.82, 16.88, 16.89 and 16.89.020 are procedure (conditional uses,
    use classification and interpretation, and the Residential Design
    Checklist, which can only relax a design standard case by case);
  - 16.46, 16.90 and 16.90.020 are about another building (manufactured
    home parks, the site plan review that multi-family housing gets, and
    the commercial design matrix LI applies to hotels);
  - 16.134.020 (floodplain) only narrows a lot.
  Unfiltered, 42 stay open, none beside a figure the screen uses.
- `uncited`: 35 statements of 257 measured lines not quoted by any value.
  Mostly Old Town's design heights (16.162), the telecommunication tower's
  70 ft, accessory structures, townhouse frontages, and the driveway 50
  percent (Refusals).
- `missed`: 35 statements naming a screened field; 16 state a figure the
  corpus has never held. 22 sit in sections nothing has been quoted from,
  one in a section read for something else (16.40.050's "within one
  hundred (100) feet of a residential zone", a distance, not a height).
  The rest are Old Town's cornice and arcade heights, 16.50's accessory
  structures, the clear vision area and the industrial lot width, none on
  the pod's path.
- `applied`: encoded 2, confirmed 2 (notes 3 and 6). Note 3 first read
  `broken`; its claim was rewritten (Tests, `test_applied.py`).
- `qualified`: 81 Sherwood rows, none unread. The first run showed every
  row "7 unread of 7" until the footnote file's census was completed.
  `qualified --write-caps` left `caps.json` unchanged: no Sherwood note is
  ruled `unmeasured`.
- `attribution`: 44 of 109 values cite a section their text is not in. All
  44 were checked by hand and none is a wrong cite (Doubts).
- `waved`: 5 Sherwood dismissal cards over 405 qualified values, in the
  corpus-wide set of 1,054. None was re-read blind; that is the local
  second reading.
- `stale`, `travelled`, `unheld`: no Sherwood rows.
- `consumed` (corpus-wide, by field): two Sherwood values sit in fields
  the screen does not read, `parking_front_prohibited` and
  `driveway_approach_max_width_ft` (16.14.030's 20 ft approach), and the
  six residential zones' 20 ft garage entrance setbacks are in a field the
  screen declares it leaves out. None of them can change an answer today.

King City (all run on 2026-09-29, on the final layer):

- `crossrefs --binding`: none open. The first run found 9 beside a number
  the screen uses; all 9 are closed in the layer's `crossrefs` block:
  - 4 are not references: Municode page footers ("174.86.42" to
    "174.86.48", page numbers of Supplements 14 and 15);
  - 16.156 (conditional uses) and 16.160 (nonconforming situations) are
    `other_path`: the pod is allowed outright and is new construction;
  - 16.172 (home occupations), 5.05 (liquor licences) and 8.04.130 (noise)
    are `other_building`.
  Unfiltered, 104 stay open (corpus-wide), none beside a figure the screen
  uses.
- `uncited`: 28 statements of 192 measured lines not quoted by any value.
  Mostly NMU's own frontage and height rows (16.102.040 and .050), which
  refuse the pod, and 16.84.050's garage door width.
- `missed`: 28 statements naming a screened field; 8 state a figure the
  layer holds nowhere, all in sections nothing has been quoted from (NMU
  16.102.040 and .050, and 16.84.050), none on the pod's path. 4 are
  figures the corpus has never held (a 4 ft window sill, an 18 ft
  accessory height, a 10 ft garage door, a 6 ft alley garage entry).
- `applied`: encoded 0. No King City note is ruled `encoded`; the six
  census notes are dismissed and the dimensional table's notes are read in
  the footnote file's header (Documents).
- `qualified`: every Kingston Terrace row "0 unread of 6". The first run
  showed "6 unread of 6" until the footnote file was written.
  `qualified --write-caps` left King City out of `caps.json`: no note is
  ruled `unmeasured`.
- `attribution`: 1 of 70 values cites a section its text is not in,
  checked by hand; the cite is right (Doubts).
- `stale`, `travelled`, `unheld`: no King City rows.
- `consumed`: no King City rows.
- `words` (not a step-9 ledger, checked because of the glossary span): 29
  cards; 18 `defined`, 11 `silent`. Four of the silent ones (multifamily,
  quadplex, duplex, triplex) are defined in 16.24.030, outside the span
  (Doubts). The other seven (net acre, story, middle housing, townhouse,
  apartment, attached dwelling, alley) are silent with or without the
  span.

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

### Beaverton

- **`flats/provenance/sources.py` `OFFICIAL`.** Add `online.encodeplus.com`
  (the city's published code) and `www.washingtoncountyor.gov` (the UPAA).
  Until then every Beaverton document fetches with "unknown source", and
  no value citing one can be verified. Not edited here (off limits).
- **`flats/provenance/fetch.py`: the encodeplus page footer.** Every page
  of the export ends "Beaverton Development Code" and "Date Printed: …
  Chapter NN, XX-NN". The footnote reader now skips both (Reader changes),
  but a fetch-time strip would keep them out of every reader. Proposed,
  not made.
- **`DECLARED_OWING`: nothing.** The resolver was run on every Beaverton
  zone on 2026-09-29, and none owes a required field.
- **The coverage ledger with Beaverton lots**, which `test_unweighed_layers`
  waits on (Tests).
- **The UPAA development list.** Until someone has the list of developments
  annexed after county approval, `site_specific_limitation` caps every
  admitting zone. Question for Steph.
- **Neighbour lists (`neighbours:` in the layer).** Beaverton declares
  none, so `abuts_residential_zone` and `abuts_nonresidential_zone` stay
  unstated on every lot. A local reader declaring them must keep every
  residential zone and RC-DT off `abuts_nonresidential_zone`'s `true_for`
  (RC-BC, RC-OT and RC-MU owe a setback beside both), and must decide
  whether WAcnty counts as residential (it is whatever county zone the map
  shows, so probably neither list).
- **Registry facts the layer had to approximate** (a `flats/rules/` change,
  not made):
  - a district-share fact for NS's 50 percent residential cap (held on
    `site_specific_limitation`);
  - the Cooper Mountain Nature Park boundary for the park setback in the
    Cooper Mountain zones (held on `site_specific_limitation`);
  - a named-neighbour-zone fact ("borders RC-DT"), the same ask as
    Hillsboro's SCR-DNC.
- **An easement layer** for `utility_easement` (MR, RMA, RMB, RMC, CM-RM,
  CM-MR).
- **Map data the stricter figures wait on:** distance to a light-rail
  platform (400 ft, SC-MU, SC-HDR, SC-S density), Figure 70.15.10.2.3
  (RC-OT's 18 or 24), and the parking zone map (it does not move the
  quadplex maximum, but it moves other rows).
- **WAcnty.** Whether the county's zoning map still carries a district on
  annexed lots (the pocket resolves through it), and which county standards
  10.40.1 lets the city's Chapters 30 to 80 replace.
- **Documents not stored** (listed under Documents), of which the
  Engineering Design Manual matters most: driveways and corner sight
  clearance both point there.
- **Clean Water Services.** The net acre deducts water quality facilities,
  wetlands and natural resource areas, and the natural area definition
  names CWS vegetated corridors. Overlay work, as for the county.
- **Readers, proposed not made:**
  - `crossrefs`: recognise encodeplus's "60.05.15. Title." heading shape
    and its in-text subsections; 19 of the 40 unfetched BINDING rows are
    in stored documents.
  - `routing`: the wrapped-line guard is skipped for a number from the
    document's own chapter, which falsely closes `70.15.10 -> 70.15.10.5`
    (pinned in `FOLLOWED`).
  - `attribution`: why 80 values read as citing a section their text is
    not in, when a hand check puts all 80 under a cited section.
- **The blind second reading, re-screen and promotion**, including the 258
  Beaverton `waved` cards.

### Sherwood

- **`flats/provenance/sources.py` `OFFICIAL`.** Add
  `www.sherwoodoregon.gov`, the city's own site, which holds Ordinance
  2022-004. Until then the three ordinance slices fetch as "unknown
  source", and every value quoting one (every minimum lot area, the
  driveway, corner-access and alley-access defaults) cannot be verified.
  Not edited here (off limits).
- **`DECLARED_OWING`: nothing.** The resolver was run on every Sherwood
  zone on 2026-09-29, and none owes a required field.
- **The coverage ledger with Sherwood lots**, which `test_unweighed_layers`
  waits on (Tests).
- **The pages the Municode PDF drops** (296.1-296.2, 296.18.1-296.18.10).
  The layer reads them from Ordinance 2022-004 as adopted. Someone with
  the city's current code (Municode's web page for 16.12.030 and 16.14.030,
  or the city's own copy) should confirm nothing later amended them
  (Doubts).
- **Planned development plans.** Until someone has the Final Development
  Plans, or a list of which allow a quadplex, `site_specific_limitation`
  caps every residential PUD lot (VLDR_PUD, LDR_PUD, MDRL_PUD, MDRH-PUD,
  HDR_PUD). Question for Steph.
- **Map ingest for the 14 ruled codes**, and a check of `JURIS_CITY` on the
  taxlots under them. If the unannexed codes (Unannex, AF-5, AF-10, AF-20,
  EFU, FD-10, FD-20, R-9, RRFF5, MG, MBP) sit on taxlots the county does
  not call `SHERWOOD`, this layer never sees them and whichever layer the
  taxlot's jurisdiction names screens them. MG and MBP read as Tualatin's
  codes and RRFF5 as Clackamas County's, so some of that land may not be in
  Washington County's unincorporated layer either. UGA (a concept plan comes
  first) and OS (no chapter sets its standards) need the same check.
- **Old Town.** A map of the base zones under the overlay (HDR, MDRL and
  RC by 16.162), so those lots can screen under their base zone. 16.162's
  own use and height exceptions are not encoded.
- **Registry facts the layer had to approximate** (a `flats/rules/` change,
  not made):
  - a transit distance or delineated-area fact for CFEC (half a mile of a
    frequent transit corridor; the Town Center and a quarter mile around
    it), so the parking minimum can go to zero there;
  - a driveway share of frontage field (16.14.030 A.2, 50 percent), apart
    from `parking_area_max_frontage_pct`;
  - an alley-as-front-line reading of `front_lot_line_corner`, if Steph's
    answer is that the city reads the words that way;
  - if the narrow reading of 16.68.030 is right, an "infill lot" fact
    (created below the zone's minimum in a land division under five acres)
    to gate the floor area ratio and the side yard plane.
- **Documents not stored** (listed under Documents). The Transportation
  System Plan matters most: street classes decide the corner access street
  and the right-of-way a lot dedicates. The CFEC map, the 16.68.030 drawing
  and the 16.14.030 driveway figure are unread.
- **Utilities.** Sufficient Infrastructure (16.12.030 B.3) needs sewer,
  water and storm mains, which no screen layer has. Question for Steph.
- **Readers, proposed not made:**
  - `attribution`: a section read off the page's running header is wrong
    where the heading's own page is missing (29 values read as 16.12.010),
    and a page number ("296.11") is taken for a section (Doubts);
  - `crossrefs`: the ordinance's scanned page footer prints a file path
    ("2022106.13.2022", "06.13.2022") that reads as two section numbers. A
    fetch-time strip in `fetch.py` would be the cleaner fix; off limits here;
  - `missed`: a fraction the PDF prints as digits ("two and one-half (21/2)
    feet") is read as the whole number before it.
- **The blind second reading, re-screen and promotion**, including the 5
  Sherwood `waved` cards.

### King City

- **Map ingest for layer 4.** The Kingston Terrace neighbourhoods are on
  layer 4 of the city's service (`Zoning_Designations`), not on layer 1
  (`ZONECLASS`). The layer's aliases take layer 4's names, but the ingest
  has to read both layers, and layer 4 must win where they overlap. Until
  then no lot reaches a zone that admits the pod. About 404 King City and
  98 unincorporated taxlots touch a Kingston Terrace polygon.
- **The county pockets.** Five "(WC)" codes send their lots to the county
  layer's R-6, R-9, R-15, CBD and INST. Check that a taxlot under one keeps
  `JURIS_CITY` = `KING CITY` and reaches this layer first, so the pocket is
  followed.
- **`DECLARED_OWING`: nothing expected.** The four Kingston Terrace zones
  hold every field the screen reads that the code states. The resolver was
  not run against a King City lot, because none is ingested; run it once
  layer 4 is in.
- **The coverage ledger with King City lots**, which
  `test_unweighed_layers` waits on (Tests).
- **Registry and model changes the layer had to approximate** (a
  `flats/rules/` change, not made):
  - an impervious-surface share field, or a coverage kind, so Kingston
    Terrace's "buildings and impervious surfaces" cap can be held as
    written. Today it is held as building coverage, which is looser;
  - `definitions_at` taking more than one span, so 16.24.030's use-type
    definitions can be declared beside 16.24.020 without the chapter
    reading as skimmed (Doubts). The residential use types are
    `L1184-L1350` ("C. Residential Use Types." to the line before "D.
    Commercial Use Types."), and all four `silent` words are in it. That
    alone is not enough: measured with the glossary's own reader, that span
    holds 20 entries with 2 out of order (the code files Duplex after the
    Dwelling entries, and Manufactured/mobile home park after Mobile home),
    and one is the most 20 entries may have, so the second span would read
    as skimmed too. The change also needs a way to say a chapter is ordered
    by the code's own grouping rather than by letter. (16.24.020 alone,
    `L20-L1117`, is 154 entries with 1 out of order, and reads whole.)
  - if Steph's answer on the density floor is that it does not reach one
    fourplex on an existing lot, a condition for "subject to development
    plan review" to gate it.
- **The older districts, if Steph's answer opens them.** Their dimensions
  (16.84.040 and the district chapters) and the citywide parking chapter
  (16.132, whose stall table lost its foot and inch marks in the PDF) would
  have to be read and encoded. Nothing is drafted for that case.
- **Documents not stored** (Documents). The Transportation System Plan
  matters most, for 16.80.060 A's right-of-way and 16.114.120's streets.
  The Habitat Conservation Area maps and the Regulating Plan are unread.
- **The unlisted-use list** (16.82.030 A), from the city (Questions).
- **The blind second reading, re-screen and promotion.**

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

Beaverton (all figures from 2026-09-29, over the whole corpus):

- `flats/encode/footnotes.py`, four changes, made one at a time so each
  can be judged. Counts are notes captured, unread, and blocking across
  the corpus, with Beaverton's captured count in brackets:

  | Step | Change | Captured / unread / blocking [Beaverton] |
  |---|---|---|
  | Before | — | 1180 / 112 / 112 [14] |
  | 1 | `NOTES_HEAD` takes "Footnotes:" (`(?:foot)?notes?`) | 1328 / 260 / 260 [162] |
  | 2 | `FURNITURE` drops the page footer: `^Beaverton Development Code$` and `^Date Printed: … Chapter NN, XX-NN$`, both anchored whole | 1373 / 305 / 305 [207] |
  | 3 | `NOTES_LEAD` takes "refer to superscripts found in Section 20.10.20" (`(?:table\|section)`) | 1464 / 396 / 396 [298] |
  | 4 | `_skipped_back`: a list that runs N, N+2, N+1 puts the N+2 back into note N | 1471 / 403 / 403 [305] |

  Every new unread note is Beaverton's, and all were then read and ruled
  (Documents). At every step the corpus moved by exactly Beaverton's
  change, so no other layer's notes moved.
  Step 4 fixes Table 20.05.15, where "If footnote 16 and / 17 apply" wraps
  a 17 to the start of a line: before, the reader took that 17 as note 17
  and stopped, losing notes 16 to 23 (`bdc.20.05.residential.txt`
  L406-L425); after, it reads them.
  Five new tests in `test_footnotes.py` (Tests).
- `flats/encode/readiness.py`: `_NOTE_BODY` and `_unmarked_by_notes`.
  Beaverton glues two-digit note markers onto the figures ("2018" is 20 ft
  with note 18, "3514" is 35 with note 14). The existing `_unmarked` cuts
  only one digit. The new function cuts a two-digit tail only when the
  quoted text also carries that note's own line ("18. …"), so Gresham's
  "12.458" is not read as 12.4. Before: 5 misquotes across the corpus, all
  Beaverton (MR `setback_front_max_ft`, RMB `max_height_ft`, RMC
  `max_height_ft`, CM-RM `min_lot_width_ft`, CM-MR `max_far`). After: none,
  and still none after the downtown setback fix. New test
  `test_a_two_digit_marker_is_cut_only_where_its_note_is_quoted`.
- Not a reader change: Beaverton's Chapter 90 slice ends at "ADDITIONAL
  ORDINANCES - PART 1", so the glossary reads only the definitions. Before:
  873 entries, 75 out of order, read as skimmed. After: 522 entries, 6 out
  of order, read whole.

Sherwood (all figures from 2026-09-29, over the whole corpus of 23
layers):

- `flats/encode/readiness.py`: a new `states_as_percent`. Sherwood's
  16.68.030 A caps floor area at "50% of lot area" in LDR (55, 60 and 65
  percent in MDRL, MDRH and HDR). The field `max_far` is a ratio, so the
  values are 0.5 to 0.65, and the quoted lines never print 0.5, so the
  misquote check flagged all four. The new function accepts a line that
  prints the value times 100 with a percent sign or word straight after
  it, and only for a field whose kind is `ratio`, and only for a positive
  value. A bare 50 still does not evidence 0.5, and a coverage (held in
  percent already) is not touched. The different-unit check still runs
  after it. Before: 4 misquotes across the corpus, all Sherwood (LDR,
  MDRL, MDRH and HDR `max_far`), and Sherwood stood at the `misquoted`
  rung. After: none, and Sherwood moves to `unsigned`, the rung the other
  three Washington drafts stand on. No other layer's rung or misquote list
  moved (a per-layer diff of all 23 before and after). New test
  `test_a_ratio_printed_as_a_percent_still_reads`.
- `flats/encode/orphaned.py`: a fourth exclusion, a comparison. Sherwood's
  16.12.030 note 3 reads "Maximum height is the lesser of feet or
  stories." That is the code's own wording (the row it notes prints "35
  feet or 2.5 stories"), and no number is missing, but "of feet" read as a
  lost numeral. `lesser` and `greater` now exclude the "of" they govern,
  the way a counting noun ("the number of stories") already did, and the
  module docstring says so. Before: 2 orphans across the corpus, Happy
  Valley's pinned `16.22.residential.txt#L1138` and
  `sdc.16.12.residential.txt#L448`. After: Happy Valley's alone. No phrase
  "lesser of" or "greater of" followed by a unit word appears anywhere
  else in the store, so nothing else could move. New test
  `test_a_comparison_is_not_a_measurement`, which also checks that a
  comparison word earlier in a line does not hide a real hole after it.
- Not a reader change: `test_glossary.py`'s comma-separated quote is a
  test change (Tests); the glossary reader already read Sherwood's
  definitions.

King City (all figures from 2026-09-29, over the whole corpus of 24
layers):

- `flats/encode/readiness.py`: a new `_regrouped`, tried under
  `glued_markers` after `_unmarked` and `_unmarked_by_notes`. King City's
  Table 16.114-4 glues note 16 to Town Center's and Beef Bend's 1,500:
  "1,50016". Both earlier readers skip any token with a comma in it, so the
  figure was printed and read as absent. Here the grouping settles what the
  quoted note line has to settle for a bare token: a group after a
  thousands comma holds exactly three digits, so a fourth or fifth can only
  be a marker, and cutting it leaves the printed number. More than two
  trailing digits is left alone. Before: King City at the `misquoted`
  rung, with KTTC and KTBB `min_lot_sqft`; every other layer's rung and
  misquote list as it is after. After: King City `unsigned`, misquotes
  none; no other layer moved (a per-layer diff of all 24 before and after).
  New test `test_a_marker_glued_to_a_thousands_group_is_read_by_the_grouping`,
  which also checks that "7,500" is not read as 750 or 75, that a
  three-digit tail ("1,500165") is not cut, and that the cut happens only
  under `glued_markers`.
- Not a reader change: King City's 16.24 slice declares `definitions_at:
  L20-L1117`, so the glossary reads 16.24.020 alone. Before: 199 entries,
  15 out of order, read as skimmed (`test_glossary` failed). After: 154
  entries, 1 out of order, read whole. `glossary.py` itself is unchanged.
  The words ledger's cost is under Doubts.
- Not a reader change: `test_orphaned.py` pins King City's NMU sentence as
  `KNOWN_MISPLACED`. `orphaned.py` is unchanged; before and after, the scan
  finds the same two lines.
