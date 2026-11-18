# 148. Minimum floor area: red only when there is clearly no room for the pods it needs (RULED 2026-11-04)

[Claude] [scan: YES -- both ways]

DONE and live (run 118 2026-11-06, run 124 now): ruling 2026-11-04-min-floor-area-more-pods; 84db8b29, 27934967, f71cf172. Bound min_far read 11-05:
746 red->yellow, all right.

STILL OPEN (Claude, no Steph answer; wrong RED, not a false green) -- move-read F1 (../vicinitideals-worktrees/min-far-more-pods.moveread.md):
3 part-overlay Portland lots stay RED that should be YELLOW. `_min_far_cannot_fit` (flats/geom/pdx_overlays.py ~L1418) calls
`clearly_cannot_fit`, whose pod count is max(2, ...); on a part-overlay lot one pod moved onto the overlay part could meet the minimum.
Smallest fix: on a part-overlay lot count pods as ceil(needed / one pod's floor) with no floor of 2, and compare against stories x overlay
buildable area; RED only when that is below the floor needed. Test: part-overlay lot where one pod on the overlay part meets the minimum -> YELLOW.
- 2026-11-13 move-read F1 fix-forward BUILT on flats/small-fixes-9 (rides rel9): on a part-overlay lot `_min_far_cannot_fit` (flats/geom/pdx_overlays.py) drops the floor of two pods and is RED only where stories x the buildable ground inside the overlay is below the floor needed. Run 124: 4 lots red only on `pdx_min_far`, all part-overlay, expected RED -> YELLOW (FAR-MIN): 1S1E23CD  -00900, 1N1W12AB  -07000, 1N1E36CB  -01100, 1N1E15CC  -14200. 1N1E22DD  -12801 now also fails fit_ft (pod80x30) and stays RED. Whole lots unchanged. Close when the bound read confirms.
