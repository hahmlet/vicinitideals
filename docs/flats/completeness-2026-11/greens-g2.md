# Green check g2 (FOLLOWUPS 217/222; API-credit worker, Opus 5.5, run 134, seed 68, 2026-11-27)

Raw worker report, unverified. Lot reports were dumped read-only from 114 (data/flats/credit/greens/, this PC only).

## greens-g2: 11 Portland GREEN lots checked against the code (run 134)

**Result:** I found no WRONG lots. Six lots are RIGHT and five are CAN'T TELL. All five CAN'T TELL lots are corner lots, and they share one gap: the screen does not check one corner-lot parking rule, and the report does not include the drawn plan that would settle it. The only exception was 1S2E17BB-07000, where the lot's shape forces a layout that passes.

I edited nothing. Everything below is evidence plus questions for you; none of it is a ruling.

### The gap shared by the corner lots
- **The rule, PCC 33.266.120.C.1.a** (`flats/provenance/docs/or/multnomah/portland/33.266/33.266.120.txt#L13`): "Vehicle area is prohibited between the primary structure and the street except as follows." The only exceptions are at #L17–L18: "Parking spaces located entirely behind the front and side street building lines of a primary structure are allowed" (and driveways to them).
- **Why it reaches across the whole lot:** a "building line" runs the full width of the lot. It is "A line running parallel to a lot line, that is the same distance from the lot line as the closest portion of a building on the site" (`33.910/33.910.030.txt#L61`). So any stall or aisle that sits closer to the side street than the building does breaks the rule.
- **This applies in every zone**, because the section is tested on the building type, not the zone (`33.266.120.txt#L4`; `portland.yaml#L2196-L2202`).
- **The screen does not check it.** `portland.yaml#L2391-L2393`: "the site plan does not yet clip the court to the side-street building line on a corner lot (FOLLOWUPS 5)". The site plan only keeps the *side* court off the street-facing side (`Lot Analysis/quadfit/s6s_siteplan.py#L1736-L1745`). The rear court starts behind the building's rear wall and is not clipped (`#L1822`), and the "least exposed to a street" ordering is a tie-break, not a rule. I grepped `s6s_siteplan.py`, `flats/score/paper.py` and `flats/ingest/quadfit.py` for "building line": the only hits are docstrings or comments; none of them clips the court.
- **The missing fact:** for each corner lot, whether the drawn court comes closer to the side street than the building does. That is visible on the lot pages' drawn plans; g2.json has no plan coordinates.

### Per lot

1. **1S2E02CD-06400 (RM1, corner, 83×182, 14,977 sf) — CAN'T TELL.**
   - **Open point:** the corner-court gap above. The 83 ft front can't hold the 80 ft face once the 10 ft street and 5 ft side setbacks come off (68 ft left), so the building must stand along the 182 ft side street. The envelope is 68 ft wide, which leaves room for the building and court to be offset either way.
   - **Checked and fine:**
     - The Eastern Pattern Area rear setback doesn't apply to corner lots (`portland.yaml#L3817-L3825`).
     - The Map 120-2 frontage rule is met on the 182 ft street, which the one-street ruling allows (2026-11-04-pdx-site-frontage-one-street).
     - The 5 seated stalls equal the 1.35-per-unit cap.
     - Entrance: with no transit street, the applicant chooses the frontage (`33.120.231.txt#L11-L17`).
   - The minimum-density shortfall is a flag by Steph's decision (DENSITY-MIN, "a flag, maybe a 2").

2. **1N1E25CB-12400 (R5, interior, 100×99) — RIGHT.**
   - Room across the lot: 80 + 5 + 5 = 90 ft, leaving 10 ft.
   - Maximum floor area for 4 units in R5 is 0.8 (`33.110/33.110.205.txt#L19`). The report lists FAR as unchecked; the building's 4,000 sf on 9,842 sf is 0.41.
   - The existing 3,500 sf house is ignored (2026-10-14-existing-buildings-stay-green).

3. **1N2E22AC-08200 (CE, corner on NE Sandy, 100×151, vacant) — CAN'T TELL.**
   - **(a) An access rule the screen doesn't encode** (PCC 33.130.215.B.1.b, `33.130/33.130.215.txt#L19-L23`):
     > The following minimum setbacks are required from a street lot line on the portion of the site that is across a local service street from an RF through RM2 or RMP zone. The setbacks do not apply in the CR or CM1 zones, or on or within 100 feet of a transit street … Vehicle access is not allowed through the setback unless the local service street facing the residential zone is the only frontage for the site.

     The config says it doesn't check this: `portland.yaml#L6898`, "Refused as well … the screen does not yet say which street line the driveway crosses". This lot has two frontages. Missing facts: which street line the drawn driveway crosses; the zone across the side street; that street's transportation-plan class; and whether the crossing is within 100 ft of Sandy.
   - **(b)** The corner-court gap above.
   - **(c)** The airport overlays (noise 33.470, aircraft landing 33.400) are neither held nor encoded. Grepping `portland.yaml` for "noise", "33.470" and "aircraft" found nothing. The lot is about 3 km from PDX, and I don't know its overlay letters.

4. **1S2E08DB-05200 (R5, corner, 95×100, 8 stalls) — CAN'T TELL.** The corner-court gap above. The envelope is 85 ft wide, so the building has 5 ft of play, and a 72 ft single row of stalls could stand up to 5 ft closer to the side street than the building. Floor area, coverage and setbacks are fine.

5. **1N1E24CD-11900 (R5, interior, 125×100) — RIGHT.** There is plenty of width. Floor area is 0.32 against 0.8, the lot is flat, and there is no alley.

6. **1N1E07BB-14700 (CM1, corner on N Lombard, 90×100, vacant) — CAN'T TELL.**
   - **Open point:** the corner-court gap above.
   - **Checked and fine:**
     - The local-service-street setback in item 3 doesn't apply in CM1 (`33.130.215.txt#L20`).
     - Lombard Subdistrict A only limits commercial uses and floor area (`33.545.txt#L47-L56`).
     - The 33.130.242 transit-street entrance rule only applies to non-residential floor area or "residential use in a multi-dwelling structure" (`33.130/33.130.242.txt#L6`). A fourplex is neither.
   - **Please check:** that the lot is outside Lombard **Subdistrict B** ("community corners"). There, surface parking is not allowed within 40 ft of the corner (`33.545.txt#L39`). That rule is enforced only as a hold on mapped areas; the report shows no hold, but I couldn't test the polygon by hand.

7. **1S1E19BD-04900 (R7, interior, 103×113) — RIGHT.** Depth works with the 15 ft R7 front setback: 15 + 25 + 38 ft of court + 5 = 83 ft of 113. Floor area is 0.34 against 0.7.

8. **1S2E17BB-07000 (R2.5, corner, alley at rear, 81×100, slack 6.67 ft) — RIGHT.**
   - The 81 ft front leaves only 71 ft after setbacks, so the building must stand along the 100 ft side street (10 ft front setback, no rear setback at the alley: 90 ft of room).
   - The applicant may choose which frontage the entrance faces (`33.110/33.110.230.txt#L11`).
   - The 10 ft strip behind the building is too shallow for a court, so the court has to sit on the interior side. That puts it behind both building lines. It is fed from the alley, which 33.266.120.C.3 requires (#L33-L34).

9. **1N1E16CD-01200 (R5, corner, 100×100, 8 stalls) — CAN'T TELL.** The corner-court gap above. The envelope is 90 ft, so the building has 10 ft of play.

10. **1S2E10DA-07800 (RM2, interior, 100×179) — RIGHT.**
    - Map 120-2: 100 ft of frontage on one street is at least 90.
    - Eastern Pattern Area rear setback: 25% of 179 ft is about 45 ft, and the slack is 92 ft.
    - 5 stalls equal the 1.35-per-unit cap.
    - The density shortfall is flagged by Steph's decision.

11. **1N1E07AC-02200 (R5, interior, 100×100) — RIGHT.** Room across the lot is 90 of 100 ft. Floor area is 0.40.

### Things that apply to every lot (no verdict changed)
- **Visitability** (`33.110/33.110.265.txt#L66-L99`, the seven R-zone lots): at least one unit needs an entrance reached with no stairs from the street lot line or a parking space, at a slope no steeper than 1:8, plus a 60-inch bathroom circle. The pod's slab sits 8 in above grade (`flats/config/pods/pod80x25.yaml`). I treated this as covered by ruling 2026-10-14-unchecked-design-details ("the pod can be adapted"). **You should confirm.** Completeness item 2 asks the same question, and the rule is deleted on 2027-01-01.
- **Driveway permits** (PCC Title 17, 17.28.110) are not held (`portland.yaml#L2463-L2468`). That could limit curb cuts on any lot.
- No lot is narrower than 32 ft, in York, or in the unread plan districts (Pleasant Valley, Swan Island, Raceway, Guild's Lake, Cascade Station). No lot is near the river overlays.

### Not done
- I didn't see the drawn plans; their absence is the whole reason for the CAN'T TELLs.
- I didn't run point-in-polygon tests (lot 6 against Lombard Subdistrict B; lot 3 against the airport overlays).
- I didn't read Title 17.

### Table
| tlid | zone | verdict | reason |
|---|---|---|---|
| 1S2E02CD -06400 | RM1 | CAN'T TELL | corner: court vs side-street building line (33.266.120.C.1.a) not checked; plan needed |
| 1N1E25CB -12400 | R5 | RIGHT | width 90/100, floor area 0.41/0.8 |
| 1N2E22AC -08200 | CE | CAN'T TELL | 33.130.215.B.1.b driveway-through-setback not encoded; corner court; airport overlays not held |
| 1S2E08DB -05200 | R5 | CAN'T TELL | corner court vs side-street building line |
| 1N1E24CD -11900 | R5 | RIGHT | wide interior lot, floor area 0.32 |
| 1N1E07BB -14700 | CM1 | CAN'T TELL | corner court; confirm outside Lombard Subdistrict B |
| 1S1E19BD -04900 | R7 | RIGHT | depth 83/113 with 15 ft front, floor area 0.34 |
| 1S2E17BB -07000 | R2.5 | RIGHT | shape forces building along side street and an interior court fed from the alley |
| 1N1E16CD -01200 | R5 | CAN'T TELL | corner court vs side-street building line |
| 1S2E10DA -07800 | RM2 | RIGHT | frontage 100 ≥ 90, rear setback met with 92 ft slack; density flagged by Steph's decision |
| 1N1E07AC -02200 | R5 | RIGHT | width 90/100, floor area 0.40 |

**WRONG cases:** none. No quote-backed failure found.

