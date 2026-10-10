# A1 notes (Portland, 13 GREEN lots)

Method: dossier fields (checks.margins, unchecked, flags, drawing, facts) plus pictures, read against the stored code in flats/provenance/docs/or/multnomah/portland/ (33.110, 33.120, 33.130, 33.266, 33.910). Line numbers cite those originals.
Limits: the production DB read was denied by the permission system and not retried. So street class, maintained-street status and overlay or map facts (Map 120-2, Map 120-3, 33.430 environmental overlays) could not be checked. 33.430 and 33.410 are not in the stored provenance.

## Cross-lot evidence (applies to every lot)
- USE: Table 120-2 (33.120.txt:394-420) says a fourplex is Yes in RM1; the R5/R7 single-dwelling chapter 33.110 allows it by right post-HB 2138; CM1 allows multi-dwelling under 33.130.
- Maintained-street gate (33.110.265.E and the 33.120 equivalent): a fourplex is prohibited on a lot with no frontage on a maintained street. Unencoded and unmeasured, treated as permissive (portland.yaml ~25-50). Not checkable here without the DB. Pattern, not a per-lot finding.
- Environmental overlays (33.430) neither stored nor screened. Same status.
- Parking 33.266.120 (33.266.txt:268-349) read; four stalls in a rear court is within the stall and aisle numbers the screen holds.

## 1. 1S1E30DA  -01000 (RM1, 9920 SW 48th Ave) RIGHT
- 25,904 sf, frontage 149.5 ft. SFR 1936, 1,412 sf, land $576.8k.
- Slope max 31% in places; the pod sits on the part that passes. pod56 green, fit [201,102,99]. Fire route 108.6 ft (<=150).
- Flag: DENSITY-MIN, below the line of 3 (standing ruling, not a false green).
- 33.120.txt:549-551 / 1083-1145 max front setback 20 ft on a transit street: deliberately not encoded; slack of 99 ft means the pod can be pulled forward, so it does not change the colour.
- 33.120.txt:1260-1262 building length 100 ft within 30 ft of a street; pod 56 or 80 ft is below it.
- Corner flag possibly missed on a diagonal edge; harmless at this slack.

## 2. 1S2E08BC  -17300 (R5, 3327 SE 64th) RIGHT
- 9,911 sf, 100 x 99 ft. pod56 fit [84.5,82,2.5], pod80 slack 3.5. Open space shape 32 vs 12. Quadfit also green.
- Tight but a pass: 2.5 ft slack is above the zero line. The 1-ft red rule is for a miss, not a thin pass.

## 3. 1N2E34BA  -07600 (R7, 1140 NE 107th Pl) RIGHT
- 10,907 sf, 100 x 109. SFR 1959, 2,792 sf, ignored by design. pod56 slack 6.5, pod80 8.5.

## 4. 1N2E27DD  -11200 (R7, 1950 NE 118th Ave) RIGHT
- 12,931 sf. SFR 1952, 2,208 sf, ignored. pod56 slack 33, pod80 4.0.

## 5. 1N1E35DC  -06700 (CM1, 1725 SE Ash St) RIGHT
- 10,009 sf, corner lot, frontage 200. Assessor COM 201, 3,871 sf, built 1955, land $950k, total $1.43M.
- POLICY: operating building ignored. Single small commercial building, not a multi-tenant retail centre or mall, so not KNOWN-47. The picture shows the pod at the south-east corner of the lot; I cannot tell whether that is the building's parking or yard.
- pod56 slack 20.5, pod80 31.5. Fire 68.7 ft. Neighbours R2.5 and CM1/CM2.

## 6. 1S3E07BB  -02300 (R7, 16510 SE Woodward) RIGHT
- 9,555 sf, 75 x 127.5. pod56 fit [107,102,5]. Outdoor-area shape exactly at its 12 ft minimum (slack 0), a pass. Existing house ignored.

## 7. 1N1E08DD  -13200 (R5, 7734 N Fowler) RIGHT
- 11,362 sf, 75 x 151.5, alley at rear. 2016 house, total $1.235M, ignored by design. pod56 slack 77, pod80 33. No lane drawn, since alley access is assumed; a drive across the open rear yard is feasible.

## 8. 1S2E15BB  -01600 (R5, 4525 SE 105th) RIGHT
- 8,109 sf, 60 x 135. pod56 slack 17.5. Existing house ignored.

## 9. 1N2E35BB  -00100 (CM1, 12520 NE Halsey) RIGHT
- 7,355 sf, corner lot. Assessor COM 201, 1,118 sf, built 1956, land $434k.
- POLICY: operating building ignored. Small single building, not a multi-tenant centre. The picture shows the pod at the north end of the lot and the court to the south of it; pod-versus-parking not determinable.
- pod56 slack 17, pod80 red. Max-density note [1] applies to CR only, so CM1 has none. Neighbours CM1, R7, RM1.

## 10. 1N2E28CC  -08500 (R5, 8443 NE Hancock) RIGHT
- 7,895 sf, 79 x 100. pod56 fit [84.5,82,2.5], pod80 4.5. Coverage 25.5% vs 34% cap.
- Picture: pod at the south front, lane on the west side, court at the rear.

## 11. 1N2E28CD  -08600 (R5, 9024 NE Schuyler) RIGHT
- 8,823 sf, 68 x 131. pod56 fit [106,102,4], pod80 red. Open space [12,12,0].
- The older quadfit screen says red (siteplan_no_layout). Stored code gives no failing number; the difference is a method difference, not a code finding. Thin slack: worth a second look if the margin rules change.

## 12. 1N2E21AD  -06200 (RM1, 9805 NE Wygant) CANT_TELL
- 9,999 sf, 50 ft frontage x 200 ft deep. pod56 red, pod80 green, fit [184,126,58]. Min-density margin 0.002.
- 33.120.206 (33.120.txt:480-500) sets a minimum site frontage on the sites mapped on Map 120-2; the map is not held (portland.yaml:724). A 50 ft frontage against 90 ft would fail, and 200 ft deep is the shape the rule targets. Neighbours are all RM1.
- 33.120.220.C.2 / Map 120-3 (33.120.txt:998-1010): Eastern Pattern Area rear setback is 25% of site depth, unencoded. Drawn layout appears to comply anyway.
- Missing fact: whether the lot is on Map 120-2 and Map 120-3. Likely falls RED if it is on Map 120-2.

## 13. 1S2E12DB  -09500 (R5, 15448 SE Powell) RIGHT
- 24,324 sf. Edge analysis shows a through lot between SE Powell and Rhone Ct, though flagged corner and civic corridor. pod56 slack 126, pod80 129.5. Large slack, so the flag does not change the colour.

## Patterns
1. Maintained-street prohibition is unmeasured for every R-zone green.
2. Map 120-2 frontage and Map 120-3 rear setback are unencoded RM1 standards (lot 12 is the exact trigger shape).
3. 33.430 environmental overlays not screened.
4. corner_lot flag unreliable (lot 13 through lot tagged corner; lot 1 likely missed). Harmless at those slacks.
5. Thin passes at 2.5 to 4 ft on lots 2, 10, 11.
