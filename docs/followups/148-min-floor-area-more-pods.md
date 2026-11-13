# 148. Minimum floor area: red only when there is clearly no room for the pods it needs (RULED 2026-11-04).

148. [Claude] [scan: YES -- both ways] **Minimum floor area: red only when more pods clearly cannot fit.**
   Ruling 2026-11-04-min-floor-area-more-pods (flats/config/rulings.yaml), Steph: "anything that clearly
   cannot fit another pod is red and anything that clearly can is yellow. Unclear is yellow" -- the same
   rough count as 2026-10-21-wide-lot-frontage-more-pods (flats/score/screen.py _pods_to_fill, MORE_BUILDINGS).
   Today: the general `min_far` check is always YELLOW (SOFT_FLOOR_CHECKS, FAR-MIN flag); Portland's
   33.415 Centers Main Street minimum (`pdx_min_far`, flats/geom/pdx_overlays.py ~L841) is always RED --
   ~1,600 lots went red on it at run 78 (FOLLOWUPS 78). The Gateway / East Corridor map minimums
   (FOLLOWUPS 109 batch C, flats/districts-pdx-pd2c) use the general check.
   Build (Copilot brief docs/copilot/briefs/min-far-more-pods.txt): pods needed n = ceil(floor area the
   code needs / one pod's floor area); RED only when even the most lenient packing cannot hold n pods
   (buildable ground after setbacks smaller than n pod footprints); otherwise YELLOW with a flag that it
   needs more buildings; unknown ground = YELLOW. Never GREEN on a missed minimum. Then bound (Portland
   main street + every city with min_far), read: expect many Portland main-street red->yellow and some
   small-lot yellow->red elsewhere.
- 2026-11-13 move-read F1 fix-forward BUILT on flats/small-fixes-9 (rides rel9): on a part-overlay lot `_min_far_cannot_fit` (flats/geom/pdx_overlays.py) drops the floor of two pods and is RED only where stories x the buildable ground inside the overlay is below the floor needed. Run 124: 4 lots red only on `pdx_min_far`, all part-overlay, expected RED -> YELLOW (FAR-MIN): 1S1E23CD  -00900, 1N1W12AB  -07000, 1N1E36CB  -01100, 1N1E15CC  -14200. 1N1E22DD  -12801 now also fails fit_ft (pod80x30) and stays RED. Whole lots unchanged. Close when the bound read confirms.
