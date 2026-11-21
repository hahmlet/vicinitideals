# 208 Beaverton 3 ft driveway rule: false REDs

Found 2026-11-19 by the rel10 full-bound move read (`../vicinitideals-worktrees/rel10-full-moves.findings.md`, findings 1-2).

Lane 201 G (ships in rel10) holds Beaverton's driveway 3 ft from a lot line. The screen slides the one drawn plan and, at the slide limit, calls the lot RED; it never tries the mirrored drive side or another plan. rel10 full bound: 31 green>red and 52 yellow>red in Beaverton, many missing by 0.1-0.4 ft with 90-160 ft of spare room (1S116DB02200, 1N131AC00100). Three lots (1S115CD10900, 1S115CD10901, 1S128AB11200) show "doesn't fit" where the real cause is this rule.

Not a false GREEN, so rel10 ships with it (fix forward). Fix lane: flats-encoder "bvt-drive-side", branch `flats/bvt-drive-side` from flats/carve-overlap 05266da7: try the mirrored side / other candidate placements; YELLOW only if a sound search cannot be built; correct the reason text. Joins rel11; every regained GREEN is read one by one. Hand-off `../vicinitideals-worktrees/bvt-drive-side.handoff.md`.

## Status 2026-11-19 -- built, waiting for rel11

Branch `flats/bvt-drive-side` head 4dca331b (fa367ea5 placement search + slide-stop fix + reason fix; 4dca331b half-foot tolerance, RED to YELLOW only). Measured on 137: the spare room in the finding was depth; the plan needs 100.0 ft of width and the lots measure 97.1-100.1 ft. Expected: about 46 RED to YELLOW, 0-6 possible GREEN gains (List B in the hand-off, read one by one), about 31 stay RED, three lots change reason only. Coordinator kept the tolerance commit: it is more cautious than ruling 2026-09-25-tight-fit-green. Being merged into `flats/rel11` as the tenth lane. Open, not changed: whether Beaverton's 3/6 ft is measured only at the curb cut rather than along the whole lane (read as whole lane, stricter).
