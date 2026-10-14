# B1 notes: Portland, 15 GREEN lots (run 74)

Code files are in flats/provenance/docs/or/multnomah/portland/. Line numbers refer to the stored text.
These rules apply to every lot:
- Colour is shown as if signed. `verdict unknown / RULE_UNVERIFIED` is normal.
- The maintained-street fourplex rule (33.110.txt:1534-1547, 33.110.265.E) is unencoded but ruled ("assume every lot qualifies", HUMAN_TODO).
- A missing minimum density is a severity-2 flag and stays green.

Key quotes used:
- 33.266.txt:282 "Vehicle area is prohibited between the primary structure and the street except as follows" ... (1) "Parking spaces located entirely behind the front and side street building lines" are allowed.
- 33.266.txt:~295 "On corner lots, no more than 20 percent of the land area between the side street lot line and the side street building line may be paved or used for vehicle areas." This cap does not appear in any margin, so it looks unencoded. It passed on every corner lot I checked.
- 33.266.txt:313 "If the lot abuts an alley, all parking and vehicle access to the site must be from the alley."
- 33.266.txt:319 "The minimum driveway width on private property is 9 feet."
- 33.910.definitions.txt:754-755 "On a corner lot, the front lot line is the shortest of the lot lines that abut a street."
- 33.910.definitions.txt:95 Building line: "parallel to a lot line, ... same distance from the lot line as the closest portion of a building".
- 33.120.txt:998-1002 Eastern Pattern Area: "rear building setback is an amount equal to 25 percent of the total depth of the site. No more than 50 percent of the Eastern Pattern Area rear setback can be vehicle area." The map is not held (KNOWN-68, item 68).
- 33.130.txt:959-975: "At least 50 percent of the length of the ground level street-facing facade of the building must meet the maximum setback". With several streets, the rule is "applied to the streets with the highest transit street classification".
- 33.130.txt:1415-1451: a ground-floor dwelling facade within 20 ft of the street must take one of three options: a flexible ground floor (12 ft ceiling), a 5 ft landscaped setback, or a floor raised 2 ft above the sidewalk.
- 33.110.txt:432-477 Table 110-4: front setback R10 20, R7 15, R5/R2.5 10; side/rear R10 10, others 5; height 30 (R2.5 35); FAR for 4+ units R7 0.7, R5 0.8, R2.5 1.0; R10 FAR only applies to lots under 10,000 sf (33.110.txt:496).
- 33.120.txt:525-567 Table 120-4: RM1 FAR 1, RM2 1.5; minimum density RM1 1 per 2,500 sf, RM2 1 per 1,450 sf; front 10, side/rear 5; coverage 50% (RM1), 60/70% (RM2).

## 1. 1S2E17AD  -07700 (RM2, 5205 SE 79th) RIGHT
- Corner lot. SE 79th on the east is the front (shorter line); Mitchell on the north is the side street. 80x90 ft, 7,199 sf.
- pod56 has 0.5 ft spare (FIT-TIGHT flag). The court is on the west side. No lane is drawn, but there is an 18 ft strip to Mitchell for access, which follows the side-street access ruling.
- Side-street 20% cap: about 162-216 sf of drive against about 324 sf allowed. Passes.
- Height 26 vs 45; coverage 28% vs 60%.
- Minimum density is 7,199/1,450 = 5 units against 4 proposed: the ruled flag.
- Slope, flood and overlays: none. Ordinary 1963 house; policy column blank.

## 2. 1S3E06CB  -06300 (R7, 16509 SE Stephens) RIGHT
- 90x85 ft, 7,650 sf, front on the south.
- pod56 spare 8.5 ft. Building is 15.0 ft from the street (15 ft required).
- The court sits beside the building at the setback line, not between the building and the street.
- Front-yard vehicle share is 20% (cap 40%). FAR 4,032 sf vs 0.7 x 7,650 = 5,355 sf.
- Nothing unchecked bites.

## 3. 1S2E04CB  -03900 (RM1, 8339 SE Stephens) RIGHT
- The lot touches only the dead end of SE Stephens, through a 25.3 ft notch (edge 3). The corner flag comes from reading the bend as a corner (KNOWN-63 shape); here it changes nothing.
- pod80 spare 11.5 ft. No lane is drawn. The only drive is a 9.2 ft gap between the building's east face and the east lot line, then round the north end into the court. That meets the 9 ft minimum (33.266.txt:319), but only just.
- Depth by midpoint is 111 ft, under 160, so the Map 120-2 frontage rule does not apply.
- If the lot is in the Eastern Pattern Area, the rear setback is 27.75 ft and the court is about 35% of it, under the 50% cap. Passes either way.
- Minimum density is the ruled flag.

## 4. 1S1E07DC  -02900 (R10, 5020 SW Bancroft) RIGHT
- Corner lot. The front is the diagonal SW Shattuck line (99 ft, the shortest); Bancroft is the side street (168 ft).
- pod80 spare 14.5 ft. Building is 20.1 ft from the front (20 ft required).
- The drawn court sticks 11.8 ft past the side-street building line, but there is room to shift it (40 ft). Side-street 20% cap: about 750 of about 930 sf. Passes.
- Coverage 24.6% max. No FAR rule (lot over 10,000 sf).

## 5. 1S2E16DB  -06700 (CM3, 9302 SE Ramona) RIGHT
- Vacant lot, sold for $800k in 2022. 62x124 ft, all neighbours CM3. The envelope is the whole lot.
- pod56 is 0.1 ft from Ramona, so the 10 ft maximum setback is met (33.130.txt:959). The lane runs on the east side.
- Spare is 15.5 ft, so the ground-floor dwelling 5 ft setback option (33.130.txt:1436-1440), or a raised floor (1445-1451), is available.
- FAR 0.53 vs 3. Height 26 vs 65. Landscaped 42% vs 15%. Fire route 97 ft.
- Minimum density is 1 per 1,000 sf (33.130.txt:624-625), about 7 units: the ruled flag.
- pod80 shows green at -0.5 ft spare (tight). That does not matter, because pod56 carries the lot.

## 6. 1S1E18BA  -00300 (R10, 4626 SW 55th Pl) RIGHT
- 82 ft front x 123 ft deep, 10,100 sf, so no FAR rule (33.110.txt:496).
- pod56 spare 3.5 ft. Building is 20.2 ft from the front (20 ft required). Fire route 136.9 ft. Coverage 29.85% max.

## 7. 1N2E26AC  -01700 (R7, 13315 NE Sacramento) RIGHT
- Interior lot. The CI1 parcel at the rear (2900 NE 132nd) is a neighbour, not this lot.
- pod56 spare 5.5 ft. Building is 15.8 ft from the street (15 ft required). Everything else passes with room.

## 8. 1S1E21DC  -13600 (R5, 1263 SW Carson) RIGHT
- 100x100 ft. geo2 marks the west edge "OPEN", but the picture shows a parcel there (labelled R5 SW CARSON ST), so this is an interior lot. corner_lot is false.
- pod56 spare 2.5 ft; pod80 spare 4.0 ft. pod56 building is 10.0 ft from Carson (10 ft required) and 5.1 ft from the west side (5 ft required). Lane 5.1 ft.
- Coverage 2,017 sf vs 2,250 + 0.15 x 5,000 = 3,000 sf (33.110.txt:780). FAR 4,032 vs 8,000.
- Outdoor area: a 21 ft strip on the north side is free. Minimum units 2, met. Fire route 105 ft.

## 9. 1S2E17AA  -00301 (R2.5, 7933 SE Schiller) RIGHT
- 84x129 ft. Both designs fit. pod56 is 10.4 ft from the street.
- The large OS parcel to the north is not this lot. FAR (1.0), coverage and height (35) all pass easily.

## 10. 1S2E11DB  -03505 (R5, 3936 SE 136th) RIGHT, with a layout note
- Streets: SE 136th on the west (edge 2, 75 ft) and a stub street on the north (edges 3-13, about 93 ft plus the curve). The rounded corner and the matching rounded corner on 3928 show it is a street.
- By 33.910.definitions.txt:754-755, the front is 136th (shorter) and the north stub is the side street. The screen's fit uses front_deg 89.85 (the north line).
- pod56 spare 9 ft. Fire route 148.6 vs 150 ft (1.4 ft spare). Coverage 24.5% vs 33.2%.
- As drawn: the building is in the east half (62 ft from 136th) and the court (2,404 sf) is in the west half, 19.4 ft from 136th, between the building and 136th. That fails 33.266.txt:282-290 (the court is not "behind the front and side street building lines"). If the north line is taken as the front instead, the court is in the side-street yard: about 2,400 of the 62 x 75 = 4,670 sf, which breaks the 20% cap.
- Alternative layout: building on the 136th side (10 ft setback; 56 ft across 75 - 10 - 5 = 60 ft), court behind it to the east (110 ft depth leaves about 64 ft), entered from the north stub. The hose route gets shorter. This fits by-right, so the lot is GREEN.
- Pattern: the drawn layout is not tested against 33.266.120.C.1.a, and front_yard_vehicle_share is not in this lot's margins.
- Unchecked FAR: 4,032 vs 0.8 x 8,225 = 6,580. Passes.

## 11. 1N1E24BC  -08200 (R5, 2425-2435 NE Wygant) RIGHT
- NE 25th on the east is the front (60 ft); Wygant on the south is the side street (100 ft); a 10 ft alley on the west. 6,000 sf.
- pod56 spare 0.5 ft (tight). The court touches the alley, so 33.266.txt:313 is met.
- Building 10.0 ft and court 10.3 ft from Wygant, so the court is behind the side-street building line.
- Coverage 33.6% vs 40%. FAR 4,032 vs 4,800.
- Policy: the address range suggests an existing duplex or multi-unit house.

## 12. 1N2E32DD  -11000 (CM2, 247 SE 82nd) RIGHT, with a layout note
- 28,195 sf. Three streets: 82nd (east), Pine (south), Ash (north). Frontage 487 ft. Both designs have more than 100 ft spare.
- Assessor: COM, prop 201, built 1959, 3,904 sf building, land $578k, total $1.30M, assessed $0, sale price $0. Quadfit had it red (existing_commercial).
- The DB holds no owner data and web searches found nothing. Prop 201 is a commercial code, not a public x0 code, and the lot has a real address, so READING_PROTOCOL.md:34-35 says screen it normally. Existing building, so the policy column applies.
- As drawn, pod56 is rotated 33 degrees, 37.3 ft from 82nd, and touches Ash only at one corner. 82nd is the highest transit class street, so 33.130.txt:959-975 requires 50% of the 82nd facade within 10 ft. The drawing fails that, but a corner placement at 82nd and Ash plainly fits (40 ft room in every direction, envelope is the whole lot). pod80 is drawn at 178 degrees.
- Pattern: maximum setback appears to be tested against one street only, not the highest-transit street.
- Minimum density is 28,195/1,450 = 19 units against 4: the ruled flag.
- Slope max 20.6%, p85 6.8%. Fine.

## 13. 1N2E24CD  -09200 (RM1, 3517-3525 NE 147th) CANT_TELL, item 68
- The front is the NE 148th side (east line). 9,537 sf, depth 126.78 ft, not a corner, in East Portland, so very likely in the Eastern Pattern Area. The map is not held (KNOWN-68).
- If the lot is in the area: rear setback is 0.25 x 126.78 = 31.7 ft, so the setback area is about 2,375 sf. The drawn court covers about 1,295 sf of it (54.5%), over the 50% cap (33.120.txt:1000-1002). Fixing that needs the court to shift about 2.3 ft forward, but the building's NE corner already touches the front envelope, so I cannot see a compliant rearrangement.
- Maximum setback is met (building 12-19 ft from the front, 20 ft allowed). Depth is under 160 ft, so the Map 120-2 frontage rule does not apply.
- Missing fact: whether the site is in the Eastern Pattern Area (33.120.220.B.2 map). If it is, it likely falls YELLOW/RED; if not, it is RIGHT.

## 14. 1N1E22DC  -04300 (R2.5, 3940-3958 N Haight) RIGHT
- 100 x 150 ft, 15,008 sf. N Haight on the west (front); 16 ft alley on the east (alley_at_rear true).
- Both designs fit with 76-88 ft spare. Building and court are both at 10.1-10.2 ft from Haight; the court is beside the building, not in front of it.
- No lane is drawn. The alley rule (33.266.txt:313) needs the drive from the alley. The court is 33.8 ft from the alley across open lot, so a 9 ft drive fits.
- Coverage 13.4% vs 25%. Fire route 106 ft.
- Policy: prop 711 multi-family, building value $242k (quadfit existing_multifamily).

## 15. 1S2E06AC  -13200 (R5, 5532 SE Taylor) RIGHT
- 50 x 158.7 ft, 7,937 sf. pod80 green at 0.0 ft spare (FIT-TIGHT flag). The lane runs along the east side.
- Fire route 146 vs 150 ft. FAR 4,032 vs 6,350.
- Ordinary 1893 house; policy column blank.

## Patterns
1. The drawn layout is not tested against 33.266.120.C.1.a (no vehicle area between the building and the street) or the 20% side-street cap (C.1.b). Lot 10's drawing breaks C.1.a, though a legal layout exists.
2. The CM maximum setback looks tested against one street, not the highest-transit street (lot 12's drawing is 37 ft off 82nd).
3. No lane is drawn on several lots (3, 8 pod80, 10, 14) where the drive must squeeze past the building or reach an alley. All happened to have room.
4. The Eastern Pattern Area rear-setback vehicle cap is unheld (lot 13, item 68).
