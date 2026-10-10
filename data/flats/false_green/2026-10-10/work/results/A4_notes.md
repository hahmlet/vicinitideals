# A4 notes (unincorporated Washington County, R-5 / R-6)

Stored code: flats/provenance/docs/or/washington/_unincorporated/ (abbrev. CDC). Method notes:
- DB read over ssh was denied by the classifier and not retried. Geometry came from work/dossiers.jsonl (lot, neighbours incl. "ROW" polygons, drawn building/court/lane/envelope), and street class from the PUBLIC county TSP layer (gispub.co.washington.or.us LUT_PDS/TSP_Layers MapServer/4, FClass2; local streets are not drawn). "ROW across" = gap from the lot edge to the nearest parcel across the street (ray cast), i.e. the street ROW width. Helper scripts were in /tmp (not kept).
- All 11 lots: SFR (prop_code 101), no flood, inside UGB, no overlay, no split zone, single zone. No substantial operating non-house building, so the coordinator's POLICY note does not apply. sewer main_dist_ft is huge (7,000-27,000 ft) = data coverage artefact, not a finding.

## Common reading (all lots)
1. USE. Pod = Quadplex under Middle Housing (CDC 106-173, 430-84.3). By right (Type I) in R-5 via 302-2.14 (cdc.302.r-5.txt:86-111) and R-6 via 303-2.14 (cdc.303.r-6.txt:86-108): A. <= 16,500 sf (R-6: 13,100) buildable area, or B. more than that and the units meet min density (R-5 four u/ac, R-6 five u/ac); AND C. on a public street, existing ROW must reach 25 ft (local) / 30 (Neighborhood Route) / 37 (Collector) / 45 (Arterial) to centerline "or the applicant proposes to dedicate"; "If road improvements built to ultimate County standard exist, no additional right-of-way is required." Dedication is recorded before the first building permit (C(2)). Type II (discretionary) otherwise (302-3.15 / 303-3.20), which would be RED.
2. LOT. Quadplex min lot 7,000 sf, "based on lot size prior to any right-of-way dedications" (cdc.302.r-5.txt:340-344); no frontage minimum in the table. All 11 lots >= 7,802 sf. Density B tests pass wherever area exceeds 16,500/13,100 (lots 2 and 4).
3. BUILDING. 302-7.1 Quadplex: front 15, street side 8, side 5, rear 15, separation 6, height 35 (pod 26). Dedication moves the line the yards are measured from; setbacks are not relaxed for new buildings (501 C, cdc.501.public-facilities.txt:~866, covers EXISTING structures only).
4. PARKING/ACCESS. 430-84.3 B(4) (cdc.430-84.middle-housing.txt:219-247): total approaches <= 32 ft; two-frontage Quad lots on local/NR only: 32 ft on one frontage or 16 ft each; Collector/Arterial-only two-frontage lots must meet 501-8.5 B. 501-8.5 preamble (cdc.501...:~872-877): "For Middle Housing, access spacing requirements Section 501 apply only to Triplexes, Quadplexes and Townhouses, and only in specific circumstances described in 430-84.3 B (4)". 413-4.8 parking grade <= 5% (cdc.413.parking.txt:174): all green courts 0.3-4.25%.
8. UNCHECKED list (same on every lot: frontage, width, depth, coverage, FAR, stories, density, ...): checked the code; no table standard in 302-7.1 / 303-7.1 for a Quadplex carries a frontage, width, depth or coverage number that these lots fail. The one that matters is the ROW-dedication gate in 302-2.14 C / 303-2.14 C, which is not among the unchecked names at all; the layer says it is NOT ENCODED (flats/config/jurisdictions/or/washington/_unincorporated.yaml ~L405-520), so no flag or number carries it.
9. FLAGS. ACCESS-STREET-RANK-UNKNOWN is "cleared" on lots 1, 4, 10. FIT-TIGHT is open on lots 6, 8 (pod80 only) and 10.

## 1. 1S103CA02500 (R-5, 11680 SW Lanewood St) RIGHT
Corner, 9,577 sf, frontage 198.8. ROW across both streets about 50 ft (25 to centerline = local minimum, no dedication). Green pod56 slack 16.0 ft; building 15.8 ft from street; court 15.3 ft from the long street edge (parking not subject to the 15 ft building setback in the table). grade 1.6%. Fire route 82.8 ft. No TSP class near. Nothing failing found.

## 2. 1S118DD00500 (R-5, 5520 SW 166th Ave) RIGHT
19,034 sf > 16,500 so 302-2.14 B: 4 units / 0.437 ac = 9.2 u/ac >= 4. ROW 60 ft across (30 to centerline). pod56 slack 97.5, pod80 54. Max slope 23% but the court grade is 1.86% and steep ground is zero in the design. Fire 113 ft.

## 3. 1N133CD08900 (R-5, 13520 NW Milburn St) RIGHT
9,418 sf. ROW across 68.5 ft. Arterial (class 3) centerline 152 ft away, not on the frontage. slack 10.0, grade 0.3%, fire 114 ft.

## 4. 2S109BB00700 (R-6, 14060 SW High Tor Dr) RIGHT
20,914 sf; 303-2.14 B: 4 units / 0.48 ac = 8.3 u/ac >= 5 (cdc.303.r-6.txt:88-92). ROW 50 ft across on both streets (25 = local minimum). Steep ground 3,630 sf (max slope 55%) handled: pod80 is red, pod56 slack 19 ft with building 15.0 ft from the street, court grade 4.17% (<5%). Fire 103 ft.

## 5. 1S118CB08000 (R-5, 5265 SW 182nd Ave) RIGHT
Corner 11,309 sf. TSP Neighborhood Route centerline 24.7 ft from the lot (ROW across 49 ft) so 5.3-5.5 ft dedication under 302-2.14 C(1)(b). pod56 slack 17.5 ft, building 15.5 ft from the NR edge; absorbs it. Side street (Madeline) ROW 50 ft = 25, fine.

## 6. 1S201CC12500 (R-5, 1760 SW 203rd Ave) WRONG (RED)
- Lot 8,489 sf, frontage 70.7 ft (segments 56 + 15 ft). TSP: Neighborhood Route centerline 26.4 ft from the lot edge. 302-2.14 C(1)(b): "Neighborhood route: 30 feet to centerline" (cdc.302.r-5.txt:98 region, lines 94-103). Deficit about 3.6 ft (nearest parcel across, 56.6 ft away, is on Rock Ct and is not a clean measure; even if the half width were 28.3 ft the deficit is 1.7 ft).
- Pod56 slack 0.0 ft, fit bounds -0.5 to +0.5 (FIT-TIGHT open). Drawn building is 14.9 ft from the street segments (envelope boundary is 14.9), court 0.3 ft from the lot line, room 0 on all sides. Moving the front line in 1.7-3.6 ft removes depth the pod does not have: fit miss >= 1 ft = RED by the standing ruling.
- Possible way out: "If road improvements built to ultimate County standard exist, no additional right-of-way is required" (cdc.302.r-5.txt:~101-103). A 50-57 ft ROW is below the 60 ft the 30-to-centerline rule implies, so improvements to ultimate standard on this street look unlikely, but I could not confirm. If confirmed, the lot is RIGHT with 0.0 slack.
- Access: single frontage; the 70 ft Neighborhood Route frontage rule (501-8.5 B(2)) is not triggered for Middle Housing (preamble limits spacing to the 430-84.3 B(4) cases), and the lot is 70.7 ft anyway.
- Kind: NEW (ROW dedication to centerline not taken out of the fit).

## 7. 1S213DB07700 (R-5, 5340 SW 191st Ct) RIGHT
Corner 10,001 sf. NR centerline 24.0 ft off (ROW ~50) -> ~6 ft dedication on whichever segment is the NR. pod56 slack is only 3.0 but pod80x25 is also green: slack 12.5, building 9.6 ft from the 100 ft side street segment (street-side setback 8) and 15.5 ft from the 98 ft segment (front 15). A 6 ft dedication takes 5-6 ft from either edge; slack 12.5 ft absorbs it and the pod can slide. Other street (Madeline) ROW 55 ft = 27.5, fine. Residual doubt: pod80 slack depends on its angle; still above 6 ft.

## 8. 1S103DA00700 (R-5, 10750 SW Butner Rd) RIGHT (with a flagged alternate reading)
- Single street frontage 87 ft, class 4 Collector (TSP centerline 37.6 ft from the lot edge = already >= 37 ft of 302-2.14 C(1)(c)). Across parcel only 49.8 ft away, which suggests the real half-width may be about 25; dedication then ~12 ft, pod56 slack is 31 ft (building 15.3 ft off the street), absorbed. pod80 slack 0.5 (FIT-TIGHT) is not the chosen green.
- 501-8.5 B(3) (cdc.501.public-facilities.txt: "All commercial, industrial and institutional uses with 150 feet or more of frontage will be permitted direct access to a Collector. Uses with less than 150 feet of frontage shall not be permitted direct access to Collectors") names no residential use, and 501-8.5 B opens "No use will be permitted to have direct access ... except as specified below". A reader who applied that literally would say a residential quad on 87 ft of Collector frontage has no by-right access (only interim access under 501-8.5 E, discretionary). I do NOT think it applies: the 501-8.5 preamble says Section 501 access spacing applies to Middle Housing "only in specific circumstances described in 430-84.3 B (4)", and B(4)(c)(ii) requires MORE THAN ONE frontage ("lots or parcels with more than one street frontage must comply with ... (ii) ... frontages only on collector and/or arterial roads"). Single frontage => B(4)(a) only (32 ft total approach). Ruled RIGHT; coordinator may want Steph to confirm this reading, since a wrong reading would turn every Collector-only single-frontage lot red.
- Grade 1.13%; max slope 22.5% elsewhere on the lot.

## 9. 1S111AB00900 (R-5, 2225 SW Knollcrest Dr) RIGHT
Corner 12,542 sf; vacant (assessor building 0, year_built 0). NR centerline 25.0 ft from the lot; the segment it fits is the 79 ft one (bearing 91, ROW across 49.7 ft => ~5 ft dedication). The other two segments (30 + 63 ft) face ROW 60 ft (30 = enough). On the 79 ft segment the building is 70 ft away, court 19.1 ft, lane 70.8 ft, envelope 8.0 (street side): a 5 ft dedication does not touch the building. Slack 2.0 ft is on a different edge. Steep ground 1,481 sf (max slope 25%) already carved; court grade 4.25% (<5%, margin 0.75). If the NR were the front (60 ft ROW) the TSP centerline distance would be 30, so the measurements agree on the 79 ft side.

## 10. 1N120AD09600 (R-6, 14603 NW Heathman Ln) WRONG (RED)
- Corner 7,802 sf (above the 7,000 Quadplex minimum before dedication, 302-7.1 note cdc.302.r-5.txt:344; R-6 equivalent). No TSP class (local streets). Roads across: 42 ft wide on the 61 ft front segment (14608 Heathman) and 46 ft on the 82 ft side segment (5320 NW 146th Ave). 303-2.14 C(1)(a): "Local street: 25 feet to centerline" (cdc.303.r-6.txt:97). Shortfall 4 ft (front) and 2 ft (side), assuming the centerline sits mid-road.
- Pod56 slack 0.0 ft (FIT-TIGHT open, room 0/0/0). Building 16.5 ft from the front segment (15 ft setback, envelope 15.0) so with the line moved in 4 ft the building needs 19 ft = 2.5 ft short; court is 0.1 ft from a lot line and cannot give. A fit miss >= 1 ft = RED.
- Escape clause (ultimate County standard improvements exist -> no dedication) cannot be tested; a 42 ft ROW is unlikely to carry ultimate-standard improvements. If it does, the lot stays RIGHT with 0.0 slack.
- Kind: NEW (same as lot 6).

## 11. 1S111BD01200 (R-5, 9780 SW Melnore St) RIGHT
15,027 sf; frontage 124.7 ft on a Neighborhood Route (centerline 26.7 ft; ROW across 50 -> ~5 ft dedication). Slack 26.5 (pod56) and 29.0 (pod80); buildings 15.0 ft off the street; courts 15.2 ft / 40.0 ft; grade 0.7%. Frontage >= 70 ft anyway.

## Cross-lot patterns
- ROW dedication to centerline (302-2.14 C / 303-2.14 C) is a by-right gate that the screen does not encode (admitted in _unincorporated.yaml). It only turns a green into a miss when slack is under about 4 ft: 2 of 11 sampled lots (6, 10). Lots 7 and 9 survive only thanks to slack on another edge / another pod.
- Class-based access gates (501-8.5 B) and the 70 ft NR frontage rule are not encoded, but 501-8.5 itself limits them for Middle Housing to the multi-frontage cases in 430-84.3 B(4); not found to bite on any single-frontage lot here (lot 8 is the closest and rests on that reading).
- Parking-grade 5% (413-4.8): not a flagged check but the DEM grades under every green court are 0.3-4.25%, so it passes.
- Street class for local streets cannot be taken from the TSP layer (local streets are not drawn); I used ROW width from the parcel fabric.
