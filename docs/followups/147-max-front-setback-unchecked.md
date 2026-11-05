# 147. The maximum front setback is never checked on its own -- FALSE GREEN RISK (found 2026-11-04).

147. [Claude] [scan: YES -- toward red] **Maximum front setback never checked on its own -- FALSE GREEN RISK.**
   Found by the move read of the fire_rp3 bound (FOLLOWUPS 142a; scratch /root/fire_rp3_rd/ on 137).
   Tigard 2S103AA00300 (RES-B, max front setback 20 ft) is GREEN with its building drawn 60 ft from the
   street, in the BASE screen too, not only on the fire branch.
   Where it is used today: `setback_front_max_ft` only bounds the building-frontage share band
   (flats/ingest/quadfit.py share_band ~L4175, flats/score/screen.py ~L2745) and caps the flatter-ground
   search (flats/ingest/flatter.py _max_front_ft, which itself allows max(stated, where the plan already
   stands)), plus the Portland main-street overlay (flats/geom/pdx_overlays.py ~L1178). A zone with a
   maximum front setback but no building-frontage share has NO check that the drawn building stands
   within it. ~25 jurisdiction files carry the field (Gresham 27, Beaverton 27, Hillsboro 16, WashCo 10,
   Portland 9, Tigard 9, ...).
   Build: (1) count live greens/yellows whose drawn building stands beyond the stated maximum on every
   street the code applies it to; (2) a screen check: if a fitting placement within the maximum exists,
   draw there; if none fits, the plan fails the maximum (RED where the rule is clear, YELLOW where the
   street it applies to is unclear, e.g. a corner); unmeasured (no drawing/street line) = held, never
   GREEN. Status: encoder BUILDING 2026-11-04 (flats/max-front-setback).

## 2026-11-04 readings (flats-batch-reader) and round 2
- Read: Tigard quadplex 15/10 ft does NOT reach the pod (pod is a rowhouse in Tigard; a "quad" is 2-over-2) -- no false green. Beaverton MR maximum excludes townhouses (note 18) and reaches only 60.05.15.6 commercial/multiple-use -> exempt (~48 false red/yellow fixed). Portland EX Standard 2 and CI2/IR "within 100 ft" left unset (conservative; transit/pedestrian district not held). Which street per city encoded (front / every / one) for Oregon City C/R-2, WashCo TO zones, Milwaukie NMU, Estacada D, Gresham DCL/DMU/DEM, Fairview, Tualatin CC, West Linn MU, Wilsonville V, Troutdale MU-3, Hillsboro SCR-MD/SCR-V/MU-N (`one`: code says met when at least one facade is within it). King City, Gladstone C2, Oregon City MUC-2 stay unset.
- Coordinator decided: the maximum is measured from the line left after a street dedication (the same line the minimum yards use).
- Copilot round 2 (brief docs/copilot/briefs/max-front-setback-r2.txt) encoding the above; then bound (ahead of stall_w) + read.
- RULED 11-04 (rulings.yaml 2026-11-04-south-hillsboro-active-use-streets-traced): "Trace the sketch, green with a flag". Encoder building flats/hillsboro-active-streets (off 586a7b9b): trace Figure 12.65.930-A, 10/15 ft max + 75/70% coverage on that frontage, illustrative-map flag. Not ruled: whether the same sketch places the Town/Village Center cores (MU-VTC stays 3-storey RED everywhere).
- Round 2 committed 33911e99 + gaps 586a7b9b (pushed); bound max_front queued on 137 ahead of stall_w.
