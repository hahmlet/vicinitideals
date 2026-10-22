# Design districts inventory — FLATS (2026-10-21)

Read-only research. Nothing in the repo was changed. The full per-district detail, with quotes and file#line citations, is in §2–§5 below. Those are the four regional agents' files, verbatim. Doc paths are relative to `flats/provenance/docs/`.

**Lot counts.** These come from `data/flats/coverage.csv` (2026-10-01), summed by zone, unless a row says otherwise. Gresham's design-district counts are different: they come from a July point-in-polygon of `data/quadfit/s2_lots.parquet` against Gresham Planning MapServer layer 11 (Design Districts). I downloaded that layer to `scratchpad/gis/gresham_dd_{8,9,10,12,13}.geojson`. Lots inside each district: Corridor 3,624 · Downtown 1,108 · Rockwood 789 (SC 480, RTC 278, SC-RJ 31) · Civic 224 · Springwater 199 · Pleasant Valley 76.

**Totals.**
- 84 districts in screened jurisdictions, plus 3 in Lake Oswego, which is switched off.
- 62 reach the pod in at least one form. 8 are unclear. 14 do not reach it, because they are exempted or the zone refuses the use.
- Most of the 62 are zone chapters that FLATS already encodes. The real gaps are the FG and FR rows below.
- 32 districts that are not simply a zone have no boundary. About 10 more lack a sub-area figure.

**Column key.**
- **Reach Q/T:** Q is a quadplex on one lot; T is townhouses on unit lots. Y reaches, N does not, ? unclear, R pod refused by the zone, – not applicable (Tigard screens the pod as rowhouses only).
- **Bnd** (boundary): Z the zone itself, H held (drawn area, OVRLY letters, or a measured fact), M missing, P partly held.
- **Risk:** FG possible false GREEN; FR false RED or over-hold; – none.

## 0. Full table

| # | Jurisdiction | District (§) | Reach Q/T | Screenable highlights | Bnd | FLATS today | Lots | Risk |
|---|---|---|---|---|---|---|---|---|
| 1 | Gresham | 7.0420(J)(1) plex frontage in Downtown/Rockwood/Civic/Corridor | Y/N | ≥50% of site frontage occupied by building between min and max setback | Z | axis_required on 8 zones; MDR-12/24/OFR fixed in run 81 | 613 (fixed) | done |
| 2 | Gresham | Rockwood Design District 7.0500 | N/Y | Townhouse track: max front 20; façade ≥50%; rear/alley parking; 18 ft approach; ≤12 ft garage. The 3-storey gateway and Triangle build-to rules exclude townhouses | H (drawn) | Hold fact `rockwood_design_district` plus card nothing_here. The hold cites text that exempts quadplexes | 789 inside (July) | FR (over-hold on SC/SC-RJ quadplexes) |
| 3 | Gresham | Rockwood Town Center Mixed-Use Area (Table 4.0420 note 3) | R/Y | Ground-floor non-residential on lots with ≥100 ft on Stark within 500 ft of 181st/187th | M (Appendix 9.000) | dismissed | part of RTC 254 | – until the RTC townhouse form opens |
| 4 | Gresham | Central Rockwood Plan Area (Table 4.0430 note 10) | N/N | Min FAR applies to non-residential only | M | dismissed | ? | – |
| 5 | Gresham | Corridor Design District | Y/? | Reaches through #1; 7.0100 not stored | Z (+ layer 11) | card other_building | 3,624 (July) | – after #1 |
| 6 | Gresham | Downtown Plan District 4.1100 | N (4.1152) / Y except DRL | 75% commercial first floor on N Powell, N Main, NE 3rd; street types | Z | cards say "never". DMU/DEM/DCL are townhouse-only and not opened | 1,026 | FR (224 townhouse-only) |
| 7 | Gresham | Civic Neighborhood 4.1200 | R/Y | 4.1252 not itemised | Z | quadplex false; card "never" | 154 | FR (townhouse-only) |
| 8 | Gresham | Gresham Butte 4.1300 | prohibits both | Use prohibited | Z | RED | 93 | – |
| 9 | Gresham | Pleasant Valley 4.1400 | Y/Y | HDR-PV height transition 35 ft | Z | encoded | 1,108 | – |
| 10 | Gresham | Springwater 4.1500 | Y/? | Master plan for VC-SW and the THR-SW land east of it | Z (sub-area M) | encoded; THR-SW is townhouse-only and not opened | 153 + THR-SW 200 | FR (THR-SW) |
| 11 | Fairview | Fairview Village 19.110–19.155 | Y/Y | Entries face the street; alley-only garages; no flat roofs, min 4:12 pitch (VSF/VTH) | Z | encoded; 19.145 left out | 254 | FG if the pod's roof is flat |
| 12 | Fairview | Halsey Storefront District 19.65.030 | N/Y | ≤50% ground-floor residential; max front 10 | M (Figure 19.65.030(B)) | TCC mixed-use variant | part of TCC 47 | – |
| 13 | Fairview | RM/TOZ townhouse overlay | ?/Y | Height 35 | Z? | encoded | 290 | – |
| 14 | Troutdale | Town Center Overlay (Ch 3) | Y/Y | HDR(TC) permits the quadplex; TC dimensions per 3.235; no parking minimum in or near the TC | M (Troutdale City_GIS) | HDR treated as excluded ("369 lots") | HDR 347, MDR 801, MU 163 | FR |
| 15 | Wood Village | Town Center 235 | ?/? | Street-type standards (Table 235-5, not stored); open space 20% | Z (street types M) | TC quadplex true; street-type diagram unread | 167 | FG (unread text under GREENs) |
| 16 | Wood Village | NC Halsey 230.390 | R/R | – | Z | RED | 60 | – |
| 17 | Portland | Centers Main Street "m" 33.415 | Y/Y | Min FAR (encoded); attached houses banned within 100 ft of a transit street; 70% of façade at max setback (Inner); vehicle areas ≤30/50% of transit frontage; active use from 2029 | H (OVRLY m) | min FAR only (`flats/geom/pdx_overlays.py`) | 1,628 went RED on FAR; the rest ? | FG (townhouse form) |
| 18 | Portland | Design overlay "d" 33.420 | ?/? | Text not stored (33.420, 33.218) | H (OVRLY d, unread) | `flats/config/dlcd_read.yaml#L1213` says d lots "now YELLOW"; no code does this | ≥5,636 (zones that always carry d) | FG (unverified) |
| 19 | Portland | Historic/Conservation Districts 33.445 | Y/Y | New construction needs historic resource review, which is discretionary. Conservation Districts allow Community Design Standards as an alternative | P (resource polygons carry DistName) | only protected resources are RED; vacant or non-contributing lots get no flag | ? | FG (should be YELLOW) |
| 20 | Portland | Plan districts 33.500–33.597 | ?/? | Text not stored; plan districts supersede base and overlay zones (33.700.070.E) | M (plan-district layer) | never mentioned | ? | FG (unknown) |
| 21 | Clackamas uninc | Clackamas Regional Center 1005.07 | Y/Y | Design-plan conformance, mostly not screenable | M (Maps X-CRC-1/3/7a) | never mentioned | ~232 | low |
| 22 | Clackamas uninc | Regional Center 1005.08 | Y/Y | No internal streets or driveways between building and street | M (X-CRC-1) | never mentioned | part of 232 | low (zones already YELLOW) |
| 23 | Clackamas uninc | Fuller Rd Station Community 1005.09 (SCMU) | Y/Y | Min height 20; frontage by street type; 50% building frontage | Z (street types M, Map 1005-1) | partly encoded; YELLOW | 36 | – |
| 24 | Clackamas uninc | PMU 1005.10 | R/R | – | Z | RED | 19 | – |
| 25 | Clackamas uninc | Sunnyside Village 1005.11 | Y/Y | Street-facing entries; garage 20 ft back and recessed; garage ≤10 ft wide; lots on an alley take no street garage access | Z | 1005.11 never mentioned; VR57/VR45 encoded | ~1,307 | FG |
| 26 | Clackamas uninc | Design types (Centers / Station / Corridor) 1005.03(I)(9) | ?/? | Judgement only | M | never mentioned | ? | – (YELLOW at most) |
| 27 | Clackamas uninc | Government Camp 1005.12 | N/N | – | Z | nothing_here | 58 | – |
| 28 | Milwaukie | Downtown DMU 19.304 / 19.508 | R/Y | Min height 25; max front 10; 50–90% frontage | Z (Figure 19.304-2 M) | never GREEN | 120 | – |
| 29 | Milwaukie | Central Milwaukie GMU 19.303 | CU/Y | Max setback 20/10; 50% frontage on the figure's block faces | Z (figures M) | YELLOW at best | 46 | – |
| 30 | Milwaukie | North Milwaukie Innovation Area 19.312 | R/R | – | Z | RED | 149 | – |
| 31 | Milwaukie | Flex Space overlay 19.404 | N/N | – | – | nothing_here | ? | – |
| 32 | Happy Valley | Rock Creek PMU 16.31 | R/R | – | Z | RED | 2 | – |
| 33 | Happy Valley | Eagle Landing 16.23.010.D | R/R | – | Z | encoded | 21 | – |
| 34 | Happy Valley | Town Center Plan Area | Y/Y | No parking minimum within ¼ mile (a relaxation) | M (check the ZOVER field) | not encoded (conservative) | ? | FR (small) |
| 35 | Oregon City | Park Place Concept Plan 17.21 | Y/Y | A footprint over 1,200 sf needs secondary masses of ≤600 sf, which the pod fails; detached side/rear garages; 3 ft path | M (maps.orcity.org) | never mentioned | ? | FG |
| 36 | Oregon City | South End Concept Plan 17.22 | Y/Y | Same massing rule; detached alley garage; porch | M | never mentioned | ? | FG |
| 37 | Oregon City | Thimble Creek Concept Plan | Y/Y | Southern-edge strip only: quadplex lot 7,000; 40 ft setback | M | "geographic, not encoded" | part of R-5 18 + R-2 624 | FG (strip only) |
| 38 | Oregon City | Historic overlay 17.40 (Canemah, McLoughlin, Barlow Rd) | Y/Y | New construction needs a certificate of appropriateness (hearing) | M (city's special zoning map) | never mentioned | ? | FG (should be YELLOW) |
| 39 | Oregon City | MUD downtown design sub-district 17.34 | Y/R | Inside the sub-district: coverage 95, landscaping 5 (looser) | M | composite of both, takes the tighter | 278 | FR (small) |
| 40 | Oregon City | Willamette Falls Downtown 17.35 | Y/R | Min FAR 1.0; two full storeys and 25 ft | Z | encoded | 4 | – |
| 41 | Oregon City | Historic Commercial 17.26 | R/R | – | Z | encoded | 37 | – |
| 42 | Gladstone | Town Center (R-5/C-3) | Y/Y | Front and street-side setbacks 10 (vs 20); no parking minimum | M (Parking Exception Map) | read, not encoded | part of R-5 1,148 | FR |
| 43 | Gladstone | Portland Avenue C-2 | Y/Y | Entrance faces Portland Ave; max front 5; no front parking | H (measured fact) | encoded | 148 | – |
| 44 | Canby | Downtown Canby Overlay 16.41 (TC nodes) | Y/Y (TC only) | Build-to 60%; max setback 15; FAR 0.4; no front parking | M (Figure 11) | C-1 refused (known false RED) | small | FR |
| 45 | Canby | North Redwood Plan District | ?/? | Subdivision-level only | M | never mentioned | ? | – |
| 46 | Sandy | Bornstedt Village Overlay 17.54 | Y/Y | Row-house average lot width 20–30 ft, which fails the townhouse form; boulevard access; lots under 40 ft frontage take access from an alley | M (zoning map "S") | not held | part of R1–R3 1,961 | FG (townhouse form) |
| 47 | Sandy | Downtown / Village Commercial 17.90.110 | R/R | – | Z | refused | ? | – |
| 48 | Estacada | Downtown D 16.26 | Y/? | Setbacks 0 min / 5 max; min density 16; no ground-floor residential on Broadway, Main or OR 224 | Z? (D spelling unconfirmed) | refused; FOLLOWUPS 53(f) | ? | FR |
| 49 | Estacada | Mill Area MMU | R/R | – | Z | refused | ? | – |
| 50 | West Linn | Willamette Historic District Ch 25 | Y/Y | 35 ft width cap (the pod fails); roof ≥6:12; front = block average | H (drawn) | drawn and measured | 71 | – (the model case) |
| 51 | West Linn | Willamette Falls Dr Commercial Ch 58 | N/? | Text not stored | M | dismissed | ? | – |
| 52 | West Linn | MU Ch 59 | Y/Y | Max front 20; FAR 0.40; min FAR 0.30 not encoded | Z | encoded | 25 | – |
| 53 | Tualatin | Central Tualatin Overlay Ch 58 | Y/Y | Sub-district density and lot sizes by block | P (Residential Sub-District drawn) | CC drawn; RH blocks deferred; CO Block 1 townhouse use never mentioned | CC 155 (91 inside), CO 46 | FR (CO Block 1) |
| 54 | Wilsonville | Villebois V 4.125 | Y/Y | Encoded; vacant-lot route fixed in run 82 | Z | encoded | 2,370 | done |
| 55 | Wilsonville | Frog Pond RN 4.127 | N/N | – | Z | RED | 580 | – |
| 56 | Wilsonville | Town Center 4.132 | R/R | – | Z | RED | 60 | – |
| 57 | Wilsonville | Old Town Residential OTR 4.123 | Y/Y | Design Standards Book (not stored) | Z | needs_verification | 103 | – |
| 58 | Wilsonville | Old Town overlay 4.138 | Y/Y | The Design Book controls setbacks, height and coverage | M | dismissed on a section-list argument, which is wrong | at least the OTR share | FG (non-OTR zones) |
| 59 | Wilsonville | Coffee Creek 4.134 | N/N | – | M (not needed) | ruled not reaching | 10 | – |
| 60 | Tigard | Bridgeport Village 18.620 | –/Y | Max front 20; min density 25; no front parking | M (Map 18.620.A) | comment only | part of MUC | FG (small, built out) |
| 61 | Tigard | River Terrace 18.640 | –/Y | No direct Boulevard access; no parking within 40 ft of the Boulevard | M (Maps 18.640.A/B) | not encoded | ? | FG (Boulevard lots) |
| 62 | Tigard | Downtown MU-CBD 18.650 | –/Y | Encoded at the strictest subarea | Z (subareas M) | encoded; MS/99H variant unknown | ? | – |
| 63 | Tigard | Triangle TMU 18.660 | –/Y | Encoded | Z | encoded | ? | – |
| 64 | Tigard | Washington Square RC 18.670 | –/Y | Rowhouses only in the Design Review Subdistrict; 4-storey minimum | M (Map 18.670.A) | `inside_mapped_use_area` holds every MUC/MUR lot at unknown | ? | FR (MUC/MUR outside WSRC) |
| 65 | Cornelius | CMU 18.60 | Y/Y | Setbacks 0 / 10; min height 16; no front parking | Z | use only; lots UNKNOWN | ? | – |
| 66 | Cornelius | Commercial Core 18.65 | Y/Y | Use limited within 50 ft of Adair/Baseline | Z | refused (Steph) | ? | – |
| 67 | Cornelius | Gateway MU 18.75 | R/Y | Covered parking required, which fails the pod | Z (subdistricts M) | unit_lots variant | ? | – |
| 68 | Durham | Multi-Dwelling Design Overlay 2.10 | ?/? | Discretionary | M (applied site by site) | refused | 3 | – |
| 69 | King City | Kingston Terrace 16.114 | Y/Y | Max front 26; main entrance faces the street (not encoded) | Z | encoded | 396 | FG (orientation) |
| 70 | King City | NMU 16.102 | N/? | Not read | Z | refused | 20 | FR? |
| 71 | Sherwood | Old Town overlay 16.162 | Y/Y | Landmarks Board decides; height 40 ft / 3 storeys | H (city layer) | unencodable; base zone missing | 117 | – |
| 72 | Hillsboro | Downtown 12.61 | Y/Y | SCC-DT frontage 50–100%; 2-storey minimum | Z | partly encoded; every Hillsboro zone is YELLOW | ≤2,874 | – (masked by YELLOW) |
| 73 | Hillsboro | Orenco 12.62 | Y/Y | Quadplex lot 7,500 | Z | encoded | 1,534 | – |
| 74 | Hillsboro | AmberGlen 12.64 | Y/Y | No surface parking between façade and street (not encoded) | Z | partly encoded | 176 | – (masked) |
| 75 | Hillsboro | South Hillsboro 12.65 | Y/Y | Townhouse alley access; solar orientation | M (Figure 12.65.930-A) | not encoded | MU-VTC 211 + ? | – (masked) |
| 76 | Hillsboro | Witch Hazel Village South 12.68 | Y/Y | Townhouse alley access; solar orientation | M (Figure 12.68.020-A) | not encoded | ? | – (masked) |
| 77 | Beaverton | Downtown Design District Ch 70 | Y/Y | Min building frontage 50–90% by street type (not encoded); active ground floor; min FAR | Z | setbacks, density and parking encoded | 460 (~150 GREEN) | FG |
| 78 | Beaverton | Multiple Use 20.20 (RC / TC / SC) | Y/Y | 60% of Primary Frontage occupied (60.05.15.6.A, not encoded); min FAR 0.30–0.60 | Z | a "doubt" note only (`beaverton.yaml#L318-L323`) | 1,504 | FG |
| 79 | Beaverton | Cooper Mountain 20.22 | Y/Y | Min FAR 0.4 | Z | encoded | 0 | – |
| 80 | WashCo uninc | Transit Oriented 375 | N (431) / Y | Section 431 design (not stored) decides Type II vs Type III for townhouses | Z | 431 not encoded | 2,412 (~880 townhouse-only) | FG |
| 81 | WashCo uninc | North Bethany 390 | ?/Y | Façade and garage rules | Z | not encoded | 1,419 | low |
| 82 | WashCo uninc | Bonny Slope West 391 | Y/Y | No street stubs or driveways at the rural edge | M | not encoded | small | – |
| 83 | WashCo uninc | Pedestrian Mixed Use 392 (NMU/CCMU) | Y/Y | 50% of frontage occupied (not encoded); outdoor area 250 sf/du | Z | partly encoded | 180 | FG |
| 84 | WashCo uninc | Community Plans / ASC (300-1.1) | Y/Y | Unknown; no plan stored | M (gispub) | not encoded; "a question for Steph" | ≤68,777 | FG (unknown) |
| – | Lake Oswego (off) | Downtown Redevelopment, Lake Grove Village Center, West Lake Grove | – | Not stored | – | switched off | – | – |

## 1. Risk ranking and build order

Two false GREENs are already fixed and live: Gresham 7.0420(J) on MDR-12/MDR-24/OFR (run 81) and Wilsonville V vacant lots (run 82). The rest are ranked by GREENs at risk below.

**Tier 1 — False-GREEN fixes, ranked by GREENs at risk**

1. **Building-frontage share, one new field.** These need a "share of street frontage the building must fill" field, which Gresham's axis_required reading partly covers:
   - Beaverton 20.20 Multiple Use: 60% of Primary Frontage, 1,504 lots. GREENs uncounted, but likely more than Downtown's.
   - Beaverton Downtown Ch 70: 50–90% by street type, ~150 GREENs.
   - WashCo 392 NMU/CCMU: 50% of frontage, 180 lots.
   - King City Kingston Terrace: entrance faces the street, 396 lots.
2. **Portland 33.415.300.B.** Ban attached houses within 100 ft of a transit street in the m overlay. The overlay and transit streets are both held already, so this needs no new data. Add the 70% Inner build-to and the 30/50% vehicle-frontage limits at the same time.
3. **Portland design overlay "d".** Nothing implements the YELLOW claim in dlcd_read.yaml. The OVRLY letters are in the snapshot, covering ≥5,636 lots. Fetch 33.420 and 33.218 to decide whether d is YELLOW or GREEN, then correct the dlcd_read note.
4. **Oregon City.** Park Place, South End and the 17.40 historic districts are never mentioned. The 1,200 sf massing rule fails the pod outright, and the historic hearing means YELLOW. The boundaries must be fetched first.
5. **Portland Historic and Conservation Districts.** Vacant or non-contributing lots need a review flag, YELLOW for Historic Districts. The DistName is already held on the resource polygons.
6. **Smaller items:**
   - Clackamas Sunnyside 1005.11 garage and alley rules (~1,300 lots).
   - WashCo 375 TO townhouse-only districts (~880 lots), which need Section 431 fetched.
   - Wood Village TC street-type table (167 lots).
   - Sandy Bornstedt row-house width.
   - Wilsonville Old Town overlay re-ruling.
   - Tigard River Terrace Boulevard access.
   - Fairview Village and West Linn roof pitch, if the pod has a flat roof. This is a pod question for Steph.

**Tier 2 — False-RED openings**

1. **Gresham townhouse-only zones never opened** (~832 lots): Civic CNTH/CNTM/CNRM 154, Downtown DMU/DEM/DCL 224, Springwater THR-SW 200, RTC 254.
   - These need the Rockwood townhouse track, the 4.1152 and 4.1252 standards, and the Stark ground-floor rule.
   - The gresham.yaml notes at L47-L55 contradict the 7.0512 card on whether a split plat counts as a townhouse, so fix those notes too.
2. **Rockwood hold over-holds SC/SC-RJ quadplex lots** (~510). It cites text that exempts quadplexes.
3. **Troutdale HDR(TC)** (~350 lots). The quadplex is permitted there but treated as excluded, because the boundary is missing.
4. **Tigard Washington Square map.** Drawing Map 18.670.A frees every MUC/MUR lot outside the Washington Square Regional Center.
5. **Small known items:** Estacada D (FOLLOWUPS 53(f)), Canby DCO TC nodes, Tualatin CO Block 1, Gladstone Town Center 10 ft setbacks, Happy Valley Town Center parking, Oregon City MUD sub-district.

**Tier 3 — New boundaries to fetch**

Ordered by the work they unlock:
1. Oregon City concept-plan and historic-overlay layers (maps.orcity.org).
2. Portland plan-district layer, plus the 33.420 and 33.5xx text.
3. Troutdale Town Center Overlay (City_GIS MapServer).
4. Tigard Maps 18.670.A, 18.640.A/B and 18.650.A.
5. Gresham layer 11: Downtown, Civic, Corridor, Springwater and Pleasant Valley. These are already downloaded.
6. Sandy Bornstedt "S" overlay.
7. Wilsonville Old Town overlay.
8. Gladstone Town Center.
9. Canby Figure 11.
10. Hillsboro South Hillsboro and Witch Hazel Village South figures. Low priority, because Hillsboro is all YELLOW.
11. WashCo community plan / Area of Special Concern layers. This is the largest unknown; ask Steph first.

---


## 2. Detail — dd_multnomah_east.md

### Design districts — Multnomah east (Gresham, Fairview, Troutdale, Wood Village, Maywood Park, Multnomah unincorporated)

Paths are relative to `flats/provenance/docs/` unless they start with `flats/` or `data/`.
Lot counts come from `data/flats/coverage.csv` (as of 2026-10-01), summed by zone.

## Definitions that decide reach (Gresham)

- Quadplex: "Middle housing quadplex units that have been divided onto individual lots through a Middle Housing Land Division are considered a quadplex" (`or/multnomah/gresham/3.0100.definitions.txt#L962`).
- Townhouse: "A dwelling unit on its own lot, constructed in a row of two or more attached units..." (`3.0100.definitions.txt#L952`).
- Design District has six members (`3.0100.definitions.txt#L826-847`):
  - Civic = CNPD lands.
  - Corridor = "CMF, CMU, MC, CC ... MDR-12, MDR-24, OFR ... that are not included in another Design District" (`#L834-837`).
  - Downtown = DPD.
  - Pleasant Valley = TC-PV, MDR-PV, HDR-PV (`#L841`).
  - Rockwood = RTC, SC along MAX, SC-RJ (`#L843`).
  - Springwater = VC-SW and THR-SW east of the VC (`#L846`).
- So in Gresham's text, a divided quadplex stays a quadplex. The townhouse form only arises when the plat is a townhouse plat rather than a middle-housing land division.
- Steph's ruling `2026-10-15-townhomes-separate-lots` (`flats/config/rulings.yaml#L926-970`, scope `{}`) says: "'Townhomes' will have separate lots. If we build a 4 unit apartment building, they would not." Under that ruling FLATS screens both forms.
  - It opened Fairview VTH, Clackamas R-2.5, Troutdale HDR and MU-1.
  - **It opened no Gresham zone.** See surprise 2.

---

## Gresham

### Gresham — 7.0420(J) plex frontage rule, Downtown/Rockwood/Civic/Corridor (7.0420(J)(1))
- Cite: `or/multnomah/gresham/7.0400.middle-housing-design.txt#L410`
- Kind: overlay. It is a city-wide chapter, but this subsection is bounded by design district, so it counts here.
- Zones covered: 7.0420 applies in "LDR-GB, LDR-5, LDR-7, TR, TLDR, MDR-12, MDR-24, OFR, LDR-PV, MDR-PV, HDR-PV, VLDR-SW, LDR-SW, CMF, CMU, SC, SC-RJ, DCC, DMU, DTM, DRL-1, and DRL-2" (`#L164-168`). Of those, (J)(1) bites only in the zones inside the Downtown, Rockwood, Civic or Corridor district: MDR-12, MDR-24, OFR, CMF, CMU, SC, SC-RJ, DCC, DMU, DTM, DRL-1, DRL-2. The quadplex is permitted in each of those where FLATS has quadplex_allowed true.
- Reach (quadplex): reaches — "The following additional design standards shall apply to single detached dwellings and plexes in the Downtown, Rockwood, Civic, and Corridor Design Districts: a. A minimum of 50 percent of the site's frontage shall be occupied by buildings oriented to the abutting street. Building frontage shall be measured by the length of the building present between the minimum and maximum front setback" (`7.0400.middle-housing-design.txt#L410-418`)
- Reach (townhouse unit lots): no — the rule names "single detached dwellings and plexes" only (`#L410`). Townhouses fall under 7.0431. Its (J)(2) applies to CMF, CMU, TC-PV and NC-PV townhouses, with a maximum of 5 attached (`#L598-625`), and it has no 50% frontage rule.
- Screenable:
  - frontage occupied by street-oriented building ≥ 50% of site frontage, measured between min and max front setback (`#L412-418`)
  - Non-screenable: 2 (façade articulation (J)(1)(b); banned materials (J)(1)(c))
- Boundary: have, via zones. Corridor membership is defined by zone (`3.0100.definitions.txt#L834`). Rockwood is drawn (see below), and Downtown is the D-zones.
- FLATS today: encoded as `orientation_constraint: axis_required` on DRL-1 (`flats/config/jurisdictions/or/multnomah/gresham.yaml#L4636-4650`), DRL-2 (`#L4805`), DCC (`#L4978`), DTM (`#L5142`), CMF (`#L5385`), SC (`#L5537`), SC-RJ (`#L5676`) and CMU (`#L5805`). **Not encoded on MDR-12 (`#L3819`), MDR-24 (`#L3997`) or OFR (`#L4202`).** All three have quadplex_allowed true and a front-setback maximum (Table 4.0131 note 7, `4.0400.corridor.txt#L351-356`), so the band the rule measures exists. I found no note or card that rules these three out.
- Lots: 613 missing the rule (MDR-12 408, MDR-24 180, OFR 25). Zones that have it: DRL-1 78, DRL-2 202, DCC 300, DTM 222, CMF 671, SC 331, SC-RJ 31, CMU 301.
- Note: **Likely false-GREEN gap on 613 lots.** MDR-12, MDR-24 and OFR are Corridor Design District zones by definition. The only exception is the share inside Rockwood, which is still in a named district.

### Gresham — Rockwood Design District (7.0500)
- Cite: `or/multnomah/gresham/7.0500.rockwood-design.txt#L33`
- Kind: overlay
- Zones covered: RTC, SC (along MAX), SC-RJ by definition (`3.0100.definitions.txt#L843`). The drawn polygon also cuts CC, CMF, CMU, MC, MDR-12, MDR-24 and OFR (`gresham.yaml#L6213-6228`).
  - Table 4.0420 (`4.0400.corridor.txt#L148-149`) for RTC SC SC-RJ CMF CMU CC MC: Quadplex "NP P P P P NP NP"; Townhouse "L3 P P P P NP NP".
  - So the quadplex is NOT permitted in RTC, CC or MC.
- Reach (quadplex): no — "Section 7.0501-7.0512 do not apply to: • Single detached dwellings, duplexes, triplexes, and quadplexes (for these developments, see Section 7.0420)." (`7.0500.rockwood-design.txt#L44-45`). A divided quadplex is still a quadplex (`3.0100.definitions.txt#L962`).
- Reach (townhouse unit lots): reaches, for a townhouse plat — 7.0502(A) lists "Townhouses" (`#L33-38`). The standards carry a separate "Townhouse: Townhouse and, where noted, Townhouse Style" track (`#L222`).
  - The gateway rule and the Triangle build-to lines sit under "All Development: All developments, except townhouses and the industrial uses permitted in ... SC-RJ ..." (`#L213-218`). **So they reach neither form.**
  - Gateway B.6.S1: masses at 181st/Burnside, 181st/Stark and Burnside/Stark "shall be no less than 3 stories in height ... three-story mass shall extend no less than 60 feet along each street frontage" (`#L3431-3462`).
  - Triangle build-to lines: Stark 0–5, 181st 0–5; Burnside, Pine, Oak, 185th, 187th, Ash and future 182nd/183rd 10–15 (`#L524-539`).
- Screenable (townhouse track):
  - front setback min per Table 4.0430 fn 1; max front setback 20 ft, inside and outside the Triangle (`#L577-580`)
  - building façades ≥ 50% of street frontage for multi-family, townhouse and townhouse style (`#L624-626`); the 90%/75% Triangle figures are commercial only (`#L612-618`)
  - lots abutting an alley take auto access from the alley (`#L1189`)
  - driveway approach ≤ 18 ft or 34% of frontage (`#L1199-1201`)
  - each townhouse lot ≥ 15 ft of street frontage, one approach, parking ≤ 12 ft wide, garage ≤ 12 ft wide (`#L1220-1235`)
  - parking rear only with a single consolidated driveway; corner lots take access from the side street (`#L1241-1258`)
  - no auto areas between building and street, except individual townhouse driveways (`#L936-941`)
  - ≤ 8 townhouse units in a continuous row (`#L2435`); the pod's 4 passes
  - townhouse sites ≥ 2.5 ac go to 7.0451 (`#L1698`)
  - parking-area landscaping 15% (`#L1833`)
  - 7.0431 is exempted inside Rockwood (`#L173`)
  - Non-screenable: ~110 (of about 122 numbered S-standards; an approximate count)
- Boundary: have — `flats/config/areas/or/multnomah/gresham/rockwood-design-district.geojson`, EPSG:2913, from Gresham Planning MapServer layer 11 (Design Districts), Name=Rockwood, fetched 2026-10-08. The drawn_areas block is at `gresham.yaml#L6213-6228`.
- FLATS today: drawn and measured, plus a hold.
  - Footnote `flats/config/footnotes/or/multnomah/gresham.yaml#L729-736` has `state: unmeasured`, `fact: rockwood_design_district`, and says "inside the Rockwood Design District the front setbacks come from Section 7.0512.A.2 rather than from this table".
  - The ConditionDef is at `flats/rules/conditions.py#L860-873`; DRAWN_CONDITIONS is at `#L1113-1116`; the flag is `FACT-ROCKWOOD-DESIGN-DISTRICT` (`flats/config/flags.yaml#L1121-1135`).
  - Chapter card `gresham.yaml#L968-1009` ("7.0500.rockwood-design.txt#7.0512") has outcome nothing_here.
- Lots: core zones 616 (RTC 254 + SC 331 + SC-RJ 31), plus an unknown share of CC 165, CMF 671, CMU 301, MC 248, MDR-12 408, MDR-24 180, OFR 25. The card's "28,873 lots behind it" equals all of Gresham (coverage sum 28,882), not the district.
- Note: **gresham.yaml contradicts itself.**
  - The early notes (`#L47-55`) say the rule "reaches the split plat" and that the Triangle bands apply.
  - The card (`#L979-983`) says a split plat is still a quadplex.
  - The RTC zone block (`~#L5863`) screens the split plat as a townhouse.
  - The hold cites front-setback rules that, for quadplexes, are exempt and, for the All-Development track, exclude townhouses. It may cost the quadplex form nothing real. It does matter for the townhouse form (max 20 ft).

### Gresham — Rockwood Town Center Mixed-Use Area (Table 4.0420 note 3)
- Cite: `or/multnomah/gresham/4.0400.corridor.txt#L219`
- Kind: overlay (a mapped sub-area of RTC)
- Zones covered: RTC. Quadplex NP; Townhouse L3, the cell that carries this note (`4.0400.corridor.txt#L148-149`).
- Reach (quadplex): no — the quadplex use is not permitted in RTC (`#L148`).
- Reach (townhouse unit lots): reaches — "Within the area identified on the Appendix 9.000 map ... all buildings on parcels with at least 100 feet of frontage on Stark that are within 500 feet of the center lines of the intersections of Stark and 181st or 187th Avenues shall have non-residential uses at the ground floor frontages" (`#L219-222`)
- Screenable:
  - ground-floor non-residential required where Stark frontage ≥ 100 ft and the lot is within 500 ft of Stark/181st or Stark/187th (`#L219-222`)
  - Non-screenable: 0
- Boundary: missing — likely source is the Appendix 9.000 map. The intersection-distance test can be computed from centrelines.
- FLATS today: dismissed — "marks a cell in a district this layer does not encode" (`flats/config/footnotes/or/multnomah/gresham.yaml#L405-409`); RTC notes are at `gresham.yaml#L5938`.
- Lots: unknown (a subset of RTC 254)
- Note: this only matters once RTC's townhouse form is opened.

### Gresham — Central Rockwood Plan Area (Table 4.0430 note 10)
- Cite: `or/multnomah/gresham/4.0400.corridor.txt#L458`
- Kind: plan district (shown on Appendix 39, Figure 1)
- Zones covered: CMU, CC, MC (minimum FAR 0.4, `#L313-315`)
- Reach (quadplex): no — "The minimum floor area ratios contained in Table 4.0430 apply to non-residential and mixed-use development" (`#L513`)
- Reach (townhouse unit lots): no — same quote (`#L513`)
- Screenable: min FAR 0.4, non-residential and mixed-use only (`#L313-315`). Non-screenable: 0
- Boundary: missing — Appendix 39 Figure 1
- FLATS today: dismissed (`flats/config/footnotes/or/multnomah/gresham.yaml#L612-616`)
- Lots: unknown
- Note: no action. Table 4.0430 note 18 sets the townhouse minimum height at 1 storey in CMU/CMF and 2 storeys elsewhere (`#L492-497`); the pod passes. Note 12 sets the Rockwood heights and gateways (`#L465-479`).

### Gresham — Corridor Design District (7.0100 / 3.0100)
- Cite: `or/multnomah/gresham/3.0100.definitions.txt#L834`
- Kind: overlay (defined by zone)
- Zones covered: CMF, CMU, MC, CC, MDR-12, MDR-24 and OFR outside other districts. Quadplex P in CMF and CMU, NP in CC and MC (`4.0400.corridor.txt#L148`); P in MDR-12, MDR-24 and OFR (FLATS quadplex_allowed true).
- Reach (quadplex): reaches through 7.0420(J)(1) (block above). For 7.0100, "Design standards in Section 7.0400 for duplexes, triplexes, quadplexes, and townhouses, and in Section 7.0100 for new construction ..." (`4.0400.corridor.txt#L99-100`). Table 4.0435 applies 7.0112 to "New multi-family residential and mixed-use (residential) development in any district" (`#L567-588`). Multi-family means 5+ units, so 7.0100 itself likely does not reach the pod. This is unclear because 7.0100 is not in the store (`flats/config/dlcd_read.yaml#L737-749`).
- Reach (townhouse unit lots): unclear — 7.0100 is not stored. 7.0431(J)(2) reaches CMF/CMU townhouses with a maximum of 5 attached (`7.0400.middle-housing-design.txt#L598-625`).
- Screenable: see the 7.0420(J) block. Non-screenable: unknown (7.0100 is not stored)
- Boundary: have via zones; also probably Planning MapServer layer 11
- FLATS today: chapter card "7.0100", outcome other_building (`gresham.yaml#L1571-1577`)
- Lots: CMF 671 + CMU 301 + MC 248 + CC 165 + MDR-12 408 + MDR-24 180 + OFR 25 = 1,998, minus the Rockwood share
- Note: the store needs 7.0100 before the townhouse form can be closed.

### Gresham — Downtown Plan District (4.1100)
- Cite: `or/multnomah/gresham/4.1100.downtown.txt#L60`
- Kind: zone-chapter (DCC, DMU, DTM, DEM, DRL-1, DRL-2, DCL)
- Zones covered: Table 4.1120 (`#L239-246`) gives Quadplex "L1 NP L1 NP P P NP" and Townhouse P in all seven. In FLATS, DCC and DTM have quadplex false at base, with a variant [inside_mapped_use_area, narrow_frontage] at ≤ 7,600 sf (`gresham.yaml#L4826-4844`).
- Reach (quadplex): no for 4.1152 — "Single detached dwellings, duplexes, triplexes, and quadplexes (for these developments, see Section 7.0420)" (`4.1100.downtown.txt#L67`). It does reach through 7.0420(J) (above).
- Reach (townhouse unit lots): reaches outside DRL — 4.1152 applies to "Townhouse Developments, except as provided below" (`#L60-65`). The exception is "Townhouses in the DRL-1 and DRL-2 sub-districts" (`#L68`).
- Screenable:
  - required first-floor uses: 75% commercial within 40 ft on north Powell (Miller–Roberts), N Main (Powell–NE 4th) and NE 3rd (`#L366-372`)
  - street-type standards per the Street Types Map (4.1142); the 4.1142(B)(7) curb-cut gate is inert only because Gresham requires no parking (`gresham.yaml#L886-932`)
  - Non-screenable: unknown; 4.1152 counted only roughly
- Boundary: have — the D-zones. The street-type and first-floor-use streets are named in text.
- FLATS today: encoded zones. Cards `gresham.yaml#L848-885` (4.1152, never), `#L886-932` (4.1100, never) and `#L690-711`. First-floor uses dismissed with a "re-read if green" caveat (`flats/config/footnotes/or/multnomah/gresham.yaml#L1709-1721`).
- Lots: DCC 300, DTM 222, DRL-2 202, DCL 152, DRL-1 78, DMU 42, DEM 30 = 1,026
- Note: the "never" cards assume the split plat is a quadplex. DMU, DEM and DCL are townhouse-only for the pod (224 lots) and not opened.

### Gresham — Civic Neighborhood Plan District (4.1200)
- Cite: `or/multnomah/gresham/4.1200.civic-neighborhood.txt#L65`
- Kind: zone-chapter (CNTH, CNTM, CNRM)
- Zones covered: Quadplex NP in all three, Townhouse P in all three (`#L196-202`; quadplex row `#L200`)
- Reach (quadplex): no — use not permitted (`#L200`)
- Reach (townhouse unit lots): reaches — "Section 4.1252 shall apply to: ... • Townhouses" (`#L65-69`)
- Screenable: 4.1252 not itemised (unclear); Non-screenable: unknown
- Boundary: have — zones
- FLATS today: encoded quadplex_allowed false; card `gresham.yaml#L933-965`, outcome never
- Lots: CNTH 33 + CNTM 108 + CNRM 13 = 154
- Note: townhouse-only zone, not opened by the 2026-10-15 ruling.

### Gresham — Gresham Butte Plan District (4.1300)
- Cite: `or/multnomah/gresham/4.1300.gresham-butte.txt#L31`
- Kind: plan district (overlay on LDR, coded LDR/GB)
- Zones covered: LDR/GB
- Reach (quadplex): reaches as a prohibition — "the Gresham Butte Plan District specifically prohibits: 1. Triplexes; 2. Quadplexes; 3. Townhouse" (`#L31-34`)
- Reach (townhouse unit lots): reaches as the same prohibition (`#L34`)
- Screenable: use prohibited (`#L31-34`); side yard 10 ft (`#L68-69`); sprinklers (`#L70-72`). Non-screenable: 0 relevant
- Boundary: have — zone code LDR/GB; the source map is Appendix 41 (`#L17-19`)
- FLATS today: encoded red (zone)
- Lots: 93
- Note: none.

### Gresham — Pleasant Valley Plan District (4.1400)
- Cite: `or/multnomah/gresham/4.1400.pleasant-valley.txt#L251`
- Kind: zone-chapter (LDR-PV, MDR-PV, HDR-PV, TC-PV, NC-PV, ME-PV)
- Zones covered: quadplex permitted in LDR-PV, MDR-PV, HDR-PV; NP in TC-PV, NC-PV, ME-PV (`#L512-514`)
- Reach (quadplex): reaches through 7.0400, which the chapter sends plexes to (`#L251-255`). 7.0420(J) does not name Pleasant Valley (`7.0400.middle-housing-design.txt#L410`).
- Reach (townhouse unit lots): reaches through 7.0431(J)(2) for TC-PV and NC-PV, max 5 attached (`7.0400.middle-housing-design.txt#L598-625`)
- Screenable: HDR-PV next to LDR-PV height transition 35 ft (`#L426-432`); neighbourhood amenities for sites ≥ 2.5 ac (`#L435-444`). Note 7 sends 7.0112 to multi-family only (`#L360`). Non-screenable: few (unclear)
- Boundary: have — zones
- FLATS today: encoded zones
- Lots: LDR-PV 694 + MDR-PV 340 + HDR-PV 74 = 1,108
- Note: TC-PV borrows Rockwood open space only for commercial over 20,000 sf (`#L724`, `#L751`).

### Gresham — Springwater Plan District (4.1500)
- Cite: `or/multnomah/gresham/4.1500.springwater.txt#L145`
- Kind: zone-chapter (VLDR-SW, LDR-SW, THR-SW, VC-SW, ...)
- Zones covered: Quadplex "P P NP" in VLDR-SW, LDR-SW, THR-SW (`#L145`); VC-SW NP (`#L440`)
- Reach (quadplex): reaches through 7.0420 and 7.0431, which 4.1510 sends there (`#L361-366`)
- Reach (townhouse unit lots): unclear — THR-SW permits townhouses but not the quadplex; Master Plan text not itemised
- Screenable: a Master Plan is required for VC-SW and the THR-SW next to it on the east (`#L813-834`), not a lot-level test; park overlays 4.1562/4.1563 (`#L855+`). Non-screenable: unclear
- Boundary: have — zones; the Master Plan sub-area is missing
- FLATS today: encoded zones
- Lots: VLDR-SW 48 + LDR-SW 105 = 153 quadplex-eligible; THR-SW 200 townhouse-only
- Note: THR-SW is townhouse-only and not opened.

---

## Fairview

### Fairview — Fairview Village (19.110–19.155)
- Cite: `or/multnomah/fairview/19.110.txt#L35`
- Kind: zone-chapter and master plan (VSF, VTH, VA, VO, VC, VMU)
- Zones covered: area "east of the NE 207th Connector, south of NE Halsey Street, north of NE Glisan Street, and west of NE 223rd Avenue as illustrated in Figure V-1" (`#L35`). Village rules control in a conflict (`#L141`).
  - VSF quadplex true through R-6's list (`19.115.txt#L21-25`; `flats/config/jurisdictions/or/multnomah/fairview.yaml#L2829-2836`).
  - VTH quadplex false; opened as townhouses on 2026-10-15.
  - VA, VO, VC and VMU false.
- Reach (quadplex): reaches — 19.145 applies in "VSF/VTH/VA" (`19.145.txt#L17`)
- Reach (townhouse unit lots): reaches — same (`19.145.txt#L17`)
- Screenable:
  - entries face a public street (`19.145.txt#L25`)
  - "On lots that abut alleys, automobile access to garages shall be exclusively from the alley" (`#L77`)
  - landscaping 25% in VTH/VA (`#L65`)
  - flat roofs not permitted in VSF/VTH; minimum pitch 4:12 (`#L45`); this bears on the pod's roof form
  - Non-screenable: ~3 (porches on every other unit `#L29`, materials, detailing)
- Boundary: have — zones (V-codes)
- FLATS today: encoded zones. The notes leave the building-shaped 19.145 standards out (`fairview.yaml#L2754-2767`, `#L2969-2976`).
- Lots: VSF 161 + VTH 93 = 254 pod-relevant (VMU 59, VA 8, VC 5, VO 3)
- Note: the 4:12 roof and alley-only garage rules are not screened. The roof rule could rule out a flat-roof pod outright.

### Fairview — Halsey Street Storefront District (19.65.030)
- Cite: `or/multnomah/fairview/19.65.txt#L184`
- Kind: overlay (sub-area of TCC)
- Zones covered: TCC — "Residential uses shall be permitted only when part of a mixed use development" (`#L198-200`)
- Reach (quadplex): no — 19.65.090 covers duplex, triplex and quadplex "developments with more than one building" and 3+ townhomes on their own lots (`#L619-625`). A single-building quadplex is outside it.
- Reach (townhouse unit lots): reaches — same, 3+ townhomes on own lots (`#L619-625`)
- Screenable: ≤ 50% ground-floor residential on Halsey (`#L206`); max front setback 10 ft, with 75% of façade inside the district vs 50% outside (`#L328`). Non-screenable: unclear
- Boundary: missing — Figure 19.65.030(B) (`#L188-190`)
- FLATS today: TCC quadplex false at base, variant mixed_use (`fairview.yaml#L2345-2364`); notes `#L2438-2477`
- Lots: TCC 47 (whole zone; district share unknown)
- Note: low impact.

### Fairview — RM/TOZ Townhouse Overlay (Table 19.30.030.A)
- Cite: `or/multnomah/fairview/19.30.txt#L95`
- Kind: overlay (its own column in the dimensional table, `#L247`)
- Zones covered: RM
- Reach (quadplex): unclear — the column governs height; whether it governs the rest is an open human question
- Reach (townhouse unit lots): reaches (it is a townhouse overlay) — the column at `#L247`
- Screenable: height 35 (`fairview.yaml#L2201-2228`). Non-screenable: 0
- Boundary: have if the zoning layer codes RM/TOZ; otherwise unclear
- FLATS today: encoded (height)
- Lots: 290
- Note: none.

---

## Troutdale

### Troutdale — Town Center Overlay District (Ch. 3)
- Cite: `or/multnomah/troutdale/3.zoning-districts.txt#L226`
- Kind: overlay
- Zones covered: MDR(TC), HDR(TC), MU-1 ("Downtown Mixed-Use (formerly CBD)", `#L79`, `#L537-541`), MU-2.
  - Table 3.120 columns "LDR-1 LDR-2 MDR MDR (TC) HDR HDR (TC)"; Quadplex "P P P P N P" (`#L226-232`), so **HDR inside the TC permits the quadplex**.
  - LDR-1, LDR-2 and CC are "not applicable ... within the Town Center district" (`#L168`, `#L176`, `#L809`).
- Reach (quadplex): reaches as a use enabler and with its own dimensions — the TC columns for MDR(TC)/HDR(TC) differ, HDR(TC) "see 3.235" (`#L284-340`)
- Reach (townhouse unit lots): reaches — Townhouse P in all columns, with TC dimensions (`#L233`, `#L284-340`)
- Screenable:
  - TC dimensional column (setbacks, lot size per 3.235) (`#L284-340`)
  - 3.140 density cap lifted in the TC (`#L413-416`)
  - no off-street parking "within the Town Center Overlay District, including lands within one-quarter (¼) mile from the district boundary line" (`9.parking.txt#L186-191`)
  - Non-screenable: unclear
- Boundary: missing — likely the Troutdale City_GIS MapServer (`flats/config/pipeline.yaml#L271`; zoning is layer 74, so the TCO is probably a neighbouring layer) or the "CFEC Parking Delineated Area Map" (`9.parking.txt#L191`)
- FLATS today: HDR quadplex false, with the note "the GIS zonecode does not distinguish HDR-TC -- treated as excluded (conservative; 369 lots)" (`flats/config/jurisdictions/or/multnomah/troutdale.yaml#~L2125-2127`). HDR opened as townhouses 2026-10-15 (`#L2106-2122`). The card at `#L190-208` says the TC columns are not mapped.
- Lots: HDR 347 (config says 369), MDR 801, MU-1 94, MU-2 69; TC share unknown
- Note: missing boundary hides permitted quadplex lots (conservative, a false RED rather than a false GREEN).

---

## Wood Village

### Wood Village — Town Center (Section 235)
- Cite: `or/multnomah/wood-village/235.410.txt#L62`
- Kind: zone-chapter (TC) and master plan
- Zones covered: TC — Household Living Y (`235.200.txt#L68`)
- Reach (quadplex): unclear — "Parcels must comply with the standards for the street type on which the parcel fronts" (Table 235-5) (`235.410.txt#L62`). Table 235-5 and 235.450 are not in the store.
- Reach (townhouse unit lots): unclear — same
- Screenable: residential height 35, front 10 (Table 235-2, `235.300.txt#L72-73`); street-type standards per Figure 235-1 (5 street types) (`235.410.txt#L62`); development plan open space 20% (`235.465.txt#L60`). Required intersections, gateways and plazas (`235.420.txt#L84-90`) are not lot-screenable. Non-screenable: unknown
- Boundary: have — zone TC. Street types are missing (Figure 235-1, regulating diagram).
- FLATS today: TC quadplex true via the MR 2 `like:`. The notes say the diagram is unreadable and street type is not held (`flats/config/jurisdictions/or/multnomah/wood-village.yaml#L1093-1253`, notes ~`#L1219-1253`).
- Lots: 167
- Note: GREEN TC lots rest on unread street-type standards. Fetch Table 235-5 and 235.450.

### Wood Village — NC Halsey main street (230.390)
- Cite: `or/multnomah/wood-village/230.315.txt#L62`
- Kind: zone-chapter (NC)
- Zones covered: NC — residential "permitted only when part of a mixed use development" (`#L62`); CU
- Reach (quadplex): no — use not permitted by right (`#L62`)
- Reach (townhouse unit lots): no — same (`#L62`)
- Screenable: none relevant. Non-screenable: n/a
- Boundary: have — zone
- FLATS today: use red (`wood-village.yaml#L1030`)
- Lots: 60
- Note: none.

---

## Multnomah unincorporated

### Multnomah — Design Review (39.8000)
- Cite: `or/multnomah/_unincorporated/39.design-review.txt#L43`
- Kind: not a district (use-triggered)
- Zones covered: any base zone
- Reach (quadplex): unclear — "shall apply to all conditional and community service uses, and to specified uses, in any base zone" (`#L43-47`). It is not area-bounded.
- Reach (townhouse unit lots): unclear — same
- Screenable: n/a. Non-screenable: n/a
- Boundary: n/a
- FLATS today: chapter card (`flats/config/jurisdictions/or/multnomah/_unincorporated.yaml#L844-864`)
- Lots: n/a
- Note: listed for completeness only; not a district.

---

## Jurisdictions with no district found

- **Maywood Park** — `flats/config/jurisdictions/or/multnomah/maywood-park.yaml` has `eligible: false` and `zones: {}`. No code is stored under `or/multnomah/maywood-park/`. Its 327 lots are unzoned in the parcel data.
- **Multnomah unincorporated** (beyond 39.8000) — grepped "design district", "overlay", "plan district", "town center", "main street", "subarea", "do not apply":
  - 33.418 is Constrained Sites, a hazard overlay, so excluded.
  - The PD overlay (39 PD) is opt-in.
  - Orient OR/OCI is a rural centre zone with no design sub-area.
  - The Portland-administered pockets (R20/R10/R7/R5/RF) have no 33.5xx plan district in the store.
- Excluded on purpose: Fairview R/CSP parks overlay 19.108 (quadplex false), 19.105 floodplain, 19.106 natural resources; Gresham hillside/flood/natural-resource overlays.

## Surprises for the coordinator

1. **7.0420(J)(1) is missing on MDR-12, MDR-24 and OFR (613 lots).** These are Corridor Design District zones by definition. The rule reaches the quadplex there and is encoded on the other 8 zones it covers. This is a likely false GREEN.
2. **The townhouse form in Gresham is not opened.** The 2026-10-15 ruling (scope `{}`) opened townhouse-only zones elsewhere but not Gresham's: CNTH/CNTM/CNRM 154, DMU/DEM/DCL 224, THR-SW 200, RTC 254 ≈ 832 lots. 4.1152, 4.1252 and 7.0512 do reach townhouses in exactly those zones. The Gresham "never" cards assume a split plat is a quadplex, which is true only for a middle-housing land division.
3. **The Rockwood gateway (3-storey) and Triangle build-to rules reach neither form**, because both sit under "All Development ... except townhouses". The hold cites text that a quadplex is exempt from, and gresham.yaml's L47-55 notes overstate it.
4. Troutdale's TCO boundary is missing, which hides permitted HDR-TC quadplex lots (conservative). Wood Village's TC street-type table is unread under 167 GREEN-eligible lots. Fairview Village bans flat roofs in VSF and VTH, and FLATS does not screen that.

## 3. Detail — dd_portland_clackamas_north.md

### Design districts — Portland, Clackamas unincorporated, Milwaukie, Happy Valley, Oregon City, Gladstone

Paths are relative to `flats/provenance/docs/` unless they start with `config/`, `geom/` or `rules/` (those are under `flats/`). Lot counts come from `data/flats/coverage.csv` (2026-10-01) and are summed by zone unless stated otherwise.

**Tally:** 28 districts. 17 reach the pod in at least one form, 3 are unclear (their text is not stored or their applicability is not stored), and 8 do not reach it or sit on zones where the pod is not permitted.

---

## Portland

The store holds 33.100–150, 33.266, 33.415, 33.418, 33.445, 33.610, 33.700, 33.910–930 and `amended/ricap11.txt`. **33.420 (Design overlay) and 33.500–33.597 (plan districts) are not stored**, apart from RICAP 11 amendment excerpts. A grep of `config/jurisdictions/or/multnomah/portland.yaml` for "design overlay", "plan district", 33.415 and 33.420 returns nothing.

### Portland — Centers Main Street overlay "m" (33.415)
- Cite: `or/multnomah/portland/33.415.txt#L36-L38`
- Kind: overlay
- Zones covered: CM1, CM2, CM3, CE and others carrying an `m` in OVRLY. The pod is permitted in the base zones.
- Reach (quadplex): reaches — "The regulations of this chapter apply to sites in the Centers Main Street overlay zone." (`#L38`). 33.415.310 applies "for all new development" (`#L80`).
- Reach (townhouse unit lots): reaches, and **prohibits** — "The following development is prohibited within 100 feet of a transit street: ... B. Houses, attached houses, and duplexes." (`#L73-L77`)
- Screenable:
  - minimum FAR = 0.5 Inner / 0.25 Eastern and Western (`#L79-L83`)
  - attached houses prohibited within 100 ft of a transit street (`#L73-L77`)
  - in the Inner area, 70% of the street-facing facade must sit at the base-zone maximum setback (`#L85-L97`)
  - vehicle areas may use at most 30% (Inner) / 50% (Eastern and Western) of any transit-street frontage (`#L99-L110`)
  - ground-floor active use of 25% within 100 ft of a transit street, with residential exempt "until January 1, 2029" (`#L52-L55`)
  - one entrance per 100 ft on transit streets, 33.415.350 (`#L121`)
  - CM1-only add-ons, 33.415.410 (`#L135`)
  - Non-screenable: 1 (ground-floor windows 60%, also residential-exempt until 2029, `#L112`)
- Boundary: have it, as the OVRLY `m` token on `zoning_portland` (`config/pipeline.yaml#L247-L256`; the dataset `overlay_pdx_main_street` is at `#L558`). Pattern areas come from `pdx_pattern_areas` (`#L572`).
- FLATS today: the minimum FAR is encoded and drawn-and-measured in `geom/pdx_overlays.py`. The lot is in the overlay where at least 10% of it is (`#L81`); minimum FAR comes from `MIN_FAR = {"Inner": 0.5, "Eastern": 0.25, "Western": 0.25}` (`#L87`); the reason code is `PDX_MAIN_STREET_MIN_FAR` (`#L104`). **The 33.415.300.B attached-house ban, the 70% build-to and the 30%/50% vehicle-area limit are never mentioned** (no grep hits for 415.300/320/330 in flats/).
- Lots: unknown. FOLLOWUPS 78 moved 1,628 lots from green to red on the minimum FAR alone.
- Note: **Surprise.** The pod as 4 townhouses is outright prohibited on any "m" lot within 100 ft of a transit street, and FLATS does not know this. The 2029 sunset will also switch on the active-use rule for residential.

### Portland — Design overlay "d" (33.420) — text not in store
- Cite: the stored mentions are `or/multnomah/portland/33.120.txt#L121`, `#L128` (RM3, RM4, RX: "The Design overlay zone is applied to this zone") and `33.130.txt#L137`, `#L163` (CX, CM3). The CM2 bonus is tied to the Design overlay at `33.130.txt#L736-L737`. RICAP 11 excerpts: 33.420.045 exemptions and Table 420-2 (`amended/ricap11.txt#L3160-L3200`).
- Kind: overlay
- Zones covered: always RM3, RM4, RX, CM3 and CX, and mapped elsewhere. The pod is permitted in RM and CM.
- Reach (quadplex): unclear — the 33.420 applicability and exemption text is not stored. You would need 33.420.041/.045 in full, plus 33.218 (Community Design Standards, the objective track).
- Reach (townhouse unit lots): unclear — same reason.
- Screenable: unknown (text absent). Non-screenable: unknown.
- Boundary: have it — the OVRLY field carries `d` (`config/pipeline.yaml#L254-L256`: "OVRLY carries overlay letters as text"). Nothing reads it; `has_m` at `geom/pdx_overlays.py#L288` is the only OVRLY reader.
- FLATS today: never mentioned in portland.yaml. `config/dlcd_read.yaml#L1213-L1215` (proposed:Portland:005-26, a design-review suspension to 2029-07-01) claims "design-overlay (d) lots now YELLOW for review", and **I found no code that does this.** Treat the claim as unverified.
- Lots: at least 5,636 (lower bound: the zones where `d` always applies — RM3 1,442 + RM4 498 + RX 253 + CM3 1,651 + CX 1,792).
- Note: fetch 33.420 and 33.218 before any plan. ORS 197A.400's exceptions cover Portland's central city/Gateway, and Steph's 197A ruling excludes Portland.

### Portland — Historic and Conservation Districts (33.445.200 / .210)
- Cite: `or/multnomah/portland/33.445.txt#L812` (Historic District), `#L1242` (Conservation District)
- Kind: historic district
- Zones covered: any. The pod is permitted wherever the base zone allows it.
- Reach (quadplex): reaches — in a Historic District, historic resource review is required for "b. Building a new structure" (`#L872`). The Conservation District text is the same (`#L1290`), but "the Community Design Standards may be used as an alternative" (`#L1283-L1284`; 33.445.500-510, `#L1995-L2035`).
- Reach (townhouse unit lots): reaches — same text.
- Reach in a National Register District: no — "Historic resource review is not required for development within the boundary of a National Register District" (`#L1682-L1683`).
- Screenable: none in the stored text. The objective track is 33.218, which is not stored. Non-screenable: all (review criteria live in 33.846).
- Boundary: partly held. `pdx_historic_resources` (`config/pipeline.yaml#L583`) is per-resource polygons carrying a DistName. District outlines are not read as areas.
- FLATS today: only protected resources are RED (`geom/pdx_overlays.py#L293-L317`; reason `PDX_PROTECTED_RESOURCE`). A vacant or non-contributing lot inside a Historic or Conservation District gets no review flag. A `historic_resource` condition is registered with assume False (`rules/conditions.py` around L357).
- Lots: unknown.
- Note: new construction in a Historic District is discretionary, so it is YELLOW under the 2026-10-14 tiers. A Conservation District might stay GREEN if 33.218 is objective.

### Portland — Plan districts (33.500–33.597) — text not in store
- Cite: the general supersede rule is at `or/multnomah/portland/33.700.txt#L365-L372`: "The regulations in a plan district supersede regulations in overlay zones, base zones..." The only stored excerpt is York, at `amended/ricap11.txt#L3755-L3800`.
- Kind: plan district (around 30 of them: Central City, Gateway, Hayden Island, St Johns, Macadam, Glendoveer, York and others)
- Zones covered: various.
- Reach (quadplex): unclear in general. For York 33.597.135, the required nonresidential use reaches new development on EX sites, but "Lots with houses are exempt" (`ricap11.txt#L3766`). A quadplex is not a house, so York reaches it.
- Reach (townhouse unit lots): unclear. In York, attached houses are probably exempt under "houses", but that needs the definitions.
- Screenable: unknown. RICAP shows Hayden Island heights and FAR (33.532) and York required ground-floor nonresidential use. Non-screenable: unknown.
- Boundary: missing. `BPS_Zoning_Code_Layers` carries a PLDIST field, but only on the environmental polygons (`config/pipeline.yaml#L481-L503`). Likely source: a plan-district layer on Portland Maps `Public/Zoning` MapServer or `BPS_Zoning_Code_Layers` (layer index not known).
- FLATS today: dismissed in the footnote ledger only as a parking-maximum note (`config/footnotes/or/multnomah/portland.yaml#L263-L270`). Otherwise never mentioned.
- Lots: unknown.
- Note: plan districts outrank both overlays and base zones (33.700.070.E). This is the biggest unread layer in Portland.

---

## Clackamas unincorporated (ZDO)

ZDO 510 is a zone chapter: NC, C-2, RCC, RTL, CC, C-3, PMU, SCMU, OA, OC, RCO (`or/clackamas/_unincorporated/zdo.510.txt#L7`). The area rules sit in ZDO 1005. 1005.02 frontage occupancy and the 20 ft maximum setback near a transit stop are county-wide, not area-bounded, so they are excluded (already encoded as `axis_required` for PMD/MR1/MR2). Design review covers "HDR, MR-1, MR-2, MRR, PMD, RCHDR, SHD, VA, and VTH Districts" with no middle-housing exemption; only detached single-family and prefabricated structures are exempt (`zdo.1102.txt#L5-L20`).

### Clackamas — Clackamas Regional Center Area design standards (ZDO 1005.07)
- Cite: `or/clackamas/_unincorporated/zdo.1005.txt#L414-L464`
- Kind: plan district
- Zones covered: RCC, RCO, RCHDR, SCMU, PMU, and parts of CC, C-3, OC and HDR inside Map X-CRC-1. The pod is permitted in RCHDR and SCMU (YELLOW), and not in PMU.
- Reach (quadplex): reaches — "Subsection 1005.07 applies in the Clackamas Regional Center Area, including the Regional Center and the Fuller Road Station Community, as identified on Comprehensive Plan Map X-CRC-1" (`#L416`). "New development is subject to the urban design elements shown on ... Map X-CRC-3" (`#L420`). No middle-housing exemption was found in zdo.1005.
- Reach (townhouse unit lots): reaches — same text.
- Screenable: corner entrances at Gateway intersections; private streets and walkways on Map X-CRC-7a (line positions, not dimensions). Non-screenable: around 4 (design-plan conformance, urban design elements).
- Boundary: missing — likely source is Comp Plan Maps X-CRC-1, X-CRC-3 and X-CRC-7a (county Comp Plan Chapter 10). FLATS itself notes X-CRC-1 is "a mapped area ... holds no boundary" (`config/jurisdictions/or/clackamas/_unincorporated.yaml#L196-L198`).
- FLATS today: never mentioned by number. The zones are encoded.
- Lots: about 232 (RCC 107 + RCO 38 + RCHDR 32 + SCMU 36 + PMU 19; parts of CC/C3/OC/HDR not counted).
- Note: the reach is mostly to things a lot screen cannot see (Chapter 10 design plan).

### Clackamas — Regional Center design standards (ZDO 1005.08)
- Cite: `zdo.1005.txt#L466-L488`
- Kind: plan district
- Zones covered: the Regional Center part of X-CRC-1 (RCC, RCO, RCHDR, CC).
- Reach (quadplex): reaches — "Subsection 1005.08 applies in the Regional Center, as identified on Comprehensive Plan Map X-CRC-1" (`#L468`).
- Reach (townhouse unit lots): reaches — same.
- Screenable:
  - "Internal streets and driveways are prohibited between buildings and the street to which building entrances are oriented" (in `#L466-L488`), i.e. no parking or driveway between building and street
  - a public entrance oriented to the street
  - Non-screenable: around 3 (pedestrian amenities, parking-structure facades)
- Boundary: missing — Map X-CRC-1.
- FLATS today: never mentioned.
- Lots: unknown (a subset of the 232 above).
- Note: the driveway rule matches the existing `parking_front_prohibited` field.

### Clackamas — Fuller Road Station Community (ZDO 1005.09, SCMU)
- Cite: `zdo.1005.txt#L490-L853`
- Kind: plan district (also a zone, SCMU)
- Zones covered: SCMU. The pod is YELLOW there today.
- Reach (quadplex): reaches — the dimensional and design standards apply to development in the Station Community, with a regulating plan on Map 1005-1. No middle-housing exemption was found.
- Reach (townhouse unit lots): reaches.
- Screenable:
  - minimum height = 20 ft
  - side/rear = 5 ft (0 for attached)
  - driveway curb cut = 24 ft maximum
  - frontage type by street type A–D: Landscape 10–15 ft, Linear 0–5 ft maximum, Porch/Stoop 5–15 ft
  - building frontage = 50% of frontage, or full length where "building frontage required"
  - ground floor = 15 ft (12 ft floor-to-floor if residential)
  - minimum building depth = 40 ft
  - no parking in the front setback
  - Sectors 1–2 exempt until a 40,000 sf threshold
  - Non-screenable: around 6
- Boundary: have it as the zone (SCMU). The street types on Map 1005-1 are missing (a figure in the text).
- FLATS today: encoded in part — side/rear 5 and minimum height 20 from 1005.09. The front setback is not encoded because the street type is unmeasured (`_unincorporated.yaml#L3967-L4100`). Chapter card `zdo.1005.txt#1005.09` is read_it (`#L520-L545`).
- Lots: 36 (SCMU; status zone_missing).
- Note: trace Map 1005-1 street types to unlock the frontage rules.

### Clackamas — PMU district standards (ZDO 1005.10 / 510 PMU1–3)
- Cite: `zdo.1005.txt#L855-L887`
- Kind: master plan
- Zones covered: PMU1–3. The pod is RED (requires a master plan / Table 510-3).
- Reach (quadplex): the text reaches, but the pod is not permitted by right (`_unincorporated.yaml#L4111-L4229`).
- Reach (townhouse unit lots): same.
- Screenable: no internal driveways between buildings and the street. Non-screenable: around 2.
- Boundary: have it (zone).
- FLATS today: encoded, RED.
- Lots: 19.
- Note: no impact.

### Clackamas — Sunnyside Village (ZDO 1005.11, plus ZDO 511 VCS)
- Cite: `zdo.1005.txt#L889-L981`; `zdo.511.txt`
- Kind: plan district / village
- Zones covered: VTH, VA, VR57, VR45, VCS and VO on Map X-SV-1. The pod is permitted in VTH (outcome unencodable), VA (YELLOW) and VR. VCS allows a quadplex only as affordable housing (`_unincorporated.yaml#L3833-L3853`).
- Reach (quadplex): reaches — "Subsection 1005.11 applies in Sunnyside Village, as identified on Comprehensive Plan Map X-SV-1" (`#L891`). In VA, multifamily orients to the street.
- Reach (townhouse unit lots): reaches — "Townhouses shall orient to and line streets with a series of attached 'rowhouse' units" (`#L905`). The VTH primary-dwelling rules start at `#L893`.
- Screenable:
  - primary entries from the street ROW (`#L895`)
  - front garage recessed 2 ft and set 20 ft from the ROW
  - garage/driveway width = 10 ft maximum
  - no street garage access where the lot abuts an alley
  - VCS: parking to the rear
  - VO: no driveway onto 142nd or Sunnyside Rd
  - Non-screenable: around 7 (porch 50% of facade and 6 ft deep, bays and balconies, hipped or gabled roofs, wood/masonry)
- Boundary: have it as zones. The village outline on Map X-SV-1 is not held but matches the V-zones.
- FLATS today: VTH outcome unencodable (`_unincorporated.yaml#L4732-L4745`, "114/115 lots"); VA encoded and YELLOW; VR57 and VR45 encoded. **1005.11 itself is never mentioned in the yaml.** The footnote at `config/footnotes/or/clackamas/_unincorporated.yaml#L603` dismissed the village's resource-protection area.
- Lots: about 1,307 (VR57 977 + VR45 215 + VTH 114 + VA 1; VCS 1).
- Note: the garage and alley rules bite the pod's parking.

### Clackamas — Design-type areas: Centers, Station Communities, Corridor Streets (ZDO 1005.03(I)(9))
- Cite: `zdo.1005.txt#L258-L262`
- Kind: overlay (comp-plan design types on Maps IV-8, X-CRC-1, X-SC-1 Sunnyside Corridor, X-MC-1 McLoughlin Corridor)
- Zones covered: various, in the urban unincorporated area.
- Reach (quadplex): unclear — "Requirements for compatibility with the intent of the design type ... design types are Centers, Station Communities or Corridor Streets" (`#L258`). Whether 1005 reaches middle housing at all depends on Section 1001 applicability, which is not stored. The neighbouring item 6 exempts "middle housing developed pursuant to Section 845" (`#L222`), but only from item 6.
- Reach (townhouse unit lots): unclear — same.
- Screenable: none. Non-screenable: 2 (all judgement words).
- Boundary: missing — Comp Plan Maps IV-8, X-SC-1 and X-MC-1.
- FLATS today: never mentioned.
- Lots: unknown.
- Note: judgement-only, so YELLOW at most under the 2026-10-14 tiers.

### Clackamas — Government Camp / Mount Hood (ZDO 1005.12, ZDO 513 RTC/RC)
- Cite: `zdo.1005.txt#L983-L990`; `zdo.513.txt`
- Kind: village
- Zones covered: MRR, RTC and RC. The pod is not permitted — only a single detached dwelling, RC false (`_unincorporated.yaml#L3854-L3877`).
- Reach (quadplex): no — "In the MRR District, the following standards shall apply to commercial developments" (`#L987`).
- Reach (townhouse unit lots): no — same quote.
- Screenable: none for the pod. Non-screenable: several (materials).
- Boundary: have it (zones).
- FLATS today: chapter card ruled nothing_here (`_unincorporated.yaml#L502-L517`).
- Lots: 58 (513 zones).
- Note: rural, outside the UGB.

---

## Milwaukie

### Milwaukie — Downtown zones DMU + Downtown Site and Building Design (19.304, 19.508)
- Cite: `or/clackamas/milwaukie/19.300.base-zones.txt#L1378`; `19.500.supplementary.txt#L2866-L2900`
- Kind: zone-chapter
- Zones covered: DMU (and OS). A quadplex is not permitted: there is no row in Table 19.304.2, and "uses not listed below, are prohibited" (`19.300.base-zones.txt#L1400-L1402`). Townhouses are permitted (`#L1433-L1438`) except on Main Street and with no ground-floor dwellings south of Scott (Figure 19.304-2).
- Reach (quadplex): not permitted, so moot.
- Reach (townhouse unit lots): reaches — "Townhouse and live/work units, where permitted, are subject to the following design elements and additional standards: a. Subsection 19.508.4.A Site Frontage" (`19.500.supplementary.txt#L2888-L2892`), plus E Entrances and M Plazas.
- Screenable:
  - minimum height 25 ft
  - maximum front setback 10 ft
  - no parking in front
  - minimum density 25
  - frontage occupancy 50/75/90% by street (19.508.4.A.2, figures)
  - no townhouses on Main Street
  - Non-screenable: around 5
- Boundary: have it as the zone (DMU). The Main Street / south-of-Scott limits are on Figure 19.304-2, which is untraced.
- FLATS today: encoded — quadplex false, townhouses held behind `inside_mapped_use_area`. The design review Type I path is treated as by-right (`config/jurisdictions/or/clackamas/milwaukie.yaml#L1960-L2125`). Frontage occupancy is not encoded. Never GREEN today.
- Lots: 120 (DMU; zone_missing).
- Note: the yaml (`#L1970-L1978`) flags that it read Type I downtown design review as not-a-bar, and that Steph could rule otherwise.

### Milwaukie — Central Milwaukie GMU (19.303)
- Cite: `19.300.base-zones.txt#L1074` (19.303.4), with the figure rules at `#L1188-L1296`
- Kind: zone-chapter
- Zones covered: GMU. A quadplex is a conditional use; townhouses are permitted (unit-lots variant).
- Reach (quadplex): CU, so YELLOW/conditional.
- Reach (townhouse unit lots): reaches — the standards apply to all development in GMU.
- Screenable:
  - minimum density 25 / maximum 50
  - maximum street setback 20 ft, or 10 ft on Figure 19.303.4.C.2.b commercial edges (`#L1188-L1194`)
  - no parking between building and street (`#L1200s`)
  - 50% frontage occupancy on the Figure 19.303.4.D block faces (`#L1222-L1232`)
  - 15 ft residential edge (Figure 19.303.5, `#L1296`)
  - Non-screenable: around 3
- Boundary: have it as the zone. The figures are untraced (`zoning_milwaukie` holds only ZONE, `config/pipeline.yaml#L304-L311`).
- FLATS today: encoded with unit lots only, YELLOW at best; frontage occupancy not encoded (`milwaukie.yaml#L2199-L2330`).
- Lots: 46.
- Note: the frontage % and edge rules depend on figures.

### Milwaukie — North Milwaukie Innovation Area (19.312 MUTSA/NME)
- Cite: `19.300.base-zones.txt#L3460-L4139`
- Kind: zone-chapter
- Zones covered: MUTSA, NME. The pod is not permitted (`milwaukie.yaml#L1788-L1840`).
- Reach: moot for both forms (pod not permitted).
- Screenable: the 19.312.7 design standards for the MUTSA and NME key streets exist but are moot. Non-screenable: n/a.
- Boundary: have it (zones).
- FLATS today: encoded, RED.
- Lots: 149 (MUTSA 82 + NME 67).
- Note: none.

### Milwaukie — Flex Space overlay (19.404)
- Cite: `19.400.overlays.txt#L2866-L2965`
- Kind: overlay
- Zones covered: employment.
- Reach: no for both forms — the overlay permits employment uses only; chapter card ruled nothing_here (`milwaukie.yaml#L453-L468`).
- Screenable: none for the pod.
- Boundary: n/a.
- FLATS today: chapter card nothing_here.
- Lots: unknown.
- Note: none.

---

## Happy Valley

### Happy Valley — Rock Creek PMU / Rock Creek Comprehensive Plan Area (16.31), plus the Rock Creek Employment Center
- Cite: `or/clackamas/happy-valley/16.31.rock-creek-pmu.txt#L27`, `#L37`, `#L73`
- Kind: master plan
- Zones covered: PMU (master plan required over 5 acres, `#L37`). The Employment Center is MUE/MUC (`16.23.commercial.txt#L854`, `#L860`, `#L934`), where the pod is not permitted.
- Reach (quadplex): the text reaches — "Standards are flexible and shall be determined through the master plan or a design review process" (`#L73`) — but the pod is RED.
- Reach (townhouse unit lots): same.
- Screenable: none (flexible). Non-screenable: all.
- Boundary: have it (zone).
- FLATS today: encoded, PMU RED (`config/jurisdictions/or/clackamas/happy-valley.yaml#L3623-L3645`).
- Lots: 2 (PMU); 45 MUE+MUC.
- Note: no impact.

### Happy Valley — Eagle Landing Plan Area (16.23.010.D)
- Cite: `16.23.commercial.txt#L158-L260` (Map X-CRC-2)
- Kind: master plan
- Zones covered: RCMU and PMU6. A quadplex is false in RCMU (`happy-valley.yaml#L3438`).
- Reach: moot for both forms.
- Screenable: master-plan-set (584 units). Non-screenable: n/a.
- Boundary: have it (zone).
- FLATS today: encoded (quadplex false).
- Lots: 21.
- Note: none.

### Happy Valley — Happy Valley Town Center Plan Area
- Cite: `16.22.residential.txt#L635`, `#L927-L928`; `16.23.commercial.txt#L856`; `16.43.parking.txt#L179`
- Kind: plan district
- Zones covered: residential zones and CCC around the town centre. CCC is pod-not-permitted (`happy-valley.yaml#L3456-L3540`).
- Reach (quadplex): reaches, as relaxations only — parking minimum exempt within ¼ mile (`16.43.parking.txt#L179`); neighbourhood commercial allowed.
- Reach (townhouse unit lots): reaches — same relaxations.
- Screenable: parking minimum = 0 within ¼ mile of the Town Center. Non-screenable: 0.
- Boundary: missing — likely the Comp Plan map / city GIS (`zoning_happy_valley` carries a ZOVER field, `config/pipeline.yaml#L295-L302`; check whether it marks the plan area).
- FLATS today: parking exemption not encoded (`happy-valley.yaml#L750-L763`), which is the conservative choice.
- Lots: unknown.
- Note: loosens only. `config/dlcd_read.yaml#L1361-L1370` has a pending Main Street District overlay proposal (MCC, +662 units) to watch.

(VC, VO, CCC and MCC are village/town-centre zone chapters where the pod is not permitted, `happy-valley.yaml#L3456-L3540`. VTH is a plain zone chapter, encoded, quadplex P, `#L3006`. None are listed as separate districts.)

---

## Oregon City

`zoning_oregon_city` holds only ZONE (`config/pipeline.yaml#L313-L320`). Concept plan areas are defined at `or/clackamas/oregon-city/17.zoning.txt#L1242-L1246`: "including the South End Concept Plan area, the Beavercreek Road Concept Plan area, and the Park Place Concept Plan area." 17.62 (site plan and design review) is city-wide with no area-bounded rules (17.62.055 applies to "institutional, office, multi-family, retail and commercial buildings", `#L17515`), so it is excluded. A grep of `config/jurisdictions/or/clackamas/oregon-city.yaml` for 17.21, 17.22, 17.40, Park Place, South End, Canemah and McLoughlin returns nothing.

### Oregon City — Park Place Concept Plan Area (17.21)
- Cite: `or/clackamas/oregon-city/17.zoning.txt#L6129-L6145`
- Kind: master plan (concept plan area)
- Zones covered: residential (R-6, R-8, R-10, R-5 and others inside the area). The pod is permitted (middle housing).
- Reach (quadplex): reaches — "This chapter applies to all new detached single-family residential units, duplexes, triplexes, quadplexes, townhouses, accessory dwelling units, and cottage clusters located within the Park Place Concept Plan areas" (`#L6130-L6133`).
- Reach (townhouse unit lots): reaches — same quote.
- Screenable:
  - footprint over 1,200 sf needs secondary masses, each no larger than 600 sf (`#L6158-L6166`). The pod's 2,016 sf box fails unless the director grants an exemption (Type II).
  - garages must be detached, side- or rear-entry (`#L6275-L6277`)
  - 3 ft pedestrian path separate from the driveway (`#L6178-L6200`)
  - Non-screenable: around 6 (5/12 roof pitch, porch 24 in above grade and 80 sf, architectural-detail points, siding, windows, style)
- Boundary: missing — likely the Comp Plan / Park Place Concept Plan map on the city GIS (maps.orcity.org, which already hosts zoning).
- FLATS today: **never mentioned.**
- Lots: unknown.
- Note: **Surprise.** It names quadplexes and townhouses explicitly, and the massing rule is a hard miss for the fixed pod. A plan conforming to all standards is Type I; anything needing an exemption is Type II (`#L6138-L6141`).

### Oregon City — South End Concept Plan Area (17.22)
- Cite: `17.zoning.txt#L6339-L6350`
- Kind: master plan (concept plan area)
- Zones covered: residential. The pod is permitted.
- Reach (quadplex): reaches — "This chapter applies to all new detached single-family residential units, duplexes, triplexes, quadplexes, townhouses, accessory dwelling units, and cottage clusters located within the South End Concept Plan area" (`#L6341-L6345`).
- Reach (townhouse unit lots): reaches — same.
- Screenable:
  - massing 1,200 / 600 sf (`#L6369-L6380`)
  - detached alley garage within 5 ft of the alley; extra parking beside, not in front of, the garage door (`#L6354-L6366`)
  - porch required if within 20 ft of the sidewalk or front line
  - 3 ft path
  - Non-screenable: around 5
- Boundary: missing — the South End Concept Plan map (city GIS).
- FLATS today: never mentioned.
- Lots: unknown.
- Note: same massing problem as Park Place.

### Oregon City — Thimble Creek (formerly Beavercreek Road) Concept Plan Area (17.10.070, 17.12.060, 17.16.155, 17.24.050, 17.29.080, 17.37.060)
- Cite: `17.zoning.txt#L4403-L4462` (R-5), `#L4660` (R-2)
- Kind: master plan (concept plan area)
- Zones covered: R-5, R-2, NC, MUC-2 and CI inside the area. The pod is permitted in R-5 and R-2.
- Reach (quadplex): reaches — "This section applies to all development in the R-5 district within the Thimble Creek Concept Plan Area ... These standards apply in addition to and supersede the standards of the R-5 zone" (`#L4405-L4410`).
- Reach (townhouse unit lots): reaches — same.
- Screenable (for lots within 20 ft of the southern boundary):
  - residential and open-space uses only
  - quadplex minimum lot 7,000 sf; townhouse 1,500 sf (`#L4421-L4426`)
  - 40 ft setback from the southern boundary (`#L4427-L4430`)
  - landscaped buffer with a 6 ft fence
  - R-2: live/work permitted; sustainability density bonus up to 26.2 du/ac (`#L4655-L4700`)
  - NC: minimum 17.4 du/ac
  - Non-screenable: around 3
- Boundary: missing — the concept plan map. The perimeter is the "southern boundary" (Tax Lot 00316, Map 32E15A).
- FLATS today: noted as "geographic and not encoded" (`oregon-city.yaml#L12-L13`); the R-2 note at `#L1535`; card 17.24.050 ruled (`#L65-L75`); CI rule at `#L2393-L2417`.
- Lots: unknown (a subset of R-5 18 and R-2 624).
- Note: the lot-size and setback rules only hit a strip along the southern edge.

### Oregon City — Historic Overlay District: Canemah Historic District, McLoughlin Conservation District, Barlow Road Historic Corridor (17.40)
- Cite: `17.zoning.txt#L8908-L8946`, `#L9057-L9067`
- Kind: historic district
- Zones covered: mostly residential (Canemah, McLoughlin), plus HC and MUD edges. The pod is permitted in R zones.
- Reach (quadplex): reaches — "nor shall there be any new construction in an historic district, conservation district, historic corridor, or on a landmark site, unless a certificate of appropriateness has previously been issued by the historic review board" (`#L9060-L9064`).
- Reach (townhouse unit lots): reaches — same.
- Screenable: none. Non-screenable: 8 (17.40.060.F criteria, `#L9119-L9140`: compatibility, scale and so on, decided at a public hearing).
- Boundary: missing — "designated on a special city zoning map or maps" (`#L8917-L8921`). Likely on the city GIS (maps.orcity.org).
- FLATS today: **never mentioned** (oregon-city.yaml mentions "historic" only as a name in a list, `#L2539`).
- Lots: unknown.
- Note: discretionary hearing, so YELLOW/REVIEW under the 2026-10-14 tiers; a historic-area exception to 197A.400 is likely.

### Oregon City — MUD with downtown design district sub-district (17.34)
- Cite: `17.zoning.txt#L7674-L7700`, `#L7850` (outside), `#L7895` (within)
- Kind: zone-chapter (with a sub-district)
- Zones covered: MUD. A quadplex is permitted (17.34.020.L, `#L7725-L7726`). Townhouses are **prohibited** (17.34.040.D).
- Reach (quadplex): reaches — the downtown design district sets different dimensions (17.34.070) for "properties located within the downtown design district" (`#L7895-L7897`).
- Reach (townhouse unit lots): not permitted (17.34.040.D, quoted in `oregon-city.yaml#L2008-L2011`).
- Screenable:
  - within the district: max height 58 ft; coverage 95%; landscaping 5%; setback 20 ft where abutting residential
  - outside it: 75 ft; 90%; 10%; 15 ft
  - minimum height 25 ft (same in both)
  - the maximum front setback (10 ft / 20 ft) does not reach: "Standalone residential development of fewer than five units are exempt from maximum setbacks" (`#L7930-L7932`)
  - the minimum FAR does not reach: it applies "to all nonresidential and mixed-use building developments" (`#L7949-L7950`)
  - Non-screenable: around 2 (storefront facade)
- Boundary: missing — the sub-district outline is not held; likely the city GIS.
- FLATS today: encoded as a composite taking the tighter of the two (`oregon-city.yaml#L1989-L2005`). The unit_lots path is refused in the notes (`#L2115-L2122`).
- Lots: 278 (MUD).
- Note: holding the boundary would loosen only (coverage 90 to 95, landscaping 10 to 5).

### Oregon City — Willamette Falls Downtown District (17.35)
- Cite: `17.zoning.txt#L7995-L8012`, `#L8188-L8215`
- Kind: zone-chapter
- Zones covered: WFDD. A quadplex is permitted (17.35.020.R). Townhouses are prohibited: "Single-family detached residential units, duplexes and townhouses" (`#L8128`).
- Reach (quadplex): reaches.
- Reach (townhouse unit lots): no (prohibited, `#L8128`).
- Screenable:
  - minimum FAR 1.0 (`#L8191-L8192`)
  - minimum height "Two entire stories and twenty-five feet" (`#L8195`)
  - maximum setback 10 ft
  - coverage 100%
  - Non-screenable: around 1 (storefront guidelines)
- Boundary: have it (zone).
- FLATS today: encoded (`oregon-city.yaml#L2213-L2325`).
- Lots: 4.
- Note: none.

### Oregon City — HC Historic Commercial (17.26)
- Cite: `17.zoning.txt#L6751-L6800`
- Kind: zone-chapter
- Zones covered: HC. A new quadplex is not permitted; only "Conversions of an existing single-family detached residential unit or duplex into a triplex or quadplex" (`#L6788-L6789`).
- Reach: moot for both forms.
- Screenable: n/a.
- Boundary: have it (zone).
- FLATS today: encoded (prohibited uses, `oregon-city.yaml#L2421-L2424`).
- Lots: 37.
- Note: none.

---

## Gladstone

17.25 HCAD is the **Habitat Conservation Area District**, an environmental overlay ("The HCAD applies to all parcels containing a Habitat Conservation Area", `or/clackamas/gladstone/17.25.hcad.txt#L20`), so it is excluded. `amended/ord1545.txt` (2026, TXT-25-03) is a state-law compliance update across 17.06–17.94. It carries the Town Center rows forward (`#L325`, `#L383-L389`) and adds no new district; `config/jurisdictions/or/clackamas/gladstone.yaml#L955-L1030` already encodes it as an amendment.

### Gladstone — Gladstone Town Center (in R-5, C-3 and parking)
- Cite: `or/clackamas/gladstone/17.12.r-5.txt#L45-L47`, `#L164`, `#L176`, `#L183`, `#L198`; `17.48.parking.txt#L23-L31`
- Kind: plan district
- Zones covered: R-5 (and C-3 mixed use). The pod is permitted (middle housing).
- Reach (quadplex): reaches, as relaxations — "Front setback 20 ft / 10 ft within Gladstone Town Center" (`17.12.r-5.txt#L182-L183`), and street side the same (`#L197-L198`). The parking minimum is waived inside the Town Center or within ¼ mile of it (`17.48.parking.txt#L25-L27`).
- Reach (townhouse unit lots): reaches — same rows.
- Screenable:
  - front setback = 10 ft (`#L183`)
  - street-side setback = 10 ft (`#L198`)
  - parking minimum = none (Zone A)
  - Non-screenable: 0
- Boundary: missing — likely source is the "Gladstone Parking Mandate Exception Map" (`17.48.parking.txt#L31`) or the city's `Gladstone_LandUseAndPlanning` MapServer (`config/pipeline.yaml#L326`, layer 7 is zoning; other layers unchecked).
- FLATS today: read and not encoded — "lots inside the Town Center screen tighter than the code holds them" (`gladstone.yaml#L1114-L1120`); parking exception not encoded (`#L611-L621`).
- Lots: unknown (a subset of R5 1,148).
- Note: loosens only; drawing it would turn some REVIEW/RED lots greener.

### Gladstone — Portland Avenue (C-2) development limits (17.18.050(3), 17.18.060(1))
- Cite: `17.18.c-2.txt#L115-L121`, `#L135-L137`
- Kind: overlay (street-defined)
- Zones covered: C-2. The pod is permitted outright (17.18.020(11), (12)).
- Reach (quadplex): reaches — "The following limitations apply to developments along Portland Avenue" (`#L115`), including "(c) All buildings shall have a primary entrance facing Portland Avenue" (`#L121`).
- Reach (townhouse unit lots): reaches — same.
- Screenable:
  - primary entrance facing Portland Ave
  - residential maximum front setback 5 ft (`#L137`)
  - parking not between building and street (17.18.070)
  - Non-screenable: 1 (25% ground-floor window, `#L119`)
- Boundary: have it — measured as `along_portland_avenue` (within 60 ft; `rules/conditions.py#L296`).
- FLATS today: encoded and measured — qualified by FACT-ALONG-PORTLAND-AVENUE (`gladstone.yaml#L1490-L1506`).
- Lots: 148 (C2; "147 lots" per `gladstone.yaml` notes).
- Note: done; the worked example of a street-bounded district.

---

## Jurisdictions with no district found
None of my six are empty. Within them, these came up empty:
- Gladstone: no design district beyond the two above (HCAD is environmental).
- Milwaukie: no separate design overlay in 19.400 besides Flex Space; 19.401 WG and 19.402 NR are environmental and 19.403 HP is landmarks.

Grep terms used: "design district", "design overlay", "overlay zone", "overlay district", "plan district", "plan area", "concept plan", "town center", "main street", "downtown", "village", "historic district", "conservation district", "sub-district", "applicability", "applies in", "exempt", "Figure", "Map", "Townhouse", "quadplex", "still considered", "supersede".

## 4. Detail — dd_clackamas_south.md

### Design-districts inventory — Clackamas south (dd-clackamas-south)

Scope: Canby, Sandy, Estacada, West Linn, Tualatin, Wilsonville, Lake Oswego, Rivergrove, Johnson City.
Paths in `Cite:` are relative to `flats/provenance/docs/`. Config paths relative to repo root.
Lot counts: data/flats/coverage.csv has NO rows for Canby, Sandy or Estacada (added after 2026-10-01);
figures for those three come from docs/FOLLOWUPS.md item 53 where quoted.

Summary: 19 districts found (16 in screened cities + 3 in switched-off Lake Oswego). 9 reach the pod in a
zone where the pod is otherwise permitted (Canby DCO-TC, Sandy BVO, Estacada D, West Linn WHD, West Linn MU,
Tualatin CTO, Wilsonville V, OTR, Old Town O overlay); 1 unclear (Canby North Redwood). Of the 9, FLATS
measures/encodes 5 (WHD, WL MU, CTO residential sub-district, V, OTR partly); 4 are refused, dismissed or
unheld (DCO-TC, BVO, Estacada D, Wilsonville O overlay).

---

## Canby

### Canby — Downtown Canby Overlay, DCO (CMC 16.41)
- Cite: `or/clackamas/canby/cmc.16.41.020.txt#L3` (boundary = Figure 11; three sub-areas CC, TC, OHC)
- Kind: overlay (with 3 sub-areas)
- Zones covered: "portions of both the C-1 and C-2 zones" (`cmc.16.41.020.txt#L9`). C-1 and C-2 refuse the
  pod (housing only in mixed use). EXCEPT the Transitional Commercial (TC) sub-area — "two Transitional
  Commercial nodes ... between 3rd and 4th and Fir and Douglas ... and 3rd and 4th and Holly and Knott"
  (`cmc.16.41.020.txt#L11`) — where multi-family and common-wall houses are permitted outright on R-2
  standards (`cmc.16.41.030.txt#L5-L11`).
- Reach (quadplex): reaches (TC only) — "the following residential uses are also permitted, provided they
  meet all R-2 development standards ... 3. Multi-family dwelling" (`cmc.16.41.030.txt#L5,L11`); DCO
  standards "supersede the base zone standards" (`cmc.16.41.050.txt#L3`). No residential exemption in 16.41.
- Reach (townhouse unit lots): reaches (TC only) — "1. Single-family dwelling having common wall
  construction" (`cmc.16.41.030.txt#L7`).
- Screenable:
  - min setback CC 0 / TC 0 / OHC 10; max setback from street lot lines CC 10 / TC 15 (`cmc.16.41.050.txt#L21-L23`)
  - build-to: at least 60% (CC, TC) / 40% (OHC) of each lot frontage built at the min setback (`#L11,L25-L28`)
  - new building at the lot corner at Figure 11 gateway intersections (`#L17`)
  - min FAR CC 0.8 (C-1 only) / TC 0.4 / OHC 0.15; max footprint 30,000/20,000/80,000; max height 60/45/45 (`#L36-L42`)
    (TC 0.4 FAR: pod 4,032 sf works only on a lot <= ~10,080 sf)
  - no parking/maneuvering between building and street in CC and TC (`#L78`)
  - side parking set back 15 ft from front lot line (`#L82`); parking+driveways <= 40% of lot frontage CC/TC, 60% OHC (`#L86`)
  - Non-screenable: 5 (screening a-d, "should" corner siting); 16.41.060/.070 (DCO design review standards,
    materials) are NOT stored — count unknown.
- Boundary: missing — Figure 11 "Downtown Canby Overlay Zone" map in the code (`cmc.16.41.040.txt#L7-L9`);
  zoning comes from the Oregon City regional fabric with fields [ZONE, CITY] only (flats/config/pipeline.yaml#L341-L353), no overlay field.
- FLATS today: dismissed into a false RED — C-1 refused with a DOUBT note: "The sub-area boundary is a
  figure in the code, not a map layer FLATS holds, so every C-1 lot stays refused (a false RED on those few
  lots, never a false GREEN). FOLLOWUPS carries the tracing." (flats/config/jurisdictions/or/clackamas/canby.yaml#L2260-L2265)
- Lots: unknown (two small nodes, a few blocks each; Canby not in coverage.csv)
- Note: tracing the two TC nodes is the whole job; the rest of the DCO sits on zones that refuse the pod.
  City-wide 16.49 Type III site/design review is not area-bounded (already green+flag CLEAR-OBJECTIVE via
  ORS 197A.400, canby.yaml#L1997-L2001).

### Canby — North Redwood Plan District (CMC 16.13.010)
- Cite: `or/clackamas/canby/cmc.16.13.010.txt#L9`
- Kind: plan district (master plan, NRDCP)
- Zones covered: R-1 and R-1.5 named (`#L51-L53`), plus "high density residential" (`#L27`). R-1.5/R-2 admit the pod.
- Reach (quadplex): unclear — applies "to all land within the North Redwood Plan District" (`#L9`), but every
  standard is a subdivision/PUD approval criterion: "prior to approval of any new subdivision or Planned Unit
  Development" (`#L15`). A pod on an existing lot meets nothing.
- Reach (townhouse unit lots): unclear — turns on whether a middle-housing land division is a "subdivision"
  here (`#L15`); not checked against 16.04.
- Screenable: block length <= 600 ft, ped connection every 330 ft (`#L37-L39`); average lot >= 5,000 sf R1 / 4,000 sf R1.5 (`#L51-L53`). Non-screenable: 9 (street alignments, loop road, cul-de-sac locations, parks dedication).
- Boundary: missing — "City of Canby's North Redwood Plan District Map" (`#L9`).
- FLATS today: never mentioned beyond the code list (canby.yaml#L1321-L1324).
- Lots: unknown
- Note: low impact; land-division-level only.

## Sandy

### Sandy — Bornstedt Village Overlay, BVO (SDC 17.54.40-17.54.140, Specific Area Plan overlay)
- Cite: `or/clackamas/sandy/sdc.17.54.txt#L218` (district), `#L266` (applicability)
- Kind: overlay / master plan (Specific Area Plan "S" overlay, 17.54.00 E)
- Zones covered: SFR, R1, R2, R3, C-3 inside the BVO (`sdc.17.54.txt#L271-L293`). Pod permitted (YELLOW tier)
  in R-1 (townhouse only), R-2, R-3; refused in SFR, C-3.
- Reach (quadplex): reaches — "Development and land use within the Bornstedt Village Overlay district ...
  shall be in conformance with the provisions outlined in this chapter. Cascadia Village Subdivisions #1
  through #6 are exempt from Sections 17.54.70—17.54.110." (`sdc.17.54.txt#L266`); design review "required
  for all new uses and structures" (`#L357`).
- Reach (townhouse unit lots): reaches — same text; row-house rows in Table 17.54.80 (`#L304-L305`).
- Screenable:
  - front 10 min, rear 15 (SFR 20), interior side 5 (SFR 7.5), corner 10, height 35 (`#L309-L316`) — same as base except SFR
  - coverage max 75% multi-family R2/R3 (`#L317`)
  - row house min AVERAGE lot width R1 30 ft / R2 20 / R3 20; at building line 20 (`#L304-L305`) — STRICTER
    than base "No minimum" (sandy.yaml#L510-L513); pod unit lot is ~14 ft wide, so the townhouse form fails in BVO
  - lots < 40 ft frontage take access from rear alley or shared private drive (`#L429`)
  - lots on Barlow Rd / Village Blvd / Cascadia Village Dr boulevards: residential access from side street,
    alley or shared drive; primary entrance oriented to the boulevard (`#L472,L496,L512`)
  - C-3 in BVO: housing only if 80% of ground floor is commercial (`#L293`)
  - Non-screenable: 8 (design review, SF design calcs, housing variety >40 lots, garage options x4 apply to SF/duplex only, Hwy 211 landscaping, tree retention, green streets, parks)
- Boundary: missing — "as shown on the City of Sandy Zoning Map (reflecting Figure 5 in the Bornstedt Village
  Specific Area Plan)" (`#L266`); SAP marked by border + "S" on the zoning map (`sdc.17.54.txt` 17.54.00 E).
  Regional fabric carries [ZONE, CITY] only (pipeline.yaml#L355-L367).
- FLATS today: never encoded — "Overlays: Specific Area Plan (Bornstedt Village), Flood Slope Hazard,
  Cultural and Historic Resource: not held by FLATS for Sandy." (flats/config/jurisdictions/or/clackamas/sandy.yaml#L473-L474)
- Lots: unknown (R-1/R-2/R-3 total 1,961 per FOLLOWUPS 53; BVO share unknown)
- Note: mostly mirrors base numbers; the binding add is the 20-30 ft row-house width on the unit-lot path.

### Sandy — Downtown and Village Commercial design standards (SDC 17.90.110)
- Cite: `or/clackamas/sandy/sdc.17.90.txt#L638`
- Kind: zone-chapter (applies by zone: C-1 Central Business District, C-3 Village Commercial)
- Zones covered: C-1, C-3 — both refuse the pod (housing only above a commercial business; sandy.yaml#L816-L850).
- Reach (quadplex): no (use refused) — C-1: "no new multi-family or row house" (sandy.yaml#L824, quoting `sdc.17.42.txt#L24,L28,L40`).
- Reach (townhouse unit lots): no (same).
- Screenable: parking rear/side, not within 10 ft of ROW (`sdc.17.90.txt` 17.90.110 A.3). Non-screenable: many (not counted; use refused).
- Boundary: have (is the zone).
- FLATS today: encoded as refused zones.
- Lots: unknown
- Note: no impact. Related street rule, not a district: 17.82 transit streets — "applies to all residential
  development located adjacent to a transit street" (collector/arterial), primary entrance within 25 ft of
  it (`sdc.17.82.txt#L20,L38,L42`); not encoded, Sandy has no street-class map.

## Estacada

### Estacada — Downtown zone D with Downtown Design Guidelines and Standards (EMC 16.26)
- Cite: `or/clackamas/estacada/emc.16.zones.txt#L907`
- Kind: zone-chapter (implements the Downtown and Riverside Area Plan, `#L923`)
- Zones covered: D. Pod use permitted conditionally on fronts/location/density (below).
- Reach (quadplex): reaches — "4 Multi-family dwelling, triplex, or fourplex, provided that ... Ground floor
  residential uses do not front Broadway Street, Main Street, or OR 224 ... prohibited ... south of OR 224;
  ... density ... not less than sixteen (16) dwelling units per acre" (`#L940-L946`); design standards
  "apply to new structures ... in the Downtown zone" (`#L1121`); Type 2 committee "Design review of all new
  construction" (`#L1131`).
- Reach (townhouse unit lots): unclear — no townhouse/attached single-family in the D outright list (`#L930-L978`); Estacada definitions not checked for "fourplex divided stays fourplex".
- Screenable:
  - front/street side 0 min / 5 max; 5 min / 10 max on 2nd Ave or OR 224; max met if 50% of the structure is in the yard (`#L1053-L1054`)
  - side and rear 10 ft if abutting a residential zone (`#L1056-L1058`)
  - min height 17 ft, max 65 (`#L1072`)
  - min density 16 du/ac (`#L944`) — pod: lot <= ~10,890 sf
  - no ground-floor residential fronting Broadway/Main/OR 224; none south of OR 224 (`#L942`)
  - parking not between primary entrance and street; beside/behind, via alley/local street (`#L1045`)
  - no vehicle access from Broadway between OR 224 and 3rd Ave (`#L1086`)
  - landscaping >= 5% (`#L1076`); Lakeshore Trail parcels: 10% open space reserve (`#L1106`)
  - Non-screenable: ~20 (materials, paint palette, transparency 50%/40%, entrances, 15-criterion points table at 65%)
- Boundary: have if the regional fabric carries "D" — unclear: pipeline.yaml#L379-L382 lists the fabric's
  Estacada spellings (R1, R2, R3, C1, C2, RC, HC, OC, M1, AP, OS) without D, CMU, MMU or NCR; check the acquired codes.
- FLATS today: refused — "the four-unit use is conditioned on street fronts and a density floor the one-lot
  screen cannot test" (flats/config/jurisdictions/or/clackamas/estacada.yaml#L544-L555). Already queued:
  FOLLOWUPS 53(f) "the Downtown zone (D) could be encoded with the named-street tool ... waiting on Steph's yes/no".
- Lots: unknown
- Note: likely false RED; every gate is testable (named_street.py exists). The committee review would fall under the ORS 197A.400 green+flag ruling.

### Estacada — Mill Area Mixed Use, MMU (EMC 16.33)
- Cite: `or/clackamas/estacada/emc.16.zones.txt#L1704`
- Kind: zone-chapter / master plan
- Zones covered: MMU; CMU uses permitted only after a Council Master Development Plan.
- Reach (quadplex): no (gated) — "every development needs a Council-approved master plan first" (estacada.yaml#L578-L584, quoting `emc.16.zones.txt#L1736,L1929`); "only areas with an approved master plan may be divided" (`#L1919`).
- Reach (townhouse unit lots): no (same, `#L1919`).
- Screenable: not read (gated). Non-screenable: n/a.
- Boundary: have if the fabric carries MMU (see D above).
- FLATS today: encoded as refused (estacada.yaml#L573-L584).
- Lots: unknown
- Note: none.

## West Linn

### West Linn — Willamette Historic District, WHD (CDC Chapter 25, 25.070(B)-(C))
- Cite: `or/clackamas/west-linn/25.willamette-historic.txt#L388`
- Kind: historic district (imposes dimensional standards)
- Zones covered: residential zones under the boundary; drawn_areas lists R-40..R-3 (west-linn.yaml#L2432); lots in practice all R-10 and R-5. Pod (quadplex) permitted outright in all nine residential zones.
- Reach (quadplex): reaches — "This subsection applies only to alterations and additions, new construction,
  and accessory structure construction of residential and historically residential properties in the
  Willamette Historic District" (`#L388`); 25.070(B) "applies only to new development or construction in a historic district" (`#L71`).
- Reach (townhouse unit lots): reaches — same text; "No building shall exceed 35 feet in overall width" (`#L426`) caps the attached 56-ft building whatever the lot pattern.
- Screenable:
  - front = average of adjacent homes on the block face; corner: average of neighbour and 20 ft (`#L392`)
  - side 5, side street 10, rear 20 min (`#L398,L404,L410`)
  - height 28 ft (`#L418`) — pod 26 clears
  - max building width 35 ft (`#L426`) — pod 56x36 FAILS on any lot
  - front facade gable <= 28 ft wide (`#L426`); roof pitch >= 6:12 (`#L428`) — a flat-roofed pod fails
  - garage/parking access from the alley when present (`#L432-L440`); corner orientation (`#L412`)
  - Non-screenable: ~8 (25.070(A) compatibility, 25.070(B) massing/style/concealment, archaeology, 25.060 materials); no variance, only discretionary modification (`#L446-L456`)
- Boundary: have — flats/config/areas/or/clackamas/west-linn/willamette-historic-district.geojson (one polygon,
  ~20 ac, from geo.westlinnoregon.gov Operational/RegulatoryZones layer 1).
- FLATS today: drawn and measured — `drawn_areas.willamette_historic_district` (west-linn.yaml#L2429-L2455);
  `max_building_width_ft` exempt with a 35 ft variant `when: [willamette_historic_district]` on R-10 and R-5
  (west-linn.yaml#L1452-L1478, #L1740-L1766); front setback qualified by the fact in all 8 zones (e.g. #L993),
  rear qualifier on R-3 and R-2.1 (#L1931, #L2054); reading card `25.070` queue: condition, outcome: applies
  (#L277-L297); site fact ConditionDef (flats/rules/conditions.py#L364-L381); flag FACT-WILLAMETTE-HISTORIC-DISTRICT (flats/config/flags.yaml#L1319).
- Lots: 71 at least 90% inside (all R-10/R-5), 2 cut by the line (1225 13th St, 1649 5th Ave) (west-linn.yaml#L2451-L2455)
- Note: the cap is the only standard in the corpus the pod fails on its own dimensions. Stale comment at
  west-linn.yaml#L1464 still says "Nothing maps the boundary". R-2.1 carries the fact (#L2037) but is not in
  drawn_areas `zones:` (#L2432) — harmless only if no R-2.1 lot is inside; worth one check.

### West Linn — Willamette Falls Drive Commercial Design District, WFC (CDC Chapter 58)
- Cite: `or/clackamas/west-linn/05.density.txt#L58` (overlay list); `25.willamette-historic.txt#L578`
- Kind: overlay (commercial design district)
- Zones covered: unknown (Ch 58 not stored); GC refers to it (`19.gc.txt#L221,L223`). GC refuses the pod
  ("multiple-family units ... only above the first floor", west-linn.yaml#L2199-L2224).
- Reach (quadplex): no (as residential) — "Other buildings are subject to the requirements in Chapter 58 CDC"
  (`25.willamette-historic.txt#L388`): residential property in the WHD takes 25.070(C), not Ch 58. Reach on a
  residential lot outside the WHD: unclear (Ch 58 unread).
- Reach (townhouse unit lots): same as quadplex.
- Screenable: unknown (not stored). Non-screenable: unknown.
- Boundary: missing — "as identified in CDC 58.030(C)" (`25.willamette-historic.txt#L578`); likely a layer on
  the same geo.westlinnoregon.gov Operational/RegulatoryZones MapServer that held the WHD.
- FLATS today: dismissed — crossref note "58": "Chapter 58 is the branch it does not take. Not fetched"
  (west-linn.yaml#L488-L494).
- Lots: unknown
- Note: low impact unless Ch 58 also covers a residential zone.

### West Linn — Willamette Neighborhood Mixed Use Transitional Zone, MU (CDC Chapter 59)
- Cite: `or/clackamas/west-linn/59.mu.txt#L33`
- Kind: zone-chapter (Willamette neighbourhood transitional zone with design standards 59.070(B))
- Zones covered: MU; quadplex and townhouse permitted outright (west-linn.yaml#L2294-L2322).
- Reach (quadplex): reaches — "c. Quadplex residential units" outright; design review Class I (Ch 55 read live, not stored) (west-linn.yaml#L2302-L2320).
- Reach (townhouse unit lots): reaches — "4. Townhouse" (same).
- Screenable (encoded): front 12 / max 20, side 7.5, street side 12, rear 20, height 35 or 2 storeys, FAR 0.40,
  parking not between building and street (west-linn.yaml#L2323-L2408, `59.mu.txt#L204-L241`). Not encoded:
  max lot 10,000 sf, min FAR 0.30, max building 6,000 sf, ground floor 5,000 sf (#L2409-L2418). Non-screenable: 3 (porch, garage-forward, Ch 55 menu).
- Boundary: have (is the zone).
- FLATS today: encoded (west-linn.yaml#L2294).
- Lots: 25 (coverage.csv, MU)
- Note: no MU lot is >= 90% inside the WHD (#L2418).

## Tualatin

### Tualatin — Central Tualatin Overlay, CTO (TDC Chapter 58), with Residential Sub-District, Commercial Sub-District, Central Design District, numbered blocks
- Cite: `or/clackamas/tualatin/58.central-tualatin-overlay.txt#L20-L22` (boundary = Comprehensive Plan Map 10-3)
- Kind: overlay / plan district (block-keyed sub-districts)
- Zones covered: CC, CG, CO, ML, MG, RH, RH-HR. Pod permitted by base zone only in RH/RH-HR (townhouse
  unit lots only); CTO OPENS it in CC Residential Sub-District and CO Block 1.
- Reach (quadplex): reaches — CC Residential Sub-District, Household Living P (L): "Townhouses; Duplexes;
  Triplexes; Quadplexes" (`#L31-L34,L43-L48`); RH/RH-HR blocks via Table 58-7 (`#L283-L285,L334-L354`).
  CO Block 1: no — "Townhouse; and Multi-Family Structure" (`#L133-L136`), and a Multi-Family Structure is 5+ units (TDC 31.060, per tualatin.yaml#L1630-L1636).
- Reach (townhouse unit lots): reaches — CC Residential Sub-District (`#L45`); CO Block 1 "Townhouse" (`#L134`), "Lot sizes for townhouses must conform to the lot size standards of the RH District" (`#L326-L328`).
- Screenable:
  - CC Residential Sub-District density 16-25 du/ac; min lot width 40; at street 40; cul-de-sac 35 (`#L295-L309`)
  - CO density 16-25; min lot 25,000 (townhouse lots per RH) (`#L325-L328`)
  - RH density 16-25; Block 25 min lot 40,000; height 45 when mixed with CC uses (`#L335-L348`)
  - RH/HR density 26-30; Blocks 31, 33 min lot 40,000; Block 26 25,000 (`#L350-L354`)
  - CG 25,000 sf / 100 ft; ML/MG block lot sizes (`#L311-L333`) — pod refused there
  - Non-screenable: 3 (retirement-housing conditions, architectural focal elements, drive-through bans)
- Boundary: have (part) — Residential Sub-District traced: flats/config/areas/or/clackamas/tualatin/residential-sub-district.geojson
  (drawn_areas, tualatin.yaml#L2110-L2143, from Map 10-3 supplied by Steph; "The city's public GIS has no block layer").
  Missing: CO Block 1, RH Blocks 4/25, RH-HR Blocks 26/31/33, Central Design District (Figure 73-4 / Urban Renewal Map 8) — same Map 10-3.
- FLATS today: CC encoded with `inside_mapped_use_area` variant (tualatin.yaml#L1508-L1630); RH/RH-HR block
  standards deliberately deferred: "every RH and RH-HR lot is red in run 69 on other grounds ... trace them
  before either zone shows a green" (#L1665-L1676, FOLLOWUPS 52); CO refused flat with no Block 1 variant
  (#L1259-L1266) — Block 1 townhouse permission never mentioned.
- Lots: CC 155 — "91 lie inside the Residential Sub-District as traced ..., 64 outside" (tualatin.yaml#L1510-L1511); CO 46 total, Block 1 share unknown; RH 198, RH/HR 6 (coverage.csv).
- Note: CO Block 1 is a latent false RED on the townhouse path (one block). Tualatin 73A residential design is city-wide, not a district. MUC (Ch 57) is an ordinary zone, encoded (tualatin.yaml#L2024). Leveton TID / Commercial Services Overlay sit in MG (no housing).

## Wilsonville

### Wilsonville — Village Zone V = Villebois (4.125), incl. Village Center sub-area
- Cite: `or/clackamas/wilsonville/4.planning.txt#L4779`
- Kind: zone-chapter / master plan (SAPs, Pattern Book; V confined to the Villebois Master Plan boundary, `#L6466`)
- Zones covered: V. Pod permitted: "C. Duplexes, Triplexes, and Quadplexes" (`#L4798`), "D. Row Houses" (`#L4799`).
- Reach (quadplex): reaches — (.23)(B) "The standards of Table V-1 for single-family dwellings apply with the
  following exceptions ... 3. The minimum lot size for quadplexes ... is 7,000 square feet" (`#L6449-L6455`).
- Reach (townhouse unit lots): reaches — Row Houses rows of Table V-1 (`#L5018,L5022`; Village Center row differs, Figure 2A, `#L5043`).
- Screenable (encoded, wilsonville.yaml#L2832-L2978): min lot 7,000; width 35; depth 50; height 35; front 20
  (12 on local street); front MAX 20 (build-to); rear 5; side 5; combined side 15 on lots >= 70 ft; street
  side 15; coverage 45; alley access required. Not encoded: 25% open space outside yards (.08)(A); Minimum
  Building Frontage Width 60% (build-to share); garage notes. Non-screenable: Pattern Book styles/patterns/fencing (~3 classes).
- Boundary: have (is the zone; Village Center sub-area boundary missing — Master Plan Figure 2A).
- FLATS today: encoded, needs_verification (wilsonville.yaml#L2979-L3058); street-class Collector Avenues are the master plan's, not the TSP's (flats/geom/street_class.py#L184-L192).
- Lots: 2,370 (coverage.csv V)
- Note: (.23) opens "For lots previously developed with at least one residential unit" (`#L6439`); FLATS
  applies its 7,000 sf route to every V lot, vacant ones included — a vacant V lot may instead fall to the
  SAP/PDP/FDP process. Townhouse (Row House) path not encoded.

### Wilsonville — Residential Neighborhood RN = Frog Pond (4.127)
- Cite: `or/clackamas/wilsonville/4.planning.txt#L6476`
- Kind: zone-chapter / master plan (Frog Pond West/East/South; sub-district Figure 6)
- Zones covered: RN.
- Reach (quadplex): no — "triplexes are permitted only on corner lots, and quadplexes are not permitted" (`#L6498-L6505`).
- Reach (townhouse unit lots): no — 4.127(.02)B.1.a.i caps attached units at two (three on a corner) during initial development (wilsonville.yaml#L2819-L2831).
- Screenable: Table 8A encoded at the R-10 row (wilsonville.yaml#L2639-L2780); Table 8B (East/South, max building width) unread.
- Boundary: have (zone); sub-district Figure 6 missing ("nothing published carries it", wilsonville.yaml#L2772-L2779).
- FLATS today: encoded RED (wilsonville.yaml#L2647-L2652).
- Lots: 580 (coverage.csv RN)
- Note: revisit when Frog Pond East/South lots appear (Table 8B).

### Wilsonville — Town Center TC (4.132), 4 sub-districts
- Cite: `or/clackamas/wilsonville/4.planning.txt#L8267`
- Kind: zone-chapter (Main Street, Neighborhood-Mixed Use, Mixed Use, Commercial-Mixed Use)
- Zones covered: TC. Only "Multiple-family Dwelling Units", defined to exclude middle housing.
- Reach (quadplex): no — 4.001(96) multi-family "where ... the dwelling units are not middle housing" (wilsonville.yaml#L3060-L3074, `#L572-L574,L8314,L8318`).
- Reach (townhouse unit lots): no (same; no townhouse in 4.132).
- Screenable: not encoded (use refused). Non-screenable: n/a.
- Boundary: have (zone).
- FLATS today: encoded RED (wilsonville.yaml#L3059-L3124).
- Lots: 60 (coverage.csv TC)
- Note: none.

### Wilsonville — Old Town Residential OTR (4.123)
- Cite: `or/clackamas/wilsonville/4.planning.txt#L4484`
- Kind: zone-chapter (Old Town neighbourhood)
- Zones covered: OTR; "B. Middle Housing" permitted (`#L4497`).
- Reach (quadplex): reaches — "(.06) ... Development shall comply ... with the standards of the Old Town
  Residential Design Standards Book including but not limited to architectural design, height, setbacks, and lot coverage" (`#L4528-L4531`).
- Reach (townhouse unit lots): reaches — same; townhouse lots 1,500 sf, cumulative 7,000 for four, frontage 20 (`#L4511-L4527`).
- Screenable: lot width 35; frontage 35 / 20 townhouse; min lot 7,000 (encoded, wilsonville.yaml#L1662-L1765). Height, setbacks, coverage: in the Book, not stored.
- Boundary: have (zone).
- FLATS today: encoded, needs_verification; setbacks are the 4.113 citywide default "absent the book" and height/coverage deliberately absent (wilsonville.yaml#L1766-L1773).
- Lots: 103 (coverage.csv OTR)
- Note: fetch the OTR Design Standards Book.

### Wilsonville — Old Town (O) Overlay Zone (4.138)
- Cite: `or/clackamas/wilsonville/4.planning.txt#L11315`
- Kind: overlay (design; "mapped as the Boones Ferry District in the City's West Side Master Plan", `#L11317`)
- Zones covered: "applied in conjunction with the underlying base zones in the Old Town neighborhood" (`#L11343`) — OTR at least; possibly R/PDR/PDC lots in the district (unknown).
- Reach (quadplex): reaches — "(.03) B ... reviewed through the Class I administrative review process ... 1. New
  single-family homes and middle housing" (`#L11361-L11366`); "(.04) A. The standards of this subsection shall
  take precedence over setback, lot coverage, height ... B. Development shall comply ... with the standards of
  the Old Town Residential Design Standards Book" (`#L11367-L11375`). Middle housing includes quadplexes and townhouses (`#L181` def at 4.001, "181. Middle Housing").
- Reach (townhouse unit lots): reaches — same; "zero setbacks for attached townhouses shall continue to apply" (`#L11370-L11371`).
- Screenable: (.05) applies to multi-family/commercial site design review, not the Class I middle-housing
  path: Boones Ferry Rd frontage buildings abut the sidewalk; garages 20 ft from sidewalk; 15% landscaping;
  up to 40% of frontage for parking (`#L11413-L11456`). For the pod the numbers are in the unstored Book.
  Non-screenable: ~6 (1880-1930 styles, entrances, pedestrian amenities, storefronts).
- Boundary: missing — West Side Master Plan Boones Ferry District map; Wilsonville GIS (gis.wilsonvillemaps.com, pipeline.yaml#L404-L411) may hold an overlay layer. Zone codes in coverage.csv carry no "-O" suffix.
- FLATS today: dismissed — card `4.planning.txt#4.138` queue nofield, outcome other_building: "4.138 appears in
  no Wilsonville zone's section list, so it reaches none of the land this layer screens" (wilsonville.yaml#L743-L752).
  That is a section-list argument for a geographic overlay; the overlay names middle housing.
- Lots: unknown (>= the OTR share of 103)
- Note: low lot count, but the dismissal reasoning is wrong; OTR is already needs_verification on the same Book, so any non-OTR zone under the overlay is the exposure.

### Wilsonville — Coffee Creek Industrial Design Overlay District (4.134)
- Cite: `or/clackamas/wilsonville/4.planning.txt#L9465`
- Kind: overlay (industrial design, inside PDI-RSIA)
- Zones covered: PDI-RSIA (refuses the pod).
- Reach (quadplex): no — "an overlay district within the Planned Development Industrial - Regionally Significant Industrial Area (RSIA) Zone" (`#L9467-L9468`); none of the zones admitting a quadplex is inside it (wilsonville.yaml#L111-L120).
- Reach (townhouse unit lots): no (same).
- Screenable: Table CC-4 min height 30 ft (would fail the pod; wilsonville.yaml#L110-L120). Non-screenable: many.
- Boundary: missing (Figure CC-1); not needed.
- FLATS today: ruled not reaching (wilsonville.yaml#L109-L120; card 4.134 #L674-L686).
- Lots: 10 (coverage.csv PDI-RSIA)
- Note: none. Also not counted as a district: IAMP Overlay (4.133, access management only, Figure I-1, `#L9234-L9248`); PDR zones (planned-development zones, city-wide); S solar overlay (no label carries it).

## Lake Oswego (switched off: eligible:false, 14,276 lots absent)
- Downtown Redevelopment Design District (LOC 50.05.004), EC zone — cross-ref only, `or/clackamas/lake-oswego/50.04.dimensional.txt#L1957`. Not stored.
- Lake Grove Village Center Overlay District — "Standards in this table may be modified by the Lake Grove Village Center Overlay District" (`50.04.dimensional.txt#L1890`). Not stored.
- West Lake Grove Design District / WLG zones — "West Lake Grove Zones. The following dimensions are applicable in the West Lake Grove zone districts" (`50.04.dimensional.txt#L1961-L1963`); WLG overlay figures (`#L2005`). Zone-chapter; WLG use rows in `50.03.002.use-table.txt#L1274`.
- One line overall: all three matter only if Lake Oswego is switched back on (HUMAN_TODO 16).

## Rivergrove (switched off) — no district: only a flood overlay is mentioned (`or/clackamas/rivergrove/rldo.composite.txt#L13`).

## Johnson City (switched off) — no district; only ORS 197A.420 stored.

---

## Jurisdictions with no district found
- Rivergrove, Johnson City (above). Grepped stored text for: design district, design overlay, overlay zone/district,
  plan district, plan area, town center, main street, downtown, village, sub-district, subarea, applicability.
- Also excluded by rule (not districts): Canby 16.49 site and design review and 16.21.070 multi-family design
  (city-wide); Sandy 17.90.150/160 residential/multi-family design (city-wide), CHR and FSH overlays;
  Estacada H-R (designated resources only), W-R, ASC, P-D overlays; Tualatin 73A (city-wide), NRPO/wetlands;
  West Linn HL landmarks, WRG, TRP, WRA, FMA; Wilsonville SROZ, SB overlay.

## Things the coordinator should know
1. Wilsonville 4.138 Old Town Overlay is dismissed on a section-list argument, but the text puts middle
   housing (quadplex and townhouses) under the unstored Old Town Residential Design Standards Book for height,
   setbacks and coverage. Boundary not held.
2. Wilsonville V: (.23) is written for "lots previously developed with at least one residential unit"; FLATS
   uses it on every Villebois lot.
3. Estacada D is a likely false RED already queued (FOLLOWUPS 53(f), awaiting Steph); it may also be missing
   from the regional fabric's Estacada spellings.
4. Canby DCO-TC and Tualatin CO Block 1 are small, known-shape false REDs (no boundary traced).
5. Sandy BVO is unheld; its row-house width (20-30 ft) would refuse the townhouse form inside it.
6. West Linn WHD is the model case (drawn + measured, 71 lots); small cleanups: stale comment west-linn.yaml#L1464, R-2.1 absent from drawn_areas zones.

## 5. Detail — dd_washington.md

### Design districts — Washington County (dd-washington, 2026-10-21)

All doc paths are relative to `flats/provenance/docs/`. Config paths are relative to the repo root.

Facts that hold across the county:

- **No Washington district has a drawn boundary.** `flats/config/areas/` contains only clackamas/tualatin, clackamas/west-linn and multnomah/gresham, and no Washington yaml has a `drawn_areas:` block. Most districts here are their own zone codes, so the zone is the boundary. The exceptions are flagged below.
- **`inside_mapped_use_area` is unknown on every lot** ("Measured only where a layer draws the area", `flats/rules/conditions.py` DRAWN_CONDITIONS ~L1112). Variants keyed on it therefore read unknown everywhere. They never read false.
- **Tigard and Cornelius per-zone lot counts are missing.** Both were switched to Metro `rlis_zoning_metro` on 2026-10-07 (`flats/config/pipeline.yaml`). coverage.csv (2026-10-01) gives only the jurisdiction totals: UNMAPPED/tigard 18,953 and UNMAPPED/cornelius 4,256. Metro's ZONE "draws no plan district subarea or subdistrict" (`flats/config/jurisdictions/or/washington/tigard.yaml#L4-L14`).
- **Every Hillsboro zone is YELLOW** (`review_discretion: conditions`, 12.80.040; Steph 2026-10-14). An unencoded Hillsboro district rule cannot make a false GREEN today.

---

## Tigard

The yaml says "THE POD IS A ROWHOUSE here": Tigard's "Quad" is stacked 2-over-2, so the pod is screened as rowhouses (`flats/config/jurisdictions/or/washington/tigard.yaml#L4-L14`).

### Tigard — Bridgeport Village Plan District (18.620)
- Cite: `or/washington/tigard/tdc.18.620.bridgeport.txt#L25`
- Kind: plan district (about 7 acres, L17)
- Zones covered: MUC. Rowhouses Y in MUC.
- Reach (quadplex): n/a. Tigard screens the pod as rowhouses.
- Reach (townhouse unit lots): reaches. "Rowhouse development in the Bridgeport Village Plan District is subject to the standards of Chapter 18.620" (`or/washington/tigard/tdc.18.280.rowhouses.txt#L45`)
- Screenable:
  - residential max front setback = 20 ft, "Except as determined in the architectural review process" (L71)
  - min height = 20 ft (L75)
  - max height = 70 ft
  - lot coverage = 90%
  - landscape = 10%
  - min density = 25 du/net acre for residential-only (L99)
  - parking not between primary structure and street (L243)
  - front entrances oriented to the street (18.620.080)
- Non-screenable: ~10
- Boundary: missing. Likely source is Map 18.620.A (L285). The text also says the district is "on the official zoning map" (L25), but Metro's layer carries only MUC.
- FLATS today: mentioned in a comment only, not encoded (`tigard.yaml#L1114-L1118`).
- Lots: unknown (part of the MUC lots; Tigard has no per-zone count)
- Note: the 20 ft minimum height is under the pod's 25–30 ft, so it is harmless. The max front setback and parking location are real checks, but this is a 7-acre built-out site.

### Tigard — River Terrace Plan District (18.640)
- Cite: `or/washington/tigard/tdc.18.640.river-terrace.txt#L47`. The district applies "in addition to, and not in lieu of" the base zones.
- Kind: plan district
- Zones covered: River Terrace residential base zones. Rowhouses are permitted there.
- Reach (quadplex): n/a (rowhouse city)
- Reach (townhouse unit lots): reaches, on Boulevard lots. 18.640.060 applies to "All small form residential and rowhouse development" on lots abutting River Terrace Boulevard ROW (L279-L283).
- Screenable:
  - "Direct individual access to River Terrace Boulevard from rowhouse… not allowed" (L273-L388)
  - no parking lots within 40 ft of the Boulevard ROW (same span)
  - lot must abut the Boulevard with a front or side line (same span)
  - funding gate (18.640.030.B, L59)
- Non-screenable: ~6. These include the elective density bonus (Table 18.640.1) and the PD-only 20% common open space (18.640.070).
- Boundary: missing. Likely source is Map 18.640.A (L1161) / 18.640.B (L1163).
- FLATS today: "NOT ENCODED: River Terrace (18.640)" (`tigard.yaml#L352-L360`). Only the 110 ft Boulevard ROW is held, as `row_to_centerline_named_ft` (`tigard.yaml#L302-L311`).
- Lots: unknown
- Note: the access ban bites only lots on the Boulevard. A named-street fact could screen it.

### Tigard — Downtown / MU-CBD (18.650)
- Cite: `or/washington/tigard/tdc.18.650.downtown.txt#L455-L457`
- Kind: zone-chapter (MU-CBD, with subareas MS, 99H, SC and FB on Map 18.650.A)
- Zones covered: MU-CBD. Rowhouses Y (Table 18.650.2). 18.280.020.C takes the rowhouse chapter away.
- Reach (quadplex): n/a
- Reach (townhouse unit lots): reaches. The first story must be at least 15 ft in MS and 99H (L455-L457, L471).
- Screenable (all encoded, strictest of the four subareas):
  - min height = 20
  - max front setback = 10/25/20 (strictest held)
  - `orientation_constraint` axis_required (18.650.080.A, L582, L614)
  - `parking_front_prohibited` (L488-L492)
  - `parking_area_max_frontage_pct` = 50
  - parking street setback = 10
  - min density = 25
  - coverage and landscape
- Non-screenable: ~20
- Boundary: zone = have (MU-CBD in Metro ZONE). Subareas missing; likely source is Map 18.650.A.
- FLATS today: encoded (`tigard.yaml#L1235-L1356`). The 15 ft first story is encoded as quadplex_allowed false `when: [inside_mapped_use_area]` (`tigard.yaml#L1265`).
- Lots: unknown
- Note: the subarea map would turn the unknown MS/99H variant into a measured answer.

### Tigard — Tigard Triangle / TMU (18.660)
- Cite: `or/washington/tigard/tdc.18.660.triangle.txt#L132`. The chapter applies in lieu of the rest of the title.
- Kind: zone-chapter
- Zones covered: TMU. Rowhouses are permitted.
- Reach (quadplex): n/a
- Reach (townhouse unit lots): reaches (the whole chapter governs TMU)
- Screenable (encoded):
  - min front = 1 ft
  - max front = 12 ft for 70% of the facade
  - min ground story = 12 ft
  - max = 4 storeys
  - parking behind the building or ≥35 ft from street lines
  - rowhouse driveway ≤10 ft (Steph 2026-10-01)
  - street-facing entrance
- Non-screenable: ~15
- Boundary: zone = have. Map 18.660.A (height areas) is not held.
- FLATS today: encoded (`tigard.yaml#L1396-L1468`)
- Lots: unknown
- Note: none.

### Tigard — Washington Square Regional Center (18.670)
- Cite: `or/washington/tigard/tdc.18.670.wsrc.txt#L60-L71`
- Kind: plan district, with subdistricts, over MUC, MUE and MUR
- Zones covered: MUC, MUR, MUE. "Property within the Residential-B (RES-B) zone or the Parks and Recreation (PR) zone is exempt from the provisions of this chapter" (L60-L63).
- Reach (quadplex): n/a
- Reach (townhouse unit lots): reaches.
  - Table 18.670.2 makes Rowhouses L in MUC and MUR (L453-L468).
  - "Rowhouses are allowed only in the Design Review Subdistrict" (E.1.a).
  - The Metzger Business Subdistrict allows only mixed use (E.1.b).
  - The Apartment Subdistrict allows only apartments and mixed use (E.2, L471-L487).
  - In the Design Review Subdistrict, residential development needs a minimum of four storeys plus 20% affordable (18.670.090.B, L760-L777).
- Screenable:
  - use prohibition by subdistrict (above)
  - 4-storey minimum (L773-L777)
- Non-screenable: ~25. Residential design defers to the housing-type chapter (18.670.080.A.2, L640).
- Boundary: missing. Subdistricts are "not on the zoning map" (L71). Likely source is Map 18.670.A.
- FLATS today: encoded as MUR/MUC quadplex_allowed false `when: [inside_mapped_use_area]` (`tigard.yaml#L996`, `#L1138`; notes `#L965-L983`, `#L1114-L1124`). Because that condition reads unknown on every lot, every Tigard MUC/MUR lot is unknown, never green, until the WSRC map is drawn.
- Lots: unknown
- Note: the pod (2 storeys) cannot be placed anywhere inside WSRC MUC/MUR. Drawing Map 18.670.A would free every MUC and MUR lot outside it.

---

## Cornelius

18.80 MSC and 18.85 MSDO print only "(Repealed by Ord. 2019-10)" (`or/washington/cornelius/cmc.18.80.msc.txt`, `cmc.18.85.msdo.txt`). The yaml notes this (`flats/config/jurisdictions/or/washington/cornelius.yaml#L241-L247`, `#L1567`).

### Cornelius — Central Mixed Use / town centre (18.60)
- Cite: `or/washington/cornelius/cmc.18.60.cmu.txt#L17`. CMU covers "the heart of the town center and historic city center".
- Kind: zone-chapter
- Zones covered: CMU. Dwellings are permitted only "above ground floor" (L59); ground-floor dwellings are a conditional use (L105).
- Reach (quadplex): reaches (whole-zone chapter)
- Reach (townhouse unit lots): reaches
- Screenable:
  - front setback = 0 min / 10 max (L195)
  - street side max = 10 (L199)
  - max height = 3 storeys / 40 ft, or 4 storeys / 60 ft on Adair or Baseline (L211)
  - min height = 16 ft (L219)
  - full parcel frontage on Adair/Baseline (L227-L243)
  - parking to the side or rear, none between building and street (L449)
  - 25% parking reduction (L441)
- Non-screenable: ~20 (entrances, weather protection, windows, materials; L249-L381)
- Boundary: zone = have (70 Metro polygons)
- FLATS today: encoded as a use only. quadplex_allowed false, with a conditional_use variant true (ORS 197A.400; Steph 2026-10-15). "No dimensional standard is encoded … its lots read UNKNOWN" (`cornelius.yaml#L1328-L1347`).
- Lots: unknown
- Note: the dimensional rules are clean numbers and could be encoded quickly. Today the lots read UNKNOWN, not wrong.

### Cornelius — Commercial Core (18.65)
- Cite: `or/washington/cornelius/cmc.18.65.cc.txt#L67`
- Kind: zone-chapter (town centre)
- Zones covered: CC
- Reach (quadplex): reaches, as a use limit (L67, L125: 50 ft from Adair/Baseline)
- Reach (townhouse unit lots): reaches (same)
- Screenable: distance from Adair/Baseline = 50 ft (L125)
- Non-screenable: ~15
- Boundary: zone = have
- FLATS today: refused (`cornelius.yaml#L1306-L1327`). Steph said to keep the refusal.
- Lots: unknown
- Note: none.

### Cornelius — Gateway Mixed Use (18.75)
- Cite: `or/washington/cornelius/cmc.18.75.gmu.txt#L469-L475`
- Kind: zone-chapter with subdistricts
- Zones covered: GMU. The fourplex is refused (not multi-family; Steph 2026-10-01). "Single-family attached residential uses (townhouses) shall only be permitted within subdistrict A… up to 50 percent" (L475).
- Reach (quadplex): no (use refused, per the ruling above)
- Reach (townhouse unit lots): reaches (subdistrict A only)
- Screenable:
  - lot = 2,000 sf, 20 ft wide
  - density = 18 du/net acre
  - front = 5
  - height = 35 ft
  - landscaped = 15%
  - covered parking required (fails the pod)
- Non-screenable: ~15
- Boundary: missing for subdistricts. Likely source is Figure 18.75.065-1 (L469-L471). The zone is in Metro (18 polygons).
- FLATS today: encoded with unit_lots and an `inside_mapped_use_area` variant (`cornelius.yaml#L1409-L1517`, variant `#L1420`)
- Lots: unknown
- Note: the covered-parking rule fails the pod anyway.

---

## Durham

### Durham — Multi-Dwelling Design Overlay (2.10)
- Cite: `or/washington/durham/ddc.2.zoning-districts.txt#L125-L137`
- Kind: overlay
- Zones covered: MDR, applied by a Type 3 zone change. The underlying MDR is refused in FLATS, but MDR 2.9.1.7 permits "Single dwelling attached residence" outright.
- Reach (quadplex): unclear. Its standards are discretionary, with density/height bonuses (`ddc.3.site-design.txt#L123-L205`).
- Reach (townhouse unit lots): unclear (same text)
- Screenable: none clear and objective
- Non-screenable: ~10
- Boundary: missing. "Not on Metro's map"; it is applied site by site by zone change.
- FLATS today: quadplex_allowed false (`flats/config/jurisdictions/or/washington/durham.yaml#L542-L557`)
- Lots: 0 mapped (MDR 3)
- Note: negligible impact. The townhouse path in MDR is worth one look (`durham.yaml#L529-L541` refuses MDR conservatively).

---

## King City

### King City — Kingston Terrace Plan District (16.114)
- Cite: `or/washington/king-city/kcc.16.114.kingston-terrace.txt#L47-L50`. The district applies "only to properties within the Kingston Terrace Plan District boundary as shown on Figure 16.114-1".
- Kind: plan district (zones KTTC, KTBB, KTC, KTRC). Fourplex is Y in all four (L150).
- Zones covered: as above. 16.114.150 B.2 allows middle housing on an existing lot outright, exempt from development plan review.
- Reach (quadplex): reaches. Table 16.114-5 has a column for "Dwelling, single-family attached, Duplex, Triplex, Fourplex" (L377-L386).
- Reach (townhouse unit lots): reaches (same column)
- Screenable:
  - max front = 26
  - min front = 10
  - garage = 18
  - impervious = 90/80%
  - min net density = 22/18/10/8 (all encoded)
  - main entrance facing the street, within 8 ft of the longest street-facing wall (L487-L496), not encoded
- Exemptions:
  - common open space "do not apply to … fourplex" (L620-L621)
  - private open space applies only to multi-dwelling/mixed use (L578)
  - the 60%/40% frontage table (Table 16.114-6) applies only to multi-dwelling/mixed-use/commercial (L457-L478)
  - no parking minimums (16.114.130)
- Non-screenable: ~12. These are the 16.114.060 articulation, eyes-on-street, detailed design and transitional-space standards.
- Boundary: zone = have (city layer 4)
- FLATS today: encoded (`flats/config/jurisdictions/or/washington/king-city.yaml#L603-L1000`; KTTC `#L708`, KTBB `#L781`, KTC `#L854`, KTRC `#L927`). The 16.114.060 design standards are NOT ENCODED.
- Lots: 396 (KTTC 389 + KTBB 7; KTC and KTRC have no rows)
- Note: none.

### King City — Neighborhood Mixed Use (16.102)
- Cite: `or/washington/king-city/kcc.16.102.nmu.txt` (16.102.020 A)
- Kind: zone-chapter
- Zones covered: NMU. There is no fourplex, but the zone permits "Dwelling, single-family attached and detached 0-foot side yard".
- Reach (quadplex): no (no fourplex use; yaml refusal)
- Reach (townhouse unit lots): unclear. The townhouse path may be open.
- Screenable: not read
- Boundary: zone = have
- FLATS today: refused (`king-city.yaml#L563-L575`)
- Lots: 20
- Note: small.

---

## Sherwood

### Sherwood — Old Town Overlay / historic district (16.162)
- Cite: `or/washington/sherwood/sdc.16.162.old-town.txt#L16-L30` ("designated a historic district"). It has two areas, Smockville and Old Cannery.
- Kind: overlay + historic district
- Zones covered: underlying RC, HDR and MDRL uses (L46-L53).
  - RC apartments are allowed only upper/rear (L62).
  - Townhouses on RC in Old Cannery are a conditional use (L79).
- Reach (quadplex): reaches. Smockville standards apply to "new development", with the Landmarks Advisory Board deciding (L400-L430).
- Reach (townhouse unit lots): reaches (same)
- Screenable:
  - RC min lot = 2,500 sf, no yards (L102-L110)
  - height = 40 ft / 3 storeys in Smockville, 50 / 4 in Cannery (L113-L119)
  - min height = 16 ft in RC/HDR (L124-L125)
  - parking: none required in Smockville, 65% in Cannery (L148-L154)
  - "Single large volumes are prohibited"; at least 2 intersecting volumes; max 40 ft; ridge ≥16 ft (L776-L789)
- Non-screenable: ~30
- Boundary: have (the overlay is on the city layer, 44.7 acres). The underlying base zone is missing.
- FLATS today: zone ruling "Old Town: outcome: unencodable" — "none of its use, height or design exceptions is encoded; a lot here stays open until the base zone is mapped" (`flats/config/jurisdictions/or/washington/sherwood.yaml#L1318-L1333`)
- Lots: 117 (coverage "Old Town", zone_missing)
- Note: the blocker is the missing base zone, not the overlay. Landmarks Board review makes this judgement-only.

---

## Hillsboro

The layer-wide comment covers all of Hillsboro's plan districts: "NOT ENCODED: the plan districts (Subchapters 12.61 to 12.68)" (`flats/config/jurisdictions/or/washington/hillsboro.yaml#L438-L466`).

- 12.50.710 B.2 removes the small-lot relief on design standards inside a plan district (`or/washington/hillsboro/cdc.12.50.700-920.design.txt#L16-L19`).
- Definitions: a quadplex on 4 child lots "created through a middle housing land division" is still a quadplex (`or/washington/hillsboro/cdc.12.01.general.txt#L910-L912`). A townhouse is a unit on its own lot (L921-L923).

### Hillsboro — Downtown Plan District (12.61)
- Cite: `or/washington/hillsboro/cdc.12.60-61.downtown.txt#L78-L85` (Figure 12.61.200-A)
- Kind: plan district
- Zones covered: SCC-DT (refused: 12.50.350 D.1 parking inside the structure), SCR-HD, SCR-MD, SCR-LD, SCR-DNC
- Reach (quadplex): reaches. "All new development is subject to the Architectural Conservation Standards in Section 12.61.800" (SCR-DNC, L478-L479). 12.61.800 A.1 applies "in the Downtown Plan District as shown on Figure 12.61.200-A" (L605-L610).
- Reach (townhouse unit lots): reaches (same)
- Screenable:
  - SCC-DT frontage = 50/75/100% (Table 12.61.400-1, L277-L289), not encoded
  - SCC-DT 2-storey minimum (L322-L325), encoded
  - SCC-DT parking not between building and street, encoded
  - 10 ft setback from SCR lines, encoded
  - SCR-HD/MD 10 ft from SCC-DT
  - SCR-DNC average front setback (D)
  - alley access "wherever practicable" (12.61.300 B)
  - garage offset 5 ft (12.61.800)
- Non-screenable: ~20 (porches, foundations 24–32", materials)
- Boundary: zone = have (DESCRIPTIO zone codes). Arterial Exception Area missing; likely source is a Figure in 12.61.700.
- FLATS today: SCR-DNC encoded (max front 25, 2.5 storeys; `hillsboro.yaml#L1248-L1370`). SCC-DT refused (`#L2039-L2160`). Everything else is in the NOT ENCODED comment. All zones are YELLOW.
- Lots: up to 2,874 (SCC-DT 541 + SCR-DNC 305 + SCR-MD 1,437 + SCR-HD 177 + SCR-LD 414). SCR-* zones may also sit outside Downtown.
- Note: none.

### Hillsboro — Orenco Plan District (12.62)
- Cite: `or/washington/hillsboro/cdc.12.62.orenco.txt#L60-L66`
- Kind: plan district
- Zones covered: SCR-OTC, SCR-V, SCC-SC, SCI (SCI refused)
- Reach (quadplex): reaches. "triplexes, quadplexes, and cottage clusters are not permitted on lots smaller than 7,500 square feet" (L93-L97). 12.62.400 Architectural Conservation applies to new construction in SCR-OTC (L420+).
- Reach (townhouse unit lots): reaches (12.62.400 in SCR-OTC). In the 12.62.500 Sunset Downs lots, townhouses are exempt.
- Screenable:
  - min lot = 7,500 sf for a quadplex (encoded via SCR-OTC min lot)
  - alley setback = 16 ft
  - required porch = 80 sf, 5 ft deep
  - garage at the rear
  - NE 67th front up to 40 ft
  - Orenco Station sub-area lots of 6,800–10,000 (12.62.500)
- Non-screenable: ~15
- Boundary: zone = have. The 12.62.500 sub-area is missing.
- FLATS today: SCR-OTC encoded YELLOW (`hillsboro.yaml#L1095-L1247`, Orenco note `#L1120-L1121`)
- Lots: 1,534 (SCR-OTC 211 + SCR-V 1,298 + SCC-SC 15 + SCI 10)
- Note: none.

### Hillsboro — AmberGlen Plan District (12.64)
- Cite: `or/washington/hillsboro/cdc.12.64.amberglen.txt#L79-L90` (Figure 12.64.020-A)
- Kind: plan district
- Zones covered: UC-RM, UC-MU, UC-RP (quadplex allowed); UC-AC, UC-NC, UC-OR (refused, with Retail Focus variants)
- Reach (quadplex): reaches.
  - Parking standards apply to "All new construction in the Amberglen Plan District" (12.64.310 A.1, L604-L606).
  - 12.64.800 applies "In the UC-RM, UC-MU, UC-AC, UC-NC, and UC-OR zones; to all new development" (12.64.820 A.1, L1519-L1522).
  - It does not apply in UC-RP (A.4).
- Reach (townhouse unit lots): reaches (same)
- Screenable:
  - "Surface parking is Not Permitted between the street-facing façade line and the street" (L778)
  - side parking ≥50 ft from street (L775)
  - usable open space = 100 sf/du (Table 12.64.210-1, ~L262)
  - height transitions of 35/55/65 ft by distance (L1536-L1547)
  - Front Property Line Coverage (12.64.130, L225)
  - vehicle maximum 2/unit (L629-L630)
- Non-screenable: ~20
- Boundary: zone = have. Retail Focus Frontage Areas (Figure 12.64.640-A) are missing.
- FLATS today: UC zones encoded with setback_front_max_ft and min_building_height_ft (UC-RM `hillsboro.yaml#L2978`). Retail Focus is an `inside_mapped_use_area` variant (`#L3249`, `#L3375`, `#L3495`). The 12.64.360 parking-location rule is NOT ENCODED (no parking_front_prohibited in UC-RM/UC-MU). Front coverage is NOT ENCODED (`#L2427-L2430`).
- Lots: 176 (UC-RM 82 + UC-MU 42 + UC-AC 5 + UC-NC 5 + UC-OR 38 + UC-RP 4)
- Note: the parking rule is one field away (`parking_front_prohibited: true` in UC-RM/UC-MU/UC-RP). It is masked today by Hillsboro's YELLOW.

### Hillsboro — South Hillsboro Plan District (12.65)
- Cite: `or/washington/hillsboro/cdc.12.65.south-hillsboro.txt#L69-L71` ("apply only within the South Hillsboro Plan District boundary as shown on Figure 12.65.930-A")
- Kind: plan district
- Zones covered: R-10, R-8.5, R-7, R-6, R-4.5, MR-1, MR-2, MR-3, MU-VTC (Table 12.65.020-1, L74-L90). The pod is allowed in all of them.
- Reach (quadplex): reaches. "The design standards in this section apply to all single detached residential, duplex, triplex, quadplex, townhouse, cottage cluster, and multi-dwelling development in the South Hillsboro Plan District" (12.65.710 B.2, L1184-L1186).
- Reach (townhouse unit lots): reaches. "all single detached, townhouse, and duplex developments shall provide vehicle access to all lots and units from an alley" (12.65.520 F, L1051-L1054).
- Screenable:
  - townhouse alley access required (L1051-L1054)
  - solar orientation: quadplex lots under 50 ft wide must have side lines ±20° of east-west (12.65.270 C, L815-L817)
  - flag lots prohibited in MU-VTC (L1097), encoded
  - 35 ft setback from TV Highway / railroad ROW (L517)
  - garage/parking ≤40% of the street facade and 5 ft behind the front wall where there is no alley (L1275-L1280)
  - Active Use Street standards (12.65.850, Figure 12.65.930-A)
- Non-screenable: ~25
- Boundary: missing. The plan-district zones are the citywide R-/MR- codes. Likely source is Figure 12.65.930-A, or Hillsboro's Community_Development FeatureServer (pipeline.yaml `zoning_hillsboro` host).
- FLATS today: NOT ENCODED, layer comment (`hillsboro.yaml#L454-L458`). MU-VTC flag-lot rule encoded (`#L2741-L2756`).
- Lots: unknown (MU-VTC 211 is wholly inside; the R-/MR- share is unknown)
- Note: the pod dodges the townhouse-alley rule by staying a "quadplex" on child lots (12.01 L910-L912). A townhouse plat without an alley fails, and FLATS already measures abuts_alley.

### Hillsboro — Witch Hazel Village South Plan District (12.68)
- Cite: `or/washington/hillsboro/cdc.12.68.witch-hazel-village-south.txt#L71-L73` (Figure 12.68.020-A)
- Kind: plan district
- Zones covered: R-10, R-8.5, R-7, R-6, R-4.5, MR-1, MR-2 (Table 12.68.020-1, L77-L86). The pod is allowed.
- Reach (quadplex): reaches. "At least 50% of lots for single detached and middle housing dwellings with lot widths less than 50 feet shall be oriented…" (L423-L425). It applies 12.50.715 as written (L839-L840).
- Reach (townhouse unit lots): reaches. "all single detached, town-house, and duplex developments shall provide vehicle access to all lots and units from an alley" (L606-L608).
- Screenable:
  - townhouse alley access (L606-L608)
  - solar orientation ±20° for 50% of lots (L423-L425)
- Non-screenable: ~10 (12.68.810+ supersede 12.50.820–840)
- Boundary: missing. Likely source is Figure 12.68.020-A.
- FLATS today: NOT ENCODED, layer comment (`hillsboro.yaml#L459-L461`)
- Lots: unknown
- Note: largely greenfield (annexation agreements, L108).

---

## Beaverton

40.21 is the citywide RMA/RMB/RMC/CM-RM middle-housing design review. It is zone-wide, not area-bounded, so it is excluded (`or/washington/beaverton/bdc.40.21.middle-housing-design-review.txt#L22-L28`).

### Beaverton — Downtown Design District (Chapter 70)
- Cite: `or/washington/beaverton/bdc.70.downtown.txt#L108-L114`. The code applies to "development projects within the Downtown Design District boundary". Downtown is exempt from Chapter 20 (except 20.25) and from 60.05 (except lighting) (L129-L131).
- Kind: zone-chapter / design district (RC-BC, RC-OT, RC-MU, RC-DT)
- Zones covered: all four. "1.C Residential Dwellings - Triplex and Quadplex P P P P" and "Townhouse P P P P" (L539-L540).
- Reach (quadplex): reaches. "No construction … shall occur … that is not in conformity with the provisions of this Beaverton Downtown Development Code" (L108-L112).
- Reach (townhouse unit lots): reaches (same)
- Screenable:
  - front min/max with ground-floor residential: RC-BC 6/12, RC-OT 6/16, RC-MU 6/16, RC-DT 10/20 (Tables 70.15.10.x.B, L237-L433)
  - min density: 60 / 24 / 43 / 30 du/ac
  - surface parking not between facade and street on the primary frontage (70.20.05.7.A S5, L1431-L1444)
  - 48 sf open space per unit (L2841)
  - minimum building frontage: 50–90% by street type (Local 75%, Major 50%) (S1, L890-L911), not encoded
  - Active Ground-floor Use streets (Figure 70.15.25.1, L650-L677; 25 ft depth), not encoded
  - minimum FAR, not encoded
- Non-screenable: ~60 (Chapter 70 standards/guidelines)
- Boundary: zone = have (ZONE_NAME RC-*). Figure 70.15.25.1 (active frontages) and Figure 70.15.10.2.3 (RC-OT density) are missing.
- FLATS today: encoded (setbacks incl. max, density, parking_front_prohibited, open space; `flats/config/jurisdictions/or/washington/beaverton.yaml#L2486-L2865`). Building frontage % is not encoded; the layer-wide note covers the 60.05 version (`#L318-L323`).
- Lots: 460 (RC-OT 236 + RC-BC 158 + RC-MU 56 + RC-DT 10)
- Note: the frontage % (75% on local streets) is the one screenable rule that could flip a GREEN. A 56 ft pod on a lot over ~75 ft wide fails it.

### Beaverton — Multiple Use zones: Regional Center, Town Centers, Station Communities (20.20)
- Cite: `or/washington/beaverton/bdc.20.20.multiple-use.txt#L11-L12`
- Kind: zone-chapter (RC-E, TC-MU, TC-HDR, SC-MU, SC-HDR, SC-S, SC-E)
- Zones covered: as above. The pod is allowed in all except SC-E (refused).
- Reach (quadplex): reaches (base zones; 60.05 applies through 60.05.11.3)
- Reach (townhouse unit lots): reaches (parent-lot standards govern, `bdc.20.05.residential.txt#L382-L384`)
- Screenable:
  - max front setback, encoded
  - parking not between building and Primary Frontage, 20 ft off ROW (60.05.20.6.A)
  - min FAR = 0.30–0.60 (L106-L108), not encoded
  - 60% Primary Frontage occupied (60.05.15.6.A, `bdc.60.05.design-review-standards.txt#L272-L273`), not encoded
- Non-screenable: ~40 (60.05)
- Boundary: zone = have
- FLATS today: encoded (TC-MU `beaverton.yaml#L1917`, SC-HDR `#L2251`; refusals `#L312-L323`)
- Lots: 1,504 (SC-HDR 800 + TC-HDR 492 + RC-E 83 + SC-MU 65 + TC-MU 56 + SC-S 8). SC-E (40) is refused and not counted.
- Note: SC-E sub-areas (L76) are employment and irrelevant.

### Beaverton — Cooper Mountain Community Plan zones (20.22)
- Cite: `or/washington/beaverton/bdc.20.22.cooper-mountain.txt#L9`
- Kind: zone-chapter / master plan (CM-RM, CM-MR, CM-HDR, CM-CS)
- Zones covered: all four allow the quadplex
- Reach (quadplex): reaches
- Reach (townhouse unit lots): reaches (parent-lot rule, L245-L247)
- Screenable:
  - CM-HDR max front + parking_front_prohibited, encoded
  - min FAR = 0.4 for CM-CS/CM-HDR (L111), not encoded
  - Parks Overlay open-space placement (20.22.45, L816-L894)
- Non-screenable: ~20
- Boundary: zone = have. The Resource and Parks overlays are not held (`beaverton.yaml#L360-L361`).
- FLATS today: encoded (CM-RM `beaverton.yaml#L910`, CM-HDR `#L1106`)
- Lots: 0 (no CM-* rows in coverage.csv; land not yet zoned in the layer)
- Note: future impact only.

---

## Washington County (unincorporated)

Zoning is gispub `Open_Data_AGOL/MapServer/2` (field LUD). It carries the TO:, NB and NMU/CCMU codes, so those districts are zone-bounded.

### Washington County — Transit Oriented Districts (375)
- Cite: `or/washington/_unincorporated/cdc.375.transit-oriented.txt#L79-L115`
- Kind: zone-chapter (nine TO: districts)
- Zones covered:
  - Middle Housing is allowed only in TO:R9-12, TO:R12-18 and TO:R18-24.
  - TO:R24-40, TO:R40-80 and TO:BUS take the pod only as "Townhouses and Rowhouses that are not Middle Housing" (Type II).
  - TO:RC and TO:EMP are refused.
- Reach (quadplex): no for the Section 431 design standards: "Middle Housing is subject to design standards in Section 430-84, not Section 431" (L885-L887). The TO dimensional tables B(1)/C(1) do reach.
- Reach (townhouse unit lots): reaches in the denser districts. "If a use … does not follow the minimum design standards in Section 431, the use shall be reviewed as a Type III use" (L888-L890).
- Screenable:
  - frontage max setback, encoded (TO:R9-12, R24-40, R40-80, BUS)
  - TO:BUS min height, encoded
  - MH height 40/50, or 35 abutting R-5/R-6 (L941-L942; 35 held)
  - min FAR = 0.25–1.0 by station distance, not encoded
- Non-screenable: unknown, because Section 431 is not stored
- Boundary: zone = have
- FLATS today: encoded with notes (`flats/config/jurisdictions/or/washington/_unincorporated.yaml#L1718-L2150`). 431 is NOT ENCODED / not stored (`#L1752-L1757`).
- Lots: 2,412 (TO:R9-12 484 + R12-18 229 + R18-24 697 + R24-40 816 + R40-80 2 + BUS 62 + RC 91 + EMP 31)
- Note: 431 is the one unread design chapter that reaches the pod-as-townhouses (1,000+ lots in R24-40/R40-80/BUS).

### Washington County — North Bethany Subarea Overlay (390)
- Cite: `or/washington/_unincorporated/cdc.390.north-bethany.txt` 390-2.1 (~L24): "only applicable to the North Bethany Subarea of the Bethany Community Plan"
- Kind: overlay / plan district (NB zone suffix)
- Zones covered: R-6 NB, R-9 NB, R-15 NB, R-24 NB allow the pod. R-25+ NB, NCC NB, NCMU NB and INST NB are refused.
- Reach (quadplex): unclear. 390-20 applies to "development in all of the North Bethany Subarea land use districts" (L3059-L3061). However, its subsections cover only Single Detached (A), Townhouse (B) and Multi-dwelling (C, 5+ units). A quadplex fits none.
- Reach (townhouse unit lots): reaches. "B. Townhouse Dwelling Units shall comply with the following standards" (L3158). "Residential development in the R-6 North Bethany District (R-6 NB) is exempt" (L3062-L3063).
- Screenable:
  - garage ≥5/8 ft behind the front wall (L3193-L3203); the pod has no garage
  - blocks of at most ten townhouses
  - Special Frontages (Subarea Plan)
  - driveway/stub bans at Rural Reserve edges (L2673-L2677)
- Non-screenable: ~15 (10% windows, stoop/porch, siding, roofline)
- Boundary: zone = have (NB suffix in LUD). Special Frontages, ASC 2 and Density Restricted Lands are missing; they are on the North Bethany Subarea Plan maps.
- FLATS today: zones encoded. 390-20, 390-22.1 and 390-18.5/19.2 A are NOT ENCODED (`_unincorporated.yaml#L1350-L1376`).
- Lots: 1,419 reached as townhouse (R-9 NB 509 + R-15 NB 629 + R-24 NB 281); R-6 NB 1,572 exempt
- Note: essentially facade rules. Low screen value.

### Washington County — Bonny Slope West Subarea Overlay (391)
- Cite: `or/washington/_unincorporated/cdc.391.bonny-slope-west.txt#L11-L14`
- Kind: overlay / plan district
- Zones covered: base R- districts in the subarea
- Reach (quadplex): reaches. "the standards of this district shall control" (L33-L36), and the Community Plan controls over both (L18-L23).
- Reach (townhouse unit lots): reaches (same)
- Screenable:
  - no street stubs or driveways at the subarea edge beside rural land north of NW Laidlaw Road, ASC 18 (L43-L49)
- Non-screenable: ~3 (landslide provisions from plan maps)
- Boundary: missing. Likely source is the Cedar Hills–Cedar Mill Community Plan map (county gispub host).
- FLATS today: NOT ENCODED (`_unincorporated.yaml#L539-L548`)
- Lots: unknown (small)
- Note: none.

### Washington County — Pedestrian-Oriented Mixed-Use Districts (392)
- Cite: `or/washington/_unincorporated/cdc.392.mixed-use.txt#L42-L54`
- Kind: zone-chapter (NMU, CCMU)
- Zones covered: both allow an "Attached Dwelling Unit" (Type II)
- Reach (quadplex): reaches
- Reach (townhouse unit lots): reaches
- Screenable:
  - max front = 20 ft, encoded
  - parking_front_prohibited, encoded
  - "At least 50% of a site's street frontage(s) must be occupied by a building located no further than the maximum 20-foot setback" (L309-L313), not encoded
  - Required Outdoor Area = 250 sf/du (L241-L242), not encoded
- Non-screenable: ~12 (392-9, L337-L581)
- Boundary: zone = have
- FLATS today: encoded in part (`_unincorporated.yaml#L2150-L2354`; NMU `#L2191`, CCMU `#L2274`)
- Lots: 180 (NMU 82 + CCMU 98)
- Note: none.

### Washington County — Community Plans (300-1.1)
- Cite: `or/washington/_unincorporated/cdc.300.introduction.txt#L7-L14`. "all development, including Land Divisions, shall comply with … Subarea Provisions, including the Design Elements and Area of Special Concern".
- Kind: master plan (eleven community plans)
- Zones covered: all urban unincorporated zones
- Reach (quadplex): reaches ("all development")
- Reach (townhouse unit lots): reaches
- Screenable: unknown. No plan is stored.
- Non-screenable: unknown
- Boundary: missing. Likely source is the county's community-plan / ASC layers on gispub.co.washington.or.us.
- FLATS today: NOT ENCODED, "a question for Steph" (`_unincorporated.yaml#L530-L537`)
- Lots: up to 68,777 (all unincorporated rows in coverage.csv)
- Note: the largest unknown in the county. ASC rules are per-site and could hold the screen's biggest hidden district standards.

---

## Jurisdictions / chapters with no district found (or excluded)

- **Durham:** only MDDO. I grepped "overlay", "district", "design" and "plan area" in ddc.2/3.
- **Sherwood:** I grepped "Brookman" (no hit in stored text) and "town center" (one parking-table hit, `sdc.16.94.parking.txt#L365`). Tonquin Employment Area (16.31.060) is industrial and excluded. The Adams Avenue Concept Plan is a commercial footnote only (`sdc.16.22`, ~L463). 16.68 Infill is an elective relief, not a district. 16.40 PUD is elective.
- **Cornelius:** MSC (18.80) and MSDO (18.85) are repealed. CR (18.70) is a plain zone "in close proximity to the city's town center".
- **Hillsboro:** Hawthorn Farm/Fair Complex (12.63; 2 non-residential zones, sidewalks only), Witch Hazel Village (12.67; street cross-sections only) and North Hillsboro Industrial (12.66) are excluded. None has a "quadplex"/"plex"/"middle housing" hit (`hillsboro.yaml#L462-L464`). 12.27 overlays (RFO, SNRO, CRO landmark sites, PUD, SID) are not design districts.
- **Washington County:** SID (377) is a special industrial overlay and excluded.
- **Beaverton:** 10.32 overlays (Historic HO, Resource RO, CMPO) are not stored or encoded (`beaverton.yaml#L360-L361`). HO was not read (landmark list).
- **Grep terms used:** design district, design overlay, overlay, plan district, plan area, community plan, town center, main street, downtown, village, subarea/sub-area, subdistrict, applicability, exempt, do not apply, Figure, Map, quadplex, townhouse, middle housing.
