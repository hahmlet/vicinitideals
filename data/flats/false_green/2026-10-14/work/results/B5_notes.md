# B5 notes -- Cornelius + Hillsboro SCR-MD (false-GREEN round 2)

## 1N334DD06300 -- Cornelius R-7, 2907 N Clark St -- RIGHT

Code read (whole chapter cmc.18.20.r-7.txt, plus 18.100, 18.145, 18.150, 18.155, 18.160, 18.195 definitions):
- USE: R-7 permits outright "Middle housing" (cmc.18.20.r-7.txt:29-31). "Dwelling, quadplex" = "a building containing four attached or detached dwelling units located on a single parcel or lot" (cmc.18.195.definitions.txt:215-216); middle housing includes quadplex and townhouse (L191-192). Review: middle housing site plans are Design review Type I (cmc.18.100.site-design.txt:89), administrative = by-right. Note a stale conflict: 18.20.040(B) prohibits "More than one dwelling unit on a single lot, except for an accessory dwelling unit or a duplex" (cmc.18.20.r-7.txt:123) -- contradicted by the later permitted-use list and the quadplex lot-size row; read as superseded (state middle-housing law), not a finding.
- LOT: quadplex min lot 7,000 sq ft (L157-159); lot 11,146. Max density "does not apply to ... quadplexes" (L151). Min density 4/net acre (L168): 4 units on 0.34 net acre = 11.7/ac, passes. Lot shape min 60x60 (L216): lot 93 x 120 ft.
- BUILDING: front 10 ft (L188), rear 10 (L192), side 5, corner street side 10 (L196); height 35 ft, measured average grade to midway ridge/eave (L172; cmc.18.195.definitions.txt:323-324). No coverage / FAR / stories in R-7 (grep whole folder: coverage appears only in CR). Design menu 18.100.070 (3 of 20 features) is architectural only.
- Envelope measured from the drawing: west (N 29th Ave, 93 ft, narrower = front) 10, north (N Clark St, street side) 10, east (rear, 297 N 30th Ct) 10, south (side) 5 -- matches the code.
- PARKING: middle housing 1.0/DU (cmc.18.145.parking.txt:131-135); 4 charged. Stall 9x20 (L501). R-7's "one covered parking space ... for each home" (cmc.18.20.r-7.txt:312) is read by the encoding as spared for the quadplex by state rule; also lot is 849 ft from a frequent route (parking_reform true). Driveway 12-25 ft (L280).
- GEOMETRY (zoomed picture): building on the west half facing N 29th Ave, court east of it, court opens north to N Clark St (side street, per corner ruling). Room 14 ft. Hose 93 ft.
- LAND: grade 4.9%, no steep, no flood, no overlay.
- WHO: SFR 101, 1992 house 1,302 sq ft. Ordinary house.
- UNCHECKED: frontage/width/depth (60 ft min, passes), coverage/FAR/stories (none in R-7), max_units (none for quadplex). Nothing fails.
- FLAGS: SOLAR-SHADE (sev 2, ruled "green with a warning"). 18.160 shade point cap H = (2xSRL - N + 150)/5 (cmc.18.160.solar-balance-point.txt:~40-50); here the north line is the N Clark St right-of-way, so the shade falls on the street (exemption "undevelopable area", L316-322). Not colour-changing.

## 1S304AA04600 -- Cornelius R-7, 1244 S Cherry St -- RIGHT

- USE / review: as lot 1 (middle housing outright, cmc.18.20.r-7.txt:31; Type I site plan, cmc.18.100.site-design.txt:89).
- LOT: 9,375 sq ft vs 7,000 quadplex minimum (L159). 75 ft frontage, 125 ft deep (60x60 minimum L216 passes). Min density 4/net acre: 4 units on 0.287 net acre = 13.9/ac.
- BUILDING: envelope measured 10 ft from the street (south, S Cherry St), 10 from the rear (1239 S Beech St), 5 from each side -- matches L188-196. Height 26 vs 35 (L172).
- PARKING: 4 stalls 1/DU; 14 ft lane (>= 12 ft minimum pavement, L280) along the east side of the building to a ~50x51 ft rear court.
- GEOMETRY: interior lot, one street, rectangle with a small jog. FIT-TIGHT -0.5 ft (the court touches the rear-yard line): ruled green-with-flag (< 1 ft). Pod80x25 does not fit (red), so pod56x36 carries the green.
- LAND: grade 3.3%, no flood/overlay.
- WHO: 1947 house, SFR 101. Ordinary.
- SOLAR: north lot line is the rear neighbour. Building north face ~59 ft from it; Table A row 60 / N 90+ gives 36 ft shade-point cap > 26 ft -- passes the basic 18.160(B)(1) test.
- UNCHECKED: no R-7 coverage/FAR/stories; nothing fails.

## 1N334DD06100 -- Cornelius R-7, 344 N 29th Ave -- RIGHT

- USE / review: as lot 1.
- LOT: 11,249 sq ft (7,000 min, L159); 75 ft frontage on N 29th Ave (west), 150 ft deep. Min density passes (11.7/ac... 4 units / 0.344 net ac).
- BUILDING: envelope measured 10 front (west), 10 rear (east), 5/4.9 sides -- matches L188-196. Height 26 vs 35.
- PARKING: 14 ft lane along the building's south side to an east court (50x54); 4 stalls charged, 7 seated.
- GEOMETRY: plain interior rectangle; pod56x36 room 16 / 21.5 ft; pod80x25 also green with a 0.5 ft tight flag.
- LAND: grade 1.8%, nothing.
- WHO: 1990 house, 2,933 sq ft, SFR 101. Ordinary (large) house.
- SOLAR (flag): drawn building's north face is ~8 ft from the north lot line (378 N 29th Ave). 18.160(B)(1): H = (2xSRL - N + 150)/5, N = 75 -> with SRL 8 (eave on the north face, flat-ish E-W roof) H = 18.2 ft, below a 2-storey eave. With 16 ft room the pod can sit ~24 ft off the line: H = (48 - 75 + 150)/5 = 24.6 ft, clearing an eave around 21-22 ft; also the 50% yard adjustment (L568) and performance option (L284) exist. Ruled green-with-warning; I agree it does not decide the lot.
- UNCHECKED: nothing in R-7 that fails.

## 1S304AC00321 -- Cornelius R-7, 506 S 8th Ave -- RIGHT

- USE / review: as lot 1.
- LOT: 9,562 sq ft vs 7,000 (L159); 76.5 ft frontage (S 8th Ave, west), 125 ft deep (60x60 min passes).
- BUILDING: envelope 10 front, 10 rear, 5 sides (measured) = L188-196. 26 vs 35 ft.
- PARKING: lane 14 ft north of the building to an east court ~50x50; 4 stalls.
- GEOMETRY: rectangle, one street. FIT-TIGHT -0.5 ft (green-with-flag by ruling). pod80x25 red (does not fit).
- LAND: grade 0.7%.
- WHO: 1964 house, SFR 101. Ordinary.
- SOLAR: building in the south half, north face ~36 ft from the north line; N = 76.5; H = (72 - 76.5 + 150)/5 = 29.1 ft > 26 -- passes 18.160(B)(1).
- UNCHECKED: nothing that fails.

## 1N333CC01700 -- Cornelius A-2, 335 N 4th Ave -- RIGHT

Code: cmc.18.35.a-2.txt (read whole; line numbers below are of the file with blank lines dropped -- grep the phrase to find them).
- USE: permitted outright "(B) Middle housing developments." (18.35.020). Prohibited (H) "More than one single-family detached or common-wall single-family dwelling unit on a single lot" -- not a quadplex. 18.35.060 intro: "All multi-family developments are subject to design review requirements as set forth in Chapter 18.100" -- but 18.100.030(A)(2) puts "middle housing" site plans in Type I (cmc.18.100.site-design.txt:89), and Steph ruled 2026-10-01 the fourplex is not multi-family in Cornelius. By-right.
- LOT: quadplex 7,000 sq ft min (18.35.050(A)(1)); lot 15,009. Max density "does not apply to middle housing". Min density 8/net acre (not the multi-family 11, by the same ruling): 15,009/32,670 = 0.459 net ac x 8 = 3.7 units -> 4 passes (at 11 it would need 5.05, fail -- rests on the ruling). Min width 30 ft at street, depth 60 (18.35.050(G)(1)): 75 x 200.
- BUILDING: front 10, rear "10 feet ... for a single-story structure, plus five feet per additional story" = 15 for 2 storeys, side 5 (single-family figure, per ruling). Envelope measured: front (east, N 4th Ave) 10.0, rear (west) 15.0, sides 5.0. Height 45 ft cap; 26 ft.
- PARKING/ACCESS: internal drives two-way 24 ft (18.35.060(D)(3)(a)) -- lane drawn 24 ft. "No entrance or exit ... closer than 100 feet to any intersection ... unless there is no reasonable alternative" -- the lot has one frontage, so no alternative; not decisive. Parking-lot 5 ft perimeter landscaped buffer ((J)(3)): court 5.6 ft from south line, 9 ft from north. Covered parking (J)(1)(a): spared for the quadplex per the encoding/state rule; parking_reform (692 ft to frequent route).
- RISK NOTED, not ruled: 18.35.060(B)(2) "the reviewing body may require" a perimeter strip up to 50 ft where the development abuts a nonresidential area -- the lot abuts C-2 on two sides. This is discretionary condition language, not a clear and objective standard; Oregon housing law (ORS 197.307(4)) bars applying it to deny or shrink needed housing. Not counted.
- GEOMETRY: rectangle, one street; building at the front, lane on its north to a west court. Room 4.5 / 40 ft.
- LAND: grade 0.6%; no flood/overlay.
- WHO: prop code 220, no building, land $149k, address 335 N 4th Ave. Screened normally (not $0, has address).
- UNCHECKED: no coverage/FAR/stories in A-2; nothing fails. No solar warning (A-2 is the multi-family district, cmc.18.195.definitions.txt:606, so 18.160 does not reach it).

- Raw line numbers in cmc.18.35.a-2.txt: permitted middle housing L31, rear yard L204, side yard L208, perimeter strip L262, internal access 24 ft / 100 ft L302, parking buffer L394.

## 1N334CC02400 -- Cornelius CR, 1820 N Davis St -- RIGHT (note on the density floor)

Code: cmc.18.70.cr.txt read whole.
- USE: "Middle housing" permitted outright (L31); "Detached single-unit dwellings and middle housing developments are subject to design review requirements set forth in CMC 18.100.070 and are subject to a Type I site design review process" (L264) -- by-right. (Multi-unit 5+ is Type III, L262; the pod is 4.)
- LOT: quadplex 7,000 sq ft (L170); lot 17,895. Width 30 ft min (L248); 95 ft.
- DENSITY: "11 dwellings per net acre for all other dwelling types" (L184), on 18.195 net acreage (L161; cmc.18.195.definitions.txt:41-54: gross acre 43,560 less "street dedications and those areas used for private streets and common driveways", constrained land, tracts). Gross: 4 / (17,895/43,560 = 0.411 ac) = 9.74/ac < 11 (would need 4.5 -> 5 units). FLATS nets out the drive aisle (`less: [drive_aisle, floodplain]`), giving 11.023 vs 11.0 -- passes by 0.023. Whether a 4-home court lane is a "common driveway" is arguable; if not, the floor is missed. Either way Steph's ruling makes a density-floor miss a DENSITY-MIN severity-2 flag (green with flag), so the colour does not change. Worth knowing: the lot is right at the edge and carries no DENSITY-MIN flag.
- BUILDING: front 10 (L212), rear 10 (L216), side 5 (L224), corner street side 10 (L228, not corner). Measured envelope: south (N Davis St) 10, north 10, sides 5. Height 35 (L192). Coverage 60% (L240): 11.3%. Separation 6 ft (L232) n/a.
- PARKING/ACCESS: internal drives two-way 24 ft (L304-308): lane 24 ft. 100 ft from an intersection "unless no reasonable alternative" -- mid-block, one frontage. Covered parking (L380) spared for the quadplex (state rule, per encoding); 950 ft to a frequent route (parking_reform). 5 ft parking-lot buffer only for 5+ units (L392).
- GEOMETRY: rectangle; building at the front east, lane west of it to a rear court. Room 4.5 / 40 ft. North neighbour 1N334CC06500 has no zone/address (a right-of-way strip); rear setback applied there anyway; not a through-lot access question since the drive uses N Davis St.
- LAND: grade 1.0%.
- WHO: 1976 house 2,224 sq ft, SFR 101. Ordinary.
- UNCHECKED: no FAR/stories in CR. CR is not one of the single-family districts (cmc.18.195.definitions.txt:606), so 18.160 solar does not apply (no warning, correctly).


## 1N231DA08200 -- Hillsboro SCR-MD, 1011 NE Lincoln St -- RIGHT

- USE:
  - Quadplex and Townhouse are P in Table 12.22.420-1 (cdc.12.22.multi-dwelling-zones.txt:887-893).
  - Development Review is not needed. cdc.12.80.applications.txt D.1: "Middle housing and single detached dwellings in the MR-1, SCR-LD, or SCR-MD zones ... when no Adjustments ... are requested".
  - A quadplex is not a "Multiple Dwelling Structure", which needs 5+ units (cdc.12.01.general.txt:902, 910).
  - South Hillsboro (12.65) does not reach this lot. The lot is in central Hillsboro, and 12.65 has its own zones.
  - Downtown Plan District: the boundary is only a figure (Figure 12.61.200-A). Its SCR-MD rules do not bite here:
    - 12.61.600.A, 10 ft from a shared line with an SCC-DT parcel: the only SCC-DT polygon nearby is street right-of-way.
    - 12.61.600.C, architecture on NE Washington St between 6th and 9th: not this lot.
    - 12.61.300.B, use the alley: there is no alley.
- LOT:
  - 12,634 sq ft vs 7,000 (L1018-1025). Frontage 210 vs 22.
  - Min density 18 du/net acre (L1030-1034). 4 units / 0.29 ac = 13.8, a miss. DENSITY-MIN is severity 2 (Steph ruling), so it stays green with a flag.
  - Max density does not apply to quadplexes.
- BUILDING:
  - Setbacks: front 5, side 5, rear 10 (L1092-1115).
  - A corner lot has 2 front lines and no rear line (cdc.12.01.general.txt:1009-1018), so the north and west lines are sides. FLATS used 10 ft on the north line, which is stricter than the code.
  - Max front: 13 ft for middle housing (L1128). The building is 5.0 ft off Cornell, so it is met.
  - Max side: "Side Yard (all structures) 5 feet" (L1132). Not encoded (see the hillsboro.yaml SCR-MD comment).
    - 12.50.130.C.3.a (lot-and-site.txt about L345): for middle housing, a maximum setback "is considered met ... where at least 1 facade, including a porch, is located no farther from the property line than the setback specified".
    - I read that as one facade within 5 ft of a side line.
    - As drawn, the building is 14.7 ft from the north line and 47 ft from the west line.
    - It can slide 12.6 ft along Cornell, staying 5 ft off it, to sit 5 ft from the north line. Nothing stands north of it.
    - A STRICT reading (a facade within 5 ft of EVERY side line) would fail this lot and almost every SCR-MD lot; see pattern note 1.
  - Height: 3 stories, at 10 ft a story (12.50.140 B.6) = 30 ft, vs 26 ft. The cap sits in the 22-30 ft band, with 4 ft of room.
  - Min 2 stories: the pod has 2. No coverage limit (L1138).
  - Open space (12.50.210, Table 12.50.210-1): no quadplex row. As townhouses, 5% (about 630 sq ft) or exempt under D. The lot has thousands of sq ft of yard.
- PARKING/ACCESS:
  - No parking minimum (12.50.310 A.2). Max 2 per unit, vs 4 charged.
  - 12.50.715 C.2.c.i, the lowest-class street: Lincoln (local) is below Cornell (arterial). The drawn court opens to Lincoln.
  - 12.50.715 C.1: "combined width of all garages and outdoor on-site parking and maneuvering areas shall not exceed a total of 50% of any street frontage" (cdc.12.50.700-920.design.txt:171-173).
    - The drawn court sits in the Lincoln front yard and spans about 58 ft across a 55 ft Lincoln frontage (cap 27.5).
    - FLATS applies C.1 only to parking beside the building (paper.py), so it was not tested here.
    - A legal layout still exists: building along Cornell, a 36x47 court in the NW part (rel x 5-45, y 60-110), and a 12 ft lane off Lincoln (12 < 27.5).
  - Hose about 103 ft.
- GEOMETRY: viewed. A trapezoid: 55 ft on Lincoln, 155 ft on the diagonal Cornell line, 123 and 151 ft interior lines. Slack 19.5.
- LAND: max 12.9% in a 1 m cell, p85 4.1%. No flood.
- WHO: SFR 101, a 1948 house of 1,115 sq ft. Ordinary.
- UNCHECKED/FLAGS: none of these changes the colour.
  - FACT-FLAG-LOT: assumed, severity 0. This is not a flag lot.
  - DENSITY-MIN: severity 2.

## 1S206AC01402 -- Hillsboro SCR-MD, 632 SE 7th Ave -- RIGHT

- USE: as for 1N231DA08200 (P, and exempt from Development Review under 12.80 D.1).
  - All neighbours are SCR-MD.
  - No SCC-DT shared line and no alley, so the plan-district rules 12.61.600.A and 12.61.300.B do not apply, even if the lot is inside the district.
- LOT:
  - 7,109 sq ft vs the 7,000 quadplex minimum (109 to spare). Frontage 60 vs 22.
  - Density 4 / 0.163 ac = 24.5 vs 18 min.
- BUILDING:
  - Depth-facing pod, 36 ft wide and 56 ft deep.
  - 5.3 ft to the front (min 5, max 13).
  - 5.1 ft to the south side line: within 0.1 ft of the 5 ft max side, and the envelope allows 5.0, so the one-facade reading is met.
  - 18.4 ft to the north side, where the lane runs. The strict both-sides reading fails (pattern note 1).
  - 26 ft vs 3 stories (30 ft).
  - Open space: no quadplex row in Table 12.50.210-1. As townhouses: exempt under D, or 5% = 355 sq ft.
    - The yard north of the lane (about 6 x 56 = 336 sq ft), plus the rear and front strips, is borderline.
    - That is a design matter and not counted.
- PARKING:
  - A 12 ft lane on the north side reaches a 48x51 rear court.
  - The court is 4.9-5.9 ft from the lot lines, inside the 4 ft perimeter planter (encoded).
  - 12.50.715 C.1: the 12 ft lane is the only parking width at the street, 20% of 60.
  - Hose 111.6 ft. 4 stalls charged, 5 seated.
- GEOMETRY: viewed. A plain rectangle with a 0.5 ft tight fit. FIT-TIGHT under 1 ft keeps it green.
- LAND: max 7.3%. No flood.
- WHO: prop 701 MFR.
  - Year 0 and building sqft 0, but building value $243k.
  - Sold 2019 for $3.51M, far above this parcel's value, so it is probably one tax lot of a multi-parcel apartment property.
  - POLICY note only.
- FLAGS: neither changes the colour.
  - FACT-FLAG-LOT: severity 0, and this is not a flag lot.
  - FIT-TIGHT.

## 1N336DA01700 -- Hillsboro SCR-MD, 360 NW Connell Ave -- RIGHT

- USE: P, and exempt from Development Review (12.80 D.1).
  - MR-1 lots sit across Connell.
  - No SCC-DT nearby.
- LOT:
  - 9,243 sq ft vs 7,000. Frontage 84.
  - Density 4 / 0.2122 ac = 18.85 vs 18 (0.85 to spare).
  - The net-area deductions FLATS assumes are none (access easements, internal fire access) do not arise on a one-lot quadplex with a private lane.
- BUILDING:
  - pod56, width-facing.
  - 5.0 ft from Connell (max 13).
  - 5.7 ft from the south side line, and the envelope allows 5.0.
    - A 0.7 ft shift meets the one-facade max side.
    - The court perimeter strip stays at 4.7 ft or more.
  - 22 ft from the north side, so the strict reading fails (pattern note 1).
  - 26 ft vs 30.
  - pod80 is also green (tight fit 0.0).
- PARKING/ACCESS:
  - A 12 ft lane on the north side reaches a 51x68 court at the east. Hose 101 ft.
  - East side: the lot touches a 1N336DA ROW strip about 14 ft wide, between it and the NW Bailey Ave lots.
    - In the picture it is an alley, but facts.abuts_alley is false.
    - 12.50.715 C.2.c.i: for a lot "abutting an alley that is improved ... access must be taken from the alley".
    - 12.50.130 J.1: beside an alley under 20 ft wide, the setback is 10 ft from the alley's centreline. That is about 3 ft from the line.
  - The court is already at the east side, 17.5 ft from that line.
    - Alley access, if the alley is improved, only shortens the drive.
    - J.1 does not reach the building, which is 68 ft away.
    - The max-setback table says "Rear (including alley) None" (L1132).
  - FINDING (does not change the colour): an alley the screen did not see.
- GEOMETRY: viewed. Rectangle, slack 13.5.
- LAND: max 11.4%. No flood.
- WHO: a 1934 house of 1,212 sq ft. Ordinary.
- FLAGS: FACT-FLAG-LOT severity 0 only.

## 1N231DD00505 -- Hillsboro SCR-MD, 121 NE 12th Ave -- RIGHT

- USE: P, and exempt from Development Review (12.80 D.1).
  - The streets are right-of-way polygons zoned SCC-DT.
  - 12.61.600.A asks for 10 ft from a "shared property line with parcels zoned SCC-DT". A street is not a parcel, so it does not apply.
  - The interior neighbours (1147 E Main, 133 NE 12th) are SCR-MD.
- LOT:
  - 8,909 sq ft vs 7,000. Frontage 195.
  - Density 4 / 0.2045 = 19.6 vs 18.
- BUILDING:
  - A corner lot. Fronts: 12th (111 ft) and Main (64 ft, plus an 18 ft chamfer).
  - Sides: west and north, with no rear line (12.01.500). FLATS put 10 ft on both, which is stricter.
  - The building is 5 ft off 12th, so the max front is met.
  - It is 13.9 ft from the north line. It can move 8.9 ft north (room depth 16; the code's side minimum is 5) to meet the one-facade 5 ft max side.
  - Strict reading fails (pattern note 1).
  - 26 ft vs 30.
- PARKING/ACCESS:
  - The drawn court (36x47, no lane) opens toward Main, 8.7 ft from the Main line and 6.2 ft from the chamfer.
  - The lowest-class street (12.50.715 C.2.c.i) is not measured in Hillsboro.
    - No TSP map is held.
    - street_class.py gives no rank because no front is named.
    - So either street can serve.
  - As drawn, the court is parking in the Main front yard, about 42 ft wide vs a 32 ft cap (50% of 64). That misses 12.50.715 C.1, which FLATS does not test there.
  - The alternative fits:
    - Building along Main at 5 ft. The 56 ft length fits the 65 ft envelope width.
    - Court 47 ft behind it, opening straight onto 12th Ave (47 vs 50% of 111 = 55.6).
    - Short hose route.
  - Either street can serve, so the green stands.
- GEOMETRY: viewed.
  - Near-rectangle with a chamfered SE corner. Slack 13.
  - The bus stop 0.9 ft away is on the frontage; the driveway apron can avoid it.
- LAND: max 9.1%. No flood.
- WHO: a 1966 house of 1,784 sq ft. Ordinary.
- FLAGS: FACT-FLAG-LOT severity 0 only.

## 1N231DD00200 -- Hillsboro SCR-MD, no address (NE 11th Dr area) -- RIGHT

- USE: P, and exempt from Development Review (12.80 D.1).
  - The front street is a right-of-way polygon zoned SCC-DT, not a parcel.
  - The sides and rear are all SCR-MD.
- LOT:
  - 10,901 sq ft vs 7,000. Frontage 80.
  - Density 4 / 0.25 ac = 16.0 vs 18. DENSITY-MIN is severity 2, so it stays green with a flag.
- BUILDING:
  - pod56, width-facing.
  - 5.4 ft from the front (max 13).
  - 5.5 ft from the east side. The envelope allows 5.0 (room width 1.5), so the one-facade max side is met.
  - 18.5 ft from the west (the lane side), so the strict reading fails (pattern note 1).
  - 26 ft vs 30.
- PARKING:
  - A 12 ft lane on the west side reaches a 51x68 court behind the building.
  - Hose 93 ft. No alley.
- GEOMETRY: viewed. A rectangle, 80x136, with a small jog at the rear (e0, 12 ft). Slack 39.5.
- LAND: max 9.8%. No flood.
- WHO: VAC 100 with no address.
  - Land $222,890 (2014 sale $140k).
  - Not zero value and not a tract: an ordinary vacant lot.
- FLAGS: FACT-FLAG-LOT severity 0 and DENSITY-MIN severity 2.

## 1S206AB06600 -- Hillsboro SCR-MD, 468 SE 7th Ave -- RIGHT

- USE: P, and exempt from Development Review (12.80 D.1).
  - The SCC-DT neighbour at 730 SE Oak St is in the neighbour list but on no lot edge.
    - East edge: 723 SE Walnut (SCR-MD).
    - North edge: 454 SE 7th (SCR-MD).
    - The other two edges are street right-of-way.
  - So the 10 ft line of 12.61.600.A does not apply.
  - The lot is not on NE Washington St, so the 12.61.800 architecture rules do not apply under 12.61.600.C.
- LOT:
  - 9,000 sq ft vs 7,000.
  - Density 4 / 0.2066 = 19.4 vs 18.
- BUILDING:
  - A corner lot. Fronts: Walnut (south, 75 ft) and 7th (west, 120 ft). Sides: east and north.
  - The building sits in the SW corner, 5.0 ft off Walnut and 5.5 ft off 7th, so the max front is met.
  - It is 13.5 ft off the east side. It can move 8.5 ft east (the code's side minimum is 5; FLATS used 10) to meet the one-facade max side.
  - Strict reading fails (pattern note 1).
  - 26 ft vs 30.
- PARKING:
  - The court (47x56) is north of the building and opens to 7th Ave, 5.5 ft off that line.
  - Its width along 7th is 50 ft vs 60 (50% of 120), so 12.50.715 C.1 passes even read literally.
  - If Walnut is the lower-class street, a second layout fits:
    - Building along 7th (36 wide x 56).
    - A 12 ft lane off Walnut beside it (12 vs 37.5).
    - A court 47 deep across the 65 ft north part.
  - Hose 82 ft.
- GEOMETRY: viewed. Rectangle, slack 27.5.
- LAND: max 9.6%. No flood.
- WHO: a 1924 house of 1,411 sq ft. Ordinary.
- FLAGS: FACT-FLAG-LOT severity 0 only.

## Pattern notes (Hillsboro SCR-MD)

1. The maximum side setback is not encoded: "Side Yard (all structures) 5 feet" (cdc.12.22.multi-dwelling-zones.txt:1132, and SCR-HD at L1424).
   - Read with 12.50.130.C.3.a ("at least 1 facade ... no farther from the property line than the setback specified"), every lot here can meet it.
   - Read strictly (a facade within 5 ft of EACH side line), it fails every sampled SCR-MD lot. A fixed 56 ft pod with a side lane cannot sit within 5 ft of both side lines.
   - Steph needs to rule which reading applies. The strict one would turn SCR-MD (and SCR-HD) red almost everywhere.
2. FLATS applies 12.50.715 C.1 only to parking beside the building. C.1 caps parking and manoeuvring at 50% of ANY street frontage.
   - On corner lots, the drawn court often sits in the second front yard and would fail as drawn (1N231DA08200, 1N231DD00505).
   - A turned layout fits on both, so the colour does not change.
   - But the drawing shown to users is not a legal plan there.
3. Hillsboro corner lots get no street rank: there is no TSP map and no named front. So the lowest-class-street access rule is not measured. On these three corners a layout works off either street.
4. Hillsboro corner lots have no rear line (12.01.500). FLATS applies the 10 ft rear on an interior line. That is stricter, and harmless.
5. On 1N336DA01700, a narrow right-of-way strip (probably an alley) was not seen by abuts_alley.
