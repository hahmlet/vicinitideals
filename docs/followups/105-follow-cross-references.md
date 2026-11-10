# 105. Follow every cross-reference one layer down (Steph 2026-10-20).

105. [Claude] [batch 1 + round 2 DONE 2026-11-08 on flats/crossref-follow; round 3 (every binding row) DONE on flats/crossref-follow-2, three chapters fetched 2026-11-08 with Steph's OK; Tigard RES-A to RES-C now carry the 5 ft S-3 strip; round 5 (references into the three chapters) on flats/crossref-3: Tigard MU-CBD 8 ft S-4 on alley, park and trail lines, Canby 16.41.070 fetched, no change] [scan: YES (new standards bind)]
   **Follow every cross-reference one layer down (Steph 2026-10-20).** A footnote or standard that says
   "see Section X", "conform with Table Y for the Z district" or "may be approved per Section W" is not
   read until the place it points to is. Steph's words: "If the next layer is clear and objective, then it
   is just as essential to understand as any other table/ruling at the top level. If it's leading to an
   administrative ruling process or something, then we need to know that too." So each reference lands in
   one of: (a) clear, measurable -> encode it like any top-level standard; (b) an approval process ->
   classify by the 2026-10-14 three tiers (clear review green / conditions yellow+flag / judgement red);
   (c) not about the pod -> dismiss with the reason. Tools: `uv run python -m flats.encode.crossrefs
   <layer> --binding` (references never fetched; a ruling goes in the jurisdiction YAML `crossrefs:` map)
   and `flats.encode.routing` (redirects into held sections; closes only on an encoded value, so its
   rulings are recorded here, not in YAML).

## Batch 1 (2026-11-08, flats/crossref-follow)

Every BINDING crossref row closed in the ten places with the most lots except Tigard (unmapped), apart
from the rows below. New outcome `design` (fills ground sized elsewhere; Portland 33.248 landscaping).
Nothing found tightened a standard the screen applies to the pod, so no lot is expected to move.
Places: Portland, Washington County, Clackamas County, Hillsboro, Gresham, Beaverton, Oregon City,
Happy Valley, West Linn. Left `later` (lot creation, binds only when a pod declares a plat): Portland
33.612-33.614, Washington 430-46/601/606, Clackamas 1105.

Routing rows read (routing.csv stays open until something is encoded inside the target):
- Portland 33.120.210 -> .211: FAR bonus options (affordability, three-bedroom, visitability, fund
  payment). Reliefs only; FAR does not bind the pod.
- Portland 33.120.220 -> .283: garage walls. The pod has no garage.
- Portland 33.130.215 -> 33.120.280: detached accessory structures. Another building.
- Portland 33.140.210 note [1] -> 33.140.215.B: Table 140-3 does not apply on lines abutting RX lots.
  Can only loosen.
- Washington 418: 418-1 projections (relief); 418-2 future right-of-way "does not apply to ... Middle
  Housing"; 418-3 corner vision triangle (see open list).

## Still open

1. **Beaverton 70.20.10.6.2, the Active Frontage Design Map: HELD, trace still owed.** Facades on
   mapped Downtown streets must meet the Active Ground Floor rules; Type A frontages (and the Area C and D
   tax lots of D.4) take the non-residential design, a ground floor at least 16 ft floor to floor
   (70.20.10.txt#L377-L378, L486-L496), against the pod's 12. Type B may take the residential design,
   which 12 ft meets. Round 2 encoded `min_ground_story_ft` 16 under the site fact
   `beaverton_type_a_frontage` in RC-BC, RC-OT, RC-MU and RC-DT. Nothing observes the fact, so every lot
   in those zones is held out of GREEN (FACT-BEAVERTON-TYPE-A-FRONTAGE). The figure is NOT in the corpus:
   the stored map PDF (flats/config/areas/or/washington/beaverton/downtown-street-types-and-frontage)
   carries Figure 70.15.25.1, the Active Frontage USE Map, a different figure. Next: fetch Chapter 70's
   Figure 70.20.10.6.2 (ask Steph first), trace its Type A streets onto RLIS centrelines the Hillsboro
   way (flats/geom/active_use.py), observe the fact in flats/ingest/quadfit.py, and the held lots off
   Type A streets reopen.
2. **Corner vision areas** -- still unmodelled; round 4 collected the legs (below). (Washington 418-3; West Linn Chapter 42, held round 4; Beaverton 60.55.35.3,
   which defers to the Engineering Design Manual). This corpus does not model vision areas anywhere.
   This is the known under-count.
3. **West Linn Chapter 28**: HELD and read round 4 (below); needs a quadfit overlay. Was: (river protection areas and Habitat Conservation Areas) kept `fetch`. The
   areas are boundaries the screen does not hold (see the 28.040 ruling).
4. **Washington "improved alley"**: DONE round 2 as a flag. 430-84 lets middle housing take access
   from an alley only where it is improved to 409-3.3 A (not held). `alley_improved_required` on the
   county's defaults raises ALLEY-IMPROVEMENT-UNCONFIRMED (severity 1, no colour change) where the court
   is reached from the alley. Today that is only the East Hillsboro overlay rows, which send the court
   there; elsewhere the county only permits alley access and the screen keeps the street. Round 4
   fetched 409: 409-3.3 A prints 16 ft of pavement for an alley of 1-8 units, and the flag now names it.
5. **Clackamas 1002.02 tree history** (ruled `procedure`): answered by Steph's 2026-11-01 trees
   ruling (trees are ignored and entered per lot). No flag.
6. **Resolver gap** in flats/encode/crossrefs.py `_resolves`. A held section answers only for printed
   full-number headings. So subsections printed locally ("7." under 60.05.15), hyphen numbering
   (Washington 431-8, 407-6, 307-7.5), letter suffixes (Hillsboro 12.61.700G), ranges (Gresham
   4.1531-4.1534) and table or figure captions all read as unfetched. A fix would let `ref` resolve
   when it starts with a held id plus "." or "-". That shifts every layer's ledger, so it is its own
   change.
7. **Beaverton, noticed and not chased**: 60.05.20.7.A asks for a 10 ft walkway along an elevation with
   a primary entrance. It reads as commercial (tenant entrances, display windows). Cooper Mountain
   Nature Park 25 ft setback (Table 20.22.15 G.6): already listed NOT ENCODED.
8. **Non-binding rows: not worked.** 1,523 open rows that stand beside no encoded value (round 3
   read one, Beaverton 60.05.25.13 landscape buffers: N/A for middle housing except the Cooper Mountain
   NPB-25 already listed). Most are use-specific chapters, procedures and boilerplate; the top of the
   queue by mentions was skimmed and nothing distance-bearing seen besides that one.
9. **Tigard 18.420 (landscaping and screening): READ 2026-11-08, encoded.** In RES-A to RES-C,
   parking at the side or rear of buildings and not in garages must be screened from adjacent
   properties to the S-3 standard of Table 18.420.2 (18.280.040.txt#L111). That is the pod's rear
   court. Fetched with Steph's OK (tdc.18.420.landscaping.txt): S-3 is a minimum depth of 5 feet
   holding a 6 ft sight-obscuring fence or wall and trees (L252-L255). Encoded as
   `parking_lot_line_buffer_ft` 5 in RES-A, RES-B and RES-C; the interim hold (site fact
   `tigard_s3_screen_reaches_court`, flag FACT-TIGARD-S3-SCREEN-REACHES-COURT, 61de78f5) is removed.
   The court now stands 5 ft further off the rear line (the side setback is already 5 ft); a plan
   that misses only by the strip goes YELLOW on PARKING_STRIP_UNCONFIRMED (Steph 2026-10-04).
10. **Canby 16.41.060 and Gladstone 17.76: READ 2026-11-08, no change.** Canby: 16.41.060.C.20/.21
   define the primary street facing facade (east-west streets: 99E, 1st to 4th Avenues) and the
   secondary (north-south streets, Birch to Locust), and 16.41.050 (A)(4)(a) bans parking in front of
   both. The screen already refuses a court beside the building on a corner lot wherever
   `parking_front_prohibited` holds (`paper.side_court`), and the rear court is in front of no
   facade. Gladstone: every subsection of 17.76 relaxes (projections, heights, front averaging,
   private-street and flag-access fronts, through-lot front by owner choice); 17.76.040(5) "may" move
   a flag lot's lines, a discretionary relief. 17.76.030 (an undersized lot of record held to one
   house) only reaches lots admitted by lot-of-record relief, which no Gladstone zone resolves.

Fetched 2026-11-08 with Steph's OK ("Yes, download"), from the cities' official code sites:
Tigard CDC Chapter 18.420 (ecode360), Canby CMC 16.41.060 (American Legal), Gladstone GMC Chapter
17.76 (Code Publishing). Stored in flats/provenance/docs with their .meta.json; declared in each
city's YAML source list.

## Round 3 (2026-11-08, flats/crossref-follow-2)

Every BINDING crossref row in the corpus is now ruled (21 left open are `fetch` or `later` on
purpose). Tigard (34 rows): 23 are table and figure captions printed inside the held section that
cites them (the resolver gap, item 6), each the source of encoded values (`read`); the rest are
apartments, wireless, industrial, procedures, adjustments and land division, and 18.420.2 (item 9).
Then Canby (16, eight of them 1984 ordinance numbering in history notes, `misread`), unincorporated
Multnomah (11: home occupations, signs, lighting, the Gorge review uses GGR2 already refuses),
Estacada (10), Gladstone (8), Milwaukie (8: variances, nonconforming, the 19.907 Type I path already
ruled in DMU), Sandy, Wilsonville, Tualatin (57.400 is cited but never enacted: the chapter's section
list stops at 57.300), King City (18.106.050 is the old numbering of 16.132, which Kingston Terrace
replaces), Sherwood, and the state layer (OAR 660-046 citing itself). Nothing read tightens a standard
the screen applies to the pod, so no lot moves.

Footnote "see Section" pass: 283 of the 1,363 dismissed footnotes carry a cross-reference. Their
reasons were grouped and the 23 on dimensional rows (setback, height, lot, parking, access) read
against their targets; every one either followed the target (ZDO 845, Gresham 4.1416, Wood Village
230.335, Tigard 18.650.080.D, Clackamas 1005.02) or is scoped off the pod. No dismissal reopened.

## Round 4 (2026-11-09, flats/crossref-follow-3)

Ledger regenerated on rel5; ten new binding rows ruled (Gresham 10.0200, Beaverton 70.15.05.1 and
60.05.60.1, Washington 403-3 and 431-5.3, Tigard 18.660.3, Estacada 16.72, 377, 16.80, Gladstone 12.02).
The 128 open routing rows were read in four batches (Washington; Wilsonville, Cornelius, Hillsboro,
King City, Tigard; Clackamas cities; Multnomah cities). Fetched under Steph's standing download OK
(2026-11-09): Washington County CDC 409 (municode publication 3090), West Linn CDC Chapters 42 and 28
(Code Publishing).

Encoded (zero colour moves: every lot in these four zones is already UNKNOWN, R-9 NB and R-24 NB for
an unencoded min_lot_sqft, NMU and CCMU for unencoded interior yards):
- Washington R-9 NB, R-24 NB, NMU, CCMU: `parking_lot_line_buffer_ft` 5 (407-6.4 by 413-4.10; their
  parking reaches 413 through 390-7 and 392-9.7 A).
- Washington R-9 NB, R-24 NB: side and rear yards `qualified_by` the new unobserved site fact
  `washington_county_411_buffer` (flag FACT-WASHINGTON-COUNTY-411-BUFFER). 411 reaches every
  non-Middle-Housing permit and its 411-5 matrix names no North Bethany district, so the buffer is
  "to be determined by review authority". NMU and CCMU's 411 widths (15/15/10/0/0/10 and
  25/15/15/0/0/5 by neighbour column) are written into their yard comment for whoever encodes the yards.
- Washington alley flag: 16 ft.

Read, not encoded (possible false GREENs, each needs a mechanism or data; listed for the coordinator):
- **Vision triangles, corpus-wide.** Legs collected: Washington 418-3 20 ft from the road-edge apex;
  Estacada 15 ft from lot lines; Tigard 18.930 30 ft (35 ft on arterials); Gresham Table 6.04 40/45 ft,
  no drive or parking inside; Milwaukie 12.24 by AASHTO; Canby 10 ft street-to-driveway, 30 ft
  street-to-street from curb lines; West Linn 42.040 30 ft at corners and 42.050 a driveway triangle
  30 ft each way along the street with its apex 30 ft into the lot for every use but a one- or
  two-family house -- the pod's own driveway. A corner triangle never reaches a building whose front
  plus street-side setback is at least the leg; the West Linn driveway triangle reaches a pod whose
  front setback plus offset from the drive centreline is under 30 ft.
- **Driveway spacing by street class.** Tigard 18.920.030.I.2 (150 ft from a collector or arterial
  intersection; relief below 150 ft of frontage) and I.3 (200 ft on a collector, 600 ft on an
  arterial, no relief); Estacada 16.116.010 (D)(2) (50 ft from an intersection, relief where no other
  access) and Table 16.116.030 (private access 200 ft on a major collector, 100 ft minor). Reaches lots
  whose every street is a collector or arterial; `local_street` answers that in Tigard, but `when:`
  cannot negate it.
- **West Linn Chapter 28.** Inside the Willamette Greenway / Tualatin protection area (city zoning map,
  not held) a lot holding a Metro HCA needs a quasi-judicial permit; on HCA land the house and its
  impermeable surfaces may total 5,000 sq ft (28.110.B). Metro Title 13 is laid over Wood Village only
  in quadfit overlays.yaml.
- **Washington 418-2 future right-of-way** for R-24 NB, NMU, CCMU (half the TSP maximum width; not
  for Middle Housing): the TSP design parameters are not held. Zones already UNKNOWN.
- Cornelius Type I middle housing site review (18.100.030 (A)(2)): ministerial, GREEN tier; no change.
- Beaverton 70.20.10.6.2 / 70.15.25.1 trace (item 1): not done this round; the hold stands.
- Lake Oswego 50.06.001.5: not fetched (layer switched off, zero lots).

## Round 5 (2026-11-10, flats/crossref-3)

References into and out of the three chapters fetched in round 3, each read one layer down.
- **Tigard MU-CBD, (a) ENCODED.** 18.650.070.B.3 screens downtown parking that abuts a public
  right-of-way, a trail in a public easement or a public park to S-4 (Table 18.420.2: 8 ft,
  tdc.18.420.landscaping.txt#L256-L257). Encoded as `parking_lot_line_buffer_ft` exempt on an
  ordinary line, 8 under `abuts_alley`, `abuts_park` or both. Tigard gained a `parks:` block
  (Park true; HOA and School Land false; Natural Area, Other, Golf Course, Cemetery unstated).
  The trail is read off Metro's regional trails layer (RLIS TRANSIT/trails.shp, registered as
  `rlis_trails`, release 2026_11, RLIS Open Database licence; flats/geom/trail.py): a counted
  trail crossing the lot or within 15 ft of a non-street line answers `abuts_trail` True. Without
  the layer in the snapshot the fact is unanswered and the lot holds out of GREEN. The strip is
  charged on every non-street line once any line abuts.
- **Tigard S-4 in Bridgeport (18.640), (c).** Lies inside MUC's 20 ft parking street setback; the
  one Bridgeport lot is stopped by the density floor.
- **Tigard S-1 (service areas, roof equipment), (c).** No depth.
- **Tigard 18.420.020.C canopy / 18.420.060 fee in lieu, (c).** Reaches land divisions,
  apartments, nonresidential, wireless, mobile home parks (L73-L93), not a pod on a lot of record;
  trees are ignored (ruling 2026-11-01). Table 18.420.1 L-1/L-2 is planting make-up.
- **Tigard 18.320.040, 18.670.070, (c).** Nonresidential / mixed-use and WSRC; no MUC lot there
  admits the pod.
- **Canby 16.41.070 (DCO site and design review), FETCHED and read, (c) under
  2026-10-14-unchecked-design-details.** Awnings, an entry per unit to the sidewalk
  (`entrance_faces_street` already required), 50% windows, banding, materials. The roof allows flat
  with a cornice or a 24 in parapet (L261-L275), so the flat-roof ruling does not refuse it. The
  12-16 ft ground floor and bays are commercial/mixed only (L207-L210). The alternative (intent)
  path is optional, (b) with a clear path beside it. Canby 16.41.050 (A)(4)(b)(2)'s 5 ft strip is
  side parking only, which the screen never offers in Canby.
- **Gladstone 17.76, (c), item 10 corrected.** Four sections; 17.76.020 is nonconforming
  buildings, where 17.21 DCO and 17.22 OP send existing buildings; the pod is a new conforming
  building. 17.76.040(7)'s 20 ft is garage/carport only. Item 10's "projections" was wrong.
Expected moves: Tigard MU-CBD only, GREEN to not-GREEN (alley or park lots, or an unstated park
line). Canby and Gladstone: none.
