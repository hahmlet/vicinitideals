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

## What the fire code says (read 2026-11-19; Steph: "read for yourself on access")

Oregon Fire Code 2025, Chapter 5 and Appendix D (held in `data/flats/books/building-codes/ofc-2025/`):

- 503.1.1 is the whole rule: an **approved** fire apparatus access road within 150 ft of every
  first-storey wall by an **approved** route. It names no kind of road that counts or does not.
  Freeways, ramps, state highways, wide roads and railroads are not mentioned. The local fire
  official decides.
- The regional guide the local agencies share
  (`flats/provenance/docs/or/ofc.2022.applications-guide.txt`, Clackamas Fire, used by Gresham and
  TVF&R) is also silent on where an engine may stand, but for hydrants it says: one across
  railroad tracks does not count unless approved (L333), one across a divided highway or freeway
  does not count, heavily travelled collectors only as approved (L337). That is the closest
  printed statement and it points the same way as the cautious answers built here.
- Sprinklers: 503.1.1 exception 1.1 authorises the official to relax the rule. A discretion, so
  Steph's 2026-10-01 ruling (RED, no sprinkler relief) stands on the text.

Coordinator's calls on that reading (cautious; Steph may overrule):

- Q53 state highway: ordinary frontage on a state highway counts as before. A highway reached
  only by a wide-road line: YELLOW with a flag (as built).
- Q54 wide main road: the code does not care how wide the road is, and Steph's 2026-10-05 ruling
  already says where the hose starts (10 ft out from the near curb, capped at the middle). So a
  wide ordinary street with a MEASURED curb could count for GREEN under that ruling. Not built for
  rel11 (stays YELLOW); a small follow-on after the release.
- Q55 freeway-only lot: stays YELLOW (an access easement or private road the map does not show is
  possible).

Scout 2026-11-19: no local fire agency says more than the state code on which roads an engine
may stand on (whole-document search of the Clackamas Fire, Tualatin Valley, Gresham, Portland and
Canby guides; files and `sources.md` in `data/flats/books/fire-agencies/`). So these calls need no
per-city rule. Newer guide editions were found: FOLLOWUPS 212.

## Not done

- No data says which state highways are access-controlled (Hwy 213 at Oregon City is; McLoughlin is
  not). A state access-control layer would let the two be told apart: a scout job, after rel11.
- Choosing the front after measuring fire, and letting the placement retry run on lots over 3 acres,
  would rescue more of the 75; both can open GREEN, so they wait on Q54.
