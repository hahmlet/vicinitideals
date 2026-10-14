# B7 notes: Oregon City x3, Tualatin x2, West Linn x2, Wilsonville x2, Beaverton x4 (run 74 GREEN lots)

Stored code text prefix: flats/provenance/docs/or/<county>/<city>/. Verdict unknown / RULE_UNVERIFIED is the normal as-if-signed state.

## 1. 22E31DC02000 Oregon City R-6, 1008 Summit St -- RIGHT
1. USE: 17.zoning.txt:4047-4052 "Permitted uses in the R-10, R-8 and R-6 districts are: ... E. Quadplexes; F. Townhouses". 17.16.020/.025 (L5195-5205): middle housing is "a Type I minor site plan and design review ... concurrently with a building permit" = ministerial. Master plans section 17.08.030 repealed (L4083-4086). Zone R-6 whole lot (zone_frac 1.0), no overlay.
2. LOT: Table 17.08.040 (L4112-4166) R-6 quadplex 7,000 sf (lot 9,999.99), width 50 (100), depth 70 (100). Density Table 17.08.050 (L4184-4193) min 5.8 du/ac -> 0.2296 ac x 5.8 = 1.33 -> 2 units <= 4; max density counts a quadplex as one unit (L4200-4203).
3. BUILDING: front 10, interior side 5, corner side 10, rear 20, coverage 40% (pod 20.2%), height 35 (pod 26; cap not in the 22-30 band).
4. PARKING/ACCESS: corner lot; front lot line = narrowest frontage (17.04.490, L1701-1704) -- both 100 ft; engine front = Summit (front_deg 154 = the north line), side_street true, court opens onto Bellevue Ave (west line) behind the building. 16.12.035 Table A local street corner distance 25 ft is "for all uses other than ... quadplexes" (16.12.streets.txt:1012-1017); the opening sits in the south half of a 100 ft frontage, 50+ ft from the corner anyway; 5 ft from property line (A.2) -- room to shift. Approach 10-36 ft (Table D, L1105-1110). 4 stalls -> no backing rule (J) trigger.
5. GEOMETRY: 100 x 100 ft square, building in the north corner, court behind it reaching Bellevue; slack 5.5 (pod56) / 16.5 (pod80). Fire route 84 ft.
6. LAND: slope max 16%, p85 5.6%, steep_sqft 0; no flood, no overlay.
7. WHO: SFR 1920, 1,499 sf, total $451k -- ordinary house.
8. UNCHECKED: frontage (no OC number), depth (70 vs 100), FAR (none), stories (none) -- nothing fails.
9. FLAGS: UTILITY-EASEMENT-ASSUMED (note 3: "Public utility easements may supersede the minimum setback", L4160) -- 10 ft assumed, equals the front setback.

## 2. 31E01DA00229 Oregon City R-10, 996 South End Rd -- WRONG (RED), KNOWN-67 kind in a new place
1. USE: quadplex permitted outright in R-10 (17.zoning.txt:4047-4052), Type I (L5195-5205). Zone whole lot.
2. LOT: Table 17.08.040 R-10 quadplex 10,000 sf (lot 11,022.9), width 65 (76.9), depth 80 (143.4). Min density 3.5 du/ac -> 0.885 -> 1 unit.
3. BUILDING: front 20, side 8, rear 20, coverage 40% (pod 18.3%), height 35 (26).
4. ACCESS: one street, South End Rd. City TSP layer (maps.orcity.org Transportation_PUBLIC/MapServer/4, the one pipeline.yaml street_class_oregon_city reads) returns FunctionalClass "Minor Arterial" for every South End Rd segment. 16.12.035 G (no backing onto an arterial) is met by the rear court; H allows the arterial access when "there is no other alternative" (single frontage).
   DEDICATION (the finding): 16.12.011.B (16.12.streets.txt:79-90) "Compliance with this chapter is also required for new construction ... of all single-family detached residential and middle housing units ... All single-family detached residential and middle housing units shall provide any necessary dedications, easements or agreements as identified in the transportation system plan and this chapter, subject to constitutional limitations." Table 16.12.016 (L327-360) Minor Arterial, Residential: "100 ft." right-of-way, 68 ft pavement. Reductions only by an alternative street design via 16.12.013 modification = Type II (L300-305, L131-145) -- discretionary.
   Existing ROW: distance from this lot to the lots across the road, read-only SQL on flats.lots (EPSG:2913 ft): 995 South End Rd 59.2 ft, 1007 South End 59.3 ft, 1011 South End 61.4 ft. Half-width ~29.6 ft vs 50 ft -> ~20.4 ft strip off the front.
   Our encoding (oregon-city.yaml:88-103) files 16.12.016 as "Right-of-way geometry, delivered when land is subdivided ... on the far side of the lot line" -- but 16.12.011.B applies it to middle housing on an existing lot.
5. GEOMETRY: 143 x 77 ft interior lot; building at the street end, lane down the south side, court at the rear. fit depth 102.5 vs 87 required (slack 15.5). After ~20.4 ft: ~82.1 vs 87 = about -4.9 ft (RED by the 1 ft rule). Area after: 11,022.9 - 20.4 x 76.9 = ~9,454 sf < 10,000 sf R-10 quadplex minimum. pod80x25 already red.
   Caveat: "subject to constitutional limitations" -- a Dolan proportionality argument might shrink the strip, but that is case-by-case (and a reduced design is a Type II modification), so not by-right.
6. LAND: slope max 30% but steep_sqft 0, p85 6.4%; no flood/overlay.
7. WHO: SFR 1973, 2,118 sf, ordinary.
8. UNCHECKED: depth/frontage/FAR -- nothing else bites.
9. FLAGS: UTILITY-EASEMENT-ASSUMED (10 ft = front setback 20, no effect).

## 3. 31E01CA05600 Oregon City R-10, 18886 Lafayette Ave -- RIGHT
1. USE: quadplex permitted outright (17.zoning.txt:4047-4052), Type I (L5195-5205). R-10 whole lot, no overlay.
2. LOT: Table 17.08.040: quadplex 10,000 sf vs 10,009.9 (margin 9.9 sf -- thin; neighbours are the same 91 x 110 plat lots at 10,009 sf, so this is the platted size), width 65 vs 91, depth 80 vs 110. Min density 3.5 du/ac -> 1 unit.
3. BUILDING: front 20, side 8, rear 20; coverage 20.1% vs 40%; height 26 vs 35.
4. ACCESS: one street. City TSP layer at this point: Lafayette Ave "Local" (a different stretch of Lafayette is a Collector, not this one). ROW gap to 18885/18895 Lafayette = 60.0 ft >= 54 ft local residential (Table 16.12.016) -> no dedication (unlike lot 2). Lane down the NW side, court at the rear; approach 10-36 ft (Table 16.12.035.D).
5. GEOMETRY: rectangle 91 x 110; across 68 (56 + 12 lane) in a 75 ft envelope width; depth 69.5 vs 67 -> slack 2.5 ft. pod80 red. Fire route 115.6 ft.
6. LAND: slope max 14%, steep 0; no flood.
7. WHO: SFR 1976, 1,110 sf, sold 2026-06 $480k -- ordinary.
8. UNCHECKED: nothing in Table 17.08.040 beyond those above; no FAR.
9. FLAGS: UTILITY-EASEMENT-ASSUMED (10 ft < 20 ft front setback, no effect).

## 4. 2S126CB10300 Tualatin RL, 10468 SW Moratoc Dr -- RIGHT
1. USE: Table 40-2 "Quadplex P" (40-41.residential.txt:118-120); design standards 73A.030 are "Clear and Objective (Type I)" (73A...txt:19-63) -- windows/roof/wall elements, walkway; ministerial.
2. LOT: Table 40-3: quadplex 6,500 sf (lot 9,759), width 50 (lot ~70 ft along the north line; own zoom plot from flats.lots), no quadplex density cap ("Quadplex None").
3. BUILDING: front 15, secondary frontage on corner 10 ("determined by the orientation of the structure, based on the location of the front door"), side 5, rear 15, garage door 20 (no garage), height 35 (pod 26), coverage 60% (20.7%), FAR 5,001-10,000 sf 0.7 -> 4,032/9,759 = 0.41 (unchecked but passes).
4. PARKING/ACCESS: Table 73C-1 middle housing "None" minimum/maximum (73C.parking.txt:149-155). Driveway 10-24 ft at the ROW line (73C.090(1)(a), L530-537); quadplexes may be within 5 ft of a side line (L650). 73C.210(3) 5 ft perimeter and (4) 25 sf island per stall (L684-702) -- the screen encodes these (parking queue 36); room 11.5-16.5 ft absorbs 100 sf. TDC 75 access spacing not in the store (cannot test).
5. GEOMETRY: 70 x 140 ft corner rectangle with a rounded SW corner; Moratoc Dr (50 ft ROW) on the south, a 60-65 ft street (SW 105th Ave area, ML/FD-10 land across) on the west. pod56 front = Moratoc, court at the rear off the west street (side street, per the corner ruling). Depth 109 vs 93.5 needed. pod80 red. Fire 96.9 ft. The dossier picture is zoomed out by a 364,000 sf ROW polygon; I drew my own zoom from flats.lots geometry.
6. LAND: max slope 22.5%, p85 12.9%, steep_sqft 0; pad grade 4.2%; no flood.
7. WHO: SFR 1986, 1,968 sf. Policy blank.
8. UNCHECKED: width, FAR (pass). Tualatin public-improvement / ROW chapter (TDC 74) is not in the store, so a dedication on the west street cannot be tested (pattern note).
9. FLAGS: none. (sewer main_dist 9,826 ft looks like missing CWS data, not a zoning gate.)

## 5. 2S135BD04700 Tualatin RL, 9860 SW Lumbee Ln -- RIGHT
1. USE: Quadplex P (40-41.residential.txt:118-120); 73A Type I clear-and-objective design (ministerial).
2. LOT: 10,758 sf vs 6,500 sf; four-sided corner lot (own zoom plot): SW line ~70 ft on Eno Pl, NW line ~111 ft + curve on Lumbee Ln, SE 120 ft, NE 78 ft. Real intersection (Eno Pl runs SE to its bulb; Lumbee continues west), not a bend.
3. BUILDING: Table 40-3: front 15, secondary frontage 10 (front door decides, L213-218), side 5, rear 15; height 35 (26); coverage 60% (18.7%); FAR 10,001-19,999 sf 0.6 -> 4,032/10,758 = 0.37.
4. PARKING/ACCESS: no minimum (Table 73C-1 middle housing None). pod56 front = Eno Pl (front_deg 134 = the SW line), side_street true, court reached from Lumbee Ln. Both local; Tualatin sends only double-frontage lots to the lowest class (36.400(1)(b)) -- not this lot. Driveway 10-24 ft (73C.090).
5. GEOMETRY: width room 8.5, depth 87 vs 73.5 (slack 13.5). pod80 red. Fire 87 ft.
6. LAND: 1,147 sf steep ground on the lot, steep_blocks false (outside the pad), pad grade 1.3%; max 28.7%; no flood.
7. WHO: SFR 1998, 4,129 sf, $1.12M -- a large but ordinary house. Policy blank.
8. UNCHECKED: width/FAR pass; TDC 74/75 not stored.
9. FLAGS: none.

## 6. 22E30BC03300 West Linn R-10, 5796 Robert Moore St -- RIGHT
1. USE: 11.030 (11.r-10.txt:53-63) "Single-family attached or detached residential unit. ... c. Quadplex residential units" permitted outright. 11.020.A: outright uses need no approval "except that some uses require design review pursuant to CDC 11.090(B)". 11.090(B) (L205): Chapter 55 design review applies "to all uses except attached and/or detached single-family dwellings ...". Definitions 02.definitions.txt:947-949: single-family attached/detached "may be further defined as a duplex, triplex, or quadplex" -> the quadplex is inside the exception. By-right.
2. LOT: 11.070 (L129-190): min lot 10,000 sf for a single-family attached/detached unit (15,000), width at front lot line 35, average 50 (120).
3. BUILDING: front 20, interior side 7.5, street side 15, rear 20; height 35 measured to the highest ridge (41.005, 41.steep-lots.txt) vs 26; coverage 35% (13.4%); FAR quadplex 0.60 (0.27; steep Type I/II land of ~1,127 sf barely moves it). Chapter 43 sidewall articulation (43.sidewall.txt 43.040: planes of 700 sf or less, or gable end to the side, or eaves <= 22 ft) is a design standard applied administratively; no footprint number to fail.
4. PARKING/ACCESS: no minimum; maximum by "most similar use" multifamily 2.0/unit = 8 (46.parking.txt:133-156) vs 4. Curb cut 16-36 ft, and on a local street no closer than 35 ft to an intersecting ROW line (48.access.txt:173-190). Both streets local (West Linn RoadFCs CITYCLASS 9 for both lines). Court opens onto Lewis St behind the building, ~56+ ft from the Robert Moore line. Driveway for 2-4 homes 14-20 ft (48.access.txt:111) -- the court meets Lewis directly.
5. GEOMETRY: 120 x 125 ft corner square; Robert Moore St (NE, 50 ft ROW) front; Lewis St (NW, 50 ft ROW) side. pod56 slack 22.5, pod80 5.5. Fire 94-114 ft.
6. LAND: max slope 32%, p85 10%, 1,127 sf steep not under the pad; pad grade 2.6%; no flood; not in the Willamette historic district.
7. WHO: SFR 1935, 3,073 sf, total $1.05M; sale $0 2018 (family transfer) with a real address -- ordinary house. Across Lewis: NO SITUS R-10 parcels (one SFR, one 401 rural) -- not this lot.
8. UNCHECKED: frontage/avg width/depth -- pass.
9. FLAGS: none.

## 7. 21E23BB03900 West Linn R-15, 1486 Marylhurst Dr -- RIGHT
1. USE: R-15 10.030 lists the quadplex as an outright single-family attached/detached type (same structure as R-10); 10.020.A (10.r-15.txt:31) and 10.090(B) (L208) exempt "attached and/or detached single-family dwellings" from Chapter 55; definitions 02.definitions.txt:947-949 fold the quadplex into those. By-right.
2. LOT: 10.070: 15,000 sf (18,750), width at front lot line 45, average 80 (100 x 187.5 rectangle).
3. BUILDING: front 20, side 7.5, street side 15, rear 20; height 40 to the ridge (26); coverage 30% (10.8%). FAR 0.45 (R-15 prints no separate quadplex row, unlike R-10's 0.60): 4,032 / 18,750 = 0.215. "Type I and II lands shall not be counted toward lot area ... except that a minimum floor area ratio of 0.30 shall be allowed regardless" -> at least 5,625 sf allowed, so passes even with the 5,325 sf of steep ground removed. FAR is in `unchecked`, but passes.
4. PARKING/ACCESS: no minimum, max 8. Encoding uses the stricter 24 ft multifamily drive (west-linn.yaml:680-830); building near Marylhurst Dr, lane down the NE side, court at the rear; curb cut 16-36 ft. One street, local.
5. GEOMETRY: across 60 (36 + 24) in an 85 ft envelope width; pod56 slack 25, pod80 5. Fire 121 / 139 ft.
6. LAND: max slope 75% somewhere on the lot (steep 5,325 sf, rear), not under the pad (grade 3%); steep_blocks false. 41.010 steep-lot rules key on the building site's average slope >= 25% -- not this pad.
7. WHO: SFR 1962, 1,958 sf, ordinary.
8. UNCHECKED: FAR (passes, above), avg width (100 vs 80).
9. FLAGS: none.

## 8. 31W15DC05351 Wilsonville PDR2, 29411 SW Camelot St -- CANT_TELL
1. USE: 4.124 PDR permitted uses include quadplexes; Table 2 PDR-2 has a quadplex row. Gate check (the coordinator's question): 4.030(.01)A.4 (4.planning.txt:2350-2355) makes "building permits for residential structures in residential zones not subject to Site Design Review, except for multi-family structures with seven or more units, meeting clear and objective ... standards ... on lots ... legally created" a Class I ministerial decision. Site Design Review exempts middle housing (4.420(.01)A.1). The 4.140 planned-development permit is triggered by parcels over 2 acres (L12609-12700); this is an 8,567 sf lot already platted. 4.140(.10)A (L12919-12927) says "the approved final plan ... shall control the issuance of all building permits and shall restrict the nature, location and design of all uses"; 4.140(.10)D and Table 1 note b (L4668) exempt middle housing from density beyond one unit per lot. The text gives no express middle-housing override of (.10)A, so whether this subdivision's Stage II conditions restrict lot uses is a FACT about the old PD file, not in the store. It is the same for every Wilsonville PDR lot; ruled as by-right (statute + Class I path), noted as a pattern.
2. LOT: Table 2 PDR-2: min 7,000 sf (8,567); frontage 30 (85.8); width at building line 60 (85.7); depth 70 (100). Interior lot on Camelot St (one front, bearing 178.5).
3. BUILDING: 4.113(.02)B lots <= 10,000 sf: front 15, side 7 (two storeys), rear 20; height 35 (26); coverage: the PDR-2 tier for 8,000-12,000 sf is 40/50, the engine charged the 45% 7,000-8,000 tier -- wrong band but harmless at 23.5%. Open space exemption inside a previously approved Stage II area (4.113(.01)B.1.b). D.1 entry orientation and D.2 15% windows are design items with no footprint number.
4. PARKING/ACCESS: Table 5 middle housing: no minimum, no maximum. D.4 approach max 32 ft per frontage -- the ~12-13 ft lane meets it. D.3 (L3538-3541): "The combined width of all garages ... and outdoor on-site parking and maneuvering areas shall not exceed a total of 50 percent of any street frontage (other than an alley)". 50% x 85.8 = 42.9 ft. In the picture the building sits at the street, the lane runs down the west side, and the court spans about 70 ft across the rear. Read literally ("combined width", no "street-facing" qualifier) the court + lane = about 80 ft > 42.9 -> RED. Read as the model code's Figure 6 (not in the stored text, only its caption) intends -- parking visible along the street face -- only the 12-13 ft lane counts -> passes. wilsonville.yaml:1201-1219 encodes parking_area_max_frontage_pct = 50 as "caps front-yard parking", and paper.py applies it only to a side court beside the building. The stored words do not decide it; this reading governs every Wilsonville green with a rear court wider than half its frontage, so it needs a ruling (item new).
5. GEOMETRY: 85.7 x 100 rectangle; envelope 4,659 sf; pod56 width room 3.0, depth room 0.5 (FIT-TIGHT, passes; a miss would need >= 1 ft); pod80 red (-42.5). Fire route 104 ft.
6. LAND: max slope 10.8%, pad grade 0.9%, no steep, no flood, public sewer 34 ft.
7. WHO: SFR 1994, 1,706 sf, sold $655k 2022. Ordinary. Policy blank.
8. UNCHECKED: width/depth pass (85.7 vs 60, 100 vs 70); FAR none in PDR; density exempt beyond one unit per lot.
9. FLAGS: FIT-TIGHT (0.5 ft). RULE_UNVERIFIED (unsigned).

## 9. 31W22DC01400 Wilsonville PDR4, 31187 SW Willamette Way W -- CANT_TELL
1. USE: same path as lot 8: 4.124 permits quadplexes in PDR; 4.030(.01)A.4 Class I ministerial building permit (4.planning.txt:2350-2355); Site Design Review exempts middle housing; 4.140 PD permit only for parcels over 2 acres; 4.140(.10)A approved-plan control is a PD-file fact not in the store (pattern, same as every PDR lot); density exempt beyond one unit per lot (Table 1 note b, L4668).
2. LOT: Table 2 PDR-4 (L4720-4730): base min lot 3,000 sf, note B: quadplex 7,000 sf (8,298); width at building line / frontage 35/35 (63 / 69); depth 60 (lot ~116-139 ft deep east-west; the dossier's 86.5 ft "depth" is the engine's own measure). Interior lot on the curved local street Willamette Way W (east line). Street gap to the lots across 51.5-56 ft -- an ordinary local right-of-way; 4.113(.02)B.4 future-street setback needs a TSP widening that a local loop does not show (TSP not stored).
3. BUILDING: 4.113(.02)B: front 15 (measured ~15 ft from the curved line on my own zoom of the dossier drawing), side 7 two storeys (~8.5 ft north; lane side ~18 ft south), rear 20 two storeys (~47 ft); height 35 (26); coverage 75/75 (24.3%).
4. PARKING/ACCESS: Table 5 no minimum/maximum. D.4 approach 32 ft max -- a 13 ft lane. D.3 (L3538-3541) 50% of 69 ft = 34.5 ft: pod56 is depth-facing (36 ft face to the street), the lane runs along the south side of the building from the street to the court, and the court fills the rear ~49 ft x ~50 ft across nearly the whole lot width. Literal "combined width" = ~50 + 13 > 34.5 -> RED; street-face reading = 13 ft lane only -> passes. Same unresolved reading as lot 8 (item new).
5. GEOMETRY: fit slack -0.5 ft (FIT-TIGHT, inside Steph's green band; red needs a miss of 1 ft or more); pod80 red. Fire 115 ft.
6. LAND: max slope 15.8%, pad grade 2.65%, no steep, no flood, sewer 28 ft.
7. WHO: SFR 1995, 2,493 sf, $0 transfer 2024 with a real address -- ordinary house. Policy blank.
8. UNCHECKED: width/depth pass; no FAR in PDR; density exempt.
9. FLAGS: FIT-TIGHT; RULE_UNVERIFIED.

## 10. 1N131BD01100 Beaverton RMB, 1420 NW 178th Pl -- RIGHT
1. USE: Table 20.05.20.A 2.D Triplex and Quadplex P in RMB (bdc.20.05.residential.txt:474). New middle housing in RMB = Single-Detached and Middle Housing Design Review One (bdc.40.21:86-101, threshold 4), Type 1, Director, criteria = 20.05.15 site standards + 60.05.60 design STANDARDS (L110-135). By-right.
2. LOT: 20.05.15 B.2 triplex/quadplex 4,000 sf (10,426); width 20; minimum density 10 du/ac x 0.239 ac = 2.39 -> 2 (20.25.05.1.A rounding) <= 4.
3. BUILDING: front 10, rear 15, side (non-land-division) only the PUE rule (footnote 7) and building spacing 6; height 35, and 20.30.10.A RMB: 25 ft at the rear setback line rising 1:1 -> a 26 ft pod must stand 16 ft from the rear line. Lot is a corner lot on a curved street by the 135-degree test (bdc.90.definitions.txt:1412-1414) as the engine says (fronts on the west straight run and on the bulb of the same cul-de-sac); for a corner lot the applicant names front and rear (L1421-1430). With front = west, rear = the 47 ft NE line, 76 ft from the building. (Even taking the bulb as front and the south line as rear, the building at 15.6 ft would need 26 ft vs 25.6 allowed -- but the applicant's choice avoids it, so no miss.) FAR RMB quadplex 1.20 on net area (20.25.10.1.B): 0.42. No coverage limit in RMB.
4. PARKING/ACCESS: 60.30 minimum 0 for middle housing (engine margin parking 4 vs 0). 60.05.60.2 S11 (bdc.60.05:~3088-3100): parking + maneuvering width <= 50% of any street frontage; S11.a: inside a cul-de-sac, measured 20 ft from the right-of-way -- 50% of 121 ft = 60 ft, only the lane crosses that line. S13 approach <= 32 ft; S13.b.1 lowest class -- both fronts are the same local cul-de-sac. S14.a up to 8 units: 9 ft paved + 1 ft clear each side. ACCESS GEOMETRY: the dossier drawing has `lane: None` (side_street true, the bulb taken as a side street), and the court is 53+ ft from every right-of-way edge (my edges.py run) -- it touches no street. But the building is 22.9 ft from the north lot line, and that strip runs from the bulb arc at the NW corner (edges 26-34, ~34 ft of right-of-way) straight to the court; 11 ft is needed. S12 lets driveways sit 3-6 ft from property lines. Note 8.c of the 60.30 stall table (bdc.60.30.parking.txt:682-687) sets middle-housing drive aisles at 22 ft two-way / 20 ft one-way; the 22.9 ft strip holds even that. So a legal way in exists; ruling RIGHT. PATTERN: bulb lots read as corners get courts with no lane and no street contact drawn -- on a lot without such a strip this would be a false GREEN.
5. GEOMETRY: irregular 6-sided lot, envelope fits pod56 slack 31.5, pod80 slack 7.5 (both green). Fire 104 / 120 ft.
6. LAND: max slope 10.3%, pad 1.2%, no steep, no flood.
7. WHO: SFR 1977, 1,626 sf. Policy blank.
8. UNCHECKED: frontage/width (121 vs 20), coverage (none in RMB).
9. FLAGS: UTILITY-EASEMENT-ASSUMED 10 ft (= the 10 ft front setback, no extra loss).

## 11. 1S128BC02300 Beaverton RMC, 8830 SW Maverick Ter -- RIGHT
1. USE: Quadplex P in RMC (bdc.20.05.residential.txt:474); Design Review One, Type 1, Director, standards only (bdc.40.21:86-135). By-right.
2. LOT: 20.05.15 B.2 RMC triplex/quadplex 5,000 sf (8,944); width 20; minimum density 7 du/ac x 0.205 ac = 1.4 -> 1 (<= 4).
3. BUILDING: front 10, rear 15, side 5 (engine; F.2 states only townhouse/land-division sides; the building is 5.3 ft from the east line, so a 5 ft reading passes and nothing larger is printed); 20.30.10.B RMC: 25 ft at BOTH front and rear setback lines, rising 1:1 (bdc.20.25-30:140-150). Corner lot: the applicant names front and rear (bdc.90.definitions.txt:1421-1430). Front = north (Maverick Ter): building 17-21 ft from the north run and 11.5-17 ft from the corner curve -> at 11.5 ft the plane allows 26.5 ft vs 26. Rear = the south line, 56.6 ft away. (Front = west would put the rear on the east line 5.3 ft away -- the applicant would not choose that.) FAR RMC quadplex 0.90 on net area: 0.50. No coverage limit.
4. PARKING/ACCESS: no minimum (Table 60.30.10.5.A row 2 N/A). Middle-housing drive aisle 22 ft two-way (60.30.15 note 8.c). The court (45.5 x 56 ft) sits behind the building and its end faces the west street (toward SW Yearling Way) across a 13.6 ft street-side yard -- the side_street_fed plan, no lane, a short drive across the yard. S13.b.1: lowest classification; Yearling Way is a local loop, so the court is on the lower or equal street either way. S11 (bdc.60.05:~3088-3096): parking + maneuvering area <= 50% of ANY street frontage. The engine charges this only to a side court beside the building (paper.py ~L1031), not to a side-street-fed court's end. Here the court's face to the west street projects 45.9 ft. West frontage = 85.0 ft straight + the 37.8 ft corner curve shared with Maverick Ter: with half the curve, 50% = 52 ft -> passes; on the straight run alone 42.5 ft -> the DRAWN court is 3.4 ft over, but a minimum court (18.5 ft stall + 22 ft aisle = 40.5 ft, Beaverton stall table 90 degrees) fits under 42.5. A legal plan exists -> RIGHT. PATTERN: S11 not charged on side-street-fed courts (Beaverton, and any city with the 50% field); a corner lot with a short side frontage could fail it.
5. GEOMETRY: 6-sided corner lot with a rounded NW corner; pod56 slack 11 (width-facing, 56 ft along Maverick Ter); pod80 red. Fire 96 ft.
6. LAND: max slope 20.4% (spot), pad 2.9%, no steep, no flood.
7. WHO: SFR 1985, 1,507 sf. Policy blank.
8. UNCHECKED: frontage/width pass; coverage none.
9. FLAGS: UTILITY-EASEMENT-ASSUMED 10 ft (building >= 11.5 ft from street lines; no loss).

## 12. 1N131DB04200 Beaverton RMC, 955 NW 170th Dr -- RIGHT
1. USE: Quadplex P in RMC; Design Review One, Type 1 standards (bdc.20.05.residential.txt:474; bdc.40.21:86-135). By-right.
2. LOT: 5,000 sf quadplex minimum (21,198); min density 7 du/ac x 0.487 ac = 3.4 -> 3 (<= 4; 20.25.05.1.A).
3. BUILDING: front 10, rear 15, side 5; 20.30.10.B RMC plane: 25 ft at the front and rear setback lines rising 1:1. Corner lot (NW 170th Dr on the north + corner curve, a N-S street toward the NW 172nd Pl bulb on the west). Engine front = west (front_deg 87.86); building 11.1 ft from the west line -> 26.1 ft allowed vs 26 (so the engine does carry the +1 ft); rear = the east line 123 ft away. FAR 0.90 -> 0.20. No coverage.
4. PARKING/ACCESS: no minimum; aisle 22 ft (note 8.c). Court behind the building, side_street_fed off NW 170th Dr across ~38 ft of street-side yard (no lane drawn; ample ground). S11 50% of any street frontage: the court's face to 170th Dr is ~47 ft vs 50% of ~155-175 ft. S13.b.1 lowest functional classification: not looked up -- with 40 ft of room in every direction a mirror plan with the court fed off the west street (or the building turned to face north) also fits, so classification cannot turn this red.
5. GEOMETRY: 143+12 x 110/125 x 170 ft near-rectangle with a rounded NW corner; pod56 slack 77, pod80 slack 88 (both green). Fire 100 / 107 ft.
6. LAND: max slope 13.8%, pad 1.3%, no steep, no flood.
7. WHO: SFR 1980, 2,994 sf on a half-acre, $922k total value -- a large ordinary house. Policy blank.
8. UNCHECKED: frontage/width pass; coverage none.
9. FLAGS: UTILITY-EASEMENT-ASSUMED 10 ft (= front setback).

## 13. 1S116DC04100 Beaverton RMB, 13355 SW Larson St -- RIGHT
1. USE: Quadplex P in RMB; Design Review One Type 1 (bdc.20.05.residential.txt:474; bdc.40.21:86-135). By-right.
2. LOT: 4,000 sf (10,688); min density 10 du/ac x 0.245 ac = 2.45 -> 2 (<= 4). ~107 x 100 ft interior rectangle; front = south line (108.1 ft) on SW Larson St. North line: 44.5 ft on the RMC 5755 SW Erickson parcel and 61.5 ft facing nothing in flats.lots (dossier lists a 1,796 sf no-situs RMC sliver 1S116DC04701 there) -- even if that were an access strip, both buildings sit 34-64 ft from it.
3. BUILDING: front 10 (pod56 10.2 ft, pod80 10.3 ft), side 5 (5.4 / 5.7 ft), rear 15 with the RMB 20.30.10.A plane (25 ft at the rear setback line, 1:1) -> needs 16 ft for 26 ft; pod56 33.7 ft, pod80 64 ft. RMB has no front plane. FAR 1.20 -> 0.43-0.44.
4. PARKING/ACCESS: no minimum; aisle 22 (note 8.c); parking may sit in side/rear yards, at most 2 spaces in the front yard (bdc.60.30.parking.txt:606-609) -- both courts are 10.2+ ft back from the front line. pod56: side court beside the building, 50.5 ft facing Larson vs S11 cap 54 ft (the engine's side-court check applies here); a 36 x 12 ft lane drawn behind the building (not street-facing). pod80: 12 ft lane down the west side to a 92 x 50.5 ft rear court -> 12 ft street-facing. S13 one frontage, local street.
DEDICATION CHECK (KNOWN-67 kind): ST_Distance from this lot to the lots across Larson St = 29.8-30.1 ft, so the existing right-of-way is ~30 ft. Beaverton 60.55.10.5: "Dedication of right-of-way shall be determined by the decision-making authority" (bdc.60.55.transportation.txt:30); the Engineering Design Manual that states street widths is not in the store, so no width can be read. At a typical 54 ft local section the half-street take is ~12 ft: lot -> ~9,390 sf (still > 4,000); pod56 (depth room 9.5) would miss by ~2.5 ft, but pod80 has 13.5 ft of depth room and survives with ~1.5 ft to spare (a 58 ft section would leave -0.5, still inside the FIT-TIGHT green band; only a 60 ft+ section would turn it red). So the GREEN holds on the likely numbers -> RIGHT, with a pattern note: Beaverton narrow streets carry an unencoded, unstated dedication.
5. GEOMETRY: pod56 slack 9.5, pod80 slack 13.5. Fire 101 / 92 ft.
6. LAND: max slope 8.2%, pad ~2%, no steep, no flood.
7. WHO: SFR 1945, 800 sf, $67,730 building value -- small old house, ordinary. Policy blank.
8. UNCHECKED: frontage/width pass; coverage none.
9. FLAGS: UTILITY-EASEMENT-ASSUMED 10 ft (= front setback).
