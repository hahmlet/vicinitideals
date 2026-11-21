# 215 -- Portland short connector roads read as limited roads (false RED / lost GREEN)

Opened 2026-11-21 from the ow11 move read (`../vicinitideals-worktrees/ow11-moves.findings.md`, F2 and F3).
Cautious direction only: no false GREEN. Fix after rel11 ships.

## F2 (build)

The open-way fix (FOLLOWUPS 211) reads RLIS ramp/connector types as limited roads. In Portland the
definition (PCC 33.910.030) excludes only interstate and Sunset Hwy ramps, so short connector roads
between ordinary streets are streets. Code: `Lot Analysis/quadfit/s4_edges.py#L214-217` and `#L576-577`.
Fix: in Portland, read RLIS types 1321, 1421, 1471, 1521 as streets unless they are interstate/Sunset
ramps. Lots: `1N2E22DA  -00200`, `1S1E10BA  -00900`, `1S2E16CA  -11600`, `1S2E17AD  -00700` (now red),
`1N1E06DC  -02400` (lost GREEN). s4 change: needs an s4 re-run and a scoped re-bound; can open GREEN,
so each gain is read.

## F3 (already deferred in open-way-fix.handoff.md L218-220)

After the buildable area grows or a street is dropped, the pod is re-placed and sometimes lands worse
(5.01% slope against 5%, front maximum missed on 10 Portland lots). Choose the better of the old and
new placement. Ties into "choose the front after measuring fire" (FOLLOWUPS 211 Not done).

Decision pending: none.

## F4 (from rel11-firenear, 2026-11-21)

Fire-hose near MISSES (under 0.5 ft over 150 ft) stay RED: `fire_access_ft` has no slack in
`flats/config/slack.yaml`. The near-PASS side is held YELLOW (FIRE-NEAR-PASS, 0.5 ft, rel11). Making a
near miss YELLOW too would mirror it (cautious direction; small count). Coordinator call, not Steph.

## F5, F6 (display only, from holds-fire-moves.findings.md, 2026-11-21)

- F5: `1S1E16CD  -03400` -- the shown front reading lacks the MEASURE-TOLERANCE mark that moved it
  (the other reading passed). Carry the mark onto the shown row.
- F6: lots over 150 ft held YELLOW for another fire reason (dead end, narrow street, unclear road;
  screen.py ~L5343-5355) lack FIRE-HOSE-VALIDATE, e.g. 1N130DC00400 189 ft. Raise it there too.
Neither moves a colour.
