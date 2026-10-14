# B4 notes -- false-GREEN sample round 2 (run 74)

Reader B4. Lots: 2 Durham SDR, 1 King City R-9, 2 Sherwood LDR, 8 Tigard (RES-B x5, RES-C, RES-D, RES-E).

## Tigard groundwork (applies to every Tigard lot)

- The pod is a ROWHOUSE development in Tigard: 18.30 "Quad" = two units on a first story over two on a second (tdc.18.30.definitions.txt:1028-1029), so four side-by-side two-storey units are "Rowhouse" (L1031-1033). Table 18.110.3 (tdc.18.110.residential-zones.txt:208,215): Rowhouses L[2] in RES-A/B/C ("up to 5 units per grouping allowed"), Y in RES-D/E. Residential Use = A in all RES zones (L76). Compliance = clear and objective standards 18.280.040 (tdc.18.280.rowhouses.txt:55) -> by right; no site development review for rowhouses (only nonresidential / mixed use, plan districts).
- Table 18.280.1 (tdc.18.280.rowhouses.txt:73-85): RES-A/B front 20 min / 20 max, street side 20/20, side 5 (0 at common wall), rear 25 (0 on alley); RES-C/D front 15 min / 20 max, side 5, rear 15; RES-E front 15/20, street side 10/20, rear 15; height 35 (RES-A-D), 45 (RES-E); coverage 80%, landscape 20%.
- Parking: no minimum, no maximum for rowhouses (18.410 Table 18.410.3 Residential -> housing-type chapter; 18.280 states none). Parking areas >= 20 ft from street lines (18.280.040.D.2, L141). Shared access 20-24 ft paved (L123). S-3 screening of side/rear parking in RES-A-C (L161): Table 18.420.2 not stored.
- Height measured to the midpoint of the highest gable (18.40.040.A.3, tdc.18.40.measurements.txt); 35 ft cap leaves 9 ft of room over the 26 ft pod.
- Table 18.805.1 (tdc.18.805.lot-standards.txt:51-197) Rowhouse row: min lot 1,500/1,500/1,250/750/None (A-E), max 3,000/3,000/1,750/1,250/1,000; min width 25/25/20/None/20. 18.280.040.B: "Rowhouse development is not allowed on lots that do not meet the dimensional lot standards for the base zone" (L67). 18.40.130.B: rowhouse min and max density "determined by the minimum and maximum lot sizes" (measurements L300). Read per dwelling, a 4-rowhouse lot needs 4 x min; the per-dwelling MAXIMUM makes a min-density floor (floor(area / max)); encoding does not hold it (Steph ruling 2026-10-01, split lots). Min density is a sev-2 flag by Steph 2026-10-02 (flags.yaml DENSITY-MIN) so it never turns a lot yellow/red: noted per lot, not a WRONG.
- 18.840 sublot plat (Type II-Modified, clear and objective criteria 18.840.050) keeps the parent lot as "a single lot" for lot standards (L77-89), so 25 ft min width / frontage read on the parent lot.
- 18.920.030.I.2/3 (tdc.18.920.access.txt): driveway >= 150 ft from a collector/arterial intersection; spacing 200 ft on collectors, 600 ft on arterials. Not encoded. Checked per lot where a collector/arterial is near.
- 18.920.030.J.4: access drives > 150 ft need a fire turnaround.
- WSRC plan district (18.670) exempts RES-B and holds no RES-C/D/E zones; River Terrace (18.640) is west Tigard only.

## 2S103CA02100 -- Tigard RES-B, 11840 SW James Ct (RIGHT)
1. USE: Residential Use A (tdc.18.110.residential-zones.txt:76); Rowhouses L[2] "up to 5 units per grouping" (L208,215): pod = 4 -> allowed by right (clear and objective 18.280.040). Zone RES-B, zone_frac 1.0, no split. Not in WSRC (RES-B exempt anyway, tdc.18.670.wsrc.txt:63) or River Terrace.
2. LOT: 15,276 sf, frontage 90.2 ft (cul-de-sac bulb + straight run; 18.805.030.C.2 20 ft on a curve). Min 4 x 1,500 = 6,000 pass. Max lot 3,000/rowhouse -> floor(15,276/3,000)=5 > 4 = a min-density shortfall (sev-2 flag kind; not held in Tigard by the 2026-10-01 ruling) -- not colour-changing.
3. BUILDING: Table 18.280.1 RES-B: front 20 min / 20 MAX, side 5, rear 25, height 35 (pod 26), coverage 80% (pod 30.5%), landscape 20% (69%). Drawn building's nearest point is 22.5 ft from the front line -- 2.5 ft past the 20 ft max (tdc.18.280.rowhouses.txt:80-81). The screen does not check a max front setback (flats/ingest/flatter.py _max_front_ft only uses it for re-placement). Fit room depth 5.5 ft -> the pod can slide 2.5 ft forward; not a lot-level miss.
4. PARKING/ACCESS: no min/max stalls (Table 18.410.3 Residential -> housing chapter). Court 58.5 ft from street line (>= 20, L141). Lane 20 ft (shared access 20-24, L123). Court 5.4 / 6.2 ft from the two rear neighbours -- S-3 screening (L161) width not stored (Table 18.420.2), a doubt only. Local cul-de-sac: no 18.920.030.I collector spacing issue. Hose 119.9 ft <= 150.
5. GEOMETRY: zoomed plot: pentagon lot, front on the James Ct bulb (NE), pod parallel to the straight front run, court behind/beside toward SW. Not a corner/through/flag.
6. LAND: slope mean 5.7%, p85 9.5%, 485 sf steep not blocking, pad grade 1.7%. No flood.
7. WHO: SFR 1970 house, 1,792 sf, $559k. Ordinary house.
8. UNCHECKED: min_lot_width (25 ft: lot ~100 ft wide, pass), depth/ratio (none stated), coverage_pct/far/stories (none stated beyond 80% coverage, checked as impervious), min density (above).
9. FLAGS: none current (table JURISDICTION-OFF is stale run-70).

## 2S103CB02200 -- Tigard RES-B, 12170 SW James St (RIGHT)
1. USE: as Tigard groundwork; RES-B, zone_frac 1.0.
2. LOT: 20,010 sf rectangle ~100 x 200; frontage 100 ft. Min 6,000 pass. Min-density floor(20,010/3,000)=6 > 4 (sev-2 kind, not held) -- noted only.
3. BUILDING: building 18.6-20.5 ft from the front line (at the 20 ft min/max line within the ROW-polygon tolerance), sides 5.6 ft, rear far. Coverage 23%, landscape 77%. Height 26/35.
4. PARKING/ACCESS: court 54-56 ft from the street (>= 20). Lane 20 ft beside the building. Court 5.1 ft from both side lines: S-3 screen width not stored (doubt only). Local street. Hose 111.5 ft.
5. GEOMETRY: plain interior rectangle, pod front-right, lane left, court behind. Fits plainly.
6. LAND: mean slope 4.1%, pad 1.1%, no steep in pad, no flood.
7. WHO: SFR 1955, 1,104 sf, ordinary house.
8. UNCHECKED: width 25 (lot 100, pass); nothing else stated that this pod fails.
9. FLAGS: none current.

## 2S103AD00104 -- Tigard RES-B, 10540 SW Errol St (RIGHT)
1. USE: rowhouses by right in RES-B (groundwork). zone_frac 1.0.
2. LOT: 14,992 sf, ~100 x 150 rectangle, frontage 100. Min 6,000 pass; floor(14,992/3,000)=4 -> no density shortfall either way.
3. BUILDING: building 20.5 ft from the front (ROW tolerance), side 6.4, rear well clear; coverage 31%, landscape 69%; height 26/35.
4. PARKING/ACCESS: court 56.5 ft from street, 5.1 ft from the east side line (S-3 doubt only). Local street. Hose 107 ft.
5. GEOMETRY: plain interior rectangle; front on Errol St to the north. Fits plainly.
6. LAND: mean 4.8%, pad 0.45%, no steep, no flood.
7. WHO: SFR 1963, 3,639 sf, sold 2026-04 for $846,500. A large ordinary house.
8. UNCHECKED: width 25 (100, pass). Nothing else.
9. FLAGS: none current.

## 1S134DD00400 -- Tigard RES-B, 10805 SW Tigard St (RIGHT)
1. USE: rowhouses by right (groundwork). zone_frac 1.0. PR parcels across the street (trail corridor) -- not this lot.
2. LOT: 18,106 sf, ~125 x 145 (side lines in two segments 115 + 30). Min 6,000 pass. floor(18,106/3,000)=6 > 4 -> min-density shortfall (sev-2 kind, not held) noted only.
3. BUILDING: building 20.0 ft from the front line (min = max = 20, met exactly), sides 33-35 ft (pod56) ; coverage 26%, landscape 74%, height 26/35. pod80x25 also green but only 1.5 ft of depth room.
4. PARKING/ACCESS: court 56 ft from street; 13.3 ft from the east line. SW Tigard St = FClass2 5 "Neighborhood Route" on the WashCo TSP layer (queried gispub.co.washington.or.us TSP_Layers/4 within 300 ft of the frontage) -> 18.920.030.I.2/3 (collector/arterial) do not apply. 18.210.030.A.1 (tdc.18.210.residential-general.txt:51): setbacks from the ULTIMATE TSP right-of-way -- not encoded; current ROW 50 ft (front line to lot across); even a 64 ft ultimate ROW moves the line 7 ft < pod56's 13.5 ft depth room. Hose 110.7 ft.
5. GEOMETRY: interior near-rectangle, front south; small carve notch at the rear-left of the envelope (steep patch, 976 sf, not blocking). Fits.
6. LAND: mean 6%, p85 10.7%, pad 2.7%. No flood.
7. WHO: SFR 1964, 1,925 sf, ordinary.
8. UNCHECKED: width 25 (125, pass).
9. FLAGS: none current.

## 1S134CD02600 -- Tigard RES-B, 11850 SW Katherine St (RIGHT)
1. USE: rowhouses by right (groundwork). zone_frac 1.0.
2. LOT: 10,752 sf, trapezoid 90 front / 100 rear / 110-116 deep. Min 6,000 pass; density band floor(10,752/3,000)=3 to floor(10,752/1,500)=7 -> 4 inside it.
3. BUILDING: building 20.4 ft from the front (20 min/max), 5.1 ft from the east side, 30.8 from the west; envelope rear 25 ft kept by the building. Coverage 43%, landscape 57%, height 26/35.
4. PARKING/ACCESS: the court runs into the 25 ft rear yard (8.4 ft from the rear line): Table 18.280.1 setbacks are for the building; the only parking-area distance stated is 20 ft from STREET lines (L141) -> OK. S-3 screening doubt only. Katherine St local (50 ft ROW). Hose 106.8 ft.
5. GEOMETRY: interior trapezoid, front north. Fits.
6. LAND: flat (mean 2.1%). No flood.
7. WHO: SFR 1967, 1,300 sf.
8. UNCHECKED: width 25 (90, pass).
9. FLAGS: none current.

## 2S112BB03800 -- Tigard RES-C, 14300 SW Hall Blvd (RIGHT, with a driveway note)
1. USE: Rowhouses L[2] in RES-C (<= 5 per grouping) -> 4 by right. zone_frac 0.9999.
2. LOT: 16,527 sf, trapezoid, 151 ft on Hall Blvd (west), 105 rear. RES-C rowhouse min 1,250 x 4 = 5,000 pass (tdc.18.805.lot-standards.txt:96). Max 1,750/rowhouse -> floor(16,527/1,750)=9 > 4 = min-density shortfall (sev-2 kind, not held) noted only.
3. BUILDING: Table 18.280.1 RES-C: front 15 min / 20 max, side 5, rear 15, height 35 (tdc.18.280.rowhouses.txt:76-83). Building 15.2 ft from the front line. Coverage 28%, landscape 72%.
4. PARKING/ACCESS: SW Hall Blvd = FClass2 3 "Arterial" on the WashCo TSP layer (queried within 150 ft of the frontage). 18.920.030.I.3: "The minimum spacing of driveways and streets along an arterial is 600 feet" -- the neighbours at 14250/14270/14358/14370 SW Hall Blvd front the same arterial within ~150 ft, so a new pod drive on Hall fails spacing; not encoded (tigard.yaml refusal says "nothing measures street class"). NOT a false GREEN: Tigard requires zero rowhouse parking (Table 18.410.3 -> 18.280, no minimum), and the standing ruling says zero-required zones need no stalls, so the pod stands with no drive; hose route 111.5 ft from the street does not need the drive. 18.210.030.A.1 ultimate ROW: current ~78 ft (front line to the lot across); a 98-100 ft arterial would push the line ~10 ft, inside pod56's 17.5 ft (pod80's 28 ft) depth room.
5. GEOMETRY: lot fronts Hall on its long west side; building along the front, lane south of it, court behind. Fits.
6. LAND: mean 3%, pad 2.4%, no steep, no flood. Frequent transit 35 ft.
7. WHO: SFR 1940, 1,116 sf, ordinary.
8. UNCHECKED: width 20 (pass). Nothing else.
9. FLAGS: none current. (If Tigard ever counts the court as part of the plan, Hall Blvd spacing would need a flag: a pattern for every Tigard lot whose only street is a collector/arterial.)

## 2S111BB01503 -- Tigard RES-D, 10330 SW McDonald St (RIGHT, two notes)
1. USE: Rowhouses Y in RES-D (tdc.18.110.residential-zones.txt:208), no grouping cap. zone_frac 1.0.
2. LOT: 9,481 sf, ~90 x 105 corner lot (McDonald St north, SW 103rd Ave east). RES-D rowhouse min 750 x 4 = 3,000 pass; max 1,250 -> floor(9,481/1,250)=7 > 4 min-density shortfall (sev-2 kind) noted only.
3. BUILDING: front = shorter street line = McDonald (90 ft) (tdc.18.30.definitions.txt:1244-1245). RES-D front 15 min / 20 max, street side 15 / 20, side 5, rear 15 (tdc.18.280.rowhouses.txt:76-82). Building 15.5 ft from McDonald, ~15.5 from 103rd -> inside both min/max bands. Coverage 39%, landscape 61%.
4. PARKING/ACCESS: court (no lane; abuts the 103rd Ave yard) is 15.3 ft from the 103rd Ave street line -- 18.280.040.D.2 asks 20 ft from ANY street property line (tdc.18.280.rowhouses.txt:141). The screen did not hold the court to it on the side street (encoded parking_street_setback_ft 20; no margin reported). Lot is ~90 ft wide, court 56 ft and 18 ft from the west line -> shifting it 4.7 ft west complies; not a lot-level miss. Driveway on 103rd < 150 ft from the McDonald (arterial) intersection (18.920.030.I.2) but the same sentence gives the relief "placed as far from the intersection as possible" for < 150 ft frontage. McDonald = FClass2 3 Arterial on the WashCo TSP layer, current ROW 44.9 ft (lot line to lot across); 18.210.030.A.1 measures setbacks from the ULTIMATE TSP ROW -- the TSP width is not stored; a 75-80 ft arterial moves the front line ~16 ft, more than pod56's 10 ft depth room WITH the court, but Tigard requires zero rowhouse parking (standing ruling: none needed) and building alone needs 15 + 36 + 15 = 66 ft of the ~88 ft left. Hose 85 ft.
5. GEOMETRY: corner lot, correctly read as corner (two real streets meeting at ~90 degrees). Building faces McDonald; entrance may face either street (L209).
6. LAND: flat (mean 2.8%), no flood.
7. WHO: SFR 1968, 1,676 sf.
8. UNCHECKED: width 20? RES-D None. Nothing fails.
9. FLAGS: none current. PATTERN NOTE: (a) the court-to-side-street 20 ft rule looks unchecked on Tigard corner lots; (b) Tigard's ultimate-ROW setback rule (18.210.030.A.1) is not encoded -- a Tigard cousin of KNOWN-67, harmless here only because Tigard needs no parking.

## 2S101DB00800 -- Tigard RES-E, 13333 SW 72nd Ave (RIGHT; POLICY: apartment complex)
1. USE: Rowhouses Y in RES-E, apartments Y (tdc.18.110.residential-zones.txt:203,208); Quads N in RES-E (L207) -- the pod is a rowhouse, so fine. No grouping cap in RES-E (tdc.18.280.rowhouses.txt:63). zone_frac 0.9997.
2. LOT: 97,949 sf (635 x ~150-183 ft). RES-E rowhouse min lot "None" (unchecked min_lot_area is right). Max 1,000/rowhouse -> min-density floor 97 units (sev-2 kind, not held) noted only.
3. BUILDING: RES-E front 15/20, street side 10/20, side 5, rear 15, height 45. Building 15.5 ft from 72nd Ave, 10.4 ft from the south line (the screen reads a corner: south line taken as a street side, 10 ft -- conservative). Coverage 3.6%.
4. PARKING/ACCESS: 72nd Ave = FClass2 3 Arterial (WashCo TSP layer). 18.920.030.I.3 600 ft arterial spacing cannot be met by any new drive, but zero rowhouse parking is required; the drawn court is reached across the south line (probably the complex's internal drive, not a street) -- a lane from 72nd also fits easily in 183 ft. Hose 121 ft. Ultimate ROW: current ~72 ft; 40 ft room absorbs any widening.
5. GEOMETRY: long rectangle, street only at the east end; observed corner_lot=true is probably the internal drive along the south line counted as a private street (frontage_ft 810 = 183 + 627). Harmless (stricter yard).
6. LAND: mean 5.3%, pod80 pad 4.55%; pod56 is YELLOW (CLOSER_LOOK_SLOPE 7.49%). No flood.
7. WHO: prop 701 MFR, land $1.3M, building $12.97M -- an occupied apartment complex; 2S101DB00801 (13325 SW 72nd, 105,774 sf) carries the same building value -> one complex on two tax lots. POLICY (Steph 2026-10-14): stays green.
8. UNCHECKED: nothing stated that fails.
9. FLAGS: pod56 SLOPE-GRADE (yellow) only.

## 2S113CD02000 -- Durham SDR, 7955 SW Peters Rd (RIGHT)
1. USE: SDR "Uses permitted outright ... 2.8.1.6 Middle housing" (ddc.2.zoning-districts.txt:67,81; Table 2.18 at :318). "Middle Housing" = Duplexes, Triplexes, Quadplexes, Cottage Clusters, Townhouses (ddc.12:93); "Quadplex means four attached dwelling units on a lot" (ddc.12:116) -- the pod on one lot is a Quadplex (Townhouse = each unit on its own lot, ddc.12:176; 7.12 Type I applies only then). Outright use "requires only ministerial review" (ddc.2:23-26). Major-modification review exempts middle housing (ddc.10:125). By-right. No overlay, no split zone.
2. LOT: 43,557 sf vs min 10,000 (ddc.3:6-7); frontage 185 vs 20 (3.1.5). No width/depth number exists for SDR (grep). Density: "minimum base density for the SDR district shall be 10,000 square feet per dwelling" (ddc.3:5-6) -> 4.356 du/ac floor; 4 units on 1.0 ac = 4.0 du/ac -> DENSITY-MIN flag [4.0, 4.356], severity 2 (Steph ruling) -> colour unchanged. Read as a floor (literal "minimum"); if it were read as a cap, 43,557/10,000 = 4.36 still allows 4.
3. BUILDING: front 20 from ROW edge, side 10, rear 15 attached (ddc.3:15-18); drawn building 20.1 ft from Peters Rd line, 15 ft from east neighbour 2S113CD01900. Height 35 above average grade (3.1.4) vs 26. Open space 5% gross for multi-unit (3.1.8.1) vs 87%. No coverage / FAR / stories numbers in SDR (grep).
4. PARKING: Middle housing 1/unit min, no max (ddc.3:436) -> 4 charged. Access: Table 3.7.1.8 SDR "Driveway 10-30 feet wide"; if 3.7.1.4.2 (3-49 units, 30 ft two-way + 5 ft sidewalk) were applied, 132 ft slack absorbs it. Apron >= 100 ft from intersection (3.7.1.7): no intersection near this frontage. Bike parking (3.7.6) trivial. Hose 122 ft.
5. GEOMETRY: rectangle ~185 x 235 ft, one street (Peters Rd, south); building at the street, court behind; plain fit.
6. LAND: slope max 17.8%, p85 5%; no flood; no overlay. Tree mitigation 35% canopy on removal (ddc.5:242-247) fits on this lot.
7. WHO: SFR 1959, 2,074 sf, prop 101 -- ordinary house.
8. UNCHECKED: lot width/depth, coverage, FAR, stories -- Durham SDR states none. density_du_per_acre: max density stated only for townhouses (18 du/ac, 7.12) and MDR; none fails.
9. FLAGS: DENSITY-MIN only (sev 2).

## 2S113CD02200 -- Durham SDR, 7878 SW Peters Rd (RIGHT)
1. USE: same as 2S113CD02000 (SDR middle housing outright, ministerial; ddc.2:81, :23-26; Quadplex ddc.12:116).
2. LOT: 37,566 sf vs 10,000; frontage 160 vs 20. Density: 4 units / 0.862 ac = 4.64 du/ac >= 4.356 floor (ddc.3:5-6) -> no flag. Note: "minimum base density ... 10,000 square feet per dwelling" is read as a FLOOR (literal word "minimum"; definitions literal). Had it been a cap, 37,566/10,000 = 3.76 -> 3 units, but the words say minimum, and Durham states no density cap for middle housing in SDR (only townhouses 18 du/ac, 7.12; MDR 16 du/ac, 3.1.2). Not a finding.
3. BUILDING: front 20/side 10/rear 15 (ddc.3:15-18): building drawn 20.5 ft from the Peters Rd line and 10.5 ft (80x25: 10.1) from the west neighbour 2S113CD02100 -- side 10 met. Height 26 vs 35. Open space 85% vs 5%.
4. PARKING: 4 stalls vs 1/unit min. Lane on the west side; apron ~150+ ft from the Peters Rd / Upper Boones Ferry Rd corner to the east (3.7.1.7 needs 100). Hose 108 ft.
5. GEOMETRY: rectangle ~160 x 235 ft, Peters Rd on the north only; rear abuts MG land (18183 SW Boones Ferry). Plain fit, slack 131 ft.
6. LAND: slope max 11%, no flood, no overlay.
7. WHO: SFR 1973, 2,537 sf, prop 101 -- ordinary house.
8. UNCHECKED: as above; Durham SDR holds no width/depth/coverage/FAR/stories numbers.
9. FLAGS: none.

## 2S116AA14200 -- King City "R-9 (WC)" county pocket, 12594 SW Bexley Ln (WRONG, RED)
0. ZONE: map code "R-9 (WC)" = Washington County R-9 kept on annexed land: KCMC 16.80.050 A "Zoning regulations applicable to an area prior to annexation to the city shall continue to apply and shall be enforced by the city until a zone change" (kcc.16.80.general.txt:84-99). The layer screens it as a pocket under the county's R-9 (king-city.yaml zone_rulings "R-9 (WC)"). Agreed.
1. USE: CDC 304-2.14 Middle Housing Type I on an existing subdivision lot <= 10,000 sf buildable (7,210 sf) "C. ... when on a public street: (1) Along the entire site frontage, existing right-of-way width meets the required minimum below, or the applicant proposes to dedicate right-of-way ...: (a) Local street: 25 feet to centerline" (cdc.304.r-9.txt:92-108). If the ROW is not met and not dedicated -> 304-3.20 B Type II exemption (cdc.304.r-9.txt:185-194). Type I path = dedicate.
2. LOT: 7,210 sf vs Quadplex 7,000 (304-7.1 A(3), measured before dedication) OK; density not a consideration (304-6.1 A); frontage no minimum.
3. BUILDING: 304-7.1 B: front 12 to the front wall, garage entrance 20, street side 8, non-street side 5 where abutting offsite land, rear 15; "Yards shall be measured from the property line, sidewalk, or easement for public travel, whichever is closest". Height 35 vs 26. 418-2 future-ROW setback does NOT apply to Middle Housing (cdc.418-419:34-35).
5. GEOMETRY (decisive): corner lot, Bexley Ln on the north (front, address street), a short N-S connector street on the west (side street; the court opens onto it, side_street true). Lot width E-W is 70.0 ft at every y from 641460 to 641540 (kc.py). Pod56x36 placed width-facing Bexley: 8.5 ft from the west line + 56.1 + 5.5 ft from the east line; envelope 57.1 wide -> slack 1.0 ft (fit_ft [69,68,1], room width 0.5). Rotating fails (36 + 47 court = 83 > 70); pod80x25 red (-36).
   ROW widths from the gap to the lots across: west connector 46.0 ft along the whole frontage (to 2S116AA14100, 12616 SW Bexley Ln) -> half-width 23.0 -> 2.0 ft short of 25; north Bexley Ln 42.0 ft -> half 21 -> 4 ft short (building sits 19 ft back from the north line, front min 12 -> 16 after dedication, so the north is not binding).
   West dedication 2.0 ft -> street-side yard measured from the new line -> 10 + 56 + 5 = 71 ft needed vs 70.0 -> 1.0 ft miss = RED (Steph: fit miss of exactly 1 ft is red). Any ROW narrower than 48 ft gives >= 1 ft miss.
   City twin: KCMC 16.80.060 A(1) "Where a yard or setback abuts a street having insufficient right-of-way width, the minimum yard or setback requirement shall be increased by the amount of right-of-way, measured from the street centerline, necessary to meet applicable city, county, or state standards" ... (2)(g) "All other city streets--Twenty-five feet" (kcc.16.80.general.txt:105-129). No exception for built improvements, no middle-housing exemption; king-city.yaml:395-401 records it as NOT ENCODED. Same 2 ft result.
   Caveat: 304-2.14 C(1) also says "If road improvements built to ultimate County standard exist, no additional right-of-way is required" -- unknown here, but 16.80.060 A has no such escape.
4. PARKING: 4 stalls in a rear court off the side street (corner rule followed); stalls required 0 per the screen. Hose 81 ft.
6. LAND: slope max 15.6%, p85 9.5%; no flood.
7. WHO: SFR 1992, 1,461 sf, prop 101 -- ordinary house.
8. UNCHECKED: frontage/width/depth (county states none for plexes), coverage/FAR (none in R-9 middle housing).
9. FLAGS: none.

## Sherwood groundwork (both LDR lots)
- USE: 16.12.020 A table "Triplex and Quadplex P P P P P" (VLDR LDR MDRL MDRH HDR) (sdc.16.12.residential.txt:108-112). Design: 16.14.010 B.1 "If all applicable standards ... are met, Residential Design Checklist review" (clear and objective; :21-26) -> by-right. 16.14.030 A driveway approach: <= 12 ft per dwelling, total <= 50% of frontage, shared driveways required (ord.2022-004.16.14.030.txt:1-20).
- LOT (LDR column = 3rd value): Quadplex 7,000 sf (ord.2022-004.16.12.030-c.txt:8; sdc.16.12:138); lot width 25 at the front line, 60 at the building line, depth 80 (sdc.16.12:178-194); max density not applied to quadplexes (16.12.010 F.1, :91).
- BUILDING: front 20, garage 20, interior side 5 (no adjustment/variance, note 6), corner street side 20, rear 20 (sdc.16.12:253-297); height 30 ft or 2 stories, lesser (:195-235, note 3). Infill 16.68.030: FAR 0.5 in LDR and a side plane of +1/2 ft per ft over 24 for dwellings over 24 ft (sdc.16.68.infill.txt:74-95) -- the layer holds both (stricter reading).
- PARKING: Quadplex on >= 7,000 sf: 4 spaces total (sdc.16.94.parking.txt ~L490-565). Neighbourhood-route driveway spacing does not apply to middle housing on recorded subdivision lots (sdc.16.106:436-445).
- RIGHT-OF-WAY (the finding): 16.106.020 A "all developments containing or abutting an existing or proposed street, that is either unimproved or substandard in right-of-way width or improvement, shall dedicate the necessary right-of-way prior to the issuance of building permits" (sdc.16.106.transportation.txt:119-125). "Development" = any man-made change (sdc.16.10.definitions.txt:161). 16.106.040 D "Additional setbacks apply when the width of a street right-of-way abutting a development is less than the standard width ... Additional setbacks shall be measured at right angles from the centerline of the street. ... 4. Neighborhood Route 32 feet" (sdc.16.106:281-292). No middle-housing exemption in 16.106 (grep: only the driveway-spacing exemption at :438 and :466). Local streets carry no additional setback. sherwood.yaml:518-521 records 16.106 as NOT ENCODED ("A doubt").
- Street class: Washington County TSP Functional Classification layer (gispub LUT_PDS/TSP_Layers/MapServer/4) returns "Neighborhood Route" (FClass2 5) for the segments in front of both lots (OBJECTID 43616 Highpoint, 43618 Division). Sherwood's own Figure 17 is not stored and its PDF map is image-only; the county layer is the best source I could reach. If either street were a LOCAL street instead: no additional setback; Highpoint would be fine (52 ft would mean 0.25 ft), and on Division the pod80x25 would still fit -- so both rulings rest on the NR class.

## 2S132CD12600 -- Sherwood LDR, 15630 SW Highpoint Dr (WRONG, RED)
1. USE: quadplex P, design checklist, by-right.
2. LOT: 10,711 sf vs 7,000; ~104 ft wide x 103 deep (zoom picture edges 104/103) vs width 60 at the building line and depth 80 -- both met (unchecked by the screen but passing).
3. BUILDING: pod56x36 drawn 20 ft back from Highpoint Dr with the court behind it reaching the rear line; the fit is TIGHT: slack -0.5 ft in depth (envelope 103 - 20 - 20 = 63 vs the 63.5 ft the room needs), FIT-TIGHT flag [-1, 0]. Alone that is green with a flag under Steph's ruling (miss under 1 ft). Height 26/30, 2 stories/2, FAR 0.376/0.5.
4. PARKING: 4 stalls; one 12 ft approach (12 of 52 ft allowed). Hose 112 ft.
5. GEOMETRY: rectangle, Highpoint Dr on the north only; rear abuts EFU land (24574 SW Ladd Hill Rd, outside the UGB).
   ROW: gap to 15607 SW Highpoint Dr across the street = 51.5 ft (ray 45.7 -> 97.2) -> half-width 25.75. Neighborhood Route (county TSP) -> 32 ft from centreline -> dedication of 6.25 ft along the frontage; front yard then measured from the new line -> envelope depth 56.75 vs 63.5 needed -> about 6.75 ft miss = RED. pod80x25 already red (-35.5).
6. LAND: slope max 32% but p85 5%; no flood.
7. WHO: SFR 1996, prop 101.
8. UNCHECKED: min width/depth pass; coverage none in LDR.
9. FLAGS: FIT-TIGHT only.

## 2S132AC01500 -- Sherwood LDR, 15069 SW Division St (WRONG, RED)
1. USE: quadplex P, by-right.
2. LOT: 22,362 sf; ~150 x 149 ft -> width 60 and depth 80 met.
3. BUILDING: both pods green. The envelope is carved by steep ground (steep_sqft 7,858; slope p85 31%, max 92%): a front pocket from 20 ft off Division St up to about y=623671-623682 and a separate strip at the north. pod56x36 sits on the front setback line with the court beside it (east) and a 12 ft lane behind; room: depth 4.5, width 16.5, both 3.0. pod80x25 room: depth 10.5, width 0.5 (FIT-TIGHT [0,1]). Height 26/30, FAR 0.18.
4. PARKING: 4-5 stalls; one 12 ft approach (12 of 75 allowed); hose 110 ft.
5. GEOMETRY: interior lot, Division St on the south. ROW: two strips, 2S132AC ROW 20.3 ft (lot side) + 2S132DB ROW 20.7 ft = 41.0 ft (rays at six x values: 37.3->57.6->78.3 etc.). NR -> 32 ft from centreline -> 32 - 20.3 = 11.7 ft dedication (11.5 using half the gap). Front yard moves ~11.7 ft north: pod56x36 has 4.5 ft before steep ground -> ~7 ft miss; pod80x25 has 10.5 ft -> ~1.0-1.2 ft miss -> RED either way (fit miss >= 1 ft).
6. LAND: steep ground behind the pocket is what makes the dedication fatal.
7. WHO: SFR 1952, 3,438 sf, prop 101.
8. UNCHECKED: width/depth pass.
9. FLAGS: FIT-TIGHT on pod80x25.
