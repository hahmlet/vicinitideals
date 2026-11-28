# Green check g1 (FOLLOWUPS 217/222; API-credit worker, Opus 5.5, run 134, seed 68, 2026-11-27)

Raw worker report, unverified. Lot reports were dumped read-only from 114 (data/flats/credit/greens/, this PC only).

I found no failing standard on any of the 10 GREEN lots, so there are **no WRONG verdicts**. 9 are RIGHT and 1 is CAN'T TELL. All 10 are in Portland, run 134. One code issue cuts across the five lots in R5 and R7 zones (visitability, point A below); it doesn't change any colour, but you should look at it.

| tlid | zone | verdict | one-line reason |
|---|---|---|---|
| 1N1E10CA -06000 | R5 | RIGHT | Corner, 100×100. Floor area is unchecked but can't fail: 4,000 sf building plus the 1,946 sf existing house is 0.59, under the 0.8 cap. Coverage cap is 3,000 sf against the pod's 2,000. The foundation note is 0.2 in *under* the step cap, so the near-cap ruling (which covers misses) doesn't apply. |
| 1S2E15CA -03200 | R7 | RIGHT | 127×344 interior lot. Floor area 0.11 against 0.7; the minimum of 2 units on lots over 14,000 sf is cleared by 4; fire route 112.6 ft is under 150. |
| 1N1E24BD -06400 | RM2 | RIGHT | Corner with a 10 ft rear alley. The alley-only access rule is encoded, and the alley width is trusted by ruling. The Eastern Pattern Area rear setback doesn't apply (corner lot, 100 ft deep). Landscaping 20% is encoded. The minimum-density shortfall is a flag only, by ruling. |
| 1S3E07DB -04500 | R7 | RIGHT | 100×122. My rough coordinate estimate puts it about 1.5 mi north of the Pleasant Valley plan district, which has never been read (completeness item 3). Floor area 0.40. |
| 1S2E03DC -13200 | CM2 | CAN'T TELL | One unencoded vehicle-access rule turns on where the driveway sits, and the report doesn't say. Detail below. |
| 1N1E22AD -16000 | CM3 | RIGHT | 100×100 corner on MLK. The whole site is within 100 ft of MLK, so the across-the-street setback and its vehicle-access bar don't apply ("do not apply … on or within 100 feet of a transit street", `33.130.txt#L801-L802`). The maximum front setback on both streets of a corner is encoded. |
| 1S2E09BC -11600 | RM1 | RIGHT | 100×135 interior. If it is in the Eastern Pattern Area, the 33.75 ft rear setback is encoded, and with 48 ft of slack it fits. Landscaping 30% is encoded. Density is a flag only. |
| 1N2E19AC -07700 | R7 | RIGHT | 114×194. The steep-ground map shows 0 sf of steep area. Floor area 0.22. |
| 1N1E35AD -07100 | RM2 | RIGHT | 100×100 corner, inner pattern area. Landscaping, coverage and floor area are encoded. One caveat on the maximum front setback (point B). |
| 1S2E11DB -07900 | R7 | RIGHT | The tightest lot (8.5 ft slack, 102×100). 15 ft front + 25 ft building + 5 ft rear leaves 55 ft for the court. Coverage cap is 3,024 sf; floor area 0.52 even with the existing house. |

**1S2E03DC -13200 (CM2) in full.** `33.130.txt#L806-L808`: "Vehicle access is not allowed through the setback unless the local service street facing the residential zone is the only frontage for the site." The setback is the one along a local street facing a residential zone across the street (`#L799-L802`). It doesn't apply within 100 ft of a transit street. The config refuses to encode this bar: "the screen does not yet say which street line the driveway crosses" (`portland.yaml#L6176`). This lot is a corner (two frontages), 215 ft deep along its side street, with 136 ft of slack. If the driveway enters from the side street more than 100 ft back from Division, and that street is local with residential zoning across it, the lot fails. To settle it: where the drawn driveway enters, and the zoning across the side street. It is most likely within 100 ft, which would make it RIGHT.

**Things to check:**

- **A. Visitability, affecting the five R5/R7 lots.** `33.110.265.txt#L72-L75`: "at least one dwelling unit on the lot must meet all of the following visitability standards: (1) Visitable entrance. At least one entrance must be accessible via a route that does not have any stairs between it and the street lot line or an on-site parking space. The slope of the route may not exceed 1:8."
  - Nothing in the config encodes this (completeness item 2).
  - On 1N1E10CA the report's own foundation note puts front door 1 at 51.3 in above the ground.
  - It reaches only the apartment form (a fourplex). Each of these lots also shows `"townhomes": "green"`, and attached houses aren't covered by section E. So the colour stands under the `2026-10-15-townhomes-separate-lots` ruling, and I am not calling it wrong.
  - But `"kept": "apartment"` is shown, and that form may fail E.3. Whether the `2026-10-14-unchecked-design-details` ruling covers a ramp is Steph's call.
  - The completeness report says Ordinance 192241 deletes E.3 from 2027-01-01. I did not verify that.
- **B. Maximum front setback in the multi-dwelling zones (RM2 lots 1N1E24BD and 1N1E35AD; possibly RM1 1S2E09BC).** The 20 ft maximum on a transit street or in a Pedestrian District is deliberately not encoded for RM zones (`portland.yaml` RM1 notes; the table is at `33.120.txt#L542-L545`).
  - The pod passes only if it is drawn at or near the 10 ft minimum. With 16.5–21.5 ft of slack it could be drawn further back.
  - The report shows neither where the building sits nor whether these streets are transit streets.
- **C. Lot location.** I could not run a point-in-polygon test (the sandbox blocked Python and PowerShell scripts), so I relied on the screen's own plan-district facts. The Pleasant Valley conclusion for 1S3E07DB is a hand estimate in state-plane feet, roughly ±3,000 ft.

I edited nothing and made no rulings.

