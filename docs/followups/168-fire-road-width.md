# 168. Fire truck assumed on streets too narrow or dead ends without turnaround

From fg-rate-B (../vicinitideals-worktrees/fg-rate-B.md): the screen never checks the street can carry a fire truck.
Fix sketch: in flats/fit/fire.py, don't count a street as a truck road where the gap between lots on either side is
< 20 ft (OFC 503.2.1), nor a dead end > 150 ft without a turnaround (OFC 503.2.5). Lane fire-road off rel6 -> rel7.
