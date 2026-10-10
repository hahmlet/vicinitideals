# A2 notes (13 Portland GREEN lots). Result: 12 RIGHT, 0 WRONG, 1 CANT_TELL

Limits of this read: the production DB read was denied by the auto-mode gate, so no DB-only facts (tenancy, owner, Map 120-3 / Map 120-2 membership, transit-street class) were available. Everything below is from the dossier JSON, the pictures, and the stored Portland text in flats/provenance/docs/or/multnomah/portland/ (33.110, 33.120, 33.130, 33.266). Pod floor area used for FAR: 56x36 x 2 storeys = 4,032 sf.

Code quotes used by several lots
- Fourplex by right in R20-R2.5: 33.110.txt:1534 "Triplexes and fourplexes that meet the following standards are allowed in the R20 through R2.5 zones." Min lot area Table 110-7 (33.110.txt:1547): R7 4,200, R5 3,000, R2.5 1,500 sf. Also 33.110.txt:1536 maintained-street frontage prohibition (not encoded; every lot here fronts a built public street, so no issue seen).
- FAR, 4 or more units (33.110.txt:441, right-aligned columns): R7 0.7, R5 0.8, R2.5 1.0. Even if the columns were shifted one place the lots below still pass.
- Coverage Table 110-5 (33.110.txt:~785): 5,000-20,000 sf lot = 2,250 sf + 15% over 5,000.
- Alley mandate 33.266.txt:313 "If the lot abuts an alley, all parking and vehicle access to the site must be from the alley." Side-street paving cap 33.266.txt:~293 "on corner lots, no more than 20 percent of the land area between the side street lot line and the side street building line may be paved". Behind-the-building-line allowance 33.266.txt:~284-289.
- Commercial/mixed use: 33.130.207 min density (33.130.txt:494, Table 130-2 line 624: CM2 1 per 1,450 sf, CM3 1 per 1,000 sf). Max building setback 33.130.215.C (Table 130-2 line 651). Small housing types 33.130.250 (garage/entrance rules are about street-facing garages; the pod's court is at the rear, nothing binds).
- Multi-dwelling: 33.120.txt:998 Eastern Pattern Area rear setback = 25% of site depth (exempt: corner lots, lots up to 100 ft deep, or 10% common area of 30 ft); 33.120.txt:480 site frontage 90 ft if deeper than 160 ft (Map 120-2 only).
- Min density flag: Steph 2026-10-02, a min-density miss is only a DENSITY-MIN flag (green). All CM/RM lots below carry it and stay green by that ruling.

## 1N1E13CA  -11800 (R5, 6206 NE 30th Ave)  RIGHT
1 Use: fourplex by right, R5. 2 Lot: 12,486 sf, 124.9 x 100; Table 110-7 min 3,000. 3 Building: FAR 4,032 vs 0.8 x 12,486 = 9,989; coverage 16.1% vs 27.0%; height 26 vs 30 (R5 cap sits in the 22-30 band, 4 ft room). 4 Parking: alley at rear (14 ft, alley_at_rear); 4 stalls charged, 8 seated; hose 110 ft. 5 Geometry: viewed, building and court well inside envelope, slack 49.5 ft. 6 Land: max 20.77% in a 1 m cell, p85 8.2%, steep sqft 0. 7 Who: SFR 101, $1.0M, 1909 house (ignored by design). 8 Unchecked (far, density, lot width etc.): none binds, FAR passes above. 9 Flags: none.

## 1S2E10CC  -05100 (R5, 10520 SE Boise)  RIGHT
Lot 7,638 sf, 61 x 125, interior lot, no alley. FAR 4,032 vs 6,110. Coverage 2,016/7,638 = 26.4% vs 34.64% (2,250 + 15% x 2,638 = 2,646 sf cap). Fit slack 7.5 ft (depth 109.5 vs 102 needed); lane drawn along the side to the rear court. Hose 105 ft. Slope 8.6%. Picture shows building at rear of the lot, no collision with neighbours. SFR 1951, 1,775 sf (ignored). Nothing found.

## 1S2E14BC  -10000 (CM2, 5410 SE 122nd Ave)  RIGHT
CM2 lot 12,598 sf, 75 x 168, on a civic corridor. Household Living allowed in CM2. FAR 0.32 vs 2.5, height 26 vs 45, landscaped 66% vs 15%, coverage 16% vs 85%, parking cap 5 vs 4 stalls (33.266.115 Table: 1.35 per unit max, so 5 stalls cap). Fit slack 70.5 ft. Min density 12,598/1,450 = 8.7, so 9 units vs 4: DENSITY-MIN flag only (Steph). POLICY: operating building ignored: assessor COM 201, 2,040 sf, built 2021 (small, a kiosk or shop); pod placement vs it unknown. 10 ft L3 buffer to residential does not arise (abuts nonresidential zone).

## 1S2E10AD  -11700 (R5, 3247 SE 118th Ave)  RIGHT
14,604 sf, 100 x 146, flat (5%). FAR 4,032 vs 11,683; coverage 13.8% vs 25.3%; fit slack 48.5 ft; hose 90 ft; 8 stalls seated. Picture: pod, court and lane inside the envelope. Neighbour parcel "3247 WI/ SE 118th" to the west is a separate R5 lot, not a street. SFR 1930 3,484 sf (ignored). Nothing found.

## 1S2E02BB  -01100 (CE, 700 SE 122nd Ave)  CANT_TELL
Lot 289,997 sf (6.66 ac), 670 x 652, corner, civic corridor, abuts nonresidential zone. Assessor COM 201, land $2.87M, total $5.03M, building 75,050 sf built 1962, sold $5.835M in 2020. Quadfit had it red as existing_commercial (policy_exclusion). FLATS ignores existing buildings by design, so this alone is not wrong.
Every CE standard FLATS holds passes: FAR 0.014 vs 2.5, height 26 vs 45, coverage 0.7% vs 75%, landscaped 98.8% vs 15%, parking cap 5 vs 4. Pod is dropped in the lot corner, probably on parking.
The deciding fact is whether the building is a multi-tenant retail centre (KNOWN-47: Steph 2026-10-06, malls and shopping centres RED). Not in the dossier; DB read denied. Likely falls toward shopping centre (1962 date, 11% site coverage, arterial corridor frontage), but I cannot confirm. If it is, WRONG KNOWN-47; if not, RIGHT with POLICY: operating building ignored. Side note only: 33.130.215.C counts the facades of all buildings combined toward the 50% max-setback share (civic corridor 20 ft), so an existing set-back centre would also make a new pod's setback compliance depend on the whole site; FLATS does not model that.
An ALERTS line was written as RED before the coordinator's note and a NOTE line follows it downgrading to CANT_TELL.

## 1S2E12AA  -05100 (R7, 2708 SE 159th Ave)  RIGHT
7,932 sf at a cul-de-sac bulb, frontage 41.7 but lot width 82.4 (quadfit once red with siteplan_no_layout). Fourplex by right (R7 min 4,200). FAR 4,032 vs 0.7 x 7,932 = 5,552. Coverage 25.4% vs 33.9%. Fit 76.5 vs 74 needed: slack 2.5 ft, over the 1 ft red line. Picture: building at the bulb side, court to the east, lane joins the lot edge at the street. Rear abuts RM1 land (no step-down in single-dwelling code for that). Thin margin; any extra geometry (curb, setback measured to the arc) of 2.5 ft would flip it, noted but not a finding.

## 1N1E13CC  -16600 (R2.5, 5734 NE 27th Ave)  RIGHT
9,990 sf corner lot (27th / Jarrett), 14 ft alley on the east, alley_at_rear. 33.266.txt:313 requires access from the alley; the screen took side_street False and the court sits 25 ft inside the alley edge with a free strip for the apron. FAR 4,032 vs 9,990 cap; height 26 vs 35; coverage 20.2% vs 30.0%; fit slack 24.5 ft. Max slope 20.75% (1 m cell), mean 6.2%, steep 0 sf. R2.5 attached houses up to eight allowed; fourplex fine. SFR 1911 (ignored). Nothing found.

## 1S2E08CA  -17400 (R5, 6930 SE Rhone St)  RIGHT
6,699 sf corner lot, 13 ft alley. FAR 4,032 vs 5,359 (0.60 vs 0.8). Coverage cap 2,250 + 15% x 1,699 = 2,505 sf vs pod 2,016 (30.1% vs 37.4%). Fit slack 3.5 ft (89.5 vs 86). Picture: pod at the north edge, court to the alley end, no collision. Thin but passes. The 80x25 pod is red here, 56x36 is the green design.

## 1N1E22CD  -19100 (CM3, 3625 WI/ N Mississippi)  RIGHT
10,368 sf, 104.5 x 100, 15 ft alley at rear, civic corridor; slope max 18.3% (1 m cell). FAR 0.39 vs 3.0; height 26 vs 65; coverage 19.4% vs 85%; landscaped 72.6% vs 15%; fit slack 35.5 ft; hose 84 ft. Min density 1 per 1,000 sf = 11 units vs 4: DENSITY-MIN flag only. Picture: building on the street edge (within the 10 / 20 ft max setback), court behind; no lane drawn to the alley but the alley is the aisle by Steph ruling. POLICY: operating building ignored: COM 201, 7,925 sf, built 1960, land $1.66M (on a 10,368 sf lot, so the pod almost certainly overlaps its parking or footprint; not confirmed; not a mall as far as the data says).

## 1S2E17BB  -19200 (CM2, 4708 SE 65th Ave)  RIGHT
3,995 sf, 40 x 100, 10 ft alley. Pod 36 ft deep on a 40 ft frontage with 10 ft fit slack. FAR 1.01 vs 2.5; coverage 50.5% vs 85%; landscaped 24.3% vs 15% (9.3 pt room); height 26 vs 45; 4 stalls seated and charged (no spare). Min density 43.6 vs 30.0 du/ac passes (3 units needed). SFR 1050 sf (ignored). Nothing found. Thin: landscaped share and stall count have little room.

## 1N2E36CC  -02700 (RM3, 105 SE 146th Ave)  RIGHT
11,627 sf, 75 x 155, one street, not a corner. RM3: FAR 0.35 vs 2.0, height 26 vs 65, coverage 17.3% vs 85%, landscaped 61% vs 15%, outdoor 7,103 vs 144 sf. Table 120-3 min width 33 and min area 4,000: passes. Eastern Pattern rear setback (33.120.txt:998, Map 120-3 not available to me, lot is east of I-205 so probably inside): 25% x 155 = 38.8 ft; building is about 88 ft from the rear line, court reaches 20 ft into the strip = about 33% of it (limit 50% vehicle). Not a miss. Max building setback: building is at the street edge. Min density 11,627/1,000 = 11.6 so 12 units vs 4: flag only. Existing SFR 1956 (ignored).

## 1S2E08AD  -08300 (R2.5, 3104 SE 78th Ave)  RIGHT
7,501 sf corner lot (78th west, Tibbetts north), no alley. Entrance on the side street per Steph ruling. 33.266.120.C.1: the court's stalls are behind the building's north wall line; the driveway across the side-street strip (about 11 ft deep x 100 ft wide = 1,100 sf) is about 120-220 sf at most, under the 20% cap. FAR 4,032 vs 7,501; coverage 26.9% vs 35.0%; height 26 vs 35; fit slack 10.5 ft; hose 80 ft. Slope 7.8%. SFR 1943 (ignored). Nothing found.

## 1N2E21AC  -02300 (RM1, 9403-9433 NE Prescott)  RIGHT
40,101 sf, 114 x 350. Site over 160 ft deep so 33.120.206 needs 90 ft of frontage on Map 120-2 sites; it has 113.9. Eastern Pattern rear setback = 25% x 350 = 87.5 ft (33.120.txt:998); pod is at the street end, 252 ft of fit slack, not affected. FAR 0.10 vs 1.0; coverage 5% vs 50%; landscaped 89% vs 30%; height 26 vs 35 (RM1). Min density 1 per 2,500 sf = 16 units vs 4: flag only; 33.120.213.B.1 reduces the minimum by 2 when adding to a site with residential units, not modelled (conservative). POLICY: operating building ignored: MFR 701, 8,312 sf, built 1992, total $3.39M, four street numbers; the picture has the pod near the street end, which is probably the existing complex's frontage or parking; not confirmed.

## Patterns
- Min density: on every large CM/RM lot (10000, 19100, 02700, 02300) the 4-unit pod misses the code minimum by a wide margin. All stay green only through Steph's 2026-10-02 flag ruling.
- Eastern Pattern Area rear setback (25% of depth, RM1-RM4) and the 90 ft frontage rule are still unencoded (see portland.yaml 33.120.220 and 33.120.206 notes); neither changed an answer here, but a deep RM lot with the pod placed at the rear could be a false GREEN.
- R-zone FAR (0.7 / 0.8 / 1.0 for 4+ units) is listed as unchecked on R zones; it passes on all seven R lots (tightest is 17400 at 0.60 vs 0.8).
- Three lots clear the 1 ft fit-miss line by less than 4 ft (05100 R7 2.5 ft, 17400 3.5 ft, 05100 R5 7.5 ft): any change in how the front line or curb is measured could turn them red.
