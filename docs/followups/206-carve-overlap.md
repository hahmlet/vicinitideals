# 206 Lane/court in a side yard is checked against no carve

Found 2026-11-18 by the clackamas-fixes lane ("Found, not fixed" in `../vicinitideals-worktrees/clackamas-fixes.handoff.md`).

In the bridge the drive lane and parking court may be drawn into one side yard, and that overlap is tested against no carve (ground taken off the lot), in any city. Harmless where every lot touching the carve is flagged yellow. A false GREEN is possible where a carve carries no flag: known case `pdx_river_e` on flats/rel10d under ruling 2026-11-18-river-e-clear-stays-green (known green `1S1E14DB  -17000`).

Lane: flats-encoder "carve-overlap" (11-18) confirms, inventories every carve for flag/no-flag, sizes exposed greens, and if real fixes on `flats/carve-overlap` from rel10d; hand-off `../vicinitideals-worktrees/carve-overlap.handoff.md`.

Decision pending (coordinator): does the fix replace rel10d as the rel10 scoped re-bound branch, or ride the next release. Must be settled before the rel10 scoped re-bound starts.

## Result 2026-11-18

No false GREEN today (30,300 carved lots, none green) or in rel10d (three river-e greens re-run locally: `1S1E14DB  -17000`, `1S1E14CD  -05700` stay GREEN; `1S1E14CA  -02700` RED). Fixed on flats/carve-overlap 05266da7: GREEN with drawn building/lane/court more than 0.5 ft on carved ground, or a carved lot with no plan drawn, becomes YELLOW. DECIDED: rel10 scoped re-bound runs 05266da7. Six carves have no flag: river e, Gresham hillside, Oregon City natural resources, Tualatin no-build wetland, FEMA floodway, Metro Title 3 unincorporated Multnomah. Still open: the front-yard drive is not drawn, so not checked against carves; Q47 for Steph (Title 3 unincorporated Multnomah: flag or green). Hand-off `../vicinitideals-worktrees/carve-overlap.handoff.md`.
