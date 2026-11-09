# 8. Pockets + corridors -- leftovers (PROMOTED run 33 2026-09-27; pocket lots 210 -> 25 still ZONE_POCKET).

8. [Claude] [scan: NO new code, check after the weekly run; YES if (b) is taken up] **Pockets + corridors -- leftovers (PROMOTED run 33 2026-09-27; pocket
   lots 210 -> 25 still ZONE_POCKET).** All code is on main and in the
   weekly runs since run 65; the two checks below are not recorded as done.
   (a) e7217598 -- s3 follows FLATS's pocket rulings (Clackamas R-MD ->
   Milwaukie, Happy Valley VR57 -> county, UPAR-10 -> Troutdale LDR-1).
   Check: NOT_MEASURED -9 (check by the pocket_of TLIDs; drift skips
   pocket lots).
   (b) OPEN: 25 lots stay ZONE_POCKET: Troutdale NSA GGC/GSO and Oregon
   City `County` read against a map that answers no code the of-layer
   holds.
   (e) c9083b88 -- 33.130.215.B.1.b: CM2/CM3/CE/CX street lines take 5 ft,
   0 only where s4's `street_across_json` reads every ray across as
   non-residential and the line is off the corridor; quadfit CE/CM2/CM3/CX
   front 0 -> 5. Check: bound said ~60 lots green/unknown -> yellow, 0
   loosened.
   Done: (c) 1ff23bdb Map 130-1 maximum 20 ft (no screen reads a maximum,
   HUMAN_TODO 12); (d) fa693288 per-line corridor minimum, run 39.
- 2026-11-09 BOTH CHECKS DONE (flats/leftovers-a, read-only on 137 /root/assign_rescreen_1110):
  (a) the 8 pocket lots s3 re-homes (Clackamas R-MD -> Milwaukie 3, Happy Valley VR57 -> county 1,
  UPAR-10 -> Troutdale LDR-1 4; plus 215 King City WashCo pockets) all reach the screen (red/yellow),
  none NOT_MEASURED; NOT_MEASURED is now 67 (Clackamas SCMU 30, Portland CI1 36, Fairview VC 1), no
  pocket among them. (e) Portland CM2/CM3/CE/CX: 963 GREEN lots, 1,420 street lines, 513 not clear
  across (a residential RF-RM2/RMP ray, or a ray unread); 0 buildings drawn within 5 ft of one.
  Only (b) is left: ZONE_POCKET is 66 lots now (rulings on Troutdale NSA, Oregon City County and,
  since, Beaverton WAcnty).
