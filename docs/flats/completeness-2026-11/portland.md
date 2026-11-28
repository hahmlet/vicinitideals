# Completeness check, portland (FOLLOWUPS 222; API-credit worker, Opus 5.5, 2026-11-27)

Raw worker report, unverified by the coordinator. Paths are repo-relative; line numbers as of main 2026-11-27.

I answered all three questions for Portland, but could not check my results against the earlier overlay findings. The sandbox blocked `../vicinitideals-worktrees/`, so I couldn't read `overlay-inventory*.findings.md` or `overlay-inventory-lists/`. Some items below may already appear there.

I ran `flats.encode.crossrefs` (wrote `data/flats/crossrefs.csv`), `flats.encode.uncited` (wrote `data/flats/uncited.csv`, 421 Portland statements) and `flats.encode.glossary --terms or/multnomah/portland`. I edited nothing.

## Ranked by whether it could make a GREEN wrong

**1. York plan district (33.597) has never been read.** It is in the city map we hold (`flats/config/areas/or/multnomah/portland/plan-districts.geojson`, `"NAME":"York (YO)"`). Nothing in `portland.yaml`, `docs/followups/` or `flats/tests/` mentions 33.597 or York, and no held-area file traces it. We don't hold the chapter, but the RICAP 11 amendment we do hold quotes it: "The nonresidential use requirement applies on sites in the EX zone" and "If any of the additional floor area will be in a residential use, the site must be brought into compliance with the required nonresidential use regulations" (`amended/ricap11.txt#L3758-3790`).
- An all-residential 4-unit building on an EX lot in York would fail this.
- Question: are any GREEN EX lots inside YO?

**2. Visitability (33.110.265.E.3) sits right below lines we cite and appears nowhere in the config.** We cite `33.110/33.110.265.txt#L45-L61`. Lines 62–92 say "Triplexes and fourplexes that meet the following standards are allowed", then require at least one unit with:
- an entrance reached by "a route that does not have any stairs between it and the street lot line or an on-site parking space", with slope no steeper than 1:8;
- a bathroom with room for a 60-inch circle;
- 200 sq ft of living area on that floor.

"Adjustments are prohibited." Exempt: lots with an average slope of 20% or more, or more than a 3 ft rise (L89-L91). The affordable path, F.8 (L140), needs two such units.
- Neither ledger catches this: it isn't a section reference and it states no field we measure.
- Ordinance 192241 deletes it from 2027-01-01 (`amended/ord192241.txt#L1553-L1557`).
- Questions: does the pod have a visitable ground-floor unit? Does Steph's 2026-10-14 ruling that an unchecked design detail doesn't block GREEN (quoted at `flats/geom/pdx_overlays.py#L136`) cover this, or is it moot after Jan 1?

**3. Five more plan districts are in the city map but were never read or listed:** Pleasant Valley (PV), Swan Island (SI), Portland International Raceway (PR), Guild's Lake Industrial Sanctuary (GS) and Cascade Station/PIC (CP). The config's list of read and pending districts (`portland.yaml#L1906-L1980`) leaves them out, and no held-area file traces them.
- Cascade Station: "In plan district. The following uses are prohibited ... 1. Household Living" until Ordinance 192241 deletes it on 2027-01-01 (`ord192241.txt#L3539-L3542`). Wrong GREEN only if a GREEN lot is in a zone that allows homes, before Jan 1.
- Guild's Lake is an industrial sanctuary, so probably no homes.
- Pleasant Valley, Swan Island, Raceway: we hold no text, so I can't tell. Pleasant Valley is the one most likely to touch residential land.

**4. Driveway permits (PCC 17.28.110) are not held.** "The Office of Transportation reviews the layout of parking areas for compliance with the curb cut and access restrictions of Section 17.28.110" (`33.266/33.266.100.txt#L27`). The crossrefs row has no outcome. `portland.yaml#L2463-L2468` itself says Title 17 "is not in this corpus ... a document that has not been read". It could set driveway width or distance from a corner, which affects vehicle access.

**5. The narrow-lot standards (33.110.260) were set aside for a reason the text doesn't support.** The uncited triage note (`portland.yaml#L1162-L1172`) calls the section about "the lot's history" and says it only loosens. The text applies by width to any lot: "lots, adjusted lots, lot remnants, lots of record ... that are less than 32 feet wide" (`33.110.260.txt#L7`). It adds:
- height capped at 1.5 × the street-facing facade width (L13);
- "Sixty percent of the area between the front lot line and the front building line must be landscaped" (L24).

Question: are any GREEN R20–R2.5 lots under 32 ft wide? A driveway could break the 60%.

**6. River and Greenway overlays, other than River Environmental "e", aren't handled.** We hold no 33.475 or 33.440 text. The only Portland river rule anywhere is `pdx_river_e` in `Lot Analysis/quadfit/config/overlays.yaml#L211`. The stored code shows the others exist: "River General (g*) overlay zone" (`33.510.txt#L179`) and "33.440.230.D.1" (`33.700.txt#L363`). Can't tell; it matters only for residential lots on the riverbanks.

**7. The airport noise overlay (33.470) is only covered inside "z".** The 68+ DNL contour counts only as a Constrained Sites trigger in R20–R2.5 (`33.418.txt#L38`). Nothing covers multi-dwelling or commercial lots under the contour. Not held, so can't tell.

**8. Three overlays appear nowhere in the stored code:** Aircraft Landing (33.400), Buffer (33.410) and Alternative Design Density (33.405). A whole-store grep for `33.4\d\d` finds only 415, 418, 420, 430, 440, 445, 465, 470, 475 and 480. Can't tell whether they still exist or reach residential lots. An airport-area height limit could fall below the pod's height.

**9. Ordinance 192241 (effective 2027-01-01) is held but read only for RF** (`portland.yaml#L2511-L2529`). It rewrites 33.418.040, 33.430, 33.465, 33.110.210/215/225/265 and 33.610.100. I found no follow-up item for reading all of it. Mostly loosening, but the text changes in 35 days.

**10. Constrained Sites is read from the mapped "z" letter only** (`flats/rules/conditions.py#L1036-L1053`). The other triggers in 33.418.030 (landslide maps, wildfire maps, industrial sanctuary, 68 DNL) aren't checked separately. Likely correct, since the rule applies through the map. Question: is a lag between the triggers and the map ever a risk?

**11. Building coverage counts high decks and stairs.** It "also includes uncovered horizontal structures such as decks, stairways and entry bridges that are more than 6 feet above grade" (`33.910/33.910.030.txt#L58`). The uncited ledger shows this line as unquoted. Question: does the pod have outside stairs or a deck more than 6 ft up?

**12. Not a GREEN risk, just a provenance gap.** We hold no text for 33.430, 33.465 or 33.475, and `portland.yaml` cites none of them. The environmental and river carves rest only on citation strings in `overlays.yaml#L164-L216`. Carves err strict.

## B. Cross-references
- The crossrefs ledger looks 12 lines either side of a citation (`flats/encode/crossrefs.py#L112`). All 14 Portland rows it flags as near a citation already have an outcome: 33.612/613/614 are parked as "later", and the others are closed.
- None of the 103 open Portland rows sits near a citation. The ones that could matter are items 4 and 1 above, plus 33.266.115's "Regulations in a plan district or overlay zone may supersede" (`#L4`, `#L35`), which ties to the unread districts.
- Its blind spots are sentences with no section number, like item 2, and references to documents we hold but haven't read. Those are not covered.
- Following the unless/except-as phrases in the 12 most-cited section files turned up nothing new. For example, the 33.130.215 vehicle-access sentence is already refused at `portland.yaml#L6176`.

## C. Defined words
- The glossary has 288 entries, all from 33.910. I found local "for the purposes of" definitions by grepping the whole store. Already captured: grade at 33.110.215.D (`portland.yaml#L261-L277`) and 33.110.230/33.120.231 (cited); lot width per 33.930.100 (`#L661`); street excluding alleys and freeways (`#L1582`, `#L8196-L8205`).
- Not captured: the "width" in 33.110.260 (L15, item 5) and "lowest grade measured at the front setback" in 33.110.265 (L91, item 2). The flag-lot width and depth rules (33.110.202 note [5], 33.610.400 L34, 33.530 L57) aren't used by any value we encode; only multi-dwelling zones carry a minimum lot width.
- Portland defines no "middle housing", "story" or "townhouse": 0 hits for "story" in 33.910 or 33.930, and "middle housing" appears only inside other entries (L341, L1102-L1148). The governing words are "Attached House" (`33.910.definitions.txt#L1086`) and "Fourplex" (`#L1119`). "Driveway" (`#L280`) may have a second meaning in Title 17, which we don't hold.

## What I didn't get to
- I didn't triage all 421 uncited Portland statements, only the setback, frontage, width, coverage and floor-area ratio ones.
- I counted no GREEN lots per finding because I had no database access. Each "any GREEN lots in X?" question above needs that run.

