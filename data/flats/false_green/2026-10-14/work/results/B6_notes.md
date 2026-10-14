# B6 notes (false-GREEN round 2)

Reader B6: Estacada, Gladstone, Happy Valley, unincorporated Clackamas.

## 34E20DA01800 -- Estacada C-2, 585 NW Zobrist St -- RIGHT
1. USE: C-2 16.32.020 lists "6 Fourplex" and "7 Commonwall dwellings" outright (emc.16.zones.txt:1572-1574). "Fourplex means a single building on its own lot with four dwelling units" (emc.16.08.txt:136); multi-family = 5+ units (:148) and is the only conditional residential use (zones :1611). No design review outside the Downtown zone (design review text only at zones :1123-1147, D zone). 16.132 is procedure only. By-right.
2. LOT: min lot "Duplex, triplex or fourplex 2,500 square feet per dwelling unit" (zones :1638) -> 10,000; lot 11,118. No width/depth/frontage minimum printed in 16.32.040. Min density (16.60.070, emc.16.60.txt:103) reaches only subdivisions and multi-family -> not a fourplex. Max density only for multi-family (zones :1646).
3. BUILDING: front 15 (zones :1652); corner lot: "all sides of a lot adjacent to a street ... shall be considered frontage" (emc.16.08.txt:244) -> both street yards 15; front lot line on a corner = "the shortest property line along a street" (:250): north line 100.4 ft vs east 106.8 ft -> north is front; rear on a corner = side yard 5 (zones :1668), screen used 15 (stricter). Side 5. Measured from the drawing: building 15.2 ft from the north line, ~19 ft from the east line, envelope 5 ft off west. Height 45 (zones :1686) vs 26. Landscaping 5% (:1688) margin 61 pts. Clear vision triangle 15 ft legs (emc.16.08.txt:94) inside the 15 ft yards.
4. PARKING: 16.25/16.32 point to 16.76: "Triplex and Fourplex 1.5 for each dwelling unit, rounded up" (emc.16.76.txt:77-78) = 6 stalls. The screen charged 4 (state Large-City cap, see pattern note below), but the court seats 8, so 6 fit. Groups of more than four: no backing into the street, curb 4.5 ft from line (emc.16.76.txt:37) -- court is 15+ ft inside the lines. Max = 6 x 1.2 = 7 (fine).
5. GEOMETRY: near-square corner lot (NW 6th Ave north, NW Zobrist St east). Building at the north, court behind it to the south; no lane drawn, court edge ~20 ft from the Zobrist line (driveway across the yard, >50 ft from the corner). Fits plainly.
6. LAND: slope max 3%; no flood; no overlay.
7. WHO: prop 201 COM, building $705,100, built 2002, sold $984k 2014 -> existing commercial building (POLICY).
8. UNCHECKED: frontage/width/depth/coverage/FAR/stories/density -- C-2 prints none of these for a fourplex (zones :1631-1696, read whole).
9. FLAGS: ZONE-MISSING (run-70 table, stale; Estacada joined in run 73). Current checks: none.

## 34E20DD00201 -- Estacada C-2, 239 NE Main St -- RIGHT
1. USE: as 34E20DA01800 (fourplex outright, zones :1572; no design review in C-2).
2. LOT: 11,000 sf vs 10,000 (zones :1638). No width/depth minimum in C-2.
3. BUILDING: front 15, side 5, rear 15 (zones :1652, :1654, :1664); height 45 (:1686). 
4. PARKING: 6 required (emc.16.76.txt:77-78); court seats 8 (pod80x25) / 7 (pod56x36). Charged 4 (state Large-City cap -- see pattern note).
5. GEOMETRY: 100 ft (E-W) x 110 ft (N-S) interior lot. Addresses (209/239/255/271 NE Main, parallel to 196-296 N Broadway) put NE Main St on the EAST 110 ft side; lots 255 and 209 NE Main are north and south; an ~18-20 ft unparcelled gap separates the west line from the N Broadway lots (an alley or unopened strip; abuts_alley=false). Drawing check: pod80x25 building runs 80 ft along the east side, ~15 ft from Main, court behind it to the west, ~20 ft clear strip on the south side for the drive -> sensible and fits. The pod56x36 drawing is odd: front_deg is None and its lane starts at the NORTH envelope edge, 5 ft from the 255 NE Main lot line, i.e. the drawn lane reaches no street. Not decisive here (pod80x25 is green with a sensible layout, and a 56x36 facing Main with a 49 ft court behind also fits: 15+36+18+24=93 < 100 ft), but worth a look: a lot with front_deg None may get a lane drawn to a side yard. 
6. LAND: slope max 2.7%; no flood/overlay.
7. WHO: prop 101 SFR, 1924 house, 1,304 sf -- an ordinary house; no policy note.
8. UNCHECKED: C-2 prints no width/depth/coverage/FAR/stories for a fourplex (zones :1631-1696).
9. FLAGS: ZONE-MISSING stale (run 70). Current: none.

## 34E17D 00700 -- Estacada NCR, 29760 SE Eagle Creek Rd -- RIGHT (parking note)
1. USE: 16.25.020 "7 Triplex, fourplex, or commonwall dwelling with three or more dwelling units within 200 feet of Eagle Creek Rd, Hinman Rd, or a street with a major collector classification" (emc.16.zones.txt:762) -- outright. Building drawn 15-70 ft from the Eagle Creek Rd line (west 60 ft end; addresses 29736/29740/29788/29780 Eagle Creek Rd around it confirm the road is at the west end). No design review in NCR.
2. LOT: 2,500 sf a dwelling (zones :827) -> 10,000; lot 24,764 (60 ft x ~413 ft strip). No width minimum printed. Min density 16.60.070 reaches subdivisions/multi-family only.
3. BUILDING: front 15 (zones :840), side 5 (:842), rear 15 (:852), "no minimum setback distance is required from Eagle Creek Rd" (:860). Measured: building 5.5 ft from the north line, ~15 ft from Eagle Creek Rd. Height 35 ft (:876) vs 26. Second-storey bedroom window over 15 ft above grade -> side yard = sill/3 (:846): with a 12 ft ground storey the sill sits ~14.5-15 ft, so 5 ft holds; sprinklers are the code's own alternative. Rider only.
4. PARKING: "The number of parking spaces as required in EMC 16.76 shall apply in the NCR zone" (zones :870) -> fourplex 1.5/unit rounded up = 6 (emc.16.76.txt:77-78). Screen charged 4: margins parking_stalls [4,4] -- the _state.yaml OAR 660-046-0220(2)(e)(B) Large-City cap (4 total on a 7,000+ sf lot). Estacada is outside Metro and ~5,000 people, so it is not a "Large City" (oar.660-046-0020.txt:72) and HB 2138 asks it only for duplexes (hb.2138.2025.txt:76-78); the cap does not reach it. Drawn court seats 5 ("band minimum") -- 1 short of 6 as drawn. But the court ends ~123 ft from Eagle Creek Rd (computed from the drawing), the 200 ft band leaves ~77 ft more, and the lot runs to ~413 ft: a second row or a longer court gives 6+ easily. "Motor vehicle parking areas fronting Eagle Creek Rd ... are prohibited" (:872) -- court is behind the building. RIGHT, but this is the only Estacada green (run 74, query of all 14) whose court seats < 6.
5. GEOMETRY: deep strip, single street, lane along the building's south side to the court. Fire 120 ft. Eagle Creek Rd may be state highway access (ODOT permit) -- outside the city code.
6. LAND: slope max 1.9%; no flood. Currin Creek 70 ft structure buffer (zones :886) not mapped (FOLLOWUPS 53(d)); nothing in the dossier puts a creek here.
7. WHO: prop 300 VAC, land $179,901 -- vacant.
8. UNCHECKED: NCR prints no width/depth/coverage/FAR/stories for a fourplex (zones :820-905 read whole).
9. FLAGS: ZONE-MISSING stale. Current: none.

## 34E17  02000 -- Estacada NCR (split, 47% NCR), 30941 SE River Mill Rd -- RIGHT (drawn court breaks an unencoded rule)
1. USE: fourplex outright within 200 ft of Eagle Creek Rd (emc.16.zones.txt:762). Building's farthest corner 71.6 ft from the Eagle Creek Rd lot line (computed from the drawing), nearest 14.9 ft. Envelope reaches ~168 ft from that line and stays inside the NCR part (the round-1 doubt "band not checked against the zone line" -- the envelope is the band cut to NCR; the pod sits at its east edge, far from any interior zone line).
2. LOT: 10,000 sf needed, 428,388 (NCR part ~200,000). 
3. BUILDING: yards 15/5/15, none required from Eagle Creek Rd (:860); height 35 (:876) vs 26.
4. PARKING: 6 required (emc.16.76.txt:77-78), seats 8. "Motor vehicle parking areas fronting Eagle Creek Rd, and motor vehicle parking areas separated from Eagle Creek Rd only by landscaping and/or fencing, are prohibited" (zones :872). The drawn layout: the pod faces River Mill Rd (side street) with its 36 ft end to Eagle Creek Rd, and the 56 x 47 ft court sits north of it with its 47 ft side ~16 ft from the Eagle Creek Rd line -- i.e. separated from the road only by the yard. That drawn court breaks :872 (estacada.yaml says this is NOT ENCODED). Not a false GREEN here: the lot is a corner (Eagle Creek Rd east, 526 ft = shortest = front; River Mill Rd south, 864 ft), and a building facing Eagle Creek Rd near the SE corner with the court behind it and the drive off River Mill Rd fits with room to spare inside the band (envelope runs to within 15 ft of the south line). Pattern risk: on a small NCR lot whose only street is Eagle Creek Rd and whose court ends up beside, not behind, the building, :872 would bind.
5. GEOMETRY: big irregular corner lot; slope fine under the pod (grade 1.25%); steep ground elsewhere (60,536 sf) not in the band where the pod is.
6. LAND: no flood; Currin Creek buffer unmapped (53(d)).
7. WHO: prop 401 RUR, 1917 buildings $196k, sold $3,198,000 2025-04 (POLICY note).
8. UNCHECKED: NCR prints none of them for a fourplex.
9. FLAGS: ZONE-MISSING stale; none current.

### Estacada pattern note (all 4 lots)
- PARKING CAP MISAPPLIED: every Estacada green is charged 4 stalls (margins parking_stalls threshold 4) because _state.yaml's OAR 660-046-0220(2)(e)(B) Large-City cap (spaces_total 4) applies. Estacada is outside Metro and well under 25,000 people, so it is not a Large City (oar.660-046-0020.txt:72: "a city with ... 25,000 or more or a city with a population over 1,000 within a metropolitan service district"); HB 2138 asks a non-Metro city of 2,500-25,000 only for duplexes (hb.2138.2025.txt:76-78). Estacada's own 6 stalls (1.5 x 4 rounded up, emc.16.76.txt:77-78) should be the charge. Queried run 74: of 14 Estacada greens only 34E17D 00700 seats fewer than 6 (5), and it has room for more. So 0 false greens today, but the cap is wrong for Estacada (and would be for Canby/Sandy/Molalla when they open).
- 16.25.050(F)(2) "no parking fronting Eagle Creek Rd" is not encoded; the drawing on 34E17 02000 breaks it though a compliant layout exists.

## 22E17DB00316 -- Gladstone R-7.2, 1125 Clayton Way -- RIGHT
1. USE: 17.10.020 "(2) Middle housing" outright (17.10.r-7.2.txt:33-39). "Middle housing means duplex, triplex, quadplex, cottage cluster, or townhouse in the R-5 or R-7.2 zone"; quadplex "four attached or detached dwelling units on a single lot in any configuration" (17.06.definitions.txt:587-589, 611-613). Conditional list (17.10.040) holds only 5-8 unit multi-household. Design Review chapter 17.80 is not stored; Gladstone is a Large City (inside Metro), so its middle-housing path must be clear-and-objective; 17.10.060(4) design features (4 of 11 on the street facade) are objective items a pod can carry.
2. LOT: middle housing min lot 3,600 sf (:161); lot 10,823. Max density "Middle housing None"; "does not allow ... more than four dwelling units on a lot, including accessory dwelling units" (:212) -> pod exactly 4 (no ADU). No width/frontage/depth minimum printed (whole 17.10.050 read). Min density applies to subdivisions/PUDs only.
3. BUILDING: front 20 (:169), side 7.5 / interior side 5 (:175, :187 -- screen takes 7.5), rear 15 (:197), height 35 (:204) vs 26. Measured from the drawing: building 20.3 ft from the Clayton Way line, ~16 ft off the west line, lane 12 ft on the east side leaving ~11 ft to the east line. No coverage/FAR in R-7.2.
4. PARKING: 1 per unit (17.48 Table 1, per yaml quote 17.48.parking.txt:171-173); stalls 9.5 x 18, aisle 24, curb 5 ft off every property line (encoded). Court 48 ft across x 49 ft deep, 17 ft off the rear line: 4 x 9.5 = 38 <= 48; 18 + 24 = 42 <= 49. Seats 6.
5. GEOMETRY: interior 75 x ~143 ft lot on Clayton Way (north), neighbours 1115/1135 Clayton Way either side. Not a corner, not a flag. Fits plainly. Fire 121 ft.
6. LAND: slope max 7.4%, p85 4.2%; no flood; sewer present.
7. WHO: prop 101 SFR, 1978 house 2,182 sf -- ordinary house.
8. UNCHECKED: none of width/depth/coverage/FAR/stories exists in 17.10.050.
9. FLAGS: none current.

## 22E20CC05400 -- Gladstone R-5, 270 W Clackamas Blvd -- RIGHT
1. USE: 17.12.020 "(2) Middle housing" outright (17.12.r-5.txt:31-37); quadplex is middle housing in R-5 (17.06.definitions.txt:587-589, 611-613). No conditional/design-review gate in the chapter.
2. LOT: "Quadplex 7,000 sf" (:167-168); lot 9,500. No width/depth minimum; min density only for cottage clusters; min vegetation 20% only for multi-household (5+).
3. BUILDING: front 20 (:182; 10 in Town Center -- only looser), side 5 (:189), street side 20 (:197), rear 15 (:205), height 35 (:~214) vs 26. Measured: building front corners 20.0 / 26.9 ft from the street line, west face 5.7 ft from the west line; lane (12.0 ft) to east line 6.2 ft; court rear 28.7 ft from the NW (rear) line.
4. PARKING: 1/unit (17.48 Table 1); stalls 9.5 x 18, aisle 24; "set back a minimum of five feet from the property line" (17.48.parking.txt:466). Court 48 x 49 ft: 4 x 9.5 = 38 <= 48, 18 + 24 = 42 <= 49; corners 6.8 and 5.2 ft off the side lines. Seats 5. No driveway width printed in 17.48 (grep "driveway|width").
5. GEOMETRY: parallelogram ~60 ft wide (perpendicular) x ~160 ft; street W Clackamas Blvd on the SE (41 + 12 + 8 ft, the 8 ft piece a chamfer, front_bearings 11.9/37.7 = same street bending). North-west end abuts R5 lots on W Arlington St (no street). East and west sides abut 250 and 280 W Clackamas Blvd. pod80x25 also green but only 1.0 ft slack and seats 4; pod56x36 has 22.5 ft slack -- the stronger one.
6. LAND: slope max 7.6%; no flood; sewer present.
7. WHO: prop 101 SFR, 1920 house 2,000 sf -- ordinary.
8. UNCHECKED: no such standards in 17.12.050 (read whole) for a quadplex.
9. FLAGS: none.


## 23E06AB00600 -- Happy Valley SFA, 12770 SE 172nd Ave -- RIGHT
1. USE: Table 16.22.050-1 (16.22.residential.txt ~L775) quadplex = P in SFA. No design-review trigger for a quadplex in the residential chapter; 16.42.landscaping.txt:25 exempts quadplexes from most of 16.42.030. By right.
2. LOT: 87,066 sf, ~470 x 185 ft, rectangular. SFA min lot 2,000 sf; no width/depth minimum in Table 16.22.050-2. Density 10-15 du/net ac carries note [2] in the SFA column: quadplexes exempt. Fine.
3. BUILDING: front 10, side 5, rear 15, street side 8, coverage 75%, height 45 (Table 16.22.050-2, L930-1040). Drawn pod 10 ft from 172nd Ave and 5.5 ft from the south line. Note [4] 10 ft landscaped buffer where SFA abuts a lower-density zone: R5 sits on the far east line (186 ft shared), about 400 ft from the pod. 16.42 B.1: 20% landscaping for fourplexes = 17,400 sf of 87,066; trivially met. 16.42.080 shared recreation applies only to subdivisions of 30+ units (L600-605). Not applicable.
4. PARKING/ACCESS: 4 stalls charged; court drawn east of the pod with no lane. Lot fronts SE 172nd Ave on the west (~185 ft). It is flagged corner_lot, probably because the end of the SE Zion St stub touches the north line in a ~53 ft gap (x 7692599-7692652). A drive from either street to the court is trivially possible on this lot.
5. GEOMETRY: big plain rectangle; pod at the SW corner, well inside the envelope.
6. LAND: slope max 4.8%; no flood plain; in the sewer district.
7. WHO: prop 101 SFR, 1972 house of 1,521 sf, $735k total. Ordinary house on a big lot; policy blank.
8. UNCHECKED: frontage/width/depth (none in the table), FAR/stories (none), density (exempt by [2]). Nothing failable.
9. FLAGS: none in run 74 checks.

## 23E06BB00502 -- Happy Valley MUR-A, 12612 SE 162nd Ave -- RIGHT (density-note remark)
1. USE: Table 16.22.050-1 (~L775): "Four-family dwelling (quadplex)" P in MUR-A. Quadplex = "A building containing four dwelling units on a single lot" sharing 20 ft walls (16.12.definitions.txt:557-558); the pod qualifies. 16.62 Design Review is not stored; the residential chapter names no review for a quadplex, and as middle housing in a Metro city only clear and objective standards may apply. By right.
2. LOT: 51,408 sf (1.18 ac), 189 ft along 162nd Ave by 272 ft deep. MUR-A min lot 3,000 sf; no width or depth minimum. Density: the max cell is "15 du/net acre[2]"; the min cell is "10 du/net acre" with NO [2] marker (L946-948). Note [2] (L1016): "...quadplexes ... are exempt from the density standards." The sentence is general (plural "standards"), and the encoding reads it that way on purpose (happy-valley.yaml:2905). A marker-strict reader would want ~11.8 units vs 4 (3.4 du/ac). Even then, the standing ruling makes a min-density miss a severity-2 flag, which stays green. Colour unchanged. Encoding remark only: a DENSITY-MIN flag would be the cautious reading.
3. BUILDING: front 10, rear 15, side 5, street side 8, coverage 75%, height 65 (note [8] 45 front elevation applies to SF attached/detached; pod 26 ft clears both). Building drawn 10+ ft from 162nd Ave and ~6 ft from the south line. 16.42 B.1 20% landscaping is trivially met. 16.42.080 shared recreation is for subdivisions of 30+ units only.
4. PARKING/ACCESS: 16.43.parking.txt:215 quadplex 1 per dwelling = 4. 16.41.030 B.1 driveway 20 ft two-way or 12 ft one-way (L58). Court drawn behind the pod with no lane, but the lot has ~110 ft of 162nd Ave frontage north of the pod for a drive. Flagged corner_lot: the north line (262 ft) is shared with a ~18-25 ft strip that belongs to 12596 SE 162nd Ave (MURM, the big lot east). It looks like that lot's access pole, not a public street. Either way a drive fits.
5. GEOMETRY: plain rectangle; pod and court at the SW, well inside the envelope (slack 181.5).
6. LAND: slope max 6.0%; no flood; sewer district.
7. WHO: prop 101 SFR, 1961 house of 1,960 sf, $588k, sold 2017 $459.5k. Policy blank.
8. UNCHECKED: frontage/width/depth (none set), FAR/stories (none), density (see 2).
9. FLAGS: none in run 74 checks.

## ZDO reading common to the six unincorporated Clackamas lots (R-7 / R-10)
- USE: Table 315-1 "Quadplexes P[8,9]" in the urban low-density districts (zdo.315.txt ~L295-300). [8] one primary use per lot (L1102); [9] subject to Section 845 (L1104). Quadplex is one building with four units on one lot; the pod qualifies. Design review is not required in R-7/R-10: 1102.01 A lists commercial, industrial, HDR/MR-1/MR-2/MRR/PMD/RCHDR/SHD/VA/VTH, institutional, and HR townhouses only (zdo.1102.txt:5-21). By right. KNOWN-61 (1005.02(L) compass setbacks) touches SHD/RCHDR/VTH/HDR only, so it does not apply here.
- LOT: 845.01 A.2 quadplex minimum 7,000 sf (zdo.845.txt:3-7). Table 315-2 DLA (7,000/5,600 for R-7; 10,000/8,000 for R-10) is applied by 1012, which covers only land divisions, design review and conditional uses (zdo.1012.txt:1-13). Minimum density (1012.08) does not reach a quadplex on an existing lot. There is no width, depth or frontage minimum in Table 315-2. 845.01 C bans quadplexes in the Floodplain Management District.
- BUILDING: Table 315-2 (L1166-1276): front 15 (20 to garage entries), rear 20, side 5, height 35, coverage 50%. Every road-abutting line is a front lot line, and a corner has more than one (zdo.202.definitions.txt:277, 285-289). 845.02 A/B windows 15% and entry orientation are design items a pod can meet.
- PARKING/ACCESS: no minimum inside the UGB for Section 315 zones (zdo.1015.txt 1015.02 B.1; Table 1015-2 quadplex 0). Stalls 8.5 x 16; maneuvering on site (1015.02 A.1-2). 845.02 C: driveway entries total 32 ft max; with more than one street, access only from the lowest-class street. 845.02 D: no garages or parking between building and public street unless 50% of frontage or screened by a dwelling.

## 21E12CB04900 -- Clackamas uninc R-7, 15574 SE Creswain Ave -- RIGHT (tight)
1. USE: R-7 quadplex P. Zone fraction 1.0; no overlay.
2. LOT: 8,001 sf >= 7,000 (+1,001). 80 ft on Creswain by 100 ft deep, interior rectangle (shared lines: 101 ft each side, 81 ft rear).
3. BUILDING: envelope 4,551 sf. Pod 56 ft face parallel to Creswain at the 15 ft line. Depth needed 64 (36 pod + 28 court room) vs 64.5 available, slack 0.5 (FIT-TIGHT flag, green). The court itself runs back into the 20 ft rear yard to ~3 ft off the rear line; the ZDO sets setbacks for structures and I found no parking-area setback in 1015. Coverage 25.2% vs 50; height 26 vs 35.
4. PARKING: 7 seated, 4 charged, 0 required. A 12 ft lane runs along the NW side of the building (about 5 ft off the side line) from the front setback to the court behind. Parking is not between building and street (845.02 D OK). One driveway entry, under 32 ft.
5. GEOMETRY: plain interior lot; front correct (Creswain, SW side). Fire route 102 ft vs 150.
6. LAND: max slope 34% somewhere on the lot, but steep_sqft 0 and pad grade 4.8% (dem_1m). No SFHA. Sewer in district.
7. WHO: prop 101 SFR, 1968 house; policy blank.
8. UNCHECKED: width/depth/frontage (none in Table 315-2), FAR/stories (none), density (1012 does not apply).
9. FLAGS: FIT-TIGHT 0-1 ft (green by design).

## 21E19BB09300 -- Clackamas uninc R-10, 6315 SW Dawn St -- RIGHT (sewer remark)
1. USE: R-10 quadplex P (common block above). Zone fraction 1.0; no overlay; inside the UGB.
2. LOT: 10,605 sf >= 7,000 (+3,605). About 100 ft wide on the curved Dawn St frontage (south) by ~115-123 ft deep. Interior lot: shared lines are 115.8 ft (6261 Dawn, east), 122.9 ft (6355 Dawn, west) and 103 ft (6262 Wayzata Ct, north). 6236 Wayzata Ct touches at one point (1 ft); the Wayzata Ct bulb is ~20 ft off the NE corner, so this is not a corner.
3. BUILDING: envelope 6,543 sf; pod 56 ft face toward Dawn St; depth fit 78 vs 67 (slack 11). Coverage 19%; height 26/35.
4. PARKING: 8 seated, 4 charged, 0 required. A 12 ft lane on the west side reaches the court behind the pod; the court ends ~11 ft off the north line. One entry. 845.02 D OK.
5. GEOMETRY: plain; front correct.
6. LAND: max slope 24.6% somewhere; steep_sqft 0 under the pod, grade 2.7%. No SFHA.
7. WHO: prop 101 SFR, 1965 house; policy blank.
8. UNCHECKED: nothing failable.
9. FLAGS: none. REMARK: sewer.in_district = False, main_dist_ft 16,042. Nothing in the stored ZDO text (315, 845, 1012, 1015, 202) makes public sewer a condition for a quadplex; Section 1006 (utilities) is not stored. FOLLOWUPS (c) at L166 already records that "no Clackamas standard turns on" public_sewer. A buildability question, not a zoning false GREEN. Worth a human look if 1006 is ever stored.

## 22E07DD00255 -- Clackamas uninc R-10, 16241 SE Katie Ct -- RIGHT
1. USE: R-10 quadplex P. Zone fraction 1.0; no overlay; in the UGB; sewer district yes (main 1,011 ft).
2. LOT: 9,967 sf >= 7,000. Front line (SE, on Katie Ct) 98 ft. Side lines 102.6 ft (16229 Katie Ct, NE) and 102.8 ft (16257 Katie Ct, SW). Rear shared with 5850/5860 Sky High Ct. Not at the cul-de-sac bulb, so a single front.
3. BUILDING: my arithmetic from the drawing coords: pod front face 15.0 ft from the Katie Ct line (front 15 OK; no garage, so the 20 ft garage figure does not apply); NE corner 5.9 ft from the NE side line (side 5 OK). Depth fit 66 vs 65 needed, slack 1.0. Coverage 20.2%, height 26/35.
4. PARKING: 8 seated, 4 charged, 0 required. 12 x 36 lane on the SW side of the pod leads to a 68 x 49 court behind it, which ends ~1.6 ft inside the rear line (on site, 1015.02 A.1). Parking not between building and street. One entry, under 32 ft.
5. GEOMETRY: plain rectangle; front correct. Fire route 101.6 vs 150.
6. LAND: max slope 24.7% at some point; steep 0 sf under the pod, grade 0.9%. No SFHA.
7. WHO: prop 101 SFR, 1993 house of 2,753 sf; policy blank.
8-9. UNCHECKED nothing failable; no flags.

## 12E32BA01100 -- Clackamas uninc R-10, 6802 SE Queen Rd -- RIGHT
1. USE: R-10 quadplex P. Zone fraction 1.0; no overlay; UGB; sewer district (main 472 ft).
2. LOT: 17,800 sf (100 ft on Queen Rd, north, by 178 ft). Interior: 179 ft shared each side, rear abuts the Jack Rd lots. One street.
3. BUILDING: envelope 12,870 sf after the steep-ground carve (jagged NW edge). Pod front face at y 655907.6 vs street line ~655925, about 17.6 ft (front 15 OK). West face ~14.7 ft from the side line. Coverage 11.3%; height 26/35. Both pods green (56x36 slack 70.5; 80x25 slack 31.5).
4. PARKING: 8 seated, 4 charged, 0 required. 12 ft lane on the east side, ~16 ft off the side line, to the court behind (south of) the pod. 845.02 D OK.
5. GEOMETRY: plain long rectangle; front correct.
6. LAND: max slope 53% and steep_sqft 2,375 (dem_1m), carved before placement; pad grade 4.2%; steep_blocks False. The ZDO steep-slope chapter (1002) is not stored, and the slope screen is KNOWN-38/49 territory. The pod stands on gentle ground, so I see no miss.
7. WHO: prop 101 SFR, 1955 house; policy blank.
8-9. UNCHECKED nothing failable; no flags.

## 12E32AC02700 -- Clackamas uninc R-7, 7621 SE Harmony Dr (through lot) -- RIGHT (drawn court breaks 845.02 D; compliant layout exists)
1. USE: R-7 quadplex P. Zone fraction 1.0; no overlay; UGB; sewer district.
2. LOT: 12,529 sf >= 7,000. 65 ft wide by ~194 ft. Through lot (observed.through_lot): SE Harmony Dr along the south line (y ~653788), SE Oris Ln along the north line (y ~653982). I confirmed Oris Ln from the DB: the 7814-7884 SE Oris Ln lots end at y ~653960 and the Heather Ct and 77th Ave lots start at y ~654000-654011, so a ~30-40 ft right-of-way runs east-west along our north line. Both are front lot lines (zdo.202.definitions.txt:285, any boundary separating a lot from a road).
3. BUILDING: depth-facing pod (36 across, 56 deep); front face 15 ft off Harmony Dr; envelope north edge 15 ft off Oris Ln. Coverage 16.1%; height 26/35. Slack 55.5 (56x36) and 31.5 (80x25).
4. PARKING/ACCESS: the drawn court is 48 ft wide (x 7667089-7667138) and runs from the pod's back wall to y 653911, which puts it between the building and Oris Ln. 845.02(D) (zdo.845.txt:51-55): parking "shall not be located between a building and a public street" unless screened by a dwelling, or "the combined width of all garages and off-street parking areas located between a building and a public street does not exceed a total of 50 percent of the street frontage". Oris Ln frontage is ~65 ft, so the cap is 32.5 ft; the drawn 48 ft breaks it. The encoding holds parking_area_max_frontage_pct 50 (_unincorporated.yaml:1022-1030), but flats/score/paper.py:1031 reads it only for the beside-the-building court; the docstring at L954 says "a through lot's far end is a street the fit cannot see". So the rear court on a through lot is not tested against it.
   A compliant layout exists: a 12 ft aisle plus 8.5 ft parallel stalls (8.5 x 22, 1015.02 A.2) is 20.5 ft wide, and 4 stalls in a row run 88 ft of the ~106 ft behind the pod. That is under the 32.5 ft cap. Zero stalls are required inside the UGB in any case (1015.02 B.1; ruling: zero-required zones need none). 845.02(C)(3) "lowest functional classification" street is unmeasured; either street can reach the court on this layout.
5. GEOMETRY: long rectangle, two parallel frontages. quadfit's layout_method = townhome_rear_court_rear_street.
6. LAND: max slope 13.9%, grade 0.3%. No SFHA. The OSM open-space parcel (7400 SE Thompson Rd) is 106 ft NW and not on the lot.
7. WHO: prop 101 SFR, 1958 house; policy blank.
8-9. UNCHECKED nothing failable; no flags. PATTERN NOTE: on Clackamas through lots (and corners), the rear court can sit between the pod and the second street. 845.02(D)'s half-frontage cap is read only for a beside court (paper.py:1031), never for a rear court facing a second street. Not a false GREEN here, because a narrower court fits.

## 22E07CA07100 -- Clackamas uninc R-10, 4825 SE Allan Rd -- RIGHT
1. USE: R-10 quadplex P. Zone fraction 1.0; no overlay; UGB; sewer district.
2. LOT: 19,009 sf >= 7,000. 100 ft on Allan Rd (SE line) by 191 ft (191.1 ft shared each side with 4847 and 4785 Allan Rd). The rear touches 4706 SE Thiessen Rd (26.4 ft); the Thiessen Ct lots are 11 ft or more off with no street between. Interior lot, one street.
3. BUILDING: envelope 13,958 sf; pod front face parallel to Allan Rd at the 15 ft line. Coverage 10.6%; height 26/35.
4. PARKING: 8 seated, 4 charged, 0 required. 12 ft lane on the SW side of the pod to the court behind; parking not between building and street. One entry.
5. GEOMETRY: plain rectangle; front correct. Fire 102 ft (56x36), 130 ft (80x25), both under 150.
6. LAND: max slope 22.4% somewhere; steep 0 sf under the pod; grade 0.6%. No SFHA.
7. WHO: prop 101 SFR, 1951 house of 2,403 sf; policy blank.
8-9. UNCHECKED nothing failable; no flags.
