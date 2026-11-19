# 205. Seven noted-but-unbuilt gaps, sized on run 128

**Status:** sized 2026-11-18 (report ../vicinitideals-worktrees/noted-gaps.findings.md; lists noted-gaps-lists/). Fix lane flats/gap-fixes (from rel10d), rides the release after rel10.

1. Driveway spacing in Canby, Gladstone, Hillsboro (no table entry; other cities got one in item 178): greens whose only frontage is a busy street -- Canby 7 (firm, CMC 16.46.030), Gladstone 39, Hillsboro ~174; 73 on arterial-type roads only. YELLOW by the 11-09 ruling. Missing: city street-class maps, Hillsboro Design and Construction Standards, Gladstone 17.50 (403).
2. Multnomah tax-exempt owners not read (institutional ruling 2026-10-06): 437 exempt greens; 36 government-owned (Portland 16, schools 6, State 4, County/Library 5, other 5; 20 with no building); 27 Housing Authority / Home Forward; 369 churches/charities stay screened by ruling. Build: mirror the Washington County treatment. STEPH (non-blocking): does housing-authority land count as public?
3. Hillsboro street-widening table CDC 12.50.130.J.2 / Table 12.50.130-1: 3 false greens on SE Bentley St (1S204BC04100, 1S204BC04200, 1S204BD00800); ~83 greens have a widening strip, the rest have room.
4. Edge smoothing up to 1 ft: 1S3E06BD  -09500 (front yard short ~0.8 ft), 1S117CD00900 (0.63 ft short).
5. Portland flag-lot setbacks 33.110.255.B / 33.120.284 not held: 13-14 greens, 4 tight (1S3E07AB  -11601, 1S1E07DC  -02802, 1N2E21CA  -03600, 1S2E04CB  -03900). Config notes reasoning from a 26 ft pod (Clackamas unincorporated, Gresham) unchecked.
6. No false green: West Linn greenway, Cornelius 100 ft entrance, Portland maximum floor area (3,655 greens tested, smallest allowance 4,814 sq ft vs 4,000).
Not sized: RM1/RM2 20 ft maximum front setback on transit streets.

## Built 2026-11-18

flats/gap-fixes 774ab332 (six commits on rel10d; later commits add the rulings). Hand-off `../vicinitideals-worktrees/gap-fixes.handoff.md`. Expected: Canby 7, Gladstone ~39, Hillsboro ~174-240 to yellow; Multnomah 9 government red + 9 housing-authority YELLOW (ruling 2026-11-18-housing-authority-land-yellow); Hillsboro widening 3 firm/13 possible; Portland flag lots 2; edge smoothing 2 firm + up to 6. Rulings: county street maps stand in (three ids), Milwaukie 5 and 10 held exactly (being built). Full suite not re-run after fixes; gaps.json stale; quadfit min_frontage_ft drift already on rel10d. Six Portland short-frontage lots stay green on shape judgement (listed in hand-off). Gladstone local driveway figures: see 204 (gladstone-fixes reads Public Works Design Standards 2017 s.5.0070).
