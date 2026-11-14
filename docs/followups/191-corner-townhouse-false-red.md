# 191. Middle townhouse lots asked for the corner lot's frontage (possible false RED)

[Claude] [scan: YES -- toward yellow/green only]

BUILT 2026-11-14: flats/corner-th-191 3652cfa6 (on pagecheck-34, rides rel10). Hand-off ../vicinitideals-worktrees/corner-th-191.handoff.md. quadfit rules.yaml re-port (Hillsboro UC) left uncommitted in the worktree -- commit at release. Bent/curved corners held YELLOW (MEASURE-CORNER-HOME-LOT); asked Steph (scratch Q19).

Found 2026-11-14 by pagecheck-34 (../vicinitideals-worktrees/pagecheck-34.handoff.md, branch
flats/pagecheck-34 d9d9edda). The screen applies the corner-lot townhouse frontage (25 ft, Gresham
dc79bd29 corner change) to every middle townhouse lot, so a corner townhouse plat can never pass.
No GREEN depends on it (run 124: the 8 corner GREENs are the single-lot apartment form; every
townhouse GREEN is interior). Fix: corner figure on the corner lot only, interior figure on the rest;
read every gain in the bound.

Also for that lane: delete the three untied Hillsboro UC-AC / UC-MU / UC-RM 25 ft flag-lot frontage
entries (no passage sends the rule to these zones; harmless today because those flag lots are refused).
