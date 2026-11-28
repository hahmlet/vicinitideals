# Completeness check, west-linn (FOLLOWUPS 222; API-credit worker, Opus 5.5, 2026-11-27)

Raw worker report, unverified by the coordinator. Paths are repo-relative; line numbers as of main 2026-11-27.

I couldn't answer "do we have everything?" with a yes for West Linn. I found one standard in text we already hold that no value uses and no ledger reports, and it could make a GREEN wrong: CDC 38.030, a front-yard setback measured from the street centreline. I found two smaller definition gaps, and several things I can't settle without text we don't hold. I edited nothing.

Both ledgers ran. `crossrefs` shows no unfollowed reference for West Linn that sits next to a value we use. Every such reference already has a ruling, and 32 references with no ruling sit next to nothing we use. I left out the West Linn rows in `uncited.csv` that already have rulings. I could not read `../vicinitideals-worktrees/overlay-inventory*.findings.md` or `overlay-inventory-lists/`, because the sandbox blocks reads outside the repo. So that earlier overlay work is not checked against this list.

## Ranked: could make a GREEN wrong

**1. CDC 38.030, setback from the street centreline. Not encoded, not cited, not in any ledger.**
- `38.yards.txt#L27`: "The minimum distance from the wall of any structure to the centerline of an abutting street shall not be less than 25 feet plus the yard required by the zone. This provision shall not apply to existing rights-of-way whose required width is 50 feet or greater."
- `#L25` raises the yard where the street is narrower than its class requires: the zone setback plus half the "constrained" width in TSP Exhibits 6–9.
- Every zone chapter's dimensional section opens "Except as may be otherwise provided by the provisions of this code" (`11/11.070.txt#L3`), and its own standards list names Chapter 38 (`11.r-10.txt` section 11.090(A)(3)).
- I grepped the config for `38.030`, "centerline" and "street widening": nothing. Neither `uncited.csv` nor `crossrefs.csv` has a 38.030 line. 85.200 appears only as a reference not next to any value, because nothing cites 38.030. It's the same blind spot as the Gresham case the crossrefs ledger was built for.
- Example: R-10 has a 20 ft front yard, so (C) needs at least 45 ft from the centreline. A 40 ft right-of-way gives 20 + 20 = 40 ft, which is 5 ft short.
- The stored `#L25` stops mid-sentence at "; however". The download may be cut short.
- **Questions:**
  - Which West Linn streets have a required width under 50 ft?
  - We don't hold TSP Exhibits 6–9; only `tsp.access-spacing.txt` (Tables 14–15) is stored.
  - Should 38.030 be encoded, or should affected lots become REVIEW?

**2. Chapter 28, Willamette Greenway / Tualatin River Protection (zoning-map overlays WRG and TRP, `05.density.txt#L55-L56`). Still open.**
The config already calls this a possible false GREEN (`west-linn.yaml#L483-L494`), and FOLLOWUPS 105 lists it as open. Nothing new here, except that it is still unhandled.

**3. "Lot area" leaves out access easements and flag-lot drive area. Not applied.**
- `02/02.030.txt#L867`: "exclusive of public and private roads, and easements of access to other property or the private driveway area of a flag lot."
- The minimum lot size and the lot-size-per-unit density both use lot area. The config never uses this exclusion: I grepped for "flag lot", "pole" and "easement" and found nothing on lot area.
- An `access_easement` fact exists (`flats/rules/conditions.py#L878`, used by Troutdale) but West Linn doesn't use it.
- **Question:** is a flag lot's drive strip counted in our lot area today?

**4. Water Resource Area (WRA) widths for ravines and long steep slopes are cut too narrow (Table 32-2 rows B and C).**
This is documented: the quadfit overlay note says it "Under-carves on steep ground by construction" (`Lot Analysis/quadfit/config/overlays.yaml`, `west_linn_wra_stream`). It is still a real false-GREEN path.

Also, we don't hold the text of Chapter 32 (WRA) or Chapter 27 (Flood Management Areas) in `flats/provenance`. The quadfit citations quote both, but nobody can check those quotes against stored text. In particular I can't tell whether Chapter 27 bans building in the floodway, which the quadfit reading says it doesn't.

## Can't tell

**5. Willamette Falls Drive Commercial Design District (zoning-map overlay WFC, `05.density.txt#L58`).**
The config's ruling on Chapter 58 (`west-linn.yaml#L504-L511`) only covers the 25.070(C) route into that chapter. It doesn't read Chapter 58's own scope or its boundary (58.030(C)), and we hold neither. The commercial zones are ineligible, so it only matters if the WFC boundary covers MU or residential lots. **Question:** does it?

**6. Planned Unit Development overlay (PUD, `05.density.txt#L51`).**
Every mention in our text is a relaxation in the commercial zones (`18.nc.txt#L143` and others). An existing approved PUD could carry its own conditions of approval, but we hold no Chapter 24 text and no PUD layer.

**7. Landslide hazard areas.**
"Potentially severe landslide hazard area" is defined (`02.definitions.txt#L764`), but no stored chapter uses it. The only place it touches our values is the density area calculation, where it's an `assumed_none` (`west-linn.yaml#L1211`). Whatever chapter applies it isn't held.

**8. Driveway line of sight.**
`48/48.060.txt#L36` says "required line of sight shall be provided at each driveway ... pursuant to the West Linn Public Works Design Standards". We don't hold those standards, so there may be a sight-distance rule beyond the Chapter 42 triangles.

**9. Height on steep lots (41.005).**
`41/41.005.txt` measures height from the lowest side when grade differs by more than 10 ft. Exposed foundation would then add to the pod's 26 ft against a 35 ft cap. The config says 41.005 is "already cited" (`#L330-L332`), but I didn't confirm the screen measures it this way.

## Cross-references (B) that change no number for this building

These are reported for completeness:
- 41.010 (garage-only setback, `41/41.010.txt`).
- 38.040 front-yard averaging and 38.060 projections: these only loosen.
- "Unless defined as an existing lot of record" (Chapter 68, `59/59.070.txt#L12`): only loosens.
- 48.030(D), access to five or more homes: we place four.
- 48.025(B)(5), double-frontage lots: already encoded (`west-linn.yaml#L1033`).
- Chapter 43, sidewalls: read, and no field can hold it.

## Defined words (C)

Searches run: a grep of `02.030` for each term, and a grep of all stored West Linn text for "for the purpose(s) of this", "shall mean", "means", "is defined" and "DEFINITIONS". The glossary tool reads only one West Linn glossary, 02.030 (518 entries).

- **Second definitions in 02.030:**
  - "Grade": `#L667` general; `#L1256` covers sign height only.
  - "Basement": `#L138`, plus a floodplain-only version at `#L403`.
  - "Building": `#L150`, plus a historic-only version at `#L703`.
  - "Structure": `#L1397`, plus a floodplain-only version at `#L579`.
  - All the extra versions are limited to a sub-glossary (headers at `#L370`, `#L689`, `#L1210`). None conflicts with a value.
- **Definitions outside Chapter 2:**
  - Building height: 41.005 calls itself "this definition" (`41/41.005.txt`). The glossary tool misses it; the config cites it.
  - Mid-block lane: defined for 48.025 alone (`48.access.txt#L55`).
  - "One standard parking space": `46.parking.txt#L231` (8×16 compact, half of stalls 9×18). The config holds 9×18.
  - Chapter 28's definitions section is repealed (`28.river-protection.txt#L63-L65`).
- **Not defined anywhere in the stored text:** setback, driveway, height (outside 41.005), accessway. No 02.030 line starts with any of them.
- **Lot depth** (`#L872`, "average horizontal distance between the front and rear property lines") drives the MU minimum lot depth of 90 ft (`west-linn.yaml#L2660`). **Question:** does the screen measure depth as that average?
- **Middle housing** (`#L942`) defers to ORS 197A.420. That law is stored only under Johnson City (`ors.197a.420.txt`), not in the state folder or West Linn's.

## Out-of-date config text (not a GREEN risk)

- The Chapter 42 note at `west-linn.yaml#L472-L481` still says clear vision is "NOT ENCODED", but the `clear_vision:` block at `#L2756` now encodes it.
- The `private_drives` note (`#L2751-L2753`) cites 02.030 at L780, L626, L638 and L177. Those terms are now at L1100, L878 and L221.

## Not done
- I didn't count how many of the 124 GREEN lots each finding touches; that needs the database.
- The overlay-inventory comparison is not done (sandbox block, above).

## Please check
- Findings 1 and 3 are the ones to act on.
- Re-download 38.030 to confirm whether the stored text is cut short.

My only side effect is that running `crossrefs` rewrote `data/flats/crossrefs.csv`, which already had uncommitted changes. One scratch-file attempt (`.claude/state/wl_xr.txt`) was refused and never written.

