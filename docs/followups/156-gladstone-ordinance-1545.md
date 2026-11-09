# 156. Gladstone quadfit rules follow the old printed code, not Ordinance 1545

**Status:** built on `flats/gladstone-1545` (off `flats/ci1-quadfit`), rides the next
package with 155; quadfit s3+ to rerun for Gladstone on 137. Found by the CI1 lane (155).

quadfit's `Lot Analysis/quadfit/config/rules.yaml` still carries Gladstone R10
and C1 as the old printed code, not as amended by Ordinance 1545. quadfit can
measure lots the new law would reject; FLATS still refuses them, so no false
GREEN, but the envelope figures are wrong. Bring R10/C1 to the amended text
(the CI1 lane added `corpus_amendment:` on rules rows for this; reuse it),
mirror test, rides the next package.

## Built (2026-11-09, branch flats/gladstone-1545)

- FLATS already follows 1545: R7.2 and R10 carry `amended: ord1545`, and C1's
  `like: R7.2` resolves to the amended R-7.2 at screen time (7,200 sq ft, C-1's
  own 15 ft side). Checked on the screen's law date. R5, MR, C2, C3 re-read by
  1545 with no change to the four-unit building's numbers or use gate; left
  codified (no `amended:` entry), noted for a later tidy.
- quadfit rules.yaml: R7.2 gains `corpus_amendment: ord1545`; R10 to 7,200 /
  5 ft side; C1 to 7,200 (side 15 kept). The audit's amendment hold is now
  layer-wide (`audit_zone_mirror.amended_layer`), so a row reaching the
  amendment through `like:` (C1) is held to it. `KNOWN_DIVERGENT` emptied.
