# 142. Placement ignores fire reach; stall width; parking down a long lot (from the est_sc read, 2026-11-03).

142. [Claude] [Steph: (b), (c)] [scan: YES -- false reds only] **Placement ignores fire reach; stall width; parking down a long lot.**
   Found by the move read of the Estacada/Canby/Sandy stall-count bound (/root/est_sc, read scripts /root/est_sc_rd/ on 137).
   (a) [Copilot building 2026-11-03: flats/fire-reach-placement, brief docs/copilot/briefs/fire-reach-placement.txt] FALSE REDS, fix forward: Canby 31E33DC05001 and 31E34CC01800 go red on fire hose reach (187-203 ft vs
       150) on very large lots (~57,000 / ~48,000 sq ft buildable); live reached 123-145 ft. The bigger court
       flipped the building's orientation and fire reach plays no part in choosing the placement
       (flats/score/screen.py ~L2338-L2363). Same defect made Sandy 24E15AB06600 a false RED in live.
       Fix: when the chosen placement fails only on fire reach, try the other fitting placements before RED.
   (b) QUESTION for Steph: Canby allows 8.5 ft stalls and Estacada 8 ft, but the court is drawn at 9 ft.
       About 6 Canby lots and Estacada 34E17D 00700 miss only by that margin. Draw to the city's narrower
       stall (more lots, tighter parking) or keep 9 ft (safer)?
   (c) QUESTION for Steph: on long narrow lots the parking could run down the lot's length instead of one
       row across the back; ~20 of the new Canby/Sandy reds are long enough. Overlaps the parking layout
       generator (FOLLOWUPS 92) -- try that layout?
