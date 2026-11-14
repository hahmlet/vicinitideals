# 191. Middle townhouse lots asked for the corner lot's frontage (possible false RED)

[Claude] [scan: YES -- toward yellow/green only]

Found 2026-11-14 by pagecheck-34 (../vicinitideals-worktrees/pagecheck-34.handoff.md, branch
flats/pagecheck-34 d9d9edda). The screen applies the corner-lot townhouse frontage (25 ft, Gresham
dc79bd29 corner change) to every middle townhouse lot, so a corner townhouse plat can never pass.
No GREEN depends on it (run 124: the 8 corner GREENs are the single-lot apartment form; every
townhouse GREEN is interior). Fix: corner figure on the corner lot only, interior figure on the rest;
read every gain in the bound.

Also for that lane: delete the three untied Hillsboro UC-AC / UC-MU / UC-RM 25 ft flag-lot frontage
entries (no passage sends the rule to these zones; harmless today because those flag lots are refused).
