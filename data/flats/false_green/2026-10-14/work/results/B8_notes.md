# B8 notes (false-GREEN sample round 2, run 74)

## 1. 12E30DB06500 - Milwaukie R-MD - 5301 SE Logus Rd - RIGHT
- Lot 27,479 sf, 138 x 199 ft rectangle. South = SE Logus Rd (centreline ~12 ft off the line per quadfit s1 streets; lots across 38 ft away). West = 200 ft shared with 12E30DB06600, a 1,993 sf NO SITUS strip carrying the SE 53rd Pl centreline (4 ft off our line) -> a private/narrow lane, a way in by ruling; corner_lot true is right. North + east = 50-acre parcel 5325 SE Logus (R-MD).
- USE: Table 19.301.2 Quadplex P, Townhouse P (19.300.base-zones.txt:31-33). P = by right (L48). No overlay (WG false, has_z_overlay false).
- LOT (Table 19.301.4 7,000+ column, L100-310): width 60 (138), depth 80 (194), frontage 35 (337). Min density 5.0 du/ac applies to land divisions only (19.301.5.D, L330-336); max density: quadplex exempt (note 4, L314).
- BUILDING: front 20, side 5/10, street side 20 on corner (19.301.5.A L322), rear 20; height 35 vs 26; coverage 30% (7.3%); vegetation 30% = 8,244 sf (lot is mostly open); side yard height plane 20 ft + 45 deg -- building ~35 ft from east line, clear.
- NOT ENCODED, checked by hand: Table 19.501.2.A (19.500.supplementary.txt:33-66) "Logus Road 25'" from centreline PLUS the zone yard -> building >= 45 ft from Logus centreline; centreline 12-19 ft from the line -> building 26-33 ft back vs the 20 ft the envelope uses. Fit slack 95.5 ft (depth room 40) absorbs it; hose route 87 -> ~100 ft. No grep hit for 19.501.2.A in milwaukie.yaml (only the porch note). Pattern to watch on other Milwaukie lots on listed streets.
- PARKING/ACCESS: max 1/unit quadplex (19.600.parking.txt:253) = 4; 9x18 stalls (L923); access from lowest class street first (12.16.access-management.txt:12.16.040.B.2) = 53rd Pl; 45 ft from intersection for plex on local streets (B.5.a), lane sits north of the building, >60 ft from Logus. Apron 12-20 ft.
- LAND: slope p85 6.5%, max 22.6% on a small spot, steep_sqft 0; no flood.
- WHO: SFR 1932, 2,624 sf house, land $324k -- ordinary house, no policy note.
- UNCHECKED: FAR/stories/max units/min height: none in R-MD table; density handled above.
- FLAGS: FACT-LOCAL-STREET, FACT-FLAG-LOT sev 0 -- not colour-changing.

## 2. 12E31BD08100 - Milwaukie R-MD - 11314 SE Home Ave - RIGHT
- Lot 20,012 sf, 100 ft frontage on SE Home Ave (west; centreline 24 ft off the line, lots across 51 ft) x 200 ft deep; interior, backs onto Park St / Hunter Ct lots (all R-MD). Not corner, not flag.
- USE: Quadplex P (19.300.base-zones.txt:31). No overlay.
- LOT: 7,000+ column: width 60 (100), depth 80 (200), frontage 35 (100). Density: quadplex exempt from max; min applies to divisions only.
- BUILDING: front 20 (envelope starts 20 ft in), side 5/10, rear 20; height 35 (26); coverage 30% (10.1%). Side yard plane (Table 19.301.4 C.3, 20 ft at the min side yard + 45 deg): south wall ~15 ft from the line; taking south as the 5 ft side, plane height there = 20+10 = 30 ft > 26. North side ~30 ft (lane). Clear.
- Table 19.501.2.A centreline yards: Home Ave not listed (19.500.supplementary.txt:33-66).
- PARKING/ACCESS: max 1/unit = 4 (19.600.parking.txt:253); lane in north side yard; front yard vehicle share 12% vs 50% cap (19.607.1.D.1, 19.600.parking.txt:973-985); one accessway per property (12.16.040.C.3); apron 12-20 ft. Fire 109 ft.
- LAND: slope p85 6.4%, max 19% small, steep 0; no flood.
- WHO: SFR 1943, 1,664 sf -- ordinary house.
- UNCHECKED: FAR/stories/units: none in R-MD. pod80x25 is yellow (outdoor shape unmeasured); pod56x36 green stands.

## 3. 1S3E15AA  -04600 - Gresham LDR-5 - 1395 SE 12th St - RIGHT
- Lot 11,903 sf wedge: west line 168 ft (N-S) on Liberty Ave lots, NE line 147 ft on 1255 SE Maple Pl (perpendicular to 12th), 15 ft north stub, SE side = SE 12th St straight 101.7 ft, south tip = rounded corner onto SE Liberty Ave (~17 ft of curve + ~25 ft of gentle arc). Real corner (two streets, s1 centrelines 18-19 ft off).
- USE: Table 4.0120 Quadplex P, Townhouse P (4.0100.residential.txt:134-135).
- LOT (Table 4.0130, L234-330): min lot 5,000 (11,903); min net density 6.22/ac -> 4/0.273 ac = 14.6; max density none for quadplex; corner width at building line 40 (lot width 43.2; at the building line ~70); corner depth 70 (131.7); corner frontage 40 "measured from the corner radius end point to the property corner" -- 12th St straight run 101.7 ft. (If one insisted the FRONT line = Liberty must have 40 ft past the curve, Liberty has ~25 ft; I read the table as a lot frontage standard met on 12th, and the applicant may pick the front where depth is met both ways, 3.0100.definitions.txt:1332-1341.)
- BUILDING: Table 4.0131 quadplex LDR-5: front 10 (sidewalk easement -> measured from easement line, note 1), interior side 5, street side 10, rear 15. Height 35 vs 26; FAR 1.0 vs 4,032/11,903 = 0.34 (unchecked but passes). 7.0420.G rear roof height 21 ft at rear setback line +1:1 (7.0400.middle-housing-design.txt:358-362): building ~90 ft from the north stub. Private open space 15% (68%).
- PARKING/ACCESS: none required (parking min 0). 7.0420.B.2.b approach max 10 ft per building with no garage (one approach). PWS Table 6.03: residential driveway centreline >= 45 ft from curb return; 12th frontage 101.7 > 75 so note 2 does not bind; drive near the NE end of 12th. Clear vision Table 6.04 street intersection 40 ft legs: hypotenuse runs ~y 714-726, building front at y 742 -- clear. Fire 104 ft.
- GEOMETRY: picture: building at the south facing Liberty, court at the north; no lane drawn but a 12 ft lane from 12th St along the NE line reaches the court's east side (14-35 ft gap). Fit slack 7.5 ft.
- LAND: slope dem_10m max 9%; no flood, no overlay.
- WHO: SFR 1974, 1,920 sf -- ordinary house.
- UNCHECKED: coverage (none in LDR-5 table), FAR (passes), max units (townhouse only). FLAGS: none.

## 4. 1S3E03CB  -00702 - Gresham LDR-5 - 2000-2020 N Main Ave - RIGHT (tight)
- Lot 9,406 sf. West line 100 ft on N Main Ave (centreline 27 ft off; NW 20th St tees into Main from the west opposite y~678330), south = NE 19th St curved ~68 ft (centreline ~25 ft), SE line 100 ft on 65 NE 19th St (LDR-5), north 82 ft + 36 ft on 2030-2050 N Main (LDR-5). Across: DCL (Main, west), MDR-24 (19th, south).
- USE: Quadplex P (4.0100.residential.txt:134).
- LOT: Table 4.0130: 5,000 sf (9,406); min net density 6.22 -> 18.5; corner width 40 (73.4); corner depth 70 (102.8); corner frontage 40 (168 total; Main 100 straight).
- FRONT: 3.0100.definitions.txt:1332-1336: existing building -> front door; no building -> line giving min depth, applicant chooses when both work. Only front = 19th fits (E-W depth ~82 ft cannot hold pod+court+setbacks), so drive must use Main = the side street, matching the corner ruling. PWS 6.03 "may be limited to ... usually the lower classification street" (pws.6.03-6.04.txt:13-14) is engineer discretion; corner_access_street = any. Main Ave's class is not held for Gresham; if it is a collector and the engineer forced access to 19th, no fit -- not a stated rule, so not a WRONG.
- BUILDING: Table 4.0131 quadplex LDR-5 front 10, interior side 5, street side 10, rear 15, measured from the sidewalk easement (note 1): FLATS takes 7 ft worst case on local lines (geom/sidewalk.py; 7 ft also covers a collector's 6 ft walk). Height 35 (26); rear roof limit 21 ft +1:1 (7.0400.middle-housing-design.txt:358-362) -- building ~45 ft from the north line, clear. FAR 1.0: 4,032/9,406 = 0.43. Open space 15% (60%).
- PARKING: none required (9.0800.parking.txt:53); 9.0822(A)(6) "shall not occupy the required setbacks for multi-dwelling structures containing three or more units" (9.0800.parking.txt:168-172) does not reach a quadplex: 9.0802(F) (L66-69) and the Parking Lot definition "Parking areas for single detached dwellings and middle housing are not parking lots except ... 7.0431 and 7.0440" (3.0100.definitions.txt:1500-1502). FLATS still keeps the court out of the rear setback (conservative). 7.0420(B)(5)(c) allows parking in front/street-side setbacks.
- GEOMETRY: picture: building faces 19th, court north of it, reached from Main through the street side yard. Slack 0.0, FIT-TIGHT [-0.5,0.5]: I cannot re-derive the placement to the half foot from the picture (my reading: front curve high point y~678262, +17 = 678279, +63.5 = 678342.5 vs rear setback line ~678346, so 0-3 ft room) -- consistent with green.
- LAND: flat (3.5% max). No flood/overlay.
- WHO: 1967, 2,400 sf, assessor SFR 101, but a 2000-2020 address range -> likely a small plex in use (policy note).
- UNCHECKED: coverage none in LDR-5; FAR passes. FLAGS: FIT-TIGHT only.

## 5. 1N3E31DB  -06200 - Gresham TLDR - 17243 NE Couch St - RIGHT
- Lot 13,575 sf, 75 ft on NE Couch St (south; centreline 14 ft off) x 181 ft. Interior; neighbours all TLDR; SC across Couch; E 172nd MAX 339 ft.
- USE: Table 4.0120 TLDR Quadplex P (4.0100.residential.txt:134); 4.0112 purpose (L69-77) lists quadplexes.
- LOT: Table 4.0130 TLDR: min lot none; width 16 (75); depth none; frontage 35 (75); min net density 10/ac (4/0.312 = 12.8); max density: quadplex none (townhouse 25).
- BUILDING: Table 4.0131 TLDR quadplex front 10, side 5, street side 10, rear 15 (L400), sidewalk easement worst case 7 ft added; height 35 (26); FAR NA for TLDR; 7.0420.G rear roof limit names LDR-7/LDR-5/TR etc., not TLDR (7.0400.middle-housing-design.txt:358-360). Open space 15% (66%). 9.0600 height transition NA for TLDR.
- PARKING: none required; quadplex court not a parking lot (3.0100.definitions.txt:1500-1502). Interior lot, one street. Fire 105 ft.
- GEOMETRY: picture: building near Couch, lane on the west side, court behind; slack 57 ft.
- LAND: flat 2%; no flood/overlay.
- WHO: SFR 1948, 1,590 sf -- ordinary house (prop 121).
- UNCHECKED: min_lot_area/depth: none in TLDR; coverage none; FAR NA. FLAGS: none.

## 6. 1N3E35CA  -04100 - Troutdale LDR-1 - 2211 SW Sundial Ave - RIGHT
- Lot 11,091 sf, 92.6 x 121 ft, rounded NE corner: north = SW 22nd St (lots across 50 ft), east = SW Sundial Ave (50 ft). Real corner, both look like 50 ft-ROW subdivision locals. Neighbours LDR-1 (west 1902 SW 22nd, south 2233 SW Sundial).
- USE: 3.120 table Quadplex P in LDR-1 (3.zoning-districts.txt:232), standards 8.120; 8.120.A.1 same process as a detached house, clear and objective only (8.development-standards.txt:505-508); C.5.c.i at L616.
- LOT: 3.130.B (3.zoning-districts.txt:319-340): 10,000 sf (11,091), width 70 (92.4), depth 100 (121), frontage 20 (204). Density: 3.140.B.4 max not applied to quadplex; 8.120.B.2 max 4 units on a lot.
- BUILDING: 3.130.B LDR-1 front 10, side 10, street side 10, rear 10; height 35 (26). Notes 1/2 (20 ft when driveway access is from the front / street side yard) are referenced only under the MDR(TC)/HDR(TC) columns (L328-333) -- not LDR-1. 8.120.B.1.b: no coverage/landscape/open space for quadplexes.
- PARKING/ACCESS: 8.120.B.3.a.iii(b) min 4 for a quadplex in a 7,000+ zone = 4 seated (target band 7). 8.120.C.4.b parking not between building and street -- court is behind the building. 8.120.C.5.c.i lowest classification street first: both appear local (50 ft ROWs); C.5.c.iii one 16 ft approach per frontage. 9.095.A parking abutting a residential district meets that district's building setback (9.parking.txt:526-527): court ~20 ft from the west line, ~35 ft from the south line. 9.095.B/D street setback: lane only passes through.
- GEOMETRY: picture: building faces 22nd (north), court south of it, lane in from Sundial. Slack 26.5 ft.
- LAND: flat 4%; no flood.
- WHO: SFR 1981, 1,349 sf -- ordinary house. FLAGS: none.

## 7. 1N3E35CA  -10200 - Troutdale LDR-1 - 1728 SW 26th St - RIGHT
- Lot 10,678 sf, ~91 x 118 ft, rounded NW corner: north = SW 26th St, west = SW Latourell Pl (lots across 50 ft both). South line on MDR lots (1793/1777 SW 27th St), east on LDR-1 (1714 SW 26th).
- USE/LOT: as lot 6: Quadplex P; 10,000 sf (10,678, +678), width 70 (91.7), depth 100 (117.9), frontage 20.
- BUILDING: 10/10/10/10, height 35 (26). Troutdale's neighbour-zone side/rear escalators (3.130.E.7) are for multi-family only.
- PARKING: 4 required = 4. 9.095.A: court ~20-22 ft from the MDR rear line, ~15 ft from the LDR-1 side line -- meets any reading of "building setback of the most restrictive adjoining residential zoning district" (LDR-1 SFD rear 15/20, side 10). Drive from Latourell (side street, local); 26th faced by the building.
- GEOMETRY: picture clean; slack 23 ft (pod80 7 ft). Fire 84 ft.
- LAND: flat 4.6%; no flood.
- WHO: SFR 1990, 1,880 sf -- ordinary house. FLAGS: none.

## 8. 1S2E20DC  -13100 - Multnomah uninc (Portland-administered) R7 - 8542 SE 75th Ave - RIGHT
1. USE: Table 110-2 Fourplex Yes in R7 (33.110.txt:313); 33.110.265.E: fourplexes "allowed in the R20 through R2.5 zones", must front a maintained street (33.110.txt:1534-1540) -- fronts SE 75th Ave and SE 75th Pl. Max four units (L1541). Zone R7 is the Portland zone name, so PCC 33 is the right code (County LR-7 files not relevant). No overlay (has_z_overlay false, constrained_sites false).
2. LOT: 14,696 sf, about 145.5 x 101 ft, a THROUGH lot (75th Ave west, 75th Pl east). Table 110-3: 36 ft wide (101). Table 110-7 R7 fourplex 4,200 sf (L1552). 33.110.205.C.1 (L421): R7 min 2 units on sites >= 14,000 sf -> 4 meets it. South line faces a 30 ft gap to the Clackamas (12E29AB) Luther Rd lots -- likely an unbuilt Clatsop St right-of-way or the county line; s1 shows Clatsop St ending at 75th Ave. Even if it is a street, a 15 ft setback leaves 81 ft N-S vs the 56 ft building.
3. BUILDING: Table 110-4 R7 (L454-464): max height 30 ft (pod 26), front 15, side 5, rear 5. Envelope 10,510 sf = (145.5-30) x (101-10), so both street lines are treated as front, which is the conservative reading. Coverage Table 110-5 (L780-786): 2,250 + 15% x 9,696 = 3,704 sf (25.2%) vs pod 2,016. FAR (unchecked) R7 4+ units 0.7 (L441) -> 10,287 sf vs about 4,032 sf for two storeys; still fits with the existing 1,328 sf house kept. Outdoor area 250 sf / 12x12 (easy).
4. PARKING: 33.266 states only MAXIMUMS (33.266.100.B; no minimum table); parking_reform true. Read sceptically: the drawn court lies east of the building, i.e. between the pod and SE 75th Pl. 33.266.120.C.1.a says "Vehicle area is prohibited between the primary structure and the street" except behind the front and side street building lines (33.266.txt:282-290). On a through lot that would catch this drawing. But no parking is required, so the pod stands without the court. A compliant court also fits: 4 stalls 9x18 beside the building within its E-W extent, about 83 of 101 ft N-S. The colour stands. Pattern: through-lot rear courts are not tested against 33.266.120.C.1.a. Spaces 9x18 (L318).
5. GEOMETRY: picture -- pod at the west, lane along its north side out to 75th Ave, court behind; all inside the lot. Slack 31 ft (pod56), 17.5 ft (pod80). Fire 122 ft.
6. LAND: slope p85 8.3%, steep 0, no flood, no overlay.
7. WHO: SFR 1921, 1,328 sf, $441k total -- ordinary house.
8. UNCHECKED: frontage/width/depth (Table 110-3 width 36 only, met); FAR met; density max 4 (met); stories none stated.
9. FLAGS: none.

## 9. 1S3E18B   -00200 - Multnomah uninc (Portland-administered) R5 - 4619 SE 174th Ave - RIGHT
1. USE: Table 110-2 Fourplex Yes in R5 (33.110.txt:313). 33.110.265.E: allowed R20-R2.5, needs frontage on a maintained street (L1534-1540) -- SE 174th Ave. No overlay flagged (has_z_overlay false). Plan districts (e.g. Johnson Creek Basin 33.537) are not stored, so I cannot check them. The dossier shows no gate.
2. LOT: 23,099 sf, 75.7 ft wide x 304 ft deep, east end on 174th. Table 110-3: 36 ft wide (75.7). Table 110-7 R5 3,000 sf (L1553). 33.110.205.C.2 (L423): R5 min 2 units on >= 10,000 sf -> 4 meets it; max four units (L1541).
3. BUILDING: Table 110-4 R5: height 30 (L454), front 10, side 5, rear 5 (L458-464). Envelope 19,030 sf = (304-15) x 65.7, i.e. front 10 / rear 5 / sides 5. Coverage Table 110-5 >= 20,000 sf: 4,500 + 7.5% x 3,099 = 4,732 sf (20.5%, L786) vs 2,016. FAR R5 4+ units 0.8 (L441) -> 18,479 sf vs about 4,032.
4. PARKING: no minimums in 33.266 (maximums only); 4 stalls 9x18 drawn. Pod at the east end, lane along the south, court west of the building.
5. GEOMETRY: the picture shows a 40.6 ft strip along the whole north line, with no parcel in it (DB: nothing within 40 ft). North of it lies a fresh row of 2,560 sf RM1 vacant lots, each addressed "SE LONG ST" ($56k each), plus 4545 SE 174th. That strip is almost certainly the newly dedicated SE Long St, not yet in the street centrelines (s1 finds only 174th). So the lot is very probably a CORNER: front 174th (75.7, shorter), side street Long St (304). Under the corner ruling the drive should come off Long St, not 174th as drawn. That does not change the colour, for three reasons:
   - 304 ft of Long St frontage takes a driveway to a court behind the building (33.266.120.C.1.a(2) allows driveways to spaces behind the building lines, 33.266.txt:282-290).
   - Even a 10 ft setback on the Long St line leaves 75.7-10-5 = 60.7 ft vs 56 ft (pod56) / 45 ft (pod80).
   - Portland requires no parking at all.
   The side-street 20% paving cap (33.266.txt:294-296) is met: 20 ft x 10 ft drive vs 20% of about 3,000 sf. Pattern: new streets missing from the centrelines make corners read as interior; harmless here.
6. LAND: flat (10 m DEM, max 3.1%), no flood, no constrained sites.
7. WHO: SFR 1946, 1,050 sf, ordinary house. Sewer main 474 ft away in the data (public_sewer not set). The new subdivision next door will very likely carry sewer in Long St. No zoning standard turns on it.
8. UNCHECKED: width (met), FAR (met), density (met), stories (none stated).
9. FLAGS: none.

## 10. 1N3E34B   -00807 - Wood Village TC - 22401 NE Glisan St - CANT_TELL (likely RED, by-right)
1. USE: Table 235-1: Household Living Y (235.200.txt:60,66-68). 710.100 defines Household Living with no housing type named, so a 4-unit pod is inside it. BUT the Town Center zone is not lot-by-lot:
   - 720.030.definitions.txt:512: "TOWN CENTER DEVELOPMENT PLAN ... information submitted by an applicant seeking approval for development within the Town Center Zone area ... as required by Section 235.400."
   - L514: "The Town Center Development Plan replaces the term Master Plan."
   - 235.340.txt:62-64: the Development Plan "must demonstrate that the transportation system is adequate or can be made adequate".
   - 235.465.txt:60: a Development Plan "shall contain a minimum of twenty (20) percent open space"; dedication must be "acceptable to the Planning Commission" (L62).
   - 235.390.txt:60: parking "except as modified in an approved Development Plan".
   - 235.410/235.420: conformity with the Concept Plan Regulating Diagram (street types, required intersections).
   The procedure (Type I/II/III, who decides, which criteria) is in 235.400 / 235.490. Neither is stored, and both return 403 from here. Our own layer admits it (wood-village.yaml TC notes: "nothing about whether a Development Plan would be approved"). Under the by-right ruling (master plans = RED) this is decisive if the plan is discretionary. Adequacy-of-services and diagram-conformity criteria read discretionary. Oregon's clear-and-objective housing rule (ORS 197.307) may force a ministerial track. CANT_TELL; likely RED; affects all ~167 TC lots, so it needs a new FOLLOWUPS item: fetch 235.400/235.490.
2. LOT: 52,786 sf, width 279, depth 203, frontage 445. TC residential defers lot size to MR2 (235.300.txt:70): 7,500 / 60 / 80 met. No density row (L68-77). MR2's 220.330 townhouse standards are not stored (round 1 note). They do not decide this lot because the pod sits on one lot as one structure.
3. BUILDING: height 35 (L72) vs 26. Front 10, side 5, rear 15 (L73-76). Note (3) 15 ft from a residential zone and note (2) 25 ft step plane (L81-83): the VSF lots are 104 ft away (not abutting); the unobserved abuts_* facts are moot with 204 ft slack. Coverage 45% (MR2) vs 3.8%. Open space 20% (a plan-level standard) met on the lot anyway (92%).
4. PARKING: 4 stalls charged; 350.065 governs; plenty of room. The drawn lane is short and sits in the open lot interior. There is a private drive/street 0.8 ft off the north line (an unnamed s1 street), plus Glisan to the south (through lot), so a way in exists.
5. GEOMETRY: an irregular pentagon at NE Glisan near 223rd. Pod mid-lot, rotated; fits easily (slack 204 / 187 ft). Fire 132 / 144 ft.
6. LAND: flat, no flood.
7. WHO: COM prop 201, 2006 building of 11,302 sf, $3.39M total, $7.7M sale 2019. This is an existing commercial building (policy note). quadfit: policy_exclusion existing_commercial. The neighbours are TC parcels of the Town Center (129k and 41k sf). This could be a pad in a shopping centre (RED by ruling), but there is no OSM mall to confirm (Overpass unreachable).
8. UNCHECKED: FAR (235.340 0.4 is a MINIMUM for nonresidential areas only); density (none in TC); frontage (Table 235-5 frontage by street type, keyed to Figure 235-1, which is not readable).
9. FLAGS: FACT-ABUTS-RESIDENTIAL-ZONE / LOWER-DENSITY, sev 0, unobserved; immaterial at this slack.

## 11. 1N3E34AD  -02500 - Wood Village LR 12 - 745 NE 239th Pl - RIGHT
1. USE: Table 210-2 "Attached or Detached Tri- or Quadplex" Y in LR12 (210.310.txt). Townhouse Y as well. Design review: 210.375.A "reviewed as a Type I procedure" (210.375.txt:60). 720.030 defines non-discretionary reviews as ministerial (720.030.definitions.txt:314), so by-right. Required elements:
   - entry facing the street;
   - 20% windows;
   - 4 of 6 facade items;
   - roof pitch at least 5:12, no flat roofs (L64-86).
   None moves the rectangle. A 5:12 gable on a 36 ft deep pod rises about 7.5 ft, which stays under 35 ft (KNOWN-62 roof shape, harmless at a 35 cap).
2. LOT: 14,098 sf, 100 x 141 ft interior lot on 239th Pl (east). Table 210-3 LR12 (210.320.txt:63-68): 12,000 sf / width 80 / depth 120 / min 0.9 du per net acre. Lot is 14,098 / 100 / 141 / 12.4 du/ac. Note (2) townhouse lot rules (L84) apply only if the units are divided onto unit lots. Not needed.
3. BUILDING: height 35 (L69). Front 10, side 10, rear 15 (L71-74). Envelope 9,278 sf = (141-25) x (100-20). Coverage 45% (L80) vs 14.3%. 220.330 is not stored (round 1), but this is LR12, so it is not in play.
4. PARKING: Table 350-1A Household Living 1-4 units, 1 per unit = 4 (350.045.required-spaces.txt:96-97). A quadplex is not a house, attached house or duplex, so 350.065 governs (not 350.055). Table 350-2: 5 ft setback from an LR lot line (350.065.all-other-uses.txt:77). The court sits 12 ft (north), 24 ft (south) and 48 ft (rear) from the lot lines. Court 47 x 68 ft holds 4 stalls 9x19 plus a 24 ft aisle. Forward exit: there is room in the court.
5. GEOMETRY: picture -- building at the front setback, facing 239th Pl. Lane runs along its south side to the street; court behind. All inside the lot. pod56 slack 43, pod80 slack 3.5. Fire 103 ft.
6. LAND: flat (max 3.3%), no flood, sewer 15 ft.
7. WHO: SFR 1965, 2,800 sf, $608k -- ordinary house.
8. UNCHECKED: frontage (no number stated in Table 210-3); FAR (none in 210); max units (quadplex = 4); stories (none).
9. FLAGS: none. abuts_residential/lower_density observed true; LR12 has no neighbour-zone variant in Table 210-3.
