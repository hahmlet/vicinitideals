# 148. Minimum floor area: red only when there is clearly no room for the pods it needs (RULED 2026-11-04)

[Claude] [scan: YES -- both ways]

DONE and live (run 118 2026-11-06, run 124 now): ruling 2026-11-04-min-floor-area-more-pods; 84db8b29, 27934967, f71cf172. Bound min_far read 11-05:
746 red->yellow, all right.

STILL OPEN (Claude, no Steph answer; wrong RED, not a false green) -- move-read F1 (../vicinitideals-worktrees/min-far-more-pods.moveread.md):
3 part-overlay Portland lots stay RED that should be YELLOW. `_min_far_cannot_fit` (flats/geom/pdx_overlays.py ~L1418) calls
`clearly_cannot_fit`, whose pod count is max(2, ...); on a part-overlay lot one pod moved onto the overlay part could meet the minimum.
Smallest fix: on a part-overlay lot count pods as ceil(needed / one pod's floor) with no floor of 2, and compare against stories x overlay
buildable area; RED only when that is below the floor needed. Test: part-overlay lot where one pod on the overlay part meets the minimum -> YELLOW.
