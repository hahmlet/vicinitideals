# B2 notes (Portland, 15 GREEN lots, run 74)

Method: dossier + picture + the stored Portland text in flats/provenance/docs/or/multnomah/portland/
(33.110, 33.120, 33.130, 33.266, 33.910, 33.930). Line numbers are those stored files.
Extra facts gathered (read-only): each lot ring was intersected with the City's own zoning layer
(portlandmaps.com ArcGIS Public/Zoning/MapServer/3, "Zoning Designations (Detailed)") to see
overlays, plan districts and historic/conservation districts, which FLATS does not hold. Where a
plan district or overlay applied, its chapter was fetched from portland.gov/code/33 (PDF, current
edition) because it is NOT in the stored corpus; those cites are marked "PCC <chapter> (fetched)".
DB: SELECT only (lot ring + checks.drawing).

Cross-lot evidence
- Fourplex Yes in R20-R2.5 (Table 110-2, 33.110.txt:313); by right (33.110.265.B, 33.110.txt:1486-1487);
  min lot area Table 110-7 (33.110.txt:1547-1554): R10 6,000, R7 4,200, R5 3,000, R2.5 1,500.
- Maintained-street gate (33.110.txt:1535-1540) unmeasured (known pattern, not a per-lot finding).
- Table 110-4 (33.110.txt:432-474): front R10 20 / R7 15 / R5 10 / R2.5 10; side+rear R10 10, R7-R2.5 5;
  height 30 (R2.5 35); FAR 4+ units R7 0.7, R5 0.8, R2.5 1.0; R10/R20 FAR only on lots < 10,000 sf
  (33.110.txt:499-500). Coverage Table 110-5 (33.110.txt:780-786). Height to the average of a gable
  (33.930.050, 33.930.txt:237); 26 ft vs 30 ft cap either way.
- Parking for fourplexes 33.266.120 (33.266.txt:268-349): 9 x 18 stall, 9 ft driveway, vehicle area
  not between building and street except driveways to spaces behind the building line; 40% front-yard
  paving cap; alley access mandatory where the lot abuts an alley.

## 1. 1S1E33BD  -03600 (R10, 1811 SW Stephenson St) RIGHT
1 USE: fourplex Yes R10; City layer: R10, no overlay, no plan district. 2 LOT: 21,871 sf, 125 x 175;
  min 6,000; Table 110-3 36 ft width met; no R10 min density. 3 BUILDING: front 20 / side 10 / rear 10
  in envelope; height 26 vs 30; FAR n/a (lot >= 10,000 sf, 33.110.txt:499-500); coverage 2,016 sf = 9.2%
  vs 4,500 + 7.5% x 1,871 = 4,640 sf (21.2%) - matches the margin. Outdoor area 250 / 12x12 easily.
4 PARKING: 4 stalls in rear court; drive along one side; front-yard share 12 vs 50 ft cap.
5 GEOMETRY: picture: street (SW Stephenson) on the south, pod at the front, court behind; slack 67.5.
6 LAND: slope mean 6.6%, p85 9.4%, max 21% (local); grade at pod 4%; no flood.
7 WHO: SFR 1937, 2,206 sf (ordinary house). 8 UNCHECKED: frontage/width/depth: none stated for R10
  fourplex beyond Table 110-3 (36 ft) - passes; FAR n/a; stories none; density max 4 (pod is 4).
9 FLAGS: none.

## 2. 1N2E26DD  -09700 (R7, 1529 NE 138th Pl) RIGHT (plan district not held, survives)
1 USE: fourplex Yes R7. City zoning layer: R7 + "h" Aircraft Landing overlay + PLDIST GL (Glendoveer
  Plan District). "h": in R zones "structures are regulated by the base zone height limits"
  (PCC 33.400.030.B, fetched) - no effect. Glendoveer (PCC 33.530, fetched): applies to R7 land formerly
  LR7.5 (33.530.020); Map 530-1 draws only the district boundary; lot is inside it (north of Halsey,
  east of 132nd). 33.530.040.A: "Front setback 30 feet / Side setback 10 feet / Rear setback 15 feet".
  33.530.030 is for land divisions only. FLATS holds neither chapter (no "Glendoveer"/"33.530" anywhere
  in flats/config); encoding uses R7 15/5/5.
2 LOT: 14,456 sf, 89.5 x 161.7 ft; min 4,200; R7 min density 2 on >= 14,000 sf (33.110.txt:421-422) -> 4 ok.
3 BUILDING: FAR 4,032/14,456 = 0.28 vs 0.7; coverage 13.9% vs 2,250 + 15% x 9,456 = 25.4%; height 26 vs 30.
  Glendoveer test on the drawn plan (checks.drawing, EPSG:2913): street (NE 138th Pl) on the EAST line;
  building east face 15.2 ft from it, north face 8.8 ft from the north line. Needs 30 / 10: slide west
  14.8 ft and south 1.2 ft. Court (51 ft deep) then ends ~44 ft from the west (rear) line; lane (12 ft)
  moves to 9.8 ft from the south line; building 95 ft from rear (>= 15). Fits. room = width 11 / depth 40.
4 PARKING: 4 stalls rear court; driveway beside building to spaces behind the building line (33.266.txt C.1.a(2)).
5 GEOMETRY: rectangular interior lot, one street. 6 LAND: slope max 4%; no flood.
7 WHO: SFR 1953, 936 sf (ordinary). 8 UNCHECKED: none binds. 9 FLAGS: none.
Pattern: Portland plan-district chapters are not held at all (only 33.110/120/130/266/... are stored);
here the stricter Glendoveer setbacks do not change the colour.

## 3. 1S1E26AB  -02800 (CM2, 8816 SE 17th Ave) RIGHT
1 USE: Household Living Y in CM2 (33.130.txt:341-343); fourplex named in 33.130.250.B.2.a. City layer:
  CM2 + "d" Design overlay, no plan district. PCC 33.420.045.A.2 (fetched): exempt when "the only use on
  the site will be Household Living; ... no more than four dwelling units total ...; ... no more than
  35 feet in height; and ... not zoned RX, EX, or CX". With the existing building ignored by policy the pod
  is exempt; even if not, 33.420.050 design standards are an objective alternative (Table 420-1 note [1]:
  no size limit where any floor area is residential) -> by-right path either way.
2 LOT: 43,121 sf, corner (SE 17th Ave on the west, 150 ft; SE Linn St on the north, 350 ft); no min
  lot size (33.130.txt:397-399). Min density 1/1,450 (33.130.txt:624) = 29.7 units vs 4: DENSITY-MIN
  flag (standing sev-2 ruling), carried in checks (if_signed yellow on that flag only).
3 BUILDING: FAR 0.09/2.5; height 26/45 (33.130.txt:627); coverage 4.7%/85%; landscaped 92%/15%.
  Max setback 10 ft for >= 50% of each street-facing facade (33.130.215.C.1; two streets so both count,
  C.2.c). Drawn pod80x25 (checks.drawing): west face 5.0 ft from 17th, north face 5.5 ft from Linn ->
  both facades within 10. (Drawn pod56 has its north face 31.5 ft off Linn, which would miss, but the
  pod80 drawing is green and complies, so the lot's best design stands.) Min street setback: civic
  corridor setback stretch false; the 5 ft across-local-street setback (33.130.215.B.1.b(1)) is met (5/5.5).
4 PARKING: fourplex -> 33.266.120; court east of the building, 5.5 ft off Linn (side street), not between
  building and street; within 100 ft of SE 17th, a transit street (stop 61 ft), where B.1.b's no-vehicle-
  access clause does not apply. Cap 1.35/unit = 5 stalls (margin parking_cap), 4 charged.
5 GEOMETRY: big irregular lot; pod at the NW corner. 6 LAND: slope max 44% in a pocket (1,055 sf steep,
  not blocking), grade 1%; no flood. 7 WHO: COM 201, 16,056 sf building 1922, total $5.38M (POLICY).
8 UNCHECKED: lot area/frontage/width/depth not stated for CM2; stories none. 9 FLAGS: DENSITY-MIN only.

## 4. 1S1E19DC  -06400 (R7, 8605 SW 52nd Ave) RIGHT
1 USE: fourplex Yes R7; City layer R7, no overlay/plan district. 2 LOT: 8,509 sf, 100 ft frontage x 85 ft;
  min 4,200; < 14,000 so no min density. 3 BUILDING: pod56 turned end-on (36 ft face to the street),
  building in the north half, 15 ft front / ~5-6 ft side and rear; slack 8.5 (room width 8.5, depth 10.5).
  FAR 4,032/8,509 = 0.47 vs 0.7 (unchecked but passes); coverage 2,016/8,509 = 23.7% vs 2,776 sf (32.6%);
  height 26/30. Outdoor area shape 33 ft vs 12. 4 PARKING: court south of the building, its street edge
  level with the building's front face (behind the front building line, 33.266.120.C.1.a(1)), 17 ft
  from the front lot line (> 10 ft, C.2.a); driveway 20 ft = 20% of the 100 ft front yard vs 40% cap.
5 GEOMETRY: rectangular interior lot, one street (east). pod80 red (-33.5), not the best design.
6 LAND: slope mean 6.4%, max 16%; no flood. 7 WHO: SFR 1978 (ordinary). 8 UNCHECKED: far passes; others
  not stated. 9 FLAGS: none.

## 5. 1S2E08DD  -05200 (CE, 8128 SE Cora St) RIGHT
1 USE: Household Living Y in CE (33.130.txt:343). City layer: CE, no overlay, no plan district.
2 LOT: 6,000 sf, 60 x 100, one street (SE Cora, north). No min lot size (33.130.txt:397); CE min density NA.
3 BUILDING (drawing, EPSG:2913): building 0.3 ft from the Cora line, 2.0 ft from the west line, 21.9 ft
  from the east; all abutting lots CE -> "Lot Line Abutting OS, RX, C, E, or I Zoned Lot: none"
  (33.130.txt:646-647). Max setback: CE outside a pedestrian district applies it to one street when none
  is a transit street (33.130.215.C.2.d) -> Cora, building at 0.3 ft, passes. Height 26/45; FAR 0.67/2.5;
  coverage 33.6% vs 75% (Eastern pattern, 33.130.txt:657); landscaped 25% vs 15%.
  Note: 33.130.215.B.2.c (dwelling-unit WINDOWS 5 ft from a lot line abutting a C/E lot, unless the unit
  has other windows on a street or a 10 ft open space) - the west wall at 2 ft simply cannot carry windows
  (also true under the building code at < 3 ft); a design fact, not a fit failure.
4 PARKING: 33.266.120 (fourplex): 12 ft lane on the east side to a 52 x 43 ft rear court, spaces behind the
  front building line; front-yard share 12 vs 24 ft (40%). Cap 1.35/unit = 5; 4 charged.
5 GEOMETRY: slack 0.5 (FIT-TIGHT, a pass; the 1 ft red rule is for a miss). pod80 red, not best.
6 LAND: flat (max 7%); no flood. 7 WHO: COM 201, 700 sf building 1948, $288k (POLICY).
8 UNCHECKED: none stated for CE. 9 FLAGS: FIT-TIGHT only.

## 6. 1S2E10AD  -09300 (RM1, 11847 SE Powell Blvd) RIGHT
1 USE: fourplex Yes RM1 (33.120.txt:394-403). City layer: RM1 + PLDIST JC (Johnson Creek Basin). PCC 33.537
  (fetched): 33.537.100 general standards = floodway prohibition, nuisance plants, erosion control; tree
  limits (125) only within 20 ft of the Springwater Corridor, in flood hazard area or South subdistrict;
  140 South subdistrict; 160 flood-risk area limits land divisions only. Lot is on Powell at 119th, north of
  the creek, no flood -> nothing applies.
2 LOT: 13,230 sf corner (Powell south 86.5 ft + 12.7 ft chamfer; SE 119th east 128 ft); Table 120-3 33 ft /
  4,000 sf met. Depth 140 < 160 so Map 120-2 frontage rule (33.120.206) cannot bite. Min density 1/2,500
  = 5.3 units vs 4 -> DENSITY-MIN flag (standing ruling).
3 BUILDING (drawing): building 10.0 ft off Powell, 13.2 ft off 119th, 25.5 ft off the west line. RM1 front
  10 / side+rear 5. Powell = transit street (frequent route 41 ft) -> max 20 ft for >= 50% of facade: 56 ft
  facade at 10 ft, passes. Eastern Pattern rear 25% exempt (corner, 33.120.220.B.2.b(1)). FAR 0.31/1.0;
  coverage 15%/50%; landscaped 74%/30%; height 26/35.
4 PARKING: court north of the building, 12.8 ft from the 119th line, entered from the side street (corner
  ruling); not within the 10 ft side-street setback; 20% side-yard paving cap: a 12 ft drive across the
  13 ft strip ~ 156 sf of ~1,660 sf (9%). Cap 1.35/unit = 5; 4 charged.
5 GEOMETRY: rectangular corner lot with a chamfer; slack 49.5 / 11.5. 6 LAND: flat; no flood.
7 WHO: SFR 1926, 2,620 sf (ordinary). 8 UNCHECKED: none binding. 9 FLAGS: DENSITY-MIN only.

## 7. 1S1E22BA  -02300 -- CM2 (+ d, m overlays; Macadam plan district), 6805-6811 S Macadam Ave -- WRONG (RED)
1. USE. Household Living Y in CM2 (33.130.txt:343). City zoning layer (portlandmaps Public/Zoning/3): ZONE CM2, OVRLY d,m, PLDIST MA (Macadam). Neither m nor the plan district is in the FLATS store (only 33.110/120/130/140/150/266/418/610/910/920/930/11.50/100 stored).
   - d overlay: 33.420.045.A.2 exempts Household Living with at most 4 units and buildings at most 35 ft (fetched 420 text) -> exempt.
   - m overlay 33.415.300.B prohibits houses/attached houses/duplexes within 100 ft of a transit street; a fourplex/multi-dwelling is not named -> allowed.
2. LOT. 8,907 sf corner lot; S Florida St on the north (84.5 ft), S Macadam Ave on the east (100.7 ft); CM2 lots on the south and west. No minimum lot size in CM2 (33.130.txt:397). Min density 1/1,450 sf -> 6 units vs 4 = DENSITY-MIN flag (standing ruling, stays green).
3. BUILDING. **33.415.310.A (415-centers-main-st-overlay_0.txt:92-94): "In the Inner Pattern Area the minimum floor area ratio (FAR) for all new development is 0.5 to 1. Pattern areas are shown on Map 415-1."** B (:96-97) is 0.25 for Eastern/Western.
   - Pattern area: BPS_Zoning_Code_Layers/MapServer/69 (Portland Pattern Areas) point query at the lot centre (-122.672028, 45.474886) returns TYPE "Inner Neighborhoods", MapLabel "Inner". Map 415-1, rendered earlier (m415_4/5.png), shows the same Inner area on the west bank south to about the Sellwood Bridge.
   - Pod floor area = 2,016 sf footprint x 2 storeys = 4,032 sf. Dossier margins: far 0.453 (pod56) and 0.449 (pod80). 0.5 x 8,907 = 4,454 sf, so the shortfall is about 420 sf. The pod is fixed, so this is a confirmed miss. No express exception is stated in 33.415.310, and an adjustment is discretionary, so the result is RED.
   - Other Inner-area m rules: 33.415.320 needs 70% of the street-facing facade at the base maximum setback (10 ft, 33.130.215.C), which is achievable. 33.415.330.B.1 caps vehicle area at 30% of a transit-street frontage (Macadam); the court and drive come off Florida, so this is fine. 33.415.200 active ground floor and 33.415.340 windows are exempt for residential until 2029-01-01.
   - Macadam plan district (550-macadam-pd.txt):
     - 33.550.200 max FAR 2.
     - 33.550.210 height per Map 550-1 (not checked; the pod is 26 ft).
     - 33.550.220 Table 550-1 (:111-145): setbacks are set by wall-plane area, and non-street lot lines are exempt on sites of 15,000 sf or less. For street lines: pod56 walls 56x26 = 1,456 sf -> 7 ft, 36x26 = 936 sf -> 5 ft; pod80 80x26 = 2,080 sf -> 9 ft, 25x26 -> 5 ft. The drawings sit 0 / 15 ft (pod56) and 0.5 / 0.5 ft (pod80) off the streets, so they fail as drawn. Pod56 could shift into a 7-10 ft band between the Macadam minimum and the base maximum, and the lot has room, so this is not decisive on its own.
     - 33.550.230 coverage 75% (pod 22.6%).
     - The future light-rail setback (33.550.220.B) applies only to buildings abutting that alignment; the lot is not on it.
   - Base CM2: height 26 vs 45, coverage 22.6 vs 85 (the Inner area allows 100), landscaped 62% vs 15%.
4. PARKING. On a corner, access comes from the side street (Florida). The court is to the south; 4 stalls; the max parking check passes (5 cap).
5. GEOMETRY. Pod and court fit inside the lot (fit slack 20.5 / 31.5). Picture viewed.
6. LAND. No c/p overlays; flat.
7. WHO/WHAT. Prop 201 commercial, 3,168 sf building (1947), $870k total. That is the existing-building POLICY, so it was not used.
8. UNCHECKED. The FLATS list does not even name min FAR. It is a standard the code really holds and the lot fails.
9. FLAGS. DENSITY-MIN only.
Ruling: WRONG, RED, NEW kind "Portland overlay zones not held (m Centers Main Street min FAR 0.5 in the Inner Pattern Area)", item new. The same gap would hit any Inner-area m-overlay site where 4,032 sf / lot area < 0.5, i.e. any lot over 8,064 sf (Eastern/Western: lots over 16,128 sf at 0.25).

## 8. 1N1E22CD  -14900 -- RM1, 3624-3626 N Borthwick Ave -- RIGHT
1. USE. Fourplex Yes in RM1 (Table 120-2). City layer (lot id 21178864): RM1, no overlay, no plan district, no historic/conservation. Not split.
2. LOT. 4,993 sf, 50 ft wide x 99.9 ft deep, interior, alley 16 ft at the rear (observed abuts_alley / alley_at_rear). Table 120-3 33 ft / 4,000 sf: pass. Min density 1/2,500 sf -> 2 units (pass). Max density: "There is no maximum density for any other multi-dwelling zone" (33.120.txt:810-811), RMP only. Map 120-2 frontage rule is for sites deeper than 160 ft; this lot is 100 ft.
3. BUILDING. b2geo:
   - pod56: the building runs 56 ft along the depth and 36 ft across.
   - Setbacks: 10.4 ft to Borthwick (E2, front 10 ft); 5.3 ft and 8.5 ft to the sides (5 ft); 33.4 ft to the rear/alley line. 33.120.220.B.3.g needs no setback from an alley line.
   - Eastern Pattern Area rear setback: exempt at 100 ft deep (33.120.220.B.2.b(1)); the lot is in the Inner area anyway (Boise).
   - Margins: FAR 0.808 vs 1, coverage 40.4 vs 50, landscaped 43.8 vs 30, height 26 vs 35 (gable measured at the average, 33.930), outdoor 2,185 vs 192 sf.
   - 33.120.230.B max 100 ft building length: pass. 231 main entrance, 232 15% windows: design detail, achievable.
4. PARKING. Court 27 x 36 ft between the building and the rear line, 6.4 ft off the alley line; 4 stalls x 9 ft = 36 ft; aisle = 16 ft alley + 6.4 ft + spare. 33.266.120 alley rule (all access from the alley) is satisfied. Fire hose 106.5 vs 150.
5. GEOMETRY. Picture viewed: a plain rectangular lot; the building and court sit inside the dashed envelope. Pod80 is red (does not fit, 50 ft width); pod56 slack 6.0.
6. LAND. Slope p85 5.5% (max 18% on a single 1 m cell); grade 0.6%. No flood. No c/p.
7. WHO/WHAT. Prop 101 SFR, 1970, 1,504 sf, $545k. An ordinary dwelling, so no policy note.
8. UNCHECKED. min_frontage (Portland RM has none except Map 120-2), depth, stories (none stated in RM1), parking_stalls (none required with transit and parking reform). None fail.
9. FLAGS. None.

## 9. 1N2E26CC  -03100 -- R7 (+ h overlay, Glendoveer plan district), 1915 NE 125th Ave -- RIGHT
1. USE. Fourplex Yes in R7, by right (33.110.txt:313, 1486-1487).
   - City layers (lot 21242948): ZONE R7, OVRLY h, PLDIST GL. BPS layer 0 and layer 143 confirm Glendoveer at the lot point (-122.534717, 45.536708).
   - Layer 1 (Subdistricts) is empty, so no separate "formerly LR7.5" polygon exists. I took the plan district as applying, because 33.530.020 says it applies to R7 land formerly LR7.5 and the whole district is R7. That is the conservative choice.
   - h overlay: base height governs (33.400).
   - The maintained-street gate (33.110.txt:1535-1540) is unmeasured; this is a known pattern.
2. LOT. 10,130 sf, 70 x 144.7 ft, interior, fronting NE 125th (east line E1).
   - Min lot area 4,200 (Table 110-7): pass.
   - 33.530.030 lot size and width apply to land divisions only, so they do not apply here.
   - Min density applies only to R7 lots of 14,000 sf or more, so not here.
3. BUILDING. The R7 base rules are what FLATS used:
   - Front setback 15 ft; the pod56 is drawn 15.5 ft back.
   - Sides 5 ft; drawn 5.0 ft (south) and 28.5 ft (north).
   - Coverage 2,250 + 15% x 5,130 = 3,020 sf, i.e. 29.8%; the pod is 19.9%.
   - FAR 4,032/10,130 = 0.40 vs 0.7. Note that far is marked unchecked.
   - Height 26 vs 30.

   **Glendoveer 33.530.040.A (530-glendoveer-pd.txt): front 30, side 10, rear 15.** FLATS does not hold these. Re-fitting pod56 by hand:
   - **Depth:** 144.7 - 30 = 114.7 ft available, against 56 ft of building plus 51 ft of court = 107 ft. That leaves 7.7 ft between the court and the rear line. The 15 ft rear setback binds buildings only; the building's rear face would sit 58.7 ft from the rear line.
   - **Width:** the building moves north 5 ft so it sits 10 ft off the south line. Building plus lane is 48 ft, ending 12 ft from the north line, and the lane is not a building.
   - Result: pod56 fits.
   - Pod80 does not fit under these setbacks: 30 + 80 + about 45 = 155 > 144.7. One fitting design is enough for GREEN.
4. PARKING. Rear court with 6 stalls seated and 4 charged. Lane off 125th; front-yard vehicle share 12 vs 28 ft (40%). No stalls within 10 ft of the front line. Fire hose 110.5 ft; about 125 ft after the 15 ft shift, still under 150.
5. GEOMETRY. Picture/drawing checked via b2geo. Plain rectangle; the north line has a small jog (E0/E4).
6. LAND. Slope 4% max (10 m DEM). No flood, no c/p.
7. WHO/WHAT. Prop 101 SFR 1954, $415k. Ordinary.
8. UNCHECKED. far (passes at 0.40). Lot width/frontage/depth: R7 Table 110-7 width/depth apply to land divisions. min_density does not apply under 14,000 sf.
9. FLAGS. None.

Pattern: the second Glendoveer lot where the unheld 30/10/15 setbacks shrink the room but do not flip the result.

## 10. 1S2E11CB  -04600 -- CM2 (Johnson Creek Basin plan district), 3726 SE 122nd Ave -- RIGHT
1. USE. Household Living Y (33.130.txt:343).
   - City layer: CM2, PLDIST JC, no d/m overlay.
   - BPS Subdistricts layer at the lot point (-122.537221, 45.495076): none, so it is not in the South subdistrict or Springwater. Not floodway (flood sfha/floodway false).
   - The 33.537 provisions that bind outside those areas govern only land divisions, so the plan district adds nothing.
   - Pattern Areas layer: Eastern.
2. LOT. 7,248 sf, 50 x 145 ft, interior; the street (west line E2) is SE 122nd.
   - Neighbours: CM2 to the north (04500), south (04700) and east (04300/04400). RM2 across 122nd.
   - CM2 has no min lot size (:397). Min density 1/1,450 sf gives 5 units vs 4: the DENSITY-MIN flag.
3. BUILDING (b2geo, pod56):
   - Building is 10.5 ft from 122nd, 0.9 ft from the south line, and 12.5 ft from the north line (the lane is 0.5 ft from that line). The court runs 66-119 ft back.
   - Table 130-2 sets no side or rear setback against C zones.
   - Front: the minimum is 10 ft on a civic corridor (observed civic_corridor true) and the max-setback limit is 20 ft for 50% of the facade (33.130.215.C), so 10.5 passes. If 122nd were not a civic corridor, the min would be 0 and the max 10, and the building could slide 0.5 ft forward; either way it fits.
   - The "5 ft across a local street from RF-RM2" minimum does not apply, because 122nd is not a local street and is within 100 ft of a transit street.
   - The window rule 33.130.215.B.2.c (33.130.txt:898-903) says windows of dwelling units must sit 5 ft from a line abutting a C lot. The south wall, at 0.9 ft, is blank or has only exempt windows. The north wall, 12.5 ft from the CM2 line, can carry every unit's windows. This limits window placement only, not a dimensional fit.
   - Margins: FAR 0.556/2.5, coverage 27.8/85 (Eastern), landscaped 37.6/15, height 26/45.
   - 33.130.230.B ground floor windows: fourplexes exempt (:1394-1396). 15% street-facing windows: design detail.
4. PARKING. Court at the rear, 5 stalls seated, 4 charged; 12 ft lane on the north side. Front-yard vehicle share 12 of 20 ft (40% of 50). Parking max 1.35/unit gives a cap of 5. Fire hose 101.6 ft.
5. GEOMETRY. Plain rectangle; both pods fit (slack 27 / 3.5).
6. LAND. Flat (2% max). No flood.
7. WHO/WHAT. Prop 121 house 1956, sold 2025 for $500k. Ordinary.
8. UNCHECKED. Lot dimensions: CM2 states none. Stories: none stated. Parking stalls: none required.
9. FLAGS. DENSITY-MIN only.

## 11. 1N1E08CA  -11600 -- R5, 8017 N Fiske Ave (corner Fiske / Drew) -- RIGHT
1. USE. A fourplex is Yes and by right under 33.110.265.E (33.110.txt:313, 1534-1541).
   - Frontage on maintained streets (Fiske, Drew) is assumed; this is a known unmeasured gate.
   - City layer: R5 only, no overlay.
2. LOT.
   - Size and shape: 6,398 sf; Fiske line E6 55 ft, Drew line E2-E5 116 ft, interior side E0 116 ft, rear E1 55 ft. A true two-street corner.
   - Lot area: Table 110-7 sets 3,000 sf for R5, so it passes.
   - Density: R5 min density applies only to lots of 10,000 sf or more, so it does not apply. The maximum is 4 units (E.1).
3. BUILDING. Distances from b2geo for pod56:
   - **Setbacks.** The building is 10.5 ft from Fiske and 13.5 ft from Drew. Its interior-side gap is 5.5 ft, and it sits 49.8 ft from the rear line.
     - Table 110-4 (:432-474) gives R5 a 10 ft front and 5 ft side and rear, so all pass.
     - If Drew were taken as the front, 13.5 is still at least 10, so it passes either way.
   - **Coverage.** Table 110-5 gives 2,250 + 15% x 1,398 = 2,460 sf, i.e. 38.4%. The pod is 31.5%.
   - **FAR.** 4,032/6,398 = 0.63, against 0.8 for 4 or more units. The far check is unchecked but passes.
   - **Height.** 26 ft against 30.
   - **Outdoor area.** 33.110.240 requires 250 sf per lot with a 12 ft square. The shape check gives 13 vs 12, so it passes.
   - **Visitability (E.3).** One unit needs 200 sf of living area on the entry floor. A 14x36 unit has 504 sf, which is design-achievable.
4. PARKING. The court sits at the west end, with access from Drew (the side street, per Steph's corner ruling).
   - **Side-street setback.** The court is 13.4 ft off Drew, outside the 5 ft side-street setback (33.266.120.C.2.a).
   - **Behind the building lines.** The parking is behind both the front and side-street building lines (C.1.a).
   - **Side-street paving cap.** C.1.b allows 20% of the land between the Drew line and the side-street building line: 116 x 13.5 = 1,566 sf, so the cap is 313 sf. A 9-12 ft drive across 13.4 ft takes 120-160 sf, so it passes.
   - **Stalls and fire access.** 4 stalls at 9x18 ft; fire access 79.9 ft.
5. GEOMETRY. I viewed the picture. The lot is a slanted rectangle, the building and court sit inside the envelope, and pod56 has 6.5 ft of slack. Pod80 does not fit and is red.
6. LAND. p85 slope 5.4%; the 15% maximum is a single cell. No flood.
7. WHO/WHAT. Prop 101 house, 1910, $624k. It is an ordinary house.
8. UNCHECKED. The far check passes. Lot width, depth and frontage are land-division standards in R5, not development standards. Min density does not apply.
9. FLAGS. None.

## 12. 1S1E18AB  -05200 -- R7, 4606 SW 53rd Ave -- RIGHT
1. USE. A fourplex is Yes in R7 and allowed by right (33.110.txt:313 and 1534-1541). The City layer (lot 21368983) shows plain R7 with no overlay and no plan district.
2. LOT. The lot is 10,001 sf, about 100 x 100 ft, with a small jog on the east (rear) line. Its front is SW 53rd on the west line (E2); there are no other streets. The minimum lot area is 4,200 sf, so it passes. Minimum density does not apply to R7 lots under 14,000 sf.
3. BUILDING. pod56 is drawn width-facing, 56 ft along 53rd.
   - Setbacks: 17.0 ft from the front (15 required) and 6.7 ft from the north side (5 required). The south side is far away: the building is 36.6 ft from it and the lane 24.6 ft.
   - Coverage: Table 110-5 gives 2,250 + 15% x 5,001 = 3,000 sf (30%); the pod is 20.2%.
   - FAR: 0.40 vs 0.7. This is listed as unchecked, but it passes.
   - Height: 26 vs 30. Height is measured from a base point that tracks the highest nearby grade, so a slope does not penalise it.
   - Outdoor area: shape 16 vs 12, so it passes.
4. PARKING. A 12 ft lane runs along the south face of the building to a rear court of 8 seated stalls, 4 of them charged.
   - The vehicle area in the front setback is the 12 ft drive only. It is 12% of the frontage (40% cap), and there are no stalls within 10 ft of the front line.
   - The parking sits behind the front building line, as 33.266.120.C.1.a requires.
   - Fire access is 102 ft.
5. GEOMETRY. I viewed the picture. The envelope has a carve in the south-west corner for steep ground, and the building, lane and court all sit in the north and east. Slack is 3.5 ft. pod80 does not fit and is shown red.
6. LAND. The p85 slope is 11.9% and the maximum is 26%. The 1,672 sf of steep ground does not block (steep_blocks false), and the grade under the pod is 3.3%. There is no flood risk and no c/p overlay. The potential landslide hazard rules are a land-division matter only.
7. WHO/WHAT. Prop 101 house, built 1957, $628k. Ordinary.
8. UNCHECKED. The far check passes. The width, depth and frontage standards are land-division standards, and minimum density does not apply.
9. FLAGS. None.

## 13. 1N2E31AA  -17500 -- RM2, 1122-1124 NE 59th Ave -- RIGHT
1. USE.
   - Fourplex is Yes in RM2 (Table 120-2).
   - City layer (lot 21252752): RM2 with no overlay and no plan district.
   - Pattern Areas layer at the lot point (-122.602892, 45.531404): Inner Neighborhoods.
2. LOT.
   - Size: 8,500 sf, 85 ft along 59th (west line E3-E6) by 100 ft deep. Interior lot.
   - Table 120-3 (33 ft / 4,000 sf): pass.
   - Minimum density: 1 unit per 1,450 sf gives 5.9, so 6 units against 4. This is the DENSITY-MIN flag.
   - Not deeper than 160 ft, so the Map 120-2 frontage rule does not apply.
3. BUILDING (pod56, width-facing).
   - Setbacks: front 10.0 ft, north side 7.5 ft, south side 21.2 ft, rear 53.9 ft. Table 120-4 asks for 10/5/5, so all pass.
   - Rear setback: the Eastern-area rule does not apply, since the lot is in the Inner area and only 100 ft deep.
   - FAR 0.474 vs 1.5; coverage 23.7 vs 60; landscaped 49.6 vs 20; height 26 vs 45.
   - Outdoor area 4,216 sf vs 192 sf (48 sf per unit).
   - Building length 56 ft, under the 100 ft maximum within 30 ft of the street (33.120.230.B).
   - Main entrance and 15% windows are design detail.
4. PARKING.
   - Layout: a 12 ft lane along the south face (9.2 ft off the south line) leads to the rear court, which sits 2.8 ft off the rear line. 5 stalls seated, 4 charged.
   - A fourplex falls under 33.266.120, so the 33.266.130 perimeter landscaping does not apply.
   - Front-yard paving: 12 of 85 ft (cap 40%), with the parking behind the building line.
   - Fire hose: 92 ft.
5. GEOMETRY. Plain rectangle. Both pods fit, with slack of 2.5 ft and 4.0 ft.
6. LAND. Flat (p85 3.7%). No flood risk and no c/p overlay.
7. WHO/WHAT. Prop 101 house, 1956, 2,997 sf, $799k. Ordinary.
8. UNCHECKED. Frontage, depth and stories: RM2 states none that this lot fails. No parking is required.
9. FLAGS. DENSITY-MIN only.

## 14. 1S2E17CA  -16200 -- R2.5, 7022 SE Ramona St -- RIGHT
1. USE. Fourplex is Yes in R2.5 and allowed by right (33.110.txt:313, 1534-1541). The City layer (lot 21456029) shows R2.5 with no overlay and no plan district.
2. LOT.
   - 7,999 sf: 80 ft on Ramona (the north line, E4/E5) by 100 ft deep. It is two 40 ft platted lots joined, and an interior lot.
   - Lot area: the Table 110-7 minimum is 1,500 sf, so it passes.
   - Minimum density (33.110.txt:425-426): lots of 5,000 sf or more need 2 or more units; this one gives 4, so it passes (margin min_units 4 vs 2).
3. BUILDING (pod56, width-facing).
   - Setbacks: front 10.2 ft (10 required); west side 5.5 ft (5); east side 18.4 ft; rear 46 ft or more.
   - Coverage: 2,250 + 15% x 2,999 = 2,700 sf, i.e. 33.75%. The pod covers 25.2%.
   - FAR: 4,032 / 7,999 = 0.50 against 1.0 for 4 units in R2.5. The FAR check is marked unchecked, but it passes.
   - Height: 26 ft against 35.
   - Outdoor area: 200 sf at 10x10 is required; there is 3,715 sf in a 32 ft shape.
4. PARKING.
   - Layout: a 12 ft lane on the east side of the building, 6.4 ft off the east line, runs to a rear court about 68 x 51 ft that sits 2 ft off the rear line. 7 stalls are seated and 4 charged.
   - Rules: the parking is behind the front building line (33.266.120.C.1.a), and the front-yard drive is 12 of 80 ft against the 40% cap.
   - Fire hose: 93.5 ft.
5. GEOMETRY. A plain rectangle. Both pods fit, with slack of 2.0 ft and 4.0 ft.
6. LAND. Slope p85 is 6.4%; the 16% maximum is a single cell. The grade under the pod is 0.8%. No flood.
7. WHO/WHAT. Prop 101 house, built 1954, $579k. Ordinary.
8. UNCHECKED. FAR passes. Width, depth and frontage are land-division standards.
9. FLAGS. None.

## 15. 1N1E22CB  -01200 -- RM1 + Mississippi Conservation District, 4044 N Missouri Ave -- RIGHT (with a heavy POLICY note)
1. USE. Fourplex Yes in RM1 (Table 120-2).
   - City layers (lot 21178468): ZONE RM1, CONSV MS. Layer 123 names it the "Mississippi Conservation District" (58.8 acres). Layer 29 puts the lot in the Albina Community Plan area. FLATS does not hold 33.445 (Historic Resource Overlay) or 33.218 (Community Design Standards); I fetched both from portland.gov.
   - 33.445.210.D.1.b (445-historic_1.txt:1524-1531): "Building a new structure" in a Conservation District "is subject to historic resource review" unless exempt. The D.2 exemptions cover only small items; x covers detached accessory structures up to 200 sf, not a fourplex.
   - 33.445.500/510: the Community Design Standards are "a clear and objective alternative" to historic resource review for Conservation Districts. They are excluded in the Central City, for demolition proposals (510.D), and for alterations to contributing resources.
   - 33.218.015.A: "If the proposal meets the standards of this chapter, no historic resource review is required"; B: "Adjustments to these standards are prohibited."
   - So on a vacant lot (FLATS ignores the existing house) the objective path exists, and that counts as by-right.
2. LOT. 4,995 sf, 50 x 99.9 ft, interior, with a 15 ft alley at the rear. Table 120-3: pass. Min density is 2, max is none.
3. BUILDING. The same layout as lot 8:
   - pod56 is 56 ft deep x 36 ft wide; front 10.4, sides 5.4 / 8.5, rear 33.4.
   - FAR 0.807/1, coverage 40.4/50, landscaped 43.1/30, height 26/35.
   - Community Design Standards 33.218.110 (218-cds.txt:312-615), checked against the pod:
     - A: foundation landscaping 3 ft and a front tree. These sit in the 10 ft front yard: OK.
     - B: front setback no more than 25 ft: 10.4, OK.
     - C: residential buffer applies only to RM2+ sites, so not here.
     - E: the front elevation is 36 x 26, about 936 sf, over 750 sf, so it must be split into planes of 500 sf or less (porch, bay or recess). Architectural.
     - F: roof pitch 6/12-12/12, or a two-part cornice. Architectural.
     - G: the main entrance faces the street, with a 9x7 ft porch for multi-unit (6x4 per single dwelling) and ornamental columns.
     - I/J/K/L/P: foundation, siding, windows, trim, eaves. Architectural.
     - R: in Mississippi, a stone or cast-stone foundation on street elevations (R.5). In Albina, a dormer or gable per 40 ft (R.3), floor-level delineation, and a ground floor at least 2 ft above grade (R.4). The extra 2 ft makes the pod about 28 ft against 35, still OK; the visitable route would need a ramp.
   - None of these are dimensional fits that FLATS models. They are detailing a factory pod would have to carry, and nothing in the stored or fetched text makes them impossible.
4. PARKING. H.1: "If the site is served by an alley, access for motor vehicles must be from the alley." The drawn court uses the alley as its aisle: OK. H.2 (no vehicle area between the building and the street) and H.3 (no parking in the front setback): met, since nothing is paved in front. 33.266.120.C.3 alley rule: met.
5. GEOMETRY. Identical to lot 8; slack 5.0.
6. LAND. p85 6.4%, no flood, no c/p.
7. WHO/WHAT. **Layer 113 shows 4044 N Missouri Ave (1910) as "Contributing" to the Mississippi Conservation District.** Under 33.445.210.E.1, demolishing a contributing resource "is subject to demolition review". Under 33.445.510.D, "proposals that meet the definition of demolition ... are not eligible to use the Community Design Standards", so the new pod would also need discretionary historic resource review. That gate exists only because of the existing house. Under the 2026-10-14 POLICY (existing buildings stay GREEN) it is recorded in the policy column, NOT as WRONG. Steph may want to rule on whether a protected (contributing) building is a different thing from an ordinary existing building. It is a legal designation, not just occupancy.
8. UNCHECKED. As lot 8; nothing fails.
9. FLAGS. None.
