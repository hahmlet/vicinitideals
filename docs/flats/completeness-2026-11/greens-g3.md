# Green check g3 (FOLLOWUPS 217/222; API-credit worker, Opus 5.5, run 134, seed 68, 2026-11-27)

Raw worker report, unverified. Lot reports were dumped read-only from 114 (data/flats/credit/greens/, this PC only).

No lot is WRONG. 8 of the 9 are RIGHT: no standard in the held code fails for this building on these lots. One (Oregon City) is CAN'T TELL. I edited nothing.

`pod80x25@3` is two storeys, not three. `flats/config/pods/pod80x25.yaml#L11-L12` (version 3, "20 ft overall, 9 ft 2 in storeys"), `#L21` (`stories: 2`), `#L25` (`height_ft: 20`). So the floor area is 4,000 sq ft, not 6,000. That makes every floor-area and rear-height check below easier to pass.

## Per lot

**1. 22E09BC02600, 8508 SE Jannsen Rd. Clackamas unincorporated, R10. RIGHT.**
- **Checked:** Table 315-2 coverage 50% (checked; `315/315.04.txt#L1171`). Setbacks 15 front, 20 rear, 5 side (`#L1197,L1206,L1215`). The 7,000 sq ft minimum (`845/845.01.txt#L7`). 845.02 windows, entry, driveways and parking (`845.02.txt#L5-L41`). Slack is 53.5 ft.
- **Not part of the verdict:** Section 1005 and 1009 do not reach middle housing in R-10 (`_unincorporated.yaml#L1993-L2008`).
- **Caveat:** the nearest sewer main is 5,555 ft away (the report says it is in a sewer district). ZDO 1006 (utilities) is not held, so I cannot quote a sewer rule. The open-space and flood rulings of 2026-11-18 are not live yet, and I had no map to test them.

**2. 32E06AD07300, 1201 Leonard St. Oregon City, R-2, corner, existing apartments. CAN'T TELL.**
- **What is missing:** a rear setback for the 4-unit building. `oregon-city.yaml#L2043-L2048` (R-2, 17.12.050.G) reads, quoted: "10 feet; plus 1 additional foot in rear setback for every 3 feet in building height over 35 feet; except for Single family detached, duplexes, townhouses and ADUs". The pod is 20 ft high, so the 10-ft base governs, and nothing in that cell covers a 4-unit building. The completeness report flags this as an undecided Steph item: `docs/flats/completeness-2026-11/oregon-city.md#L35`, "OC R-2: which rear setback applies to a quadplex ...". So the rear distance the screen used is not settled by the text.
- **Checked:** the R-2 standards encoded in the config: min lot 6,000; width 50; depth 70; coverage 85%; front 5 (max 20); side and street side 5; landscaping 15%; height 35. Slack is 56.5 ft.
- **Already ruled or flagged:**
  - The minimum density of 17.4 du/acre fails (4 units = 7.26 du/acre). Steph ruled this a flag (DENSITY-MIN, 2026-10-02).
  - Oregon City's two-driveway rule is overridden by state law (DRIVEWAY-STATE-OVERRIDE, a flag).
  - The existing apartments are covered by the occupied-building ruling.
- **Open question that does not change the answer:** on a corner lot the director picks the rear line (17.04.1000, `oregon-city.md#L29-L33`), which is an open Steph question. The other choice moves the rear yard at most about 5 ft against 56.5 ft of slack.

**3. 1S3E07DA -03400, 18004 SE Marie St. Gresham, LDR-5. RIGHT.**
- **Checked:**
  - Table 4.0130, `4/4.0130.txt`: width 35 (`#L42`), depth 70 (`#L64`), frontage 35 (`#L80`).
  - Row J FAR is 1.0 (`#L107`). It is not encoded, but 4,000 / 19,210 = 0.21.
  - Minimum density 6.22 (`#L21`): 4 units = 9.1 du/acre.
  - Rear roof height limit of 21 ft at the rear setback line (`7.0400...txt#L358-L362`). The pod is 20 ft, and the rule is encoded (`gresham.yaml#L2526`).
- **Can't confirm:** 9.0100 buffers are not held (222 finding). The flag-lot status is assumed, not known.

**4. 1N127BC05600, 12430 NW Woodland Ct. Washington County unincorporated, R-9. RIGHT.**
- **Checked:** 304-7 yards, 35 ft height, 7,000 sq ft lot. The Type I gate: the lot is over 10,000 sq ft, but 4 units on 15,319 sq ft is 11.4 du/acre, which clears the 7 du/acre escape (`cdc.304.r-9.txt#L92-L100`). The standard-plat gate is read from the lot's plat origin (`screen.py#L5025`).
- **Already ruled:** slack is 0.0 under FIT-TIGHT (Steph 2026-09-25).
- **Not held:** 2,579 sq ft of the lot is steeper than 15%. Section 410 (grading and landslide) is not held, so I can't test it.

**5. 1S213DB03501, 19160 SW Madeline St. Washington County unincorporated, R-5, corner. RIGHT.**
- **Checked:** 302-7.1 (`302/302-7.txt#L2-L51`), quoted: front 15 (`#L14`), street side 8 (`#L19`), side 5 (`#L22`), rear 15 (`#L36`), height 35 (`#L46`), and "No minimum" frontage (`#L51`). R-5 has no coverage or width rule for middle housing.
- **Type I gate:** 14,999 sq ft is under 16,500 (`#L44` of `302-2.txt`). Slack is 15 ft.

**6. 1S212BD13100, 19605 SW Jann Ct. Washington County unincorporated, R-5, on a cul-de-sac bulb. RIGHT.**
- **Checked:** the same 302-7.1 standards. The bulb street-width rule (302-7.2 D(4), `#L83`) is for non-middle housing only. Slack is 6 ft.

**7. 1S102CD01000, 1820 SW 96th Ave. Washington County unincorporated, R-5, corner. RIGHT.**
- **Checked:** the same 302-7.1 standards, the corner façade feature (430-84.3 B(3), a design item), and the 32-ft driveway approach total.
- **Already ruled:** slack is -0.5 under FIT-TIGHT.
- **Parking:** no parking is required inside the UGB (413-6.1, `_unincorporated.yaml#L991-L996`).
- **Note:** 0 stalls seated but 4 charged (see the coordinator checks).

**8. 1S127BB00100, 12055 SW Davies Rd. Beaverton, RMC, corner. RIGHT.**
- **Checked:** Table 20.05.15 (`20.05/20.05.15.txt`):
  - Lot 5,000 (`#L16-L18`); front 10, side 5, rear 15 (`#L36-L53`).
  - Quadplex FAR 0.90 (`#L110-L125`): 4,000 / 8,249 = 0.48.
  - Minimum density 7 (`#L26`): 21 du/acre.
  - The 25-ft height plane at the setback lines (pod is 20 ft); open space 500 sq ft.
- **No coverage limit:** no Beaverton zone table has one (`beaverton.md#L50`).
- **Easement:** the 10-ft utility easement is assumed and the building is fitted clear of it.
- **Already ruled:** slack is -0.5 under FIT-TIGHT. 0 stalls are seated, so the EDM 210.21.I parking-lot-driveway rule has nothing to act on.

**9. 1S208DC06800, 3711 SE Palmire Ct. Hillsboro, R-7. RIGHT.**
- **Checked:** Table 12.21.350-1 values in the config: 2½ storeys (pod is 2), coverage 45% (actual 12%), minimum density 5 (actual 10.2), yards 20 front / 5 side / 13 total sides / 20 rear. Slack is 25.5 ft.
- **Stub street:** the 222 finding is 12.50.110 D.4 (`12.50/12.50.110.txt#L35`). It makes a lot at the end of a stub street have no frontage. The lot is not on the bulb, the street ends in a cul-de-sac, and frontage width and depth are lifted for lots of record (`hillsboro.yaml#L978-L983`). So D.4 has nothing to fail.

## Table

| tlid | zone | verdict | one-line reason |
|---|---|---|---|
| 22E09BC02600 | R10 (Clack. uninc.) | RIGHT | Table 315-2 and 845 all pass; slack 53.5; sewer rule (ZDO 1006) not held |
| 32E06AD07300 | R-2 (Oregon City) | CAN'T TELL | Rear setback for a 4-unit building is not settled (`oregon-city.yaml#L2043-L2048`, open item in `oregon-city.md#L35`) |
| 1S3E07DA -03400 | LDR-5 (Gresham) | RIGHT | Width, depth and frontage pass; unencoded FAR 0.21 vs 1.0; 20 ft under the 21-ft rear roof limit |
| 1N127BC05600 | R-9 (Wash. uninc.) | RIGHT | Type I density escape met; slack 0 under FIT-TIGHT; grading (410) not held |
| 1S213DB03501 | R-5 (Wash. uninc.) | RIGHT | 302-7.1 yards pass; slack 15; under the 16,500 sq ft Type I limit |
| 1S212BD13100 | R-5 (Wash. uninc.) | RIGHT | 302-7.1 passes; bulb rule is for non-middle housing only; slack 6 |
| 1S102CD01000 | R-5 (Wash. uninc.) | RIGHT | Slack -0.5 under FIT-TIGHT; no parking required in the UGB |
| 1S127BB00100 | RMC (Beaverton) | RIGHT | FAR 0.48 vs 0.90; density 21 vs 7; slack -0.5 under FIT-TIGHT |
| 1S208DC06800 | R-7 (Hillsboro) | RIGHT | Storeys, coverage and density pass; the stub-street rule does not apply here |

## WRONG cases

None. I found no standard in the held code that one of these lots fails.

## For the coordinator to check

1. **Lots 7 and 8 (1S102CD01000, 1S127BB00100) seat 0 stalls but are GREEN.** By `screen.py#L1538-L1539`, 0 means "not even the floor holds". Both are FIT-TIGHT at -0.5, so the drawn plan misses by half a foot and that is probably why. No held code requires parking there. But the 2026-08-26 ruling ("we want to know what we would have to do if we do parking (which we will)") and the brief's "with its parking" suggest a GREEN with no seated stalls deserves a look. That is a decision for you or Steph, not a code failure.
2. **Washington County 501-8.1 E.** It requires a 9–10 ft pedestrian/utility easement next to Special Area streets (`cdc.501.public-facilities.txt#L555-L562`). We do not hold the Special Area street map, and whether the rule reaches middle housing is the open S question in item 222. Lots 4 (slack 0), 7 (-0.5) and 6 (6) would lose their fit if it applied. I did not count this against them.
3. **Lot 4 run-history inconsistency.** It carried a CLEAR-OBJECTIVE "standard plat" flag on the earlier designs (opened run 80, last seen run 122). The `pod80x25@3` report in run 134 does not carry it. That is consistent with the gate now reading plat origin (`screen.py#L5025`), but it is worth confirming the lot's plat origin was actually read and found "platted".
4. **Not covered** because the text or map is not held: Clackamas open-space and flood maps (rulings not live), ZDO 1006 sewer, Gresham 9.0100 buffers and the Gresham Butte map boundary, Washington 410/421/422.

