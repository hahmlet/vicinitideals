# 142. Placement ignores fire reach; stall width; parking down a long lot (from the est_sc read, 2026-11-03).

142. [Claude] [Steph: (b), (c)] [scan: YES -- false reds only] **Placement ignores fire reach; stall width; parking down a long lot.**
   Found by the move read of the Estacada/Canby/Sandy stall-count bound (/root/est_sc, read scripts /root/est_sc_rd/ on 137).
   (a) [BUILT by Copilot bf18785e on flats/fire-reach-placement (pushed); needs bound + read every gain; hand-off ../vicinitideals-worktrees/fire-reach-placement.handoff.md] FALSE REDS, fix forward: Canby 31E33DC05001 and 31E34CC01800 go red on fire hose reach (187-203 ft vs
       150) on very large lots (~57,000 / ~48,000 sq ft buildable); live reached 123-145 ft. The bigger court
       flipped the building's orientation and fire reach plays no part in choosing the placement
       (flats/score/screen.py ~L2338-L2363). Same defect made Sandy 24E15AB06600 a false RED in live.
       Fix: when the chosen placement fails only on fire reach, try the other fitting placements before RED.
   (b) RULED Steph 2026-11-03 (rulings 2026-11-03-stall-width-city-minimum): CITY'S OWN WIDTH -- build next. Was: Canby allows 8.5 ft stalls and Estacada 8 ft, but the court is drawn at 9 ft.
       About 6 Canby lots and Estacada 34E17D 00700 miss only by that margin. Draw to the city's narrower
       stall (more lots, tighter parking) or keep 9 ft (safer)?
   (c) RULED Steph 2026-11-03 (2026-11-03-long-lot-parking-later): LATER, with FOLLOWUPS 92 -- nothing now. Was: on long narrow lots the parking could run down the lot's length instead of one
       row across the back; ~20 of the new Canby/Sandy reds are long enough. Overlaps the parking layout
       generator (FOLLOWUPS 92) -- try that layout?
- 2026-11-08 fire_rp5 READ: HOLD -- 1 wrong GREEN Milwaukie 12E30CD04700 (retry moved the court between building and street; MMC 19.505.3.D.4.a) + 4 unconfirmed yellows same defect; 3 greens right. Round 6 fix (re-check court position after the move) being built; rides flats/rescreen-1110. [Steph] OFFERED: in codes silent on it, may parking sit between the building and the street? Built as NO meanwhile.
- Steph 2026-11-08: NO front-yard parking in silent codes (rulings.yaml 2026-11-08-no-front-yard-parking-silent-codes, added on the fire placement branch with round 6).
- 2026-11-08 round 6 BUILT 9e9b4176 (flats/fire-reach-placement), rides flats/rescreen-1110. OPEN (needs its own bound, applies the 11-08 no-front-yard ruling beyond the fire retry): (1) first placement in flats/fit/draw.py -- through lot court behind faces the far street, corner court can face the side street, never re-read; (2) draw.py placement listing uses the weak 'building nearer the nearest street' test, also used by flatter.py (57); (3) fire_checked truck-served-front + other-angle redraws put the court toward the other street on through lots; (4) paper.py side_court on corners. Check against the through-lot/corner rulings (2026-09-30 access, 10-02/10-05 corners) before building.
- 2026-11-08 court-front-yard BUILT 78090cae (flats/court-front-yard, off rescreen-1110): all 4 places guarded; final check holds out of green. Answered from rulings: corner street-side yard in silent codes allowed; private road is a front only where the city counts it for setbacks (09-30). OPEN Steph (non-blocking, built YELLOW): through lot where the parking faces the back street's front yard -> yellow or red? Bound vs the re-screen output after it lands.
