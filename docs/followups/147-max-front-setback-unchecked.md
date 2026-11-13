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
- Coordinator 11-04: 12.65.130.A makes South Hillsboro max setback either/or (base zone OR 12.65.850), so the 10/15 ft adds no fail; the 75/70% Active Use frontage coverage binds (not under 130.A). Mixed-street corners YELLOW. Streets snapped to the regional layer on 137 (read-only). Figure: Municode PDF p889 (hash matches stored 12.65).
- RULED 11-04 (2026-11-04-south-hillsboro-centre-cores-traced): trace the Town/Village Center cores from the same figure; MU-VTC outside a core = GREEN+flag if it passes, inside = RED+flag. Encoder adding to flats/hillsboro-active-streets; hb_active bound re-pointed to the new head.
- Cores BUILT 8adfedd5 (Town 43 ac, Village 35 ac; MU-VTC min FAR 0.4/0.5 + 200 sq ft open space now encoded). 10 inside stay RED+flag; 156 outside, ~2 RED->YELLOW, rest fail size/fit/slope. Coordinator 11-04: 12.65.150.A counts free-standing residential toward FAR only "within an approved PUD" -- whether a lot is in one is unknown, so per ruling 2026-11-04-min-floor-area-more-pods (unclear = yellow) MU-VTC outside the cores stays YELLOW; not asked of Steph (~2 lots). hb_active re-pointed to 8adfedd5 + all MU-VTC.
- 2026-11-08 fix forward BUILT on flats/wrong-red-fixes (off rescreen-1110 0f2620b3): the slide's court test asked the whole drawn court on its ground, but the drawn court spans the lane into the side yard, so the slide never moved such a plan (its test passed only on the fire step's redraw); now the court may stand on its ground or where the plan's own court/lane stood. New snap: a wall up to 3 deg off its street is turned square about its near corner, then slid to the envelope's front edge (GREEN where it then clears). A slide that brings the near corner within but leaves the far end past is kept as the question (YELLOW, never GREEN). Needs a bound (every zone with setback_front_max_ft) + read; hand-off ../vicinitideals-worktrees/wrong-red-fixes.handoff.md. Portland CM2 1S2E17BA  -14300 not touched (unverified).
- 2026-11-08 rel3 READ: SHIP (../vicinitideals-worktrees/rel3.moveread.md, md5 94f88ae4...); release running. Fix forward: 3 Tigard RES-B wrong REDs 0.08-0.83 ft past the 20 ft max (2S103BA00137, 2S103DD00434, 2S103BA00108) -- let the slide to the maximum snap to the envelope's front edge; possible wrong RED Portland CM2 1S2E17BA  -14300 (16.52 vs 10 ft; facade-share measure?) check next round.
- 2026-11-13 CLOSED (small-fixes-9, no code change): Portland CM2 1S2E17BA  -14300 (7111 SE Foster Rd) is a TRUE RED on run 124. Corner lot on two streets (SE Foster, SE 71st), so 33.130.215.C.2.c holds the 10 ft maximum on both. The drawn pod stands 5.2 ft from Foster but 18.0 ft (17.3 after the strip) from 71st at its nearest point, so even the lenient reading misses. The fit has 1 ft of slack: the room (pod + rear court, 80 x 73 ft) is pinned by the north line and the Foster diagonal and cannot move west; turned it does not fit; court toward Foster puts the building 43+ ft off Foster. The 16.52 ft / 5.0 / 8.5 ft figures came from an earlier drawing.
