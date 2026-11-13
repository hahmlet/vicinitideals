# 188. Lots cut by a district boundary pass untested (possible false GREEN)

[Claude] [scan: YES -- toward yellow]

Found 2026-11-12 by the gresham-end-glass lane. BUILT 2026-11-13 on branch `flats/cut-district`
(hand-off ../vicinitideals-worktrees/cut-district.handoff.md); rides the release after rel8 (rel9),
not merged into flats/rel8.

What was open: a traced district (`drawn_areas`) answers a lot True, False or -- where its line cuts the
lot -- not at all. A `when` variant on the fact already held such a lot (FACT-<district>, then
`_bounded` tries both sides). Two paths did not:
1. `only_when` / `unless` values (resolver): the silenced or applied value recorded no lever, so the cut
   lot screened as if outside, untested on the inside rule (Portland Map 120-2 frontage, Map 120-3 rear
   vehicle area, East Hillsboro city standards; South Hillsboro glass once rel8 lands).
2. The screen's own traced-area reviews and records (`AREA_REVIEWS`, `AREA_FLAGS`) were asked only of a
   lot wholly inside.

Built: `ZoneResolution.gate_levers` (every `only_when`/`unless` condition, applied or silent) joins
`levers`, so a cut lot leans on the district -> YELLOW + FACT-<district>, lowered to severity 0 only
where `_bounded` finds every side clears. `LotFacts.drawn_cut` (bridge `drawn_cut()`) names a cut
review/record area; `area_review` asks it as if inside (the worse side). Tests:
flats/tests/test_cut_district.py.

Count on rel7a (run 124 outputs, 137 /root/bridge_spliced_rel7a): 8 GREEN cut lots, all read right;
the only_when gap held 5 cut lots, none GREEN; washington_plan_review 2 cut, 1 GREEN (stays GREEN with
CLEAR-OBJECTIVE). Remaining: the bound on rel9 (expected moves all toward yellow, a handful).
