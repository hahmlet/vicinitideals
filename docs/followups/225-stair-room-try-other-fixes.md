# 225. Stair-room red: try the court's other turn fixes before calling it red

[Claude] [scan: YES -- toward yellow/green]

From the dcourt move read 2026-11-28 (../vicinitideals-worktrees/dcourt-moves.findings.md, finding 1).
The screen takes the first turn fix a court holds; the stair-room re-placement never tries the others.
In 136 of the 151 dcourt yellow->red lots the same court passes with a fix that only lengthens the dead end
(no extra depth); some have 70-187 ft slack (22E28BB00900, 11E36CC00300, 1S116BD01300). Steph's 2026-10-03
ruling makes the dead end the last resort, so it must be tried before red -- no new ruling needed.
Also from the same read (small): cmp.py's move label hides 69 plan/form switches (finding 2); the bound
control rule should count only NEW codes and run with foundation classes (finding 3); 12 red courts match no
carried shape, unread (finding 4, no false-green risk).
Do after 216 ships: fix in the stair-room pass, scoped re-bound on the 151 + the 12, move read, release.
