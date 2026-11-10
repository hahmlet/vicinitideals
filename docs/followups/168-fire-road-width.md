# 168. Fire truck assumed on streets too narrow or dead ends without turnaround

From fg-rate-B (../vicinitideals-worktrees/fg-rate-B.md): the screen never checks the street can carry a fire truck.
Fix sketch: in flats/fit/fire.py, don't count a street as a truck road where the gap between lots on either side is
< 20 ft (OFC 503.2.1), nor a dead end > 150 ft without a turnaround (OFC 503.2.5). Lane fire-road off rel6 -> rel7.
BUILT 2026-11-09 flats/fire-road 164ddbfc (off rel6; ../vicinitideals-worktrees/fire-road.handoff.md): truck can't use <20 ft
gaps, networks reached only through them, dead ends >150 ft with no turnaround (hose from last truck point). Estimate vs run 122:
~1,170 GREEN->RED (~1,110 dead ends), ~100 GREEN->YELLOW, ~870 YELLOW->RED. Coordinator: use Portland PCC 31.30.010.B 300 ft
(local amendment governs) + other cities' amendments; re-estimate. ASKED Steph 2026-11-09: long EXISTING public dead ends with no
visible turnaround -> RED (code as written) or YELLOW (crews back in; fire marshal decides)? Recommended YELLOW + flag.
