# Completeness check, wash-uninc (FOLLOWUPS 222; API-credit worker, Opus 5.5, 2026-11-27)

Raw worker report, unverified by the coordinator. Paths are repo-relative; line numbers as of main 2026-11-27.

I've answered all three questions for unincorporated Washington County. No ruled item looked wrong. I found three gaps that could make a GREEN wrong and several I can't call until we fetch more text, all ranked below.

**Limits on this pass:**
- I couldn't read `../vicinitideals-worktrees/overlay-inventory*.findings.md` because the sandbox blocks paths outside the repo. Some items below may already be in those findings.
- Inline Python is blocked here, so for B I grepped the most-cited files rather than every cited line.
- I couldn't count how many of the 1,247 GREEN lots each finding touches, because there was no DB access.
- **Side effect:** running `flats.encode.crossrefs` with no arguments rewrote `data/flats/crossrefs.csv` (now dated Nov 27). Nothing else was written.

## A. Overlays, special districts and plan districts

**Could make a GREEN wrong:**
1. **Transit-district frontage easement.** The code requires "a 9-foot pedestrian/utility easement … adjacent to frontage on a Special Area Neighborhood Route or Special Area Commercial street. A 10-foot … adjacent to a Special Area Local street" (`cdc.501.public-facilities.txt#L555-L562`). This applies in every TO district and next to any Special Area street.
   - Yards are measured from the "easement for public travel, whichever is closest" (`302-7.txt#L11`; `cdc.106.definitions.txt#L1165-L1170`). So the building moves back 9–10 ft, and the TO middle-housing table's 10 ft minimum / 15 ft maximum front yard (`375-10.txt#L296-L297`) is then measured from the easement.
   - The config treats any sidewalk easement as an unmeasured doubt (`_unincorporated.yaml#L1106-L1112`) and never cites 501-8.1 E, which makes the easement mandatory here.
   - **Questions:** Do 431-4 A's middle-housing exclusions (`cdc.431.transit-design.txt#L113-L123`) reach 501-8.1 E? 501-8.1 E itself says "(See Section 431 for use-specific exclusions…)". And is a "pedestrian/utility easement" an "easement for public travel" (`106#L508`)?
   - No layer is held for the TSP's Special Area Street Overlay Maps (`cdc.300.introduction.txt#L42`), so lots outside TO districts can't be found.
2. **County Significant Natural Resources (CDC 422).** The code applies it in every district ("Section 422 (Significant Natural Resources), are applicable", `375-10.txt#L3`; `cdc.430-84.middle-housing.txt#L23`). The text of 422 is not held, and the county's own Community Plan resource maps are not held either. Metro Title 13 stands in for them (`flats/rules/resource_overlays.py#L158-L162`).
   - **Can't tell** whether 422 bars a dwelling in any designation, or how far Metro's map differs from the county's.
3. **Drainage Hazard Areas (CDC 421).** These are by definition "outside the mapped base flood area … four percent chance annual flood" (`cdc.106.definitions.txt#L414-L416`), so the FEMA layer cannot show them.
   - The 421 note says only "The floodplain itself is screened on its mapped layer" (`_unincorporated.yaml#L99-L105`).
   - 421 is not held. **Can't tell** what it requires inside a drainage hazard area.

**Can't tell (target not held):**
4. **Landslide Study Areas (410-4).** "Lands shown on adopted Landslide Study Areas maps are subject to … 410-4" (`391/391-6.txt`, per the crossrefs.csv row). Section 410 (Grading and Drainage) is on 430-84's list of standards that apply to middle housing (`#L18`). It has 19 mentions and no outcome in the ledger. No Washington landslide layer is held (Clackamas has one, `pipeline.yaml#L1346`).
5. **Section 380, Convenient Access to Transit Overlay District.** It is named at `501#L625-L627` and is not held; the ledger lists it as 380 x1 with no outcome. Nearby, a transit stop "easement or dedication" can be required at the Transit District's request (`501#L609-L624`).
6. **Mineral and Aggregate Overlay (379, Districts A/B).** It is named at `300#L17`. Section 379 is not held and the config has no entry for it. The plans' quarry-noise review is ruled as a flag (`yaml#L1294-L1296`).

**Still open in the config (already recorded, listed only because they are unresolved):**
- Airport heights and the approach-zone rule (`yaml#L1129-L1137`).
- 419-1, the neighbouring district's lower height limit (`#L1122-L1127`).
- Bonny Slope West, Section 391 (`#L1314-L1323`).

**Checked and not a gap:**
- Historic overlay 373 (`flats/config/historic/protection.yaml#L131-L135`).
- State and Regional Park Overlay: rural zones only.
- Interim Light Rail Station overlay: removed (`community-plan.cedar-hills-cedar-mill.txt#L153-L154`).
- "Cultural Management Overlay" is the old name used in the plans.
- West Union plan: no eligible lot (`yaml#L1263-L1265`).
- Clean Water Services corridors: Metro Title 3 stands in.

## B. Cross-references near cited lines

1. **501-8.1 E (finding A1).** It is reached through 430-84's "(8) Requirements specified as applicable under Section 501 shall be met" (`430-84#L148`), eight lines above the cited L156. The target is held but hasn't been read for this rule.
2. **430-84 references with no outcome in the ledger:**
   - 410 Grading (x19)
   - 406-6 solid-waste storage (could take ground)
   - 416 Utility Design
   - 403-2 Master Plan

   All four are listed at `430-84#L14-L20` and none is held. **Can't tell.**
3. **Wrong target.** `430-84#L392` reads "spacing standards of 501-8.2 B", but 501-8.2 is "Essential Services" (`501#L566`); 501-8.5 B is probably meant. It only affects extra townhouse driveways on a collector or arterial. Low.
4. **Sight distance.** 418-3 says "Nothing in this Section shall supersede … sight distance standards in Section 501-8.5 F" (`cdc.418-419.setbacks-height.txt#L68-L69`). 501-8.5 F is held (`501#L1079+`) but not encoded; it could limit where the driveway goes. Low.
5. **Retained existing house.** "Except in areas subject to Section 421 and/or 422-8" (`302-6.txt#L7`) and "421 and/or 422-3.3" (`375-10.txt#L385`). The ledger has no 422-3.3 row and only 422-8.1 (from 106). This matters only if the screen keeps an existing house on the lot. Low.

## C. Defined words

1. **Through lot** has no definition in Section 106 (headword grep of 106-1 to 106-222). Values depend on it at 392-9.5 B(1) (`yaml#L4159-L4162`; `cdc.392.mixed-use.txt#L510`). Question: what test does the screen use?
2. **Average lot width** is not defined; 106-121 defines lot width only at the midpoint (`106#L669-L670`). The config encodes `min_average_lot_width_ft` 85 for NMU and CCMU (`yaml#L4069-L4072`), and North Bethany uses the same phrase (`390#L1207`, `#L1352`). **Can't tell** which way it would move a result.
3. **Driveway** has no 106 definition, and no card exists for it in `words.py`. `driveway_approach_max_width_ft` depends on it (`yaml#L1050`).
4. **Wrong text on `words.py` cards** (a reviewer signing these would sign the wrong definition):
   - "street" quotes 106-201 Street Plug (`106#L1070`). Section 106 defines no Street, as the config itself says (`yaml#L926`).
   - "building height" quotes 106-101, height above mean sea level (`106#L592-L593`). The building-height definition is 106-101.1 (`#L594-L601`), so 106 has two height definitions.
   - "townhouse" and "attached dwelling" show as silent, but 106-211 defines them (`#L1104-L1107`).
   - "multifamily" and "apartment" show as silent; the code's term is 106-143 (`#L782`).
   - "grade" shows as silent; "building grade" is defined inside 106-101.1 (`#L599-L601`).
5. **A second glossary for flood purposes.** Several Section 106 entries send the reader to 421-2.x for their meaning "for flood and drainage hazard area management purposes" (`106#L213`, `L388`, `L719`, `L745`, `L750`, `L895`). 421-2 is not held.
6. **Transit-district definition sets** at 375-3 (`#L29-L74`) and 431-3 (`#L30-L86`) are not in the `definitions:` block. The middle-housing table uses "Front Yard", not 375-3.6's "Frontage Yard", so these don't change the pod's path. Low.
7. **Words with no Section 106 definition that we borrow:**
   - "Flag lot": 430-46 is not held. The East Hillsboro `flag_lot` values use Hillsboro's code (`yaml#L1555`).
   - "Lot coverage": the only values are East Hillsboro's, taken from Hillsboro's tables (`yaml#L1595-L1604`). The coordinator should check that Hillsboro's definition came with them.

**Not reached:** a cross-reference scan of the community-plan and 392 cited lines, reading the overlay-inventory worktree files, and the 410, 421 and 422 text, which is not held and needs fetching.

