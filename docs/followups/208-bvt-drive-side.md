# 208 Beaverton 3 ft driveway rule: false REDs

Found 2026-11-19 by the rel10 full-bound move read (`../vicinitideals-worktrees/rel10-full-moves.findings.md`, findings 1-2).

Lane 201 G (ships in rel10) holds Beaverton's driveway 3 ft from a lot line. The screen slides the one drawn plan and, at the slide limit, calls the lot RED; it never tries the mirrored drive side or another plan. rel10 full bound: 31 green>red and 52 yellow>red in Beaverton, many missing by 0.1-0.4 ft with 90-160 ft of spare room (1S116DB02200, 1N131AC00100). Three lots (1S115CD10900, 1S115CD10901, 1S128AB11200) show "doesn't fit" where the real cause is this rule.

Not a false GREEN, so rel10 ships with it (fix forward). Fix lane: flats-encoder "bvt-drive-side", branch `flats/bvt-drive-side` from flats/carve-overlap 05266da7: try the mirrored side / other candidate placements; YELLOW only if a sound search cannot be built; correct the reason text. Joins rel11; every regained GREEN is read one by one. Hand-off `../vicinitideals-worktrees/bvt-drive-side.handoff.md`.
