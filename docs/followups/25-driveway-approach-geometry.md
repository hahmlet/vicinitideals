# 25. Driveway approach geometry, ahead of a second approach (Steph 2026-09-30, flag only -- do not build yet).

25. [Claude] [scan: YES, when built (on hold)] **Driveway approach geometry, ahead of a second approach (Steph
   2026-09-30, flag only -- do not build yet).** What is measured today: the
   drive lane's width (`driveway_min_width_one_way_ft` / `_two_way_ft`, read
   by `flats/score/paper.py`) and the driveway's share of frontage
   (`driveway_max_frontage_pct`, `flats/score/screen.py`). What is encoded
   but read by NOTHING: the approach (curb cut) width,
   `driveway_approach_min_width_ft` / `_max_width_ft`, filled in 14
   jurisdiction files. Not encoded at all: spacing between approaches and
   from the corner (Oregon City Table 16.12.035.A, refused as NOT ENCODED),
   the 5 ft offset from the property line (OC note 2, a known live gap), and
   any "combine approaches"/one-per-frontage limits (OC 16.12.035.D: one per
   local frontage, never more than two). If the pod ever draws two
   approaches, all of these start to bind together: per-approach width,
   spacing between them, offset from lot lines, count per frontage. Since
   2026-10-10 Oregon City's second approach is overridden by state law
   (item 24), so the remaining trigger is Cornelius's two-lots-per-shared-
   driveway limit (item 24).
