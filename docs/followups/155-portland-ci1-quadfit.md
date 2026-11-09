# 155. Portland CI1 lots unmeasured in quadfit

**Status:** built, awaiting bound (2026-11-08, branch `flats/ci1-quadfit`).

Since RICAP 11 (2026-11-01) CI1 allows homes built to RM1 standards. FLATS
knows that, but quadfit had no CI1 rules, so 36 Portland CI1 lots went
red -> yellow in re-screen 1110 and stayed unmeasured. Never a false GREEN:
unmeasured stays yellow.

Done on the branch: rules.yaml gains a CI1 row that is RM1's (10/5/5, 4,000 sq ft,
33 ft wide, 50% coverage, the RM1 minimum density), tagged
`corpus_amendment: ricap11` so the zone mirror compares it against the corpus's
RICAP 11 block rather than the codified Table 150-2. footprints.yaml gives CI1
RM1's 192 sq ft outdoor area. No alley waiver in quadfit (conservative).

Left: bound the CI1 lots on 137 (quadfit s2-s7 for the CI1 TLIDs, then the
bridge screen and splice), read the moves, release. CI2 stays held behind the
neighbour-zoning lane.
