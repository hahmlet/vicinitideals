# 211 -- Freeway, ramp and railroad sides counted as street sides (false GREEN in the wide-road lane)

Found 2026-11-19 by the second-pass move read of the rel10 scoped re-bound
(`../vicinitideals-worktrees/rel10d-moves.findings.md`). Nothing false is live: the wide-road lane
never shipped. **rel10 does not ship on its own; live goes run 128 -> rel11 directly.**

## What was wrong

The wide-road lane (rel10) lets a lot line count as a street side when the street's centre line is
further away than the old 50 ft test. It also counted:

- a freeway or its ramp (`1S1E31BB  -16100` Portland RM1 at the I-5/Barbur ramp; `1S2E04AC  -09600`
  Portland R2.5 at an I-205 ramp) -- 2 false GREEN;
- a street on the far side of a railroad (`1S205CD03601` Hillsboro MR-2, rail before TV Hwy) -- 1 false GREEN;
- plus 21 wrong losses (16 false yellow of the same two kinds, 5 false red from a 60 ft reach limit on
  the road-widening strip) and 75 yellow-to-red on fire access (the plan was re-placed to face the
  new wide-road side, where no engine was allowed to stand).

## The fix

Branch `flats/open-way-fix` (from `flats/rel11` d4803423), head ea8a94c1 plus a small addition in
progress. Hand-off: `../vicinitideals-worktrees/open-way-fix.handoff.md`.

- Portland: a freeway or ramp is not a street (PCC 33.910.030, quoted in the city's rule file). The
  lot is screened as if that line were an ordinary side or rear line.
- Everywhere else, and for rail and other limited roads: the lot is screened both ways, the worse
  result kept, and it is held YELLOW with a flag naming the side. Never GREEN.
- Road-widening strip: measured across a wide right-of-way instead of failing at 60 ft.
- Fire: a route that misses only because no engine may stand on a wide road is YELLOW with a flag
  where the hose would reach from the road's middle; RED where it would not. Never GREEN.
- Engine standing on a state highway reached by a wide-road line: YELLOW with a flag (coordinator
  default; two lots, Oregon City on Hwy 213 and Gladstone on McLoughlin).

## Plan (coordinator, 2026-11-19)

1. Full rel11 bound keeps running on 137 (`/root/rel11_bound/`, started 02:57Z 11-20, about 25 h).
2. Merge `flats/open-way-fix` into `flats/rel11`.
3. Scoped re-bound on top: s4 re-run in full (stop if any edge class, tier or frontage moves), then
   the union in the hand-off's BOUND SCOPE (about 13,000 lots).
4. Two move reads: rel10d -> rel11 (ten lanes) and rel11 -> rel11 + fix (this lane). Every gained
   GREEN read one by one; Portland lots that come back GREEN each rest on PCC 33.910.030.
5. Release run 128 -> rel11; then re-measure the foundation records (FOLLOWUPS 209).

## Waiting on Steph (none blocking; the cautious answer is built)

Logged as Q52 to Q56 in `../vicinitideals-worktrees/QUESTIONS-FOR-STEPH-scratch.md`:

- Q52: outside Portland, does a side backing onto a freeway or ramp count as a street side?
- Q53: may a fire engine stand on a state highway to serve the lot beside it?
- Q54: may an engine standing on a wide main road (centre line 50 to 150 ft away) count for GREEN?
- Q55: a lot whose only street side is a freeway: yellow (as built) or red?
- Q56: a road-widening strip that still cannot be measured: worst case (as built) or yellow?

## Not done

- No data says which state highways are access-controlled (Hwy 213 at Oregon City is; McLoughlin is
  not). A state access-control layer would let the two be told apart: a scout job, after rel11.
- Choosing the front after measuring fire, and letting the placement retry run on lots over 3 acres,
  would rescue more of the 75; both can open GREEN, so they wait on Q54.
