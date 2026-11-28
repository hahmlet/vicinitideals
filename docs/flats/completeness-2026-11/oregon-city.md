# Completeness check, oregon-city (FOLLOWUPS 222; API-credit worker, Opus 5.5, 2026-11-27)

Raw worker report, unverified by the coordinator. Paths are repo-relative; line numbers as of main 2026-11-27.

I found seven things the existing ledgers miss that could make an Oregon City GREEN wrong, plus some smaller gaps. Two of the four ledger runs did not finish, so part C is incomplete (see the last section).

**What I could and couldn't run:**
- **Cross-references and unquoted lines:** `crossrefs` and `uncited` were each started twice (once by mistake through `--help`, which has no help option and ran the full job). None of the four runs had finished when I wrote this. I worked from the CSVs already on disk, which were modified before I started; finished runs may rewrite them. Every Oregon City cross-reference the ledger marks as binding is already closed (misread, `narrows_only` or `other_path`), so everything below is a miss.
- **Glossary:** finished. It captures only the 17.04 definitions chapter (L834–L3883).
- **Words review:** produced no output in time, and the config has no word-card rulings for Oregon City.
- **Past overlay work:** I could not read `../vicinitideals-worktrees/overlay-inventory*`, because it is outside my allowed directory. I used `docs/flats/design_districts_2026-10-21.md` instead.
- **Which of the 218 GREEN lots are affected:** I had no list to check against. Each finding below needs the GREEN lots intersected with the named area.

I edited nothing. Running the ledgers may have rewritten `data/flats/crossrefs.csv` and `uncited.csv`.

## Ranked: could make a GREEN wrong

1. **Thimble Creek in R-5: a 40 ft setback from the area's southern edge is not encoded. Yes, could make a GREEN wrong.**
   - The code says: "Where any portion of a lot is within twenty feet of the southern boundary … all primary structures shall be set back a minimum of forty feet from the southern boundary" (`17.zoning.txt#L4427-L4430`). Section 17.10.070 applies it to all development in R-5 inside the plan area (#L4403-L4410).
   - The boundary file `flats/config/areas/or/clackamas/oregon-city/thimble-creek-beavercreek-concept-plan.geojson` is already held, but nothing uses it. Searching `flats/` for `thimble-creek-beavercreek` finds no reference.
   - The config's header at `oregon-city.yaml#L12-L13` cites "OCMC 17.16.155" for this. That section does not exist in the stored text (grep finds nothing); the rule is 17.10.070.
   - Question: should this area be wired up as a drawn area, with the 40 ft setback measured from that one southern edge?

2. **Thimble Creek in MUC-2: residential use is allowed on upper stories only. Yes, could make a GREEN wrong.**
   - The code says: "All residential uses, except live/work units, are limited to upper stories only, and may only be proposed as part of a single development application incorporating nonresidential uses" (17.29.080.E, `#L7254-L7257`).
   - The config allows the quadplex in MUC-2 (`oregon-city.yaml#L2646-L2650`) with only a greenway exception. The design-districts doc lists MUC-2 as covered (`design_districts_2026-10-21.md#L795-L812`) but leaves this rule out.
   - Question: same boundary file — should the quadplex be closed off in MUC-2 inside Thimble Creek?

3. **On a corner lot, the city planning director decides which line is the rear. Yes, could make a GREEN wrong.**
   - The code says: "In the case of a corner lot, the community development director shall determine the rear lot line" (17.04.1000, `#L2820-L2822`).
   - The screen always takes the interior line opposite the front as the rear (`flats/geom/corner.py#L44-L48`). Nothing in the config or `rulings.yaml` cites 17.04.1000; I grepped both.
   - If the director names the other interior line, the 20 ft rear setback falls where the screen measured only the 5–8 ft side setback.
   - Question for Steph: should corner GREENs carry a flag, or be screened both ways and keep the worse result?

4. **South End: porch and walkway rules are held but not encoded. Can't tell how many lots.**
   - The code says: "Residences within twenty feet of the public sidewalk or front property line … shall contain a front porch … at least eighty square feet … no dimension under six feet … twenty-four inches above average grade", covered (17.22.050.A, `#L6390-L6397`).
   - 17.22.050.C also requires a separate 3 ft path from each front door to the sidewalk.
   - The pod has no porch. The config encodes only the South End massing and window rules. South End sets no roof pitch, so its lots can reach GREEN.
   - The Park Place twin (17.21.050.A, `#L6179`) doesn't matter: the 5:12 roof pitch already rules out the flat-roof pod there (`oregon-city.yaml#L1103-L1117`).
   - Question for Steph: does the no-porch ruling (2026-11-08) mean these lots fail, or can a porch be added on site?

5. **Lot coverage may include the parking court. Can't tell.**
   - "Lot coverage" means the area covered by "the footprint of all structures two hundred square feet or greater (excluding decks and porches)" (`#L2085-L2089`).
   - "Structure" means "anything constructed or erected that requires location on the ground" (`#L3295-L3297`), which arguably takes in a paved parking court.
   - The residential coverage values (40% at `#L1163`) count the building only, and no reading in the config addresses this.
   - Question: does a paved court count toward coverage in R-10, R-8 and R-6?

6. **Flood management overlay: the 1996 flood area beyond FEMA's map is not screened. Can't tell.**
   - 17.42.020.B (`#L9931-L9942`) adds "the area of inundation for the February 1996 flood" and lands with "documented evidence of flooding" to the overlay.
   - Only the FEMA floodway and flood-zone layers apply to Oregon City. Quadfit records this same gap for Gladstone (`Lot Analysis/quadfit/config/overlays.yaml#L1193-L1200`) but not for Oregon City.
   - Question: could the FLOOD96 attribute on the Metro Title 3 layer be used as a flag?

7. **Drive-in rules in 16.12.035 that nothing encodes. Low risk.**
   - "No backing of a vehicle" onto a collector or arterial (`16.12.streets.txt#L1069-L1071`). Question: does the parking layout check this when the lot's only street is a collector?
   - "No driveway with a slope of greater than fifteen percent" without the engineer's approval (`#L1149-L1150`). The GREEN grade cap of 5% (`flats/config/slope.yaml#L41`) mostly covers this.

## A. Overlays and special areas

The code names five overlays (17.06.015, `#L3940-L3946`) and several special areas. Most are already handled:

| Overlay or area | Status |
|---|---|
| Historic (17.40) | Handled: closes the use (`oregon-city.yaml#L1052-L1061`, `#L3476-L3498`) |
| Willamette River Greenway (17.48) | Handled: closes the use (`#L1064-L1076`) |
| Natural resource (17.49) | Handled: carved out (`overlays.yaml#L1008-L1016`) and subtracted from net area (`#L1198`) |
| Geologic hazards (17.44) | Handled: flagged and carved (`overlays.yaml#L1042-L1060`; `pipeline.yaml#L1312-L1322`) |
| Downtown design district (MUD) | Handled: uses the tighter of the two standard sets (`#L2797-L2812`) |
| Park Place | Handled: roof pitch, massing and windows encoded |
| Flood management (17.42) | Partial: see finding 6 |
| Thimble Creek | Not handled: findings 1 and 2. Its NC, CI and R-2 parts are already closed or only relax. |
| South End | Partial: porch and walkway not encoded (finding 4) |
| Tree protection (17.41) | Not handled, low risk: designated heritage trees (17.41.020.D, `#L9356-L9358`) send to Chapter 12.32, which we don't hold. A designated tree could block a spot; can't tell. |

## B. Cross-references near the cited lines

Most cross-references near the cited lines point at text we hold and either relax a number or are already encoded:
- 16.08.065, 17.54.010.B and 17.62.055.D only relax.
- 16.12.035 and 10.32 are held and encoded.
- 17.62.035 is procedure. 17.62.030 limits a quadplex to that section's standards only (`#L16794-L16797`), so the general site-review standards do not apply.

The ones still open:
- **17.21.020 / 17.22.020 → porch sections 17.21.050 and 17.22.050.** Held, not encoded (finding 4).
- **17.16.060.B → 17.14.030.** Held and read. 17.14.035.B requires windows and doors on 15% of the second street-facing ground-floor wall of a corner or through lot (`#L4917-L4919`). 17.16.060.B names only 17.14.030, not 17.14.035. Question: does 17.14.035 reach a quadplex?
- **17.04.550 height → 17.42.** Inside the flood overlay, height is measured from the design flood elevation (`#L1864-L1867`). This is not encoded, but the pod is 20 ft against a 35 ft limit, so no effect.
- **Unheld targets:** 12.08 (street trees), 12.32 (heritage trees), 12.04 (right-of-way permits). None changes a dimension.
- **Dangling reference:** "17.44.020" is referenced at `#L16979` but no such section exists in the code. No effect, since the hazard area is already flagged.

## C. Defined words (partial)

Where each word is defined in 17.04:

| Word | Location |
|---|---|
| corner lot | L2081 (encoded) |
| through lot | L3433 |
| lot width | L2120 |
| lot depth | L2091 |
| front lot line | L1701 (encoded) |
| rear lot line | L2818 (finding 3) |
| frontage | L1715 |
| yard, front, rear, side, corner side, interior side | L3846–L3877 |
| setback | L3048 |
| height | L1841 |
| story | L3254 (ruled) |
| townhouse | L3463; "single-family attached" = townhouse, L3124 |
| middle housing | L2329 |
| quadplex | L2801 |
| gross floor area | L1825 |
| lot coverage | L2085 |
| footprint | L1681 (scoped to 17.54.010 only) |
| alley | L906 |
| street | L3286 |
| accessory | L855 |
| flag lot | L1610 |
| residence | L2877 (ruled per unit) |

- **Not defined at all:** grade, driveway, side lot line, abut. A search of 17.04 headings finds only "Grading" (L1820) and "Access, vehicular" (L895).
- **Second, local definitions not captured:**
  - 17.14.020 defines "residences" as single-family detached homes and duplexes for that chapter only (`#L4793-L4795`). 17.16.060.B imports 17.14.030, which is worded for "a residence". This only matters if 17.14.035 is found to reach a quadplex.
  - 17.14 defines "garage" to include carports (`#L4812-L4818`). Not relevant: the pod files have no garage.
  - 17.04.1215 gives "structure" a separate meaning for 17.42 only (`#L3298`).
  - 17.04.550 gives "height" a separate meaning for 17.80, wireless facilities only (`#L1869`).
  - The whole-document search for "for the purpose(s) of", "shall mean" and "as defined in" found no other second definition of a word in the list.
- **16.12** takes its words from 17.04 (`16.12.streets.txt#L40-L44`), so it adds no definitions of its own.

**Not finished:** a card-by-card cross-check against the words review, because it produced no output in time.

